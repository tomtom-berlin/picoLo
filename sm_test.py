# Servicemode-Test
# Version 0.5ß 2024-06-05
#
from classes.servicemode import SERVICEMODE as SM
import time


def command(cv, bit):
      sm.verify_bit(cv, bit, 1)
        

def evaluate(bit, val):
    if sm.ack():
        val |= 1 << bit
    return val

def loco_on_rail():
    I = sm.get_current()
    if I < 3:
        print("Keine Lok erkannt", end="\r")
        return False
    print(30 * " ")
    return True

def read(cv):
    cv_val = 0
    chk_val = -1
    repetitions = sm.REPETITIONS
    while chk_val != cv_val and repetitions >= 0:
        for bit in range(8):
            sm.verify_bit(cv, bit, 1)
            sm.loop()
            cv_val = evaluate(bit, cv_val)
        sm.verify(cv, cv_val)
        sm.loop()
        if sm.ack():
            chk_val = cv_val
        else:
            repetitions -= 1
    if repetitions < 0:
        raise(ValueError("Lesen nicht erfolgreich"))
    return cv_val

def write(cv, val):
    repetitions = sm.REPETITIONS
    while read(cv) != val and repetitions >= 0:
        sm.write(cv, val)
        sm.loop()
        if sm.ack():
            continue
        else:
            repetitions -= 1
    if repetitions < 0:
        raise(ValueError("Lesen nicht erfolgreich"))
    return True

def test_directmode_support():
    sm.verify_bit(8, 7, 1)
    sm.loop()
    directmode_support = sm.ack()
    sm.verify_bit(8, 7, 0)
    sm.loop()
    directmode_support ^= sm.ack()
    if not directmode_support:
        raise(AssertionError("Direct Mode vom Decoder nicht unterstützt"))
    



# Liest eine Gruppe von CVs
def get_cvs(cvs = []):
    cv_array = []
    for cv in cvs:
        if 0 < cv <= 1024:
            cv_array.append((cv, read(cv)))
    return cv_array




sm = SM()
sm.begin()

t = time.ticks_ms() + 5 * 6e4  ## 5 Minuten Timeout
# for i in range(50):
#     print(sm.get_current(), "mA")

try:
    while not loco_on_rail() and t > time.ticks_ms():
        sm.loop()
    
    timeout = t <= time.ticks_ms()

    if timeout:
        raise(RuntimeError("Timeout"))

    for i in range(100):
        sm.loop()
    
    test_directmode_support()
    
    cv29 = read(29)
    print("CV29 =", cv29)
    use_long_address = cv29 & 0x20
    
    if use_long_address:
        cv17 = read(17)
        cv18 = read(18)
        addr = (cv17 - 192) * 256 + cv18
    else:
        addr = read(1)
    print(f"gefunden: Lok mit Adresse {addr}")
    
    cv_array = get_cvs([1, 2, 3, 4, 5, 6, 8, 9, 17, 18, 19, 29, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 48, 49, 50, 51, 52, 53, 123])
    for i in cv_array:
        print(f"CV{i[0]:<2}", end="  ")
    print()
    for i in cv_array:
        print(f"{i[1]:<6}", end="")
    print()
    
#     for cv in (48, 49, 50, 51, 52, 53):
#         write(cv,16)
#         print(f"CV{cv} = {read(cv)}", end=",  ")
#     print()
    
except KeyboardInterrupt:
    raise(KeyboardInterrupt("Benutzer hat abgebrochen"))

sm.deinit()
