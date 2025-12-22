from control.ps4_controller import PS4Controller
import time

ps4 = PS4Controller()
ps4.connect()

while True:
    ps4.update()
    th, st, rx, ry, fire, estop = ps4.get_manual_command()
    print(f"TH:{th:.2f} ST:{st:.2f} RX:{rx:.2f} RY:{ry:.2f} FIRE:{fire} ESTOP:{estop}")
    time.sleep(0.1)
