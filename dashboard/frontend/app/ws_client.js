// app/ws_client.js
import { CFG } from "./config.js";
import { $ } from "./dom.js";
import { fmtAge, safeJsonParse } from "./utils.js";
import { log } from "./log.js";
import { updateControllerFromTx } from "./controller_viz.js";

export function createWsClient({ hud } = {}) {
  let lastTelemTs = 0;
  let lastTxTs = 0;

  function setConn(ok) {
    if (!$.conn) return;
    $.conn.textContent = ok ? "CONNECTED" : "DISCONNECTED";
    $.conn.style.borderColor = ok ? "#2b8a3e" : "#a61e4d";
  }

  function setWsState(text) {
    if ($.wsState) $.wsState.textContent = text;
  }

  function updateAges() {
    const now = Date.now();
    if ($.telemAge) $.telemAge.textContent = lastTelemTs ? fmtAge(now - lastTelemTs) : "-";
    if ($.txAge) $.txAge.textContent = lastTxTs ? fmtAge(now - lastTxTs) : "-";
  }

  setInterval(updateAges, CFG.ui.ageTickMs);

  function connect() {
    const wsUrl = CFG.urls.ws();
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      setConn(true);
      setWsState("open");
      log(`WS open ${wsUrl}`);
    };

    ws.onclose = () => {
      setConn(false);
      setWsState("closed (reconnecting)");
      log("WS closed, reconnecting...");
      setTimeout(connect, 800);
    };

    ws.onerror = () => {
      setConn(false);
      setWsState("error");
    };

    ws.onmessage = (msg) => {
      const payload = safeJsonParse(msg.data);
      const ev = payload?.data;
      if (!ev) return;

      if (ev.type === "telem") {
        lastTelemTs = Date.now();
        if ($.telemSrc) $.telemSrc.textContent = ev.src ?? "-";
        if ($.latestTelem) $.latestTelem.textContent = JSON.stringify(ev, null, 2);
        log(`OUT(TELEM) from ${ev.src || "unknown"}`);

        // Feed turret actual pose to HUD
        const d = ev?.data || {};
        const rxAct = d.rx_act;
        const ryAct = d.ry_act;

        if (rxAct !== undefined || ryAct !== undefined) {
          hud?.onTelem?.({
            rx_act: rxAct ?? 0,
            ry_act: ryAct ?? 0,
            yaw_deg: d.yaw_deg,
            pitch_deg: d.pitch_deg
          });
        }
        return;
      }

      if (ev.type === "tx") {
        lastTxTs = Date.now();
        if ($.txSrc) $.txSrc.textContent = ev.src ?? "-";
        if ($.latestTx) $.latestTx.textContent = JSON.stringify(ev, null, 2);
        log(`IN(TX) from ${ev.src || "unknown"}`);

        const cmd = ev?.data?.cmd || ev?.data || {};
        updateControllerFromTx(cmd);
      }

      if (ev.type === "aim") {
        const src = ev?.data?.aim_source;
        if ($.aimState) $.aimState.textContent = `AIM:${src || "-"}`;
        log(`AIM updated => ${src}`);
        return;
      }      

    };
  }

  return { connect };
}
