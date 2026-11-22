"""Approximate animated preview of the Yenkee Odyssey lighting effects.

Not the firmware's exact maths – a simulation based on what the webcam showed (docs/odyssey-protocol.md),
so the user gets an idea of how an effect, its speed, direction, colour and rainbow option look.
"""
from __future__ import annotations

import colorsys
import math

from PyQt6.QtGui import QColor

from keyboardlight.devices.odyssey_layout import FIXED_COLORS, KEYS

W = max(k.x + k.w for k in KEYS)              # ~16.2 key units
H = 6.25
CX, CY = W / 2, H / 2
SPEED = [2.2, 1.6, 1.1, 0.75, 0.5]           # speed byte 0 (fastest) .. 4 (slowest) -> relative tempo
REACTIVE = {7, 8, 9}


def _centre(k):
    return k.x + k.w / 2, k.y + 0.5


def _hash(n: int) -> float:
    """deterministic pseudo-random 0..1"""
    n = (n * 2654435761) & 0xFFFFFFFF
    n ^= n >> 15
    n = (n * 2246822519) & 0xFFFFFFFF
    n ^= n >> 13
    return (n & 0xFFFF) / 0xFFFF


def _rgb(h: float, v: float = 1.0) -> tuple[float, float, float]:
    return colorsys.hsv_to_rgb(h % 1.0, 1.0, max(0.0, min(1.0, v)))


