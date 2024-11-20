# Fahrtest
#  Version 0.51ß 2024-11-20
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
            clx.end()
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
        clx.statemachine.end()
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
        clx.statemachine.end()
        raise(AssertionError("Direct Mode vom Decoder nicht unterstützt"))
    
def loco_on_rail():
    I = clx.get_current()
    if I < 2:
        print("Keine Lok erkannt", end="\r")
        return False
    print(30 * " ")
    return True
    

clx = SM()
clx.begin()

# addr = 3
# speedsteps = 28
# use_long_address = False

t = time.ticks_ms() + 5 * 6e4  ## 5 Minuten Timeout

try:
    while not loco_on_rail() and t > time.ticks_ms():
        clx.loop()
    
    timeout = t <= time.ticks_ms()

    if timeout:
        clx.statemachine.end()
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
    clx.end()
    raise(KeyboardInterrupt("Benutzer hat abgebrochen"))

clx.end()

########################

#speedsteps=28
#addr=8489
#use_long_address = True

def drive(direction=1, speed=0):
    clx.drive(direction, speed)
    
def eventloop(t):
    global r, n, aspect, speed, rounds, fahrzeit, direction
    if t < time.ticks_ms():
        if n == 0:
            n += 1
            clx.ctrl_accessory_basic(3, clx.ACTIVATE, r)
            r = clx.LEFT_OR_STOP if r == clx.RIGHT_OR_TRAVEL else clx.RIGHT_OR_TRAVEL
            
        elif n == 1:
            n += 1
            t += fahrzeit
            if direction == 1:
                t += 1000
            drive(direction, speed)
            
        elif n == 2:
            n += 1
            drive(direction,0)

        elif n == 3:
            n += 1
            t += fahrzeit
            if direction == 0:
                t += 1000
            drive(0 if direction == 1 else 1, speed)
            if aspect == 0b11111111:
                aspect = aspect_halt
            elif aspect == aspect_halt:
                aspect = 0b10000111
                
            clx.ctrl_accessory_extended(5, aspect)
            aspect = ((aspect << 1) & 0xff) | 0b10000001
        
        elif n == 4:
            n += 1
            drive(0 if direction == 1 else 1,0)
            
        elif n == 5:
            n += 1
        
        elif n == 6:
            n += 1
            t += 1000
        
        elif n == 7:
            n = 0
            rounds += 1
            t = time.ticks_ms() + 2000
    return t

#addr, use_long_address, speedsteps = recognize_loco()

clx = OP()
clx.begin()

n = 0
rounds = 0

r = clx.LEFT_OR_STOP
aspect = 0b10000111
aspect_halt = 0b00000000

if speedsteps != 14:
    speedsteps = 28
speed_ratio = 100 # Angabe in Prozent
speed = round(speed_ratio / 100) * speedsteps
if speed > 127:
    speed = 127
    
fahrzeit = 17000
direction = 0
try:
    t = time.ticks_ms() + 60000
    # 1 Minute auf eine Lok warten
    while not loco_on_rail() and t > time.ticks_ms():
        clx.loop()

    clx.ctrl_loco(addr, use_long_address, speedsteps)
    clx.function_on(3)
    t = time.ticks_ms() + 2000
    # ein wenig hin- und herfahren
    while True:
        if rp2.bootsel_button():
            clx.power_off()
            clx.end()
            raise(RuntimeError("BootSel - Abbruch"))

        t = eventloop(t)
        clx.loop()
#        time.sleep(0.5)
        
except KeyboardInterrupt:
    clx.power_off()
    clx.end()
    raise(KeyboardInterrupt("Benutzer hat abgebrochen"))

clx.end()
