# Fahrtest
#  Version 0.52ß 2025-07-16
#

from classes.operationmode import OPERATIONS as OP
from classes.servicemode import SERVICEMODE as SM
import time
#import rp2
import uselect as select
from machine import Timer, Pin, I2C
from libraries.ssd1309 import Display as DISPLAY
from libraries.xglcd_font import XglcdFont as fm
import os, re
import sys

######################################################################
        
def text(display, font, col, line, text):
    text_height = font.height
    text_width = font.measure_text(text)
    while text_width > 127:
        text = text[:-1]
        text_width = font.measure_text(text)
        
    display.draw_text(col, line, text, font, rotate=0)
    display.present()

def get_font_size(path, pattern):
    f = open(path)
    r = (5, 8)
    matches = None
    l = f.readline()
    while l > "":
        matches = pattern.match(l)
        if matches:
            r = matches.groups()
            f.close
            return r
        l = f.readline()

    return r

###########################################

speedsteps = None
loco = None
access = None
use_long_access = False
functions = []
    
op = None
sm = None
########################
        

def finish():
    if not timer_cpufreq == None:
        timer_cpufreq.deinit()
    if not op == None:
        op.emergency_stop()
        op.power_off()
        op.end()
    if not oled == None:
        oled.clear()
        font = fm(f"/libraries/fonts/PerfectPixel_18x25.c", 18, 25)
        oled.draw_text(0, 15 if oled.height > 32 else 0, f"{'ENDE':^7}", font, rotate=0)
        oled.present()
        time.sleep(5)
        oled.cleanup()

def get_loco_profile():

    def read_cv(cv):
        cv_val = 0
        for cv_val in range(256):
            repetitions = 3
            while repetitions > 0:
                sm.verify(cv, cv_val)
                if sm.ack():
                    return cv_val
                else:
                    repetitions -= 1
                
        if cv_val == 255 and repetitions == 0:
            sm.end()
            raise(ValueError(f"Lesen von CV {cv} nicht erfolgreich"))
        return cv_val

    def read(cv):
        if directmode == False:
            return read_cv(cv)
        cv_val = 0
        chk_val = -1
        repetitions = sm.REPETITIONS
        while chk_val != cv_val and repetitions >= 0:
            for bit in range(8):
                sm.verify_bit(cv, bit, 1)
                if sm.ack():
                    cv_val |= 1 << bit
            sm.verify(cv, cv_val)
            if sm.ack():
                chk_val = cv_val
            else:
                repetitions -= 1
        if repetitions < 0:
            sm.end()
            raise(ValueError(f"Lesen von CV {cv} nicht erfolgreich"))
        return cv_val

    def test_directmode_support():
        sm.verify_bit(8, 7, 1)
        directmode_support = sm.ack()
        sm.verify_bit(8, 7, 0)
        directmode_support ^= sm.ack()
        return directmode_support
        
        
    sm = SM()
    sm.begin()

    t = time.ticks_ms() + 5 * 6e4  ## 5 Minuten Timeout

    try:
        while t > time.ticks_ms():
            I = sm.get_current()
            if I < -1:
                print(f"Keine Lok erkannt ({I:>4} mA)", end="\r")
            else:
                break
     
        print(30 * " ")

        timeout = t <= time.ticks_ms()

        if timeout:
            sm.statemachine.end()
            return(None, 0, 0)

        for i in range(100):
            sm.loop()
        
        directmode = test_directmode_support()
        
        cv29 = read(29)
        use_long_address = cv29 & 0x20
        if not cv29 & 0x02:
            speedsteps = 14
        else:
            if cv29 & 0b10:
                if cv29 & 0b1000:
                    speedsteps = 28 # indiv. Tabelle
                else:
                    speedsteps = 128
            else:
                speedsteps = 14
        
        if use_long_address:
            cv17 = read(17)
            cv18 = read(18)
            loco = (cv17 - 192) * 256 + cv18
        else:
            loco = read(1)
        
    except KeyboardInterrupt:
        sm.end()
        raise(KeyboardInterrupt("Benutzer hat abgebrochen"))

    sm.end()
    return (loco, use_long_address, speedsteps)


