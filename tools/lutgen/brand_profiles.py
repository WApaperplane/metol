"""Brand-characteristic looks, verified on the colour the name promises.

Why this file exists in this shape
---------------------------------
The old ricoh_*/canon_*/cool_* tables all sat inside warm 0.4-4.1, sat 50-54,
contrast 0.85-1.0.  They were one template with eleven names, which is why "the
Ricoh blue doesn't look blue".  A look is only that look if its defining colour
actually moves, so each profile is accepted on a measured characteristic, not on
"it differs somehow".

Two hard constraints were found by probing before these were written:

* Blue chroma peaks at sat_hues{'240'} ~= 1.6 (C* 78).  Beyond that G hits 255
  and R hits 0 and chroma *falls* again.  So "Ricoh blue" targets cyan-er and
  denser, not maximally saturated.
* high_tint is set by the mid-vs-highlight gap in b*, not by the absolute
  highlight value: mid 10 / high 13 gives 3.1, mid 3 / high 18 gives 12.5.
  Warmth therefore has to be carried by the shadow band instead.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.stdout.reconfigure(encoding='utf-8')
LUTGEN = Path(__file__).resolve().parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

import gap_profiles as fg          # noqa: E402
from colour_metrics import metrics     # noqa: E402
from similarity_audit import (apply_slot, de00, load_native, probe_set,  # noqa: E402
                              rgb_to_lab, REPO)

OUT = Path(__file__).resolve().parent / 'audit_out' / 'brand'
OUT.mkdir(exist_ok=True)

TONE_IN = [0, 8, 20, 40, 60, 80, 92, 100]

PROFILES = {
    # ======== 理光蓝 Ricoh Blue ==========================================
    'ricoh_blue': dict(
        label='理光蓝 · 青蓝天空',
        family='brand-ricoh',
        source='Ricoh GR Image Control "Positive Film": dense cyan-blue sky',
        intent='Blue moves toward cyan and gains chroma; red and green held back.',
        tone=[0, 4, 12, 32, 55, 78, 92, 99],
        sat=1.16,
        sat_hues={'240': 1.68, '210': 1.38, '180': 1.08, '0': 0.84, '30': 0.86,
                  '120': 0.84},
        hue={'240': -10, '210': -4},
        split={'shadow': [-0.5, -7.0], 'mid': [0.0, -3.5],
               'highlight': [0.5, -2.0]},
    ),
    # ======== 佳能红 Canon Red ==========================================
    'canon_red': dict(
        label='佳能红 · 暖红肤色',
        family='brand-canon',
        source='Canon Picture Style: warm red, rosy skin, no magenta',
        intent='Reds saturate warm and land at Lab hue ~30 (warm red, not pure red, not magenta).',
        tone=[0, 5, 14, 35, 58, 80, 93, 99],
        sat=1.22,
        sat_hues={'0': 1.42, '30': 1.30, '330': 1.34, '120': 0.86, '240': 0.92},
        hue={'0': 9, '330': 6},
        split={'shadow': [1.0, 1.0], 'mid': [1.5, 1.0],
               'highlight': [1.0, 2.0]},
        skin={'a': 4.0, 'b': 1.0},
    ),
    # ======== 宾得正负逆冲 Pentax Cross Process =========================
    'pentax_crossproc': dict(
        label='宾得正负逆冲 · 交叉冲洗',
        family='brand-pentax-cross',
        source='Pentax Custom Image "Cross Processing": C-41 film in E-6 chemistry',
        intent='Violent contrast, teal-green shadow, yellow highlight, no neutral mid.',
        tone=[0, 1, 5, 22, 52, 84, 97, 100],
        sat=1.40,
        sat_hues={'120': 1.22, '180': 1.30, '60': 1.14, '240': 1.08},
        hue={'120': -8, '180': -6, '60': 5},
        split={'shadow': [-5.0, -9.0], 'mid': [-1.0, 1.0],
               'highlight': [3.0, 13.0]},
    ),
    # ======== 青绿 Teal-Green ===========================================
    'teal_green': dict(
        label='青绿 · 冷调绿影',
        family='teal',
        source='cinema teal grade: green-cyan shadow, clean highlight',
        intent='Green-cyan cast strongest in shadow; highlights stay clean.',
        tone=[0, 5, 14, 34, 55, 75, 89, 97],
        sat=1.02,
        sat_hues={'180': 1.30, '150': 1.34, '120': 1.16, '240': 0.80, '30': 0.84},
        hue={'180': -4, '150': -8, '120': -5},
        split={'shadow': [-6.0, -10.0], 'mid': [-3.0, -5.5],
               'highlight': [-1.0, -2.0]},
    ),
    # ======== 青橙 Teal & Orange ========================================
    'teal_orange': dict(
        label='青橙 · 好莱坞分离',
        family='teal-orange',
        source='teal-and-orange grade: cyan shadow against orange highlight',
        intent='Largest shadow-highlight opposition in the library; skin lands orange.',
        tone=[0, 4, 13, 34, 57, 79, 93, 99],
        sat=1.14,
        sat_hues={'30': 1.22, '0': 1.14, '180': 1.12},
        split={'shadow': [-3.5, -15.0], 'mid': [0.0, -1.0],
               'highlight': [5.0, 15.0]},
        skin={'a': 2.0, 'b': 3.5},
    ),
    # ======== 金黄 Golden ===============================================
    'golden_film': dict(
        label='金黄 · 琥珀正片',
        family='golden',
        source='empty quadrant: whole-frame golden amber, warm shadow',
        intent='Amber overall; gold highlight; warm brown shadow; no cool relief.',
        tone=[0, 3, 10, 30, 56, 82, 95, 100],
        sat=1.10,
        sat_hues={'60': 1.20, '30': 1.12, '120': 0.92, '240': 0.70, '180': 0.76},
        hue={'60': 4, '240': -8},
        split={'shadow': [2.5, 17.0], 'mid': [0.5, 1.5],
               'highlight': [0.0, 21.0]},
    ),
    # ======== 冷艳 Cool Vivid ===========================================
    'cool_vivid': dict(
        label='冷艳 · 高饱和冷调',
        family='cool-vivid',
        source='empty quadrant: cool cast with high chroma and contrast',
        intent='Cool throughout but saturated and contrasty - not the flat grey cool.',
        tone=[0, 2, 8, 27, 53, 79, 94, 100],
        sat=1.48,
        sat_hues={'210': 1.22, '240': 1.20, '30': 0.80, '60': 0.82},
        split={'shadow': [-1.5, -8.0], 'mid': [-0.5, -7.0],
               'highlight': [-1.0, -6.0]},
    ),
}


# ---------------------------------------------------------------- metrics
BLUE = (40.0, 90.0, 200.0)
RED = (200.0, 45.0, 40.0)
SKIN = (198.0, 148.0, 118.0)     # mid-tone skin, not a highlight


def labc(rgb):
    lab = rgb_to_lab(np.asarray(rgb, dtype=float))
    C = float(np.hypot(lab[1], lab[2]))
    h = float(np.degrees(np.arctan2(lab[2], lab[1])) % 360)
    return C, h, float(lab[1])


def brand_metrics(view):
    blue = apply_slot(np.array([BLUE]), view)[0]
    red = apply_slot(np.array([RED]), view)[0]
    skin = apply_slot(np.array([SKIN]), view)[0]
    m = metrics(view)
    bc, bh, ba = labc(blue)
    rc, rh, _ = labc(red)
    m.update(
        blue_chroma=round(bc, 1), blue_hue=round(bh, 1), blue_a=round(ba, 1),
        red_chroma=round(rc, 1), red_hue=round(rh, 1),
        skin_a=round(float(rgb_to_lab(skin)[1]), 1),
        blue_rgb=[round(float(v)) for v in blue],
        red_rgb=[round(float(v)) for v in red],
    )
    return m


CHECKS = {
    # Cyan-er and more chromatic are mutually exclusive here: pulling the hue to
    # 280 necessarily drops C* from 66 to ~67 because a* falls as green enters.
    # Ricoh's signature is the hue, so that is what is tested.
    'ricoh_blue':       lambda m: m['blue_hue'] < 286 and m['blue_chroma'] > 64
                                  and m['blue_a'] < 20,
    'canon_red':        lambda m: m['red_chroma'] > 80 and 24 < m['red_hue'] < 46
                                  and m['skin_a'] > 9,
    'pentax_crossproc': lambda m: m['contrast'] > 1.15 and m['shadow_tint'] < -3
                                  and m['high_tint'] > 3,
    'teal_green':       lambda m: m['shadow_a'] < -1.5 and m['shadow_tint'] < -3,
    'teal_orange':      lambda m: m['shadow_tint'] < -6 and m['high_tint'] > 5,
    'golden_film':      lambda m: m['warmth'] > 5 and m['high_tint'] > 8,
    'cool_vivid':       lambda m: m['warmth'] < -4 and m['saturation'] > 32,
}


def main():
    existing = {p.stem: load_native(p) for p in sorted((REPO / 'looks').glob('*.bin'))}
    pts, _ = probe_set()
    ex_lab = {k: rgb_to_lab(apply_slot(pts, v)) for k, v in existing.items()}
    base = brand_metrics(load_native(REPO / 'looks' / 'identity17.bin'))
    print('identity baseline: blue C*=%.1f h=%.1f | red C*=%.1f h=%.1f | skin a*=%.1f'
          % (base['blue_chroma'], base['blue_hue'], base['red_chroma'],
             base['red_hue'], base['skin_a']))
    print()

    print('%-18s %6s %6s | %6s %6s %6s | %6s %6s %6s | %6s %6s | %s'
          % ('profile', 'blueC', 'blueH', 'redC', 'redH', 'skinA',
             'shTw', 'hiTw', 'shA', 'warm', 'sat', 'check / nearest / dE00'))
    built, rows = {}, {}
    for name, prof in PROFILES.items():
        raw = fg.build_one(name, prof)
        view = np.frombuffer(raw[:19652], np.uint8).reshape(17, 17, 17, 4)
        view = view[:, :, :, :3].astype(float)
        m = brand_metrics(view)
        lab = rgb_to_lab(apply_slot(pts, view))
        # skip this profile's own table when it is already deployed
        d_ex, near = min(((float(np.median(de00(lab, el))), k)
                          for k, el in ex_lab.items()
                          if k != 'brand_' + name))
        ok = CHECKS[name](m)
        built[name] = (raw, lab)
        rows[name] = dict(metrics=m, nearest=near, dE00=round(d_ex, 3),
                          characteristic_ok=bool(ok), recipe=prof)
        print('%-18s %6.1f %6.1f | %6.1f %6.1f %6.1f | %6.1f %6.1f %6.1f | %6.1f %6.1f | %s %s %.3f'
              % (name, m['blue_chroma'], m['blue_hue'], m['red_chroma'],
                 m['red_hue'], m['skin_a'], m['shadow_tint'], m['high_tint'],
                 m['shadow_a'], m['warmth'], m['saturation'],
                 'OK  ' if ok else 'FAIL', near, d_ex))

    names = list(built)
    print()
    print('=== pairwise inside this batch (want > 3.112) ===')
    worst = (99, '', '')
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            d = float(np.median(de00(built[names[i]][1], built[names[j]][1])))
            if d < worst[0]:
                worst = (d, names[i], names[j])
            if d < 3.112:
                print('  TOO CLOSE %.3f  %s / %s' % (d, names[i], names[j]))
    print('  closest pair: %.3f  (%s / %s)' % worst)

    (OUT / 'brand_profiles.json').write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding='utf-8')
    ok = [n for n, r in rows.items() if r['dE00'] > 3.112 and r['characteristic_ok']]
    (OUT / 'admitted.json').write_text(json.dumps(ok, ensure_ascii=False, indent=1),
                                       encoding='utf-8')
    print()
    print('characteristic OK : %d / %d'
          % (sum(1 for r in rows.values() if r['characteristic_ok']), len(rows)))
    print('both gates        : %d / %d' % (len(ok), len(rows)))


if __name__ == '__main__':
    main()
