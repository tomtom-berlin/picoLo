#
# "pico Lo" - Digitalsteuerung mit RPI pico
#
# (c) 2024 Thomas Borrmann
# Lizenz: GPLv3 (sh. https://www.gnu.org/licenses/gpl-3.0.html.en)
#
# Funktionen zur Darstellung des Menüs
#
# ----------------------------------------------------------------------
# 
#

from libraries.oled128x64 import OLED128x64
from classes.electrical import PACKETS
import ujson
from micropython import const


#
# --------------------------------------
# zeigt die Auswahl der Lokomotiven an
class MENU:
    def __init__(self, display = None, electrical=None, locos_filename="data/my_locos.json"):
        self.oled = display
        self.electrical = electrical
        self.filename = locos_filename
        self.loco_array = self.load_locomotives(self.filename)
        self.menu_items = self.create_menu_items(self.loco_array)
        self.menu_items_count = len(self.menu_items)
        self.selected = 0

    def get_locos(self):
        return self.loco_array
    
    
    # laedt die Lokomotiven aus einer JSON-formatierten Datei ins array
    def load_locomotives(self, filename):
        loco_array = [] 
        f = open(filename, 'rt')
        if f:
            json_obj = ujson.loads(f.read())
            if json_obj:
                for i in range(len(json_obj)):
                    loco = json_obj[i]
                    loco_array.append(PACKETS(name=loco["name"],
                                              address=loco["address"],
                                              use_long_address=loco["use_long_address"],
                                              speedsteps=loco["speedsteps"],
                                              electrical=self.electrical))
        
        return loco_array


    def create_menu_items(self, loco_array):
        menu_items = []
        for i in range(len(loco_array)):
            loco = loco_array[i]
            menu_items.append((loco,f"{loco.name} @ {loco.address}"))
        return menu_items

    def show(self):
        if self.oled != None:
            self.oled.show_list("Lok waehlen", self.menu_items, self.selected)
    
    # Lok auswählen, mit + und - werden die Zeilen gewechselt
    def select(self, key):
        temp = self.selected
        if key == '+' and self.selected < self.menu_items_count:
            temp = self.selected + 1
        elif key == '-' and self.selected > 0:
            temp = self.selected - 1
        if temp != self.selected:
            self.selected = temp % self.menu_items_count
            self.show()

        return self.loco_array[self.selected]

# ---------------------------------------------

