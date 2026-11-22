"""Yenkee YKB 30 Odyssey (Telink 320f:5055) protocol driver.

Protocol notes: docs/odyssey-protocol.md. Summary:
  64-byte frames on interface 1, report ID 0x04 (usage page 0xFF1C):
  [0]=0x04 [1..2]=sum(bytes[3..63]) LE [3]=cmd [4]=len [5..6]=offset LE [7]=status(0 ok, 0xff error) [8..]=data
  Every write: back up the area once per session, write, verify by read-back.
"""
from __future__ import annotations

import contextlib
import glob
import os
import select
import time
from dataclasses import dataclass
from keyboardlight.i18n import _

VID, PID = 0x320F, 0x5055
CHUNK = 0x38

CMD_BEGIN, CMD_END = 0x01, 0x02
CMD_INFO = 0x03
CMD_CFG_READ, CMD_CFG_WRITE = 0x05, 0x06
CMD_KEYMAP_DEFAULT = 0x07
CMD_KEYMAP_READ, CMD_KEYMAP_WRITE = 0x08, 0x09
CMD_COLORS_READ, CMD_COLORS_WRITE = 0x0A, 0x0B
CMD_MACRO_WRITE = 0x15

CFG_BLOCK = 0x40          # flash block that is erased by a write at offset 0
KEYMAP_SIZE = 0x180       # 128 slots x 3 B
COLORS_SIZE = 0x180       # 128 slots x RGB
SLOTS = 128

BACKUP_DIR = os.path.expanduser('~/.local/share/keyboardlight/backups/odyssey')


class OdysseyError(RuntimeError):
    pass


def frame(cmd: int, length: int = 0, offset: int = 0, data: bytes = b'') -> bytes:
    b = bytearray(64)
    b[0] = 0x04
    b[3] = cmd
    b[4] = length
    b[5] = offset & 0xFF
    b[6] = offset >> 8
    b[8:8 + len(data)] = data
    cs = sum(b[3:]) & 0xFFFF
    b[1], b[2] = cs & 0xFF, cs >> 8
    return bytes(b)


def find_hidraw() -> str | None:
    """hidraw node of the config interface (descriptor contains usage page 0xFF1C)."""
    want = f'HID_ID=0003:{VID:08X}:{PID:08X}'
    for p in sorted(glob.glob('/sys/class/hidraw/hidraw*')):
        dev = os.path.realpath(p + '/device')
        try:
            if want not in open(dev + '/uevent').read():
                continue
            if b'\x06\x1c\xff' in open(dev + '/report_descriptor', 'rb').read():
                return '/dev/' + os.path.basename(p)
        except OSError:
            continue
    return None


@dataclass
class Lighting:
    effect: int
    brightness: int        # 0..4
    speed: int             # 0 fastest .. 4 slowest
    direction: int         # 0 = left->right, 1 = right->left
    rainbow: bool
    color: tuple[int, int, int]

    @classmethod
    def from_block(cls, b: bytes) -> 'Lighting':
        return cls(effect=b[1], brightness=b[2], speed=b[3], direction=1 if b[4] else 0,
                   rainbow=bool(b[5]), color=(b[6], b[7], b[8]))

    def apply_to(self, block: bytearray) -> None:
        block[1] = self.effect
        block[2] = max(0, min(4, self.brightness))
        block[3] = max(0, min(4, self.speed))
        block[4] = 0xFF if self.direction else 0x00
        block[5] = 0xFF if self.rainbow else 0x00
        block[6:9] = bytes(self.color)


