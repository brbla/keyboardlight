#!/usr/bin/env python3
"""Cheap text summary of what the keyboard backlight is doing, from the webcam preview frames.

Reads the frame file written by the preview ffmpeg (default $KEYBOARDLIGHT_CAM_FRAME or /tmp/keyboardlight-cam/latest.jpg),
samples it for a few seconds and prints:
  - overall brightness of the keyboard area (lit / dark)
  - grid of dominant colours (rows x cols) as short colour names
  - temporal behaviour: static / blinking-breathing / moving (with horizontal direction)

usage: cam_watch.py [--secs 3] [--roi x0,y0,x1,y1] [--grid 3x8] [--thumb out.png]
"""
import argparse, colorsys, os, time
import numpy as np
from PIL import Image

FRAME = os.environ.get('KEYBOARDLIGHT_CAM_FRAME', '/tmp/keyboardlight-cam/latest.jpg')
ROI = (130, 160, 1260, 560)   # keyboard area in the webcam frame (top-down view)


def load(path):
    for _ in range(5):
        try:
            return np.asarray(Image.open(path).convert('RGB'), dtype=np.float32)
        except Exception:
            time.sleep(0.05)   # file being rewritten
    raise RuntimeError('cannot read frame')


def name(rgb):
    r, g, b = (c / 255 for c in rgb)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    if v < 0.12:
        return 'dark'
    if s < 0.25:
        return 'white' if v > 0.5 else 'grey'
    names = [(15, 'red'), (40, 'orange'), (70, 'yellow'), (160, 'green'), (200, 'cyan'),
             (255, 'blue'), (290, 'purple'), (340, 'pink'), (361, 'red')]
    deg = h * 360
    return next(n for lim, n in names if deg < lim)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--secs', type=float, default=3)
    ap.add_argument('--roi', default=','.join(map(str, ROI)))
    ap.add_argument('--grid', default='6x15')
    ap.add_argument('--frame', default=FRAME)
    ap.add_argument('--thumb', help='also save a small crop of the ROI here')
    a = ap.parse_args()
    x0, y0, x1, y1 = map(int, a.roi.split(','))
    gr, gc = map(int, a.grid.split('x'))

    frames, t_end, last = [], time.time() + a.secs, None
    while time.time() < t_end or len(frames) < 2:
        m = os.path.getmtime(a.frame)
        if m != last:
            last = m
            frames.append(load(a.frame)[y0:y1, x0:x1])
        time.sleep(0.1)
    st = np.stack(frames)                       # T,H,W,3
    T, H, W, _ = st.shape
    lum = st.mean(axis=3)                       # T,H,W

    # background-subtracted "glow": brightest 30 % of pixels per cell
    print(f'frames={T} roi={x0},{y0},{x1},{y1}  mean_luma={lum.mean():.0f}  max_luma={lum.max():.0f}')
    mean_img = st.mean(axis=0)
    rows = []
    for i in range(gr):
        row = []
        for j in range(gc):
            cell = mean_img[i * H // gr:(i + 1) * H // gr, j * W // gc:(j + 1) * W // gc].reshape(-1, 3)
            k = cell.sum(1).argsort()[-max(1, len(cell) * 3 // 10):]
            row.append(name(cell[k].mean(0)))
        rows.append(' '.join(f'{c:6s}' for c in row))
    print('colours (top row = F-keys side):')
    print('\n'.join('  ' + r for r in rows))

    # temporal behaviour
    per_frame = lum.reshape(T, -1).mean(1)
    global_var = per_frame.std()
    col_prof = lum.mean(axis=1)                 # T,W  horizontal profile per frame
    col_prof = col_prof - col_prof.mean(1, keepdims=True)
    spatial_var = np.abs(np.diff(col_prof, axis=0)).mean() if T > 1 else 0
    shift = 0
    if T > 2:
        shifts = []
        for t in range(T - 1):
            a1, a2 = col_prof[t], col_prof[t + 1]
            c = np.correlate(a2, a1, mode='full')
            shifts.append(c.argmax() - (W - 1))
        shift = float(np.median(shifts))
    if global_var < 1.5 and spatial_var < 1.5:
        beh = 'static'
    elif spatial_var > 2 * global_var:
        beh = 'moving ' + ('left->right' if shift > 2 else 'right->left' if shift < -2 else '(direction unclear)')
    else:
        beh = 'pulsing/breathing (whole board)'
    print(f'behaviour: {beh}   [frame-luma std={global_var:.1f}, profile change={spatial_var:.1f}, shift/frame={shift:+.0f}px]')

    if a.thumb:
        Image.fromarray(frames[-1].astype(np.uint8)).resize((W // 3, H // 3)).save(a.thumb)
        print('thumb:', a.thumb)


if __name__ == '__main__':
    main()
