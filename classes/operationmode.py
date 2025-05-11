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
# ----------------- ACCESSORIES --------------------
# erzeugen von DCC-Signal für Zubehördekoder
# Basic format:
#         {preamble} 0 10AAAAAA 0 1AADAAR 0 EEEEEEEE 1
#         {preamble} 0 [10 A7 A6 A5 A4 A3 A2] 0 [1 ~A10 ~A9 ~A8 D A1 A0 R] 0 EEEEEEEE 1
#
# Extended format:
#         {preamble} 0 10AAAAAA 0 0AAA0AA1 0 XXXXXXXX 0 EEEEEEEE 1
#         {preamble} 0 [10 A7 A6 A5 A4 A3 A2] 0 [0 ~A10 ~A9 ~A8 0 A1 A0 1] 0 [XXXXXXXX] 0 EEEEEEEE 1
# XXXXXXXX: 00000000 : Absolutes Halt, 000xxxxx all other aspects
#           RZZZZZZZ : R = which output of a pair on the same address with ZZZZZZZ as active time in ms
#           R1111111 : always on (continuously) or R0000000: always of
#
# ----------------------------------------------------------------------
#  Version 0.8ß 2024-09-30
#
import machine
from classes.bitgenerator import BITGENERATOR as bitgenerator
from micropython import const
import utime


DEBUG = False
#DEBUG = True
motordriver = "LM18200D"  # oder "DRV8871"

class ELECTRICAL:
    
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
    PREAMBLE = const(14)                              # Präambel f. Servicemode
    ACK_TRESHOLD = const(40)                          # Hub f. Ack
    CURRENT_SMOOTHING = const(0.175)                  # Glättung der Messergebnisse versuchen
    
    # preamble 0 11111111 0 00000000 0 11111111 1
    IDLE =      [ const(0b11111111111111111111111111111111), const(0b11110111111110000000000111111111) ]
    # preamble 0 00000000 0 00000000 0 00000000 1
    EMERG =     [ const(0b11111111111111111111111111111111), const(0b11110000000000010000010010000011) ]
    # long-preamble 0 01111111 0 00001000 0 01110111 1
    
    locos = []
    devices = []
    
    # DCC- und H-Bridge-LMD18200T-Modul elektrische Steuerung
    #
