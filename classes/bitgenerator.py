import rp2
import machine

# Statemachine zum Erzeugen von NMRA-DCC-Pulsen
#
# 2.0us clock cycle ==> 0 = 100µs = 50 Takte, 1 = 58µs = 29 Takte bei Frequenz 500 kHz (freq = 500000)
#
# der base_bin gibt den ersten Pin an, auf den die Impulse ausgegeben werden - bei DRV8871 (2_PWM) muss der nächste,
# bei LM18200D (1_PWM+BRAKE+DIR) auch der übernächste für die Statemachine zur Verfügung stehen.
#
# LMD18200T Logiktabelle:
# PWM | Dir | Brake | Output
# ----+-----+-------+-------
#  H  |  H  |   L   | A1, B2 -> A = VCC, B = GND
#  H  |  L  |   L   | A2, B1 -> A = GND, B = VCC
#  L  |  X  |   L   | A1, B1 -> Brake (Motor kurzgeschlossen über VCC
#  H  |  H  |   H   | A1, B1 -> Brake (Motor kurzgeschlossen über VCC
#  H  |  L  |   H   | A2, B2 -> Brake (Motor kurzgeschlossen über GND
#  L  |  X  |   H   | None   -> Power off
#
# DRV8871 Logiktabelle:
# IN1 | IN2 | Output
# ----+-----+-------
# PWM |  L  | Vorwärts
#  L  | PWM | Rückwärts
#  L  |  L  | Stop
#  H  |  H  | nicht definiert



class BITGENERATOR():
    # Ausgangszustand = nix!
    statemachine = None
    
    def __init__(cls, base_pin=None, model="LMD18200T"):
        if base_pin == None:
            raise(ValueError("Kein Basis-Pin für die Ausgabe"))
        if model == "DRV8871":
            cls.statemachine = rp2.StateMachine(0, cls.dccbit_2_pwm, freq=500000, set_base=machine.Pin(base_pin))
        elif model == "LMD18200T":
            cls.statemachine = rp2.StateMachine(0, cls.dccbit, freq=500000, set_base=machine.Pin(base_pin))
        else:
            raise(ValueError(f"{model} unbekannt"))
        cls.model = model
        
    def begin(cls):
        cls.statemachine.active(1)
        if (cls.model == 'DRV8871'):
            cls.statemachine.exec('set(pins, 0b11)')
        
    def end(cls):
        if cls.model == "DRV8871":
            cls.statemachine.exec('set(pins, 0b00)')
        cls.statemachine.active(0)

    def put(cls, word):
        cls.statemachine.put(word)

# 0 = 100µs = 50 Takte, 1 = 58µs = 29 Takte
# für DDRV8871 H-Bridge-Modul
# mit Leerlauf ==> IDLE?         cycles
    @rp2.asm_pio(set_init=(rp2.PIO.OUT_LOW, rp2.PIO.OUT_LOW), out_shiftdir=rp2.PIO.SHIFT_LEFT, autopull=True)
    def dccbit_2_pwm():
        label("bitstart")        # _–
        set(pins, 0b10)[24]      # 25     1
        jmp(not_osre, "next")    # 26     2
        # default: Einsen
        mov(x, 1)                # 27     3
        jmp("check")             # 28     4
        
        label("next")            # --      
        out(x, 1)[1]             # 28     5
        label("check")
        jmp(not_x, "is_zero")    # 29     6
        set(pins, 0b01)[27]      # 28     7
        jmp("bitstart")          # 29     8
        label("is_zero")       
        nop()[20]                # 50      9
        set(pins, 0b01)[28]      # 29     10 
        nop()[20]                # 50     11

# für LM18200D H-Bridge-Module mit Einsen als Leerlauf
    @rp2.asm_pio(set_init=(rp2.PIO.OUT_HIGH), out_shiftdir=rp2.PIO.SHIFT_LEFT, autopull=True)
    def dccbit():
        label("bitstart")        # _–
        set(pins, 1)[24]         # 25     1
        jmp(not_osre, "next")    # 26     2
        # default: Einsen
        mov(x, 1)                # 27     3  
        jmp("check")             # 28     4
        
        label("next")            # --      
        out(x, 1)[1]             # 28     5
        label("check")
        jmp(not_x, "is_zero")    # 29     6
        set(pins, 0)[27]         # 28     7
        jmp("bitstart")          # 29     8
        label("is_zero")       
        nop()[20]                # 50      9
        set(pins, 0)[28]         # 29     10 
        nop()[20]                # 50     11

        
if __name__ == "__main__":
    import time
    generator = BITGENERATOR(19, model="LMD18200T")
    time.sleep(3)
    generator.begin()
    while True:
        try:
          n = 3
          generator.put(0b11111111111111111111111111111111)
#          generator.put(0b11110000000000010000010010000011)  #emerg
          generator.put(0b00000000000000000000000000000000)  #emerg
          time.sleep(0.1)
        except KeyboardInterrupt:
            generator.end()
            raise(KeyboardInterrupt("Benutzer hat abgebrochen"))
