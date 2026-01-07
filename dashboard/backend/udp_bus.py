# import asyncio
# import json
# import socket
# import time
# from dataclasses import dataclass, field
# from typing import Any, Dict, Optional, Set

# @dataclass
# class TelemetryStore:
#     latest: Optional[Dict[str, Any]] = None
#     last_rx_ts: float = 0.0
#     ring: list = field(default_factory=list)
#     ring_max: int = 300  # last N events
#     clients: Set[asyncio.Queue] = field(default_factory=set)

#     def push_event(self, event: Dict[str, Any]):
#         self.latest = event
#         self.last_rx_ts = time.time()
#         self.ring.append(event)
#         if len(self.ring) > self.ring_max:
#             self.ring = self.ring[-self.ring_max :]

#     def rx_age_s(self) -> float:
#         if self.last_rx_ts <= 0:
#             return 999.0
#         return time.time() - self.last_rx_ts


# STORE = TelemetryStore()


# def make_udp_sender(host: str, port: int):
#     """
#     Returns a function send_event(event_dict) that sends one JSON line via UDP.
#     Non-blocking for your control loop in practice (UDP sendto is fast).
#     """
#     sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
#     addr = (host, port)

#     def send_event(event: Dict[str, Any]):
#         try:
#             payload = json.dumps(event, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
#             sock.sendto(payload, addr)
#         except Exception:
#             # do not crash control loop
#             pass

#     return send_event


# async def udp_receiver_loop(host: str, port: int):
#     """
#     Async UDP server that receives JSON events and forwards to WS clients.
#     """
#     loop = asyncio.get_running_loop()
#     sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
#     sock.bind((host, port))
#     sock.setblocking(False)

#     while True:
#         try:
#             data, _addr = await loop.sock_recvfrom(sock, 65535)
#             if not data:
#                 continue
#             try:
#                 event = json.loads(data.decode("utf-8", errors="ignore"))
#                 if isinstance(event, dict):
#                     STORE.push_event(event)
#                     # broadcast to ws queues
#                     for q in list(STORE.clients):
#                         # drop if queue is full
#                         if q.full():
#                             continue
#                         q.put_nowait(event)
#             except Exception:
#                 # ignore malformed udp packets
#                 pass
#         except Exception:
#             await asyncio.sleep(0.01)


# dashboard/backend/udp_bus.py
import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Set


@dataclass
class TelemetryStore:
    latest: Optional[Dict[str, Any]] = None
    last_rx_ts: float = 0.0
    ring: list = field(default_factory=list)
    ring_max: int = 300
    clients: Set[asyncio.Queue] = field(default_factory=set)

    def push_event(self, event: Dict[str, Any]):
        self.latest = event
        self.last_rx_ts = time.time()
        self.ring.append(event)
        if len(self.ring) > self.ring_max:
            self.ring = self.ring[-self.ring_max :]

    def rx_age_s(self) -> float:
        if self.last_rx_ts <= 0:
            return 999.0
        return time.time() - self.last_rx_ts


STORE = TelemetryStore()


class UdpServerProtocol(asyncio.DatagramProtocol):
    def datagram_received(self, data: bytes, addr):
        try:
            event = json.loads(data.decode("utf-8", errors="ignore"))
            if not isinstance(event, dict):
                return
            STORE.push_event(event)

            # broadcast non-blocking to websocket queues
            for q in list(STORE.clients):
                if q.full():
                    continue
                q.put_nowait(event)

        except Exception:
            # ignore malformed packets
            return


_udp_transport = None


async def start_udp_server(host: str, port: int):
    """
    Robust UDP listener based on asyncio DatagramProtocol.
    """
    global _udp_transport
    loop = asyncio.get_running_loop()
    transport, _protocol = await loop.create_datagram_endpoint(
        lambda: UdpServerProtocol(),
        local_addr=(host, port),
    )
    _udp_transport = transport
    return transport


def make_udp_sender(host: str, port: int):
    """
    UDP sender helper for runtime side.
    """
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    addr = (host, port)

    def send_event(event: Dict[str, Any]):
        try:
            payload = json.dumps(event, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            sock.sendto(payload, addr)
        except Exception:
            pass

    return send_event
