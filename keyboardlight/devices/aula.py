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

    # ---- actuation write: 21 00 00 00 18 [mode] [22-byte key bitmask] … [28] press lo [29] release lo
    #      [30] RT press sensitivity [31] RT release sensitivity [32] press hi [33] release hi
    #      bitmask: byte 6+col, bit = row (index = row*22+col); mode 0x0d = rapid trigger on, 0x0c = off
    def write_actuation(self, indices, rapid: bool, press_mm: float, release_mm: float,
                        rt_press_mm: float, rt_release_mm: float) -> None:
        f = bytearray(63)
        f[0:5] = bytes([0x21, 0, 0, 0, 0x18])
        f[5] = 0x0D if rapid else 0x0C
        for idx in indices:
            row, col = divmod(idx, 22)
            f[6 + col] |= 1 << row
        p, r = round(press_mm * 100), round(release_mm * 100)
        f[28], f[29], f[32], f[33] = p & 0xFF, r & 0xFF, p >> 8, r >> 8
        f[30], f[31] = round(rt_press_mm * 100), round(rt_release_mm * 100)
        self.xfer(bytes(f), first=0.3)
        for idx in indices:
            b = self.read_key_block(idx)
            if self.decode_actuation(b) != (rapid, p / 100, r / 100, f[30] / 100, f[31] / 100):
                raise AulaError(_('ověření nastavení spínačů selhalo'))

    @staticmethod
    def decode_actuation(block: bytes):
        """(rapid trigger on, press mm, release mm, RT press mm, RT release mm) from a 12-byte key block."""
        if len(block) < 8:
            return None
        return (bool(block[1] & 1), ((block[6] << 8) | block[2]) / 100, ((block[7] << 8) | block[3]) / 100,
                block[4] / 100, block[5] / 100)

    # ---- SOCD (cmd 24, "Prcs" in the official driver) ------------------------------------------
    # read 24 01 -> 2 packets [24 01 00 i 28] + 10 slots × [enabled][mode][hid1][hid2]; 24 02 -> data[0] = on/off
    # write 24 00 00 i 28 + 10 slots (2 packets, max 20 pairs); 24 03 00 00 01 [0/1] = global switch
    SOCD_MODES = 4

    def read_socd(self) -> tuple[bool, list[tuple[int, int, int]]]:
        pairs = []
        for rep in self.xfer(bytes([0x24, 0x01])):
            if rep[:2] != b'\x24\x01' or len(rep) < 45:
                continue
            for slot in range(10):
                en, mode, k1, k2 = rep[5 + 4 * slot:9 + 4 * slot]
                if en == 1:
                    pairs.append((mode, k1, k2))
        on = False
        for rep in self.xfer(bytes([0x24, 0x02])):
            if rep[:2] == b'\x24\x02' and len(rep) > 5:
                on = rep[5] == 1
        return on, pairs

    def write_socd(self, on: bool, pairs: list[tuple[int, int, int]]) -> None:
        if len(pairs) > 20:
            raise AulaError(_('SOCD umí nejvýše 20 párů.'))
        for packet in range(2):
            data = bytearray(40)
            for slot in range(10):
                i = packet * 10 + slot
                if i < len(pairs):
                    mode, k1, k2 = pairs[i]
                    data[4 * slot:4 * slot + 4] = bytes([1, mode, k1, k2])
            self.xfer(bytes([0x24, 0x00, 0x00, packet, 0x28]) + bytes(data), first=0.3)
        self.xfer(bytes([0x24, 0x03, 0x00, 0x00, 0x01, 1 if on else 0]), first=0.3)
        if self.read_socd() != (on, list(pairs)):
            raise AulaError(_('ověření nastavení SOCD selhalo'))

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
        elif e['label'] == '24 01':
            pairs = []
            for rep in rx:
                if rep[:2] == b'\x24\x01' and len(rep) >= 45:
                    for slot in range(10):
                        en, mode, k1, k2 = rep[5 + 4 * slot:9 + 4 * slot]
                        if en == 1:
                            pairs.append((mode, k1, k2))
            out['socd_pairs'] = pairs
        elif e['label'] == '24 02' and rx and len(rx[0]) > 5:
            out['socd_on'] = rx[0][5] == 1
        elif e['label'].startswith('keys 21 05 r') and rx and len(rx[0]) > 16:
            lab = e['label'].split()
            out.setdefault('keys', {})[int(lab[3][1:]) * 22 + int(lab[4][1:])] = rx[0][5:17]
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
    """Write back everything we know how to write from a backup file (verified)."""
    return apply_areas(dev, backup_areas(path))


def capture(dev: 'Aula') -> dict:
    """Current restorable state (same keys as backup_areas) – fast: only the 68 real keys."""
    from keyboardlight.devices.aula_layout import KEYS
    on, pairs = dev.read_socd()
    return {'light': dev.read_lighting_raw(), 'side': dev.read_lighting_raw(True),
            'colors0': dev.read_custom_colors(0), 'colors1': dev.read_custom_colors(1),
            'keys': {k.slot: dev.read_key_block(k.slot) for k in KEYS}, 'socd_on': on, 'socd_pairs': pairs}


def areas_to_json(a: dict) -> dict:
    out = {}
    for k, v in a.items():
        if isinstance(v, (bytes, bytearray)):
            out[k] = bytes(v).hex()
        elif k == 'keys':
            out[k] = {str(i): bytes(b).hex() for i, b in v.items()}
        elif k == 'socd_pairs':
            out[k] = [list(p) for p in v]
        else:
            out[k] = v
    return out


def areas_from_json(d: dict) -> dict:
    out = {}
    for k, v in d.items():
        if k in ('light', 'side', 'colors0', 'colors1'):
            out[k] = bytes.fromhex(v)
        elif k == 'keys':
            out[k] = {int(i): bytes.fromhex(b) for i, b in v.items()}
        elif k == 'socd_pairs':
            out[k] = [tuple(p) for p in v]
        else:
            out[k] = v
    return out


def apply_areas(dev: 'Aula', areas: dict) -> list[str]:
    """Write the given areas to the keyboard, only where they differ; every write is verified."""
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
    # the WIN68 HE has no side light strip: its 08 block exists but writes are ignored – skip quietly
    if 'socd_pairs' in areas and 'socd_on' in areas:
        want = (areas['socd_on'], areas['socd_pairs'])
        if dev.read_socd() != want:
            dev.write_socd(*want)
            done.append('SOCD')
    if 'keys' in areas:
        from keyboardlight.devices.aula_layout import KEYS
        groups: dict = {}
        for k in KEYS:
            want = Aula.decode_actuation(areas['keys'].get(k.slot, b''))
            if want and Aula.decode_actuation(dev.read_key_block(k.slot)) != want:
                groups.setdefault(want, []).append(k.slot)
        for (rapid, p, r, rp, rr), idx in groups.items():
            dev.write_actuation(idx, rapid, p, r, rp, rr)
        if groups:
            done.append(_('spínače ({n} kláves)').format(n=sum(len(v) for v in groups.values())))
    return done
