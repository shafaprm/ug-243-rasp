// // app.js
// const connEl = document.getElementById("conn");
// const wsStateEl = document.getElementById("ws_state");

// const telemAgeEl = document.getElementById("telem_age");
// const txAgeEl = document.getElementById("tx_age");
// const telemSrcEl = document.getElementById("telem_src");
// const txSrcEl = document.getElementById("tx_src");

// const latestTelemEl = document.getElementById("latest_telem");
// const latestTxEl = document.getElementById("latest_tx");
// const logEl = document.getElementById("log");

// let lastTelemTs = 0;
// let lastTxTs = 0;

// function log(line) {
//   const now = new Date().toISOString();
//   if (!logEl) return;
//   logEl.textContent = `[${now}] ${line}\n` + logEl.textContent;
//   const lines = logEl.textContent.split("\n");
//   if (lines.length > 120) logEl.textContent = lines.slice(0, 120).join("\n");
// }

// function setConn(ok) {
//   if (!connEl) return;
//   connEl.textContent = ok ? "CONNECTED" : "DISCONNECTED";
//   connEl.style.borderColor = ok ? "#2b8a3e" : "#a61e4d";
// }

// function setWsState(text) {
//   if (!wsStateEl) return;
//   wsStateEl.textContent = text;
// }

// function fmtAge(ms) {
//   if (!ms) return "-";
//   return `${(ms / 1000.0).toFixed(2)} s`;
// }

// function updateAges() {
//   const now = Date.now();
//   if (telemAgeEl) telemAgeEl.textContent = lastTelemTs ? fmtAge(now - lastTelemTs) : "-";
//   if (txAgeEl) txAgeEl.textContent = lastTxTs ? fmtAge(now - lastTxTs) : "-";
// }

// setInterval(updateAges, 200);

// function clearActive() {
//   document.querySelectorAll(
//     ".btn-triangle.active,.btn-circle.active,.btn-cross.active,.btn-square.active," +
//     ".btn-dpad.active,.btn-shoulder.active,.btn-trigger.active,.btn-stick.active," +
//     ".btn-options.active,.btn-share.active,.btn-ps.active"
//   ).forEach(el => el.classList.remove("active"));
// }

// function clamp(x, lo, hi) {
//   return Math.max(lo, Math.min(hi, x));
// }

// /**
//  * Sync controller visualization from our project TX cmd schema:
//  * cmd = {
//  *   estop: bool,
//  *   drive: { th: [-1..1], st: [-1..1] },
//  *   turret: { rx: [-1..1], ry: [-1..1], fire: bool }
//  * }
//  */
// function updateControllerFromTx(cmd) {
//   clearActive();

//   const drive = cmd?.drive || {};
//   const turret = cmd?.turret || {};

//   const fire = !!turret.fire;
//   const estop = !!cmd.estop;

//   if (fire) document.querySelector(".btn-square")?.classList.add("active");
//   if (estop) document.querySelector(".btn-ps")?.classList.add("active");

//   const st = clamp(Number(drive.st ?? 0), -1, 1);
//   const rx = clamp(Number(turret.rx ?? 0), -1, 1);
//   const ry = clamp(Number(turret.ry ?? 0), -1, 1);

//   const leftStick = document.querySelector(".stick-left");
//   const rightStick = document.querySelector(".stick-right");

//   const L_BASE_X = 213, L_BASE_Y = 206;
//   const R_BASE_X = 388, R_BASE_Y = 206;
//   const RANGE = 15;

//   if (leftStick) {
//     leftStick.setAttribute("cx", (L_BASE_X + st * RANGE).toFixed(1));
//     leftStick.setAttribute("cy", (L_BASE_Y + 0 * RANGE).toFixed(1));
//     if (Math.abs(st) > 0.05) leftStick.classList.add("active");
//   }

//   if (rightStick) {
//     rightStick.setAttribute("cx", (R_BASE_X + rx * RANGE).toFixed(1));
//     rightStick.setAttribute("cy", (R_BASE_Y + ry * RANGE).toFixed(1));
//     if (Math.abs(rx) > 0.05 || Math.abs(ry) > 0.05) rightStick.classList.add("active");
//   }

//   const th = clamp(Number(drive.th ?? 0), -1, 1);
//   const r2p = th > 0 ? th : 0;
//   const l2p = th < 0 ? -th : 0;

//   const l2 = document.querySelector(".l2");
//   const r2 = document.querySelector(".r2");

//   if (l2) {
//     const p = clamp(l2p, 0, 1);
//     l2.style.opacity = (0.4 + p * 0.6).toFixed(2);
//     if (p > 0.1) l2.classList.add("active");
//   }

//   if (r2) {
//     const p = clamp(r2p, 0, 1);
//     r2.style.opacity = (0.4 + p * 0.6).toFixed(2);
//     if (p > 0.1) r2.classList.add("active");
//   }
// }

