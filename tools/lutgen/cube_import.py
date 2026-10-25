#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任意 .cube（显示参考输入）-> 原生 Cr,Cb,Y 槽表，并给出去重判据。

只处理 domain 0..1、输入是显示参考（sRGB/Standard）的表。日志域输入的表
（V-Log / L-Log / Cineon）不能直接吃：我们的源是相机 JPEG，前面没有对数
解码，硬套会得到双重解码的错色。这类表要么先用 Panasonic S2V 链烘成
Standard 输入（见 merge_standard_luts.py），要么不要用。

用法:
  python cube_import.py a.cube b.cube --out webstage2 --names leica_m9,hasselblad_std
  python cube_import.py --dir some/dir --out webstage2
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.stdout.reconfigure(encoding='utf-8')
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import native_codec as nc                                      # noqa: E402
from colour_metrics import metrics                             # noqa: E402
from similarity_audit import (apply_slot, de00, load_native, probe_set,  # noqa: E402
                              rgb_to_lab, REPO)


def parse_cube(path):
    n = None
    dmin, dmax = (0.0, 0.0, 0.0), (1.0, 1.0, 1.0)
    vals = []
    for line in open(path, encoding='utf-8', errors='replace'):
        s = line.strip()
        if not s or s.startswith('#'):
            continue
        if s.startswith('LUT_3D_SIZE'):
            n = int(s.split()[1]); continue
        if s.startswith('DOMAIN_MIN'):
            dmin = tuple(float(v) for v in s.split()[1:4]); continue
        if s.startswith('DOMAIN_MAX'):
            dmax = tuple(float(v) for v in s.split()[1:4]); continue
        if s.startswith(('TITLE', 'LUT_1D_SIZE', 'LUT_1D', 'LUT_3D_INPUT_RANGE')):
            continue
        t = s.split()
        if len(t) >= 3:
            try:
                vals.append([float(t[0]), float(t[1]), float(t[2])])
            except ValueError:
                pass
    if n is None:
        raise ValueError('%s: no LUT_3D_SIZE' % path)
    if len(vals) != n ** 3:
        raise ValueError('%s: %d nodes, expected %d' % (path, len(vals), n ** 3))
    if tuple(dmin) != (0.0, 0.0, 0.0) or tuple(dmax) != (1.0, 1.0, 1.0):
        raise ValueError('%s: domain %s..%s not supported (would need rescaling)'
                         % (path, dmin, dmax))
    # .cube 平铺顺序 = r 最快、其次 g、再次 b ⇒ 自然 reshape 就是 [b][g][r]，
    # 正是 compile_uniform_rgb 要的排列，不要再 transpose。
    nodes = np.array(vals, np.float32).reshape(-1, 3) * 255.0
    return n, nodes


def convert(path, n, nodes):
    return nc.compile_uniform_rgb(nodes.tolist(), n, boundary='linear')


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('cubes', nargs='*')
    ap.add_argument('--dir')
    ap.add_argument('--out', required=True)
    ap.add_argument('--names', default='')
    args = ap.parse_args()

    files = list(args.cubes)
    if args.dir:
        files += [str(p) for p in sorted(Path(args.dir).glob('*.cube'))]
    if not files:
        print('no input'); return 2

    names = [s.strip() for s in args.names.split(',') if s.strip()]
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)

    existing = {p.stem: load_native(p) for p in sorted((REPO / 'looks').glob('*.bin'))}
    pts, _ = probe_set()
    ex_lab = {k: rgb_to_lab(apply_slot(pts, v)) for k, v in existing.items()}

    print('%-18s %4s %6s %6s %6s | %-20s %6s' %
          ('name', 'n', 'sat', 'contr', 'warm', 'nearest existing', 'dE00'))
    rows = []
    for i, f in enumerate(files):
        stem = names[i] if i < len(names) else Path(f).stem
        try:
            n, nodes = parse_cube(f)
            raw = convert(f, n, nodes)
        except Exception as e:                                  # noqa: BLE001
            print('%-18s SKIP  %s' % (stem, e)); continue
        target = out / (stem + '.bin')
        target.write_bytes(raw)
        nc.record_native(target, raw)
        view = np.frombuffer(raw[:19652], np.uint8).reshape(17, 17, 17, 4)[:, :, :, :3].astype(float)
        m = metrics(view)
        lab = rgb_to_lab(apply_slot(pts, view))
        d, near = min(((float(np.median(de00(lab, el))), k) for k, el in ex_lab.items()))
        print('%-18s %4d %6.1f %6.2f %6.2f | %-20s %6.2f  %s' %
              (stem, n, m['saturation'], m['contrast'], m['warmth'], near, d,
               'DISTINCT' if d > 3.112 else 'DUPLICATE'))
        rows.append(dict(name=stem, source=str(f), cube_size=n, metrics=m,
                         nearest=near, dE00=round(d, 3),
                         distinct=bool(d > 3.112)))
    (out / 'import_report.json').write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding='utf-8')
    print('\n%d 张，去重门槛 3.112；DISTINCT 的才值得上机' % len(rows))
    return 0


if __name__ == '__main__':
    sys.exit(main())
