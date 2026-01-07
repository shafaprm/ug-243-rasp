SERIAL_PORT = "/dev/ttyACM0"   # ganti kalau Arduino muncul sebagai /dev/ttyUSB0
BAUDRATE = 115200

CONTROL_HZ = 20
TELEMETRY_PRINT_HZ = 10


# Dashboard IPC (UDP)
DASH_UDP_HOST = "127.0.0.1"
DASH_UDP_PORT = 15555

# Publish rate limiting (optional)
DASH_PUB_TX_HZ = 2      # max publish TX to dashboard = 10
DASH_PUB_TELEM_HZ = 5   # max publish telem to dashboard = 20
