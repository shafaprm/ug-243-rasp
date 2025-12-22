import time

from config import SERIAL_PORT, BAUDRATE, CONTROL_HZ, TELEMETRY_PRINT_HZ
from comm.serial_link import SerialLink
from control.ps4_controller import PS4Controller
import json

def clamp(x, lo, hi):
    return lo if x < lo else hi if x > hi else x

def main():
    link = SerialLink(SERIAL_PORT, BAUDRATE)
    link.open()

    ps4 = PS4Controller()
    ps4.connect()

    dt = 1.0 / CONTROL_HZ
    t0 = time.time()
    BOOT_SAFE_SEC = 8.0
    last_print = 0.0

    mode = "manual"
    estop = False

    try:
        while True:
            now = time.time()
            ms = int((now - t0) * 1000)

            ps4.update()

            # NEW: now returns (throttle, steer, rx, ry, fire_event, estop)
            throttle, steer, rx, ry, fire_event, estop_from_pad = ps4.get_manual_command()

            # estop dari controller (opsional toggle PS button)
            estop = estop_from_pad

            # Safety clamp untuk test awal (boleh kamu naikkan nanti)
            throttle = clamp(throttle, -0.8, 0.8)
            steer = clamp(steer, -1.0, 1.0)

            # rx/ry untuk turret juga kita clamp supaya bersih
            rx = clamp(rx, -1.0, 1.0)
            ry = clamp(ry, -1.0, 1.0)

            # Boot-safe: selama 8 detik pertama, semua output dinolkan + estop dipaksa true
            elapsed = now - t0
            boot_safe = elapsed < BOOT_SAFE_SEC

            mode = "safe" if boot_safe else "manual"
            estop = True if boot_safe else estop_from_pad

            # Drive safe
            th_out = 0.0 if boot_safe else throttle
            st_out = 0.0 if boot_safe else steer

            # Turret safe (center)
            rx_out = 0.0 if boot_safe else rx
            ry_out = 0.0 if boot_safe else ry
            fire_out = False if boot_safe else fire_event

            cmd = {
                "t": ms,
                "cmd": "set",
                "mode": mode,
                "estop": estop,
                "drive": {"th": th_out, "st": st_out},
                "turret": {
                    "rx": rx_out,   # right stick X -> yaw (A2)
                    "ry": ry_out,   # right stick Y -> pitch (A1)
                    "fire": fire_out,  # square button -> fire servo (A0)
                },
            }

            link.send(cmd)

            telem = link.recv_latest()
            if telem and (now - last_print) > (1.0 / TELEMETRY_PRINT_HZ):
                last_print = now
                print("TELEM:", telem)
                print("TX:", json.dumps(cmd, separators=(',', ':')))

            time.sleep(dt)

    except KeyboardInterrupt:
        pass
    finally:
        # kirim stop sekali sebelum close
        try:
            link.send({
                "cmd": "set",
                "mode": "safe",
                "estop": True,
                "drive": {"th": 0.0, "st": 0.0},
                "turret": {"rx": 0.0, "ry": 0.0, "fire": False},
            })
        except Exception:
            pass
        link.close()

if __name__ == "__main__":
    main()
