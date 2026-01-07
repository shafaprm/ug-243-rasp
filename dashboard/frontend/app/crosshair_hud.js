// app/crosshair_hud.js
import { $ } from "./dom.js";
import { clamp } from "./utils.js";
import { log } from "./log.js";
import { CFG } from "./config.js";

export function createCrosshairHUD() {
  const stage = $.videoStage;
  const cross = $.crosshair;

  if (!stage || !cross) {
    return {
      init() { log("CrosshairHUD disabled (missing #video_stage or #crosshair)"); },
      onTelem() {}
    };
  }

  // persisted calib params
  let calib = {
    rx0: 0.0,
    ry0: 0.0,
    sx: 260.0,
    sy: 240.0,
    invert_y: true,
    invert_x: true

  };

  // runtime state
  let calibMode = false;       // ON/OFF
  let pendingAxis = null;      // "x" | "y" | null
  let clickTarget = null;      // {x,y} stage pixels

  // telemetry pose (actual turret)
  let rxAct = 0.0;
  let ryAct = 0.0;
  let hasPose = false;

  function rect() { return stage.getBoundingClientRect(); }

  function turretToPixel(rx, ry) {
    const r = rect();
    const cx = r.width / 2;
    const cy = r.height / 2;

    const dx = (Number(rx) - calib.rx0) * calib.sx;
    const sign = calib.invert_y ? -1 : 1;
    const dy = sign * (Number(ry) - calib.ry0) * calib.sy;

    return { x: cx + dx, y: cy + dy };
  }

  function pixelToTurret(x, y) {
    const r = rect();
    const cx = r.width / 2;
    const cy = r.height / 2;
  
    const dx = x - cx;
    const dy = y - cy;
  
    const signX = calib.invert_x ? -1 : 1;
    const rx = calib.rx0 + signX * (dx / calib.sx);   // FIX: dx, bukan dx_px
  
    const signY = calib.invert_y ? -1 : 1;
    const ry = calib.ry0 + (dy / (signY * calib.sy));
  
    return {
      rx: clamp(Number(rx), -1, 1),
      ry: clamp(Number(ry), -1, 1)
    };
  }
  

  async function sendTurretTarget(rx, ry) {
    const url = CFG.urls.tx();
  
    const body = {
      cmd: {
        drive: { th: 0, st: 0 },
        turret: { rx, ry, fire: false, mode: 1 }, // IMPORTANT: mode=1 (POS)
        estop: false
      },
      meta: { src: "dash_click" },
      ts: Date.now()
    };
  
    try {
      log(`CLICK->TX sending to ${url}`); // DEBUG
      const r = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      });
  
      const txt = await r.text();
      if (!r.ok) throw new Error(`HTTP ${r.status} ${txt}`);
  
      log(`CLICK->TX ok rx=${rx.toFixed(3)} ry=${ry.toFixed(3)}`);
    } catch (e) {
      log(`CLICK->TX error: ${e?.message || e}`);
    }
  }
  


  function setCrosshairPx(x, y) {
    const r = rect();
    const px = clamp(Number(x), 0, r.width);
    const py = clamp(Number(y), 0, r.height);

    cross.style.left = `${px}px`;
    cross.style.top  = `${py}px`;
    cross.style.transform = "translate(-50%, -50%)";
  }

  function render() {
    if (hasPose) {
      const p = turretToPixel(rxAct, ryAct);
      setCrosshairPx(p.x, p.y);
      return;
    }
    const r = rect();
    setCrosshairPx(r.width / 2, r.height / 2);
  }

  function syncUI() {
    // If buttons are absent, skip
    if (!$.btnCalibToggle) return;

    $.btnCalibToggle.textContent = calibMode ? "Calib: ON" : "Calib: OFF";
    if ($.calibState) $.calibState.textContent = calibMode ? "ON" : "OFF";

    const enabled = calibMode && hasPose;
    if ($.btnSetCenter) $.btnSetCenter.disabled = !enabled;
    if ($.btnAxisX) $.btnAxisX.disabled = !enabled;
    if ($.btnAxisY) $.btnAxisY.disabled = !enabled;
    if ($.btnSaveCalib) $.btnSaveCalib.disabled = !enabled;

    if ($.calibMode) $.calibMode.textContent = pendingAxis ? pendingAxis.toUpperCase() : "-";

    if ($.calibHint) {
      if (!calibMode) {
        $.calibHint.textContent = 'Klik "Calib: OFF" untuk mulai.';
      } else if (!hasPose) {
        $.calibHint.textContent = "Menunggu telemetry turret (rx_act/ry_act)...";
      } else if (!pendingAxis) {
        $.calibHint.textContent = "Urutan: Set Center → Axis X (klik target, confirm) → Axis Y (klik target, confirm) → Save.";
      } else {
        $.calibHint.textContent = `Axis ${pendingAxis.toUpperCase()}: klik target di video, lalu klik tombol Axis lagi untuk Confirm.`;
      }
    }
  }

  async function loadCalib() {
    try {
      const r = await fetch(CFG.urls.calib(), { cache: "no-store" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const j = await r.json();
      if (j && typeof j === "object") calib = { ...calib, ...j };
      log(`CrosshairHUD: calib loaded ${JSON.stringify(calib)}`);
      render();
      syncUI();
    } catch (e) {
      log(`CrosshairHUD: calib load failed (${e?.message || e})`);
      render();
      syncUI();
    }
  }

  async function saveCalib() {
    try {
      const r = await fetch(CFG.urls.calib(), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(calib)
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      log(`CrosshairHUD: calib saved ${JSON.stringify(calib)}`);
    } catch (e) {
      log(`CrosshairHUD: calib save failed (${e?.message || e})`);
    }
  }

  function confirmAxis(axis) {
    if (!clickTarget) { log("CrosshairHUD: click target first"); return; }
    if (!hasPose) { log("CrosshairHUD: no turret telemetry"); return; }

    const r = rect();
    const cx = r.width / 2;
    const cy = r.height / 2;

    if (axis === "x") {
      const dx_px = clickTarget.x - cx;
      const drx = rxAct - calib.rx0;

      if (Math.abs(drx) < 1e-4) {
        log("CrosshairHUD: drx too small. Move turret horizontally, then confirm X.");
        return;
      }

      calib.sx = dx_px / drx;
      pendingAxis = null;
      clickTarget = null;

      log(`CrosshairHUD: CONFIRM X => sx=${calib.sx.toFixed(2)} px/unit`);
      render();
      syncUI();
      return;
    }

    if (axis === "y") {
      const dy_px = clickTarget.y - cy;
      const dry = ryAct - calib.ry0;

      if (Math.abs(dry) < 1e-4) {
        log("CrosshairHUD: dry too small. Move turret vertically, then confirm Y.");
        return;
      }

      const ratio = dy_px / dry;
      calib.sy = Math.abs(ratio);
      calib.invert_y = ratio > 0;

      pendingAxis = null;
      clickTarget = null;

      log(`CrosshairHUD: CONFIRM Y => sy=${calib.sy.toFixed(2)} invert_y=${calib.invert_y}`);
      render();
      syncUI();
      return;
    }
  }

  function install() {
    // capture target click only during calibMode
    stage.addEventListener("click", (ev) => {
      try {
        const r = rect();
        const px = ev.clientX - r.left;
        const py = ev.clientY - r.top;
    
        if (calibMode) {
          clickTarget = { x: px, y: py };
          log(`CrosshairHUD: target set x=${px.toFixed(1)} y=${py.toFixed(1)}`);
          syncUI();
          return;
        }
    
        if (!hasPose) {
          log("CLICK ignored: waiting turret telemetry (rx_act/ry_act)...");
          return;
        }
    
        if (!isFinite(calib.sx) || Math.abs(calib.sx) < 1e-6 || !isFinite(calib.sy) || Math.abs(calib.sy) < 1e-6) {
          log("CLICK ignored: calib sx/sy invalid. Do calibration first.");
          return;
        }
    
        const t = pixelToTurret(px, py);
    
        // jangan overwrite rxAct/ryAct di sini (biar telemetry tetap jadi source of truth)
        // render();
    
        sendTurretTarget(t.rx, t.ry);
      } catch (e) {
        log(`CLICK handler error: ${e?.message || e}`);
      }
    });
    
  

    window.addEventListener("resize", () => render());

    if ($.btnCalibToggle) {
      $.btnCalibToggle.onclick = () => {
        calibMode = !calibMode;
        pendingAxis = null;
        clickTarget = null;
        log(`CrosshairHUD: calibMode=${calibMode ? "ON" : "OFF"}`);
        syncUI();
      };
    }

    if ($.btnSetCenter) {
      $.btnSetCenter.onclick = () => {
        if (!calibMode) return;
        if (!hasPose) { log("CrosshairHUD: no turret telemetry"); return; }

        calib.rx0 = rxAct;
        calib.ry0 = ryAct;
        log(`CrosshairHUD: set center rx0=${calib.rx0.toFixed(3)} ry0=${calib.ry0.toFixed(3)}`);

        render();
        syncUI();
      };
    }

    if ($.btnAxisX) {
      $.btnAxisX.onclick = () => {
        if (!calibMode) return;
        if (pendingAxis === "x" && clickTarget) confirmAxis("x");
        else {
          pendingAxis = "x";
          clickTarget = null;
          log("CrosshairHUD: X mode - click target then click Axis X again to confirm");
          syncUI();
        }
      };
    }

    if ($.btnAxisY) {
      $.btnAxisY.onclick = () => {
        if (!calibMode) return;
        if (pendingAxis === "y" && clickTarget) confirmAxis("y");
        else {
          pendingAxis = "y";
          clickTarget = null;
          log("CrosshairHUD: Y mode - click target then click Axis Y again to confirm");
          syncUI();
        }
      };
    }

    if ($.btnSaveCalib) $.btnSaveCalib.onclick = () => { if (calibMode) saveCalib(); };
    if ($.btnReloadCalib) $.btnReloadCalib.onclick = () => loadCalib();
  }

  return {
    init() {
      install();
      loadCalib();
      render();
      syncUI();
      log("CrosshairHUD ready (calibration + telemetry)");
    },

    // Called by WS client
    onTelem(t) {
      rxAct = clamp(-Number(t?.rx_act ?? 0), -1, 1);
      // flip Y if needed (try first without flipping Y)
      ryAct = clamp(Number(t?.ry_act ?? 0), -1, 1);
      hasPose = true;

      render();
      syncUI();
    }
  };
}
