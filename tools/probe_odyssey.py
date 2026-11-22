#!/usr/bin/env python3
"""Read-only probe of Yenkee Odyssey (320f:5055) using the EVision-style protocol.

Frame (64 B, report ID 0x04 on interface 1, usage page 0xFF1C):
  [0]=0x04 [1..2]=checksum LE (sum of bytes 3..63) [3]=cmd [4]=size [5..6]=offset LE [7]=0 [8..]=data
Commands used here: 0x01 begin configure, 0x05 read config, 0x02 end configure.
"""
import glob, os, select, sys

def find_hidraw():
    for p in glob.glob('/sys/class/hidraw/hidraw*'):
        dev = os.path.realpath(p + '/device')
        ue = open(dev + '/uevent').read()
        if 'HID_ID=0003:0000320F:00005055' in ue:
            desc = open(dev + '/report_descriptor', 'rb').read()
            if b'\x06\x1c\xff' in desc:
                return '/dev/' + os.path.basename(p)
    sys.exit('Odyssey config interface not found')

def frame(cmd, size=0, offset=0, data=b''):
    b = bytearray(64)
    b[0] = 0x04; b[3] = cmd; b[4] = size; b[5] = offset & 0xff; b[6] = offset >> 8
    b[8:8 + len(data)] = data
    cs = sum(b[3:]) & 0xffff
    b[1] = cs & 0xff; b[2] = cs >> 8
    return bytes(b)

def xfer(fd, pkt, timeout=1.0):
    os.write(fd, pkt)
    out = []
    while True:
        r, _, _ = select.select([fd], [], [], timeout)
        if not r:
            break
        out.append(os.read(fd, 64))
        timeout = 0.15
    return out

def hx(b):
    return ' '.join(f'{x:02x}' for x in b)

if __name__ == '__main__':
    path = find_hidraw()
    print('using', path)
    fd = os.open(path, os.O_RDWR)
    try:
        for name, pkt in [('begin', frame(0x01)),
                          ('read cfg', frame(0x05, 0x38, 0x0000)),
                          ('end', frame(0x02))]:
            print(f'>> {name}: {hx(pkt[:16])}')
            for r in xfer(fd, pkt):
                print(f'<< {hx(r)}')
    finally:
        os.close(fd)
