```
Benutzung:
Zeichen eingeben und mit Enter abschicken, Befehlstrenner = '#'

Zeichen| Führt aus
-------+---------------------------------------------------------------------
?      | Diese Hilfe
e      | Nothalt alle Fahrzeuge
       |
l      | Lok suchen (via Servicemode, es darf nur ein Decoder ansprechbar sein)
l{nnn} | Lok bedienen {nnn} = Dekoder-Adresse (sh.unten)
n{ccc} | Name setzen {ccc} = Name
s{nnn} | Fahrstufen setzen {nnn} = Fahrstufen (28/128)
v{nnn} | Lok vorwärts Fahrstufe {nnn}
r{nnn} | Lok rückwärts Fahrstufe {nnn}
+      | Lok Fahrstufe erhöhen um 1 (mehrere Plus = Anzahl der Fahrstufen)
-      | Lok Fahrstufe verringern um 1 (mehrere Minus = Anzahl der Fahrstufen)
V      | Lok vorwärts höchste Fahrstufe
R      | Lok rückwärts höchste Fahrstufe
h      | Lok Halt
       |
d      | Liste der Loks ausgeben
d{nnn} | Lok aus der Liste entfernen (keine weiteren Pakete generieren), {nnn} = Adresse
       |
F|f{nn}| Funktion {nn = 0..12} ein/ausschalten
f o. F | Welche Funktionen sind eingeschaltet?
       |
w{nnn} | Weiche geradeaus {nnn} = Weichenadresse
W{nnn} | Weiche abzweigend {nnn} = Weichenadresse
       |
q o. Q | Beenden
-------+---------------------------------------------------------------------
       |
PoM:   | [P, p, A, a]{Adresse, CV-Nummer, Wert}
P o. p | für Multifunktionsdekoder
A o. a | für Accessory-Decoder 
-----------------------------------------------------------------------------
```
