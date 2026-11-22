#!/usr/bin/env python3
"""Capture USB traffic of one device from /dev/usbmonN (binary API, no tshark needed).

usage: usbmon_capture.py <bus> <vid:pid> <outfile.log> [--quiet-input]
  Writes one line per URB: time, S/C, transfer type, endpoint, length, setup, data hex.
  Also decodes Odyssey config frames (report 0x04). --quiet-input hides interrupt-IN key reports.
Device address is looked up from sysfs (and re-looked up if the device is re-plugged).
"""
import fcntl, glob, os, struct, sys, time, ctypes

MON_IOCX_GETX = 0x4018920a
HDR = struct.Struct('<QBBBBHccqiiII8siiII')   # 64 B usbmon_packet
XFER = {0: 'ISO', 1: 'INT', 2: 'CTL', 3: 'BLK'}


def devnum(bus, vidpid):
    vid, pid = vidpid.lower().split(':')
    for d in glob.glob('/sys/bus/usb/devices/*'):
        try:
            if open(d + '/idVendor').read().strip() == vid and open(d + '/idProduct').read().strip() == pid \
                    and int(open(d + '/busnum').read()) == bus:
                return int(open(d + '/devnum').read())
        except OSError:
            pass
    return None


def main():
    bus, vidpid, out = int(sys.argv[1]), sys.argv[2], sys.argv[3]
    quiet = '--quiet-input' in sys.argv
    fd = os.open(f'/dev/usbmon{bus}', os.O_RDONLY)
    hdr = ctypes.create_string_buffer(64)
    data = ctypes.create_string_buffer(4096)
    arg = struct.pack('PPN', ctypes.addressof(hdr), ctypes.addressof(data), 4096)
    argbuf = ctypes.create_string_buffer(arg, len(arg))
    dev, last_lookup = devnum(bus, vidpid), 0
    with open(out, 'a', buffering=1) as log:
        log.write(f'# capture start {time.strftime("%F %T")} bus {bus} dev {dev}\n')
        print(f'capturing bus {bus} dev {dev} -> {out}', flush=True)
        while True:
            fcntl.ioctl(fd, MON_IOCX_GETX, argbuf)
            (_id, typ, xt, ep, dn, _bus, fsetup, _fd, sec, usec, status, length, lcap,
             setup, *_rest) = HDR.unpack(hdr.raw)
            if time.time() - last_lookup > 2:
                dev, last_lookup = devnum(bus, vidpid) or dev, time.time()
            if dn != dev:
                continue
            payload = data.raw[:lcap]
            t = chr(typ)
            if quiet and xt == 1 and ep & 0x80 and t == 'C' and payload[:1] != b'\x04':
                continue
            line = f'{sec}.{usec:06d} {t} {XFER.get(xt, xt)} ep{ep:02x} st={status} len={length}'
            if fsetup == b'\x00' and xt == 2:
                line += ' setup=' + setup.hex(' ')
            if payload:
                line += ' | ' + payload.hex(' ')
                f = payload[-64:] if len(payload) >= 64 else b''
                if f[:1] == b'\x04' and (f[1] | f[2] << 8) == (sum(f[3:]) & 0xffff):
                    line += f'   << cmd={f[3]:02x} len={f[4]:02x} off={f[5] | f[6] << 8:04x} b7={f[7]:02x}'
            log.write(line + '\n')


if __name__ == '__main__':
    main()
