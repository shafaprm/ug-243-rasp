# from flask import Flask, Response, send_from_directory, jsonify, request, send_file
# import cv2
# import time
# import os, json
# APP_HOST = "0.0.0.0"
# APP_PORT = 8001

# # Set ini sesuai kamera kamu (USB cam biasanya 0)
# CAM_INDEX = 0
# JPEG_QUALITY = 80
# FPS_LIMIT = 15

# app = Flask(__name__, static_folder="../frontend", static_url_path="")

# cap = None

# def get_cap():
#     global cap
#     if cap is None or not cap.isOpened():
#         cap = cv2.VideoCapture(CAM_INDEX)
#         # optional tuning:
#         cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
#         cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
#         cap.set(cv2.CAP_PROP_FPS, FPS_LIMIT)
#     return cap

# def mjpeg_generator():
#     period = 1.0 / max(1e-6, FPS_LIMIT)
#     next_t = time.time()

#     while True:
#         c = get_cap()
#         ok, frame = c.read()
#         if not ok:
#             # camera glitch, retry
#             time.sleep(0.2)
#             continue

#         ok, jpg = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
#         if not ok:
#             continue

#         yield (b"--frame\r\n"
#                b"Content-Type: image/jpeg\r\n\r\n" + jpg.tobytes() + b"\r\n")

#         next_t += period
#         sleep_s = next_t - time.time()
#         if sleep_s > 0:
#             time.sleep(sleep_s)
#         else:
#             next_t = time.time()

# @app.get("/")
# def index():
#     return send_from_directory(app.static_folder, "index.html")

# @app.get("/<path:path>")
# def static_files(path):
#     return send_from_directory(app.static_folder, path)

# @app.get("/stream.mjpg")
# def stream():
#     return Response(mjpeg_generator(),
#                     mimetype="multipart/x-mixed-replace; boundary=frame")

# @app.get("/api/calib/crosshair")
# def get_crosshair():
#     if not os.path.exists("calibration/crosshair.json"):
#         return jsonify({
#             "rx0": 0.0,
#             "ry0": 0.0,
#             "sx": 260.0,
#             "sy": 240.0,
#             "invert_y": True
#         })
#     return send_file("calibration/crosshair.json")

# @app.post("/api/calib/crosshair")
# def save_crosshair():
#     os.makedirs("calibration", exist_ok=True)
#     data = request.json
#     with open("calibration/crosshair.json", "w") as f:
#         json.dump(data, f, indent=2)
#     return {"ok": True}

# fetch("/api/calib/crosshair")
#   .then(r => r.json())
#   .then(cfg => CrosshairHUD.init(cfg));

# fetch("/api/calib/crosshair", {
#   method: "POST",
#   headers: {"Content-Type":"application/json"},
#   body: JSON.stringify(cfg)
# });

# if __name__ == "__main__":
#     app.run(host=APP_HOST, port=APP_PORT, threaded=True)

from flask import Flask, Response, send_from_directory, jsonify, request
import cv2
import time
import os
import json

APP_HOST = "0.0.0.0"
APP_PORT = 8001

# Set ini sesuai kamera kamu (USB cam biasanya 0)
CAM_INDEX = 0
JPEG_QUALITY = 80
FPS_LIMIT = 15

# Folder calibration disimpan relatif ke file ini
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CALIB_DIR = os.path.join(BASE_DIR, "calibration")
CROSSHAIR_PATH = os.path.join(CALIB_DIR, "crosshair.json")

# Static frontend (sesuaikan path)
# Struktur yang aman:
# project/
#   backend/camera_server.py
#   frontend/index.html, app.js, styles.css
FRONTEND_DIR = os.path.join(BASE_DIR, "..", "frontend")

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")

cap = None

def get_cap():
    global cap
    if cap is None or not cap.isOpened():
        cap = cv2.VideoCapture(CAM_INDEX)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        cap.set(cv2.CAP_PROP_FPS, FPS_LIMIT)
    return cap

def mjpeg_generator():
    period = 1.0 / max(1e-6, FPS_LIMIT)
    next_t = time.time()

    while True:
        c = get_cap()
        ok, frame = c.read()
        if not ok:
            time.sleep(0.2)
            continue

        ok, jpg = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
        if not ok:
            continue

        yield (b"--frame\r\n"
               b"Content-Type: image/jpeg\r\n\r\n" + jpg.tobytes() + b"\r\n")

        next_t += period
        sleep_s = next_t - time.time()
        if sleep_s > 0:
            time.sleep(sleep_s)
        else:
            next_t = time.time()

@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")

@app.get("/<path:path>")
def static_files(path):
    return send_from_directory(app.static_folder, path)

@app.get("/stream.mjpg")
def stream():
    return Response(mjpeg_generator(),
                    mimetype="multipart/x-mixed-replace; boundary=frame")

@app.get("/api/calib/crosshair")
def get_crosshair():
    # default config
    default_cfg = {
        "rx0": 0.0,
        "ry0": 0.0,
        "sx": 260.0,
        "sy": 240.0,
        "invert_y": True
    }

    if not os.path.exists(CROSSHAIR_PATH):
        return jsonify(default_cfg)

    try:
        with open(CROSSHAIR_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        # merge with defaults for safety
        default_cfg.update(data if isinstance(data, dict) else {})
        return jsonify(default_cfg)
    except Exception:
        return jsonify(default_cfg)

@app.post("/api/calib/crosshair")
def save_crosshair():
    os.makedirs(CALIB_DIR, exist_ok=True)

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"ok": False, "err": "invalid json"}), 400

    # sanitize keys (only allow expected)
    allowed = {"rx0", "ry0", "sx", "sy", "invert_y"}
    clean = {k: data[k] for k in data.keys() if k in allowed}

    # type normalize (best effort)
    def to_float(v, default=0.0):
        try:
            return float(v)
        except Exception:
            return default

    cfg = {
        "rx0": to_float(clean.get("rx0", 0.0), 0.0),
        "ry0": to_float(clean.get("ry0", 0.0), 0.0),
        "sx":  to_float(clean.get("sx", 260.0), 260.0),
        "sy":  to_float(clean.get("sy", 240.0), 240.0),
        "invert_y": bool(clean.get("invert_y", True)),
    }

    with open(CROSSHAIR_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

    return jsonify({"ok": True, "path": "calibration/crosshair.json", "cfg": cfg})

if __name__ == "__main__":
    app.run(host=APP_HOST, port=APP_PORT, threaded=True)
