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

PREAMBLE = const(14)  # Standard Präambel für DCC-Instruktionen

CURRENT_SENS_ERROR = const(8.5)
SENS_SHUNT = const(20000) # Ohm
AREF_VOLT = const(3300) # mV !!
ACK_SAMPLES = const(2000)  # Anzahl der Messzyklen, für Rauschunterdrückung
SENS_AMPERE_PER_AMPERE = (1000000 / 377) # 377µA / A lt. Datenblatt

class ELECTRICAL:
    # DCC- und H-Bridge-LMD18200T-Modul elektrische Steuerung
    def __init__(self, power_pin, pwm_pin, brake_pin, dir_pin, ack_pin):   
        self.brake = machine.Pin(brake_pin, machine.Pin.OUT)
        self.pwm = machine.Pin(pwm_pin, machine.Pin.OUT)
        self.power = machine.Pin(power_pin, machine.Pin.OUT)
        self.dir_pin = dir_pin
        self.ack = machine.ADC(machine.Pin(ack_pin))
        self.power_state = self.power.value()
        self.in_servicemode = False
        self.power_off()
        
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
        self.power.value(self.pwm.value())
        self.power_state = self.power.value()

    def power_on(self):
        self.pwm.value(1)
        self.brake.value(0)  
        self.power.value(self.pwm.value())
        self.power_state = self.power.value()

    def emergency_stop(self):
        speed = 0b01000001  # Nothalt
        self.send2track([(PREAMBLE, [0, speed], 4)])

    def ack_request(self, addr, use_long_address=False):
        if use_long_address == True:
            self.send2track([(PREAMBLE, [192 | (addr // 256), addr & 0xff, 00001111], 5)])
        else:
            self.send2track([(PREAMBLE, [addr & 0x7f, 00001111], 5)])

    def servicemode_on(self):
        self.in_servicemode = True

    def servicemode_off(self):
        self.in_servicemode = False

    # Reset-Instruction (RP 9.2.1)
    def reset(self):
        if self.in_servicemode == True:
            self.send2track([(PREAMBLE, [0x00, 0x00], 1)])

    # Idle-Instruction (RP 9.2.1)
    def idle(self):
        self.send2track([(PREAMBLE, [0xff, 0x00], 1)])

    def berechne_mA(self, analog_value):
        analog_value = analog_value * AREF_VOLT / 65535  # ADC mappt auf 0..65535
        analog_value /= SENS_SHUNT  # Rsense
        return (analog_value * SENS_AMPERE_PER_AMPERE) - CURRENT_SENS_ERROR  # lt. Datenblatt 377 µA / A +/- 10 %

    def get_current(self):
        analog_value = 0
        for i in range(0, ACK_SAMPLES):
            analog_value += self.ack.read_u16()
        return round(self.berechne_mA(analog_value / ACK_SAMPLES), 1)
    
    def to_bin(self, num):
        stream = 0
        for j in range(0, 8):
            if num & 1 << (7 - j):
                stream |= 1
            stream <<= 1
        return stream

    def send2track(self, packets=[(PREAMBLE, [0xff,0x00], 1)]):
        stream = 0
        bits = 0
        for p in range(0, len(packets)):
            # bitlen = jedem Byte ein 0 voran, das Xor-byte + 1 ans Ende + preamble
            err = 0;
            packet = packets[p]
            for i in range(0, len(packet[1])):
                err ^= packet[1][i]
            packet[1].append(err)
            for r in range(0, packet[2]):
                for i in range(0, packet[0]):
                    stream |= 1
                    stream <<= 1
                    bits += 1
                for i in range(0, len(packet[1])):
                    stream <<= 9
                    stream |= self.to_bin(packet[1][i])
                    bits += 9
                stream |= 1
                stream <<= 1
                bits += 1

        while bits % 32:
            stream <<= 1
            stream |= 1
            bits += 1

        words = bits//32
        while words > 0:
            words -= 1
            word = stream >> words * 32 & 0xffffffff
            state = machine.disable_irq()
            self.statemachine.put(word) 
            machine.enable_irq(state)

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

