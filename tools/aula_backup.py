#!/usr/bin/env python3
"""Read-only full backup of an AULA WIN60/WIN68/WIN75 HE (2e3c:c365) configuration.

Replays exactly the read requests the official web driver (hed.aulacn.com) sends when it connects
(sequence taken from the AulaControl project's capture re/captures/01_connect_handshake.json,
Apache-2.0, https://github.com/sgtflixy/AulaControl) and stores every request + reply as JSON.
Command 21 reads the per-key block addressed by (row, col): 21 00 00 00 18 05 ROW COL.
All rows 1-6 x cols 0-15 are read (WIN68 has a different matrix than the WIN60 in the capture).

usage: aula_backup.py [out.json]
"""
import glob, json, os, select, sys, time

VID, PID = '00002E3C', '0000C365'


def find():
    for p in sorted(glob.glob('/sys/class/hidraw/hidraw*')):
        dev = os.path.realpath(p + '/device')
        ue = open(dev + '/uevent').read()
        if f'HID_ID=0003:{VID}:{PID}' in ue and b'\x06\x1b\xff' in open(dev + '/report_descriptor', 'rb').read():
            return '/dev/' + os.path.basename(p)
    sys.exit('AULA WIN HE (2e3c:c365) config interface not found')


class Dev:
    def __init__(self, path):
        self.fd = os.open(path, os.O_RDWR)

    def xfer(self, payload: bytes, quiet=0.12, first=0.6):
        while select.select([self.fd], [], [], 0)[0]:
            os.read(self.fd, 64)
        os.write(self.fd, b'\x01' + payload.ljust(63, b'\0'))
        out, deadline = [], time.time() + first
        while True:
            r, _, _ = select.select([self.fd], [], [], max(0.0, deadline - time.time()))
            if not r:
                break
            rep = os.read(self.fd, 64)
            out.append(rep[1:] if rep[:1] == b'\x01' else rep)
            deadline = time.time() + quiet
        return out


def req(*b):
    return bytes(b)


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else time.strftime('aula_backup_%Y%m%d_%H%M%S.json')
    d = Dev(find())
    log = []

    def run(label, payload):
        replies = d.xfer(payload)
        log.append({'label': label, 'tx': payload.hex(' '), 'rx': [r.hex(' ') for r in replies]})
        return replies

    for i in range(2):
        run('info 0d', req(0x0d, 0, 0, 0))
    run('status 01', req(0x01))
    run('fixed 0e', req(0x0e))
    for sub in range(0x80, 0x8a):
        run(f'table 19 {sub:02x}', req(0x19, sub))
    run('table 22 80', req(0x22, 0x80))
    run('24 02', req(0x24, 0x02))
    run('24 01', req(0x24, 0x01))
    run('table 18 80', req(0x18, 0x80))
    run('table 18 82', req(0x18, 0x82))
    run('config 0a', req(0x0a))
    run('02', req(0x02))
    run('lighting 07 01', req(0x07, 0x01))
    run('lighting 08 01', req(0x08, 0x01))
    for sub in (0x20, 0x80, 0x81):
        run(f'rgb 09 {sub:02x}', req(0x09, sub))
    run('keys 21 04 00', req(0x21, 0, 0, 0, 0x18, 0x04, 0x00))
    keys = 0
    for row in range(1, 7):                       # 21 00 00 00 18 05 ROW COL  = read per-key block at (row, col)
        for col in range(0, 16):
            replies = run(f'keys 21 05 r{row} c{col}', req(0x21, 0, 0, 0, 0x18, 0x05, row, col))
            if replies and any(replies[0][5:11]):
                keys += 1
    print('per-key blocks with data:', keys, flush=True)
    run('keys 21 09', req(0x21, 0, 0, 0, 0x01, 0x09, 0x00))
    run('keys 21 11', req(0x21, 0, 0, 0, 0x00, 0x11, 0x00))
    run('25 00', req(0x25, 0x00))
    run('25 02', req(0x25, 0x02))
    run('26 00', req(0x26, 0x00))
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    json.dump({'device': '2e3c:c365', 'time': time.strftime('%F %T'), 'log': log}, open(out_path, 'w'), indent=1)
    print('saved', out_path, len(log), 'requests')


if __name__ == '__main__':
    main()
