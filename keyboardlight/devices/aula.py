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

    # ---- lighting (07 main, 08 side strip) ---------------------------------
    # data = [EFFECT][SPEED][BRIGHT][R G B][R2 G2 B2][DIRECTION][RAINBOW][…] – write = same layout, verified
    def read_lighting_raw(self, side: bool = False) -> bytes:
        for rep in self.xfer(bytes([0x08 if side else 0x07, 0x01])):
            if rep[:1] == bytes([0x08 if side else 0x07]) and len(rep) > 5:
                return bytes(rep[5:5 + rep[4]])
        raise AulaError(_('Klávesnice AULA neodpověděla na čtení podsvícení.'))

    def write_lighting_raw(self, data: bytes, side: bool = False) -> None:
        self.xfer(bytes([0x08 if side else 0x07, 0, 0, 0, len(data)]) + bytes(data), first=0.15)
        if self.read_lighting_raw(side)[:len(data)] != bytes(data):
            raise AulaError(_('ověření nastavení podsvícení selhalo'))

    # ---- per-key blocks (actuation) ---------------------------------------
    def read_key_block(self, index: int) -> bytes:
        row, col = divmod(index, 22)
        for rep in self.xfer(bytes([0x21, 0, 0, 0, 0x18, 0x05, row, col]), quiet=0.05):
            if rep[:1] == b'\x21' and len(rep) > 12:
                return bytes(rep[5:17])      # length byte under-reports; the block is 12 bytes
        return b''

    @staticmethod
    def actuation_mm(block: bytes) -> float | None:
        """block = [05][mode][trig lo][…][…][…][trig hi] -> trigger travel in mm (AulaControl)."""
        if len(block) < 7:
            return None
        return ((block[6] << 8) | block[2]) / 100

    # ---- per-key custom colours (effect 10), 0x18c-byte buffer, index*3 = R G B --------------
    COLORS_LEN, COLORS_CHUNK = 0x18C, 0x36

    def read_custom_colors(self, slot: int = 0) -> bytes:
        buf = bytearray(self.COLORS_LEN)
        for rep in self.xfer(bytes([0x09, 0x80 if slot == 0 else 0x81])):
            if rep[:1] != b'\x09' or len(rep) < 5:
                continue
            chunk, n = (rep[2] << 8) | rep[3], rep[4]
            buf[chunk * self.COLORS_CHUNK:chunk * self.COLORS_CHUNK + n] = rep[5:5 + n]
        return bytes(buf)

    def write_custom_colors(self, buf: bytes, slot: int = 0) -> None:
        """Note: the keyboard switches to the custom-colour effect (10) when colours are written."""
        buf = bytes(buf).ljust(self.COLORS_LEN, b'\0')[:self.COLORS_LEN]
        for chunk, off in enumerate(range(0, self.COLORS_LEN, self.COLORS_CHUNK)):
            part = buf[off:off + self.COLORS_CHUNK]
            self.xfer(bytes([0x09, slot, chunk >> 8, chunk & 0xFF, len(part)]) + part, first=0.15)
        if self.read_custom_colors(slot) != buf:
            raise AulaError(_('ověření barev kláves selhalo'))


def backup_areas(path: str) -> dict:
    """Pull restorable areas out of a tools/aula_backup.py JSON file."""
    import json
    log = json.load(open(path))['log']
    out = {}
    for e in log:
        rx = [bytes.fromhex(x) for x in e['rx']]
        if e['label'] == 'lighting 07 01' and rx:
            out['light'] = rx[0][5:5 + rx[0][4]]
        elif e['label'] == 'lighting 08 01' and rx:
            out['side'] = rx[0][5:5 + rx[0][4]]
        elif e['label'] in ('rgb 09 80', 'rgb 09 81'):
            buf = bytearray(Aula.COLORS_LEN)
            for rep in rx:
                if rep[:1] == b'\x09' and len(rep) >= 5:
                    c, n = (rep[2] << 8) | rep[3], rep[4]
                    buf[c * Aula.COLORS_CHUNK:c * Aula.COLORS_CHUNK + n] = rep[5:5 + n]
            out['colors0' if e['label'].endswith('80') else 'colors1'] = bytes(buf)
    return out


def full_backup(dev: 'Aula', out_path: str) -> str:
    """Read-only backup: replays the official driver's connect-time reads (see tools/aula_backup.py)."""
    import json
    log = []

    def run(label, payload):
        replies = dev.xfer(payload)
        log.append({'label': label, 'tx': bytes(payload).hex(' '), 'rx': [r.hex(' ') for r in replies]})

    for _i in range(2):
        run('info 0d', bytes([0x0d]))
    for label, payload in [('status 01', [0x01]), ('fixed 0e', [0x0e])] + \
            [(f'table 19 {s_:02x}', [0x19, s_]) for s_ in range(0x80, 0x8a)] + \
            [('table 22 80', [0x22, 0x80]), ('24 02', [0x24, 0x02]), ('24 01', [0x24, 0x01]),
             ('table 18 80', [0x18, 0x80]), ('table 18 82', [0x18, 0x82]), ('config 0a', [0x0a]), ('02', [0x02]),
             ('lighting 07 01', [0x07, 0x01]), ('lighting 08 01', [0x08, 0x01]),
             ('rgb 09 20', [0x09, 0x20]), ('rgb 09 80', [0x09, 0x80]), ('rgb 09 81', [0x09, 0x81]),
             ('keys 21 04 00', [0x21, 0, 0, 0, 0x18, 0x04, 0x00])]:
        run(label, bytes(payload))
    for row in range(0, 7):
        for col in range(0, 22):
            run(f'keys 21 05 r{row} c{col}', bytes([0x21, 0, 0, 0, 0x18, 0x05, row, col]))
    for label, payload in [('keys 21 09', [0x21, 0, 0, 0, 0x01, 0x09, 0]), ('keys 21 11', [0x21, 0, 0, 0, 0, 0x11, 0]),
                           ('25 00', [0x25, 0]), ('25 02', [0x25, 2]), ('26 00', [0x26, 0])]:
        run(label, bytes(payload))
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, 'w') as fh:
        json.dump({'device': '2e3c:c365', 'time': time.strftime('%F %T'), 'log': log}, fh, indent=1)
    return out_path


BACKUP_DIR = os.path.expanduser('~/.local/share/keyboardlight/backups/aula')


def restore(dev: 'Aula', path: str) -> list[str]:
    """Write back the areas we know how to write (lighting, side strip, per-key colours), verified."""
    areas = backup_areas(path)
    done = []
    # per-key colours first: writing them switches the keyboard to the custom-colour effect,
    # so the lighting block (with the original effect) must be written afterwards
    for slot, key in ((0, 'colors0'), (1, 'colors1')):
        if key in areas and dev.read_custom_colors(slot) != areas[key]:
            dev.write_custom_colors(areas[key], slot)
            done.append(_('barvy kláves'))
    if 'light' in areas and dev.read_lighting_raw() != areas['light']:
        dev.write_lighting_raw(areas['light'])
        done.append(_('podsvícení'))
    if 'side' in areas and dev.read_lighting_raw(True) != areas['side']:
        dev.write_lighting_raw(areas['side'], True)
        done.append(_('boční podsvícení'))
    return done
