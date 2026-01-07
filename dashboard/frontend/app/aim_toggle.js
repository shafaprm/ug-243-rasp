import { CFG } from "./config.js";
import { $ } from "./dom.js";
import { log } from "./log.js";

export function initAimToggle() {
  async function setAim(src) {
    log(`Aim UI clicked => ${src}`);
    const r = await fetch(CFG.urls.aim(), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ aim_source: src }),
    });
    const j = await r.json();
    log(`Aim POST resp => ${JSON.stringify(j)}`);
    if ($.aimState) $.aimState.textContent = `AIM:${j.aim_source || "-"}`;
  }

  if ($.btnAimController) $.btnAimController.onclick = () => setAim("controller");
  else log("btn_aim_controller not found");

  if ($.btnAimDashboard) $.btnAimDashboard.onclick = () => setAim("dashboard");
  else log("btn_aim_dashboard not found");
}
