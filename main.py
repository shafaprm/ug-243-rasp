# main.py (fixed: aim source toggle + dashboard turret override via UDP 15556)
import time
import curses
import threading

from core.lidar_sensor import LidarC1
from comm.serial_link import SerialLink
from control.ps4_controller import PS4Controller
from control.autonomy import AutonomyController
from dashboard.backend.udp_bus import make_udp_sender
from tools.live_tui import LiveTUI
from config import (
    SERIAL_PORT, BAUDRATE, CONTROL_HZ,
    DASH_UDP_HOST, DASH_UDP_PORT, DASH_PUB_TELEM_HZ, DASH_PUB_TX_HZ
)

from comm.cmd_udp import CmdUdpRx

# =========================
# GLOBAL FEATURE FLAGS
# =========================
USE_TUI = True
USE_DASHBOARD = True
USE_LIDAR = True

LIDAR_HZ = 5.0
BOOT_SAFE_SEC = 8.0

# Dashboard -> local command UDP (IN)
CMD_UDP_HOST = "0.0.0.0"
CMD_UDP_PORT = 15556


def clamp(x, lo, hi):
    return lo if x < lo else hi if x > hi else x


def clampf(v, lo=-1.0, hi=1.0) -> float:
    try:
        x = float(v)
    except Exception:
        x = 0.0
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x


