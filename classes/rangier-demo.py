#
# "picoLok" - Digitalsteuerung mit RPI pico
#
# (c) 2024 Thomas Borrmann
# Lizenz: GPLv3 (sh. https://www.gnu.org/licenses/gpl-3.0.html.en)
#
# Demo-Programm
# Dieses Programm ist gedacht für die Verwendung mit einem "Inglenook Siding" - also
# ein Rangierpuzzle oder einem Diorama und automatischem Betrieb.
#
# ---------------------------------------------------------------------------------------
# mein Funktionsmapping:
# F0 - Spitzenlicht
# F1 - rotes Licht (Schiebelok)
# F3 - Rangiergang u. Rangierlicht
# F4 - Kabinenlicht
# F5 - Bremsen/Anfahren aus
# F6 - Rangiergeschwindigkeit aus
# F7 - Lok-Alleinfahrt vorwärts
# F8 - Lok-Alleinfahrt rückwärts
# F9 - Lok abgestellt (rot vorn und hinten)
# Wenn ein Decoder oder die Lok eine Funktion nicht bietet, wird diese nicht benutzt
# Funktionen F0, F1 und F3 sind obligatorisch (Spitzen- und Schlusssignal lt. Signalbuch)
# ---------------------------------------------------------------------------------------

from machine import Pin, Timer, ADC
from libraries.oled128x64 import OLED128x64
from classes.electrical import ELECTRICAL
from classes.servicemode import SERVICEMODE
from classes.menu import MENU
from classes.packets import PACKETS

import utime
import rp2
import ujson
from micropython import const

PROG_NAME = const("Tom's picoLo")
PROG_VERSION = const("0.01& 2024-04-26")

ACK_TRESHOLD = const(7.5)  # mA

POWER_PIN = const(22)
BRAKE_PIN = const(20)
PWM_PIN = const(19)
DIR_PIN = const(21)
ACK_PIN = const(27)

BTN_PIN = const(6)
DEBOUNCE_TIME = const(20)


def wait_nop(milliseconds):
    t = utime.ticks_ms()
    while utime.ticks_ms() - t < milliseconds:
        pass

def wait_idle(milliseconds):
    global electrical
    t = utime.ticks_ms()
    while utime.ticks_ms() - t < milliseconds:
        electrical.idle()

def charge_supercap(timeout=10000):
    global oled
    global col
    global line
    global electrical
    x = 0
    bias = electrical.get_current()
    temp = 0
    oled.clear()
    oled.display_text(col, line - 12, "Lade Speicher")
    oled.display_text(col, line, f"Ladestrom: {bias:>5} mA")
    time_remains = timeout
    t = utime.ticks_ms()
    while bias >= temp and utime.ticks_ms() - t < time_remains:
        seconds = (time_remains - utime.ticks_ms() + t) // 1000
        oled.display_text(col, line + 25, f"max. noch ca. {seconds:>2} s") 
        oled.display_text(66, line, f"{temp:>5}")
        temp = electrical.get_current()
        if temp < bias: # hat sich noch einmal verringert
            time_remains = timeout
        bias = temp
        wait_idle(1000)

    oled.clear()
    oled.display_text(col, round(1.5 * (oled.get_text_height() + 1)), "Bestimme ACK-Schwelle")
    oled.display_text(col, line, f"ACK-Schwelle: {bias+ACK_TRESHOLD:>4} mA")
    wait_idle(2000)
    oled.clear()
    oled.display_text(40, line, "Bereit")
    wait_idle(2000)
    return bias