// // =========================================================
// // Crosshair HUD + Calibration UI
// // =========================================================

// // OPTIONAL UI (jika tombol ada di index.html)
// const btnCalibToggle = document.getElementById("btn_calib_toggle");
// const btnSetCenter   = document.getElementById("btn_set_center");
// const btnAxisX       = document.getElementById("btn_axis_x");
// const btnAxisY       = document.getElementById("btn_axis_y");
// const btnSaveCalib   = document.getElementById("btn_save_calib");
// const btnReloadCalib = document.getElementById("btn_reload_calib");

// const calibStateEl = document.getElementById("calib_state");
// const calibModeEl  = document.getElementById("calib_mode");
// const calibHintEl  = document.getElementById("calib_hint");

// const CrosshairHUD = (() => {
//   const stage = document.getElementById("video_stage");
//   const cross = document.getElementById("crosshair");

//   if (!stage || !cross) {
//     return {
//       init() { log("CrosshairHUD disabled (missing #video_stage or #crosshair)"); },
//       onTurret() {}
//     };
//   }

//   // default calib
//   let calib = {
//     rx0: 0.0,
//     ry0: 0.0,
//     sx: 260.0,
//     sy: 240.0,
//     invert_y: true
//   };

//   // last turret command
//   let lastRx = 0.0;
//   let lastRy = 0.0;

//   // calibration state
//   let calibMode = false;          // ON/OFF
//   let pendingAxis = null;         // "x" | "y" | null
//   let clickTarget = null;         // {x,y} in stage pixels

//   function clamp01(v, lo, hi) {
//     return Math.max(lo, Math.min(hi, v));
//   }

//   function getStageRect() {
//     return stage.getBoundingClientRect();
//   }

//   function pixelToTurret(x, y) {
//     const rect = getStageRect();
//     const w = rect.width;
//     const h = rect.height;
//     const cx = w / 2;
//     const cy = h / 2;
  
//     const dx_px = x - cx;
//     const dy_px = y - cy;
  
//     const rx = calib.rx0 + (dx_px / calib.sx);
  
//     // inverse dari turretToPixel:
//     // y = cy + (invert? -1 : 1) * sy * (ry-ry0)
//     const sign = calib.invert_y ? -1 : 1;
//     const ry = calib.ry0 + (dy_px / (sign * calib.sy));
  
//     return {
//       rx: clamp(Number(rx), -1, 1),
//       ry: clamp(Number(ry), -1, 1)
//     };
//   }
  
//   async function sendTurretTarget(rx, ry) {
//     const url = `http://${location.hostname}:8000/api/tx`;
//     const body = {
//       cmd: {
//         drive: { th: 0, st: 0 },
//         turret: { rx, ry, fire: false },
//         estop: false
//       },
//       meta: { src: "dash_click" },
//       ts: Date.now()
//     };
  
//     try {
//       const r = await fetch(url, {
//         method: "POST",
//         headers: { "Content-Type": "application/json" },
//         body: JSON.stringify(body)
//       });
//       const txt = await r.text();
//       if (!r.ok) throw new Error(`HTTP ${r.status} ${txt}`);
//       log(`CLICK->TX ok rx=${rx.toFixed(3)} ry=${ry.toFixed(3)}`);
//     } catch (e) {
//       log(`CLICK->TX error: ${e?.message || e}`);
//     }
//   }
  

  

//   function render() {
//     const p = turretToPixel(lastRx, lastRy);
//     cross.style.left = `${p.x}px`;
//     cross.style.top = `${p.y}px`;
//     cross.style.transform = "translate(-50%, -50%)";
//   }

//   async function loadCalib() {
//     try {
//       const url = `http://${location.hostname}:8001/api/calib/crosshair`;
//       const r = await fetch(url, { cache: "no-store" });
//       if (!r.ok) {
//         log("CrosshairHUD: calib endpoint not OK (using defaults)");
//         render();
//         return;
//       }
//       const j = await r.json();
//       calib = { ...calib, ...j };
//       log(`CrosshairHUD: calib loaded ${JSON.stringify(calib)}`);
//       render();
//     } catch (e) {
//       log(`CrosshairHUD: calib load error ${e?.message || e}`);
//       render();
//     }
//   }

//   async function saveCalib() {
//     try {
//       const url = `http://${location.hostname}:8001/api/calib/crosshair`;
//       const r = await fetch(url, {
//         method: "POST",
//         headers: { "Content-Type": "application/json" },
//         body: JSON.stringify(calib)
//       });
//       if (!r.ok) throw new Error(`HTTP ${r.status}`);
//       log("CrosshairHUD: calib saved");
//     } catch (e) {
//       log(`CrosshairHUD: calib save error ${e?.message || e}`);
//     }
//   }

