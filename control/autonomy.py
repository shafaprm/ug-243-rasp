# control/autonomy.py
def clamp(x, lo, hi):
    return lo if x < lo else hi if x > hi else x

class AutonomyController:
    def __init__(self):
        self.stop_dist = 0.35
        self.slow_dist = 0.70

        # output limits supaya match dengan main.py kamu
        self.max_th = 0.6
        self.max_st = 1.0

    def compute_drive(self, min_front, avg_left, avg_right):
        """
        Returns:
          th_out in [-0.8, 0.8] (tapi kita batasi max_th)
          st_out in [-1.0, 1.0]
          auto_estop (bool) -> obstacle terlalu dekat
        """
        # obstacle kritis
        if min_front < self.stop_dist:
            return 0.0, 0.0, True

        # throttle: melambat saat mendekati obstacle
        if min_front < self.slow_dist:
            th = (min_front - self.stop_dist) / (self.slow_dist - self.stop_dist)
            th = clamp(th, 0.0, 1.0) * self.max_th
        else:
            th = self.max_th

        # steering: pilih sisi lebih lapang
        if avg_left > avg_right:
            st = +0.6 * self.max_st
        else:
            st = -0.6 * self.max_st

        # kalau depan sangat lapang → luruskan
        if min_front > 1.2:
            st *= 0.3

        return th, st, False
