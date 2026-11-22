"""Physical layout of the Odyssey (ANSI 75 %, 82 keys + knob) and key-map encoding helpers.

Slot index (= LED index = key-map index) is row * 15 + col of the firmware matrix.
Key-map entry (3 B): 20 mm uu = keyboard (mm modifier mask, uu HID usage),
                     30 lo hi = consumer usage, a0 xx 00 = special (Fn, knob rotation).
"""
from __future__ import annotations

from dataclasses import dataclass
from keyboardlight.i18n import _


@dataclass(frozen=True)
class Key:
    slot: int
    label: str
    x: float      # position in key units
    y: float
    w: float = 1.0
    round: bool = False


def _row(y, items, x0=0.0):
    keys, x = [], x0
    for it in items:
        if it is None:                 # gap of 0.25 u
            x += 0.25
            continue
        slot, label, w = (it + (1.0,))[:3] if len(it) == 2 else it
        keys.append(Key(slot, label, x, y, w))
        x += w
    return keys


KEYS: list[Key] = (
    _row(0, [(0, 'Esc'), None, (1, 'F1'), (2, 'F2'), (3, 'F3'), (4, 'F4'), None,
             (5, 'F5'), (6, 'F6'), (7, 'F7'), (8, 'F8'), None,
             (9, 'F9'), (10, 'F10'), (11, 'F11'), (12, 'F12'), (13, 'Del')])
    + [Key(14, '◉', 15.15, -0.1, 1.0, round=True)]
    + _row(1.25, [(15, '`'), (16, '1'), (17, '2'), (18, '3'), (19, '4'), (20, '5'), (21, '6'), (22, '7'),
                  (23, '8'), (24, '9'), (25, '0'), (26, '-'), (27, '='), (28, 'Backspace', 2.0), (29, 'Home')])
    + _row(2.25, [(30, 'Tab', 1.5), (31, 'Q'), (32, 'W'), (33, 'E'), (34, 'R'), (35, 'T'), (36, 'Y'), (37, 'U'),
                  (38, 'I'), (39, 'O'), (40, 'P'), (41, '['), (42, ']'), (43, '\\', 1.5), (44, 'End')])
    + _row(3.25, [(45, 'Caps', 1.75), (46, 'A'), (47, 'S'), (48, 'D'), (49, 'F'), (50, 'G'), (51, 'H'),
                  (52, 'J'), (53, 'K'), (54, 'L'), (55, ';'), (56, "'"), (58, 'Enter', 2.25), (59, 'PgUp')])
    + _row(4.25, [(60, 'Shift', 2.25), (62, 'Z'), (63, 'X'), (64, 'C'), (65, 'V'), (66, 'B'), (67, 'N'),
                  (68, 'M'), (69, ','), (70, '.'), (71, '/'), (72, 'Shift', 1.75), (73, '↑'), (74, 'PgDn')])
    + _row(5.25, [(75, 'Ctrl', 1.25), (76, 'Win', 1.25), (77, 'Alt', 1.25), (81, '', 6.25), (84, 'Alt'),
                  (85, 'Fn'), (86, 'Ctrl'), (87, '←'), (88, '↓'), (89, '→')])
)
KEY_BY_SLOT = {k.slot: k for k in KEYS}
WIDTH_U, HEIGHT_U = 16.25, 6.25
FN_SLOT = 85
KNOB_SLOTS = {14: _('stisk knoflíku'), 118: _('knoflík ←'), 119: _('knoflík →')}