//   function syncUI() {
//     // if no UI controls exist, skip (keyboard still works)
//     if (!btnCalibToggle) return;

//     const on = !!calibMode;

//     btnCalibToggle.textContent = on ? "Calib: ON" : "Calib: OFF";
//     if (calibStateEl) calibStateEl.textContent = on ? "ON" : "OFF";

//     if (btnSetCenter) btnSetCenter.disabled = !on;
//     if (btnAxisX) btnAxisX.disabled = !on;
//     if (btnAxisY) btnAxisY.disabled = !on;
//     if (btnSaveCalib) btnSaveCalib.disabled = !on;

//     const mode = pendingAxis ? pendingAxis.toUpperCase() : "-";
//     if (calibModeEl) calibModeEl.textContent = mode;

//     if (calibHintEl) {
//       if (!on) {
//         calibHintEl.textContent = 'Klik "Calib: OFF" untuk mulai.';
//       } else if (!pendingAxis) {
//         calibHintEl.textContent = "Langkah: (1) Set Center, (2) Axis X/Y lalu klik target di video, (3) Confirm, (4) Save.";
//       } else {
//         calibHintEl.textContent = `Axis ${mode}: klik target di video, lalu klik tombol Axis ${mode} lagi untuk Confirm.`;
//       }
//     }
//   }

//   function confirmAxis(axis) {
//     if (!clickTarget) {
//       log("CrosshairHUD: click target first");
//       return;
//     }

//     const rect = getStageRect();
//     const w = rect.width;
//     const h = rect.height;
//     const cx = w / 2;
//     const cy = h / 2;

//     if (axis === "x") {
//       const dx_px = clickTarget.x - cx;
//       const drx = (lastRx - calib.rx0);
//       if (Math.abs(drx) < 1e-4) {
//         log("CrosshairHUD: drx too small, move turret horizontally then confirm X");
//         return;
//       }
//       calib.sx = dx_px / drx;
//       pendingAxis = null;
//       clickTarget = null;
//       log(`CrosshairHUD: CONFIRM X => sx=${calib.sx.toFixed(2)} px/unit`);
//       render();
//       syncUI();
//       return;
//     }

//     if (axis === "y") {
//       const dy_px = clickTarget.y - cy;
//       const dry = (lastRy - calib.ry0);
//       if (Math.abs(dry) < 1e-4) {
//         log("CrosshairHUD: dry too small, move turret vertically then confirm Y");
//         return;
//       }

//       const ratio = dy_px / dry;
//       calib.sy = Math.abs(ratio);
//       calib.invert_y = ratio > 0;

//       pendingAxis = null;
//       clickTarget = null;
//       log(`CrosshairHUD: CONFIRM Y => sy=${calib.sy.toFixed(2)} invert_y=${calib.invert_y}`);
//       render();
//       syncUI();
//       return;
//     }
//   }

//   function installUX() {
//     // click to capture target only in calibMode
//     stage.addEventListener("click", (ev) => {
//       const rect = getStageRect();
//       const px = ev.clientX - rect.left;
//       const py = ev.clientY - rect.top;
    
//       if (calibMode) {
//         // calibration capture
//         clickTarget = { x: px, y: py };
//         log(`CrosshairHUD: target px x=${px.toFixed(1)} y=${py.toFixed(1)}`);
//         syncUI();
//         return;
//       }
    
//       // click-to-aim
//       const t = pixelToTurret(px, py);
    
//       // instant visual feedback
//       lastRx = t.rx;
//       lastRy = t.ry;
//       render();
    
//       sendTurretTarget(t.rx, t.ry);
//     });
    

//     // keep crosshair consistent when layout changes
//     window.addEventListener("resize", () => render());

//     // keyboard fallback (optional)
//     window.addEventListener("keydown", (e) => {
//       if (e.key === "c") {
//         calibMode = !calibMode;
//         pendingAxis = null;
//         clickTarget = null;
//         log(`CrosshairHUD: calibMode=${calibMode ? "ON" : "OFF"}`);
//         syncUI();
//         return;
//       }
//       if (!calibMode) return;

//       if (e.key === "0") {
//         calib.rx0 = lastRx;
//         calib.ry0 = lastRy;
//         log(`CrosshairHUD: set center rx0=${calib.rx0.toFixed(3)} ry0=${calib.ry0.toFixed(3)}`);
//         render();
//         syncUI();
//         return;
//       }
//       if (e.key === "x") {
//         pendingAxis = "x";
//         clickTarget = null;
//         log("CrosshairHUD: X mode - click target then press x again to confirm");
//         syncUI();
//         return;
//       }
//       if (e.key === "y") {
//         pendingAxis = "y";
//         clickTarget = null;
//         log("CrosshairHUD: Y mode - click target then press y again to confirm");
//         syncUI();
//         return;
//       }
//       if (e.key === "s") {
//         saveCalib();
//         return;
//       }

