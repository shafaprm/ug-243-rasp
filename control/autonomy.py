# control/autonomy.py
# Rule-based autonomy controller (front 90° only) with:
# - Emergency stop + lidar timeout fail-safe
# - Smooth throttle based on front distance
# - Gap-seeking steering (compare left vs right)
# - Hysteresis + commit time to avoid zig-zag
# - Output rate limiting (throttle/steer)
# - Simple recovery for "buntu" (stop -> reverse -> rotate)
#
# EXPECTED INPUTS (from your lidar processing):
#   front_dist : robust front distance (e.g., percentile-20% of sector Front, or avg/median)
#   min_front  : minimum front distance (for emergency stop)
#   left_dist  : robust left distance (Front-Left sector)
#   right_dist : robust right distance (Front-Right sector)
#
# If you only have (min_front, avg_left, avg_right) like your current code:
#   - map: left_dist=avg_left, right_dist=avg_right, front_dist=min_front (fallback)
#
# NOTE:
# - reverse without rear sensing is risky; this keeps reverse slow + short by default.


def clamp(x, lo, hi):
    return lo if x < lo else hi if x > hi else x


def sign(x, default=1.0):
    if x > 0:
        return 1.0
    if x < 0:
        return -1.0
    return default


def rate_limit(current, target, max_delta):
    """Limit change per call: current -> target with step <= max_delta."""
    if target > current + max_delta:
        return current + max_delta
    if target < current - max_delta:
        return current - max_delta
    return target


