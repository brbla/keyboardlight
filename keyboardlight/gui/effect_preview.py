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
CLOUD_PERIOD = [0.33, 0.6, 0.95, 1.25, 1.6]   # seconds per flash, speed byte 0 (fastest) .. 4 (measured 0, 2, 4)


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
        elif eff == 2:                                          # cloud (30 fps camera measurements)
            period = CLOUD_PERIOD[max(0, min(4, light.speed))]
            if rainbow:                                         # whole board slowly cycles through the hues
                c = _rgb(t * 0.135 / period + x / W * 0.08)
            else:                                               # repeated flash sweeping across, dark in between
                xx = x / W if sgn > 0 else 1 - x / W
                local = (t - xx * 0.3 * period) % period
                dur = 0.55 * period
                c = col(0, math.sin(math.pi * local / dur) ** 2 if local < dur else 0.0)
        elif eff == 3:                                          # serpentine: snake along rows
            row = int(y)
            pos = (x if row % 2 == 0 else W - x) + row * W
            ph = pos / (W * 2) - sgn * t * v * 0.4
            c = col(ph, 0.35 + 0.65 * (0.5 + 0.5 * math.sin(2 * math.pi * ph * 3)))
        elif eff == 11:                                         # flowers: every key lit, own colour drifting
            h = _hash(k.slot) + t * v * 0.12 * (0.6 + 0.8 * _hash(k.slot + 77))
            h += 0.08 * math.sin(t * v * (0.8 + _hash(k.slot + 5)) * 2 * math.pi / 3)
            c = _rgb(h)
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


EDGE_SEGMENTS = 160


def edge_frame(mode: int, t: float, brightness: int) -> list[QColor] | None:
    """Colours of the edge strip (underglow), EDGE_SEGMENTS points around the case starting at the bottom middle
    and going clockwise. Approximation of what the webcam and the user saw (docs/odyssey-protocol.md)."""
    if mode is None or mode >= 6 or brightness <= 0:
        return None
    gain = brightness / 4
    out = []
    for i in range(EDGE_SEGMENTS):
        s = i / EDGE_SEGMENTS
        u = min(s, 1 - s) * 2                       # 0 = bottom middle, 1 = top middle (symmetric)
        val = 1.0
        if mode == 0:                               # rainbow flowing around
            h = s - t * 0.12
        elif mode == 1:                             # one colour, slowly changing
            h = t * 0.04
        elif mode == 2:                             # pulsing
            h = 0.6 - 0.25 * u
            val = 0.5 - 0.5 * math.cos(t * 1.6)
        elif mode == 3:                             # static gradient
            h = 0.62 - 0.3 * u
        elif mode == 4:                             # rainbow running symmetrically up and down
            h = u * 0.8 - t * 0.3
        else:                                       # 5: rainbow rotating around, fixed spacing
            h = s * 3 - t * 0.5
        r, g, b = _rgb(h, val * gain)
        out.append(QColor(int(r * 255), int(g * 255), int(b * 255)))
    return out
