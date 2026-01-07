# tools/live_tui.py
import curses
import json
import time
from typing import Any, Dict, Optional

def _flatten(d: Any, prefix: str = "", out: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if out is None:
        out = {}
    if isinstance(d, dict):
        for k, v in d.items():
            _flatten(v, f"{prefix}{k}.", out)
    elif isinstance(d, list):
        for i, v in enumerate(d):
            _flatten(v, f"{prefix}{i}.", out)
    else:
        out[prefix[:-1]] = d
    return out

class LiveTUI:
    """
    Minimal terminal dashboard that refreshes at a fixed interval (like nvidia-smi -l 1).
    Call tui.update(...) each control loop tick.
    """
    def __init__(self, refresh_hz: float = 4.0, show_flat: bool = True, max_lines: int = 28):
        self.refresh_dt = 1.0 / max(1e-6, refresh_hz)
        self.show_flat = show_flat
        self.max_lines = max_lines
        self._last_draw = 0.0

        self._last_telem: Optional[Dict[str, Any]] = None
        self._last_cmd: Optional[Dict[str, Any]] = None
        self._last_link_age: float = 999.0

    def update(self, stdscr, now: float, telem: Optional[Dict[str, Any]], cmd: Dict[str, Any], link_age_s: float):
        # keep latest snapshots
        if telem is not None:
            self._last_telem = telem
        self._last_cmd = cmd
        self._last_link_age = link_age_s

        if (now - self._last_draw) < self.refresh_dt:
            return
        self._last_draw = now

        stdscr.erase()
        h, w = stdscr.getmaxyx()

        # Header
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        title = f"UG-243 LIVE DEBUG (refresh {self.refresh_dt:.2f}s) | {ts}"
        stdscr.addnstr(0, 0, title, w - 1, curses.A_BOLD)

        # Status line
        mode = (cmd.get("mode") if isinstance(cmd, dict) else None) or "-"
        estop = (cmd.get("estop") if isinstance(cmd, dict) else None)
        estop_s = "ON" if estop else "OFF"
        age_s = self._last_link_age
        age_flag = "OK" if age_s < 0.5 else ("WARN" if age_s < 2.0 else "STALE")
        status = f"Serial RX age: {age_s:6.2f}s [{age_flag}] | mode={mode} | estop={estop_s}"
        stdscr.addnstr(1, 0, status, w - 1)

        # TX summary
        drive = (cmd.get("drive") or {}) if isinstance(cmd, dict) else {}
        turret = (cmd.get("turret") or {}) if isinstance(cmd, dict) else {}
        th = drive.get("th", 0.0)
        st = drive.get("st", 0.0)
        rx = turret.get("rx", 0.0)
        ry = turret.get("ry", 0.0)
        fire = turret.get("fire", False)
        txline = f"IN: th={th:+.2f} st={st:+.2f} | turret rx={rx:+.2f} ry={ry:+.2f} fire={int(bool(fire))}"
        stdscr.addnstr(3, 0, txline, w - 1, curses.A_BOLD)

        # AUTO / LIDAR summary (from cmd.meta, if present)
        meta = (cmd.get("meta") or {}) if isinstance(cmd, dict) else {}
        auto_enabled = meta.get("auto_enabled", None)
        auto_enabled_s = "-" if auto_enabled is None else ("ON" if auto_enabled else "OFF")

        lidar = (meta.get("lidar") or {}) if isinstance(meta, dict) else {}
        min_front = lidar.get("min_front", None)
        avg_left = lidar.get("avg_left", None)
        avg_right = lidar.get("avg_right", None)

        def _fmt(x):
            try:
                return f"{float(x):.2f}"
            except Exception:
                return "-"

        autoline = (
            f"AUTO: {auto_enabled_s} | "
            f"LIDAR m_front={_fmt(min_front)}m "
            f"avg_L={_fmt(avg_left)}m avg_R={_fmt(avg_right)}m"
        )
        stdscr.addnstr(4, 0, autoline, w - 1)


        # Telemetry area
        y = 6
        stdscr.addnstr(y, 0, "OUT (latest):", w - 1, curses.A_UNDERLINE)
        y += 1

        telem_obj = self._last_telem or {}
        if self.show_flat:
            flat = _flatten(telem_obj)
            # sort keys for stable view
            items = sorted(flat.items(), key=lambda kv: kv[0])
            for k, v in items[: self.max_lines]:
                line = f"{k:28s} : {v}"
                if y >= h - 1:
                    break
                stdscr.addnstr(y, 0, line, w - 1)
                y += 1
        else:
            # pretty JSON block
            blob = json.dumps(telem_obj, indent=2, ensure_ascii=False)
            for line in blob.splitlines()[: self.max_lines]:
                if y >= h - 1:
                    break
                stdscr.addnstr(y, 0, line, w - 1)
                y += 1

        stdscr.addnstr(
            h - 1, 0,
            "Keys: q=quit | a=toggle AUTO | f=toggle flat/json | + / - refresh",
            w - 1, curses.A_DIM
        )
        stdscr.refresh()

def run_tui(loop_fn):
    """
    loop_fn(stdscr, tui) must run your control loop,
    call tui.update(stdscr, now, telem, cmd, link_age_s),
    and return when user exits.
    """
    def _wrapped(stdscr):
        curses.curs_set(0)
        stdscr.nodelay(True)
        stdscr.timeout(0)
        loop_fn(stdscr)
    curses.wrapper(_wrapped)
