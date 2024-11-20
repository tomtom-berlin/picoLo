import utime, rp2

t = utime.ticks_ms()
while utime.ticks_ms() - t < 3000:  # 3 Sekunden warten auf evtl. Unterbrechung mit Bootsel-Button
    if rp2.bootsel_button():
        raise(RuntimeError("BOOTSEL - Abbruch"))

import op_test

    
    
