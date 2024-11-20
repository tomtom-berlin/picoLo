#
# "pico Lo" - Digitalsteuerung mit RPI pico
#
# (c) 2024 Thomas Borrmann
# Lizenz: GPLv3 (sh. https://www.gnu.org/licenses/gpl-3.0.html.en)
#
# Funktionen für den Bereich "ELECTRICAL" der NMRA DCC RP 9.2
#
# ----------------------------------------------------------------------
#
# NMRA-DCC Instructions
#
#                        11AAAAAA 0 AAAAAAAA               lange Adresse
#              berechnen:  [Adresse // 256 | 0xc0)] [Adresse & 0xff]
#   {instruction-bytes} = CCCDDDDD
#                         CCCDDDDD 0 DDDDDDDD
#                         CCCDDDDD 0 DDDDDDDD 0 DDDDDDDD
#
#   CCCDDDDD = CCCGGGGG or CCCGTTTT
#
#   CCC = 000: Decoder and Consist Control Instruction
#              Decoder Control (GTTTT=0TTTF):
#                   {instruction byte} = 0000TTTF
#                   {instruction byte} = 0000TTTF 0 DDDDDDDD
#
#              TTT = 101 Set Advanced Addressing (CV#29 bit 5==F)
#                    {instruction byte} = 00001011: Lange Adresse benutzen
#                                         00001010: kurze Adresse benutzen 
#
#                    111 Ack anfordern
#                    {instruction byte} = 00001111
#
#  @TODO
#              Consist Control (GTTTT=1TTTT)
#                    {instruction bytes} = 0001TTTT 0 0AAAAAAA
#  /@TODO
#
#         001: Advanced Operation Instructions 001GGGGG
#                    {instruction bytes} = 001GGGGG 0 DDDDDDDD
#                    GGGGG = 11111: 128 Speed Step Control
#                            DDDDDDDD = DSSSSSSS
#
#                            D=1: vorwärts,
#                            D=0: rückwärts
#                            SSSSSSS = 0:        Stop
#                                      1:        Notstop
#                                      2 .. 127: Fahrstufe 1..126
#
#         010: Speed and Direction Instruction for reverse operation
#         011: Speed and Direction Instruction for forward operation
#
#         01DCSSSS wie RP 9.2 - Fahren (sh. "CSSSS berechnen" unter "Baseline instructions")
#           D = 0: rueckwaerts, D=1: vorwaerts
#            CSSSS: Fahrstufen = 0: Stop, 1-28: ((Fahrstufe + 3 & 0x01) << 4) | ((Fahrstufe + 3) << 1)
#
#         100: Function Group One Instruction
#
#         100DDDDD Funktionen Gruppe 0 u. FL
#            DDDDD: 10000 FL, 01000 F4 ... 00001 F1
#
# ----------------------------------------------------------------------
# 
#  Version 0.5ß 2024-06-05
#
import machine
from classes.bitgenerator import BITGENERATOR as bitgenerator
from micropython import const
import utime

DEBUG = False
#DEBUG = True

