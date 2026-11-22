"""Character -> (HID usage, modifier mask) tables for ANY system keyboard layout, via libxkbcommon.

A macro sends key codes; the OS layout turns them into characters. To type a given text we need the
reverse mapping for the layout the user actually has. libxkbcommon (part of every Linux desktop)
compiles the layout and we enumerate keys x levels (plain / Shift / AltGr / Shift+AltGr).
"""
from __future__ import annotations

import ctypes
import ctypes.util
import functools
import os
import subprocess

from keyboardlight.devices.odyssey_layout import EVDEV_TO_HID

SHIFT, ALTGR = 0x02, 0x40      # key-map / macro modifier bits (L Shift, R Alt)


class _RuleNames(ctypes.Structure):
    _fields_ = [('rules', ctypes.c_char_p), ('model', ctypes.c_char_p), ('layout', ctypes.c_char_p),
                ('variant', ctypes.c_char_p), ('options', ctypes.c_char_p)]


@functools.lru_cache(maxsize=1)
def _lib():
    name = ctypes.util.find_library('xkbcommon') or 'libxkbcommon.so.0'
    try:
        lib = ctypes.CDLL(name)
    except OSError:
        return None
    lib.xkb_context_new.restype = ctypes.c_void_p
    lib.xkb_context_new.argtypes = [ctypes.c_int]
    lib.xkb_keymap_new_from_names.restype = ctypes.c_void_p
    lib.xkb_keymap_new_from_names.argtypes = [ctypes.c_void_p, ctypes.POINTER(_RuleNames), ctypes.c_int]
    lib.xkb_keymap_num_levels_for_key.restype = ctypes.c_uint32
    lib.xkb_keymap_num_levels_for_key.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32]
    lib.xkb_keymap_key_get_syms_by_level.restype = ctypes.c_int
    lib.xkb_keymap_key_get_syms_by_level.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32,
                                                     ctypes.c_uint32, ctypes.POINTER(ctypes.POINTER(ctypes.c_uint32))]
    lib.xkb_keymap_key_get_mods_for_level.restype = ctypes.c_size_t
    lib.xkb_keymap_key_get_mods_for_level.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32,
                                                      ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32), ctypes.c_size_t]
    lib.xkb_keymap_mod_get_index.restype = ctypes.c_uint32
    lib.xkb_keymap_mod_get_index.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    lib.xkb_keysym_to_utf32.restype = ctypes.c_uint32
    lib.xkb_keysym_to_utf32.argtypes = [ctypes.c_uint32]
    lib.xkb_keymap_unref.argtypes = [ctypes.c_void_p]
    lib.xkb_context_unref.argtypes = [ctypes.c_void_p]
    return lib


def available() -> bool:
    return _lib() is not None


@functools.lru_cache(maxsize=32)
def char_table(layout: str, variant: str = '') -> dict[str, tuple[int, int]]:
    """{character: (HID usage, modifier mask)} for an xkb layout; empty dict if it cannot be compiled."""
    lib = _lib()
    if lib is None:
        return {}
    ctx = lib.xkb_context_new(0)
    names = _RuleNames(b'evdev', b'pc105', layout.encode(), variant.encode(), b'')
    km = lib.xkb_keymap_new_from_names(ctx, ctypes.byref(names), 0)
    table: dict[str, tuple[int, int]] = {}
    if not km:
        lib.xkb_context_unref(ctx)
        return table
    shift_bit = 1 << lib.xkb_keymap_mod_get_index(km, b'Shift')
    mod5 = lib.xkb_keymap_mod_get_index(km, b'Mod5')            # ISO_Level3_Shift (AltGr)
    altgr_bit = 1 << mod5 if mod5 < 32 else 0
    syms = ctypes.POINTER(ctypes.c_uint32)()
    masks = (ctypes.c_uint32 * 8)()
    for evdev, hid in EVDEV_TO_HID.items():
        if 0x54 <= hid <= 0x63 or hid == 0x58:                  # skip numpad: not on the keyboard, NumLock-dependent
            continue
        kc = evdev + 8
        for level in range(lib.xkb_keymap_num_levels_for_key(km, kc, 0)):
            if lib.xkb_keymap_key_get_syms_by_level(km, kc, 0, level, ctypes.byref(syms)) < 1:
                continue
            ch = lib.xkb_keysym_to_utf32(syms[0])
            if not ch:
                continue
            ch = chr(ch)
            n = lib.xkb_keymap_key_get_mods_for_level(km, kc, 0, level, masks, len(masks))
            best = None
            for i in range(n):
                m = masks[i]
                if m & ~(shift_bit | altgr_bit):
                    continue                                    # needs another modifier (Ctrl, Lock…) – skip
                mods = (SHIFT if m & shift_bit else 0) | (ALTGR if m & altgr_bit else 0)
                if best is None or (bin(mods).count('1'), mods != SHIFT) < (bin(best).count('1'), best != SHIFT):
                    best = mods
            if best is None:
                continue
            prev = table.get(ch)
            if prev is None or (bin(best).count('1'), best != SHIFT) < (bin(prev[1]).count('1'), prev[1] != SHIFT):
                table[ch] = (hid, best)
    for ch, code in (('\n', 0x28), ('\t', 0x2B)):
        table.setdefault(ch, (code, 0))
    lib.xkb_keymap_unref(km)
    lib.xkb_context_unref(ctx)
    return table


def system_layouts() -> list[tuple[str, str]]:
    """Layouts configured in the desktop: [(layout, variant), …], first = default."""
    out: list[tuple[str, str]] = []
    try:
        conf = open(os.path.expanduser('~/.config/kxkbrc'), encoding='utf-8').read()
        lay = var = ''
        for line in conf.splitlines():
            if line.startswith('LayoutList='):
                lay = line.split('=', 1)[1]
            elif line.startswith('VariantList='):
                var = line.split('=', 1)[1]
        vs = var.split(',')
        out = [(l.strip(), (vs[i] if i < len(vs) else '').strip()) for i, l in enumerate(lay.split(',')) if l.strip()]
    except OSError:
        pass
    if not out:
        try:
            r = subprocess.run(['localectl', 'status'], capture_output=True, text=True, timeout=3)
            for line in r.stdout.splitlines():
                if 'X11 Layout:' in line:
                    out = [(l.strip(), '') for l in line.split(':', 1)[1].split(',') if l.strip()]
        except (OSError, subprocess.SubprocessError):
            pass
    return out or [('us', '')]