########################

def drive(direction=1, speed=0):
    op.drive(direction, speed)
 
def halt():
    op.drive(direction, 0)
    time.sleep(0.5)

def pom_input():
    i = 1
    j = 0
    addr = 0
    cv = 0
    val = 0
    while i < len(input_buffer):
        c = input_buffer[i]
        if c == '*' or c == ',':
            if j == 0:
                addr = val
                j += 1
                val = 0
            elif j == 1:
                cv = val
                j += 1
                val = 0
        else:
            val = val * 10 + int(c)

        i += 1
    return (addr, cv, val)
        
def pom_acc():
    (addr, cv, value) = pom_input()
    print(f"PoM Accessory Addr {addr}, CV {cv} = {value}")
    op.pom_accessory(addr, cv, value)
#     pass

def pom_loco():
    (addr, cv, value) = pom_input()
    print(f"PoM Loco Addr {addr}, CV {cv} = {value}")
    op.pom_multi(addr, cv, value)
#     pass

def show_fn():
    print(" F0  F1  F2  F3  F4  F5  F6  F7  F8  F9 F10 F11 F12")
    for f in range(0, 13):
        print(f"{'*' if op.get_function(f) else ' ':^4}", end="")
    print()
    
def get_loco():
    global loco, use_long_address, speedsteps
    clear_input_buffer()
    op.end()
    loco, use_long_address, speedsteps = get_loco_profile()
    set_loco_data(loco)
    print(f"Lok {loco}, {'Lange' if use_long_address else 'Kurze'} Adresse, {speedsteps} Fahrstufen")
    op.begin()
    op.ctrl_loco(loco, use_long_access, speedsteps)
    print(f"Lok {loco} bereit")
    
def process_input_buffer():
    global loco, turnout, speed, max_speed, direction
    cmd = None
    value = 0
    if len(input_buffer) > 0:
        cmd = input_buffer[0]
        if  cmd == 'P' or cmd == 'p':
            pom_loco()
        elif cmd == 'A' or cmd == 'a':
            pom_acc()
        elif not (cmd == 'l' or cmd == 'L' or cmd == 'w' or cmd == 'W') and loco == None:
            print("no loco")
            return
            
        if cmd in ['V', 'v', 'R', 'r', 'f', 'F', 'l', 'L', 'd', 'D', 'w', 'W', '+', '-']:
            if cmd in ['f', 'F', 'w', 'W', 'l', 'L', 'd', 'D', 'v', 'r']:
                for i in range(1, len(input_buffer)):
                    value = value * 10 + int(input_buffer[i])
                if cmd == 'l' or cmd == 'L':
                    if len(input_buffer) == 1:
                        get_loco()
                    else:
                        print(f"Lok {value} bedienen")
                        loco = value
                        if loco != None:
                            set_loco_data(loco)
                            op.ctrl_loco(loco, use_long_access, speedsteps)
                            
                elif cmd == 'd' or cmd == 'D':
                    if len(input_buffer) == 1:
                        show_locos()
                    else:
                        if loco == value:
                            print(f"Aktive Lok kann nicht aus Liste entfernt werden")
                        else:
                            for l in op.locos:
                                if l.address == value:
                                    op.locos.remove(l)
                                    print(f"Keine Pakete mehr an Lok {value} senden")

                elif cmd == 'f' or cmd == 'F':
                    if len(input_buffer) == 1:
                        show_fn()
                    else:
                        fn = op.get_function(value)
                        print(f"Funktion {value} {'aus' if fn else 'ein'}")
                        if fn:
                            op.function_off(value)
                        else:
                            op.function_on(value)
                        
                elif cmd == 'w':
                    print(f"Weiche {value} gerade")
                    op.ctrl_accessory_basic(value, 1, 0)
                    
                elif cmd == 'W':
                    print(f"Weiche {value} abzweigend")
                    op.ctrl_accessory_basic(value, 1, 1)
                    
                elif cmd == 'r':  # Richtung rueckwaerts
                    if(direction == 1):
                        halt()
                        print("HALT", end=" ")
                        time.sleep(1.5)
                    if value != 0:
                        speed = value if speed <= max_speed else max_speed
                    print(f"Lok {loco} <-- Fahrstufe {speed}")
                    direction = 0
                    drive(direction, speed)
                    
                elif cmd == 'v':  # Richtung vorwaerts
                    if(direction == 0):
                        halt()
                        print("HALT", end=" ")
                        time.sleep(1.5)
                    if value != 0:
                        speed = value if speed <= max_speed else max_speed
                    print(f"Lok {loco} --> Fahrstufe {speed}")
                    direction = 1
                    drive(direction, speed)

            elif cmd == 'R':  # Richtung rueckwaerts, Höchstgeschwindigkeit
                if(direction == 1):
                    halt()
                speed = max_speed
                direction = 0
                print(f"Lok {loco} HALT, <-- Fahrstufe {max_speed}")
                drive(direction, speed)
            elif cmd == 'V':  # Richtung vorwaerts, Höchstgeschwindigkeit
                if(direction == 0):
                    halt()
                speed = max_speed
                direction = 1
                print(f"Lok {loco} HALT, --> Fahrstufe {max_speed}")
                drive(direction, speed)
        else:
            cmd = None
            
