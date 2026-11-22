#!/usr/bin/env python3
"""Poll the Odyssey config and print every change of bytes 0x00-0x1F (read-only).

usage: watch_odyssey.py [seconds] [--cam]   (--cam: webcam summary after each change)
"""
import os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from probe_odyssey import find_hidraw, frame, xfer, hx

if __name__ == '__main__':
    dur = float(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1] != '--cam' else 60
    fd = os.open(find_hidraw(), os.O_RDWR)
    prev, end = None, time.time() + dur
    try:
        while time.time() < end:
            xfer(fd, frame(0x01))
            r = xfer(fd, frame(0x05, 0x20, 0))
            xfer(fd, frame(0x02))
            cur = r[0][8:40] if r else None
            if cur and cur != prev:
                diff = '' if prev is None else ' '.join(
                    f'[{i:#04x}]{prev[i]:02x}->{cur[i]:02x}' for i in range(32) if prev[i] != cur[i])
                print(f'{time.strftime("%H:%M:%S")} effect={cur[1]:2d}  {diff or hx(cur[:16])}', flush=True)
                prev = cur
                if '--cam' in sys.argv:
                    time.sleep(0.5)
                    subprocess.run([sys.executable, '-I', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cam_watch.py'), '--secs', '2.5'])
            time.sleep(0.3)
    finally:
        os.close(fd)
