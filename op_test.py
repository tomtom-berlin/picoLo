# Fahrtest
#  Version 0.5ß 2024-06-05
#
from classes.operationmode import OPERATIONS as OP
from classes.servicemode import SERVICEMODE as SM
import time
import rp2


########################
def command(cv, bit):
      clx.verify_bit(cv, bit, 1)
        

def evaluate(bit, val):
    if clx.ack():
        val |= 1 << bit
    return val

def read(cv):
    cv_val = 0
    chk_val = -1
    repetitions = clx.REPETITIONS
    while chk_val != cv_val and repetitions >= 0:
        if rp2.bootsel_button():
            clx.deinit()
            raise(RuntimeError("BootSel - Abbruch"))

        for bit in range(8):
            clx.verify_bit(cv, bit, 1)
            clx.loop()
            cv_val = evaluate(bit, cv_val)
        clx.verify(cv, cv_val)
        clx.loop()
        if clx.ack():
            chk_val = cv_val
        else:
            repetitions -= 1
    if repetitions < 0:
        raise(ValueError("Lesen nicht erfolgreich"))
    return cv_val

def test_directmode_support():
    clx.verify_bit(8, 7, 1)
    clx.loop()
    directmode_support = clx.ack()
    clx.verify_bit(8, 7, 0)
    clx.loop()
    directmode_support ^= clx.ack()
    if not directmode_support:
        raise(AssertionError("Direct Mode vom Decoder nicht unterstützt"))
    
def loco_on_rail():
    I = clx.get_current()
    if I < 3:
        print("Keine Lok erkannt", end="\r")
        return False
    print(30 * " ")
    return True
    

clx = SM()
clx.begin()

t = time.ticks_ms() + 5 * 6e4  ## 5 Minuten Timeout

try:
    while not loco_on_rail() and t > time.ticks_ms():
        clx.loop()
    
    timeout = t <= time.ticks_ms()

    if timeout:
        raise(RuntimeError("Timeout"))

    for i in range(100):
        clx.loop()
    
    test_directmode_support()
    
    cv29 = read(29)
#    print("CV29 =", cv29)
    use_long_address = cv29 & 0x20
    if not cv29 & 0x02:
        speedsteps = 14
    else:
        if cv29 & 0x10:
            speedsteps = 28
        else:
            speedsteps = 128
    
    if use_long_address:
        cv17 = read(17)
        cv18 = read(18)
        addr = (cv17 - 192) * 256 + cv18
    else:
        addr = read(1)
    print(f"gefunden: Lok mit Adresse {addr}, {speedsteps} Fahrstufen")
    
except KeyboardInterrupt:
    raise(KeyboardInterrupt("Benutzer hat abgebrochen"))

clx.deinit()


########################


def drive(direction=1, speed=0):
    clx.drive(direction, speed)
    
def eventloop(t):
    global n, speed
    if t < time.ticks_ms():
        if n == 0:
            n += 1
            clx.function_on(3)
            
        elif n == 1:
            n += 1
            t += 26000
            drive(0, speed)
            
        elif n == 2:
            n += 1
            drive(0,0)

        elif n == 3:
            n += 1
            t += 27000
            drive(1, speed)
        
        elif n == 4:
            n += 1
            drive(1,0)
            
        elif n == 5:
            n += 1
            clx.function_off(3)
        
        elif n == 6:
            n += 1
            t += 5000
            clx.function_on(9)
        
        elif n == 7:
            clx.function_off(9)
            n = 0
            t = time.ticks_ms() + 2000
    return t

clx = OP(addr, use_long_address, speedsteps)
clx.begin()

n = 0    

speed_ratio = 50 # Angabe in Prozent
speed = round(speed_ratio / 100 * speedsteps)

try:
    t = time.ticks_ms() + 60000
    # 1 Minute auf eine Lok warten
    while not loco_on_rail() and t > time.ticks_ms():
        clx.loop()

    t = time.ticks_ms() + 2000
    # ein wenig hin- und herfahren
    while True:
        if rp2.bootsel_button():
            clx.deinit()
            raise(RuntimeError("BootSel - Abbruch"))

        t = eventloop(t)
        clx.loop()
        
except KeyboardInterrupt:
    clx.deinit()
    raise(KeyboardInterrupt("Benutzer hat abgebrochen"))

clx.deinit()
