from machine import Pin, Timer, ADC, reset
from classes.electrical import ELECTRICAL, PACKETS

import time
import rp2
import ujson
from micropython import const

POWER_PIN = const(22)
BRAKE_PIN = const(20)
PWM_PIN = const(19)
DIR_PIN = const(21)
ACK_PIN = const(27)

intr = -1
lok1 = None
lok2 = None
last_second = 0
last_intr = intr

def isr(timer):  # ISR kann auch via GPIO ausgelöst werden
    global intr
    if timer != cmd_timer:
        return
    intr += 1

def locommander():  # ISR kann auch via GPIO ausgelöst werden
    global intr
    global last_intr
    global last_second
    global lok1
    global lok2
    global start_time
    
    if rp2.bootsel_button():
        print("BOOTSEL")
        cmd_timer.deinit()
        return False

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
        if lok1 == None:
            lok1 = PACKETS(name="BR80 023", address=80, use_long_address=False, speedsteps = 128, electrical=electrical)

            for i in electrical.locos:
                print(f"Addr: {i.address} = Name: {i.name}, Speed: {i.current_speed}, Fn: [{i.functions[0]}, {i.functions[1]}, {i.functions[2]}]")
                
        electrical.power_on()
#        for i in range(13):

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
        for i in range(13):
            lok1.function_off(i)

    elif intr == 20:
        electrical.power_off()
        intr = -1

    else:
        pass

    last_second = time.ticks_ms()
    return True

# ------------------------Main Loop---------------

cmd_timer = Timer(period=2000, mode=Timer.PERIODIC, callback=isr)
try:
    print("Anfang")
    start_time = time.ticks_ms()
    last_second = start_time
    electrical = ELECTRICAL(POWER_PIN, PWM_PIN, BRAKE_PIN, DIR_PIN, ACK_PIN)
    if not electrical.loop(controller=locommander):
        print(f"Short: {electrical.short}")
    
    electrical.power_off()
    print("Ende")
    
except KeyboardInterrupt:
    raise(TypeError("Benutzerabbruch, Reset"))
    reset()

