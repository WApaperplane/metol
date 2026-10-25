"""Render a photo through a native Cr,Cb,Y slot exactly as the camera would.

The camera reads the slot as (Cr, Cb, Y) input coordinates and trilinearly
interpolates.  Rendering through that path - not through the design-space RGB
table - is the only way a preview can predict what the sensor JPEG will look
like.  That mismatch is why the old .cube previews looked fine while the camera
did not.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.stdout.reconfigure(encoding='utf-8')

N = 17
GRID = np.array([min(i * 16, 255) for i in range(N)], dtype=np.float64)


def load_slot(path):
    raw = np.frombuffer(Path(path).read_bytes()[:19652], dtype=np.uint8)
    return raw.reshape(N, N, N, 4)[:, :, :, :3].astype(np.float64)


def rgb_to_ycc(r, g, b):
    return (128.0 + 0.5 * r - 0.418688 * g - 0.081312 * b,
            128.0 - 0.168736 * r - 0.331264 * g + 0.5 * b,
            0.299 * r + 0.587 * g + 0.114 * b)


def ycc_to_rgb(cr, cb, y):
    cr = cr - 128.0
    cb = cb - 128.0
    return (y + 1.402 * cr,
            y - 0.714136 * cr - 0.344136 * cb,
            y + 1.772 * cb)


def apply_slot(rgb_image, table):
    """rgb_image: (H,W,3) float 0..255 -> same, through the native slot."""
    h, w, _ = rgb_image.shape
    r, g, b = rgb_image[..., 0], rgb_image[..., 1], rgb_image[..., 2]
    cr, cb, y = rgb_to_ycc(r, g, b)
    # lattice coordinates
    coords = []
    for v in (cr, cb, y):
        v = np.clip(v, 0.0, 255.0)
        idx = np.clip((v / 16.0).astype(np.int32), 0, N - 2)
        idx = np.where(v >= 240.0, N - 2, idx)
        frac = (v - GRID[idx]) / (GRID[idx + 1] - GRID[idx])
        coords.append((idx, np.clip(frac, 0.0, 1.0)))
    (ci, cf), (bi, bf), (yi, yf) = coords
    out = np.zeros((h, w, 3), dtype=np.float64)
    for dz in (0, 1):
        wz = yf if dz else (1 - yf)
        zz = yi + dz
        for dy in (0, 1):
            wy = bf if dy else (1 - bf)
            yy = bi + dy
            for dx in (0, 1):
                wx = cf if dx else (1 - cf)
                xx = ci + dx
                wgt = wz * wy * wx
                samp = table[zz, yy, xx, :]
                out += samp * wgt[..., None]
    # the table stores Cr,Cb,Y output
    rr, gg, bb = ycc_to_rgb(out[..., 0], out[..., 1], out[..., 2])
    return np.clip(np.stack([rr, gg, bb], axis=-1), 0, 255)


def render_file(src, table_path, dst):
    from PIL import Image
    im = Image.open(src).convert('RGB')
    arr = np.asarray(im, dtype=np.float64)
    out = apply_slot(arr, load_slot(table_path))
    Image.fromarray(out.astype(np.uint8)).save(dst, quality=96)
    return dst


if __name__ == '__main__':
    if len(sys.argv) < 4:
        print('usage: render_slot.py <src.jpg> <table.bin> <dst.jpg>')
        raise SystemExit(2)
    print(render_file(sys.argv[1], sys.argv[2], sys.argv[3]))
