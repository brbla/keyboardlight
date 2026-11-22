"""AULA WIN60 / WIN68 / WIN75 HE (Standard edition, 2e3c:c365) – minimal driver.

Protocol notes: docs/aula-protocol.md (based on https://github.com/sgtflixy/AulaControl, Apache-2.0).
Config channel: interface with usage page 0xFF1B, report ID 1, 63-byte payloads:
  [CMD] [SUB] [00] [IDX] [LEN] [data…]   – multi-packet replies, IDX = packet number.
"""
from __future__ import annotations

import glob
import os
import re
import select
import time
from dataclasses import dataclass

from keyboardlight.i18n import _

VID, PID = 0x2E3C, 0xC365


class AulaError(RuntimeError):
    pass


def find_hidraw() -> str | None:
    want = f'HID_ID=0003:{VID:08X}:{PID:08X}'
    for p in sorted(glob.glob('/sys/class/hidraw/hidraw*')):
        dev = os.path.realpath(p + '/device')
        try:
            if want in open(dev + '/uevent').read() and \
                    b'\x06\x1b\xff' in open(dev + '/report_descriptor', 'rb').read():
                return '/dev/' + os.path.basename(p)
        except OSError:
            continue
    return None


@dataclass
class AulaInfo:
    model: str          # e.g. "W669"
    chip: str           # e.g. "SI2828HEARGB"
    version: str        # e.g. "V3.14.29"
    build: str          # e.g. "Jul  2 2025,14:52:56"
    raw: str

    @property
    def name(self) -> str:
        return {'W669': 'AULA WIN68 HE'}.get(self.model, f'AULA {self.model}')


class Aula:
    def __init__(self, path: str | None = None):
        self.path = path or find_hidraw()
        if not self.path:
            raise AulaError(_('Klávesnice AULA nenalezena.'))
        try:
            self.fd = os.open(self.path, os.O_RDWR)
        except PermissionError as e:
            raise AulaError(_('Nemám přístup k {path} – chybí udev pravidlo (udev/70-keyboardlight.rules)')
                            .format(path=self.path)) from e

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def xfer(self, payload: bytes, first: float = 0.6, quiet: float = 0.12) -> list[bytes]:
        while select.select([self.fd], [], [], 0)[0]:
            os.read(self.fd, 64)
        os.write(self.fd, b'\x01' + bytes(payload).ljust(63, b'\0'))
        out, deadline = [], time.monotonic() + first
        while True:
            r, _w, _x = select.select([self.fd], [], [], max(0.0, deadline - time.monotonic()))
            if not r:
                return out
            rep = os.read(self.fd, 64)
            out.append(rep[1:] if rep[:1] == b'\x01' else rep)
            deadline = time.monotonic() + quiet

    def info(self) -> AulaInfo:
        texts = []
        for _attempt in range(3):            # 0d returns model / build date alternately (FIFO cursor)
            for rep in self.xfer(bytes([0x0D])):
                if rep[:1] == b'\x0d' and len(rep) > 5:
                    texts.append(rep[5:5 + rep[4]].split(b'\0')[0].decode('ascii', 'replace'))
            if any(',' in t and t.count(',') >= 4 for t in texts):
                break
        ident = next((t for t in texts if t.count(',') >= 4), '')
        build = next((t for t in texts if re.match(r'[A-Z][a-z]{2} ', t)), '')
        parts = ident.split(',')
        if len(parts) < 6:
            raise AulaError(_('Klávesnice AULA nevrátila informace o firmwaru.'))
        return AulaInfo(model=parts[0], chip=parts[4], version=parts[5], build=build, raw=ident)
