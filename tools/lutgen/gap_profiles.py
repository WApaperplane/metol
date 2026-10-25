"""Fill the empty quadrants of the look space.

The coverage audit showed the existing 90 tables occupy a narrow band:

    warmth       0.4 .. 11.8     (no cool look exists at all)
    saturation  33.7 .. 56.2     (nothing above 56)
    contrast     0.62 .. 1.38    (nothing flat, nothing hard)
    black_lift   0 .. 17.1       (nothing with a real lifted black)
    high_tint   -3.2 .. 9.4      (no cold highlight, weak warm highlight)

So the problem was never "not enough looks".  It was that every design landed in
the same comfortable middle.  These profiles are chosen by *empty coordinate*,
not by style name, and each one is then verified to sit > 3.112 median dE00 from
everything already in the library.

Coordinates are L* units for tone and Lab units for split; see coverage.py for
how each axis is measured.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.stdout.reconfigure(encoding='utf-8')
LUTGEN = Path(__file__).resolve().parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

import style_collection as sc          # noqa: E402
from similarity_audit import (apply_slot, de00, load_native, probe_set,  # noqa: E402
                              rgb_to_lab, REPO)

OUT = Path(__file__).resolve().parent / 'audit_out'
TONE_IN = [0, 8, 20, 40, 60, 80, 92, 100]

# ---------------------------------------------------------------------------
# Each entry names the empty region it fills, not a film stock.
# ---------------------------------------------------------------------------
PROFILES = {
    # ---- 1. cool axis: warmth far below the library's floor (0.4) ----------
    'nordic_overcast': dict(
        label='北欧阴天 · 冷灰',
        family='cool-neutral',
        source='empty quadrant: cool cast, nothing in the library is cool',
        intent='Whole image sits blue of neutral; flat light; no warm cast anywhere.',
        tone=[0, 6, 17, 37, 56, 71, 80, 86],
        sat=0.88,
        split={'shadow': [-1.0, -15.0], 'mid': [-0.5, -15.0],
               'highlight': [-1.0, -15.0]},
    ),
    # ---- 2. high key: no table lifts black AND keeps white high -----------
    'high_key_cool': dict(
        label='高调冷光 · 亮部主导',
        family='high-key',
        source='empty quadrant: lifted black with a bright, flat, cool body',
        intent='Bright airy rendering, black sits high, little separation, cool cast.',
        tone=[22, 30, 42, 56, 69, 81, 90, 96],
        sat=0.72,
        split={'shadow': [-0.5, -7.0], 'mid': [0.0, -6.0],
               'highlight': [-0.5, -4.0]},
    ),
    # ---- 3. black lift: nothing in the library exceeds 17 ----------------
    'expired_1970s': dict(
        label='过期胶卷 · 抬黑褪色',
        family='faded-lift',
        source='empty quadrant: black point lifted to L*32',
        intent='Black sits high and warm-brown; contrast collapses; no true black.',
        tone=[32, 36, 43, 53, 63, 72, 78, 83],
        sat=0.78,
        split={'shadow': [1.5, 8.0], 'mid': [0.5, 3.0],
               'highlight': [0.0, 2.0]},
    ),
    # ---- 4. flat contrast: nothing is below 0.62 -------------------------
    'fog_flat': dict(
        label='雾面 · 极低反差',
        family='flat-veil',
        source='empty quadrant: lowest contrast in the library',
        intent='Barely any tonal separation; milky highlights; grey-green veil.',
        tone=[15, 20, 28, 39, 49, 58, 65, 71],
        sat=0.62,
        split={'shadow': [-0.5, -3.0], 'mid': [0.0, -2.0],
               'highlight': [-0.5, -3.0]},
    ),
    # ---- 5. hard contrast: nothing is above 1.38 -------------------------
    'press_hard': dict(
        label='新闻硬调 · 高反差',
        family='hard-print',
        source='empty quadrant: contrast far beyond 1.38',
        intent='Ink blacks, violently compressed mids, restrained colour.',
        tone=[0, 1, 5, 21, 50, 84, 97, 100],
        sat=0.74,
        split={'shadow': [0.0, -1.0], 'mid': [0.0, 0.0],
               'highlight': [0.0, 0.5]},
    ),
    # ---- 6. maximum chroma: library tops out at 56.2 ---------------------
    #      Capped at sat=1.75, not the 2.55 first tried: on-device the orange
    #      box (230,120,40) turned magenta-red because B hits 0 first and only G
    #      is left to push.  Beyond this the lattice runs out of gamut, so this
    #      is the honest ceiling of the axis, not a taste choice.
    'chrome_vivid': dict(
        label='浓艳正片 · 超高饱和',
        family='ultra-chroma',
        source='empty quadrant: saturation past every existing table',
        intent='Chroma pushed past the library while keeping warm hues from going red.',
        tone=[0, 4, 13, 33, 56, 79, 93, 100],
        sat=1.75,
        sat_hues={'30': 1.06, '120': 1.10, '240': 1.08},
        split={'shadow': [0.0, -1.5], 'mid': [0.0, 0.0],
               'highlight': [0.0, 1.0]},
    ),
    # ---- 7. cool shadow + magenta highlight ------------------------------
    'neon_night': dict(
        label='霓虹夜 · 冷影品红高光',
        family='neon',
        source='empty quadrant: cool shadow against magenta highlight',
        intent='Teal-blue shadows, magenta-pushed highlights, saturated throughout.',
        tone=[0, 3, 10, 28, 49, 70, 87, 94],
        sat=1.35,
        split={'shadow': [-1.7, -16.0], 'mid': [0.5, -4.0],
               'highlight': [11.0, 6.0]},
    ),
    # ---- 8. warm axis: ceiling is 11.8 ----------------------------------
    'desert_noon': dict(
        label='沙漠正午 · 极暖金',
        family='ultra-warm',
        source='empty quadrant: warm cast past every existing table',
        intent='Global yellow-orange cast, ochre shadows, no cool relief.',
        tone=[0, 4, 14, 34, 57, 79, 92, 99],
        sat=1.10,
        sat_hues={'60': 1.12, '240': 0.78, '180': 0.82},
        split={'shadow': [1.5, 16.0], 'mid': [0.5, 16.0],
               'highlight': [0.5, 14.0]},
    ),
    # ---- 9. low key: no table compresses the white point -------------------
    'low_key_warm': dict(
        label='低调暖 · 暗部主导',
        family='low-key',
        source='empty quadrant: white point pulled to L*80, dark dominant',
        intent='Dark, moody, warm; highlights never reach paper white.',
        tone=[0, 2, 8, 22, 43, 62, 73, 80],
        sat=1.18,
        sat_hues={'30': 1.08, '60': 1.06},
        split={'shadow': [1.0, 9.0], 'mid': [0.5, 8.0],
               'highlight': [0.5, 6.0]},
    ),
    # ---- 10. magenta/green axis: nothing is magenta-leaning -------------
    'magenta_shadow': dict(
        label='品红影 · 洋红暗部',
        family='magenta-split',
        source='empty quadrant: positive a* cast, absent from the whole library',
        intent='Shadows drift magenta-crimson; highlights stay cool; no green cast.',
        tone=[0, 5, 15, 35, 56, 76, 89, 96],
        sat=1.08,
        split={'shadow': [13.0, 3.0], 'mid': [4.0, 0.0],
               'highlight': [-3.0, -2.0]},
    ),
    # ---- 11. cool + lifted black (two empty axes at once) ---------------
    'cold_archive': dict(
        label='冷调档案 · 抬黑偏青',
        family='cool-faded',
        source='empty quadrant: lifted black AND cool cast together',
        intent='A faded print kept cool instead of the usual warm yellow.',
        tone=[26, 31, 39, 50, 60, 70, 77, 83],
        sat=0.70,
        split={'shadow': [-1.0, -12.0], 'mid': [-0.5, -10.0],
               'highlight': [-0.5, -8.0]},
    ),
    # ---- 12. desaturated hard contrast ---------------------------------
    'silver_retain': dict(
        label='银盐保留 · 极端漂白',
        family='bleach-extreme',
        source='empty quadrant: near-monochrome with a hard curve',
        intent='Almost no colour left, but the tone curve is steep and clean.',
        tone=[0, 1, 6, 24, 52, 82, 96, 100],
        sat=0.18,
        split={'shadow': [0.0, -1.0], 'mid': [0.0, 0.0],
               'highlight': [0.0, 1.0]},
    ),
}


def measure(view):
    """Six interpretable axes, same definitions as coverage.py."""
    pts, tags = probe_set()
    lab = rgb_to_lab(apply_slot(pts, view))
    bi = {t: i for i, t in enumerate(tags)}
    greys = [bi['grey_%02d' % i] for i in range(21)]
    glab = lab[greys]
    gL = glab[:, 0]
    colors = [i for i, t in enumerate(tags) if t.startswith('p_')]
    clab = lab[colors]
    slope = (gL[12] - gL[8]) / (GRIDV[12] - GRIDV[8]) * 255.0 / 100.0
    return dict(warmth=float(np.mean(clab[:, 2])),
                saturation=float(np.mean(np.hypot(clab[:, 1], clab[:, 2]))),
                contrast=float(slope),
                shadow_tint=float(glab[0][2] - glab[10][2]),
                high_tint=float(glab[-1][2] - glab[10][2]),
                green_mag=float(np.mean(clab[:, 1])),
                black_lift=float(gL[0]),
                white_level=float(gL[-1]))


GRIDV = np.array([min(i * 16, 255) for i in range(17)], dtype=float)


def build_one(name, prof, n=33):
    """Compile a profile to native slot bytes without writing to looks/."""
    import native_codec as nc
    axis = np.linspace(0, 255, n)
    b, g, r = np.meshgrid(axis, axis, axis, indexing='ij')
    src = np.stack((r, g, b), axis=-1)
    nodes = sc.grade(src, prof, TONE_IN)
    raw = nc.compile_uniform_rgb(nodes.reshape(-1, 3).tolist(), n,
                                 boundary='linear')
    return raw


def main():
    existing = {}
    for p in sorted((REPO / 'looks').glob('*.bin')):
        existing[p.stem] = load_native(p)
    ex_pts, _ = probe_set()
    ex_lab = {k: rgb_to_lab(apply_slot(ex_pts, v)) for k, v in existing.items()}

    print('%-18s %6s %6s %6s %7s %7s %7s %6s | %-22s %6s %6s'
          % ('profile', 'warm', 'sat', 'contr', 'shTw', 'hiTw', 'blk',
             'wht', 'nearest existing', 'vs ex', 'vs new'))
    built = {}
    for name, prof in PROFILES.items():
        raw = build_one(name, prof)
        view = np.frombuffer(raw[:19652], np.uint8).reshape(17, 17, 17, 4)
        view = view[:, :, :, :3].astype(float)
        built[name] = (raw, view, measure(view),
                       rgb_to_lab(apply_slot(ex_pts, view)))

    # greedy admission: keep a design only if it is far enough from BOTH the
    # existing library and everything already admitted
    order = sorted(built, key=lambda n: -min(
        float(np.median(de00(built[n][3], el))) for el in ex_lab.values()))
    admitted, rejected = [], {}
    results = {}
    for name in order:
        raw, view, m, lab = built[name]
        d_ex, near_ex = min(((float(np.median(de00(lab, el))), k)
                             for k, el in ex_lab.items()
                             if k != 'gap_' + name))
        d_new, near_new = 99.0, '-'
        if admitted:
            d_new, near_new = min(((float(np.median(de00(lab, built[a][3]))), a)
                                   for a in admitted))
        ok = d_ex > 3.112 and d_new > 3.112
        results[name] = dict(axes=m, nearest_existing=near_ex,
                             dE00_existing=round(d_ex, 3),
                             nearest_new=near_new, dE00_new=round(d_new, 3),
                             admitted=ok, recipe=prof)
        print('%-18s %6.1f %6.1f %6.2f %7.1f %7.1f %7.1f %6.1f | %-22s %6.3f %6.3f%s'
              % (name, m['warmth'], m['saturation'], m['contrast'],
                 m['shadow_tint'], m['high_tint'], m['black_lift'],
                 m['white_level'], near_ex, d_ex, d_new,
                 '' if ok else '   REJECT'))
        if ok:
            admitted.append(name)
        else:
            rejected[name] = (d_ex, near_ex, d_new, near_new)

    (OUT / 'new_profiles.json').write_text(
        json.dumps(results, ensure_ascii=False, indent=1), encoding='utf-8')
    (OUT / 'admitted.json').write_text(
        json.dumps(admitted, ensure_ascii=False, indent=1), encoding='utf-8')
    print()
    print('admitted %d / %d' % (len(admitted), len(results)))
    if rejected:
        print('rejected:')
        for k, (de, ne, dn, nn) in rejected.items():
            print('  %-18s vs existing %-22s %.3f | vs new %-18s %.3f'
                  % (k, ne, de, nn, dn))


if __name__ == '__main__':
    main()
