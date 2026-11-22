"""Odyssey macros: data model, binary block encoding and local storage.

The app keeps the macros (with their names) in ~/.config/keyboardlight/odyssey_macros.json and writes the
whole block; the keyboard can report the block back (command 0x14, verified), names are not stored there.
Format: docs/odyssey-protocol.md, section "Macros".
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
from dataclasses import asdict, dataclass, field

from keyboardlight.devices.odyssey_layout import HID_NAMES, MODIFIERS
from keyboardlight.i18n import _

TYPE_MOUSE, TYPE_HWHEEL, TYPE_MODS, TYPE_KEY = 0x01, 0x02, 0x09, 0x0A
STORE = os.path.expanduser('~/.config/keyboardlight/odyssey_macros.json')
WRITTEN = os.path.expanduser('~/.config/keyboardlight/odyssey_macros.written')   # sha256 of last block sent
MAX_EVENTS = 256          # vendor limit per macro
MODES = [  # (key-map type, mode byte, label)
    (0x70, 0, _('Jednou při stisku')),
    (0x70, 1, _('Opakovat, dokud je klávesa držena')),
    (0x70, 2, _('Přepínač: stisk spustí / další stisk zastaví')),
    (0x70, 3, _('Opakovat při držení, po puštění ihned stop')),
    (0x71, None, _('Přehrát N-krát')),
]
MOUSE_BUTTONS = {0x01: _('levé tlačítko myši'), 0x02: _('pravé tlačítko myši'), 0x04: _('prostřední tlačítko myši'),
                 0x08: _('tlačítko myši zpět'), 0x10: _('tlačítko myši vpřed')}


@dataclass
class MacroEvent:
    type: int          # TYPE_KEY / TYPE_MODS / TYPE_MOUSE ...
    code: int
    down: bool
    delay: int = 20    # ms after this event

    def encode(self) -> bytes:
        return struct.pack('<HBB', max(0, min(0xFFFF, self.delay)),
                           (self.type & 0x7F) | (0x80 if self.down else 0), self.code & 0xFF)

    def label(self) -> str:
        if self.type == TYPE_KEY:
            return HID_NAMES.get(self.code, f'HID {self.code:#04x}')
        if self.type == TYPE_MODS:
            return ' + '.join(n for m, n in MODIFIERS if self.code & m) or _('modifikátor')
        if self.type == TYPE_MOUSE:
            return MOUSE_BUTTONS.get(self.code, _('myš {code}').format(code=f'{self.code:#04x}'))
        return f'typ {self.type:#04x} kód {self.code:#04x}'


@dataclass
class Macro:
    name: str
    events: list[MacroEvent] = field(default_factory=list)


def build_block(macros: list[Macro]) -> bytes:
    n = len(macros)
    start = 0x10 + 2 * n
    offsets, body = [], b''
    for m in macros:
        offsets.append(start + len(body))
        body += struct.pack('<HH', len(m.events), 0) + b''.join(e.encode() for e in m.events[:MAX_EVENTS])
    total = start + len(body)
    head = struct.pack('<HHH', 0x55AA, total, n).ljust(0x10, b'\0')
    return head + b''.join(struct.pack('<H', o) for o in offsets) + body


def parse_block(block: bytes, names: list[str] | None = None) -> list[Macro] | None:
    """Inverse of build_block. None if the area does not hold a valid macro block (e.g. after a factory reset)."""
    if len(block) < 0x10 or struct.unpack_from('<H', block)[0] != 0x55AA:
        return None
    total, n = struct.unpack_from('<HH', block, 2)
    if total > len(block) or 0x10 + 2 * n > total:
        return None
    macros = []
    for i in range(n):
        off = struct.unpack_from('<H', block, 0x10 + 2 * i)[0]
        if off + 4 > total:
            return None
        count = struct.unpack_from('<H', block, off)[0]
        evs = []
        for j in range(min(count, MAX_EVENTS)):
            p = off + 4 + 4 * j
            if p + 4 > total:
                return None
            delay, t, code = struct.unpack_from('<HBB', block, p)
            evs.append(MacroEvent(type=t & 0x7F, code=code, down=bool(t & 0x80), delay=delay))
        name = names[i] if names and i < len(names) else _('Makro {n}').format(n=i + 1)
        macros.append(Macro(name, evs))
    return macros


# ---- text -> events -----------------------------------------------------------
# The keyboard sends key codes; the character that appears depends on the OS keyboard layout.
SHIFT, ALTGR = 0x02, 0x40
_LETTERS = {chr(ord('a') + i): 0x04 + i for i in range(26)}


def _us() -> dict[str, tuple[int, int]]:
    m = {c: (u, 0) for c, u in _LETTERS.items()}
    m.update({c.upper(): (u, SHIFT) for c, u in _LETTERS.items()})
    m.update({str((i + 1) % 10): (0x1E + i, 0) for i in range(10)})
    plain = {' ': 0x2C, '\n': 0x28, '\t': 0x2B, '-': 0x2D, '=': 0x2E, '[': 0x2F, ']': 0x30, '\\': 0x31,
             ';': 0x33, "'": 0x34, '`': 0x35, ',': 0x36, '.': 0x37, '/': 0x38}
    m.update({c: (u, 0) for c, u in plain.items()})
    shifted = {'!': 0x1E, '@': 0x1F, '#': 0x20, '$': 0x21, '%': 0x22, '^': 0x23, '&': 0x24, '*': 0x25, '(': 0x26,
               ')': 0x27, '_': 0x2D, '+': 0x2E, '{': 0x2F, '}': 0x30, '|': 0x31, ':': 0x33, '"': 0x34, '~': 0x35,
               '<': 0x36, '>': 0x37, '?': 0x38}
    m.update({c: (u, SHIFT) for c, u in shifted.items()})
    return m


def _cz(qwerty: bool) -> dict[str, tuple[int, int]]:
    letters = dict(_LETTERS)
    if not qwerty:                       # QWERTZ: Y and Z swapped
        letters['y'], letters['z'] = 0x1D, 0x1C
    m = {c: (u, 0) for c, u in letters.items()}
    m.update({c.upper(): (u, SHIFT) for c, u in letters.items()})
    m.update({str((i + 1) % 10): (0x1E + i, SHIFT) for i in range(10)})   # digits need Shift on CZ
    plain = {' ': 0x2C, '\n': 0x28, '\t': 0x2B, ';': 0x35, '+': 0x1E, 'ě': 0x1F, 'š': 0x20, 'č': 0x21, 'ř': 0x22,
             'ž': 0x23, 'ý': 0x24, 'á': 0x25, 'í': 0x26, 'é': 0x27, '=': 0x2D, 'ú': 0x2F, ')': 0x30, 'ů': 0x33,
             '§': 0x34, ',': 0x36, '.': 0x37, '-': 0x38, '\\': 0x64}
    m.update({c: (u, 0) for c, u in plain.items()})
    shifted = {'%': 0x2D, '/': 0x2F, '(': 0x30, '"': 0x33, '!': 0x34, "'": 0x31, '?': 0x36, ':': 0x37, '_': 0x38,
               '|': 0x64}
    m.update({c: (u, SHIFT) for c, u in shifted.items()})
    altgr = {'@': 0x19, '#': 0x1B, '&': 0x06, '{': 0x05, '}': 0x11, '[': 0x09, ']': 0x0A, '$': 0x33, '€': 0x08,
             '~': 0x1E, '<': 0x36, '>': 0x37, '*': 0x38}
    m.update({c: (u, ALTGR) for c, u in altgr.items()})
    return m


BUILTIN = {'cz': _cz(False), 'cz:qwerty': _cz(True), 'us': _us()}   # fallback without libxkbcommon
COMMON_LAYOUTS = ['cz', 'cz:qwerty', 'sk', 'sk:qwerty', 'us', 'gb', 'de', 'at', 'pl', 'hu', 'fr', 'es', 'it',
                  'ua', 'ru']


def layout_table(key: str) -> dict[str, tuple[int, int]]:
    """key = 'layout' or 'layout:variant' (xkb names)."""
    from keyboardlight import xkb_layout
    lay, _sep, var = key.partition(':')
    table = xkb_layout.char_table(lay, var) if xkb_layout.available() else {}
    return table or BUILTIN.get(key) or BUILTIN['us']


def system_layout() -> str:
    from keyboardlight import xkb_layout
    lay, var = xkb_layout.system_layouts()[0]
    return f'{lay}:{var}' if var else lay


def text_to_events(text: str, delay: int = 15, layout: str = 'us') -> tuple[list[MacroEvent], str]:
    """Events typing `text` for the given OS layout. Returns (events, skipped characters)."""
    table = layout_table(layout)
    evs, skipped = [], ''
    for ch in text:
        if ch not in table:
            skipped += ch
            continue
        code, mods = table[ch]
        if mods:
            evs.append(MacroEvent(TYPE_MODS, mods, True, delay))
        evs += [MacroEvent(TYPE_KEY, code, True, delay), MacroEvent(TYPE_KEY, code, False, delay)]
        if mods:
            evs.append(MacroEvent(TYPE_MODS, mods, False, delay))
    return evs, skipped


# ---- storage -----------------------------------------------------------------
def load() -> list[Macro]:
    try:
        data = json.load(open(STORE, encoding='utf-8'))
    except (OSError, ValueError):
        return []
    return [Macro(m['name'], [MacroEvent(**e) for e in m['events']]) for m in data.get('macros', [])]


def save(macros: list[Macro]) -> None:
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    tmp = STORE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump({'macros': [{'name': m.name, 'events': [asdict(e) for e in m.events]} for m in macros]},
                  f, ensure_ascii=False, indent=1)
    os.replace(tmp, STORE)


def mark_written(block: bytes) -> None:
    os.makedirs(os.path.dirname(WRITTEN), exist_ok=True)
    with open(WRITTEN, 'w') as f:
        f.write(hashlib.sha256(block).hexdigest())


def is_written(block: bytes) -> bool:
    try:
        return open(WRITTEN).read().strip() == hashlib.sha256(block).hexdigest()
    except OSError:
        return False
