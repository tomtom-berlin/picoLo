#
# "picoLok" - Digitalsteuerung mit RPI pico
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
#
# Timergesteuerter Ablauf im 2-Sekunden-Takt:
# -  0: init, F3 (Rangierfahrt) an
# -  1: Rangierfahrt vorwärts, FS = 95
# -  8: Rangierfahrt bremsen, FS = 55
# -  9: Halt
# - 10: Rangierfahrt rückwärts, FS = 95
# - 17: Rangierfahrt bremsen, FS = 55
# - 18: Halt
# - 19: F3 aus
# ... und wieder von vorne
# ---------------------------------------------------------------------------------------

from machine import Pin, Timer, ADC
from libraries.oled128x64 import OLED128x64
from classes.electrical import ELECTRICAL, PACKETS
from classes.servicemode import SERVICEMODE
from classes.menu import MENU

import utime
import rp2
import ujson
from micropython import const

PROG_NAME = const("Tom's picoLok")
PROG_VERSION = const("0.03& 2024-05-17")

from machine import Pin, Timer, ADC, reset
from classes.electrical import ELECTRICAL, PACKETS

import time
import rp2
import ujson
from micropython import const, alloc_emergency_exception_buf

POWER_PIN = const(22)
BRAKE_PIN = const(20)
PWM_PIN = const(19)
DIR_PIN = const(21)
ACK_PIN = const(27)

lok1 = None
last_second = 0
intr = -1
last_intr = intr

cmd_timer = False
fn = -1

alloc_emergency_exception_buf(100)

class BoundsException(Exception):
    pass

def isr(timer):  # ISR kann auch via GPIO ausgelöst werden
    global intr
    if timer != cmd_timer:
        return
    intr += 1

def locommander():  # ISR kann auch via GPIO ausgelöst werden

# definiert die auszuführenden Aktionen abhängig von intr, Pin oder anderen Ereignissen, z. B.:
# fn = 3
# if intr == 0:
#         if lok1 == None:
#             lok1 = PACKETS(name="BR80 023", address=80, use_long_address=False, speedsteps = 128, electrical=electrical)
#             for i in electrical.locos:
#                 print(f"Addr: {i.address} = Name: {i.name}, Speed: {i.current_speed}, Fn: [{i.functions[0]}, {i.functions[1]}, {i.functions[2]}]")
#                 
#         electrical.power_on()
#         lok1.function_on(fn)
#         
#     if intr == 1:
#         lok1.drive(1, 95)
#     ...
    
    global intr
    global cmd_timer
    global last_intr
    global last_second
    global lok1
    global start_time
    
    if cmd_timer == False:
        cmd_timer = Timer(period=2000, mode=Timer.PERIODIC, callback=isr)
    
    if rp2.bootsel_button():
        print("BOOTSEL")
        cmd_timer.deinit()
        return False

    if intr > 19:
        intr = 0
        
    if last_intr == intr:
        return True

    last_intr = intr

    def text(intr):
        if intr == 0:
            return "Rangierlicht an"

        if intr == 1:
            return "Rangieren 95 <<--"

        elif intr == 8:
            return "Rangieren  55 <<--"
            
        elif intr == 9:
            return "Halt"

        elif intr == 10:
            return "Rangieren 95 -->>"

        elif intr == 17: 
            return "Rangieren  55 -->>"
            
        elif intr == 18:
            return "Halt"

        elif intr == 19:
            return "Licht aus"

        else:
            return "n/a"

    textausgabe = text(intr)
    
    fn = 3
    
    if textausgabe != "n/a":
        t = time.ticks_diff(time.ticks_ms(), start_time) // 1000
        print(f"{t//3600:02d}:{(t//60)%60:02d}:{t%60:02d} - {textausgabe:<48s} [{electrical.get_actual_current():>3} mA]")

    if intr == 0:
        lok1.function_on(fn)
        
    if intr == 1:
        lok1.drive(1, 95)

    elif intr == 8:
        lok1.drive(1, 55)
        
    elif intr == 9:
        lok1.drive(1, 0)

    elif intr == 10:
        lok1.drive(0, 95)

    elif intr == 17: 
        lok1.drive(0, 55)
        
    elif intr == 18:
        lok1.drive(0, 0)
 
    elif intr == 19:
        lok1.function_off(fn)

    else:
        pass

    last_second = time.ticks_ms()
    return True

# ----------------------------------------------------------------------

try:
    print("Anfang")
    start_time = time.ticks_ms()
    last_second = start_time
    electrical = ELECTRICAL(POWER_PIN, PWM_PIN, BRAKE_PIN, DIR_PIN, ACK_PIN)
    lok1 = PACKETS(name="BR80 023", address=80, use_long_address=False, speedsteps = 128, electrical=electrical)
    for i in electrical.locos:
        print(f"Addr: {i.address} = Name: {i.name}, Speed: {i.current_speed}, Fn: [{i.functions[0]}, {i.functions[1]}, {i.functions[2]}]")
    electrical.power_on()
    if not electrical.loop(controller=locommander):
        print(f"Short: {electrical.short}")
    
    electrical.power_off()
    print("Ende")
    
except KeyboardInterrupt:
    raise(TypeError("Benutzerabbruch, Reset"))
    reset()



