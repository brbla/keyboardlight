#!/usr/bin/env python3
"""Extract Odyssey/EVision config frames (64 B, report 0x04, valid checksum) from a usbmon pcapng.

usage: pcap_frames.py file.pcapng [--all]   (--all: also print device replies)
No tshark needed: minimal pcapng parser, frames are found as the last 64 bytes of each packet.
"""
import struct, sys


def packets(path):
    d = open(path, 'rb').read()
    i, le = 0, '<'
    linktypes = []
    while i + 12 <= len(d):
        btype, blen = struct.unpack_from(le + 'II', d, i)
        if btype == 0x0A0D0D0A:                      # section header
            le = '<' if d[i + 8:i + 12] == b'\x4d\x3c\x2b\x1a' else '>'
            btype, blen = struct.unpack_from(le + 'II', d, i)
        elif btype == 1:                             # interface description
            linktypes.append(struct.unpack_from(le + 'H', d, i + 8)[0])
        elif btype == 6:                             # enhanced packet
            ifid, th, tl, caplen, _ = struct.unpack_from(le + 'IIIII', d, i + 8)
            yield ((th << 32) | tl), d[i + 28:i + 28 + caplen]
        if blen < 12:
            break
        i += blen


def frame_of(pkt):
    if len(pkt) < 64:
        return None
    f = pkt[-64:]
    if f[0] != 0x04:
        return None
    cs = sum(f[3:]) & 0xFFFF
    if f[1] | (f[2] << 8) != cs:
        return None
    return f


if __name__ == '__main__':
    show_all = '--all' in sys.argv
    seen_out = set()
    t0 = None
    for ts, pkt in packets(sys.argv[1]):
        f = frame_of(pkt)
        if f is None:
            continue
        # usbmon header byte 8 = 'S' (submit, host->dev) or 'C' (complete, dev->host)
        kind = chr(pkt[8]) if len(pkt) >= 64 + 64 and chr(pkt[8]) in 'SC' else '?'
        if kind == 'C' and not show_all:
            continue
        t0 = t0 or ts
        cmd, ln, off = f[3], f[4], f[5] | (f[6] << 8)
        data = f[8:8 + ln] if ln <= 56 else f[8:]
        print(f'{(ts - t0) / 1e6:8.3f} {kind} cmd={cmd:02x} len={ln:02x} off={off:04x} b7={f[7]:02x} | '
              + ' '.join(f'{b:02x}' for b in data))
