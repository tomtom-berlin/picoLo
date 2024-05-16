#from machine import Pin, SoftI2C
from machine import Pin, I2C
from libraries.ssd1309 import Display
from libraries.xglcd_font import XglcdFont as fm
from math import floor

# einbinden der OLED-Anzeige via I2C an Pin 5 (SCL) und 4 (SDA)
class OLED128x64:

    def __init__(self, scl_pin=5, sda_pin=4):
        self.i2c = I2C(0, scl=Pin(scl_pin), sda=Pin(sda_pin), freq=400000)
        # self.i2c = SoftI2C(scl=Pin(scl_pin), sda=Pin(sda_pin), freq=100000)
        self.oled = Display(i2c=self.i2c)
        self.menu_new = True
        self.menu_start_index = 0

    def display_text(self, col=0, line=0, text=""):
        self.oled.draw_text(col, line, text, self.font, rotate=0)
        self.oled.present()

    def get_text_height(self):
        text_height = self.font.height
        return text_height

    def splash_screen(self, splash_sprite="images/V60_120x52.mono"):
        self.oled.draw_bitmap(splash_sprite, 4, 0, 120, 52, True)
        self.oled.present()

    def set_font(self, font_name="FixedFont5x8.c", bbox_w=5, bbox_h=8):
        self.font = fm(f"../fonts/{font_name}", bbox_w, bbox_h)

    def show_list(self, title, list_items, current=0):
        n = len(list_items)
        max_lines = min(self.oled.height / (self.get_text_height() + 1), n)
        max_lines -= 2
        start_index = self.menu_start_index # Anzeige an Zeilenzahl anpassen
        while start_index + max_lines <= current and start_index < n - max_lines:
            start_index += 1
        self.start_index = start_index
        if self.menu_new:
            self.clear()
            self.display_text(0, 0, title)
            self.menu_new = False

        for i in range(max_lines):
            l = (i + 1) * (self.get_text_height() + 1)
            list_index = start_index + i
            self.display_text(0, l, f"{'*' if list_index == current else ' '}{list_items[list_index][1]}")
        

    def clear(self):
        self.oled.clear()

    def cleanup(self):
        self.oled.cleanup()
