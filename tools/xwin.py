#!/usr/bin/env python3
"""Tiny X11 (XWayland) automation for the Wine vendor app: list / screenshot / click / type.

usage:
  xwin.py list
  xwin.py shot <title-substr> <out.png> [maxwidth]
  xwin.py click <title-substr> <x> <y> [right|double]     (coords relative to window, in full-size px)
  xwin.py key <title-substr> <keysym> [...]                 e.g. Return, Escape, a
  xwin.py type <title-substr> <text>
"""
import sys, time
from Xlib import X, XK, display
from Xlib.ext import xtest
from PIL import Image

d = display.Display()
root = d.screen().root


def windows():
    out = []

    def walk(w):
        try:
            name = w.get_wm_name()
            attrs = w.get_attributes()
            geo = w.get_geometry()
        except Exception:
            return
        if name and attrs.map_state == X.IsViewable and geo.width > 50:
            out.append((w, name, geo))
        for c in w.query_tree().children:
            walk(c)
    walk(root)
    return out


def find(sub):
    if sub.startswith('0x'):
        w = d.create_resource_object('window', int(sub, 16))
        return w, w.get_geometry()
    for w, name, geo in windows():
        if sub.lower() in name.lower():
            return w, geo
    sys.exit(f'window "{sub}" not found')


def abs_pos(w):
    t = w.translate_coords(root, 0, 0)
    return -t.x, -t.y


def shot(sub, out, maxw=None):
    w, geo = find(sub)
    raw = w.get_image(0, 0, geo.width, geo.height, X.ZPixmap, 0xffffffff)
    im = Image.frombytes('RGB', (geo.width, geo.height), raw.data, 'raw', 'BGRX')
    if maxw and geo.width > int(maxw):
        im = im.resize((int(maxw), int(geo.height * int(maxw) / geo.width)))
    im.save(out)
    print(f'{out} window {geo.width}x{geo.height} saved {im.size[0]}x{im.size[1]}')


def click(sub, x, y, mode='left'):
    w, _ = find(sub)
    ax, ay = abs_pos(w)
    xtest.fake_input(d, X.MotionNotify, x=ax + int(x), y=ay + int(y))
    d.sync(); time.sleep(0.05)
    btn = 3 if mode == 'right' else 1
    for _ in range(2 if mode == 'double' else 1):
        xtest.fake_input(d, X.ButtonPress, btn); d.sync(); time.sleep(0.05)
        xtest.fake_input(d, X.ButtonRelease, btn); d.sync(); time.sleep(0.08)


def send_click(sub, x, y):
    """Synthetic ButtonPress/Release sent straight to the window (works without XTest permission)."""
    from Xlib.protocol import event
    w, _ = find(sub)
    ax, ay = abs_pos(w)
    x, y = int(x), int(y)
    kw = dict(time=X.CurrentTime, root=root, window=w, same_screen=1, child=X.NONE,
              root_x=ax + x, root_y=ay + y, event_x=x, event_y=y)
    w.send_event(event.MotionNotify(detail=0, state=0, **kw), X.PointerMotionMask, propagate=False)
    w.send_event(event.ButtonPress(detail=1, state=0, **kw), X.ButtonPressMask, propagate=False)
    d.sync(); time.sleep(0.06)
    w.send_event(event.ButtonRelease(detail=1, state=X.Button1Mask, **kw), X.ButtonReleaseMask, propagate=False)
    d.sync(); time.sleep(0.1)


def send_key(sub, name):
    """Synthetic KeyPress/Release sent straight to the window."""
    from Xlib.protocol import event
    w, _ = find(sub)
    code = d.keysym_to_keycode(XK.string_to_keysym(name))
    kw = dict(time=X.CurrentTime, root=root, window=w, same_screen=1, child=X.NONE,
              root_x=0, root_y=0, event_x=0, event_y=0, state=0, detail=code)
    w.send_event(event.KeyPress(**kw), X.KeyPressMask, propagate=False)
    d.sync(); time.sleep(0.05)
    w.send_event(event.KeyRelease(**kw), X.KeyReleaseMask, propagate=False)
    d.sync(); time.sleep(0.05)


def key(name):
    code = d.keysym_to_keycode(XK.string_to_keysym(name))
    xtest.fake_input(d, X.KeyPress, code); d.sync(); time.sleep(0.03)
    xtest.fake_input(d, X.KeyRelease, code); d.sync(); time.sleep(0.03)


if __name__ == '__main__':
    c = sys.argv[1]
    if c == 'list':
        for w in root.query_tree().children:
            try:
                a, g = w.get_attributes(), w.get_geometry()
            except Exception:
                continue
            if a.map_state == X.IsViewable and g.width > 50 and g.width < 3000 and not (g.x == 0 and g.y == 0):
                print(hex(w.id), g.width, g.height, abs_pos(w), repr(w.get_wm_name()))
    elif c == 'shot':
        shot(*sys.argv[2:5])
    elif c == 'click':
        click(*sys.argv[2:6])
    elif c == 'sclick':
        send_click(*sys.argv[2:5])
    elif c == 'skey':
        for k in sys.argv[3:]:
            send_key(sys.argv[2], k)
    elif c == 'key':
        find(sys.argv[2])
        for k in sys.argv[3:]:
            key(k)
    elif c == 'type':
        find(sys.argv[2])
        for ch in sys.argv[3]:
            key({' ': 'space'}.get(ch, ch))
