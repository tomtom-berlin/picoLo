"""
ESP-NOW receiver, zum Test des Inglenook Siding Remote Controllers
auf ESP32-C3 Super mini
"""

import network
import espnow
from machine import UART, Pin
import struct
import binascii
from micropython import const

SHUTDOWN_PIN = const(10)  # Layuot ausschalten, aktiv HIGH
RESET_PIN = const(3)      # Reset des Layouts auslösen, aktiv HIGHT
LED_PIN = const(8)        # Nur zum Testen, Verwendung nicht empfehlenswert!!

# 84:0d:8e:8c:98:ee = rcv
# 
# A WLAN interface must be active to send()/recv()

def print_mac(name="Throttle", host=b'\ff\ff\ff\ff\ff\ff'):
    p1, p2, p3, p4, p5, p6 = struct.unpack("BBBBBB", host)
    return f"\\{hex(p1)[2:4]}\\{hex(p2)[2:4]}\\{hex(p3)[2:4]}\\{hex(p4)[2:4]}\\{hex(p5)[2:4]}\\{hex(p6)[2:4]}"

def encode_mac(host):
    k = []
    for c in host:
        k.append(int(c))
    return k

def reset():          # Wert an Ausgang shutdown und reset
    led_pin.on()      #                     0          1
    reset_pin.on()    
    shutdown_pin.off()

def emerg():
    led_pin.on()      #                     1          1
    reset_pin.on()
    shutdown_pin.on()

def shutdown():
    led_pin.on()      #                     1          0
    reset_pin.off()
    shutdown_pin.on()

sta = network.WLAN(network.STA_IF)
sta.active(True)
mac = sta.config('mac')
mac_address = ''.join('\\%x' % b for b in mac)
print(mac_address)


reset_pin = Pin(RESET_PIN, Pin.OUT)
reset_pin.off()
shutdown_pin = Pin(SHUTDOWN_PIN, Pin.OUT)
shutdown_pin.off()
led_pin = Pin(LED_PIN, Pin.OUT)
led_pin.off()

#print(encode_mac(mac))

#sta.disconnect()   # Because ESP8266 auto-connects to last Access Point

e = espnow.ESPNow()
e.active(True)


"""
typedef struct {
  int address;
  uint16_t cv;
  uint8_t direction_on_off;
  uint8_t speed_ascpect_function_value;
} SUBCOMMAND_TYPE;

typedef struct {
  MESSAGE_TYPE msg_type;
  uint8_t mac[6];
  int throttle_id;
  int size;
  SUBCOMMAND_TYPE subcommand;
} COMMAND_TYPE
"""

recv_format = "b6si224s"
send_format = "bBBBBBBi224s"

uart = UART(1, baudrate=115200, tx=Pin(21), rx=Pin(20))
print("Starte UART und ESP-Now")
old_host = None
while True:
    host, msg = e.recv()
    
    if(host):
        host_mac = ''.join('%x' % b for b in host)
        if(host_mac != old_host):
            print("HOST ", host_mac)
            old_host = host_mac
    if msg:             # msg == None if timeout in recv()
#         print(msg)
        msg_type, broadcast_mac, length, text = struct.unpack(recv_format, msg)
#         print(binascii.hexlify(sender_mac.decode()))      
        print(print_mac("Broadcast ", broadcast_mac))
        print(f"{'Pairing Request' if msg_type == 0 else 'Data' } from {print_mac("Sender", broadcast_mac)} received {length} bytes, text = {text[:length].decode('utf-8')}")
        mac_sender = encode_mac(mac)
        if(msg_type == 0):
            try:
                e.add_peer(host)
                
            except OSError as num:
                print(num)
#                 if(num == 'ESP_ERR_ESPNOW_EXIST'):
                pass

            answer = struct.pack(send_format, 0,
                                 mac_sender[0],
                                 mac_sender[1],
                                 mac_sender[2],
                                 mac_sender[3],
                                 mac_sender[4],
                                 mac_sender[5],
                                 28, "Inglenook Siding Layout 1" )
            e.send(host, answer, False)
#             print(answer)

#         uart.write(f"{print_mac(host=throttle_mac):<10} [{msg_type:>3}]{throttle_id:>3} : {cmd[0].decode('utf-8').split('#')}\n")
        print("!"+text[:length].decode('utf-8')+"!")
        if text[:length].decode('utf-8') == "<<<QUIT>>>":
            print("quit()")
            shutdown()
            break
        if text[:length].decode('utf-8') == "<<<EMERG>>>":
            print("quit()")
            emerg()
            break
        if text[:length].decode('utf-8') == "<<<RESET>>>":
            print("quit()")
            reset()
            break
 
        