//       // confirm if already have target
//       if ((e.key === "x" || e.key === "X") && pendingAxis === "x" && clickTarget) confirmAxis("x");
//       if ((e.key === "y" || e.key === "Y") && pendingAxis === "y" && clickTarget) confirmAxis("y");
//     });

//     // bind buttons (if exist)
//     if (btnCalibToggle) {
//       btnCalibToggle.onclick = () => {
//         calibMode = !calibMode;
//         pendingAxis = null;
//         clickTarget = null;
//         log(`CrosshairHUD: calibMode=${calibMode ? "ON" : "OFF"}`);
//         syncUI();
//       };
//     }

//     if (btnSetCenter) {
//       btnSetCenter.onclick = () => {
//         if (!calibMode) return;
//         calib.rx0 = lastRx;
//         calib.ry0 = lastRy;
//         log(`CrosshairHUD: set center rx0=${calib.rx0.toFixed(3)} ry0=${calib.ry0.toFixed(3)}`);
//         render();
//         syncUI();
//       };
//     }

//     if (btnAxisX) {
//       btnAxisX.onclick = () => {
//         if (!calibMode) return;
//         if (pendingAxis === "x" && clickTarget) {
//           confirmAxis("x");
//         } else {
//           pendingAxis = "x";
//           clickTarget = null;
//           log("CrosshairHUD: X mode - click target then click Axis X again to confirm");
//           syncUI();
//         }
//       };
//     }

//     if (btnAxisY) {
//       btnAxisY.onclick = () => {
//         if (!calibMode) return;
//         if (pendingAxis === "y" && clickTarget) {
//           confirmAxis("y");
//         } else {
//           pendingAxis = "y";
//           clickTarget = null;
//           log("CrosshairHUD: Y mode - click target then click Axis Y again to confirm");
//           syncUI();
//         }
//       };
//     }

//     if (btnSaveCalib) {
//       btnSaveCalib.onclick = () => {
//         if (!calibMode) return;
//         saveCalib();
//       };
//     }

//     if (btnReloadCalib) {
//       btnReloadCalib.onclick = () => loadCalib();
//     }
//   }

//   return {
//     init() {
//       installUX();
//       loadCalib();
//       syncUI();
//       log("CrosshairHUD ready. Buttons: Calib/Center/AxisX/AxisY/Save/Reload. Keys: c/0/x/y/s");
//     },

//     onTurret(rx, ry) {
//       lastRx = clamp(Number(rx ?? 0), -1, 1);
//       lastRy = clamp(Number(ry ?? 0), -1, 1);
//       render();
//     }
//   };
// })();

// function connect() {
//   const ws = new WebSocket(`ws://${location.hostname}:8000/ws`);

//   ws.onopen = () => {
//     setConn(true);
//     setWsState("open");
//     log("WS open");
//     CrosshairHUD.init();
//   };

//   ws.onclose = () => {
//     setConn(false);
//     setWsState("closed (reconnecting)");
//     log("WS closed, reconnecting...");
//     setTimeout(connect, 800);
//   };

//   ws.onerror = () => {
//     setConn(false);
//     setWsState("error");
//   };

//   ws.onmessage = (msg) => {
//     const payload = JSON.parse(msg.data);
//     const ev = payload?.data;
//     if (!ev) return;

//     if (ev.type === "telem") {
//       lastTelemTs = Date.now();
//       if (telemSrcEl) telemSrcEl.textContent = ev.src ?? "-";
//       if (latestTelemEl) latestTelemEl.textContent = JSON.stringify(ev, null, 2);
//       log(`OUT(TELEM) from ${ev.src || "unknown"}`);
    
//       // >>> ADD THIS: drive crosshair from telemetry (actual turret pose)
//       // const t = ev?.data?.turret || ev?.data?.telem?.turret || ev?.turret || null;
//       // if (t && (t.rx !== undefined || t.ry !== undefined)) {
//       //   CrosshairHUD.onTurret(t.rx ?? 0, t.ry ?? 0);
//       // }
//       return;
//     }

//     if (ev.type === "tx") {
//       lastTxTs = Date.now();
//       if (txSrcEl) txSrcEl.textContent = ev.src ?? "-";
//       if (latestTxEl) latestTxEl.textContent = JSON.stringify(ev, null, 2);
//       log(`IN(TX) from ${ev.src || "unknown"}`);

//       // ev.data = {ts,src,cmd,meta,telem}
//       const cmd = ev?.data?.cmd || ev?.data || {};
//       updateControllerFromTx(cmd);

//       // const turret = cmd?.turret || {};
//       // CrosshairHUD.onTurret(turret.rx, turret.ry);
//     }
//   };
// }

// connect();
