# control/turret_controller.py
class TurretController:
    def __init__(self):
        self._fire_requested = False

    def request_fire(self):
        """Dipanggil saat trigger tembak (event)"""
        self._fire_requested = True

    def consume_fire(self) -> bool:
        """
        Mengembalikan True sekali,
        lalu reset otomatis
        """
        if self._fire_requested:
            self._fire_requested = False
            return True
        return False