# --------------------------------------
# Long-preamble 0 0111CCAA 0 AAAAAAAA 0 DDDDDDDD 0 EEEEEEEE 1
# CC=10 Bit Manipulation
# CC=01 Verify byte
# CC=11 Write byte
# CC=10: DDDDDDDD = 111KDBBB mit K=0: Read, K=1: Write, D=0|1 (Datenbit), BBB = Bit 0..7
                               
                               
class ELECTRICAL_SM:
    # hier Verbindungen einstellen
    DIR_PIN = const(19)
    BRAKE_PIN = const(20)
    PWM_PIN = const(21)
    POWER_PIN = const(22)
    ACK_PIN = const(27)

    LMD18200_QUIESCENT_CURRENT = const(17.0)
    LMD18200_SENS_SHUNT = const(20000)                # Ohm
    AREF_VOLT = const(3300)                           # mV !!
    DENOISE_SAMPLES = const(200)                      # Anzahl der Messzyklen, für Rauschunterdrückung
    LMD18200_SENS_AMPERE_PER_AMPERE = const(0.000377) # Empfindlichkeit: 377µA / A lt. Datenblatt
    SHORT = const(1000)                               # erlaubter max. Strom in mA
    SM_SHORT = const(250)                             # im Servicemode Power-On-Cycle für die zul. Dauer erlaubter max. Strom (mA)
    SM_SHORT_MS = const(100)                          # zul. Dauer des erhöhten Stromes
    PREAMBLE = const(14)                              # Standard Präambel für DCC-Instruktionen
    LONG_PREAMBLE = const(24)                         # Präambel f. Servicemode
    ACK_TRESHOLD = const(40)                          # Hub f. Ack
    CURRENT_SMOOTHING = const(0.175)                  # Glättung der Messergebnisse versuchen
    
    # preamble 0 11111111 0 00000000 0 11111111 1
    IDLE =      [ const(0b11111111111111111111111111111111), const(0b11110111111110000000000111111111) ]
    # preamble 0 00000000 0 00000000 0 00000000 1
    RESET =     [ const(0b11111111111111111111111111111111), const(0b11110000000000000000000000000001) ]
    EMERG =     [ const(0b11111111111111111111111111111111), const(0b11110000000000010000010010000011) ]
    # long-preamble 0 01111111 0 00001000 0 01110111 1
    HARDRESET = [ const(0b11111111111111111111111111111111), const(0b11110011111110000010000011101111) ]
    
    # DCC- und H-Bridge-LMD18200T-Modul elektrische Steuerung
    def __init__(self):   
        self.brake = machine.Pin(self.BRAKE_PIN, machine.Pin.OUT)
        self.pwm = machine.Pin(self.PWM_PIN, machine.Pin.OUT)
        self.power = machine.Pin(self.POWER_PIN, machine.Pin.OUT)
        self.dir_pin = machine.Pin(self.DIR_PIN, machine.Pin.OUT)
        self.analog_in = machine.ADC(machine.Pin(self.ACK_PIN))
        self.power_state = self.power.value()
        self.ack_committed = False
        self.buffer_dirty = False

        self.servicemode_instruction = {"valid": False, "write": False, "cv": 8, "bit":7, "value": 0} # dict
                # Grundstellung: Bit 7 von CV8 auf "0" testen, valid: False - Instruction is invalid
        self.hardreset = False
        self.power_on_cycle = 20
        
        self.statemachine = bitgenerator(self.dir_pin)
        self.statemachine.begin()

        self.messtimer = utime.ticks_ms()
        
    # LMD18200T
    # Logiktabelle:
    # PWM | Dir | Brake | Output
    # ----+-----+-------+-------
    #  H  |  H  |   L   | A1, B2 -> A = VCC, B = GND
    #  H  |  L  |   L   | A2, B1 -> A = GND, B = VCC
    #  L  |  X  |   L   | A1, B1 -> Brake (Motor kurzgeschlossen über VCC
    #  H  |  H  |   H   | A1, B1 -> Brake (Motor kurzgeschlossen über VCC
    #  H  |  L  |   H   | A2, B2 -> Brake (Motor kurzgeschlossen über GND
    #  L  |  X  |   H   | None   -> Power off
    def power_off(self):
        self.brake.value(1)  
        self.pwm.value(0)
        self.statemachine.end()
        self.power.value(False)
        self.power_state = False


    def power_on(self):
        self.pwm.value(1)
        self.power_time = utime.ticks_ms()
        self.brake.value(0)  
        self.power.value(True)
        self.power_state = True
        self.chk_short()

    def raw2mA(self, analog_value):
        analog_value = analog_value * self.AREF_VOLT / 65535  # ADC mappt auf 0..65535
        analog_value /= self.LMD18200_SENS_SHUNT  # Rsense
        return (analog_value / self.LMD18200_SENS_AMPERE_PER_AMPERE) - self.LMD18200_QUIESCENT_CURRENT  # lt. Datenblatt 377 µA / A +/- 10 %

    def get_current(self):
        analog_value = 0
        max_value = 0
        for i in range(0, self.DENOISE_SAMPLES):
            analog_value = (self.analog_in.read_u16() - analog_value) * self.CURRENT_SMOOTHING + analog_value * (1 - self.CURRENT_SMOOTHING)
            max_value = max(analog_value, max_value)
        return round(self.raw2mA(max_value))
    
    def chk_short(self):
        if self.get_current() > self.SHORT: # Kurzschluss (ggf. im Servicemode
            raise(RuntimeError("!!! KURZSCHLUSS !!!"))

    def chk_sm_short(self, end_time):  #end_time = start + 100ms
        if end_time < utime.ticks_ms() and self.get_current() > self.SM_SHORT: # Kurzschluss (ggf. im Servicemode
            raise(RuntimeError("!!! ZU HOHER STROM IM SERVICEMODE !!!"))

    def chk_ack(self, quiescent_current):
        I_load = self.get_current()
        if DEBUG:
            print(f"Laststrom {I_load} mA, Ruhestrom: {quiescent_current} mA, Diff: {I_load - quiescent_current} mA, Schwelle: {self.ACK_TRESHOLD} mA, ACK: {I_load - quiescent_current >= self.ACK_TRESHOLD} ")
        return I_load - quiescent_current >= self.ACK_TRESHOLD
        
   
    def to_bin(self, num):
        stream = 0
        for j in range(0, 8):
            if num & 1 << (7 - j):
                stream |= 1
            stream <<= 1
        return (stream >> 1) & 0xff 
        
    def prepare(self, packet=[]):  # Daten in den Puffer stellen
        stream = 0
        bits = 0
        padding = 0
        if 2 <= len(packet) <= 5:  # Anzahl Bytes ohne XOR
            # Streamlänge = jedem Byte ein 0 voran, das XOR-byte + 1 ans Ende + Preamble + Padding auf Wortgrenze (32 Bit)
            err = 0;
            for byte in packet:
                err ^= byte
            packet.append(err)
            preamble = self.LONG_PREAMBLE
            bits = preamble + len(packet) * 9 + 1
            padding = 32 - (bits % 32) # links mit 1 erweitern bis Wortgrenze
            for i in range(0, padding + preamble):
                stream <<= 1
                stream |= 1
            for i in packet:
                stream <<= 9
                stream |= self.to_bin(i)
            stream <<= 1
            stream |= 1
        return (padding + bits) // 32, stream  # Anzahl der Worte + Bitstream
            
                    
    # Long-preamble 0 0111CCAA 0 AAAAAAAA 0 DDDDDDDD 0 EEEEEEEE 1
    # CC=10 Bit Manipulation
    # CC=01 Verify byte
    # CC=11 Write byte
    # CC=10: DDDDDDDD = 111KDBBB mit K=0: Read, K=1: Write, D=0|1 (Datenbit), BBB = Bit 0..7
    def generate_servicemode_instructions(self):  # Schreiben oder Prüfen, CV 1..1024, value=0..255, bit=0..7        
        words  = []
        lengths = []
        
        if self.servicemode_instruction["valid"] == True:
            
            byte0 = 0b01110000 | self.servicemode_instruction["cv"] >> 8 & 0x03  # Address pt. 1
            byte1 = self.servicemode_instruction["cv"] & 0xff       # Address pt. 2
            if self.servicemode_instruction["bit"] == -1:
                byte0 |= 0b00000100
                if self.servicemode_instruction["write"] == True:
                    byte0 |= 0b00001000
                byte2 = self.servicemode_instruction["value"]
            else:
                byte0 |= 0b00001000  # Bit manipulation
                byte2 = 0b11100000
                if self.servicemode_instruction["write"] == True:
                    byte2 |= 0b10000
                if self.servicemode_instruction["value"] > 0:
                    byte2 |= 0b1000
                byte2 |= self.servicemode_instruction["bit"]

            l, w = self.prepare([byte0, byte1, byte2])
            self.servicemode_instruction["valid"] = False
            words.append(w)
            lengths.append(l)

        return lengths, words
        

    def set_servicemode_instruction(self, cv=0, value=0, bit=-1, write=0):  # Schreiben oder Prüfen, CV 1..1024, value=0..255, bit=0..7
        instruction = {}
        if 0 < cv <=1024:
            instruction["cv"] = cv - 1
        else:
            raise(ValueError("Error #1: Fehler CV #"))
        
        if 0 <= bit <= 7:
            instruction["bit"] = bit
            if value:
                instruction["value"] = 1
            else:
                instruction["value"] = 0  # nur 0 oder 1 erlaubt
        
        elif bit > 7:
            raise(ValueError("Error #3: Fehler Bit #"))
        else:
            instruction["bit"] = -1

            if 0 <= value <= 255:
                instruction["value"] = value
            else:
                raise(ValueError("Error #2: Fehler CV Wert"))
            
        if write > 0:
            instruction["write"] = True
        else:
            instruction["write"] = False
            
        instruction["valid"] = True
        
        self.servicemode_instruction = instruction
        self.buffer_dirty = True
        return 0
            
                
    def buffering(self):
        buffer = []
        if self.hardreset == True:
            for i in range(5):
                for h in self.HARDRESET:
                    buffer.append(h)
            self.hardreset = False
            
        else:
            l, w = self.generate_servicemode_instructions()
            for i in range(len(l)):
                while l[i] > 0:
                    l[i] -= 1
                    buffer.append(w[i] >> l[i] * 32 & 0xffffffff)

            if buffer == []:
                buffer = self.RESET

        return buffer
    
    def send2track(self):
        buffer = []
        try:
            if self.power_state == True:
                if (utime.ticks_ms() - self.messtimer > 100):
                    self.chk_short()
                    self.messtimer = utime.ticks_ms()
     
                if self.buffer_dirty:
                    quiescent_current = self.get_current()   # ermittle Ruhestrom
                    buffer = self.buffering()
                    if self.power_on_cycle > 0:
                        end_time = utime.ticks_ms() + 100
                        while self.power_on_cycle > 0:
                            self.chk_sm_short(end_time)
                            for word in self.IDLE:
                                self.statemachine.put(word)
                            self.power_on_cycle -= 1

                        self.ack_committed = False

                    if not DEBUG:
                        state = machine.disable_irq()

                    for i in range(5):  #Start min. 3x Reset
                        for word in self.RESET:
                            self.statemachine.put(word)
                    for i in range(6):  # 5+ x verify or write command
                        if DEBUG:
                            print("Service Mode Track signal:", i, end=": ")
                        for word in buffer:
                            if DEBUG:
                                print("["+bin(word)+"]", end=" ")
                            self.statemachine.put(word)
                        if i > 2:
                            self.ack_committed |= self.chk_ack(quiescent_current)
                            if self.ack_committed:
                                while self.chk_ack(quiescent_current):
                                    pass
                                break
                        if DEBUG:
                            print()
                            print(f"{'No ' if not self.ack_committed else '   '} ACK")

                    if self.servicemode_instruction["write"] == True:
                        for i in range(7):  # 6+ x identical write command (Recovery)
                            for word in buffer:
                                self.statemachine.put(word)
                        
                    for i in range(3):
                        for word in self.RESET: # 1 x RESET
                            self.statemachine.put(word)
                        
                    
                    if not DEBUG:
                        machine.enable_irq(state)

                    self.buffer_dirty = False
                        
                else:
                    for word in self.IDLE:
                        self.statemachine.put(word)
                    
        except KeyboardInterrupt:
            raise(KeyboardInterrupt("SIGINT"))

