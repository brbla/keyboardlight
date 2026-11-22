"""Named profiles (presets) for the Odyssey: lighting, per-key colours, key map + macros.

Stored in ~/.config/keyboardlight/odyssey_profiles.json. Applying a profile writes only the areas
that differ from what the keyboard currently has (saves flash wear).
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass

from keyboardlight.devices import odyssey_macros
from keyboardlight.devices.odyssey import Lighting, Odyssey
from keyboardlight.devices.odyssey_macros import Macro, MacroEvent
from keyboardlight.i18n import _

STORE = os.path.expanduser('~/.config/keyboardlight/odyssey_profiles.json')


@dataclass
class Profile:
    name: str
    lighting: dict                        # Lighting fields
    key_colors: list | None = None        # 128 x [r, g, b]
    keymap: list | None = None            # 128 x hex string (3 bytes)
    macros: list | None = None            # [{'name':…, 'events':[…]}], stored together with keymap

    def summary(self) -> str:
        parts = [_('podsvícení')]
        if self.key_colors is not None:
            parts.append(_('barvy kláves'))
        if self.keymap is not None:
            parts.append(_('klávesy a makra'))
        return ', '.join(parts)


def load_all() -> list[Profile]:
    try:
        data = json.load(open(STORE, encoding='utf-8'))
    except (OSError, ValueError):
        return []
    return [Profile(**p) for p in data.get('profiles', [])]


def save_all(profiles: list[Profile]) -> None:
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    tmp = STORE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump({'profiles': [asdict(p) for p in profiles]}, f, ensure_ascii=False, indent=1)
    os.replace(tmp, STORE)


def capture(name: str, light: Lighting, key_colors=None, keymap=None, macros: list[Macro] | None = None) -> Profile:
    return Profile(
        name=name,
        lighting={**asdict(light), 'color': list(light.color)},
        key_colors=[list(c) for c in key_colors] if key_colors is not None else None,
        keymap=[bytes(e).hex() for e in keymap] if keymap is not None else None,
        macros=[{'name': m.name, 'events': [asdict(e) for e in m.events]} for m in macros]
        if keymap is not None and macros is not None else None,
    )


def profile_macros(p: Profile) -> list[Macro] | None:
    if p.macros is None:
        return None
    return [Macro(m['name'], [MacroEvent(**e) for e in m['events']]) for m in p.macros]


def apply(dev: Odyssey, p: Profile) -> list[str]:
    """Write the profile to the keyboard; returns list of areas actually written."""
    written = []
    want = Lighting(**{**p.lighting, 'color': tuple(p.lighting['color'])})
    if dev.read_lighting() != want:
        dev.write_lighting(want)
        written.append(_('podsvícení'))
    if p.key_colors is not None:
        cols = [tuple(c) for c in p.key_colors]
        if dev.read_key_colors() != cols:
            dev.write_key_colors(cols)
            written.append(_('barvy kláves'))
    if p.keymap is not None:
        macros = profile_macros(p)
        if macros is not None:
            # the keyboard cannot report macros back -> compare with a hash of the last block written
            block = odyssey_macros.build_block(macros)
            if not odyssey_macros.is_written(block):
                dev.write_macros(block)
                written.append('makra')
            odyssey_macros.save(macros)
        km = [bytes.fromhex(h) for h in p.keymap]
        if dev.read_keymaps()[1] != km:
            dev.write_keymap(km)
            written.append(_('mapa kláves'))
    return written
