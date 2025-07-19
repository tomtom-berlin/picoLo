# Fahrtest
#  Version 0.52ß 2025-07-16
#

from classes.operationmode import OPERATIONS as OP
from classes.servicemode import SERVICEMODE as SM
import time
import uselect as select
from machine import Timer, Pin, I2C, UART
from libraries.ssd1309 import Display as DISPLAY
from libraries.xglcd_font import XglcdFont as fm
import os, re
import sys
from tools.byte_print import int2bin

from micropython import const

TX = const(12)
RX = const(13)
SDA = const(4)
SCL = const(5)

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
address = None
use_long_address = False
functions = []
    
op = None
sm = None
uart = None
client_uart = False
client_kbd = False
########################
        

def finish():
    if not timer_cpufreq == None:
        timer_cpufreq.deinit()
    if not op == None:
        op.emergency_stop()
        op.power_off()
        op.end()
    if uart != None:
        uart.deinit()
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

# Abfrage, ob das eingegebne Zeichen eine Ziffer ist
def is_number(number):
    return number in ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9']

def pom_input():
    i = 1
    j = 0
    addr = 0
    cv = 0
    val = 0
    while i < len(input_buffer):
        c = input_buffer[i]
        if is_number(c):
            val = val * 10 + int(c)
        else:
            if c == '*' or c == ',':
                if j == 0:
                    addr = val
                    j += 1
                    val = 0
                elif j == 1:
                    cv = val
                    j += 1
                    val = 0

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

def value_of(input_buffer):
    value = 0
    for i in range(1, len(input_buffer)):
        c = input_buffer[i]
        if is_number(c):
            value = value * 10 + int(c)
        else:
            break
    return value

def text_of(input_buffer):
    t = input_buffer[1:len(input_buffer)]
    s = ""
    for c in t:
        s += c
    return s

def show_fn():
    for f in range(0, 13):
        print(f"{'F' if op.get_function(f) else 'f'}{f:<4}", end="")
    print()
    
def show_accessories():
    if (len(op.accessories) == 0):
        print("Kein Zubehör")
        return
    for i in range(len(op.accessories)):
        acc = op.accessories[i]
        print(f"{acc.address:<5}", end=", ")
        if(acc.signal):
            print(f"{int2bin(acc.aspect):^9}", end=", ")
        else:
            print(f"D={acc.D} R={acc.R}", end=", ")
        print(acc.name)

def show_locos():
    if (len(op.locos) == 0):
        print("Keine Triebfahrzeuge")
        return
    for i in range(len(op.locos)):
        loco = op.locos[i]
        print(f"Addr: {loco.address:>5} | ", end="")
        print(f"{loco.speedsteps:3} Fahrstufen | ", end="")
        print(f"FS {loco.current_speed["FS"]:>3} {'vorw.' if loco.current_speed["Dir"]==1 else 'rückw.':<6} | ", end="")
        print(loco.name)
        show_fn()
        print()
        
def get_loco():
    global loco, use_long_address, speedsteps
    clear_input_buffer()
    op.end()
    loco, use_long_address, speedsteps = get_loco_profile()
    set_loco_data(loco)
    print(f"Lok {loco}, {'Lange' if use_long_address else 'Kurze'} Adresse, {speedsteps} Fahrstufen")
    op.begin()
    op.ctrl_loco(loco, use_long_address, speedsteps)
    print(f"Lok {loco} bereit")
    
def process_input_buffer():
    global turnout, direction, max_speed, speed, loco, use_long_address, speedsteps
    cmd = None
    value = 0
