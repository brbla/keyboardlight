"""Named profiles for the AULA WIN68 HE: lighting, per-key colours, actuation/rapid trigger, SOCD.

Stored in ~/.config/keyboardlight/aula_profiles.json; applying writes only what differs (verified).
"""
from __future__ import annotations

import json
import os

from keyboardlight.devices.aula import Aula, apply_areas, areas_from_json, areas_to_json, capture

STORE = os.path.expanduser('~/.config/keyboardlight/aula_profiles.json')


def load_all() -> dict[str, dict]:
    try:
        return json.load(open(STORE, encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def _save_all(data: dict) -> None:
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    tmp = STORE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, STORE)


def save(dev: Aula, name: str) -> None:
    data = load_all()
    data[name] = areas_to_json(capture(dev))
    _save_all(data)


def delete(name: str) -> None:
    data = load_all()
    data.pop(name, None)
    _save_all(data)


def apply(dev: Aula, name: str) -> list[str]:
    return apply_areas(dev, areas_from_json(load_all()[name]))


def label(name: str, d: dict) -> str:
    from keyboardlight.devices.aula_layout import EFFECTS
    from keyboardlight.i18n import _
    light = bytes.fromhex(d.get('light', '00'))
    names = dict(EFFECTS)
    eff = names.get(light[0], str(light[0])) if light else '?'
    return f'{name} – ' + _('{effect}, jas {b}').format(effect=eff, b=light[2] if len(light) > 2 else '?')
