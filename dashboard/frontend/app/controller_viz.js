// app/controller_viz.js
import { clamp } from "./utils.js";

function clearActive() {
  document.querySelectorAll(
    ".btn-triangle.active,.btn-circle.active,.btn-cross.active,.btn-square.active," +
    ".btn-dpad.active,.btn-shoulder.active,.btn-trigger.active,.btn-stick.active," +
    ".btn-options.active,.btn-share.active,.btn-ps.active"
  ).forEach(el => el.classList.remove("active"));
}

/**
 * cmd = {
 *   estop: bool,
 *   drive: { th: [-1..1], st: [-1..1] },
 *   turret: { rx: [-1..1], ry: [-1..1], fire: bool }
 * }
 */
export function updateControllerFromTx(cmd) {
  clearActive();

  const drive = cmd?.drive || {};
  const turret = cmd?.turret || {};

  const fire = !!turret.fire;
  const estop = !!cmd.estop;

  if (fire) document.querySelector(".btn-square")?.classList.add("active");
  if (estop) document.querySelector(".btn-ps")?.classList.add("active");

  const st = clamp(Number(drive.st ?? 0), -1, 1);
  const rx = clamp(Number(turret.rx ?? 0), -1, 1);
  const ry = clamp(Number(turret.ry ?? 0), -1, 1);

  const leftStick = document.querySelector(".stick-left");
  const rightStick = document.querySelector(".stick-right");

  const L_BASE_X = 213, L_BASE_Y = 206;
  const R_BASE_X = 388, R_BASE_Y = 206;
  const RANGE = 15;

  if (leftStick) {
    leftStick.setAttribute("cx", (L_BASE_X + st * RANGE).toFixed(1));
    leftStick.setAttribute("cy", (L_BASE_Y + 0 * RANGE).toFixed(1));
    if (Math.abs(st) > 0.05) leftStick.classList.add("active");
  }

  if (rightStick) {
    rightStick.setAttribute("cx", (R_BASE_X + rx * RANGE).toFixed(1));
    rightStick.setAttribute("cy", (R_BASE_Y + ry * RANGE).toFixed(1));
    if (Math.abs(rx) > 0.05 || Math.abs(ry) > 0.05) rightStick.classList.add("active");
  }

  const th = clamp(Number(drive.th ?? 0), -1, 1);
  const r2p = th > 0 ? th : 0;
  const l2p = th < 0 ? -th : 0;

  const l2 = document.querySelector(".l2");
  const r2 = document.querySelector(".r2");

  if (l2) {
    const p = clamp(l2p, 0, 1);
    l2.style.opacity = (0.4 + p * 0.6).toFixed(2);
    if (p > 0.1) l2.classList.add("active");
  }

  if (r2) {
    const p = clamp(r2p, 0, 1);
    r2.style.opacity = (0.4 + p * 0.6).toFixed(2);
    if (p > 0.1) r2.classList.add("active");
  }
}