# --------------------------------------------

class SERVICEMODE(ELECTRICAL_SM):

    REPETITIONS = const(15)

    def __init__(self):
        super().__init__()
        
    def end(self):
        if self.power_state == True:
            self.power_off()
        utime.sleep_ms(100)
        self = None
    
    def begin(self):
        self.power_on()
        self.chk_short()
        utime.sleep_ms(100)
        self.power_on_cycle = 20
    
    def loop(self):
        if self.power_state == False:
            raise(RuntimeError("Power is off"))
        self.send2track()    # scheduler: Funktion liefert die DCC-Instruktionen an das Gleis
    
    def ack(self):
        ack = self.ack_committed
        self.ack_committed = False
        return ack
    
    def manufacturer_reset():
        self.write(8,0)

    def verify_bit(self, cv=1, bit=-1, value=0):
        # {Long-preamble} 0 011110AA 0 AAAAAAAA 0 111KDBBB 0 EEEEEEEE 1
        self.set_servicemode_instruction(cv, value, bit)

    def verify(self, cv=1, value=3):
        # {Long-preamble} 0 011101AA 0 AAAAAAAA 0 DDDDDDDD 0 EEEEEEEE 1
        self.set_servicemode_instruction(cv, value)

    def write(self, cv=1, value=3):
        # {Long-preamble} 0 011111AA 0 AAAAAAAA 0 DDDDDDDD 0 EEEEEEEE 1
        self.set_servicemode_instruction(cv=cv, value=value, write=True)
            
            
# --------------------------------------

