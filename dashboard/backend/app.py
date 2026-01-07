# dashboard/backend/app.py
import asyncio
import time
from typing import Any, Dict, Optional, Literal

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Body
from fastapi.middleware.cors import CORSMiddleware

from udp_bus import STORE, start_udp_server, make_udp_sender

UDP_HOST = "127.0.0.1"
UDP_PORT = 15555  # telemetry IN (UGV -> dashboard)

TX_UDP_HOST = "127.0.0.1"
TX_UDP_PORT = 15556  # command OUT (dashboard -> UGV bridge)
tx_sender = make_udp_sender(TX_UDP_HOST, TX_UDP_PORT)

AIM_SOURCE = "controller"  # "controller" | "dashboard"

app = FastAPI(title="UG-243 Dashboard Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    await start_udp_server(UDP_HOST, UDP_PORT)

@app.get("/health")
def health() -> Dict[str, Any]:
    latest: Optional[Dict[str, Any]] = STORE.latest
    return {
        "ok": True,
        "udp_listen": f"{UDP_HOST}:{UDP_PORT}",
        "ws_clients": len(STORE.clients),
        "last_rx_age_s": round(STORE.rx_age_s(), 3),
        "latest_type": (latest.get("type") if isinstance(latest, dict) else None),
        "tx_target": f"{TX_UDP_HOST}:{TX_UDP_PORT}",
    }

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    q: asyncio.Queue = asyncio.Queue(maxsize=50)
    STORE.clients.add(q)

    try:
        if STORE.latest is not None:
            await ws.send_json({"type": "snapshot", "data": STORE.latest})

        while True:
            event = await q.get()
            await ws.send_json({"type": "event", "data": event})
    except WebSocketDisconnect:
        pass
    finally:
        STORE.clients.discard(q)

@app.post("/api/tx")
async def api_tx(payload: Dict[str, Any]):
    # 1) kirim command ke UGV bridge via UDP
    tx_sender(payload)

    # 2) broadcast ke WS untuk debug/monitoring
    event = {
        "type": "tx",
        "src": "dash_http",
        "ts": payload.get("ts", time.time()),
        "data": payload,
    }
    STORE.push_event(event)
    for q in list(STORE.clients):
        if not q.full():
            q.put_nowait(event)

    return {"ok": True}

@app.get("/api/aim")
def get_aim():
    return {"ok": True, "aim_source": AIM_SOURCE}

@app.post("/api/aim")
def set_aim(payload: Dict[str, Any] = Body(...)):
    global AIM_SOURCE
    src = payload.get("aim_source")
    if src not in ("controller", "dashboard"):
        return {"ok": False, "err": "aim_source must be controller|dashboard"}, 400

    AIM_SOURCE = src

    # broadcast ke WS agar UI update
    event = {"type": "aim", "src": "dash_http", "ts": time.time(), "data": {"aim_source": AIM_SOURCE}}
    STORE.push_event(event)
    for q in list(STORE.clients):
        if not q.full():
            q.put_nowait(event)

    # kirim ke Pi via UDP command port (15556)
    tx_sender({"cmd": "aim", "aim_source": AIM_SOURCE, "ts": int(time.time() * 1000)})

    return {"ok": True, "aim_source": AIM_SOURCE}