#!/usr/bin/env python3
"""Set bytes in the Odyssey lighting config block (offsets 0x00-0x3F).

Config lives in flash: a write can only clear bits, and a write starting at
offset 0 erases the block first. So we always read-modify-write the whole
0x40-byte block: 0x38 bytes at offset 0 (erase + write), then the rest.

usage: poke_odyssey.py <offset> <byte> [<byte> ...]     (values hex or dec, e.g. 0x03 4)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from probe_odyssey import find_hidraw, frame, xfer, hx

BLOCK = 0x40
CHUNK = 0x38

def read(fd, off, size):
    r = xfer(fd, frame(0x05, size, off))
    if not r or r[0][3] != 0x05:
        raise RuntimeError(f'read failed at {off:#x}: {r}')
    return r[0][8:8 + size]

def write(fd, off, data):
    r = xfer(fd, frame(0x06, len(data), off, data))
    if not r or r[0][3] != 0x06:
        raise RuntimeError(f'write not acknowledged at {off:#x}: {r}')

if __name__ == '__main__':
    off = int(sys.argv[1], 0)
    data = bytes(int(x, 0) for x in sys.argv[2:])
    if off + len(data) > BLOCK:
        sys.exit('only offsets within 0x00-0x3F are supported')
    fd = os.open(find_hidraw(), os.O_RDWR)
    try:
        xfer(fd, frame(0x01))
        block = bytearray(read(fd, 0, CHUNK) + read(fd, CHUNK, BLOCK - CHUNK))
        block[off:off + len(data)] = data
        write(fd, 0, bytes(block[:CHUNK]))
        write(fd, CHUNK, bytes(block[CHUNK:]))
        back = read(fd, 0, CHUNK) + read(fd, CHUNK, BLOCK - CHUNK)
        print('config[0:32]:', hx(back[:32]))
        if back != bytes(block):
            sys.exit('VERIFY FAILED: read-back differs from written block')
    finally:
        xfer(fd, frame(0x02))
        os.close(fd)
