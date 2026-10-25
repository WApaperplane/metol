"""Perceptual de-duplication audit for the whole NX500 LUT library.

Why this exists
---------------
"Too many similar looks" is a real complaint but a vague one.  Two LUTs can look
identical in a grey ramp and completely different on foliage, or vice versa.  A
single probe point proves nothing.  So we measure every pair over the same probe
set Codex used for its dedup gate (12 hues x 2 saturations x 3 lightness = 72),
plus a 21-step grey ramp and eight real-world colours, and report the
**median CIEDE2000** between each pair.

Gate reference: Codex set the project threshold at median dE00 = 3.112 (its
closest surviving pair).  Pairs below that are saying the same thing twice.

Everything is decoded through the native Cr,Cb,Y slot before measuring, so the
distance is what the camera would actually produce, not what the design grid
intended.
"""
from __future__ import annotations

import colorsys
import json
import sys
from pathlib import Path

import numpy as np

sys.stdout.reconfigure(encoding='utf-8')
REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / 'audit_out'
OUT.mkdir(exist_ok=True)
N = 17
GRID = np.array([min(i * 16, 255) for i in range(N)], dtype=np.float64)


# ---------------------------------------------------------------- decoding
def load_native(path):
    raw = np.frombuffer(Path(path).read_bytes()[:19652], dtype=np.uint8)
    return raw.reshape(N, N, N, 4)[:, :, :, :3].astype(np.float64)


def ycc_to_rgb(cr, cb, y):
    cr = cr - 128.0
    cb = cb - 128.0
    return (y + 1.402 * cr,
            y - 0.714136 * cr - 0.344136 * cb,
            y + 1.772 * cb)


def apply_slot(rgb, table):
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    cr = 128.0 + 0.5 * r - 0.418688 * g - 0.081312 * b
    cb = 128.0 - 0.168736 * r - 0.331264 * g + 0.5 * b
    y = 0.299 * r + 0.587 * g + 0.114 * b
    coords = []
    for v in (cr, cb, y):
        v = np.clip(v, 0.0, 255.0)
        i = np.minimum((v / 16.0).astype(np.int32), N - 2)
        i = np.where(v >= 240.0, N - 2, i)
        coords.append((i, np.clip((v - GRID[i]) / (GRID[i + 1] - GRID[i]), 0, 1)))
    (ci, cf), (bi, bf), (yi, yf) = coords
    out = np.zeros(rgb.shape, dtype=np.float64)
    for dz in (0, 1):
        wz = yf if dz else 1 - yf
        for dy in (0, 1):
            wy = bf if dy else 1 - bf
            for dx in (0, 1):
                wx = cf if dx else 1 - cf
                out += table[yi + dz, bi + dy, ci + dx, :] * (wz * wy * wx)[..., None]
    rr, gg, bb = ycc_to_rgb(out[..., 0], out[..., 1], out[..., 2])
    return np.clip(np.stack([rr, gg, bb], -1), 0, 255)


# ---------------------------------------------------------------- colour math
def rgb_to_lab(rgb):
    """sRGB (0-255) -> CIE Lab, D65.

    The matrix is written XYZ-rows by RGB-columns and applied as rgb @ M.T, i.e.
    XYZ = M @ rgb.  An earlier version wrote the rows as RGB coefficients and
    transposed again, which silently produced a=-55 for a neutral grey and L=107
    for pure white - a wrong colour space that still gave plausible-looking dE00
    because it is a consistent transform of the input.
    """
    f = np.asarray(rgb, dtype=np.float64) / 255.0
    lin = np.where(f <= 0.04045, f / 12.92, ((f + 0.055) / 1.055) ** 2.4)
    M = np.array([[0.4124564, 0.3575761, 0.1804375],
                  [0.2126729, 0.7151522, 0.0721750],
                  [0.0193339, 0.1191920, 0.9503041]])
    xyz = lin @ M.T
    xyz = xyz / np.array([0.95047, 1.0, 1.08883])
    q = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * q[..., 1] - 16,
                     500 * (q[..., 0] - q[..., 1]),
                     200 * (q[..., 1] - q[..., 2])], -1)