def setloco(loco):
    print(f"Write CV 1 = {loco % 128}, 29 = 34, 17 = {192 + (loco // 256)}, 18 = {loco & 0xff}")
    servicemode.set(1,loco % 128)
    servicemode.set(1,loco % 128)
    servicemode.set(17, 192 + (loco // 256))
    servicemode.set(17, 192 + (loco // 256))
    servicemode.set(18, loco & 0xff)
    servicemode.set(18, loco & 0xff)
    servicemode.set(29, 34)
    servicemode.set(29, 34)

def set_function_cv(cv, value):
    print(f"Write Value {value} auf CV {cv}")
    servicemode.set(cv, value)

def setloco2(loco):
    print("Write CV 29, 1")
    servicemode.set(29, 2)
    servicemode.set(1, loco)

# --------------------------------------
# Zeigt eine Zeile mit dem Funktionsstatus
def display_functions(col, line):
    global oled
    # Headline
    for i in range(13):
        oled.display_text(col + i * 9, line - 18, f"{' ' if i < 10 else '1'}")
        oled.display_text(col + i * 9, line - 9, f"{'L' if i == 0 else i % 10}")
        oled.display_text(col + i * 9, line,  '*' if this_loco.get_function_state(i) else '-')
    

# ---------------------------------------------
# Lokomotivdaten ermitteln, Adresse zurückgeben
def get_loco_properties(servicemode):
    adr = None
    oled.clear()
    oled.display_text(col, 9, "   Ermittle")
    oled.display_text(col, 18, "Lokeigenschaften")

    wait_idle(2000)
    servicemode.verify_bit(8, 8, 0)
    servicemode.verify_bit(8, 8, 1)
    cv8 = servicemode.get(8)
    oled.display_text(col, 45, f"Decoder-Manuf.:{cv8:>3}")
    #print(f"CV8= {cv8}")
    cv29 = servicemode.get(29)
    #print(f"CV29 = {cv29:3}")
    oled.display_text(col, 45, f"Lange Adresse:{'Ja' if cv29 & (1 << 5) else 'Nein' :>4}")
    wait_idle(500)
    if cv29 & 0x20:
        cv17 = servicemode.get(17)
        print(f"CV17 = {cv17:3}")
        cv18 = servicemode.get(18)
        print(f"CV18 = {cv18:3}")
        adr = (cv17-192)*256 + cv18
        print(f"Lokadresse 14 Bit: {adr}")
        oled.display_text(col, 45, f"Adresse: {adr:>9}")
    else:
        cv1 = servicemode.get(1)
        print(f"CV1= {cv1}")
        adr = cv1
        print(f"Lokadresse 7 Bit:  {adr}")
        oled.display_text(col, 45, f"Adresse: {adr:>9}")

    return adr


# --------------------------------------

electrical = ELECTRICAL(POWER_PIN, PWM_PIN, BRAKE_PIN, DIR_PIN, ACK_PIN)
electrical.power_on()
electrical.emergency_stop()

oled = OLED128x64()
oled.splash_screen()
utime.sleep(10)
oled.clear()
oled.set_font()

line = 3 * (oled.get_text_height() + 1)
col = 0
print(f"Digitalspannung {'aus' if electrical.power_state == 0 else 'ein'}")
oled.clear()
oled.display_text(col, line, f"Digitalspannung {'aus' if electrical.power_state == 0 else 'ein'}")

oled.clear()

print(PROG_NAME)
print(PROG_VERSION)
oled.display_text(col, line, f"{PROG_NAME}")
oled.display_text(col, line + 10, f"{PROG_VERSION}")
wait_idle(2000)


oled.clear()
start_ticks = utime.ticks_ms()
current = electrical.get_current()
oled.display_text(col, line, f"Ruhestrom: {current:>5} mA")
while utime.ticks_ms() - start_ticks < 5000:
    current = electrical.get_current()
    oled.display_text(66, line, f"{current:>5}")
    wait_idle(300)

#electrical.reset()
electrical.idle()
bias = charge_supercap()
servicemode = SERVICEMODE(electrical, bias, ACK_TRESHOLD)

# #setloco(56)
# setloco(92)
# #setloco(8615)
# #setloco(312)
# #setloco2(118)
# #servicemode.manufacturer_reset()
# cv_nums = [9, 35, 36, 47, 60, 114, 115]
# cv_vals = [1,  8,  4,  0,  1,  16,  8]
# cvs = get_cvs(cv_nums)
# print(cvs)
# for i in range(len(cv_nums)):
#     write(cv_nums[i], cv_vals[i])
#     print(f"geprüft: CV{cv_nums[i]} == {cv_vals[i]}? => {read(cv_nums[i]) == cv_vals[i]}")

# cv38 = read(38)
# print(f"CV38: {cv38}")
# set_function_cv(39, cv38)
#loco_array = load_locomotives()

menu = MENU(oled, electrical, "data/meine_lokomotiven.json")

adr = get_loco_properties(servicemode)

#adr = None
if adr == None:
    menu.show()
    for i in ('+', '+', '+', '-', '-', '-', '-'):
        loco = menu.select(i)
        utime.sleep_ms(100)
    adr = loco.address
    print(f"manuell ausgewählt: {loco.name} @ {loco.address}")

this_loco = None
start = utime.ticks_ms()
print(f"gesucht: {adr}")
loco_array = menu.get_locos()
for i in range(0, len(loco_array)):
    print(f" {loco_array[i].name} ({loco_array[i].address})?")
    if menu.loco_array[i].address == adr:
        print(f" gefunden: {loco_array[i].address}")
        this_loco = menu.loco_array[i] 
        break

if this_loco != None: # gefunden

    print(f"aktuelle Lok: {this_loco.name}")
    line = 4
    oled.clear()
    oled.display_text(col, line, f"{this_loco.name}")
    line = round(2.5 * (oled.get_text_height() + 1))
    f_line = 55 # Zeile für die Funktionen


    speed = this_loco.max_speed
    for i in range(13):
        this_loco.set_function(i, True)
        display_functions(0, f_line)
        wait_idle(2500)
        this_loco.set_function(i, False)
        display_functions(0, f_line)

    wait_idle(1000)

    this_loco.set_function(7, True)
    display_functions(0, f_line)
    print(f"fahren vorw. {speed}")
    oled.display_text(col, line, f"Zugfahrt    -> {speed:>4}")

    this_loco.drive(1, speed)
    print("stop")
    oled.display_text(col, line, f"Zugfahrt       HALT")
    this_loco.drive(0, 0)
    wait_idle(1000)
    this_loco.set_function(4, True)
    this_loco.set_function(7, False)
    display_functions(0, f_line)

    wait_idle(1000)
    this_loco.set_function(8, True)
    this_loco.set_function(4, False)
#    this_loco.set_function(0, True)
    display_functions(0, f_line)

    print(f"fahren rückw. {speed}")
    oled.display_text(col, line, f"Zugfahrt    <- {speed:>4}")
    this_loco.drive(0, speed)
    wait_idle(1000)

    print("stop")
    oled.display_text(col, line, f"Zugfahrt       HALT")
    this_loco.drive(0, 0)
    this_loco.set_function(4, True)
    this_loco.set_function(8, False)
    display_functions(0, f_line)
    wait_idle(1000)

# Nachschieben
    this_loco.set_function(1, True)
    this_loco.set_function(4, False)
    display_functions(0, f_line)
    print(f"schieben vorw. {speed}")
    oled.display_text(col, line, f"Schieben    -> {speed:>4}")

    this_loco.drive(1, speed)
    print("stop")
    oled.display_text(col, line, f"Schieben       HALT")
    this_loco.drive(0, 0)
    wait_idle(1000)
    this_loco.set_function(4, True)
    display_functions(0, f_line)

    wait_idle(1000)
    this_loco.set_function(4, False)
    display_functions(0, f_line)
    print(f"schieben rückw. {speed}")
    oled.display_text(col, line, f"Schieben    <- {speed:>4}")
    this_loco.drive(0, speed)
    wait_idle(1000)

    print("stop")
    oled.display_text(col, line, f"Schieben       HALT")
    this_loco.drive(0, 0)
    this_loco.set_function(4, True)
    this_loco.set_function(1, False)
    display_functions(0, f_line)
    wait_idle(1000)

    # Rangiergang
    this_loco.set_function(3, True)
    this_loco.set_function(6, True)
    this_loco.set_function(4, False)
    display_functions(0, f_line)
    print(f"rangieren vorw. {speed}")
    oled.display_text(col, line, f"Rangiergang -> {speed:>4}")
    this_loco.drive(1, speed)
    print("stop")
    oled.display_text(col, line, f"               HALT")
    this_loco.drive(1, 0)

    wait_idle(1000)

    print(f"rangieren rückw. {speed}")
    oled.display_text(col, line, f"Rangiergang -> {speed:>4}")
    this_loco.drive(0, speed)
    wait_idle(1000)
    print("stop")
    oled.display_text(col, line, f"               HALT")
    this_loco.drive(0, 0)

    this_loco.set_function(4, True)
    wait_idle(1000)
    this_loco.set_function(3, False)
    wait_idle(500)
    this_loco.set_function(9, True)
    this_loco.set_function(3, False)
    this_loco.set_function(6, False)
    wait_idle(1500)
    this_loco.set_function(4, False)
    display_functions(0, f_line)
    wait_idle(3500)

    
oled.clear()
oled.display_text(49, line, "Fertig")
flv = 1
flr = 2
aux1 = 4
aux2 = 8
aux3 = 16
aux4 = 32

# for i in [flv + aux3, flr + aux4, aux2 + flv + aux3, flr + aux1 + aux4]:
#     write(47, i)
#     wait_idle(200)
#     print(f"geprüft: CV{47} == {i}? => {read(47) == i}")
#     this_loco.set_function(12, True)
#     wait_idle(4000)
#     this_loco.set_function(12, False)
    
#
#          F0vF0r  F1vF1r  F2  F3  F4  F5  F6  F7  F8  F9  F10F11 F12  PWMPWM PWM PWM PWM PWM MOT SUS SPP
#cv_nums = [33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 60,122,123]
#cv_vals = [17, 34,  8,  4,  0, 48,  0,  0,  0, 25, 38, 12,  0,  0,  0,225,225,255,255,255,255,129,  0,255]
# cv_nums = [9, 35, 36, 47, 114, 115]
# cv_vals = [5,  8,  4,  0,  16,  32]
# cvs = get_cvs(cv_nums)
# print(cvs)
# for i in range(len(cv_nums)):
#     write(cv_nums[i], cv_vals[i])
#     print(f"geprüft: CV{cv_nums[i]} == {cv_vals[i]}? => {read(cv_nums[i]) == cv_vals[i]}")
# richtung = 1
# for i in [0, 0, 1, 2, 3, 7, 8, 9]:
#     display_functions(i, f_line)
#     if i < 2:
#         this_loco.drive(richtung, 5)
#         richtung = richtung ^ 1 ^ 0
#     this_loco.set_function(i, True)
#     print(f"Funktion {i}{'vorwärts' if i == 0 and richtung == 1 else 'rückwärts' if richtung == 0 and i == 0 else ''}")
#     wait_idle(200)
#     this_loco.drive(richtung, 0)
#     wait_idle(2000)
#     this_loco.set_function(i, False)
# 
# 

electrical.power_off()
print(f"Digitalspannung {'aus' if electrical.power_state == 0 else 'ein'}")
oled.clear()
oled.display_text(col, line, f"Digitalspannung {'aus' if electrical.power_state == 0 else 'ein'}")
