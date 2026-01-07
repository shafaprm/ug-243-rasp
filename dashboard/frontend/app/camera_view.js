// app/camera_view.js
import { CFG } from "./config.js";
import { $ } from "./dom.js";
import { log } from "./log.js";

export function initCameraView() {
  if (!$.camImg) return;

  const streamUrl = CFG.urls.stream();
  if ($.camUrlLabel) $.camUrlLabel.textContent = streamUrl;

  $.camImg.onload = () => { if ($.camStatus) $.camStatus.textContent = "RUNNING"; };
  $.camImg.onerror = () => { if ($.camStatus) $.camStatus.textContent = "FAILED"; };

  $.camImg.src = streamUrl + `?t=${Date.now()}`;
  if ($.camStatus) $.camStatus.textContent = "LOADING";

  log(`CameraView: loading ${streamUrl}`);
}
