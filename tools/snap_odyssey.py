#!/usr/bin/env python3
"""Read-only: dump Odyssey config area and diff against the previous snapshot.

usage: snap_odyssey.py <label>        # saves tools/snapshots/<n>_<label>.bin and prints diff vs previous
"""
import os, sys, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from probe_odyssey import find_hidraw, frame, xfer

CHUNK = 0x38
LENGTH = 0x7E0          # bytes of config to read
SNAPDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'snapshots')

def read_config(fd):
    data = bytearray()
    xfer(fd, frame(0x01))
    try:
        for off in range(0, LENGTH, CHUNK):
            resp = xfer(fd, frame(0x05, CHUNK, off))
            if not resp or resp[0][3] != 0x05:
                raise RuntimeError(f'bad response at offset {off:#x}: {resp}')
            data += resp[0][8:8 + CHUNK]
    finally:
        xfer(fd, frame(0x02))
    return bytes(data)

def dump(data):
    for i in range(0, len(data), 16):
        row = data[i:i + 16]
        if any(row):
            print(f'{i:04x}: ' + ' '.join(f'{b:02x}' for b in row))

if __name__ == '__main__':
    label = sys.argv[1] if len(sys.argv) > 1 else 'snap'
    os.makedirs(SNAPDIR, exist_ok=True)
    prev = sorted(glob.glob(os.path.join(SNAPDIR, '[0-9][0-9]_*.bin')))
    fd = os.open(find_hidraw(), os.O_RDWR)
    try:
        data = read_config(fd)
    finally:
        os.close(fd)
    nxt = max((int(os.path.basename(f)[:2]) for f in prev), default=-1) + 1
    path = os.path.join(SNAPDIR, f'{nxt:02d}_{label}.bin')
    open(path, 'wb').write(data)
    print(f'saved {path}')
    if not prev:
        dump(data)
    else:
        old = open(prev[-1], 'rb').read()
        print(f'diff vs {os.path.basename(prev[-1])}:')
        diffs = [(i, old[i], data[i]) for i in range(min(len(old), len(data))) if old[i] != data[i]]
        for i, a, b in diffs:
            print(f'  {i:#06x}: {a:02x} -> {b:02x}  ({a} -> {b})')
        if not diffs:
            print('  (no change)')