class AutonomyController:
    """
    Outputs:
      th_out : throttle command in [-max_th, +max_th] (forward positive)
      st_out : steering command in [-max_st, +max_st] (left negative, right positive by convention)
      auto_estop : bool
    """

    def __init__(self):
        # === Distance thresholds (meters) ===
        self.stop_dist = 0.40     # D_STOP (emergency stop)
        self.slow_dist = 1.00     # D_SLOW (start slowing down)
        self.clear_dist = 1.80    # D_CLEAR (consider "front is clear")
        self.bottleneck_dist = 0.70  # for buntu detection (all near)

        # Optional side safety (slow down if side very close even if front is clear)
        self.side_safe_dist = 0.55

        # === Output limits ===
        self.max_th = 0.60  # match your main.py scaling
        self.max_st = 1.00

        # Reverse safety
        self.max_rev_th = 0.20  # slow reverse

        # === Anti zig-zag ===
        self.hyst = 0.25         # meters (difference needed to switch turn preference)
        self.commit_time = 0.50  # seconds to "commit" to chosen turn direction

        # === Rate limiting (per call) ===
        # Choose values assuming compute_drive called at ~10–30 Hz.
        self.th_rate = 0.06  # max throttle change per call
        self.st_rate = 0.12  # max steer change per call

        # === Lidar timeout fail-safe ===
        self.timeout_s = 0.35

        # === Smoothing (simple 1st-order low-pass) ===
        self.alpha = 0.35  # 0..1, higher = less smoothing

        # === Internal state ===
        self._last_time = None
        self._last_lidar_time = None

        self._front_s = None
        self._left_s = None
        self._right_s = None
        self._min_front_s = None

        self._last_th = 0.0
        self._last_st = 0.0

        self._turn_dir = 0          # -1 left, +1 right, 0 unknown
        self._commit_until = 0.0

        self._state = "RUN"         # RUN / RECOVERY_STOP / RECOVERY_REVERSE / RECOVERY_ROTATE
        self._state_until = 0.0

        self._last_auto_estop = False

    # ---------- Helpers ----------
    def _now(self, now):
        """Allow caller to pass `now` (monotonic seconds). If None, use time.monotonic()."""
        if now is not None:
            return float(now)
        # Import lazily so file can be used in constrained envs
        import time
        return time.monotonic()

    def _is_valid_dist(self, d):
        return d is not None and d > 0.0

    def _smooth(self, prev, new):
        if prev is None:
            return new
        return (1.0 - self.alpha) * prev + self.alpha * new

    def _map_front_to_throttle(self, front_dist, steer_abs):
        """
        Rule:
          - If front <= stop_dist -> 0 (handled elsewhere)
          - If stop_dist..slow_dist -> ramp 0..max_th
          - If >= slow_dist -> max_th
          - Additionally reduce speed when turning sharply
          - Additionally reduce speed if sides are very close
        """
        if front_dist <= self.stop_dist:
            base = 0.0
        elif front_dist < self.slow_dist:
            # linear ramp between stop_dist and slow_dist
            t = (front_dist - self.stop_dist) / (self.slow_dist - self.stop_dist)
            base = clamp(t, 0.0, 1.0) * self.max_th
        else:
            base = self.max_th

        # Slow down when steering sharply (turning penalty)
        # a=0.55 means at full steer, speed ~45% of base
        a = 0.55
        turn_limit = self.max_th * (1.0 - a * clamp(steer_abs, 0.0, 1.0))
        base = min(base, turn_limit)

        return clamp(base, 0.0, self.max_th)

    def _choose_turn_dir(self, left_dist, right_dist, now):
        """
        Gap seeking with hysteresis + commit time.
        We treat larger distance = more open.
        """
        # Determine raw preference
        diff = right_dist - left_dist  # >0 means right more open
        raw_dir = +1 if diff > 0 else -1

        # If no prior direction, take raw
        if self._turn_dir == 0:
            self._turn_dir = raw_dir
            self._commit_until = now + self.commit_time
            return self._turn_dir

        # If still in commit window, keep direction
        if now < self._commit_until:
            return self._turn_dir

        # Past commit: switch only if strong enough (hysteresis)
        if self._turn_dir == +1:
            # currently right; switch to left only if left is clearly better
            if (left_dist - right_dist) > self.hyst:
                self._turn_dir = -1
                self._commit_until = now + self.commit_time
        else:
            # currently left; switch to right only if right clearly better
            if (right_dist - left_dist) > self.hyst:
                self._turn_dir = +1
                self._commit_until = now + self.commit_time

        return self._turn_dir

    def _steer_from_gap(self, left_dist, right_dist, front_dist):
        """
        Produce steer magnitude based on how different left vs right is.
        Simple proportional scaling + clamp.
        Convention here: left negative, right positive.
        """
        diff = right_dist - left_dist  # meters
        # gain: tune based on your lidar ranges
        k = 0.55
        steer = clamp(k * diff, -1.0, 1.0)

        # If front is very clear, straighten (reduce steer)
        if front_dist >= self.clear_dist:
            steer *= 0.30

        return clamp(steer, -self.max_st, self.max_st)

    def _detect_bottleneck(self, left_dist, front_dist, right_dist):
        return (
            left_dist < self.bottleneck_dist
            and front_dist < self.bottleneck_dist
            and right_dist < self.bottleneck_dist
        )

    def _apply_limits_and_rate(self, th_target, st_target):
        # clamp
        th_target = clamp(th_target, -self.max_th, self.max_th)
        st_target = clamp(st_target, -self.max_st, self.max_st)

        # rate limit from last outputs
        th_out = rate_limit(self._last_th, th_target, self.th_rate)
        st_out = rate_limit(self._last_st, st_target, self.st_rate)

        self._last_th = th_out
        self._last_st = st_out
        return th_out, st_out

    # ---------- Public API ----------
    def compute_drive(
        self,
        min_front,
        avg_left,
        avg_right,
        front_dist=None,
        left_dist=None,
        right_dist=None,
        now=None,
        lidar_timestamp=None,
        lidar_valid=True,
    ):
        """
        Backward compatible with your original signature:
          compute_drive(min_front, avg_left, avg_right)

        Recommended usage (after you split 90° front into sectors):
          compute_drive(
              min_front=min_front,
              avg_left=fl_p20,
              avg_right=fr_p20,
              front_dist=f_p20,
              left_dist=fl_p20,
              right_dist=fr_p20,
              lidar_timestamp=now_monotonic,
          )

        Args:
          min_front : minimum distance in front sector (emergency stop trigger)
          avg_left  : robust distance in front-left sector (kept for compatibility)
          avg_right : robust distance in front-right sector (kept for compatibility)
          front_dist / left_dist / right_dist : preferred explicit distances (override avg_*)
          now : monotonic seconds (optional)
          lidar_timestamp : monotonic seconds of last lidar update (optional)
          lidar_valid : set False if data invalid/too few points
        """
        now = self._now(now)

        # Track lidar update time (for timeout)
        if lidar_timestamp is not None:
            self._last_lidar_time = float(lidar_timestamp)
        elif self._last_lidar_time is None:
            # If caller doesn't provide timestamps, assume "fresh" each call
            self._last_lidar_time = now

        # Timeout check
        if (now - self._last_lidar_time) > self.timeout_s:
            # Fail-safe stop
            th_out, st_out = self._apply_limits_and_rate(0.0, 0.0)
            self._last_auto_estop = True
            self._state = "RUN"  # reset state on sensor fault
            return th_out, st_out, True

        # Determine which distances to use (prefer explicit sector distances)
        ld = left_dist if self._is_valid_dist(left_dist) else avg_left
        rd = right_dist if self._is_valid_dist(right_dist) else avg_right
        fd = front_dist if self._is_valid_dist(front_dist) else min_front  # fallback

        # Validate basic numeric inputs
        if not (self._is_valid_dist(min_front) and self._is_valid_dist(ld) and self._is_valid_dist(rd) and self._is_valid_dist(fd)):
            # Invalid ranges -> stop
            th_out, st_out = self._apply_limits_and_rate(0.0, 0.0)
            self._last_auto_estop = True
            self._state = "RUN"
            return th_out, st_out, True

        if not lidar_valid:
            # Data exists but flagged unreliable -> conservative slow/stop
            th_out, st_out = self._apply_limits_and_rate(0.0, 0.0)
            self._last_auto_estop = True
            self._state = "RUN"
            return th_out, st_out, True

        # Smooth distances (optional but helps stability)
        self._front_s = self._smooth(self._front_s, fd)
        self._left_s = self._smooth(self._left_s, ld)
        self._right_s = self._smooth(self._right_s, rd)
        self._min_front_s = self._smooth(self._min_front_s, min_front)

        fd_s = self._front_s
        ld_s = self._left_s
        rd_s = self._right_s
        minf_s = self._min_front_s

        # ----- Priority 1: Emergency stop -----
        if minf_s < self.stop_dist:
            # If looks like bottleneck, enter recovery sequence
            if self._detect_bottleneck(ld_s, fd_s, rd_s):
                self._state = "RECOVERY_STOP"
                self._state_until = now + 0.30  # stop pause
            th_out, st_out = self._apply_limits_and_rate(0.0, 0.0)
            self._last_auto_estop = True
            return th_out, st_out, True

        # ----- Recovery state machine (optional) -----
        if self._state.startswith("RECOVERY"):
            # Decide preferred turn direction based on openness
            # Note: steer sign convention left negative, right positive
            preferred_dir = +1 if rd_s > ld_s else -1

            if self._state == "RECOVERY_STOP":
                if now < self._state_until:
                    th_out, st_out = self._apply_limits_and_rate(0.0, 0.0)
                    return th_out, st_out, True
                # move to reverse
                self._state = "RECOVERY_REVERSE"
                self._state_until = now + 0.60
                # fallthrough

            if self._state == "RECOVERY_REVERSE":
                if now < self._state_until:
                    # reverse slowly with slight steer toward more open side
                    th_t = -self.max_rev_th
                    st_t = 0.25 * preferred_dir
                    th_out, st_out = self._apply_limits_and_rate(th_t, st_t)
                    return th_out, st_out, False
                # move to rotate
                self._state = "RECOVERY_ROTATE"
                self._state_until = now + 0.90
                # fallthrough

            if self._state == "RECOVERY_ROTATE":
                if now < self._state_until:
                    # rotate / aggressive turn-in-place (approx) at low forward throttle
                    # If your mixer supports true rotate-in-place, you can set speed small and steer high.
                    th_t = 0.18
                    st_t = 0.85 * preferred_dir
                    th_out, st_out = self._apply_limits_and_rate(th_t, st_t)
                    return th_out, st_out, False

                # Done recovery
                self._state = "RUN"

        # ----- Normal RUN behavior -----

        # Pick/keep a turn direction using hysteresis + commit time (for stability)
        self._choose_turn_dir(ld_s, rd_s, now)

        # Steering from gap (continuous, but you can quantize if you prefer)
        st_target = self._steer_from_gap(ld_s, rd_s, fd_s)

        # Optional: if side too close, bias steering away and reduce speed a bit
        if ld_s < self.side_safe_dist and rd_s >= ld_s:
            # left very close -> steer right
            st_target = max(st_target, +0.35)
        elif rd_s < self.side_safe_dist and ld_s >= rd_s:
            # right very close -> steer left
            st_target = min(st_target, -0.35)

        # Throttle based on front distance + turning penalty
        th_target = self._map_front_to_throttle(fd_s, abs(st_target))

        # Extra slowdown if both sides are close (tight corridor)
        if min(ld_s, rd_s) < self.side_safe_dist:
            th_target = min(th_target, 0.45 * self.max_th)

        # Output with rate limiting
        th_out, st_out = self._apply_limits_and_rate(th_target, st_target)

        # auto_estop only for emergency stop / timeout in this implementation
        self._last_auto_estop = False
        return th_out, st_out, False
