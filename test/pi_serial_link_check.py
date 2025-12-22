import serial
import time
import json

PORT = "/dev/ttyACM0"   # pastikan sesuai
BAUD = 115200

print("Opening serial:", PORT)
ser = serial.Serial(PORT, BAUD, timeout=0.5)

# Arduino reset saat serial open
time.sleep(2.0)

print("Listening for Arduino output (3s)...")
t_end = time.time() + 15.0
got_any = False

while time.time() < t_end:
    if ser.in_waiting:
        line = ser.readline().decode(errors="ignore").strip()
        if line:
            print("RX:", line)
            got_any = True

if not got_any:
    print("❌ TIDAK ADA OUTPUT dari Arduino")
    print("   → kemungkinan salah port / kabel / Arduino tidak jalan")
    ser.close()
    exit(1)

print("\nArduino terlihat hidup ✅")

# ============================
# KIRIM COMMAND VALID (sesuai Comm.cpp)
# ============================
cmd = {
    "cmd": "set",
    "mode": "safe",
    "estop": True,
    "drive": {"th": 0.0, "st": 0.0},
    "turret": {"rx": 0.0, "ry": 0.0, "fire": False},
}

line = json.dumps(cmd, separators=(",", ":"))
print("\nSending command:")
print("TX:", line)

ser.write((line + "\n").encode("utf-8"))

# ============================
# TUNGGU BALASAN TELEMETRY
# ============================
print("\nWaiting telemetry (15s)...")
t_end = time.time() + 3.0
got_telem = False

while time.time() < t_end:
    if ser.in_waiting:
        line = ser.readline().decode(errors="ignore").strip()
        if not line:
            continue
        print("RX:", line)
        if line.startswith("{") and '"stat"' in line:
            got_telem = True
            break

ser.close()

if got_telem:
    print("\n✅ KONEKSI PI ↔ ARDUINO BERHASIL")
else:
    print("\n❌ Arduino TIDAK membalas telemetry")
    print("   → kemungkinan parse error / baud mismatch / flood")
