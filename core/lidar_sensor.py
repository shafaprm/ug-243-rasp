# core/lidar_sensor.py
import asyncio
import threading
import time
from typing import Dict, Optional, Tuple

# rplidarc1 package provides RPLidar class (async scanning) in scanner.py
from rplidarc1.scanner import RPLidar  # works with installed package layout

def _angle_diff(a: float, b: float) -> float:
    return (a - b + 180.0) % 360.0 - 180.0

def _in_sector(angle_deg: float, center_deg: float, half_width_deg: float) -> bool:
    return abs(_angle_diff(angle_deg, center_deg)) <= half_width_deg

def _clean_dist_m(dist_mm) -> Optional[float]:
    if dist_mm is None:
        return None
    try:
        d_mm = float(dist_mm)
    except Exception:
        return None
    if d_mm <= 0:
        return None
    d = d_mm / 1000.0
    if d < 0.10 or d > 12.0:
        return None
    return d

class LidarC1:
    """
    Threaded wrapper for rplidarc1's asyncio scanner.
    Keeps latest output_dict snapshot for synchronous consumers (main loop).
    """
    def __init__(self, port="/dev/ttyUSB0", baud=460800, mirror_angle=False):
        self._lidar = RPLidar(port, baudrate=baud, timeout=0.2)
        self._mirror_angle = mirror_angle
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self._lock = threading.Lock()
        self._last_dict: Dict[float, int] = {}
        self._last_update_ts = 0.0

        self.start()

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run_async, daemon=True)
        self._thread.start()

    def close(self):
        self._stop.set()
        # signal async stop_event if possible
        try:
            self._lidar.stop_event.set()
        except Exception:
            pass
        # wait a bit for thread to exit
        if self._thread:
            self._thread.join(timeout=2.0)
        # reset/shutdown lidar
        try:
            self._lidar.reset()
        except Exception:
            pass
        try:
            self._lidar.shutdown()
        except Exception:
            pass

    @property
    def last_age_s(self) -> float:
        ts = self._last_update_ts
        if ts <= 0:
            return 999.0
        return time.time() - ts

    def _run_async(self):
        async def _runner():
            # run scanning continuously, update output_dict
            while not self._stop.is_set():
                try:
                    # start scan task, store dict internally
                    # make_return_dict=True => fills self._lidar.output_dict (angle -> distance)
                    await self._lidar.simple_scan(make_return_dict=True)
                except Exception:
                    # brief backoff on errors
                    await asyncio.sleep(0.2)

        try:
            asyncio.run(_runner())
        except Exception:
            # if event loop crashed, nothing else to do; main will detect stale age
            pass

    def read_sectors(self) -> Tuple[float, float, float]:
        """
        Return (min_front_m, avg_left_m, avg_right_m) from latest output_dict snapshot.
        Sectors:
          front: 0°±30°
          left:  60°±30° (30..90)
          right: 300°±30° (270..330)
        """
        # snapshot latest dict from lidar object
        d = {}
        try:
            # copy from library's output_dict
            d = dict(self._lidar.output_dict)  # angle -> distance_mm
        except Exception:
            d = {}

        # update last snapshot age marker
        with self._lock:
            self._last_dict = d
            self._last_update_ts = time.time()

        front = []
        left = []
        right = []

        for a, dist_mm in d.items():
            try:
                angle = float(a)
            except Exception:
                continue
            if self._mirror_angle:
                angle = (360.0 - angle) % 360.0
            dist = _clean_dist_m(dist_mm)
            if dist is None:
                continue

            if _in_sector(angle, 0.0, 30.0):
                front.append(dist)
            elif _in_sector(angle, 60.0, 30.0):
                left.append(dist)
            elif _in_sector(angle, 300.0, 30.0):
                right.append(dist)

        min_front = min(front) if front else float("inf")
        avg_left = (sum(left) / len(left)) if left else 0.0
        avg_right = (sum(right) / len(right)) if right else 0.0
        return min_front, avg_left, avg_right
