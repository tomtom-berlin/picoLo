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
        cls.statemachine.put(0b11110111111110000000000111111111) # IDLE als Leerlaufsequenz
        
    def end(cls):
        if cls.model == "DRV8871":
            cls.statemachine.exec('set(pins, 0b00)')
        else: # model == "LMD18200T"
            cls.statemachine.exec('set(pins, 0b101)')
        cls.statemachine.active(0)

    def put(cls, word):
        cls.statemachine.put(word)

# 0 = 100µs = 50 Takte, 1 = 58µs = 29 Takte
# für DDRV8871 H-Bridge-Modul
# mit Leerlauf ==> IDLE?         cycles
    @rp2.asm_pio(set_init=(rp2.PIO.OUT_LOW, rp2.PIO.OUT_LOW), out_shiftdir=rp2.PIO.SHIFT_LEFT, autopull=True)
    def dccbit_2_pwm():
        out(isr, 32)
        wrap_target()
        label("bitstart")        # _–
        set(pins, 0b10)[23]      # 24     2
        jmp(not_osre, "next")    # 25     3
        # default: Preamble, IDLE
        mov(osr, isr)            # 26     4  
        mov(y, 5)                # 27     5  14 Bit "1", mov nur 3 bit möglich, daher 3 Impulse * y+1
        jmp("low")[1]            # 29    20
        label("preamble")        # --
        nop()                    # 29
        set(pins, 0b10)[28]      # 29     6
        label("low")
        set(pins, 0b01)[28]      # 29    15 
        set(pins, 0b10)[28]      # 29    16
        set(pins, 0b01)[28]      # 29    15 
        set(pins, 0b10)[28]      # 29    16
        set(pins, 0b01)[26]      # 27    17 
        jmp(y_dec, "preamble")   # 28    18
        jmp("bitstart")          # 29    19
        
        label("next")            # --     7 
        out(x, 1)[2]             # 28     8
        label("check")
        jmp(not_x, "is_zero")    # 29     9
        set(pins, 0b01)[27]      # 28    10
        jmp("bitstart")          # 29    11
        label("is_zero")       
        nop()[20]                #50     12
        set(pins, 0b01)[28]      #29     13 
        nop()[20]                #50     14
        wrap()

# für LM18200D H-Bridge-Module
    @rp2.asm_pio(set_init=(rp2.PIO.OUT_HIGH), out_shiftdir=rp2.PIO.SHIFT_LEFT, autopull=True)
    def dccbit():
        out(isr, 32)
        wrap_target()
        label("bitstart")        # _–
        set(pins, 1)[23]         # 24     2
        jmp(not_osre, "next")    # 25     3
        # default: Preamble, IDLE
        mov(osr, isr)            # 26     4  
        mov(y, 5)                # 27     5  14 Bit "1", mov nur 3 bit möglich, daher 3 Impulse * y+1
        jmp("low")[1]            # 29    20
        label("preamble")        # --
        nop()                    # 29
        set(pins, 1)[28]         # 29     6
        label("low")
        set(pins, 0)[28]         # 29    15 
        set(pins, 1)[28]         # 29    16
        set(pins, 0)[28]         # 29    15 
        set(pins, 1)[28]         # 29    16
        set(pins, 0)[26]         # 27    17 
        jmp(y_dec, "preamble")   # 28    18
        jmp("bitstart")          # 29    19
        
        label("next")            # --     7 
        out(x, 1)[2]             # 28     8
        label("check")
        jmp(not_x, "is_zero")    # 29     9
        set(pins, 0)[27]         # 28    10
        jmp("bitstart")          # 29    11
        label("is_zero")       
        nop()[20]                #50     12
        set(pins, 0)[28]         #29     13 
        nop()[20]                #50     14
        wrap()
        

        
if __name__ == "__main__":
    import time
    generator = BITGENERATOR(19, model="DRV8871")
    time.sleep(3)
    generator.begin()
    while True:
        try:
          n = 3
          generator.put(0b11111111111111111111111111111111)
          generator.put(0b11110000000000010000010010000011)  #emerg
          time.sleep(1.5)
        except KeyboardInterrupt:
            generator.end()
            raise(KeyboardInterrupt("Benutzer hat abgebrochen"))
