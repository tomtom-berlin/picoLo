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
#
import machine
import rp2
from micropython import const
import utime


class ELECTRICAL:
    
    CURRENT_SENS_ERROR = const(4.9)
    SENS_SHUNT = const(20000) # Ohm
    AREF_VOLT = const(3300) # mV !!
    DENOISE_SAMPLES = const(3)  # Anzahl der Messzyklen, für Rauschunterdrückung
    SENS_AMPERE_PER_AMPERE = (1000000 / 377) # Empfindlichkeit: 377µA / A lt. Datenblatt
    SHORT = const(500)         # erlaubter max. Strom in mA
    SM_SHORT = const(250)      # im Servicemode für die zul. Dauer erlaubter max. Strom (mA)
    SM_SHORT_MS = const(100)   # zul. Dauer des erhöhten Stromes
    PREAMBLE = const(14)       # Standard Präambel für DCC-Instruktionen
    LONG_PREAMBLE = const(22)  # Präambel f. Servicemode

    IDLE =  [ const(0b11111111111111111111111111111111), const(0b11110111111110000000000111111111) ]
    RESET = [ const(0b11111111111111111111111111111111), const(0b11110000000000000000000000000001) ]
    EMERG = [ const(0b11111111111111111111111111111111), const(0b11110000000000010000010010000011) ]
    
    # DCC- und H-Bridge-LMD18200T-Modul elektrische Steuerung
    def __init__(self, power_pin, pwm_pin, brake_pin, dir_pin, ack_pin):   
        self.brake = machine.Pin(brake_pin, machine.Pin.OUT)
        self.pwm = machine.Pin(pwm_pin, machine.Pin.OUT)
        self.power = machine.Pin(power_pin, machine.Pin.OUT)
        self.dir_pin = dir_pin
        self.ack = machine.ADC(machine.Pin(ack_pin))
        self.power_state = self.power.value()
        self.mode = 0                          # 0 = inactive, 1 = operational, 2 = servicemode
        self.ack_start = -1
        self.wait_for_ack = False
        self.ack_committed = False
        self.locos = []
        self.ringbuffer = []
        self.buffer_dirty = False
        self.emergency = False
        self.short = False
        self.overcurrent_ticks = -1
        self.last_current = 0
        
        # freq = 500_000 # 2.0us clock cycle
        self.statemachine = rp2.StateMachine(0, self.dccbit, freq=500000, set_base=machine.Pin(self.dir_pin))
        self.statemachine.active(1)
        
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
        self.power.value(False)
        self.power_state = False
        self.emergency = False
        self.ringbuffer = []


    def power_on(self):
        self.pwm.value(1)
        self.brake.value(0)  
        self.power.value(True)
        self.power_state = True
        self.emergency = False
        self.short = False


    def get_actual_current(self):
        return self.last_current

    def emergency_stop(self):
        self.emergency = True

    def servicemode_on(self):
        self.mode = 2
        self.overcurrent_ticks = 0

    def servicemode_off(self):
        self.mode = 0
        self.overcurrent_ticks = 0

    # Reset-Instruction (RP 9.2.1)
    def reset(self):
        self.ringbuffer = []

    # Idle-Instruction (RP 9.2.1)
    def idle(self):
        self.ringbuffer = []

    def raw2mA(self, analog_value):
        analog_value = analog_value * self.AREF_VOLT / 65535  # ADC mappt auf 0..65535
        analog_value /= self.SENS_SHUNT  # Rsense
        return (analog_value * self.SENS_AMPERE_PER_AMPERE) - self.CURRENT_SENS_ERROR  # lt. Datenblatt 377 µA / A +/- 10 %

    def get_current(self):
        analog_value = 0
        for i in range(0, self.DENOISE_SAMPLES):
            analog_value += self.ack.read_u16()
        return round(self.raw2mA(analog_value / self.DENOISE_SAMPLES))
    
    def current_measurement(self):
        Iload = self.get_current()
        if Iload > self.SHORT:
            self.short = True

        if self.mode == 2:
            if Iload > self.SM_SHORT: # Kurzschluss im Servicemode
                if self.overcurrent_ticks < 0:
                    self.overcurrent_ticks = utime.ticks_ms()
                elif utime.ticks_ms() - self.overcurrent_ticks > self.SM_SHORT_MS: # RP 9.2.3 erlaubt 100 ms mit max. 250 mA
                    self.short = True
                    self.overcurrent_ticks = -1
            else:
                self.overcurrent_ticks = -1
                if self.wait_for_ack:
                    if self.ack_start < 0:
                        if Iload - self.last_current >= self.ACK_TRESHOLD:
                            self.ack_start = utime.ticks_us()
                    else:
                        if Iload - self.last_current < self.ACK_TRESHOLD:
                            pulse_time = utime.ticks_us() - self.ack_start
                            self.ack_committed = 4500 < pulse_time < 7000
                            self.ack_start = -1
                            self.wait_for_ack = False

        self.last_current = Iload
    
    # Geschwindigkeitscode 14 Fahrstufen
    def speed_control_14steps(self, direction, speed):
        pass
    
    # Geschwindigkeitscode 128 Fahrstufen
    def speed_control_128steps(self, direction, speed):
        if speed == -1:
            speed = 1
        elif speed == 0:
            speed = 0
        else:
            if speed < 126:
                speed += 2
            speed &= 0x7e
        speed |= (direction << 7)
        speed &= 0xff
        return speed

    # Geschwindigkeitscode 28 Fahrstufen
    def speed_control_28steps(self, direction, speed):
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
        
   
    def to_bin(self, num):
        stream = 0
        for j in range(0, 8):
            if num & 1 << (7 - j):
                stream |= 1
            stream <<= 1
        return stream

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
            if self.mode == 2:
                preamble = self.LONG_PREAMBLE
            else:
                preamble = self.PREAMBLE
            bits = preamble + len(packet) * 9 + 1
            padding = 32 - (bits % 32) # links mit 1 erweitern bis Wortgrenze
            for i in range(0, padding + preamble):
                stream |= 1
                stream <<= 1
            for i in packet:
                stream <<= 9
                stream |= self.to_bin(i)
            stream |= 1
        return (padding + bits) // 32, stream  # Anzahl der Worte + Bitstream
            
    def sync_buffer(self, words, stream):  # in den Ringpuffer schieben
        if self.mode > 0:
            while words > 0:
                words -= 1
                self.ringbuffer.append(stream >> words * 32 & 0xffffffff)

        
    def generate_instructions(self):
        words  = []
        lengths = []
        for loco in self.locos:
            # Richtung, Geschwindigkeit
            instruction = []
            if loco.use_long_address:
                instruction.append(192 | (loco.address // 256))
                instruction.append(loco.address & 0xff)
            else:
                instruction.append(loco.address)
            richtung = loco.current_speed["Dir"]
            fahrstufe = loco.current_speed["FS"]
            if loco.speedsteps == 128:
                speed = self.speed_control_128steps(richtung, fahrstufe)
                instruction.append(0b00111111)
                instruction.append(speed)
            elif loco.speedsteps == 28:
                speed = self.speed_control_28steps(richtung, fahrstufe)
                instruction.append(speed)
            elif loco.speedsteps == 14: # @TODO
                speed = self.speed_control_14steps(richtung, fahrstufe)
                pass
            else:
                pass

            l, w = self.prepare(instruction)
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

                l, w = self.prepare(instruction)
                words.append(w)
                lengths.append(l)
                
        return lengths, words
            
    def buffering(self):
        buffer = []
        if self.emergency == True:
            self.ringbuffer = []
            self.servicemode_off()
            for e in self.EMERG:
                buffer.append(e)
            for i in range(5):
                buffer.extend(buffer)
            self.emergency = False
        else:
            if self.mode == 1: # Operational 
                self.ringbuffer = []
#                if self.locos != []:
                l, w = self.generate_instructions()
                for i in range(len(l)):
                    if l[i] > 0:
                        self.sync_buffer(l[i], w[i])
                if self.ringbuffer == []:
                    buffer = self.IDLE
                else:
                    buffer = self.ringbuffer
            elif self.mode == 2: # Servicemode
                if self.ringbuffer == []:
                    buffer = self.RESET
                else:
                    for r in self.RESET:
                        buffer.append(r)
                    for i in range(3):
                        buffer.extend(buffer)
                    buffer = self.ringbuffer
            else:
                buffer = self.IDLE

        return buffer

    def loop(self, controller=None):   # Alias für die Gleissignalerzeugung
        return self.send2track(controller)    # controller: Funktion liefert die DCC-Instruktionen an den Ringpuffer
        
    def send2track(self, controller=None):
        buffer = []

        if controller==None:
            return False
        buffer = self.buffering()
        while controller():
            if self.power_state == True:
            
                self.current_measurement()
                if self.short:
                    self.power_off()
                    return False
        
                if self.buffer_dirty:
                    buffer = self.buffering()
                    self.buffer_dirty = False
                else:
                    state = machine.disable_irq()
                    
                    if self.mode == 1:
                        for word in buffer:
                            self.statemachine.put(word)
                    elif self.mode == 2:
                        self.wait_for_ack = True
                        self.ack_commited = False
                        while buffer != [] and not self.ack_committed:
                            word = buffer.pop(0)
                            self.statemachine.put(word)
                    else:
                        for word in self.IDLE:
                            self.statemachine.put(word)
                            
                    machine.enable_irq(state)
        return True

    # 0 = 100µs = 50 Takte, 1 = 58µs = 29 Takte 
    @rp2.asm_pio(set_init=rp2.PIO.OUT_LOW, out_shiftdir=rp2.PIO.SHIFT_LEFT, autopull=True)
    def dccbit():
        label("bitstart")
        set(pins, 1)[26]
        out(x, 1)
        jmp(not_x, "is_zero")
        set(pins, 0)[27]
        jmp("bitstart")
        label("is_zero")
        nop()[20]
        set(pins, 0)[28]
        nop()[20]

# --------------------------------------

class PACKETS:
    def __init__(self, name="Neu", address=3, use_long_address=False, speedsteps = 128, electrical=None):
        if name != "Neu":
            self.name = name
            self.address = address
            self.use_long_address = use_long_address
            self.current_speed = {"Dir": 1, "FS": 0}
            self.speedsteps = speedsteps
            self.functions = [0b10000000, 0b10110000, 0b10100000]
            self.electrical = electrical
            self.electrical.locos.append(self)
        
    # Funktionsgruppen-ID
    def get_function_group_index(self, function_nr):
        if function_nr < 5:
            function_group = 0
        elif function_nr < 9:
            function_group = 1
        else:
            function_group = 2
        return function_group
    
    # Shift für die Funktionsbytes    
    def get_function_shift(self, function_nr):
        if function_nr == 0:
            function_shift = 4
        else:
            function_shift = ((function_nr - 1) % 4)
        return function_shift

    # Funktionscode
    def function_control(self, funktion=0): #, status_bits=0b0):
        f =  0b10000000
        if 0 <= funktion <= 4:
            pass
        elif 5 <= funktion <= 8:
            f |= 0b110000
        elif 9 <= funktion <= 12:
            f |= 0b100000
        return f

    def function_on(self, function_nr):
        self.set_function(function_nr)
        
    def function_off(self, function_nr):
        self.set_function(function_nr, False)

    # Funktionsbits setzen und an Lok senden
    def set_function(self, function_nr, status = True):
        if self.electrical.mode != 1:
            self.electrical.mode = 1

        if 0 <= function_nr <= 12:
            function_group = self.get_function_group_index(function_nr)
            instruction_prefix = self.function_control(function_nr)
            if status == True:
                self.functions[function_group] |= ((1 << self.get_function_shift(function_nr)) | instruction_prefix)
            else:
                self.functions[function_group] &= (~(1 << self.get_function_shift(function_nr)) | instruction_prefix)
            self.electrical.buffer_dirty = True
        
    # fahre mit 14 oder 28/128 FS (128 bevorzugt)
    def drive(self, richtung, fahrstufe):  # Fahrstufen
        if self.electrical.mode != 1:
            self.electrical.mode = 1
        self.current_speed = {"Dir": richtung, "FS": fahrstufe}
        self.electrical.buffer_dirty = True
        
    
# --------------------------------------


class SERVICEMODE:
    
    def __init__(self, electrical, treshold, timeout=5000):
        self.treshold = treshold
        self.timeout = timeout
        self.electrical = electrical
        
    def timer_isr(timer):
        if timer == self.timer:
            self.timeout_flag = True

    def on(self):
        self.electrical.servicemode_on()
    
    def off(self):
        self.electrical.servicemode_off()

    def manufacturer_reset():
        for i in range(0,10):
            servicemode.set(8,0)

    # Liest eine Gruppe von CVs
    def get_cvs(self, cvs = []):
        cv_array = []
        for cv in cvs:
            cv_array.append((cv, self.get(cv)))
        return cv_array

    def verify_bit(self, cv=1, bit=1, value=0):
        if self.electrical.mode != 2:
            self.electrical.mode = 2

        # {Long-preamble} 0 011110AA 0 AAAAAAAA 0 111KDBBB 0 EEEEEEEE 1
        cv -= 1
        bit -= 1
        self.electrical.send2track([(PREAMBLE, [0x00, 0x00], 3), (LONG_PREAMBLE, \
                    [0b1111000 | (cv >> 8), cv & 0xff, (0b11100000 | value << 3 | bit) & 0xff], 5), \
                    (PREAMBLE, [0x00, 0x00], 1)])


    def verify(self, cv=1, value=3):
        if self.electrical.mode != 2:
            self.electrical.mode = 2
        # {Long-preamble} 0 011101AA 0 AAAAAAAA 0 DDDDDDDD 0 EEEEEEEE 1
        cv -= 1
        self.electrical.send2track([(PREAMBLE, [0x00, 0x00], 3), \
                    (LONG_PREAMBLE, [0b01110100 | (cv >> 8), cv & 0xff, value & 0xff], 5), \
                    (PREAMBLE, [0x00, 0x00], 1)])

    def get(self, cv):
        if self.electrical.mode != 2:
            self.electrical.mode = 2
        cv_val = 0
        treshold = self.treshold + self.electrical.get_current()
        for bit in range(1, 9):
            self.verify_bit(cv, bit, 1)
            current = self.electrical.get_current()
            if current > treshold:
                cv_val += 1 << (bit - 1)
#        print(f"Teste {cv}")
        self.verify(cv, cv_val)
        t = utime.ticks_ms() + self.timeout
        while self.electrical.get_current() < treshold and t > utime.ticks_ms():
            cv_val = 0
            for bit in range(1, 9):
                self.verify_bit(cv, bit, 1)
                if self.electrical.get_current() > treshold:
                    cv_val += 1 << (bit - 1)
#            print(f"CV{cv} = {cv_val}")
            self.verify(cv, cv_val)
        return cv_val

    def set(self, cv=1, value=3):
        if self.electrical.mode != 2:
            self.electrical.mode = 2
        # {Long-preamble} 0 011111AA 0 AAAAAAAA 0 DDDDDDDD 0 EEEEEEEE 1
        cv -= 1
        treshold = self.treshold + self.electrical.get_current()

        self.electrical.send2track([(PREAMBLE, [0x00, 0x00], 3), \
                     (LONG_PREAMBLE, [0b01111100 | (cv >> 8), cv & 0xff, value & 0xff], 5), \
                     (LONG_PREAMBLE, [0b01111100 | (cv >> 8), cv & 0xff, value & 0xff], 6) ])
        ack_flag = self.electrical.get_current() > treshold
    
        while not ack_flag:
            self.electrical.send2track([(LONG_PREAMBLE, [0b01111100 | (cv >> 8), cv & 0xff, value & 0xff], 5)])
            ack_flag = self.electrical.get_current() > treshold
 
        self.electrical.send2track([(PREAMBLE, [0x00, 0x00], 1)])
            
            
# --------------------------------------

