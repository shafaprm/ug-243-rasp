# comm/serial_link.py
import threading
import time
from queue import Queue, Empty
from typing import Optional, Dict, Any

import serial

from messages.pack import loads_line


class SerialLink:
    """
    Serial USB link to Arduino using line-delimited JSON.
    - send(): writes one JSON per line
    - recv_latest(): returns newest telemetry (drops older)
    """

    def __init__(self, port: str, baudrate: int):
        self.port = port
        self.baudrate = baudrate

        self._ser: Optional[serial.Serial] = None
        self._rx_thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

        self.rx_queue: "Queue[Dict[str, Any]]" = Queue()
        self._last_rx_ts = 0.0

    def open(self):
        self._ser = serial.Serial(self.port, self.baudrate, timeout=0.1)
        time.sleep(1.5)  # Arduino often resets on serial open
        self._stop.clear()
        self._rx_thread = threading.Thread(target=self._rx_loop, daemon=True)
        self._rx_thread.start()

    def close(self):
        self._stop.set()
        if self._rx_thread:
            self._rx_thread.join(timeout=1.0)
        if self._ser and self._ser.is_open:
            self._ser.close()

    def send(self, msg: Dict[str, Any]):
        import json
        if not self._ser or not self._ser.is_open:
            return
        line = json.dumps(msg, separators=(",", ":"), ensure_ascii=False)
        self._ser.write((line + "\n").encode("utf-8"))

    def recv_latest(self) -> Optional[Dict[str, Any]]:
        latest = None
        while True:
            try:
                latest = self.rx_queue.get_nowait()
            except Empty:
                break
        return latest

    @property
    def last_rx_age_s(self) -> float:
        if self._last_rx_ts <= 0:
            return 999.0
        return time.time() - self._last_rx_ts

    def _rx_loop(self):
        assert self._ser is not None
        buf = ""
        while not self._stop.is_set():
            try:
                raw = self._ser.read(256)
                if not raw:
                    continue
                buf += raw.decode("utf-8", errors="ignore")

                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = loads_line(line)
                        self.rx_queue.put(obj)
                        self._last_rx_ts = time.time()
                    except Exception:
                        # ignore malformed lines, keep link alive
                        pass
            except Exception:
                time.sleep(0.1)