def clear_input_buffer():
    global input_buffer
    input_buffer = []

def usage():
    print("""
Benutzung:
Zeichen eingeben und mit Enter abschicken

Zeichen| Führt aus
-------+---------------------------------------------------------------------
?      | Diese Hilfe
e      | Nothalt alle Fahrzeuge
       |
l      | Lok suchen
l{nnn} | Lok bedienen {nnn} = Dekoder-Adresse
v{nnn} | Lok vorwärts Fahrstufe {nnn}
r{nnn} | Lok rückwärts Fahrstufe {nnn}
+      | Lok Fahrstufe erhöhen um 1 (mehrere Plus = Anzahl der Fahrstufen)
-      | Lok Fahrstufe verringern um 1 (mehrere Minus = Anzahl der Fahrstufen)
V      | Lok vorwärts höchste Fahrstufe
R      | Lok rückwärts höchste Fahrstufe
h      | Lok Halt
       |
F|f{nn}| Funktion {nn = 0..12} ein/ausschalten
f o. F | Welche Funktionen sind eingeschaltet?
       |
w{nnn} | Weiche geradeaus {nnn} = Weichenadresse
W{nnn} | Weiche abzweigend {nnn} = Weichenadresse
       |
q o. Q | Beenden
-------+---------------------------------------------------------------------
       |
PoM:   | [P, p, A, a]{Adresse, CV-Nummer, Wert}
P o. p | für Multifunktionsdekoder
A o. a | für Accessory-Decoder 
-----------------------------------------------------------------------------


"""
)


def eventloop():
    global direction, max_speed, speed, loco, use_long_address, speedsteps
    c = kbd_in()
    if c != None:
        if c == 'e' or c == 'E': # Nothalt alles
            clear_input_buffer()            
            print(f"Nothalt")
            op.emergency_stop()
            
        elif c == 'q' or c == 'Q': # Ende
            return False
#         print(f"{c}, buffer:{input_buffer}")
        if c == 'H' or c == 'h': # Halt
            clear_input_buffer()            
            print(f"Lok {loco} Halt")
            speed = 0
            halt()
        
        elif c == '+':
            clear_input_buffer()            
            if speed < max_speed:
                speed += 1
            print(f"Lok {loco} Fahrstufe {speed}")
            drive(direction, speed)

        elif c == '-':
            clear_input_buffer()            
            if speed > 0:
                speed -= 1
            print(f"Lok {loco} Fahrstufe {speed}")
            drive(direction, speed)

        elif c == '?':
            usage()

        elif c == '#' or c == '\n':
            process_input_buffer()
            clear_input_buffer()            
        else:
            input_buffer.append(c)
    return True