#    @classmethod
    def __init__(cls):   
        cls.brake = machine.Pin(BRAKE_PIN, machine.Pin.OUT)
        cls.pwm = machine.Pin(PWM_PIN, machine.Pin.OUT)
        cls.power = machine.Pin(POWER_PIN, machine.Pin.OUT)
        cls.dir_pin = machine.Pin(DIR_PIN, machine.Pin.OUT)
        cls.ack = machine.ADC(machine.Pin(ACK_PIN))
        cls.power_state = cls.power.value()
        cls.buffer_dirty = False
        cls.emergency = False
        cls.ringbuffer = []
        cls.accessory_buffer = [] # Accessory-Commands
        cls.locos = []
        
        cls.statemachine = bitgenerator(cls.dir_pin)
        cls.statemachine.begin()

        cls.messtimer = utime.ticks_ms()
        
         
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
    #
    @classmethod
    def power_off(cls):
        cls.brake.value(1)  
        cls.pwm.value(0)
        cls.statemachine.end()
        cls.power.value(False)
        cls.power_state = False
        cls.emergency = False

    #
    @classmethod
    def power_on(cls):
        cls.brake.value(0)  
        cls.pwm.value(1)
        cls.power_time = utime.ticks_ms()
        cls.power.value(True)
        cls.power_state = True
        cls.chk_short()

    #
    @classmethod
    def raw2mA(cls, analog_value):
        analog_value = analog_value * cls.AREF_VOLT / 65535  # ADC mappt auf 0..65535
        analog_value /= cls.LMD18200_SENS_SHUNT  # Rsense
        return (analog_value / cls.LMD18200_SENS_AMPERE_PER_AMPERE) - cls.LMD18200_QUIESCENT_CURRENT  # lt. Datenblatt 377 µA / A +/- 10 %

    #
    @classmethod
    def get_current(cls):
        analog_value = 0
        max_value = 0
        for i in range(0, cls.DENOISE_SAMPLES):
            analog_value = (cls.ack.read_u16() - analog_value) * cls.CURRENT_SMOOTHING + analog_value * (1 - cls.CURRENT_SMOOTHING)
            max_value = max(analog_value, max_value)
        return round(cls.raw2mA(max_value))
    
    #
    @classmethod
    def chk_short(cls):
        if cls.get_current() > cls.SHORT: # Kurzschluss (ggf. im Servicemode
            raise(RuntimeError("!!! KURZSCHLUSS !!!"))

    #
    @classmethod
    def emergency_stop(cls):
        cls.emergency = True
    
    # Geschwindigkeitscode 14 Fahrstufen
    #
    @classmethod
    def speed_control_14steps(cls, direction, speed):
        pass
    
    # Geschwindigkeitscode 128 Fahrstufen
    #
    @classmethod
    def speed_control_128steps(cls, direction, speed):
        if speed == -1:
            speed = 1
        elif speed == 0:
            speed = 0
        else:
            if speed <= 126:
                speed += 2
            else:
                speed = 127
            speed &= 0xfe
        speed |= (direction << 7)
        speed &= 0xff
        return speed

    # Geschwindigkeitscode 28 Fahrstufen
    #
    @classmethod
    def speed_control_28steps(cls, direction, speed):
        cssss = 0
        speed = min(speed, 28)
        if speed == -1:                  # Notstop
           cssss = 0b00000
        elif 0 <= speed <= 28:
           if speed == 0:
               cssss = 0b00000
           else:
               temp = speed + 3
               c = (temp & 0b1) << 4
               ssss = temp >> 1
               cssss = c | ssss

        return (0b01000000 | direction << 5 | cssss) & 0xff
        
   
    #
    @classmethod
    def to_bin(cls, num):
        stream = 0
        for j in range(0, 8):
            if num & 1 << (7 - j):
                stream |= 1
            stream <<= 1
        return stream >> 1 & 0xff


    @classmethod
    def prepare(cls, packet=[]):  # Daten in den Puffer stellen
        stream = 0
        bits = 0
        padding = 0
        if 2 <= len(packet) <= 5:  # Anzahl Bytes ohne XOR
            # Streamlänge = jedem Byte ein 0 voran, das XOR-byte + 1 ans Ende + Preamble + Padding auf Wortgrenze (32 Bit)
            err = 0;
            for byte in packet:
                err ^= byte
            packet.append(err)
            preamble = cls.PREAMBLE
            bits = preamble + len(packet) * 9 + 1
            padding = 32 - (bits % 32) # links mit 1 erweitern bis Wortgrenze
            for i in range(0, padding + preamble):
                stream <<= 1
                stream |= 1
            if DEBUG:
                print(bin(stream), ": ", len(bin(stream))-2, " <") 
            for i in packet:
                stream <<= 9
                stream |= cls.to_bin(i)
            if DEBUG:
                print(bin(stream), ": ", len(bin(stream))-2, " <") 
            stream <<= 1
            stream |= 1
            if DEBUG:
                print(bin(stream), ": ", len(bin(stream))-2, " <") 
        return (padding + bits) // 32, stream  # Anzahl der Worte + Bitstream
            
    
    #
    @classmethod
    def generate_address(cls, loco):
        instruction = []
        if loco.use_long_address:
            instruction.append(192 | (loco.address // 256))
            instruction.append(loco.address & 0xff)
        else:
            instruction.append(loco.address)
        return instruction
        
    #
    @classmethod
    def generate_instructions(cls):
        words  = []
        lengths = []
        for loco in cls.locos:
            # lange oder kurze Adresse
            instruction = cls.generate_address(loco)
            # Richtung, Geschwindigkeit
            richtung = loco.current_speed["Dir"]
            fahrstufe = loco.current_speed["FS"]
            if loco.speedsteps == 128:
                speed = cls.speed_control_128steps(richtung, fahrstufe)
                instruction.append(0b00111111)
                instruction.append(speed)
            elif loco.speedsteps == 28:
                speed = cls.speed_control_28steps(richtung, fahrstufe)
                instruction.append(speed)
            elif loco.speedsteps == 14: # @TODO
                speed = cls.speed_control_14steps(richtung, fahrstufe)
                pass
            else:
                pass

            l, w = cls.prepare(instruction)
            words.append(w)
            lengths.append(l)
        
            # Funktionen
            for f in loco.functions:
                instruction = []
                if loco.use_long_address:
                    instruction.append(192 | (loco.address // 256))
                    instruction.append(loco.address & 0xff)
                else:
                    instruction.append(loco.address)
                    
                instruction.append(f)

                l, w = cls.prepare(instruction)
                words.append(w)
                lengths.append(l)
                
        return lengths, words
            
    #
    @classmethod
    def buffering(cls):
        buffer = []
        if cls.emergency == True:
            for i in range(5):
                for e in cls.EMERG:
                    buffer.append(e)
            cls.emergency = False
            
        else:
            l, w = cls.generate_instructions()
            buffer = cls.make_buffer(l, w)
            if buffer == []:
                buffer = cls.IDLE

        return buffer
    

    #
    @classmethod
    def make_buffer(cls, l, w):
        buffer = []
        for i in range(len(l)):
            if DEBUG:
                print("Array#",i, end=": ")
            while l[i] > 0:
                l[i] -= 1
                word = (w[i] >> l[i] * 32 & 0xffffffff)
                if DEBUG:
                    print("[" + bin(word) + "]", end=" ")
                buffer.append(word)
            if DEBUG:
                print()
        return buffer

    #
    @classmethod
    def send2track(cls):
        try:
            if cls.power_state == True:
                if (utime.ticks_ms() - cls.messtimer > 100):
                    cls.chk_short()
                    cls.messtimer = utime.ticks_ms()
     
                if cls.buffer_dirty:
                    buffer = cls.buffering()
                    cls.ringbuffer = buffer
                else:
                    buffer = cls.ringbuffer
                if buffer == []:
                    buffer = cls.IDLE
                
                if not DEBUG:
                    state = machine.disable_irq()

                if cls.accessory_buffer != []:
                    if DEBUG:
                        print("Accessory signal: ", end="")
                    for word in cls.accessory_buffer:
                        if DEBUG:
                            print("["+bin(word)+"]", end=" ")
                        cls.statemachine.put(word)
                    cls.accessory_buffer = []

                if DEBUG:
                    print("Operation Mode Track signal:", end=" ")
                for word in buffer:
                    if DEBUG:
                        print("["+bin(word)+"]", end=" ")
                    cls.statemachine.put(word)
                if DEBUG:
                    print()
                if not DEBUG:
                    machine.enable_irq(state)
                cls.buffer_dirty = False

        except KeyboardInterrupt:
            raise(KeyboardInterrupt("SIGINT"))

# --------------------------------------

class OPERATIONS(ELECTRICAL):
    
    # a few constants for accressories 
    LEFT_OR_STOP = const(0)      # Parameter 'R': Fahrweg nach links bzw. Signal rot lt. RP 9.2.1 Abschnitt 2.4.1 
    RIGHT_OR_TRAVEL = const(1)   # Parameter 'R': Fahrweg nach rechts bzw. Signal grün
    DEACTIVATE = const(0)        # Parameter 'D': Aktivieren oder deaktivieren des angesprochenen Zubehörs
    ACTIVATE = const(1)          # Parameter 'D': Aktivieren oder deaktivieren des angesprochenen Zubehörs
    
    active_loco = None # Active Loco
    device = None # Active accessory
    #
    @classmethod
    def __init__(cls):
        super().__init__()
        
    @classmethod
    def ctrl_loco(cls, address=3, use_long_address=False, speedsteps=28):
        cls.active_loco = LOCO(address, use_long_address, speedsteps)
        index = cls.search(cls.active_loco)
        if index == None:
            cls.locos.append(cls.active_loco)
        else:
            if cls.active_loco.speedsteps != cls.locos[index].speedsteps or \
               cls.active_loco.use_long_address != cls.locos[index].use_long_address:
                cls.locos.remove(cls.locos[index])
                cls.locos.append(cls.active_loco)
            else:
                cls.active_loco = cls.locos[index]

    @classmethod
    def search(cls, loco):
        for i in range(len(cls.locos)):
            if cls.locos[i].address == loco.address:
                return i
        return None

    #
    @classmethod
    def end(cls):
        if cls.power_state == True:
            cls.power_off()
        utime.sleep_ms(100)
        cls.emergency_stop()
        cls.locos = []
        cls.device = None
        cls.active_loco = None
        cls = None
    
    #
    @classmethod
    def begin(cls):
        cls.power_on()
        cls.chk_short()
        utime.sleep_ms(100)
    
    # run this in a infinitive loop
    @classmethod
    def loop(cls):
        if cls.power_state == False:
            raise(RuntimeError("Power is off"))
        cls.send2track()    # scheduler: Funktion liefert die DCC-Instruktionen an das Gleis

    # Funktionsgruppen-ID
    #
    @classmethod
    def get_function_group_index(cls, function_nr):
        if function_nr < 5:
            function_group = 0
        elif function_nr < 9:
            function_group = 1
        else:
            function_group = 2
        return function_group
    
    # Shift für die Funktionsbytes    
    #
    @classmethod
    def get_function_shift(cls, function_nr):
        if function_nr == 0:
            function_shift = 4
        else:
            function_shift = ((function_nr - 1) % 4)
        return function_shift

    # Funktionscode
    #
    @classmethod
    def function_control(cls, funktion=0):
        f =  0b10000000
        if 0 <= funktion <= 4:
            pass
        elif 5 <= funktion <= 8:
            f |= 0b110000
        elif 9 <= funktion <= 12:
            f |= 0b100000
        return f

    #
    @classmethod
    def function_on(cls, function_nr):
        cls.set_function(function_nr)
        
    #
    @classmethod
    def function_off(cls, function_nr):
        cls.set_function(function_nr, False)

    # Funktion aktiv oder inaktiv?
    #
    @classmethod
    def get_function(cls, function_nr):
        status = False
        if 0 <= function_nr <= 12:
            function_group = cls.get_function_group_index(function_nr)
            status = (cls.active_loco.functions[function_group] & (1 << cls.get_function_shift(function_nr))) != 0 
        return status
        
    # Funktionsbits setzen und an Lok senden
    #
    @classmethod
    def set_function(cls, function_nr, status = True):
        if 0 <= function_nr <= 12:
            function_group = cls.get_function_group_index(function_nr)
            instruction_prefix = cls.function_control(function_nr)
            if status == True:
                cls.active_loco.functions[function_group] |= ((1 << cls.get_function_shift(function_nr)) | instruction_prefix)
            else:
                cls.active_loco.functions[function_group] &= (~(1 << cls.get_function_shift(function_nr)) | instruction_prefix)
        cls.buffer_dirty = True
        
    # fahre mit 14 oder 28/128 FS (128 bevorzugt)
    #
    @classmethod
    def drive(cls, richtung, fahrstufe):  # Fahrstufen
        cls.active_loco.current_speed = {"Dir": richtung, "FS": fahrstufe}
        cls.buffer_dirty = True
        
    #
    @classmethod
    def speed(cls, speed=None):
        if speed != None:
            if speed != cls.active_loco.current_speed["FS"]:
                cls.drive(cls.active_loco.current_speed["Dir"], speed)
        return cls.active_loco.current_speed["FS"]
        
    #
    @classmethod
    def direction(cls, direction=None):
        if direction != None:
            if direction != cls.active_loco.current_speed["Dir"]:
                cls.drive(direction, cls.active_loco.current_speed["FS"])
        return cls.active_loco.current_speed["Dir"]

    #
    @classmethod
    def ctrl_accessory_basic(cls, address=1, D=0, R=0):
        byte2 = 0b10000000
        device = ACCESSORY(address, D, R)
  
        address = address + 3 & 0b0000011111111111
        
        byte1 = ((address >> 2) & 0x3f) | byte2
  
        byte2 |= (address & 0b11) << 1
        byte2 |= ~(address & 0b11100000000) >> 4 & 0b11110000
        byte2 |= (D << 3)
        byte2 |= R
        
        l, w = cls.prepare([byte1, byte2])
        cls.accessory_buffer = cls.make_buffer([l], [w])
    
    #
    @classmethod
    def ctrl_accessory_extended(cls, address=1, aspects=0):
        b1 = 0b10000000
        b2 = 0b01110001
        b3 = 0b00000000

        device = ACCESSORY(address, 0, 1)
        b = address + 3 & 0b0000011111111111
        byte1 = ((b >> 2) & 0x3f) | b1
        byte2 = ~(b >> 3) & 0b01110000 | b2 | (b << 1) & 0b00000110
        byte3 = aspects & 0xff  # set aspects
            
        l, w = cls.prepare([byte1, byte2, byte3])
        cls.accessory_buffer = cls.make_buffer([l], [w])
        
# ----------------------------------------------------------------

class ACCESSORY:
    # new accessory
    def __init__(self, address=1, R=0, D=0, signal = False, timed = False, name=""):
        self.address = address
        self.R = R
        self.D = D
        self.signal = signal
        self.timed = timed
        self.name = name
        
class LOCO:
    # new_loco
    def __init__(self, address=None, use_long_address=False, speedsteps=28, name=""):
        if address != None:
            self.address = address
            if(self.address > 127):
                self.use_long_address = True
            else:
                self.use_long_address = use_long_address
            self.current_speed = {"Dir": 1, "FS": 0}
            self.speedsteps = speedsteps
            self.functions = [0b10000000, 0b10110000, 0b10100000]
            self.name = name

        
# ------------------------------------------------------------------