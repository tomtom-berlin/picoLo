def binary(bytestring):
    string = ''
  
    for j in range(0, len(bytestring)):
        byte = bytestring[j]
        string += int2bin(byte)            
    return string

def int2bin(byte):
    string = ''
    for i in range(0, 8):
        if i == 4:
            string += "-"
        string += chr(((byte >> (7 - i)) & 0x1) | 0x30)
    return string
    