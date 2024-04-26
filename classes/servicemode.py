#
# "pico Lo" - Digitalsteuerung mit RPI pico
#
# (c) 2024 Thomas Borrmann
# Lizenz: GPLv3 (sh. https://www.gnu.org/licenses/gpl-3.0.html.en)
#
# Funktionen für den Bereich "SERVICE MODE" der NMRA DCC RP 9.2.2
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

from micropython import const
from machine import Timer

LONG_PREAMBLE = const(22)
PREAMBLE = const(14)


class SERVICEMODE:
    
    def __init__(self, electrical, bias, treshold, timeout=30000):
        self.treshold = treshold + bias
        self.timeout_flag = False
        self.timeout = timeout
        self.timer = Timer(-1)
        self.electrical = electrical
        
    def timer_isr(timer):
        if timer == self.timer:
            self.timeout_flag = True

    
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
        # {Long-preamble} 0 011110AA 0 AAAAAAAA 0 111KDBBB 0 EEEEEEEE 1
        cv -= 1
        bit -= 1
        self.electrical.send2track([(PREAMBLE, [0x00, 0x00], 3), (LONG_PREAMBLE, \
                    [0b1111000 | (cv >> 8), cv & 0xff, (0b11100000 | value << 3 | bit) & 0xff], 5), \
                    (PREAMBLE, [0x00, 0x00], 1)])


    def verify(self, cv=1, value=3):
        # {Long-preamble} 0 011101AA 0 AAAAAAAA 0 DDDDDDDD 0 EEEEEEEE 1
        cv -= 1
        self.electrical.send2track([(PREAMBLE, [0x00, 0x00], 3), \
                    (LONG_PREAMBLE, [0b01110100 | (cv >> 8), cv & 0xff, value & 0xff], 5), \
                    (PREAMBLE, [0x00, 0x00], 1)])

    def get(self, cv):
        cv_val = 0
        self.timer.init(period=self.timeout, mode=Timer.ONE_SHOT, callback=self.timer_isr)
        for bit in range(1, 9):
            self.verify_bit(cv, bit, 1)
            current = self.electrical.get_current()
            if current > self.treshold:
                cv_val += 1 << (bit - 1)
        print(f"Teste {cv}")
        self.verify(cv, cv_val)
        while self.electrical.get_current() < self.treshold and self.timeout_flag == False:
            cv_val = 0
            for bit in range(1, 9):
                if self.timeout_flag:
                    break
                self.verify_bit(cv, bit, 1)
                if self.electrical.get_current() > self.treshold:
                    cv_val += 1 << (bit - 1)
            print(f"CV{cv} = {cv_val}")
            self.verify(cv, cv_val)
        self.timer.deinit()
        return cv_val

    def set(self, cv=1, value=3):
        # {Long-preamble} 0 011111AA 0 AAAAAAAA 0 DDDDDDDD 0 EEEEEEEE 1
        cv -= 1
        self.electrical.send2track([(PREAMBLE, [0x00, 0x00], 3), \
                     (LONG_PREAMBLE, [0b01111100 | (cv >> 8), cv & 0xff, value & 0xff], 5), \
                     (LONG_PREAMBLE, [0b01111100 | (cv >> 8), cv & 0xff, value & 0xff], 6) ])
        ack_flag = self.electrical.get_current() < self.treshold
        while not ack_flag:
            self.electrical.send2track([(LONG_PREAMBLE, [0b01111100 | (cv >> 8), cv & 0xff, value & 0xff], 5)])
            ack_flag = self.electrical.get_current() < self.treshold
 
        self.electrical.send2track([(PREAMBLE, [0x00, 0x00], 1)])
            
            
# --------------------------------------

