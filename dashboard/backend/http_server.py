from flask import Flask, Response, send_from_directory, jsonify, request
import time
import os
import json

# =============================
# CONFIG
# =============================
APP_HOST = "0.0.0.0"
APP_PORT = 8001

# Stream settings
JPEG_QUALITY = 80
FPS_LIMIT = 15

# Resolution for Pi AI Camera
FRAME_W = 1280
FRAME_H = 720

# If you still want USB cam fallback
CAM_INDEX = 0

# =============================
# PATHS
# =============================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CALIB_DIR = os.path.join(BASE_DIR, "calibration")
CROSSHAIR_PATH = os.path.join(CALIB_DIR, "crosshair.json")

# Static frontend (relative to this backend file)
FRONTEND_DIR = os.path.join(BASE_DIR, "..", "frontend")

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")

# =============================
# CAMERA BACKENDS
# =============================

# We'll use OpenCV only for JPEG encoding + color conversion
import cv2

# Preferred: Picamera2 for Raspberry Pi AI Camera / CSI camera
_picam2 = None
_cap = None  # OpenCV VideoCapture fallback
_backend = None  # "picamera2" or "opencv"


def _init_picamera2():
    """Initialize Raspberry Pi camera using Picamera2."""
    global _picam2, _backend

    try:
        from picamera2 import Picamera2
    except Exception as e:
        return False, f"picamera2 import failed: {e}"

    try:
        picam2 = Picamera2()

        # create_video_configuration is good for streaming
        # format RGB888 gives easy numpy array for OpenCV
        config = picam2.create_video_configuration(
            main={"size": (FRAME_W, FRAME_H), "format": "RGB888"}
        )
        picam2.configure(config)
        picam2.start()

        # Small warmup
        time.sleep(0.2)

        _picam2 = picam2
        _backend = "picamera2"
        return True, "picamera2 OK"
    except Exception as e:
        _picam2 = None
        return False, f"picamera2 init failed: {e}"


def _init_opencv_v4l2():
    """Fallback init for USB webcam or /dev/video0."""
    global _cap, _backend
    try:
        cap = cv2.VideoCapture(CAM_INDEX)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_W)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_H)
        cap.set(cv2.CAP_PROP_FPS, FPS_LIMIT)
        if not cap.isOpened():
            return False, "OpenCV VideoCapture cannot open camera index"
        _cap = cap
        _backend = "opencv"
        return True, "opencv OK"
    except Exception as e:
        _cap = None
        return False, f"opencv init failed: {e}"


def ensure_camera():
    """
    Ensure one camera backend is active.
    Priority: picamera2 -> opencv fallback
    """
    global _backend

    # if already initialized and looks alive, keep it
    if _backend == "picamera2" and _picam2 is not None:
        return True
    if _backend == "opencv" and _cap is not None and _cap.isOpened():
        return True

    # try picamera2 first
    ok, msg = _init_picamera2()
    if ok:
        print("[CAM] Using Picamera2 (CSI / AI camera).")
        return True
    else:
        print("[CAM] Picamera2 not available:", msg)

    # fallback to OpenCV
    ok, msg = _init_opencv_v4l2()
    if ok:
        print("[CAM] Using OpenCV VideoCapture (USB / V4L2).")
        return True
    else:
        print("[CAM] OpenCV camera not available:", msg)

    return False


def read_frame_rgb():
    """
    Returns frame as RGB (H,W,3) uint8, or None if failed.
    """
    if not ensure_camera():
        return None

    if _backend == "picamera2":
        try:
            frame = _picam2.capture_array()  # RGB888 -> numpy array
            return frame
        except Exception as e:
            print("[CAM] picamera2 capture failed:", e)
            return None

    # opencv backend
    try:
        ok, frame_bgr = _cap.read()
        if not ok or frame_bgr is None:
            return None
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        return frame_rgb
    except Exception as e:
        print("[CAM] opencv capture failed:", e)
        return None


def mjpeg_generator():
    period = 1.0 / max(1e-6, FPS_LIMIT)
    next_t = time.time()

    while True:
        frame_rgb = read_frame_rgb()
        if frame_rgb is None:
            # camera glitch / not ready
            time.sleep(0.2)
            continue

        # Convert to BGR for OpenCV encode to avoid weird colors
        frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)

        ok, jpg = cv2.imencode(
            ".jpg",
            frame_bgr,
            [int(cv2.IMWRITE_JPEG_QUALITY), int(JPEG_QUALITY)],
        )
        if not ok:
            continue

        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + jpg.tobytes() + b"\r\n"
        )

        next_t += period
        sleep_s = next_t - time.time()
        if sleep_s > 0:
            time.sleep(sleep_s)
        else:
            next_t = time.time()


# =============================
# ROUTES: FRONTEND + STREAM
# =============================
@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/<path:path>")
def static_files(path):
    return send_from_directory(app.static_folder, path)


@app.get("/stream.mjpg")
def stream():
    return Response(
        mjpeg_generator(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


# =============================
# ROUTES: CALIBRATION API
# =============================
@app.get("/api/calib/crosshair")
def get_crosshair():
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
        if isinstance(data, dict):
            default_cfg.update(data)
        return jsonify(default_cfg)
    except Exception:
        return jsonify(default_cfg)


@app.post("/api/calib/crosshair")
def save_crosshair():
    os.makedirs(CALIB_DIR, exist_ok=True)

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"ok": False, "err": "invalid json"}), 400

    allowed = {"rx0", "ry0", "sx", "sy", "invert_y"}
    clean = {k: data[k] for k in data.keys() if k in allowed}

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


# =============================
# ENTRY
# =============================
if __name__ == "__main__":
    # Try init camera early so error terlihat jelas
    ensure_camera()
    app.run(host=APP_HOST, port=APP_PORT, threaded=True)
