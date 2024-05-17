import utime, rp2

t = utime.ticks_ms()
run_eventloop = True
while utime.ticks_ms() - t < 3000:  # 3 Sekunden warten auf evtl. unterbrechung mit Bootsel-Buttone
    run_eventloop &= not rp2.bootsel_button()

if run_eventloop:
    import eventloop2
    
    