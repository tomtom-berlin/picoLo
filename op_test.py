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
   
def loco_on_rail():
    I = clx.get_current()
    if I < 2:
        print("Keine Lok erkannt", end="\r")
        return False
    print(30 * " ")
    return True
    

########################

def drive(direction=1, speed=0, fahrzeit=0):
    print(direction, speed, end=" ")
    t = time.ticks_ms() + fahrzeit
    while t > time.ticks_ms():
        clx.drive(direction, speed)
        clx.loop()
    print("fertig")

    

clx = OP()
clx.begin()

if speedsteps != 14:
    speedsteps = 128
speed_ratio = 65 # Angabe in Prozent
speed = round(speed_ratio * speedsteps / 100)
print(speed)
if speed > 127:
    speed = 127
    
fahrzeit = 15000
direction = 1

try:
    t = time.ticks_ms() + 60000
    # 1 Minute auf eine Lok warten
    while not loco_on_rail() and t > time.ticks_ms():
        clx.loop()

    clx.ctrl_loco(addr, use_long_address, speedsteps)
    clx.function_on(0)
    t = time.ticks_ms() + 2000
    # ein wenig hin- und herfahren
    while True:
        if rp2.bootsel_button():
            clx.power_off()
            clx.end()
            raise(RuntimeError("BootSel - Abbruch"))
        drive(direction, speed, fahrzeit)
        direction = (direction + 1) % 2
        print(direction)
        
except KeyboardInterrupt:
    clx.power_off()
    clx.end()
    raise(KeyboardInterrupt("Benutzer hat abgebrochen"))

clx.end()
