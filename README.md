# picoLok - Digitalsteuerung mit RPI pico
### Version 0.01& 2024-05-10
(c) 2024 Thomas Borrmann
Lizenz: GPLv3 (sh. https://www.gnu.org/licenses/gpl-3.0.html.en)
Programmiersprache: Micropython

Dieses Programm ist gedacht für die Verwendung mit einem "Inglenook Siding" - also
ein Rangierpuzzle - oder einem Diorama und automatischem Betrieb.

## Dieses Projekt verwendet die Libraries SSD1309 und XGLCD-Font von [Rototron](https://www.rototron.info/projects/wi-fi-caller-id-blocking/)

### Änderungen 2024-05-10: Fehlerbeseitigung, vertiefte Tests der DCC-Instruktionen

### Änderungen 2024-05-16:
- DCC-Signal wird kontinuierlich erzeugt
- Kurzschluss- und Überstromschutz
- der Servicemode funktioniert in dieser Version nicht

### Installation:
- alle Verzeichnisse z.B. mit rshell auf den RPi pico kopieren
- "thread_test.py" in Thonny ausführen oder
- thread_test.py auf den RPi pico kopieren
- main.py auf dem pico erstellen:
  import thread_test.py

### Verwendung:
```
# main.py
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
```


