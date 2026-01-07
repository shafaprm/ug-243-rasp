// app/config.js
export const CFG = {
  host: () => location.hostname,

  ports: {
    ws: 8000,
    api: 8000,  // http api backend (uvicorn)
    cam: 8001,
  },

  urls: {
    ws:     () => `ws://${CFG.host()}:${CFG.ports.ws}/ws`,
    tx:     () => `http://${CFG.host()}:${CFG.ports.api}/api/tx`,
    aim:    () => `http://${CFG.host()}:${CFG.ports.api}/api/aim`,
    stream: () => `http://${CFG.host()}:${CFG.ports.cam}/stream.mjpg`,

    // kalau calib memang ada di camera server (8001) tetap begini:
    calib:  () => `http://${CFG.host()}:${CFG.ports.cam}/api/calib/crosshair`,
  },

  ui: {
    logMaxLines: 120,
    ageTickMs: 200,
  }
};
