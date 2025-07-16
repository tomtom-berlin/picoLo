# Fahrtest
#  Version 0.91ß 2025-07-16
#
from classes.operationmode import OPERATIONS as OP
from classes.servicemode import SERVICEMODE as SM
import time
import rp2

# hier einstellen
speedsteps=128
addr=545
use_long_address = True
fahrzeit = 15
direction = 0 # Richtung zu Beginn, rückwärts = 0, vorwärts = 1


def loco_on_rail():
    I = clx.get_current()
    if I < 2:
        print("Keine Lok erkannt", end="\r")
        return False
    print(30 * " ")
    return True
    

########################

def drive(direction=1, speed=0, fahrzeit=0):
    t = time.ticks_ms() + (fahrzeit * 1000)
    while t > time.ticks_ms():
        clx.drive(direction, speed)
        clx.loop()

    

clx = OP()
clx.begin()

if speedsteps != 14:
    speedsteps = 128
speed_ratio = 65 # Angabe in Prozent
speed = round(speed_ratio * speedsteps / 100)

if speed > 127:
    speed = 127

f = 0

try:
    t = time.ticks_ms() + 60000
    # 1 Minute auf eine Lok warten
    while not loco_on_rail() and t > time.ticks_ms():
        clx.loop()

    clx.ctrl_loco(addr, use_long_address, speedsteps)
    t = time.ticks_ms() + 2000
    # ein wenig hin- und herfahren
    d = direction
    while True:
        if rp2.bootsel_button():
            clx.power_off()
            clx.end()
            raise(RuntimeError("BootSel - Abbruch"))
        clx.function_on(f)
        drive(d, speed, fahrzeit)
        d = 1 if d == 0 else 0
        clx.function_off(f)
        if d == direction:
            f += 1
            f %= 13
        
except KeyboardInterrupt:
    clx.power_off()
    clx.end()
    raise(KeyboardInterrupt("Benutzer hat abgebrochen"))

clx.end()

