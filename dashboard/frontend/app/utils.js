// app/utils.js
export function clamp(x, lo, hi) {
    return Math.max(lo, Math.min(hi, x));
  }
  
  export function fmtAge(ms) {
    if (!ms) return "-";
    return `${(ms / 1000.0).toFixed(2)} s`;
  }
  
  export function safeJsonParse(str) {
    try { return JSON.parse(str); } catch { return null; }
  }
  