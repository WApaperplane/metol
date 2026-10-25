"""Where does the library actually cover, and where is it empty?

Dedup alone gives you a smaller library, not a better one.  Diversity has to be
measured in interpretable axes, otherwise "add more looks" just adds more of the
same.  Six axes, all readable off the 90 tables through the native slot:

  warmth        mean b*            (+) yellow/warm   (-) blue/cool
  saturation    mean C*            flat vs chromatic
  contrast      grey-ramp mid slope
  shadow_tint   b*(low)  - b*(mid) shadows warmer or cooler than midtone
  high_tint     b*(high) - b*(mid) highlights warmer or cooler
  green_mag      mean a*           (+) magenta lean (-) green lean
  black_lift    L* of the black point
  white_level   L* of the white point
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, str(Path(__file__).parent))
from similarity_audit import (GRID, N, apply_slot, de00, load_native,  # noqa: E402
                              probe_set, rgb_to_lab, REPO)

OUT = Path(__file__).resolve().parent / 'audit_out'
PROTECT_PREFIX = ('v2_',)


def metrics(table):
    pts, tags = probe_set()
    lab = rgb_to_lab(apply_slot(pts, table))
    bi = {t: i for i, t in enumerate(tags)}
    greys = [bi['grey_%02d' % i] for i in range(21)]
    glab = lab[greys]
    gL = glab[:, 0]
    colors = [i for i, t in enumerate(tags) if t.startswith('p_')]
    clab = lab[colors]

    # grey-ramp slope over the middle 40-60% of the input range
    lo, hi = 8, 12
    slope = (gL[hi] - gL[lo]) / (GRID[hi] - GRID[lo]) * 255.0 / 100.0

    shadow = lab[greys[0]][2]
    mid = lab[greys[10]][2]
    high = lab[greys[-1]][2]
    return dict(
        warmth=float(np.mean(clab[:, 2])),
        saturation=float(np.mean(np.hypot(clab[:, 1], clab[:, 2]))),
        contrast=float(slope),
        shadow_tint=float(shadow - mid),
        high_tint=float(high - mid),
        green_mag=float(np.mean(clab[:, 1])),
        black_lift=float(gL[0]),
        white_level=float(gL[-1]),
    )


def main():
    tables = sorted((REPO / 'looks').glob('*.bin'))
    rows = {}
    for p in tables:
        rows[p.stem] = metrics(load_native(p))
    (OUT / 'axes.json').write_text(json.dumps(rows, ensure_ascii=False, indent=1),
                                   encoding='utf-8')

    names = sorted(rows)
    M = {k: np.array([rows[n][k] for n in names]) for k in rows[names[0]]}

    print('%-24s %7s %7s %7s %7s %7s %7s %6s %6s'
          % ('table', 'warm', 'sat', 'contr', 'shTw', 'hiTw', 'gMag', 'blk', 'wht'))
    for n in names:
        r = rows[n]
        mark = '*' if n.startswith(PROTECT_PREFIX) else ' '
        print('%-1s%-22s %7.1f %7.1f %7.2f %7.1f %7.1f %7.1f %6.1f %6.1f'
              % (mark, n, r['warmth'], r['saturation'], r['contrast'],
                 r['shadow_tint'], r['high_tint'], r['green_mag'],
                 r['black_lift'], r['white_level']))

    print()
    print('=== axis ranges (how wide is the library actually?) ===')
    for k in M:
        v = M[k]
        print('  %-12s min %7.1f  max %7.1f  span %7.1f  std %6.2f'
              % (k, v.min(), v.max(), v.max() - v.min(), v.std()))

    # occupancy grid on the two most decision-relevant axes
    print()
    print('=== occupancy: warmth x saturation (each cell = #tables) ===')
    wx = np.linspace(M['warmth'].min(), M['warmth'].max(), 7)
    sx = np.linspace(M['saturation'].min(), M['saturation'].max(), 6)
    H, _, _ = np.histogram2d(M['warmth'], M['saturation'], bins=[wx, sx])
    print('            sat->%s' % ' '.join('%6.0f' % v for v in sx[:-1]))
    for i in range(len(wx) - 1):
        print('warm %6.1f  %s' % (wx[i], ' '.join('%6d' % v for v in H[i])))
    empty = int((H == 0).sum())
    print('  empty cells: %d / %d' % (empty, H.size))

    print()
    print('=== occupancy: contrast x black_lift ===')
    cx = np.linspace(M['contrast'].min(), M['contrast'].max(), 6)
    bx = np.linspace(M['black_lift'].min(), M['black_lift'].max(), 5)
    H2, _, _ = np.histogram2d(M['contrast'], M['black_lift'], bins=[cx, bx])
    print('            black->%s' % ' '.join('%6.0f' % v for v in bx[:-1]))
    for i in range(len(cx) - 1):
        print('contr %6.2f  %s' % (cx[i], ' '.join('%6d' % v for v in H2[i])))
    print('  empty cells: %d / %d' % (int((H2 == 0).sum()), H2.size))

    # most isolated tables = current extremes
    print()
    print('=== current extremes (the edges of what the library can do) ===')
    for k in ('warmth', 'saturation', 'contrast', 'shadow_tint', 'green_mag',
              'black_lift'):
        v = M[k]
        print('  %-12s low %-22s (%.1f)   high %-22s (%.1f)'
              % (k, names[int(v.argmin())], v.min(),
                 names[int(v.argmax())], v.max()))


if __name__ == '__main__':
    main()