# ---- effects (byte 0x01 of the config block) ------------------------------
EFFECTS = [  # value, Czech name, note
    (6, _('Statické'), ''), (1, _('Vlnění'), ''), (4, _('Spektrum'), ''), (5, _('Dýchání'), ''), (2, _('Mrak'), ''),
    (3, _('Serpentýna'), ''), (8, _('Vlnky'), _('reaguje na stisk')), (7, _('Reakce na stisk'), _('reaguje na stisk')),
    (9, _('Přechod'), _('reaguje na stisk')), (11, _('Květiny'), ''), (10, _('Hvězdy'), ''), (12, _('Řádky'), ''),
    (13, _('Mávání'), ''), (14, _('Kulatá animace'), ''), (15, _('Déšť'), ''), (16, _('Skenovat'), ''),
    (17, _('Přechodová reakce'), ''), (18, _('Přechod ze středu'), ''),
    (19, _('Vlastní barvy kláves'), ''), (20, _('Vypnuto'), ''),
]
EFFECT_CUSTOM = 19
EFFECT_OFF = 20
NO_SPEED = {6, 17, 18, EFFECT_CUSTOM, EFFECT_OFF}   # static, or speed has no visible effect (webcam-verified, 30 fps)
FIXED_COLORS = {4, 11, 12, 17, 18}                # own colours; colour + rainbow ignored (webcam-verified)
WITH_DIRECTION = {1, 2, 3, 12, 18}             # webcam-verified; labels for direction 00 / ff:
EDGE_MODES = [  # config byte 0x1B – edge strip around the case (webcam-verified 2026-11-22)
    (0, _('Duha plynule dokola (tovární)')), (1, _('Jedna barva, pomalu se mění')), (2, _('Pulzování')),
    (3, _('Statický barevný přechod')), (4, _('Duha běží symetricky nahoru a dolů')), (5, _('Duha rotuje dokola')),
    (6, _('Vypnuto')),
]
DIRECTION_LABELS = {
    12: (_('Shora dolů'), _('Zdola nahoru')),
    18: (_('Ze středu ven'), _('Do středu')),
    3: (_('Jedním směrem'), _('Opačným směrem')),
}                                              # others: left→right / right→left
PRESET_COLORS = ['#ff0000', '#ff6000', '#ffff00', '#00ff00', '#00ffff', '#0000ff', '#8000ff',
                 '#ff00ff', '#ff0080', '#ffa000', '#80ff80', '#40ffff', '#004080', '#ffffff']

# ---- HID usages -----------------------------------------------------------
HID_NAMES: dict[int, str] = {0x04 + i: chr(ord('A') + i) for i in range(26)}
HID_NAMES.update({0x1E + i: str((i + 1) % 10) for i in range(10)})
HID_NAMES.update({0x3A + i: f'F{i + 1}' for i in range(12)})
HID_NAMES.update({
    0x28: 'Enter', 0x29: 'Esc', 0x2A: 'Backspace', 0x2B: 'Tab', 0x2C: _('Mezerník'), 0x2D: '-', 0x2E: '=',
    0x2F: '[', 0x30: ']', 0x31: '\\', 0x32: '# (ISO)', 0x33: ';', 0x34: "'", 0x35: '`', 0x36: ',', 0x37: '.',
    0x38: '/', 0x39: 'CapsLock', 0x46: 'PrintScreen', 0x47: 'ScrollLock', 0x48: 'Pause', 0x49: 'Insert',
    0x4A: 'Home', 0x4B: 'PageUp', 0x4C: 'Delete', 0x4D: 'End', 0x4E: 'PageDown', 0x4F: _('Šipka →'),
    0x50: _('Šipka ←'), 0x51: _('Šipka ↓'), 0x52: _('Šipka ↑'), 0x53: 'NumLock', 0x54: 'Num /', 0x55: 'Num *',
    0x56: 'Num -', 0x57: 'Num +', 0x58: 'Num Enter', 0x59: 'Num 1', 0x5A: 'Num 2', 0x5B: 'Num 3',
    0x5C: 'Num 4', 0x5D: 'Num 5', 0x5E: 'Num 6', 0x5F: 'Num 7', 0x60: 'Num 8', 0x61: 'Num 9', 0x62: 'Num 0',
    0x63: 'Num .', 0x64: '\\ (ISO)', 0x65: 'Menu', 0x68: 'F13', 0x69: 'F14', 0x6A: 'F15', 0x6B: 'F16',
    0x6C: 'F17', 0x6D: 'F18', 0x6E: 'F19', 0x6F: 'F20', 0x70: 'F21', 0x71: 'F22', 0x72: 'F23', 0x73: 'F24',
})
MODIFIERS = [(0x01, 'L Ctrl'), (0x02, 'L Shift'), (0x04, 'L Alt'), (0x08, 'L Win'),
             (0x10, 'R Ctrl'), (0x20, 'R Shift'), (0x40, 'R Alt'), (0x80, 'R Win')]
