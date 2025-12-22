# control/ps4_controller.py
import time
import select
from dataclasses import dataclass
from typing import Optional, Tuple

from evdev import InputDevice, ecodes, list_devices

# =====================
# AXES
# =====================
ABS_LX = ecodes.ABS_X       # Left stick X (steer)
ABS_L2 = ecodes.ABS_Z       # L2 trigger
ABS_R2 = ecodes.ABS_RZ      # R2 trigger

# Right stick (turret)
ABS_RX = ecodes.ABS_RX      # Right stick X (yaw)
ABS_RY = ecodes.ABS_RY      # Right stick Y (pitch)

# =====================
# BUTTONS
# =====================
BTN_FIRE = ecodes.BTN_WEST   # Square (umumnya)
BTN_ESTOP = ecodes.BTN_MODE  # PS button (opsional)

def clamp(x, lo, hi): return max(lo, min(hi, x))
def deadzone(x, dz): return 0.0 if abs(x) < dz else x

def get_abs_range(dev, code, fallback_min=0, fallback_max=255):
    try:
        info = dev.absinfo(code)
        return info.min, info.max
    except Exception:
        return fallback_min, fallback_max

def calibrate_idle(dev, code, seconds=0.7):
    end = time.time() + seconds
    vals = []
    while time.time() < end:
        r, _, _ = select.select([dev.fd], [], [], 0.05)
        if not r:
            continue
        for e in dev.read():
            if e.type == ecodes.EV_ABS and e.code == code:
                vals.append(e.value)
    if not vals:
        return None
    return int(sum(vals) / len(vals))

def trigger_to_norm(v, vmin, vmax, idle):
    v = clamp(v, vmin, vmax)
    if idle is None:
        idle = vmin
    idle = clamp(idle, vmin, vmax)

    # deteksi apakah trigger kebalik secara hardware
    dist_min = abs(idle - vmin)
    dist_max = abs(vmax - idle)
    inverted = dist_max < dist_min

    if inverted:
        denom = max(1, idle - vmin)
        norm = (idle - v) / denom
    else:
        denom = max(1, vmax - idle)
        norm = (v - idle) / denom

    return clamp(norm, 0.0, 1.0)

def norm_stick_to_unit(v, vmin, vmax):
    center = (vmin + vmax) / 2.0
    half = max(1.0, (vmax - vmin) / 2.0)
    x = (v - center) / half
    return clamp(x, -1.0, 1.0)

def is_main_ds4_device(dev: InputDevice) -> bool:
    name = (dev.name or "").lower()
    if "wireless controller" not in name:
        return False
    if "touchpad" in name or "motion" in name or "sensor" in name:
        return False
    caps = dev.capabilities()
    return (ecodes.EV_KEY in caps) and (ecodes.EV_ABS in caps)

def find_ds4_device() -> Optional[InputDevice]:
    for path in list_devices():
        d = InputDevice(path)
        if is_main_ds4_device(d):
            return d
    return None

# =====================
# CONFIG
# =====================
@dataclass
class PS4Config:
    deadzone_steer: float = 0.10
    deadzone_trig_norm: float = 0.03

    # deadzone right stick buat servo biar tidak jitter
    deadzone_turret: float = 0.08

    failsafe_sec: float = 2.0

