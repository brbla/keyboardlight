#!/usr/bin/env python3
"""Read-only: dump Odyssey device info (cmd 0x03) and key map (cmd 0x07).

Key map: 0x180 B = 128 slots x 3 B, slot index == LED index (row*15+col).
  [0] type: 0x20 keyboard (byte1 = modifier mask, byte2 = HID usage),
            0x30 consumer (bytes 1..2 = usage, LE)  ... others printed raw
usage:
  keymap_odyssey.py [--save prefix]                     dump info + default map (0x07) + active map diff
  keymap_odyssey.py set <slot>=<hex6> [...]             e.g. 45=200029 (CapsLock -> Esc)
  keymap_odyssey.py reset                               active map := default map
Every write first saves the current active map to tools/snapshots/keymap/active_<time>.bin
and is verified by read-back (cmd 0x08). Write = cmd 0x09.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from probe_odyssey import find_hidraw, frame, xfer, hx

HID = {0x04 + i: chr(ord('A') + i) for i in range(26)}
HID.update({0x1e + i: str((i + 1) % 10) for i in range(10)})
HID.update({0x3a + i: f'F{i + 1}' for i in range(12)})
HID.update({0x28: 'Enter', 0x29: 'Esc', 0x2a: 'Backspace', 0x2b: 'Tab', 0x2c: 'Space', 0x2d: '-', 0x2e: '=',
            0x2f: '[', 0x30: ']', 0x31: '\\', 0x32: '#(ISO)', 0x33: ';', 0x34: "'", 0x35: '`', 0x36: ',',
            0x37: '.', 0x38: '/', 0x39: 'CapsLock', 0x46: 'PrtSc', 0x47: 'ScrLk', 0x48: 'Pause', 0x49: 'Insert',
            0x4a: 'Home', 0x4b: 'PgUp', 0x4c: 'Delete', 0x4d: 'End', 0x4e: 'PgDn', 0x4f: 'Right', 0x50: 'Left',
            0x51: 'Down', 0x52: 'Up', 0x64: '\\(ISO)', 0x65: 'Menu'})
MODS = {0x01: 'LCtrl', 0x02: 'LShift', 0x04: 'LAlt', 0x08: 'LWin', 0x10: 'RCtrl', 0x20: 'RShift', 0x40: 'RAlt',
        0x80: 'RWin'}
CONSUMER = {0xcd: 'Play/Pause', 0xe9: 'Vol+', 0xea: 'Vol-', 0xe2: 'Mute'}


def read(fd, cmd, size):
    out = bytearray()
    for off in range(0, size, 0x38):
        n = min(0x38, size - off)
        r = xfer(fd, frame(cmd, n, off))
        if not r or r[0][3] != cmd or r[0][7] != 0:
            raise RuntimeError(f'cmd {cmd:#x} read failed at {off:#x}')
        out += r[0][8:8 + n]
    return bytes(out)


def describe(e):
    t, a, b = e
    if t == 0x20:
        if b == 0 and a:
            return '+'.join(n for m, n in MODS.items() if a & m)
        name = HID.get(b, f'hid{b:02x}')
        return name if not a else '+'.join(n for m, n in MODS.items() if a & m) + '+' + name
    if t == 0x30:
        u = a | (b << 8)
        return 'consumer:' + CONSUMER.get(u, f'{u:#06x}')
    return f'raw {hx(e)}'


def write_active(fd, km):
    for off in range(0, 0x180, 0x38):
        c = km[off:off + 0x38]
        r = xfer(fd, frame(0x09, len(c), off, c))
        if not r or r[0][3] != 0x09 or r[0][7] != 0:
            raise RuntimeError(f'write failed at {off:#x}: {r}')
    if read(fd, 0x08, 0x180) != bytes(km):
        raise RuntimeError('VERIFY FAILED: active map read-back differs')


def modify(argv):
    import time
    fd = os.open(find_hidraw(), os.O_RDWR)
    try:
        xfer(fd, frame(0x01))
        default, active = read(fd, 0x07, 0x180), read(fd, 0x08, 0x180)
        snap = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'snapshots', 'keymap',
                            time.strftime('active_%Y%m%d_%H%M%S.bin'))
        open(snap, 'wb').write(active)
        km = bytearray(default if argv[0] == 'reset' else active)
        for spec in argv[1:]:
            slot, val = spec.split('=')
            km[int(slot) * 3:int(slot) * 3 + 3] = bytes.fromhex(val)
        write_active(fd, bytes(km))
        print(f'backup {snap}; written + verified')
        for i in range(0, 0x180, 3):
            if km[i:i + 3] != default[i:i + 3]:
                print(f'  slot {i // 3:3d}: {describe(default[i:i + 3])} -> {describe(km[i:i + 3])}')
    finally:
        xfer(fd, frame(0x02))
        os.close(fd)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] in ('set', 'reset'):
        modify(sys.argv[1:])
        sys.exit()
    fd = os.open(find_hidraw(), os.O_RDWR)
    try:
        xfer(fd, frame(0x01))
        info = read(fd, 0x03, 0x22)
        km = read(fd, 0x07, 0x180)
        active = read(fd, 0x08, 0x180)
        t1b = read(fd, 0x1b, 0x80)
    finally:
        xfer(fd, frame(0x02))
        os.close(fd)
    print('device info (0x03):', hx(info))
    print('table 0x1b        :', hx(t1b))
    for i in range(0, 0x180, 3):
        e = km[i:i + 3]
        if e == bytes([0x20, 0, 0]) or not any(e):
            continue
        idx = i // 3
        print(f'{idx:3d} r{idx // 15} c{idx % 15:2d}: {hx(e)}  {describe(e)}')
    diff = [i for i in range(0, 0x180, 3) if active[i:i + 3] != km[i:i + 3]]
    print('active map differs from default in slots:', [(i // 3, describe(active[i:i + 3])) for i in diff] or 'none')
    if '--save' in sys.argv:
        p = sys.argv[sys.argv.index('--save') + 1]
        open(p + '_keymap.bin', 'wb').write(km)
        open(p + '_info.bin', 'wb').write(info)
        open(p + '_1b.bin', 'wb').write(t1b)
