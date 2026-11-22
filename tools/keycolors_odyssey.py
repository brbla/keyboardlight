#!/usr/bin/env python3
"""Per-key colours for Yenkee Odyssey (effect 19 = Custom).

LED index = row * 15 + col  (6 rows x 15 cols, 128 slots x RGB = 0x180 bytes)
  write: cmd 0x0b, read: cmd 0x0a, chunks of 0x38 bytes from offset 0.

usage:
  keycolors_odyssey.py read                       print lit LEDs
  keycolors_odyssey.py set <base RRGGBB> [idx,idx,...=RRGGBB ...]
      e.g. set 101010 32,46,47,48=ff0000 73,87,88,89=0000ff
  keycolors_odyssey.py restore <file.bin>         write a raw 0x180-byte backup
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from probe_odyssey import find_hidraw, frame, xfer, hx

SIZE, CHUNK, EFFECT_CUSTOM = 0x180, 0x38, 19


def read_colors(fd):
    data = bytearray()
    for off in range(0, SIZE, CHUNK):
        n = min(CHUNK, SIZE - off)
        r = xfer(fd, frame(0x0a, n, off))
        if not r or r[0][3] != 0x0a or r[0][7] != 0:
            raise RuntimeError(f'read failed at {off:#x}')
        data += r[0][8:8 + n]
    return bytes(data)


def write_colors(fd, data):
    for off in range(0, SIZE, CHUNK):
        chunk = data[off:off + CHUNK]
        r = xfer(fd, frame(0x0b, len(chunk), off, chunk))
        if not r or r[0][3] != 0x0b or r[0][7] != 0:
            raise RuntimeError(f'write failed at {off:#x}: {r}')


def rgb(s):
    return bytes.fromhex(s)


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'read'
    fd = os.open(find_hidraw(), os.O_RDWR)
    try:
        xfer(fd, frame(0x01))
        if cmd == 'read':
            d = read_colors(fd)
            for i in range(0, SIZE, 3):
                if any(d[i:i + 3]):
                    print(f'led {i // 3:3d} (r{i // 3 // 15} c{i // 3 % 15:2d}): {hx(d[i:i + 3])}')
        else:
            if cmd == 'set':
                base = rgb(sys.argv[2])
                d = bytearray(base * 90 + bytes(SIZE - 270))
                for spec in sys.argv[3:]:
                    idxs, col = spec.split('=')
                    for i in idxs.split(','):
                        d[int(i) * 3:int(i) * 3 + 3] = rgb(col)
            elif cmd == 'restore':
                d = bytearray(open(sys.argv[2], 'rb').read())
            else:
                sys.exit(__doc__)
            write_colors(fd, bytes(d))
            back = read_colors(fd)
            print('verify:', 'OK' if back == bytes(d) else 'MISMATCH')
    finally:
        xfer(fd, frame(0x02))
        os.close(fd)
