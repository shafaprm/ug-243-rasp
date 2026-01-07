// app/dom.js
export const $ = {
    conn: document.getElementById("conn"),
    wsState: document.getElementById("ws_state"),
  
    telemAge: document.getElementById("telem_age"),
    txAge: document.getElementById("tx_age"),
    telemSrc: document.getElementById("telem_src"),
    txSrc: document.getElementById("tx_src"),
  
    latestTelem: document.getElementById("latest_telem"),
    latestTx: document.getElementById("latest_tx"),
    log: document.getElementById("log"),
  
    // Camera card
    camImg: document.getElementById("cam_img"),
    camStatus: document.getElementById("cam_status"),
    camUrlLabel: document.getElementById("cam_url_label"),
  
    // Video stage & crosshair
    videoStage: document.getElementById("video_stage"),
    crosshair: document.getElementById("crosshair"),
  
    // Calib controls (optional)
    btnCalibToggle: document.getElementById("btn_calib_toggle"),
    btnSetCenter: document.getElementById("btn_set_center"),
    btnAxisX: document.getElementById("btn_axis_x"),
    btnAxisY: document.getElementById("btn_axis_y"),
    btnSaveCalib: document.getElementById("btn_save_calib"),
    btnReloadCalib: document.getElementById("btn_reload_calib"),
  
    calibState: document.getElementById("calib_state"),
    calibMode: document.getElementById("calib_mode"),
    calibHint: document.getElementById("calib_hint"),

    btnAimController: document.getElementById("btn_aim_controller"),
    btnAimDashboard:  document.getElementById("btn_aim_dashboard"),
    aimState:         document.getElementById("aim_state"),
  };
  