CONSUMER = {0x00CD: _('Přehrát/Pauza'), 0x00B5: _('Další skladba'), 0x00B6: _('Předchozí skladba'), 0x00B7: _('Stop'),
            0x00E2: _('Ztlumit'), 0x00E9: _('Hlasitost +'), 0x00EA: _('Hlasitost -'), 0x0183: _('Přehrávač'),
            0x018A: 'E-mail', 0x0192: _('Kalkulačka'), 0x0194: _('Tento počítač'), 0x0223: _('Prohlížeč – domů'),
            0x0221: _('Hledat'), 0x006F: _('Jas obrazovky +'), 0x0070: _('Jas obrazovky -')}

# Linux evdev key code -> HID usage (Qt nativeScanCode() == evdev + 8 on Linux)
EVDEV_TO_HID = {
    1: 0x29, **{2 + i: 0x1E + i for i in range(10)}, 12: 0x2D, 13: 0x2E, 14: 0x2A, 15: 0x2B,
    16: 0x14, 17: 0x1A, 18: 0x08, 19: 0x15, 20: 0x17, 21: 0x1C, 22: 0x18, 23: 0x0C, 24: 0x12, 25: 0x13,
    26: 0x2F, 27: 0x30, 28: 0x28, 30: 0x04, 31: 0x16, 32: 0x07, 33: 0x09, 34: 0x0A, 35: 0x0B, 36: 0x0D,
    37: 0x0E, 38: 0x0F, 39: 0x33, 40: 0x34, 41: 0x35, 43: 0x31, 44: 0x1D, 45: 0x1B, 46: 0x06, 47: 0x19,
    48: 0x05, 49: 0x11, 50: 0x10, 51: 0x36, 52: 0x37, 53: 0x38, 55: 0x55, 57: 0x2C, 58: 0x39,
    **{59 + i: 0x3A + i for i in range(10)}, 69: 0x53, 70: 0x47, 71: 0x5F, 72: 0x60, 73: 0x61, 74: 0x56,
    75: 0x5C, 76: 0x5D, 77: 0x5E, 78: 0x57, 79: 0x59, 80: 0x5A, 81: 0x5B, 82: 0x62, 83: 0x63, 86: 0x64,
    87: 0x44, 88: 0x45, 96: 0x58, 98: 0x54, 99: 0x46, 102: 0x4A, 103: 0x52, 104: 0x4B, 105: 0x50,
    106: 0x4F, 107: 0x4D, 108: 0x51, 109: 0x4E, 110: 0x49, 111: 0x4C, 119: 0x48, 127: 0x65,
}
EVDEV_MODIFIER = {29: 0x01, 42: 0x02, 56: 0x04, 125: 0x08, 97: 0x10, 54: 0x20, 100: 0x40, 126: 0x80}


def keyboard_entry(usage: int, mods: int = 0) -> bytes:
    return bytes([0x20, mods & 0xFF, usage & 0xFF])


def consumer_entry(usage: int) -> bytes:
    return bytes([0x30, usage & 0xFF, usage >> 8])


DISABLED_ENTRY = bytes([0x20, 0x00, 0x00])


def macro_entry(index: int, mode: int = 0, times: int | None = None) -> bytes:
    """70 ii mm = macro ii in mode mm (0..3); 71 ii nn = play nn times."""
    if times is not None:
        return bytes([0x71, index & 0xFF, max(1, min(255, times))])
    return bytes([0x70, index & 0xFF, mode & 0x03])


def describe(entry: bytes) -> str:
    t, a, b = entry
    if t == 0x20:
        mods = [n for m, n in MODIFIERS if a & m]
        if b == 0:
            return ' + '.join(mods) if mods else _('vypnuto')
        return ' + '.join(mods + [HID_NAMES.get(b, f'HID {b:#04x}')])
    if t == 0x30:
        u = a | b << 8
        return CONSUMER.get(u, _('multimédia {code}').format(code=f'{u:#06x}'))
    if t == 0x70:
        return _('makro {n}').format(n=a + 1) + ('' if b == 0 else _(' (režim {m})').format(m=b))
    if t == 0x71:
        return f'makro {a + 1} ×{b}'
    if entry == b'\xa0\x01\x00':
        return 'Fn'
    return _('speciální ({raw})').format(raw=entry.hex(' '))
