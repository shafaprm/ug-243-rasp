// app/main.js
import { initCameraView } from "./camera_view.js";
import { createWsClient } from "./ws_client.js";
import { createCrosshairHUD } from "./crosshair_hud.js";
import { log } from "./log.js";
import { initAimToggle } from "./aim_toggle.js";

initCameraView();
initAimToggle();

const hud = createCrosshairHUD();
hud.init();

const ws = createWsClient({ hud });
ws.connect();

log("Dashboard boot complete.");
