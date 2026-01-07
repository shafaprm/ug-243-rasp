// app/log.js
import { CFG } from "./config.js";
import { $ } from "./dom.js";

export function log(line) {
  const now = new Date().toISOString();
  if (!$.log) return;

  $.log.textContent = `[${now}] ${line}\n` + $.log.textContent;
  const lines = $.log.textContent.split("\n");
  if (lines.length > CFG.ui.logMaxLines) {
    $.log.textContent = lines.slice(0, CFG.ui.logMaxLines).join("\n");
  }
}