def start_display():
    global font
    SCL_PIN = 5
    SDA_PIN = 4
    i2c = I2C(0, scl=Pin(SCL_PIN), sda=Pin(SDA_PIN), freq=400000)
    adr_i2c = i2c.scan()
    # print(f"Devices @ {adr_i2c}")

    oled = DISPLAY(i2c=i2c, width=128)
    oled.clear()
    font = fm(f"/libraries/fonts/PerfectPixel_18x25.c", 18, 25)
    text(oled, font, 0, 15, f"{'FAHREN':^7}")
    time.sleep(3)
    font = fm(f"/libraries/fonts/FixedFont5x8.c", 5, 8)
    oled.clear()
    return oled


def set_loco_data(loco):
    global functions, speed, speedsteps, max_speed, direction, speed_ratio
    functions = []
    direction = 0
    if speedsteps == None:
        speedsteps = 128
        
    if loco == 3:
        speed_ratio = 95 # Angabe in Prozent
        functions = [0, 8, 9, 10]
    elif loco == 10:
        speed_ratio = 75 # Angabe in Prozent
        direction = 1
        functions = [3]
    elif loco == 20:
        speed_ratio = 75 # Angabe in Prozent
        direction = 1
        functions = [3]
    elif loco == 23:
        speed_ratio = 100 # Angabe in Prozent
        direction = 1
    #    functions = [3]
    elif loco == 55:
        speed_ratio = 33 # Angabe in Prozent
        functions = [1,4,5]
    elif loco == 89:
        speed_ratio = 60 # Angabe in Prozent
        functions= [4]
        direction = 1
    elif loco == 133:
        speed_ratio = 70 # Angabe in Prozent
        functions = [0]
    elif loco == 135:
        speed_ratio = 40 # Angabe in Prozent
        functions = [0]
    elif loco == 312:
        speed_ratio = 25 # Angabe in Prozent
        functions= [4,5]
        direction = 0
    elif loco == 260:
        speed_ratio = 65 # Angabe in Prozent
        direction = 0
    elif loco == 8489:
        speed_ratio = 26 # Angabe in Prozent
        direction = 1
    elif loco == 8615:
        speed_ratio = 72 # Angabe in Prozent
        functions= [1]
        direction = 0
    elif loco == 8646:
        speed_ratio = 55 # Angabe in Prozent
        functions= [1]
        direction = 0

    s = ""
    for f in functions:
        s += f"[{f}] "
    print(s)
    max_speed = round((speed_ratio * speedsteps) / 100)
    if max_speed > 127:
        max_speed = 127
    speed = 0
        

##---------------------------------

# Funktion: Eingabe lesen
def kbd_in():
    return(sys.stdin.read(1) if spoll.poll(0) else None)

def show_cpu_freq(t):
    text(oled, font, 5, 45 if oled.height > 32 else 24, f"DCC-Strom: {op.get_current():>6} mA")
    if loco != None:
        text(oled, font, 5, 5, f"Lok: {loco} FS: {'->>' if direction == 1 else '<<-'}{speed}")
        s = ""
        for f in range(0, 13):
            s += '*' if op.get_function(f) else '.'
        text(oled, font, 0, 18, f"{s:^20}") 
        
##############################################################

# Tastatur-Eingabe
spoll = select.poll()
spoll.register(sys.stdin, select.POLLIN)

op = OP()
op.begin()
current_A = op.get_current()

# Weiche
turnout = 1
# Lok
loco = None

oled = start_display()

input_buffer = []
    
speed_ratio = 65
direction = 0
functions = []

time.sleep(1)
usage()

try:
    t = time.ticks_ms() + 60000
    timer_cpufreq = Timer()
    timer_cpufreq.init(mode=Timer.PERIODIC, freq=1, period=1000, callback=show_cpu_freq)

    # 1 Minute auf eine Lok warten
    while t > time.ticks_ms():
        I = op.get_current()
        if I < -1:
            print(f"Keine Lok erkannt ({I:>4} mA)", end="\r")
        else:
            break
     
    print(30 * " ")

    while True:
        if rp2.bootsel_button():
            finish()
            raise(RuntimeError("BootSel - Abbruch"))
        
        op.loop()
        if eventloop() == False:
            break
        
except KeyboardInterrupt:
    finish()
    raise(KeyboardInterrupt("Benutzer hat abgebrochen"))

finish()

