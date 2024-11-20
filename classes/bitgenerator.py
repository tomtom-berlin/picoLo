import rp2
import machine

class BITGENERATOR():
    # Ausgangszustand = nix!
    statemachine = None
    
    def __init__(cls, base_pin=None):
        # freq = 500_000 # 2.0us clock cycle
        if base_pin == None:
            raise(ValueError("Kein Basis-Pin für die Ausgabe"))
        cls.statemachine = rp2.StateMachine(0, cls.dccbit, freq=500000, set_base=machine.Pin(base_pin))
        cls.statemachine.active(1)
        cls.statemachine.put(0b11110111111110000000000111111111)
        
        
    def begin(cls):
        cls.statemachine.active(1)
        
    def end(cls):
        cls.statemachine.exec('set(pins, 0b111)')
        cls.statemachine.active(0)

    def put(cls, word):
        cls.statemachine.put(word)

    # 0 = 100µs = 50 Takte, 1 = 58µs = 29 Takte
# for LM18200D H-Bridge Module
#    @rp2.asm_pio(set_init=(rp2.PIO.OUT_HIGH), out_shiftdir=rp2.PIO.SHIFT_LEFT, autopull=True)
# for DDRV8871 H-Bridge Module
    @rp2.asm_pio(set_init=(rp2.PIO.OUT_HIGH, rp2.PIO.OUT_HIGH, rp2.PIO.OUT_HIGH), out_shiftdir=rp2.PIO.SHIFT_LEFT, autopull=True)
    def dccbit():
#steht, wenn kein input
#         label("bitstart")
#         set(pins, 1)[26]
#         out(x, 1)
#         jmp(not_x, "is_zero")
#         set(pins, 0)[27]
#         jmp("bitstart")
#         label("is_zero")
#         nop()[20]
#         set(pins, 0)[28]
#         nop()[20]

# #mit Leerlauf ==> IDLE?    # cycles
        out(isr, 32)
        wrap_target()
        label("bitstart")        # _–
        set(pins, 0b10)[23]      # 24     2
#        set(pins, 1)[23]         # 24     2
        jmp(not_osre, "next")    # 25     3
        # default: Preamble, IDLE
        mov(osr, isr)            # 26     4  
        mov(y, 4)                # 27     5  14 Bit "1", mov nur 3 bit möglich, daher 3 Impulse * y+1
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
        set(pins, 0b10)[28]      # 29     6
#         set(pins, 0)[28]         # 29    15 
#         set(pins, 1)[28]         # 29    16
#         set(pins, 0)[28]         # 29    15 
#         set(pins, 1)[28]         # 29    16
#         set(pins, 0)[26]         # 27    17 
        jmp(y_dec, "preamble")   # 28    18
        jmp("bitstart")          # 29    19
        
        label("next")            # --     7 
        out(x, 1)[2]             # 28     8
        label("check")
        jmp(not_x, "is_zero")    # 29     9
#         set(pins, 0)[27]         # 28    10
        set(pins, 0b01)[27]      # 28    10
        jmp("bitstart")          # 29    11
        label("is_zero")       
        nop()[20]                #50     12
        set(pins, 0b01)[28]      #29     13 
        nop()[19]                #49     14
        wrap()
        
        
if __name__ == "__main__":
    import time
    generator = BITGENERATOR(19)
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
