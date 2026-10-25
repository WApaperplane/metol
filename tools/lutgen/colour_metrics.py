"""Trustworthy colour metrics for the LUT library.

Two bugs in the earlier pass are fixed here:

1. rgb_to_lab had the sRGB->XYZ matrix multiplication reversed.  It reported
   a* = -55 for a neutral grey and L* = 107 for pure white, so every "warmth"
   and "saturation" number was measured in a distorted space.  Fixed in
   similarity_audit and verified against known patches.

2. shadow_tint / high_tint were read at L*=0 and L*=100.  grade() fades its
   split-toning to zero at both ends (endpoints = smooth(0,7,L), and
   protect_white above 96), so both readings collapsed to 0 and the two metrics
   became -b*(mid) -- the same number twice.  Measured here at input 45 and 210
   instead, which is where the toning actually lives.

Axes:
  warmth       mean b* over the colour probes   (+ yellow, - blue)
  saturation   mean C* over the colour probes
  contrast     dL*/dInput across the midslope
  shadow_tint  b*(in 45)  - b*(in 128)
  high_tint    b*(in 210) - b*(in 128)
  shadow_a     a*(in 45)  - a*(in 128)   (green vs magenta in shadow)
  high_a       a*(in 210) - a*(in 128)
  black_lift   L* of input 0
  white_level  L* of input 255
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, str(Path(__file__).parent))
from similarity_audit import (GRID, apply_slot, load_native, probe_set,  # noqa: E402
                              rgb_to_lab, REPO)

PROBE_IN = (45.0, 128.0, 210.0)


def metrics(table):
    pts, tags = probe_set()
    lab = rgb_to_lab(apply_slot(pts, table))
    bi = {t: i for i, t in enumerate(tags)}
    greys = [bi['grey_%02d' % i] for i in range(21)]
    glab = lab[greys]
    gL = glab[:, 0]
    colors = [i for i, t in enumerate(tags) if t.startswith('p_')]
    clab = lab[colors]

    dark = rgb_to_lab(apply_slot(np.array([[PROBE_IN[0]] * 3]), table)[0])
    mid = rgb_to_lab(apply_slot(np.array([[PROBE_IN[1]] * 3]), table)[0])
    light = rgb_to_lab(apply_slot(np.array([[PROBE_IN[2]] * 3]), table)[0])

    return dict(
        warmth=float(np.mean(clab[:, 2])),
        saturation=float(np.mean(np.hypot(clab[:, 1], clab[:, 2]))),
        contrast=float((gL[12] - gL[8]) / (GRID[12] - GRID[8]) * 255.0 / 100.0),
        shadow_tint=float(dark[2] - mid[2]),
        high_tint=float(light[2] - mid[2]),
        shadow_a=float(dark[1] - mid[1]),
        high_a=float(light[1] - mid[1]),
        shadow_L=float(dark[0]),
        high_L=float(light[0]),
        black_lift=float(gL[0]),
        white_level=float(gL[-1]),
    )


def main():
    tables = sorted((REPO / 'looks').glob('*.bin'))
    rows = {p.stem: metrics(load_native(p)) for p in tables}
    (Path(__file__).parent / 'axes2.json').write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding='utf-8')

    ks = ['warmth', 'saturation', 'contrast', 'shadow_tint', 'high_tint',
          'shadow_a', 'high_a', 'black_lift', 'white_level']
    print('%-24s' % 'table' + ''.join('%8s' % k[:7] for k in ks))
    for k in sorted(rows):
        print('%-24s' % k + ''.join('%8.1f' % rows[k][x] for x in ks))

    print()
    print('=== ranges ===')
    for x in ks:
        v = np.array([rows[k][x] for k in rows])
        print('  %-12s %7.1f .. %7.1f   span %6.1f  std %5.2f'
              % (x, v.min(), v.max(), v.max() - v.min(), v.std()))

    print()
    print('=== extremes ===')
    names = sorted(rows)
    for x in ks:
        v = np.array([rows[k][x] for k in names])
        print('  %-12s low %-24s %7.1f   high %-24s %7.1f'
              % (x, names[int(v.argmin())], v.min(),
                 names[int(v.argmax())], v.max()))


if __name__ == '__main__':
    main()