def main():
    # -------------------------
    # Serial link (Arduino)
    # -------------------------
    link = SerialLink(SERIAL_PORT, BAUDRATE)
    link.open()

    # -------------------------
    # Dashboard UDP publish OUT (optional)
    # -------------------------
    udp_send = make_udp_sender(DASH_UDP_HOST, DASH_UDP_PORT) if USE_DASHBOARD else None
    last_pub_telem = 0.0
    last_pub_tx = 0.0

    # -------------------------
    # Dashboard command receiver (aim toggle + click)
    # -------------------------
    cmdrx = CmdUdpRx(CMD_UDP_HOST, CMD_UDP_PORT)

    # -------------------------
    # PS4 Controller
    # -------------------------
    ps4 = PS4Controller()
    ps4.connect()

    # -------------------------
    # TUI (optional)
    # -------------------------
    tui = LiveTUI(refresh_hz=1.0, show_flat=True) if USE_TUI else None

    # -------------------------
    # Timing
    # -------------------------
    dt = 1.0 / max(1, CONTROL_HZ)
    t0 = time.time()

    # -------------------------
    # Autonomy + LiDAR
    # -------------------------
    auto = AutonomyController()
    auto_enabled = False

    lidar = None
    lidar_lock = threading.Lock()
    lidar_cache = {"min_f": None, "avg_l": None, "avg_r": None, "ts": 0.0}

    if USE_LIDAR:
        try:
            lidar = LidarC1("/dev/ttyUSB0", 460800, mirror_angle=True)
        except Exception:
            lidar = None

    stop_flag = threading.Event()

    def lidar_poller():
        period = 1.0 / max(1e-6, LIDAR_HZ)
        next_poll = time.time()
        while not stop_flag.is_set():
            if lidar is not None:
                try:
                    mf, al, ar = lidar.read_sectors()
                    with lidar_lock:
                        lidar_cache["min_f"] = mf
                        lidar_cache["avg_l"] = al
                        lidar_cache["avg_r"] = ar
                        lidar_cache["ts"] = time.time()
                except Exception:
                    with lidar_lock:
                        lidar_cache["min_f"] = None
                        lidar_cache["avg_l"] = None
                        lidar_cache["avg_r"] = None
                        lidar_cache["ts"] = time.time()

            next_poll += period
            sleep_s = next_poll - time.time()
            if sleep_s > 0:
                time.sleep(sleep_s)
            else:
                next_poll = time.time()

    if USE_LIDAR and lidar is not None:
        threading.Thread(target=lidar_poller, daemon=True).start()

    # -------------------------
    # Aim source + dashboard target cache
    # -------------------------
    aim_source = "controller"  # "controller" | "dashboard"

    # hold last dashboard target so no spam needed
    dash_hold = {"rx": 0.0, "ry": 0.0, "fire": False}
    dash_hold_until = 0.0  # "fresh" window (optional)

    def loop(stdscr=None):
        nonlocal t0, last_pub_tx, last_pub_telem, auto_enabled
        nonlocal aim_source, dash_hold, dash_hold_until

        if stdscr is not None:
            curses.curs_set(0)
            stdscr.nodelay(True)
            stdscr.timeout(0)

        next_tick = time.time()

        while True:
            loop_start = time.time()
            now = loop_start
            ms = int((now - t0) * 1000)

            # -------------------------
            # Keypress (optional)
            # -------------------------
            if stdscr is not None and tui is not None:
                ch = stdscr.getch()
                if ch == ord("q"):
                    break
                elif ch == ord("a"):
                    auto_enabled = not auto_enabled
                elif ch == ord("f"):
                    tui.show_flat = not tui.show_flat
                elif ch == ord("+"):
                    tui.refresh_dt = max(0.05, tui.refresh_dt / 1.5)
                elif ch == ord("-"):
                    tui.refresh_dt = min(5.0, tui.refresh_dt * 1.5)

            # -------------------------
            # Read dashboard UDP (non-blocking)
            # -------------------------
            dash_cmd = cmdrx.poll_latest()
            if dash_cmd:
                c = dash_cmd.get("cmd")

                # Aim toggle: {"cmd":"aim","aim_source":"dashboard","ts":...}
                if isinstance(c, str) and c == "aim":
                    src = dash_cmd.get("aim_source")
                    if src in ("controller", "dashboard"):
                        aim_source = src

                # Click payload: {"cmd":{...,"turret":{"rx":..,"ry":..,"fire":..}},"meta":...,"ts":...}
                if isinstance(c, dict):
                    t = c.get("turret")
                    if isinstance(t, dict) and ("rx" in t) and ("ry" in t):
                        dash_hold = {
                            "rx": clampf(t.get("rx", dash_hold["rx"])),
                            "ry": clampf(t.get("ry", dash_hold["ry"])),
                            "fire": bool(t.get("fire", dash_hold["fire"])),
                        }
                        dash_hold_until = time.time() + 1.5  # hold "fresh" 1.5s

            # -------------------------
            # Read PS4
            # -------------------------
            ps4.update()
            throttle, steer, rx, ry, fire_event, estop_from_pad = ps4.get_manual_command()

            # -------------------------
            # Boot-safe
            # -------------------------
            elapsed = now - t0
            boot_safe = elapsed < BOOT_SAFE_SEC

            mode = "safe" if boot_safe else "manual"
            estop = True if boot_safe else estop_from_pad

            # drive defaults
            th_out = 0.0 if boot_safe else clamp(throttle, -0.8, 0.8)
            st_out = 0.0 if boot_safe else clamp(steer, -1.0, 1.0)

            # controller turret defaults
            rx_out = 0.0 if boot_safe else clamp(rx, -1.0, 1.0)
            ry_out = 0.0 if boot_safe else clamp(ry, -1.0, 1.0)
            fire_out = False if boot_safe else fire_event

            # -------------------------
            # Read LiDAR cache
            # -------------------------
            with lidar_lock:
                min_f = lidar_cache["min_f"]
                avg_l = lidar_cache["avg_l"]
                avg_r = lidar_cache["avg_r"]
                lidar_ts = lidar_cache["ts"]

            # -------------------------
            # AUTO override (drive only)
            # -------------------------
            if (not boot_safe) and auto_enabled and (lidar is not None) and (not estop):
                try:
                    if min_f is None:
                        raise RuntimeError("lidar not ready")

                    th_auto, st_auto, auto_estop = auto.compute_drive(min_f, avg_l, avg_r)

                    mode = "auto"
                    th_out = clamp(th_auto, -0.8, 0.8)
                    st_out = clamp(st_auto, -1.0, 1.0)

                    if auto_estop:
                        mode = "safe"
                        estop = True
                        th_out = 0.0
                        st_out = 0.0
                except Exception:
                    mode = "manual"

            # -------------------------
            # Turret mux: controller vs dashboard
            # -------------------------
            if boot_safe:
                turret_out = {"rx": 0.0, "ry": 0.0, "fire": False}
                turret_mode = 0
            else:
                if aim_source == "dashboard":
                    turret_mode = 1  # POS mode

                    # IMPORTANT: do not reset to 0 when no new click.
                    turret_out = dash_hold

                    # allow controller fire even in dashboard aim (optional)
                    if fire_out:
                        turret_out = {**turret_out, "fire": True}
                else:
                    turret_mode = 0  # RATE mode
                    turret_out = {"rx": rx_out, "ry": ry_out, "fire": fire_out}

            # -------------------------
            # Build Arduino command
            # -------------------------
            cmd_arduino = {
                "t": ms,
                "cmd": "set",
                "mode": mode,
                "estop": estop,
                "drive": {"th": th_out, "st": st_out},
                "turret": {
                    "rx": float(turret_out["rx"]),
                    "ry": float(turret_out["ry"]),
                    "fire": bool(turret_out["fire"]),
                    "mode": int(turret_mode),
                },
            }

            link.send(cmd_arduino)

            # -------------------------
            # Telemetry
            # -------------------------
            telem = link.recv_latest()

            # -------------------------
            # Debug packet (dashboard/TUI)
            # -------------------------
            loop_cost_ms = (time.time() - loop_start) * 1000.0
            debug = {
                "ts": now,
                "src": "pi",
                "cmd": cmd_arduino,
                "meta": {
                    "aim_source": aim_source,
                    "dash_cmd_age_s": cmdrx.age_s,
                    "loop_cost_ms": loop_cost_ms,
                    "auto_enabled": auto_enabled,
                    "lidar": {
                        "min_front": min_f,
                        "avg_left": avg_l,
                        "avg_right": avg_r,
                        "age_s": (now - lidar_ts) if lidar_ts else None,
                    },
                },
                "telem": telem,
            }

            # publish to dashboard (optional)
            if USE_DASHBOARD and udp_send is not None:
                if (now - last_pub_tx) >= (1.0 / max(1, DASH_PUB_TX_HZ)):
                    last_pub_tx = now
                    udp_send({"ts": now, "src": "pi", "type": "tx", "data": debug})

                if telem and (now - last_pub_telem) >= (1.0 / max(1, DASH_PUB_TELEM_HZ)):
                    last_pub_telem = now
                    udp_send({"ts": now, "src": "arduino", "type": "telem", "data": telem})

            # TUI
            if stdscr is not None and tui is not None:
                tui.update(
                    stdscr=stdscr,
                    now=now,
                    telem=telem,
                    cmd=debug,
                    link_age_s=link.last_rx_age_s,
                )

            # pacing
            next_tick += dt
            sleep_s = next_tick - time.time()
            if sleep_s > 0:
                time.sleep(sleep_s)
            else:
                next_tick = time.time()

    try:
        if USE_TUI:
            curses.wrapper(loop)
        else:
            loop(None)
    finally:
        stop_flag.set()

        try:
            cmdrx.close()
        except Exception:
            pass

        # safe-stop
        try:
            link.send({
                "cmd": "set",
                "mode": "safe",
                "estop": True,
                "drive": {"th": 0.0, "st": 0.0},
                "turret": {"rx": 0.0, "ry": 0.0, "fire": False, "mode": 0},
            })
        except Exception:
            pass

        link.close()

        if lidar is not None:
            try:
                lidar.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
