# control/safety.py
import time

class Safety:
    def __init__(self):
        self.estop = False
        self._last_cmd_ts = time.time()

    def heartbeat(self):
        """Dipanggil setiap kali Pi mengirim command"""
        self._last_cmd_ts = time.time()

    def is_stale(self, timeout_s: float) -> bool:
        """True jika Pi tidak update command dalam waktu lama"""
        return (time.time() - self._last_cmd_ts) > timeout_s
