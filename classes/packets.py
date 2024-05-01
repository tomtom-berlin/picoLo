#
# "pico Lo" - Digitalsteuerung mit RPI pico
#
# (c) 2024 Thomas Borrmann
# Lizenz: GPLv3 (sh. https://www.gnu.org/licenses/gpl-3.0.html.en)
#
# Funktionen für die Lokverwaltung und
# den Bereich GENERAL- und EXTENDED PACKET FORMATS der NMRA DCC RP 9.2 u. 9.2.1
#
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

LONG_PREAMBLE = const(22)
PREAMBLE = const(14)

class PACKETS:
    def __init__(self, name="Neu", address=3, use_long_address=False, max_speed=0, speedsteps = 28, electrical=None):
        if name != "Neu":
            self.name = name
            self.address = address
            self.use_long_address = use_long_address
            self.max_speed = max_speed
            self.speedsteps = speedsteps
            self.functions = [0b00000, 0b10000, 0b00000]
            self.electrical = electrical
        
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
    def function_control(self, funktion=0, status_bits=0b0):
        f = 0b10000000
        if 0 <= funktion <= 4:
            f |= status_bits
        elif 5 <= funktion <= 8:
            f |= (0b110000 | status_bits)
        elif 9 <= funktion <= 12:
            f |= (0b100000 | status_bits)
        return f


    # Funktionsbits setzen und an Lok senden
    def set_function(self, function_nr, status = False):
        if 0 <= function_nr <= 12:
            function_group = self.get_function_group_index(function_nr)
            
            if status == True:
                self.functions[function_group] |= (1 << self.get_function_shift(function_nr))
            else:
                self.functions[function_group] &= ~(1 << self.get_function_shift(function_nr))
        if self.use_long_address:
            self.electrical.send2track([(PREAMBLE, [192 | (self.address // 256), self.address & 0xff, self.function_control(function_nr, self.functions[function_group])], 10)])
        else:
            self.electrical.send2track([(PREAMBLE, [self.address, self.function_control(function_nr, self.functions[function_group])], 10)])
       
    
    def get_functions(self):
        return self.functions
        

    # Rueckgabe des Status eine bestimmten Funktion
    def get_function_state(self, function_nr):
        block = self.functions[self.get_function_group_index(function_nr)]
        bit = block & (1 << self.get_function_shift(function_nr))
        return bit != 0
        
    # Geschwindigkeitscode 14 Fahrstufen
    def speed_control_14steps(self, direction, speed):
        pass
    
    # Geschwindigkeitscode 28 Fahrstufen
    def speed_control_128steps(self, direction, speed):
        if speed == -1:
            speed = 1
        elif speed == 0:
            speed = 0
        else:
            speed += 1
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
        

    # fahre mit 28 FS
    def drive(self, richtung, fahrstufe):  # Fahrstufen
        c = 500 if fahrstufe > 0 else 10
        if self.speedsteps == 28:
            speed = self.speed_control_28steps(richtung, fahrstufe)
            for n in range(0, c):
                if self.use_long_address:
                    self.electrical.send2track([(PREAMBLE, [192 | (self.address // 256), self.address & 0xff, speed], 2)])
                else:
                    self.electrical.send2track([(PREAMBLE, [self.address, speed], 2)])
        elif self.speedsteps == 128:
            speed = self.speed_control_128steps(richtung, fahrstufe)
            for n in range(0, c):
                if self.use_long_address:
                    self.electrical.send2track([(PREAMBLE, [192 | (self.address // 256), self.address & 0xff, 0b00111111, speed], 2)])
                else:
                    self.electrical.send2track([(PREAMBLE, [self.address, 0b00111111, speed], 2)])
        elif self.speedsteps == 14:
            pass
        else:
            pass
    
# --------------------------------------
