"""AULA WIN68 HE layout (65 %, 68 keys). Slot = the firmware's key index = row * 22 + col.

Positions were derived from the board itself: exactly 68 matrix positions carry a real per-key
actuation block (rows 1-5); column numbers match the WIN60 HE table in AulaControl for the shared keys.
Labels of the right-hand column are the usual WIN68 ones.
"""
from __future__ import annotations

from keyboardlight.devices.odyssey_layout import Key
from keyboardlight.i18n import _

COLS = 22


def _row(y, items):
    keys, x = [], 0.0
    for col_row, label, w in items:
        row, col = col_row
        keys.append(Key(row * COLS + col, label, x, y, w))
        x += w
    return keys


KEYS: list[Key] = (
    _row(0, [((1, 0), 'Esc', 1)] + [((1, i), str(i % 10), 1) for i in range(1, 11)]
         + [((1, 11), '-', 1), ((1, 12), '=', 1), ((1, 14), 'Backspace', 2), ((1, 16), 'Del', 1)])
    + _row(1, [((2, 0), 'Tab', 1.5)] + [((2, i), c, 1) for i, c in enumerate('QWERTYUIOP[]', 1)]
           + [((2, 14), '\\', 1.5), ((2, 16), 'PgUp', 1)])
    + _row(2, [((3, 0), 'Caps', 1.75)] + [((3, i), c, 1) for i, c in enumerate("ASDFGHJKL;'", 2)]
           + [((3, 14), 'Enter', 2.25), ((3, 16), 'PgDn', 1)])
    + _row(3, [((4, 0), 'Shift', 2.25)] + [((4, i), c, 1) for i, c in enumerate('ZXCVBNM,./', 2)]
           + [((4, 13), 'Shift', 1.75), ((4, 15), '↑', 1), ((4, 16), 'End', 1)])
    + _row(4, [((5, 0), 'Ctrl', 1.25), ((5, 1), 'Win', 1.25), ((5, 2), 'Alt', 1.25), ((5, 6), '', 6.25),
               ((5, 9), 'Alt', 1), ((5, 11), 'Fn', 1), ((5, 12), 'Ctrl', 1),
               ((5, 14), '←', 1), ((5, 15), '↓', 1), ((5, 16), '→', 1)])
)
KEY_BY_SLOT = {k.slot: k for k in KEYS}
WIDTH_U, HEIGHT_U = 16.0, 5.0

EFFECTS = [  # (wire id, name) – ids recovered by AulaControl from the official driver
    (0, _('Statické')), (1, _('Dýchání')), (2, _('Vlnění')), (3, _('Neon')), (4, _('Radar')),
    (6, _('Reakce na stisk')), (7, _('Polární záře')), (8, _('Vlnky')), (9, _('Třpyt')),
    (10, _('Vlastní barvy kláves')), (11, _('Kříž')), (12, _('Reakce na rychlost psaní')),
    (14, _('Automatické vlnky')), (15, _('Pruhy')), (16, _('Ohňostroj')),
]
EFFECT_CUSTOM = 10
