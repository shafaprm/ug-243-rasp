# comm/cmd_udp.py
import socket
import json
import time
from typing import Optional, Dict, Any


class CmdUdpRx:
    """
    UDP receiver for dashboard->controller bridge commands.
    Non-blocking poll via poll_latest().
    """

    def __init__(self, host: str, port: int):
        self.addr = (host, port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(self.addr)
        self.sock.setblocking(False)

        self._latest: Optional[Dict[str, Any]] = None
        self._last_ts: float = 0.0

        print(f"[CmdUdpRx] binding to {self.addr}")

    def poll_latest(self) -> Optional[Dict[str, Any]]:
        """
        Drain socket; return newest message (dict) if any.
        """
        latest = None
        while True:
            try:
                data, _ = self.sock.recvfrom(8192)
            except BlockingIOError:
                break
            except Exception:
                break

            if not data:
                continue

            try:
                obj = json.loads(data.decode("utf-8", errors="ignore"))
            except Exception:
                continue

            if isinstance(obj, dict):
                latest = obj

        if latest is not None:
            self._latest = latest
            self._last_ts = time.time()

        return self._latest
    
    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass


    @property
    def age_s(self) -> float:
        if self._last_ts <= 0:
            return 999.0
        return time.time() - self._last_ts