class Odyssey:
    name = 'Yenkee YKB 30 Odyssey'

    def __init__(self, path: str | None = None):
        self.path = path or find_hidraw()
        if not self.path:
            raise OdysseyError(_('Klávesnice Odyssey nenalezena (je připojená kabelem v režimu USB?)'))
        try:
            self.fd = os.open(self.path, os.O_RDWR)
        except PermissionError as e:
            raise OdysseyError(_('Nemám přístup k {path} – chybí udev pravidlo (udev/70-keyboardlight.rules)').format(path=self.path)) from e
        self._backed_up: set[str] = set()

    def close(self) -> None:
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    # ---- transport -------------------------------------------------------
    def _xfer(self, cmd: int, length: int = 0, offset: int = 0, data: bytes = b'') -> bytes:
        while select.select([self.fd], [], [], 0)[0]:     # drop stale input (key reports etc.)
            os.read(self.fd, 64)
        os.write(self.fd, frame(cmd, length, offset, data))
        deadline = time.monotonic() + 1.0
        while True:
            left = deadline - time.monotonic()
            if left <= 0 or not select.select([self.fd], [], [], left)[0]:
                raise OdysseyError(_('klávesnice neodpověděla na příkaz {cmd}').format(cmd=f'{cmd:#04x}'))
            rep = os.read(self.fd, 64)
            if len(rep) >= 8 and rep[0] == 0x04 and rep[3] == cmd and (rep[5] | rep[6] << 8) == offset:
                break
        if rep[7] != 0:
            raise OdysseyError(_('klávesnice odmítla příkaz {cmd}').format(cmd=f'{cmd:#04x}'))
        return rep

    @contextlib.contextmanager
    def session(self):
        self._xfer(CMD_BEGIN)
        try:
            yield
        finally:
            self._xfer(CMD_END)

    def _read(self, cmd: int, size: int) -> bytes:
        out = bytearray()
        for off in range(0, size, CHUNK):
            n = min(CHUNK, size - off)
            out += self._xfer(cmd, n, off)[8:8 + n]
        return bytes(out)

    def _write(self, cmd: int, data: bytes) -> None:
        for off in range(0, len(data), CHUNK):
            chunk = data[off:off + CHUNK]
            self._xfer(cmd, len(chunk), off, chunk)

    def _backup(self, area: str, data: bytes) -> None:
        if area in self._backed_up:
            return
        os.makedirs(BACKUP_DIR, exist_ok=True)
        path = os.path.join(BACKUP_DIR, time.strftime(f'{area}_%Y%m%d_%H%M%S.bin'))
        with open(path, 'wb') as f:
            f.write(data)
        self._backed_up.add(area)

    # ---- device info -----------------------------------------------------
    def info(self) -> bytes:
        with self.session():
            return self._read(CMD_INFO, 0x22)

    # ---- lighting (config block) -----------------------------------------
    def read_config_block(self) -> bytes:
        with self.session():
            return self._read(CMD_CFG_READ, CFG_BLOCK)

    def read_lighting(self) -> Lighting:
        return Lighting.from_block(self.read_config_block())

    def write_lighting(self, light: Lighting) -> None:
        with self.session():
            block = bytearray(self._read(CMD_CFG_READ, CFG_BLOCK))
            self._backup('config', bytes(block))
            light.apply_to(block)
            # write at offset 0 erases the flash block -> always rewrite the whole block
            self._xfer(CMD_CFG_WRITE, CHUNK, 0, bytes(block[:CHUNK]))
            self._xfer(CMD_CFG_WRITE, CFG_BLOCK - CHUNK, CHUNK, bytes(block[CHUNK:]))
            if self._read(CMD_CFG_READ, CFG_BLOCK) != bytes(block):
                raise OdysseyError(_('ověření nastavení podsvícení selhalo'))

    # ---- per-key colours (effect 19) -------------------------------------
    def read_key_colors(self) -> list[tuple[int, int, int]]:
        with self.session():
            d = self._read(CMD_COLORS_READ, COLORS_SIZE)
        return [tuple(d[i:i + 3]) for i in range(0, COLORS_SIZE, 3)]

    def write_key_colors(self, colors: list[tuple[int, int, int]]) -> None:
        data = b''.join(bytes(c) for c in colors[:SLOTS]).ljust(COLORS_SIZE, b'\0')
        with self.session():
            self._backup('keycolors', self._read(CMD_COLORS_READ, COLORS_SIZE))
            self._write(CMD_COLORS_WRITE, data)
            if self._read(CMD_COLORS_READ, COLORS_SIZE) != data:
                raise OdysseyError(_('ověření barev kláves selhalo'))

    # ---- key map ---------------------------------------------------------
    def read_keymaps(self) -> tuple[list[bytes], list[bytes]]:
        """(default map, active map), each 128 entries of 3 bytes."""
        with self.session():
            dflt = self._read(CMD_KEYMAP_DEFAULT, KEYMAP_SIZE)
            active = self._read(CMD_KEYMAP_READ, KEYMAP_SIZE)
        split = lambda d: [d[i:i + 3] for i in range(0, KEYMAP_SIZE, 3)]
        return split(dflt), split(active)

    def write_keymap(self, entries: list[bytes]) -> None:
        data = b''.join(entries)
        if len(data) != KEYMAP_SIZE:
            raise ValueError('key map must have 128 entries of 3 bytes')
        with self.session():
            self._backup('keymap', self._read(CMD_KEYMAP_READ, KEYMAP_SIZE))
            self._write(CMD_KEYMAP_WRITE, data)
            if self._read(CMD_KEYMAP_READ, KEYMAP_SIZE) != data:
                raise OdysseyError(_('ověření mapy kláves selhalo'))

    # ---- macros (write only – the keyboard has no known read command) -----
    def write_macros(self, block: bytes) -> None:
        from keyboardlight.devices.odyssey_macros import mark_written
        with self.session():
            self._write(CMD_MACRO_WRITE, block)
        mark_written(block)
