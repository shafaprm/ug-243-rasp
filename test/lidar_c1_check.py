#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import time
from core.lidar_sensor import LidarC1

def main():
    port = "/dev/ttyUSB0"
    baud = 460800

    lidar = None
    try:
        lidar = LidarC1(port, baud)

        print("RPLIDAR C1 test started")
        print("Press Ctrl+C to stop")
        print("-" * 60)

        last = 0.0
        while True:
            now = time.time()

            # read at ~5 Hz (lightweight)
            if now - last >= 0.2:
                last = now

                min_f, avg_l, avg_r = lidar.read_sectors()

                age = getattr(lidar, "last_age_s", None)
                age_s = age() if callable(age) else None

                age_str = "-" if age_s is None else f"{age_s:.2f}s"
                print(
                    f"min_front={min_f:>5.2f} m | "
                    f"avg_left={avg_l:>5.2f} m | "
                    f"avg_right={avg_r:>5.2f} m | "
                    f"age={age_str}"
                )

            time.sleep(0.02)

    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        if lidar is not None:
            try:
                lidar.close()
            except Exception:
                pass

if __name__ == "__main__":
    main()
