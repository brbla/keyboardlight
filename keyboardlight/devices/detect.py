"""Cheap detection of connected keyboards from sysfs (never talks to the devices)."""
from __future__ import annotations

import glob
import os

# (kind, HID_ID prefix, how) – the config interface is checked by usage page where it matters
_SIGNATURES = [
    ('odyssey', 'HID_ID=0003:0000320F:00005055', 'usb'),
    ('odyssey', 'HID_ID=0003:0000320F:00005088', '2.4g'),
    ('odyssey', 'HID_ID=0005:0000320F:00005055', 'bt'),
    ('aula', 'HID_ID=0003:00002E3C:0000C365', 'usb'),
]
_RANK = {'usb': 0, '2.4g': 1, 'bt': 2}


def connected() -> dict[str, str]:
    """{'odyssey': 'usb'|'2.4g'|'bt', 'aula': 'usb'} for keyboards that are present right now."""
    found: dict[str, str] = {}
    for p in glob.glob('/sys/class/hidraw/hidraw*'):
        try:
            ue = open(os.path.realpath(p + '/device') + '/uevent').read()
        except OSError:
            continue
        for kind, sig, how in _SIGNATURES:
            if sig in ue and (kind not in found or _RANK[how] < _RANK[found[kind]]):
                found[kind] = how
    return found