#     print(input_buffer)
    if len(input_buffer) > 0:
        cmd = input_buffer[0]
        if  cmd == 'P' or cmd == 'p':
            pom_loco()
        elif cmd == 'A' or cmd == 'a':
            pom_acc()
        elif not (cmd == 'l' or cmd == 'L' or cmd == 'w' or cmd == 'W' or cmd == 't' or cmd == 'T') and loco == None:
            print("no loco")
            return True
        
        if cmd in ['e', 'E', 'q', 'Q', '+', '-', 'h', 'H']:
            if cmd == 'e' or cmd == 'E': # Nothalt alles
                print(f"Nothalt")
                op.emergency_stop()
                
            elif cmd == 'q' or cmd == 'Q': # Ende
                return False

            if cmd == 'H' or cmd == 'h': # Halt
                print(f"Lok {loco} Halt")
                speed = 0
                halt()
            
            elif cmd == '+':
                speed += input_buffer.count('+')
                if speed > max_speed:
                    speed = max_speed
                print(f"Lok {loco} Fahrstufe {speed}")
                drive(direction, speed)

            elif cmd == '-':
                speed -= input_buffer.count('-')
                if speed < 0:
                    speed = 0
                print(f"Lok {loco} Fahrstufe {speed}")
                drive(direction, speed)

            
        if cmd in ['V', 'v', 'R', 'r', 'f', 'F', 'l', 'L', 'd', 'D', 'w', 'W', 't', 'T', 's', 'S', 'n', 'N']:
            if cmd in ['f', 'F', 'w', 'W', 't', 'T', 'l', 'L', 'd', 'D', 'v', 'r', 's', 'S', 'n', 'N']:
                value = value_of(input_buffer)
                if cmd == 'l' or cmd == 'L':
                    if len(input_buffer) == 1:
                        get_loco()
                    else:
                        print(f"aktive Lokadresse: {value}")
                        loco = value
                        if loco != None:
                            op.ctrl_loco(loco, use_long_address, speedsteps)
                if cmd == 's' or cmd == 'S':
                        speedsteps = value
                        if loco != None:
                            print(f"{loco}: {speedsteps} Fahrstufen")
                            op.update_speedsteps(speedsteps)                            
                if cmd == 'n' or cmd == 'N':
                        name = text_of(input_buffer)
                        print(f"Adresse {loco}: {name}")
                        if loco != None:
                            op.update_name(name)
                            
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
                    if len(input_buffer) == 1:
                        show_accessories()
                    else:
                        print(f"Weiche {value} gerade")
                        op.ctrl_accessory_basic(value, 1, 0)
                    
                elif cmd == 'W':
                    if len(input_buffer) == 1:
                        show_accessories()
                    else:
                        print(f"Weiche {value} abzweigend")
                        op.ctrl_accessory_basic(value, 1, 1)
                    
                elif cmd == 't' or cmd == 'T':
                    if len(input_buffer) == 1:
                        show_accessories()
                    else:
                        i = op.search_accessory(value)
                        if i != None:
                            print(f"Weiche {value} umlegen")
                            r = op.accessories[i].R
                            r = 1 if r == 0 else 0
                            op.ctrl_accessory_basic(value, 1, r)

                elif cmd == 'r':  # Richtung rueckwaerts
                    if(direction == 1):
                        halt()
                        print("HALT", end=" ")
                        time.sleep(1.5)
                    if value != 0:
                        speed = value if speed <= max_speed else max_speed
                    print(f"Lok {loco} <<- Fahrstufe {speed}")
                    direction = 0
                    drive(direction, speed)
                    
                elif cmd == 'v':  # Richtung vorwaerts
                    if(direction == 0):
                        halt()
                        print("HALT", end=" ")
                        time.sleep(1.5)
                    if value != 0:
                        speed = value if speed <= max_speed else max_speed
                    print(f"Lok {loco} ->> Fahrstufe {speed}")
                    direction = 1
                    drive(direction, speed)

            elif cmd == 'R':  # Richtung rueckwaerts, Höchstgeschwindigkeit
                if(direction == 1):
                    halt()
                speed = max_speed
                direction = 0
                print(f"Lok {loco} HALT, <<- Fahrstufe {max_speed}")
                drive(direction, speed)
            elif cmd == 'V':  # Richtung vorwaerts, Höchstgeschwindigkeit
                if(direction == 0):
                    halt()
                speed = max_speed
                direction = 1
                print(f"Lok {loco} HALT, ->> Fahrstufe {max_speed}")
                drive(direction, speed)
        else:
            cmd = None
        return True
            
def clear_input_buffer():
    global input_buffer, client_uart
    input_buffer = []
    client_uart = False
    client_kbd = False

def usage():
    print("""
Benutzung:
Zeichen eingeben und mit Enter abschicken, Befehlstrenner = '#'

Zeichen| Führt aus
-------+---------------------------------------------------------------------
?      | Diese Hilfe
e      | Nothalt alle Fahrzeuge
       |
l      | Lok suchen
l{nnn} | Lok bedienen {nnn} = Dekoder-Adresse (sh.unten)
n{ccc} | Name setzen {ccc} = Name
s{nnn} | Fahrstufen setzen {nnn} = Fahrstufen (28/128)
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
    answer = True
    c = poll_cmd()
    if c != None:
        if c == '?':
            usage()
        elif c == '#' or c == '\n':
            answer = process_input_buffer()
            clear_input_buffer()
            
        else:
            input_buffer.append(c)
    return answer


def start_display():
    global font
    i2c = I2C(0, scl=Pin(SCL), sda=Pin(SDA), freq=400000)
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

def start_uart():
    uart = UART(0, baudrate=9600, tx=Pin(TX), rx=Pin(RX))
    return uart


def set_loco_data(loco):
    pass
        
##---------------------------------

# Funktion: Eingabe lesen
def poll_cmd():
    global client_uart, client_kbd
    if not client_kbd:
        if uart != None:
            if uart.any():
                client_uart = True
                return uart.read(1)
            
    if not client_uart:
        if spoll.poll(0):
            client_kbd = True
            return sys.stdin.read(1)
    return None

def show_cpu_freq(t):
    response(5, 45 if oled.height > 32 else 24, f"DCC-Strom: {op.get_current():>6} mA")
    if loco != None:
        response(5, 5, f"Lok:{loco:^5} FS:{'->>' if direction == 1 else '<<-':^3}{speed:^3}")
        s = ""
        if loco != None:
            for f in range(0, 13):
                s += '*' if op.get_function(f) else '.'
        else:
            s = "............."
        response(0, 18, f"{s:^20}") 
  
  
# Response if available
def uart_out(uart=None, string=""):
    if(uart != None):
        uart.write(string)         # write string

def response(col=0, line=0, s=""):
    text(oled, font, col, line, s) 
    uart_out(uart, s) 
    

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
speedsteps = 128
direction = 0
speed = 0
max_speed = 127
speed_ratio = 90
functions = []

oled = start_display()
uart = start_uart()

input_buffer = []
    
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
            print("Beginne")
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

