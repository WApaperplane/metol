#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Internet film-emulation CLUTs -> NX500 native Cr,Cb,Y slot table.

Source: G'MIC's colour-preset library (https://gmic.eu/color_presets/), which
republishes the widely used free film-simulation sets (RawTherapee / PIXLS.US
negative and slide CLUTs, Juan Melara print-film LUTs, Fujifilm X-Trans III
in-camera simulations). Presets are CC-BY-SA; stock names are trademarks used
only to say which film the table approximates.

Hald PNG layout (measured, not assumed)
--------------------------------------
512x512 PNG = 64^3 cube, decoded as ``idx = y*512 + x`` with
``r = idx%64, g = (idx//64)%64, b = idx//4096`` (red fastest).

Two wrong answers came before this one, both worth remembering:

1. The textbook Hald layout (64x64 tiles, ``r`` fastest in x) is off by 250/255.
   G'MIC's writer is not the textbook one.
2. Matching the PNG against G'MIC's own 13^3 ``.cube`` export is NOT a valid
   test of channel order. Both files store the cube in the same (blue-fastest)
   order, so the comparison "passes" at mean 2.2/255 with red and blue
   transposed. It flagged only as ``hue_err`` ~145 deg on every colour table in
   audit.py, while our own tables sit at 5-12 deg. Order was finally settled by
   looking at where primary colours land: Portra 400 must send
   (208,48,48) -> (251,65,23), not -> (113,80,227).

The PNG is still preferred over the published ``.cube`` for resolution only:
64 nodes per axis instead of 13, which matters on a print-film highlight
roll-off.

Output goes through ``native_codec.compile_uniform_rgb`` so the RGB->CrCbY
mapping, boundary extrapolation and slot padding stay identical to every other
table in ``looks/``.

Usage
-----
  python web_import.py --selftest
  python web_import.py --stage            # convert the whole curated catalogue
  python web_import.py --stage --only kodak_2383
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from native_codec import compile_uniform_rgb, record_native      # noqa: E402

BASE = Path(__file__).resolve().parent
CACHE = BASE / 'webcache'
STAGE = BASE / 'webstage'
URL = 'https://gmic.eu/color_presets/{cat}/clut/{preset}.png'
LEVEL = 64

# target file stem -> (category, preset, action, stock label)
# action: 'replace' overwrites an existing self-derived table, 'add' is new.
MANIFEST = {
    # --- cinema print film (the most-referenced "film look" transform) ---
    'kodak_2383':            ('print', 'kodak_2383_constlmap', 'add', 'Kodak 2383 print'),
    'kodak_2393':            ('print', 'kodak_2393_constlmap', 'add', 'Kodak 2393 print'),
    'fuji_3510':             ('print', 'fuji_3510_constlmap', 'add', 'Fuji 3510 print'),
    'fuji_3513':             ('print', 'fuji_3513_constlmap', 'add', 'Fuji 3513 print'),
    'print_2383_clip':       ('print', 'kodak_2383_constlclip', 'add', 'Kodak 2383 print / hard clip'),

    # --- colour negative ---
    'kodak_portra400':       ('negative_new', 'kodak_portra_400', 'replace', 'Kodak Portra 400'),
    'kodak_portra160':       ('negative_new', 'kodak_portra_160', 'add', 'Kodak Portra 160'),
    'kodak_portra800':       ('negative_new', 'kodak_portra_800', 'add', 'Kodak Portra 800'),
    'kodak_ektar100':        ('negative_color', 'kodak_ektar_100', 'replace', 'Kodak Ektar 100'),
    'fuji_400h':             ('negative_new', 'fuji_400h', 'replace', 'Fuji Pro 400H'),
    'fuji_160c':             ('negative_new', 'fuji_160c', 'add', 'Fuji Pro 160C'),
    'fuji_800z':             ('negative_new', 'fuji_800z', 'add', 'Fuji Pro 800Z'),
    'fuji_superia400':       ('negative_old', 'fuji_superia_400', 'replace', 'Fuji Superia 400'),
    'fuji_superia100':       ('negative_old', 'fuji_superia_100', 'add', 'Fuji Superia 100'),
    'fuji_superia1600':      ('negative_old', 'fuji_superia_1600', 'add', 'Fuji Superia 1600'),
    'agfa_ultra100':         ('negative_color', 'agfa_ultra_color_100', 'replace', 'Agfa Ultra Color 100'),
    'agfa_vista200':         ('negative_color', 'agfa_vista_200', 'add', 'Agfa Vista 200'),
    'kodak_elitecolor200':   ('negative_color', 'kodak_elite_color_200', 'add', 'Kodak Elite Color 200'),
    'kodak_elitecolor400':   ('negative_color', 'kodak_elite_color_400', 'add', 'Kodak Elite Color 400'),
    'lomo_redscale100':      ('negative_color', 'lomography_redscale_100', 'add', 'Lomography Redscale 100'),

    # --- colour slide / reversal ---
    'fuji_velvia50':         ('colorslide', 'fuji_velvia_50', 'replace', 'Fuji Velvia 50'),
    'fuji_velvia100':        ('colorslide', 'fuji_velvia_100_generic', 'add', 'Fuji Velvia 100'),
    'fuji_provia100f':       ('colorslide', 'fuji_provia_100f', 'replace', 'Fuji Provia 100F'),
    'fuji_astia100f':        ('colorslide', 'fuji_astia_100f', 'replace', 'Fuji Astia 100F'),
    'fuji_sensia100':        ('colorslide', 'fuji_sensia_100', 'add', 'Fuji Sensia 100'),
    'kodak_kchrome25':       ('colorslide', 'kodak_kodachrome_25', 'replace', 'Kodak Kodachrome 25'),
    'kodak_kchrome64':       ('colorslide', 'kodak_kodachrome_64', 'replace', 'Kodak Kodachrome 64'),
    'kodak_kchrome200':      ('colorslide', 'kodak_kodachrome_200', 'add', 'Kodak Kodachrome 200'),
    'kodak_ektachrome100':   ('colorslide', 'kodak_e-100_gx_ektachrome_100', 'add', 'Kodak Ektachrome E100GX'),
    'kodak_elitechrome200':  ('colorslide', 'kodak_elite_chrome_200', 'add', 'Kodak Elite Chrome 200'),
    'slide_precisa100':      ('colorslide', 'agfa_precisa_100', 'replace', 'Agfa Precisa 100'),
    'lomo_xpro_slide200':    ('colorslide', 'lomography_x-pro_slide_200', 'add', 'Lomography X-Pro 200'),

    # --- black and white ---
    'mono_acros':            ('bw', 'fuji_neopan_acros_100', 'replace', 'Fuji Neopan Acros 100'),
    'mono_trix400':          ('bw', 'kodak_tri-x_400', 'add', 'Kodak Tri-X 400'),
    'mono_tmax100':          ('bw', 'kodak_t-max_100', 'add', 'Kodak T-Max 100'),
    'mono_tmax3200':         ('bw', 'kodak_t-max_3200', 'add', 'Kodak T-Max 3200'),
    'mono_hp5':              ('bw', 'ilford_hp_5_plus_400', 'add', 'Ilford HP5 Plus 400'),
    'mono_delta100':         ('bw', 'ilford_delta_100', 'add', 'Ilford Delta 100'),
    'mono_delta3200':        ('bw', 'ilford_delta_3200', 'add', 'Ilford Delta 3200'),
    'mono_fp4':              ('bw', 'ilford_fp_4_plus_125', 'add', 'Ilford FP4 Plus 125'),
    'mono_panf50':           ('bw', 'ilford_pan_f_plus_50', 'add', 'Ilford Pan F Plus 50'),
    'mono_xp2':              ('bw', 'ilford_xp_2', 'add', 'Ilford XP2 Super'),
    'mono_apx100':           ('bw', 'agfa_apx_100', 'add', 'Agfa APX 100'),
    'mono_hie_infra':        ('bw', 'kodak_hie_hs_infra', 'add', 'Kodak HIE infrared'),
    'mono_retro80s':         ('bw', 'rollei_retro_80s', 'add', 'Rollei Retro 80S'),

    # --- instant ---
    'polaroid_669':          ('instant_pro', 'polaroid_669', 'add', 'Polaroid 669'),
    'polaroid_690':          ('instant_pro', 'polaroid_690', 'add', 'Polaroid 690'),
    'polaroid_665':          ('instant_pro', 'polaroid_665', 'add', 'Polaroid 665'),
    'fuji_fp100c':           ('instant_pro', 'fuji_fp-100c', 'add', 'Fuji FP-100C'),
    'fuji_fp3000b':          ('instant_pro', 'fuji_fp-3000b', 'add', 'Fuji FP-3000B'),
    'polaroid_polachrome':   ('colorslide', 'polaroid_polachrome', 'add', 'Polaroid Polachrome'),
    'polaroid_timezero':     ('instant_consumer', 'polaroid_time_zero_expired', 'add', 'Polaroid Time-Zero (expired)'),

    # --- Fujifilm in-camera film simulations (their own colour science) ---
    'fuji_classicchrome':    ('fujixtransiii', 'fuji_xtrans_iii_classic_chrome', 'replace', 'Fuji Classic Chrome'),
    'fuji_pro_neg_hi':       ('fujixtransiii', 'fuji_xtrans_iii_pro_neg_hi', 'add', 'Fuji Pro Neg Hi'),
    'fuji_pro_neg_std':      ('fujixtransiii', 'fuji_xtrans_iii_pro_neg_std', 'add', 'Fuji Pro Neg Std'),
    'fuji_xtrans_provia':    ('fujixtransiii', 'fuji_xtrans_iii_provia', 'add', 'Fuji Provia (in-camera)'),
    'fuji_xtrans_velvia':    ('fujixtransiii', 'fuji_xtrans_iii_velvia', 'add', 'Fuji Velvia (in-camera)'),
    'fuji_xtrans_acros':     ('fujixtransiii', 'fuji_xtrans_iii_acros', 'add', 'Fuji Acros (in-camera)'),
    'fuji_xtrans_sepia':     ('fujixtransiii', 'fuji_xtrans_iii_sepia', 'add', 'Fuji Sepia (in-camera)'),
}


# Judged too extreme on real photos to sit in a camera menu: redscale rotates
# every hue hard, expired Time-Zero lifts black to 102/255. Both stay in
# webstage/ as candidates; neither is deployed.
SKIP = {'lomo_redscale100', 'polaroid_timezero'}

# Additions that actually get deployed. Everything else stays staged so the
# look menu does not grow without a decision.
DEPLOY_ADD = {
    # cinema print stock
    'kodak_2383', 'kodak_2393', 'fuji_3510', 'fuji_3513',
    # colour negative not previously covered
    'kodak_portra160', 'kodak_portra800', 'fuji_160c', 'fuji_800z',
    'fuji_superia100', 'agfa_vista200', 'kodak_elitecolor200',
    # slide
    'fuji_velvia100', 'kodak_kchrome200', 'kodak_ektachrome100', 'lomo_xpro_slide200',
    # black and white
    'mono_trix400', 'mono_tmax100', 'mono_hp5', 'mono_delta100', 'mono_delta3200',
    'mono_fp4', 'mono_panf50', 'mono_hie_infra',
    # instant
    'polaroid_669', 'polaroid_690', 'fuji_fp100c', 'fuji_fp3000b',
    # Fujifilm's own in-camera simulations
    'fuji_pro_neg_hi', 'fuji_pro_neg_std', 'fuji_xtrans_provia',
}


def fetch(cat: str, preset: str) -> Path:
    CACHE.mkdir(exist_ok=True)
    dst = CACHE / ('%s__%s.png' % (cat, preset))
    if not dst.is_file() or dst.stat().st_size < 10000:
        url = URL.format(cat=cat, preset=preset)
        print('  GET %s' % url)
        with urllib.request.urlopen(url, timeout=60) as r:
            dst.write_bytes(r.read())
    return dst


def decode(png: Path, level: int = LEVEL) -> np.ndarray:
    """Hald PNG -> cube[r, g, b, 3] floats 0..255."""
    a = np.asarray(Image.open(png).convert('RGB')).astype(np.float32)
    side = a.shape[0]
    if a.shape[1] != side or side * side != level ** 3:
        raise ValueError('%s: %dx%d does not hold a %d^3 cube'
                         % (png.name, side, a.shape[1], level))
    flat = a.reshape(-1, 3)
    cube = np.empty((level, level, level, 3), np.float32)
    idx = np.arange(level ** 3)
    cube[idx % level, (idx // level) % level, idx // (level * level)] = flat[idx]
    return cube


def to_slot(cube: np.ndarray) -> bytes:
    n = cube.shape[0]
    # compile_uniform_rgb indexes nodes as [b][g][r] with r fastest.
    nodes = cube.transpose(2, 1, 0, 3).reshape(-1, 3).tolist()
    return compile_uniform_rgb(nodes, n)


def selftest() -> int:
    from native_codec import NATIVE
    N = 64
    g = np.arange(N, dtype=np.float32) * (255.0 / (N - 1))
    ident = np.empty((N, N, N, 3), np.float32)
    ident[..., 0] = g[:, None, None]
    ident[..., 1] = g[None, :, None]
    ident[..., 2] = g[None, None, :]
    got = to_slot(ident)
    ref = (BASE.parent.parent / 'looks' / 'identity17.bin').read_bytes()[:19652]
    # identity17.bin predates slotwrap(): its 60-byte pad is all zero while
    # slotwrap repeats the last node three times. The table body is what matters.
    bad = sum(1 for a, b in zip(got[:19652], ref) if a != b)
    print('identity %d^3 -> native: %d bytes, table mismatch %d  %s'
          % (N, len(got), bad, 'OK' if bad == 0 else 'FAIL'))
    if bad:
        for i in range(0, len(got), 4):
            if got[i:i + 4] != ref[i:i + 4]:
                print('  first diff at node %d: %s vs %s'
                      % (i // 4, got[i:i + 4].hex(), ref[i:i + 4].hex()))
                break
    return 0 if bad == 0 else 1


def deploy(looks: Path, backup: Path) -> int:
    """Copy staged tables into looks/, backing up anything they overwrite."""
    looks.mkdir(parents=True, exist_ok=True)
    backup.mkdir(parents=True, exist_ok=True)
    done = []
    for stem, (_cat, _preset, action, label) in MANIFEST.items():
        if stem in SKIP:
            continue
        if action != 'replace' and stem not in DEPLOY_ADD:
            continue
        src = STAGE / (stem + '.bin')
        if not src.is_file():
            print('  MISSING staged %s' % stem)
            continue
        dst = looks / (stem + '.bin')
        raw = src.read_bytes()
        if dst.is_file():
            (backup / (stem + '.bin')).write_bytes(dst.read_bytes())
        dst.write_bytes(raw)
        record_native(dst, raw)          # keeps encoding.json honest for readers
        done.append(dict(file=dst.name, action=action, label=label,
                         replaced=dst.name in {p.name for p in backup.glob('*.bin')}))
        print('  %-7s %-24s %s' % (action, stem, label))
    return len(done)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--selftest', action='store_true')
    ap.add_argument('--stage', action='store_true')
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--only', default='')
    ap.add_argument('--looks', default=str(BASE.parent.parent / 'looks'))
    ap.add_argument('--backup', default=r'E:/NXWA/_looks_before_web_20261025')
    args = ap.parse_args()

    if args.apply:
        n = deploy(Path(args.looks), Path(args.backup))
        print('\n%d tables written to %s (originals in %s)' % (n, args.looks, args.backup))
        return 0

    if args.selftest or not (args.stage):
        return selftest() or 0

    STAGE.mkdir(exist_ok=True)
    only = {s.strip() for s in args.only.split(',') if s.strip()}
    rows = []
    for stem, (cat, preset, action, label) in MANIFEST.items():
        if only and stem not in only:
            continue
        png = fetch(cat, preset)
        cube = decode(png)
        raw = to_slot(cube)
        out = STAGE / (stem + '.bin')
        out.write_bytes(raw)
        record_native(out, raw)          # without this every reader assumes legacy RGB
        rows.append(dict(file=stem + '.bin', preset=preset, category=cat,
                         action=action, label=label, source=URL.format(cat=cat, preset=preset),
                         bytes=len(raw)))
        print('  %-24s <- %-32s %s' % (stem, preset, 'replace' if action == 'replace' else 'add'))
    (STAGE / 'manifest.json').write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding='utf-8')
    print('\n%d tables staged in %s' % (len(rows), STAGE))
    return 0


if __name__ == '__main__':
    sys.exit(main())