def frame(light, t: float, presses: list[tuple[int, float]]) -> dict[int, QColor]:
    """Colours of all keys at time t (seconds). presses = [(slot, time_pressed)] for reactive effects."""
    eff = light.effect
    v = SPEED[max(0, min(4, light.speed))]
    sgn = -1 if light.direction else 1
    rainbow = light.rainbow or eff in FIXED_COLORS
    base = tuple(c / 255 for c in light.color)
    gain = light.brightness / 4

    def col(h, val=1.0):
        if rainbow:
            return _rgb(h, val)
        return tuple(c * max(0.0, min(1.0, val)) for c in base)

    out: dict[int, QColor] = {}
    for k in KEYS:
        x, y = _centre(k)
        c = (0.0, 0.0, 0.0)
        if eff == 6:                                            # static
            c = col(x / W)
        elif eff == 1:                                          # wave: rainbow / band travelling sideways
            ph = x / W - sgn * t * v * 0.25
            c = col(ph, 1.0) if rainbow else col(0, 0.25 + 0.75 * (0.5 + 0.5 * math.sin(2 * math.pi * ph)))
        elif eff == 4:                                          # spectrum: whole board cycles hue
            c = _rgb(t * v * 0.08)
        elif eff == 5:                                          # breathing
            c = col(x / W + t * 0.02, 0.5 - 0.5 * math.cos(t * v * 1.6))
        elif eff == 2:                                          # cloud: soft blobs drifting sideways
            ph = x / W * 2 - sgn * t * v * 0.3
            val = 0.5 + 0.5 * math.sin(2 * math.pi * ph) * math.cos(y / H * math.pi)
            c = col(ph * 0.5, val)
        elif eff == 3:                                          # serpentine: snake along rows
            row = int(y)
            pos = (x if row % 2 == 0 else W - x) + row * W
            ph = pos / (W * 2) - sgn * t * v * 0.4
            c = col(ph, 0.35 + 0.65 * (0.5 + 0.5 * math.sin(2 * math.pi * ph * 3)))
        elif eff == 11:                                         # flowers: colourful spots blooming
            n = int(t * v * 0.8)
            val = 0.0
            for i in range(n - 3, n + 1):
                fx, fy = _hash(i * 7 + 1) * W, _hash(i * 7 + 2) * H
                age = t * v * 0.8 - i
                if 0 <= age < 4:
                    d = math.hypot(x - fx, (y - fy) * 1.3)
                    val = max(val, max(0.0, 1 - abs(d - age * 1.5) / 1.5) * (1 - age / 4))
            c = _rgb(x / W + t * 0.1, 0.3 + 0.7 * val)
        elif eff == 10:                                         # stars: random twinkles
            per = 1.5 + 2 * _hash(k.slot)
            ph = (t * v + _hash(k.slot + 999) * per) % per / per
            val = max(0.0, math.sin(math.pi * ph * 3)) if ph < 1 / 3 else 0.0
            c = col(_hash(k.slot + int(t * v / per) * 131), val)
        elif eff == 12:                                         # rows: colour rows rolling up/down
            c = _rgb(y / H * 0.8 - sgn * t * v * 0.2)
        elif eff == 13:                                         # waving: sine line travelling right
            line = CY + 2.4 * math.sin(x / W * 2 * math.pi - t * v * 2)
            c = col(x / W + t * 0.05, max(0.0, 1 - abs(y - line) / 0.9))
        elif eff == 14:                                         # circles: rings expanding at random places
            n = int(t * v * 0.7)
            val = 0.0
            for i in range(n - 2, n + 1):
                fx, fy = _hash(i * 5 + 3) * W, _hash(i * 5 + 4) * H
                r = (t * v * 0.7 - i) * 3.0
                d = math.hypot(x - fx, (y - fy) * 1.2)
                val = max(val, max(0.0, 1 - abs(d - r) / 0.7) * max(0.0, 1 - r / 6))
            c = col(_hash(n) + x / W * 0.3, val)
        elif eff == 15:                                         # rain: drops falling down columns
            colx = int(x)
            per = 2.5 + 2 * _hash(colx)
            drop = ((t * v * 2 + _hash(colx + 50) * per * 3) % (per * 3)) - 1
            val = max(0.0, 1 - abs(y - drop) / 1.2) if y <= drop + 0.6 else 0.0
            c = col(colx / W, val)
        elif eff == 16:                                         # scan: slanted line sweeping left->right
            span = W + 6
            pos = (t * v * 3) % (span + 4) - 3
            d = x + (y - CY) * 0.8 - pos
            c = col(x / W, max(0.0, 1 - abs(d) / 0.9))
        elif eff == 17:                                         # transition reaction: white
            c = (0.92, 0.92, 0.92)
        elif eff == 18:                                         # centre transition (always rainbow)
            if light.rainbow:                                   # rings from the centre out / in
                d = math.hypot((x - CX) / W * 2, (y - CY) / H * 1.2)
                c = _rgb(d - sgn * t * v * 0.25)
            else:                                               # rainbow flowing sideways
                c = _rgb(abs(x - CX) / W - sgn * t * v * 0.25)
        elif eff in REACTIVE:
            val = 0.0
            for slot, tp in presses:
                age = t - tp
                if age < 0:
                    continue
                pk = next((p for p in KEYS if p.slot == slot), None)
                if pk is None:
                    continue
                px, py = _centre(pk)
                if eff == 7:                                    # reaction: pressed key lights and fades
                    if slot == k.slot:
                        val = max(val, max(0.0, 1 - age * v * 0.8))
                elif eff == 8:                                  # ripples: ring from the pressed key
                    r = age * v * 6
                    d = math.hypot(x - px, (y - py) * 1.2)
                    val = max(val, max(0.0, 1 - abs(d - r) / 0.8) * max(0.0, 1 - r / 12))
                elif eff == 9:                                  # traverse: light runs along the row
                    if abs(y - py) < 0.6:
                        r = age * v * 8
                        val = max(val, max(0.0, 1 - abs(abs(x - px) - r) / 1.0) * max(0.0, 1 - r / 16))
            c = col(_hash(int(x)) if light.rainbow else 0, val)
        if eff == 20:
            continue
        r, g, b = (max(0.0, min(1.0, ch * gain)) for ch in c)
        if r + g + b > 0.02:
            out[k.slot] = QColor(int(r * 255), int(g * 255), int(b * 255))
    return out