def de00(lab1, lab2):
    """CIEDE2000, vectorised over the trailing axis."""
    L1, a1, b1 = np.moveaxis(lab1, -1, 0)
    L2, a2, b2 = np.moveaxis(lab2, -1, 0)
    C1 = np.hypot(a1, b1)
    C2 = np.hypot(a2, b2)
    Cb = (C1 + C2) / 2
    G = 0.5 * (1 - np.sqrt(Cb ** 7 / (Cb ** 7 + 25.0 ** 7)))
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = np.hypot(a1p, b1), np.hypot(a2p, b2)
    h1p = np.degrees(np.arctan2(b1, a1p)) % 360
    h2p = np.degrees(np.arctan2(b2, a2p)) % 360
    dLp = L2 - L1
    dCp = C2p - C1p
    dhp = h2p - h1p
    dhp = np.where(dhp > 180, dhp - 360, np.where(dhp < -180, dhp + 360, dhp))
    dhp = np.where(C1p * C2p == 0, 0.0, dhp)
    dHp = 2 * np.sqrt(C1p * C2p) * np.sin(np.radians(dhp / 2))
    Lbp = (L1 + L2) / 2
    Cbp = (C1p + C2p) / 2
    hsum = h1p + h2p
    hbp = np.where(np.abs(h1p - h2p) > 180,
                   np.where(hsum < 360, (hsum + 360) / 2, (hsum - 360) / 2),
                   hsum / 2)
    T = (1 - 0.17 * np.cos(np.radians(hbp - 30))
         + 0.24 * np.cos(np.radians(2 * hbp))
         + 0.32 * np.cos(np.radians(3 * hbp + 6))
         - 0.20 * np.cos(np.radians(4 * hbp - 63)))
    dtheta = 30 * np.exp(-(((hbp - 275) / 25) ** 2))
    Rc = 2 * np.sqrt(Cbp ** 7 / (Cbp ** 7 + 25.0 ** 7))
    Sl = 1 + 0.015 * (Lbp - 50) ** 2 / np.sqrt(20 + (Lbp - 50) ** 2)
    Sc = 1 + 0.045 * Cbp
    Sh = 1 + 0.015 * Cbp * T
    Rt = -np.sin(np.radians(2 * dtheta)) * Rc
    return np.sqrt((dLp / Sl) ** 2 + (dCp / Sc) ** 2 + (dHp / Sh) ** 2
                   + Rt * (dCp / Sc) * (dHp / Sh))


# ---------------------------------------------------------------- probes
def probe_set():
    """72 perceptual probes + 21 grey steps + 8 real-world colours."""
    pts, tags = [], []
    for li, light in enumerate((0.22, 0.45, 0.70)):
        for si, sat in enumerate((0.30, 0.62)):
            for k in range(12):
                h = k * 30.0
                r, g, b = colorsys.hsv_to_rgb(h / 360.0, sat, light)
                pts.append((r * 255, g * 255, b * 255))
                tags.append('p_L%d_S%d_H%03d' % (li, si, int(h)))
    for i in range(21):
        v = i * 255 / 20
        pts.append((v, v, v))
        tags.append('grey_%02d' % i)
    named = {
        'skin_light': (231, 191, 171), 'skin_mid': (198, 148, 118),
        'skin_deep': (122, 78, 55), 'sky': (110, 155, 205),
        'foliage': (74, 104, 58), 'brick': (146, 78, 62),
        'sand': (198, 176, 142), 'white_wall': (222, 220, 216),
    }
    for k, v in named.items():
        pts.append(v)
        tags.append(k)
    return np.array(pts, dtype=np.float64), tags


# ---------------------------------------------------------------- main
def main():
    tables = sorted((REPO / 'looks').glob('*.bin'))
    pts, tags = probe_set()
    lab_of = {}
    for p in tables:
        out = apply_slot(pts, load_native(p))
        lab_of[p.stem] = rgb_to_lab(out)

    names = sorted(lab_of)
    n = len(names)
    D = np.zeros((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            d = float(np.median(de00(lab_of[names[i]], lab_of[names[j]])))
            D[i, j] = D[j, i] = d

    pairs = []
    for i in range(n):
        for j in range(i + 1, n):
            pairs.append((D[i, j], names[i], names[j]))
    pairs.sort()

    np.save(OUT / 'distance.npy', D)
    (OUT / 'names.json').write_text(json.dumps(names), encoding='utf-8')
    (OUT / 'pairs.json').write_text(
        json.dumps([{'dE00': round(d, 3), 'a': a, 'b': b}
                    for d, a, b in pairs], ensure_ascii=False, indent=1),
        encoding='utf-8')

    print('tables: %d   probe points: %d' % (n, len(tags)))
    print('project dedup gate (Codex): median dE00 = 3.112')
    print()
    print('=== 40 closest pairs ===')
    print('%-8s %-26s %-26s' % ('dE00', 'A', 'B'))
    for d, a, b in pairs[:40]:
        print('%-8.3f %-26s %-26s' % (d, a, b))

    # cluster at the project gate
    thresh = 3.112
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(n):
        for j in range(i + 1, n):
            if D[i, j] < thresh:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[ri] = rj
    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(names[i])
    clusters = sorted(groups.values(), key=len, reverse=True)

    print()
    print('=== clusters with intra-distance < %.3f ===' % thresh)
    dup = 0
    for g in clusters:
        if len(g) > 1:
            dup += len(g) - 1
            print('[%d] %s' % (len(g), ', '.join(g)))
    print()
    print('redundant tables if one kept per cluster: %d' % dup)
    (OUT / 'clusters.json').write_text(
        json.dumps(clusters, ensure_ascii=False, indent=1), encoding='utf-8')

    # per-table "loneliness": nearest neighbour distance
    print()
    print('=== least differentiated tables (smallest nearest-neighbour dE00) ===')
    nn = [(min(D[i, j] for j in range(n) if j != i), names[i])
          for i in range(n)]
    nn.sort()
    for d, nm in nn[:25]:
        print('  %6.3f  %s' % (d, nm))


if __name__ == '__main__':
    main()
