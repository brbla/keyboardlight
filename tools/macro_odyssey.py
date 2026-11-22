#!/usr/bin/env python3
"""Write macros to the Yenkee Odyssey (format reverse-engineered from YENKEE ODYSSEY.exe).

Macro block (written with cmd 0x15 in 0x38-byte chunks from offset 0):
  0x00 u16 0x55AA   0x02 u16 total length   0x04 u16 macro count   0x06..0x0F zero
  0x10 u16 offset[count]  (absolute offset of each macro in the block)
  macro: u16 event count, u16 0, then events of 4 bytes:
         [0..1] delay ms (u16 LE)  [2] type | 0x80 if key down  [3] code
         types: 0x0A = key (HID usage), 0x09 = modifiers (bit mask), 0x01 = mouse buttons (bit mask), 0x02 = horizontal wheel, 3/4/5 = other mouse (unverified)
Key map entry to trigger macro i: 70 ii mm (mm = mode 0..3) or 71 ii NN (play NN times).

usage: macro_odyssey.py text <string>      single macro #0 typing lowercase letters/digits
"""
import os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from probe_odyssey import find_hidraw, frame, xfer, hx

LETTER = {chr(ord('a') + i): 0x04 + i for i in range(26)}
LETTER.update({str((i + 1) % 10): 0x1E + i for i in range(10)})
LETTER[' '] = 0x2C


def event(code, down, delay=10, typ=0x0A):
    return struct.pack('<HBB', delay, (typ & 0x7F) | (0x80 if down else 0), code)


def build(macros):
    n = len(macros)
    pos = 0x10 + 2 * n
    offsets, body = [], b''
    for evs in macros:
        offsets.append(pos + len(body))
        body += struct.pack('<HH', len(evs), 0) + b''.join(evs)
    total = pos + len(body)
    head = struct.pack('<HHH', 0x55AA, total, n).ljust(0x10, b'\0')
    return head + b''.join(struct.pack('<H', o) for o in offsets) + body


def write(block):
    fd = os.open(find_hidraw(), os.O_RDWR)
    try:
        xfer(fd, frame(0x01))
        for off in range(0, len(block), 0x38):
            c = block[off:off + 0x38]
            r = xfer(fd, frame(0x15, len(c), off, c))
            if not r or r[0][3] != 0x15 or r[0][7] != 0:
                raise RuntimeError(f'write rejected at {off:#x}: {[hx(x[:8]) for x in r]}')
    finally:
        xfer(fd, frame(0x02))
        os.close(fd)


if __name__ == '__main__':
    if len(sys.argv) >= 3 and sys.argv[1] == 'text':
        evs = []
        for ch in sys.argv[2]:
            evs += [event(LETTER[ch], True), event(LETTER[ch], False)]
        blk = build([evs])
        print('block:', hx(blk))
        write(blk)
        print('written', len(blk), 'bytes')
    else:
        sys.exit(__doc__)
