"""Battery level of the Odyssey over Bluetooth LE (standard GATT Battery Service, exposed by BlueZ).

Only available while the keyboard is connected over Bluetooth (the USB cable / 2.4 GHz receiver report no
battery). BlueZ publishes it as org.bluez.Battery1.Percentage on the device object; the keyboard is identified
by its Modalias usb:v320Fp5055.
"""
from __future__ import annotations

import re
import shutil
import subprocess

MODALIAS = 'usb:v320Fp5055'


def _busctl(*args: str) -> str:
    r = subprocess.run(['busctl', '--system', *args], capture_output=True, text=True, timeout=5)
    return r.stdout if r.returncode == 0 else ''


def bluetooth_battery() -> int | None:
    """Battery percentage of a connected Odyssey over Bluetooth, or None."""
    if not shutil.which('busctl'):
        return None
    tree = _busctl('tree', '--list', 'org.bluez')
    for path in re.findall(r'^(/org/bluez/hci\d+/dev_[0-9A-F_]+)$', tree, re.M):
        alias = _busctl('get-property', 'org.bluez', path, 'org.bluez.Device1', 'Modalias')
        if MODALIAS.lower() not in alias.lower():
            continue
        if 'true' not in _busctl('get-property', 'org.bluez', path, 'org.bluez.Device1', 'Connected'):
            continue
        out = _busctl('get-property', 'org.bluez', path, 'org.bluez.Battery1', 'Percentage')   # "y 67"
        m = re.match(r'y (\d+)', out.strip())
        if m:
            return int(m.group(1))
    return None