# =====================
# CONTROLLER
# =====================
class PS4Controller:
    def __init__(self, cfg: PS4Config = PS4Config()):
        self.cfg = cfg
        self.dev: Optional[InputDevice] = None

        # ranges
        self.lx_min = -32768; self.lx_max = 32767
        self.rx_min = -32768; self.rx_max = 32767
        self.ry_min = -32768; self.ry_max = 32767

        self.l2_min = 0; self.l2_max = 255
        self.r2_min = 0; self.r2_max = 255

        self.idle_L2 = None
        self.idle_R2 = None

        # raw states
        self.lx_raw = 0
        self.rx_raw = 0
        self.ry_raw = 0
        self.raw_l2 = 0
        self.raw_r2 = 0

        self.last_input = time.time()

        # outputs (drive)
        self.steer = 0.0
        self.l2 = 0.0
        self.r2 = 0.0
        self.throttle = 0.0

        # outputs (turret)
        self.rx = 0.0
        self.ry = 0.0

        # buttons
        self.estop = False
        self._fire_pending = False

    def connect(self):
        dev = find_ds4_device()
        if not dev:
            raise RuntimeError("Tidak menemukan DS4 main input device. Pastikan controller connect via Bluetooth.")
        self.dev = dev
        print("Controller:", dev.path, "|", dev.name)

        # abs ranges (stick + triggers)
        self.lx_min, self.lx_max = get_abs_range(dev, ABS_LX, -32768, 32767)
        self.rx_min, self.rx_max = get_abs_range(dev, ABS_RX, -32768, 32767)
        self.ry_min, self.ry_max = get_abs_range(dev, ABS_RY, -32768, 32767)

        self.l2_min, self.l2_max = get_abs_range(dev, ABS_L2, 0, 255)
        self.r2_min, self.r2_max = get_abs_range(dev, ABS_R2, 0, 255)

        # init centers
        self.lx_raw = int((self.lx_min + self.lx_max) / 2)
        self.rx_raw = int((self.rx_min + self.rx_max) / 2)
        self.ry_raw = int((self.ry_min + self.ry_max) / 2)

        self.raw_l2 = self.l2_min
        self.raw_r2 = self.r2_min

        print("Calibrating triggers (lepas L2 & R2)...")
        self.idle_L2 = calibrate_idle(dev, ABS_L2)
        self.idle_R2 = calibrate_idle(dev, ABS_R2)
        print(f"Trigger idle: L2={self.idle_L2}  R2={self.idle_R2}")
        print("RUNNING. Square = FIRE.\n")

    def update(self):
        if not self.dev:
            return

        r, _, _ = select.select([self.dev.fd], [], [], 0.0)
        if r:
            for e in self.dev.read():
                if e.type == ecodes.EV_ABS:
                    if e.code == ABS_LX:
                        self.lx_raw = e.value
                        self.last_input = time.time()
                    elif e.code == ABS_RX:
                        self.rx_raw = e.value
                        self.last_input = time.time()
                    elif e.code == ABS_RY:
                        self.ry_raw = e.value
                        self.last_input = time.time()
                    elif e.code == ABS_L2:
                        self.raw_l2 = e.value
                        self.last_input = time.time()
                    elif e.code == ABS_R2:
                        self.raw_r2 = e.value
                        self.last_input = time.time()

                elif e.type == ecodes.EV_KEY:
                    if e.code == BTN_FIRE and e.value == 1:
                        self._fire_pending = True
                        self.last_input = time.time()
                    elif e.code == BTN_ESTOP and e.value == 1:
                        # toggle estop
                        self.estop = not self.estop
                        self.last_input = time.time()

        # failsafe: tidak ada input -> stop + turret center
        if time.time() - self.last_input > self.cfg.failsafe_sec:
            self.steer = 0.0
            self.l2 = 0.0
            self.r2 = 0.0
            self.throttle = 0.0
            self.rx = 0.0
            self.ry = 0.0
            return

        # drive
        self.steer = deadzone(
            norm_stick_to_unit(self.lx_raw, self.lx_min, self.lx_max),
            self.cfg.deadzone_steer
        )
        self.l2 = trigger_to_norm(self.raw_l2, self.l2_min, self.l2_max, self.idle_L2)
        self.r2 = trigger_to_norm(self.raw_r2, self.r2_min, self.r2_max, self.idle_R2)

        l2_use = 0.0 if self.l2 < self.cfg.deadzone_trig_norm else self.l2
        r2_use = 0.0 if self.r2 < self.cfg.deadzone_trig_norm else self.r2
        self.throttle = clamp(r2_use - l2_use, -1.0, 1.0)

        # turret (right stick, natural direction, NO invert)
        rx = norm_stick_to_unit(self.rx_raw, self.rx_min, self.rx_max)
        ry = norm_stick_to_unit(self.ry_raw, self.ry_min, self.ry_max)

        self.rx = deadzone(rx, self.cfg.deadzone_turret)
        self.ry = deadzone(ry, self.cfg.deadzone_turret)

    def consume_fire(self) -> bool:
        if self._fire_pending:
            self._fire_pending = False
            return True
        return False

    def get_manual_command(self) -> Tuple[float, float, float, float, bool, bool]:
        """
        Returns: (throttle, steer, rx, ry, fire_event, estop)
        rx, ry: right stick normalized [-1..1]
        """
        return (self.throttle, self.steer, self.rx, self.ry, self.consume_fire(), self.estop)
