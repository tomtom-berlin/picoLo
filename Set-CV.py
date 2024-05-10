#
# "pico Lo" - Digitalsteuerung mit RPI pico
#
# (c) 2024 Thomas Borrmann
# Lizenz: GPLv3 (sh. https://www.gnu.org/licenses/gpl-3.0.html.en)
#
# Demo-Programm
# Dieses Programm ist gedacht für die Verwendung mit einem "Inglenook Siding" - also
# ein Rangierpuzzle.
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

PROG_NAME = const("Tom's picoLok")
PROG_VERSION = const("0.01& 2024-04-26")

ACK_TRESHOLD = const(7.5)  # mA

POWER_PIN = const(22)
BRAKE_PIN = const(20)
PWM_PIN = const(19)
DIR_PIN = const(21)
ACK_PIN = const(27)

BTN_PIN = const(6)
DEBOUNCE_TIME = const(20)


def wait_idle(milliseconds):
    global electrical
    t = utime.ticks_ms()
    while utime.ticks_ms() - t < milliseconds:
        electrical.idle()

def charge_supercap(timeout=5000):
    global oled
    global col
    global line
    global electrical
    x = 0
    bias = electrical.get_current()
    temp = bias
    oled.clear()
    oled.display_text(col, line - 12, "Lade Speicher")
    oled.display_text(col, line, f"Ladestrom: {bias:>5} mA")
    t = utime.ticks_ms() + timeout
    wait_idle(333)
    while utime.ticks_ms() < t:
        wait_idle(333)
        seconds = (t - utime.ticks_ms()) // 1000
        oled.display_text(col, line + 25, f"     noch ca. {seconds:>2} s")
        bias = electrical.get_current()
        oled.display_text(66, line, f"{bias:>5}")
        if temp > bias: # hat sich noch einmal verringert
            temp = bias
            t = utime.ticks_ms() + timeout
   
    oled.clear()
    oled.display_text(0, line, "Fertig")
    wait_idle(500)

