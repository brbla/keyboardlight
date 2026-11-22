"""KDE Plasma global shortcuts: let Ctrl + knob (Ctrl + Volume Up/Down) change the screen brightness.

The knob always sends Volume Up/Down (fixed in firmware), but held modifiers are passed through,
so the desktop can bind Ctrl+Volume to brightness. Uses KGlobalAccel over D-Bus (busctl), which
applies the change immediately and persists it.
"""
from __future__ import annotations

import shutil
import subprocess

COMPONENT = 'org_kde_powerdevil'
CTRL = 0x04000000
KEY_VOL_DOWN, KEY_VOL_UP = 0x01000070, 0x01000072          # Qt::Key_VolumeDown / Key_VolumeUp
ACTIONS = {'Increase Screen Brightness': CTRL | KEY_VOL_UP,
           'Decrease Screen Brightness': CTRL | KEY_VOL_DOWN}


def _busctl(*args: str) -> str:
    r = subprocess.run(['busctl', '--user', 'call', 'org.kde.kglobalaccel', '/kglobalaccel',
                        'org.kde.KGlobalAccel', *args], capture_output=True, text=True, timeout=5)
    if r.returncode:
        raise RuntimeError(r.stderr.strip() or 'busctl failed')
    return r.stdout.strip()


def _get(action: str) -> list[int]:
    out = _busctl('shortcut', 'as', '4', COMPONENT, action, '', '').split()   # "ai N k1 k2 …"
    return [int(x) for x in out[2:]]


def _set(action: str, keys: list[int]) -> None:
    _busctl('setForeignShortcut', 'asai', '4', COMPONENT, action, '', '', str(len(keys)), *map(str, keys))


def available() -> bool:
    if not shutil.which('busctl'):
        return False
    try:
        _get('Increase Screen Brightness')
        return True
    except (RuntimeError, OSError, subprocess.SubprocessError, ValueError):
        return False


def is_enabled() -> bool:
    return all(key in _get(action) for action, key in ACTIONS.items())


def set_enabled(on: bool) -> None:
    for action, key in ACTIONS.items():
        keys = [k for k in _get(action) if k != key]
        if on:
            keys.append(key)
        _set(action, keys)
