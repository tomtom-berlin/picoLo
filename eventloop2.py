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
# Steuerung mittels Digitaljoystick
# Joystick-Taste | Aktion                                        | Rp2040-Pin
# ---------------+-----------------------------------------------+-----------
# Up:            | Funktionsnr. +                                |   13
# Dn:            | Funktionsnr. -                                |   12
# Lft:           | Rückwärts beschleunigen oder vorwärts bremsen |   11
# Rht:           | Vorwärst beschleunigen oder rückwärts bremsen |   10
# Mid:           | sofort Fahrstufe 0                            |    9
# Set:           | Funktion lt. Nr. einschalten                  |    8
# Rst:           | Funktion lt. Nr. ausschalten                  |    7
# ---------------------------------------------------------------------------------------

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


PIN_UP = const(13)   # Funktion Nr +
PIN_DN = const(12)   # Funktion Nr
PIN_LFT = const(11)  # rückwärts, wenn bereits fährt: Fahrstufe + 15 %
PIN_RHT = const(10)  # vorwärts, wenn bereits fährt: Fahrstufe + 15 %
PIN_MID = const(9)   # Halt
PIN_SET = const(8)   # Funktion an
PIN_RST = const(7)   # Funktion aus
CTRL_PINS = [PIN_UP, PIN_DN, PIN_LFT, PIN_RHT, PIN_MID, PIN_SET, PIN_RST]
control_pins = []
command = -1
lok1 = None
fn = -1

alloc_emergency_exception_buf(100)

class BoundsException(Exception):
    pass

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
    
    global lok1
    global start_time
    global fn, speed
    global command
    
    fwd = 0
    speed = 0
    max_fs = 128
    

    if rp2.bootsel_button():
        print("BOOTSEL")
        return False
    
    def text(command):
        global speed, fwd, fn
        if command == 0:
            if 0 <= fn <= 12:
                return f"Fn = {fn}"
            
        elif command == 1:
            if 0 <= fn <= 12:
                return f"Fn = {fn}"
            
        if command == 2:
            if speed > 0:
                return f"<<-- {speed}"
            else:
                return "Halt"

        elif command == 3:
            if speed > 0:
                return f"-->> {speed}"
            else:
                return "Halt"

        elif command == 4:
            return "Halt"

        elif command == 5:
            return f"F{fn}"

        elif command == 6: 
            return f"f{fn}"
        
        else:
            return "n/a"


    if 0 <= command <= 6:

        fwd = lok1.current_speed["Dir"]
        speed = lok1.current_speed["FS"]
        max_fs = lok1.speedsteps
        if max_fs == 128:
            max_fs = 126
        current_speedstep_percent = speed * 100 // max_fs

        if command == 0:
            fn += 1
            if fn > 12:
                fn = 12
            
        elif command == 1:
            fn -= 1
            if fn < 0:
                fn = 0
            
        if command == 2:
            if fwd == 0:
                current_speedstep_percent += 33
                if current_speedstep_percent > 100:
                    current_speedstep_percent = 100
            else:
                current_speedstep_percent -= 33
                if current_speedstep_percent < 0:
                    fwd = 0
                    current_speedstep_percent = 0
            speed = current_speedstep_percent * max_fs // 100
            lok1.drive(fwd, speed)

        elif command == 3:
            if fwd == 1:
                current_speedstep_percent += 33
                if current_speedstep_percent > 100:
                    current_speedstep_percent = 100
            else:
                current_speedstep_percent -= 33
                if current_speedstep_percent < 0:
                    fwd = 1
                    current_speedstep_percent = 0
            speed = current_speedstep_percent * max_fs // 100
            lok1.drive(fwd, speed)

        elif command == 4:
            current_speedstep_percent = 0
            speed = current_speedstep_percent * max_fs // 100
            lok1.drive(fwd, speed)

        elif command == 5:
            lok1.function_on(fn)

        elif command == 6: 
            lok1.function_off(fn)

        textausgabe = text(command)
        if textausgabe != "n/a":
            t = time.ticks_diff(time.ticks_ms(), start_time) // 1000
            print(f"{t//3600:02d}:{(t//60)%60:02d}:{t%60:02d} - {textausgabe:<48s} [{electrical.get_actual_current():>3} mA]")
        
    command = -1
    return True


# ----------------------------------------------------------------------

def controller(pin):
    global command
    global control_pins
    command = control_pins.index(pin)

try:
    print("Anfang")
    start_time = time.ticks_ms()
    electrical = ELECTRICAL(POWER_PIN, PWM_PIN, BRAKE_PIN, DIR_PIN, ACK_PIN)
    if control_pins == []:
        for pin in CTRL_PINS:
            control_pins.append(Pin(pin, mode=Pin.IN, pull=Pin.PULL_UP))
        for pin in control_pins:
            pin.irq(trigger=Pin.IRQ_FALLING, handler=controller)

    lok1 = PACKETS(name="BR80 023", address=80, use_long_address=False, speedsteps = 128, electrical=electrical)
    for i in electrical.locos:
        print(f"Addr: {i.address} = Name: {i.name}, Speed: {i.current_speed}, Fn: [{i.functions[0]}, {i.functions[1]}, {i.functions[2]}]")
    electrical.power_on()
    if not electrical.loop(controller=locommander2):
        print(f"Short: {electrical.short}")
    
    electrical.power_off()
    print("Ende")
    
except KeyboardInterrupt:
    raise(TypeError("Benutzerabbruch, Reset"))
    reset()