def setloco(loco, long_address = False):
    if loco < 128:
        servicemode.set(1,loco % 128)
        wait_idle(300)
        servicemode.set(1,loco % 128)
    else:
        servicemode.set(1,loco % 100)
        wait_idle(300)
        servicemode.set(1,loco % 100)
    wait_idle(300)
    if long_address == True:
        print(f"Write CV 17 = {192 + (loco // 256)}, CV 18 = {loco & 0xff}, CV 29 = 34")
        servicemode.set(29, 34)
        wait_idle(300)
        servicemode.set(29, 34)
        wait_idle(300)
        servicemode.set(17, 192 + (loco // 256))
        wait_idle(300)
        servicemode.set(17, 192 + (loco // 256))
        wait_idle(300)
        servicemode.set(18, loco & 0xff)
        wait_idle(300)
        servicemode.set(18, loco & 0xff)
        wait_idle(300)
    else:
        if loco < 128:
            print(f"Write CV 1 = {loco}, CV 29 = 2")
            servicemode.set(29, 2)
            wait_idle(300)
            servicemode.set(29, 2)
            wait_idle(300)
            servicemode.set(17, 192)
            wait_idle(300)
            servicemode.set(17, 192)
            wait_idle(300)
            servicemode.set(18, 0)
            wait_idle(300)
            servicemode.set(18, 0)
            wait_idle(300)
        else:
            print(f"7-Bit-Adresse > 127 nicht erlaubt")


def set_function_cv(cv, value):
    print(f"Write Value {value} auf CV {cv}")
    servicemode.set(cv, value)

def set_loco_address(loco):
    if loco > 0:
        if loco < 128:
            setloco(loco, False)
        else:
            setloco(loco, True)

electrical = ELECTRICAL(POWER_PIN, PWM_PIN, BRAKE_PIN, DIR_PIN, ACK_PIN)
electrical.power_on()
electrical.emergency_stop()

oled = OLED128x64()
oled.splash_screen()
utime.sleep(3)
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
while utime.ticks_ms() - start_ticks < 1000:
    current = electrical.get_current()
    oled.display_text(66, line, f"{current:>5}")
    wait_idle(300)

#electrical.reset()
electrical.idle()
charge_supercap()
servicemode = SERVICEMODE(electrical, ACK_TRESHOLD, 3000)
servicemode.on()
wait_idle(300)

#servicemode.set(111,185)
#wait_idle(300)
# servicemode.set(1, 1)
# wait_idle(300)
# servicemode.set(29,2)
# wait_idle(300)
# servicemode.set(33,5)  # F0v
# wait_idle(300)
# servicemode.set(34,10) # F0r
# wait_idle(300)
# servicemode.set(35,0)  # F1v Lokommander, F1 NMRA
# wait_idle(300)
# servicemode.set(36,0)  # F1r Lokommander, F2 NMRA
# wait_idle(300)
# servicemode.set(37,0)  # F2 Lokommander, F3 NMRA
# wait_idle(300)
# servicemode.set(38,12) # F3 Lokommander, F4 NMRA
# wait_idle(300)
# servicemode.set(41,5)  # F6 Lokommander, F7 NMRA
# wait_idle(300)
# servicemode.set(42,5)  # F7 Lokommander, F8 NMRA
# wait_idle(300)
# servicemode.set(43,10) # F8 Lokommander, F9 NMRA
# wait_idle(300)
# servicemode.set(170,3) # F0v u. F0r gesperrt mit F3 Lokommander
# wait_idle(300)
# servicemode.set(48,16) # Dimmen A0v Lokommander
# wait_idle(300)
# servicemode.set(49,16) # Dimmen A0r Lokommander
# wait_idle(300)
# servicemode.set(50,16) # Dimmen A Lokommander
# wait_idle(300)
# servicemode.set(51,16) # Dimmen A2 Lokommander
# wait_idle(300)
# servicemode.set(61,97)
# wait_idle(300)
# servicemode.set(64,2) # Bremsweg  Lokommander
# wait_idle(300)
# servicemode.set(117,15) # Dimmen Ausgänge Lokommander
# wait_idle(300)
# servicemode.set(153,0) # Bremsweg vorw. Lokommander
# wait_idle(300)
# servicemode.set(161,0) # Bremsweg rückw. Lokommander
# wait_idle(300)

# servicemode.set(124,0)
# wait_idle(300)
# servicemode.set(155,3)
# wait_idle(300)
# servicemode.set(156,5)
# wait_idle(300)
# servicemode.set(146,50)
# wait_idle(300)
# # servicemode.set(54,100)
# # wait_idle(300)
# 
# servicemode.set(3, 2)
# wait_idle(300)
# servicemode.set(4, 5)
# wait_idle(300)
# servicemode.set(5, 150)
# wait_idle(300)
# servicemode.set(9, 0) # Lokommander mit Glockenankermotor
# wait_idle(300)
# servicemode.set(130, 1) # Lokommander mit Glockenankermotor
# wait_idle(300)
# servicemode.set(123, 188) # Lokommander mit E-Speicher n * 0.016 Sek. (128 = 2s, 188 = 3s, 255 = 4s)
# wait_idle(300)

# set_loco_address(260)
# set_loco_address(56)
# set_loco_address(92)
# set_loco_address(8615)
# set_loco_address(312)
# set_loco_address(80)
# set_loco_address(75)
# set_loco_address(20)

# BR118
# CV [   1,   2,   3,   4,   5,   7,   8,  17,  18,  29,  33,  34,  35,  36,  37,  38,  39,  40,  41,  42,  43,  44,  45,  46,  54]
# Val[ 118,   8,   8,   8, 150,  24, 117, 192, 118,  34,   1,   2,   4,   8,   3,  32,   8,  16,  32,   0,  72,  81,  90,  99,  70]

# #servicemode.manufacturer_reset()
#          AdrMinAccDecMaxVerManMot Ahi Alo Conf F0v  F0r  F1   F2   F3   F4   F5   F6   F7   F8   F9   F10 F11  F12  ]# Lenz LE010XF
#Map       Fvaus Fr  DimA0  A1  A2   A3   A4   A5   A6   A7  AV2   BV2 FABV Fade NEON:dauer anz. # Uhlenbrock
cv_nums = [1, 2, 3, 4, 5, 7, 8, 9, 17, 18, 29,  33,  34,  35,  36,  37,  38,  39,  40,  41,  42,  43,  44,  45,  46, 48, 49, 50, 51, 54, 61, 123, 124, 146, 155, 156 ] #,  96, 113, 114, 116, 117, 118, 119, 120, 121, 122, 123, 144, 145, 148, 186, 188, 189, 190]
#ist                1,   2,   4,   8, 224,  16,  64, 128,   5,  10,   0,   0,   0,   0,   0,   0,   0,  32,  63,  63, 200,  63,  63,  63,  63,   0                        0,   8
#cv_soll = [  1,   2,  12,   0,  96,  16,  0,    0,   5,  10,  12,   0,   0,   0,   0,   4,   8,  32,  32,  32,  32,  32,  63,   0,   0,   1,   1,   6,  31,  16,  20,  10]
#cv_soll = [   17,   34]#,   4,   4,   8,  48,   0,   0,   0,  25,  38,  12,   0,   0,   0,  25,   4,  16,   0,   0,  50,  50,  30,  66, 255,  15,  50,   0, 255, 255, 255, 255]

cvs = servicemode.get_cvs(cv_nums)
servicemode.off()

for i in range(len(cv_nums)):
    print(f"{chr(91) if i == 0 else ','}{cvs[i][0]:>4}", end="")
print("]")
for i in range(len(cv_nums)):
    print(f"{chr(91) if i == 0 else ','}{cvs[i][1]:>4}", end="")
print("]")

# for i in range(len(cv_nums)):
#      print(f"Setze CV{cv_nums[i]:<3} = {cv_soll[i]:>4} ... ", end="")
#      servicemode.set(cv_nums[i], cv_soll[i])
#      print(f"geprüft: {servicemode.get(cv_nums[i]) == cv_soll[i]}")

# cv38 = read(38)
# print(f"CV38: {cv38}")
# set_function_cv(39, cv38)
#loco_array = load_locomotives()
