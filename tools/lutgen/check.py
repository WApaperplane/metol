#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对生成的 .bin 做物理合理性检查：灰阶单调性、动态范围、色相偏移。"""
import math
import os

BASE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(BASE))
BIN = os.path.join(REPO, 'looks')
N = 17


def read_lut(path):
    return open(path, 'rb').read()[:N * N * N * 4]


def coord(v):
    if v <= 0:
        return 0, 0.0
    if v >= 255:
        return 16, 0.0
    i = min(15, v // 16)
    lo = 16 * i
    hi = 16 * (i + 1) if i < 15 else 255
    return i, (v - lo) / float(hi - lo)


def sample(lut, r, g, b):
    ri, rt = coord(r)
    gi, gt = coord(g)
    bi, bt = coord(b)
    out = [0.0, 0.0, 0.0]
    for db in (0, 1):
        for dg in (0, 1):
            for dr in (0, 1):
                ii, jj, kk = min(16, ri + dr), min(16, gi + dg), min(16, bi + db)
                o = ((kk * N + jj) * N + ii) * 4
                w = ((rt if dr else 1 - rt) * (gt if dg else 1 - gt) * (bt if db else 1 - bt))
                out[0] += lut[o] * w
                out[1] += lut[o + 1] * w
                out[2] += lut[o + 2] * w
    return out


def luma(o):
    return 0.299 * o[0] + 0.587 * o[1] + 0.114 * o[2]


def hue_of(o):
    r, g, b = o
    mx, mn = max(o), min(o)
    d = mx - mn
    if d < 1e-6:
        return None
    if mx == r:
        h = ((g - b) / d) % 6
    elif mx == g:
        h = (b - r) / d + 2
    else:
        h = (r - g) / d + 4
    return h * 60


rows = []
import json
NAMES = [k for k in json.load(open(os.path.join(BASE,'films.json'), encoding='utf-8')) if not k.startswith('_')]
for fn in sorted(NAMES):
    fn = fn + '.bin'
    lut = read_lut(os.path.join(BIN, fn))
    # 灰阶单调性
    ys = [luma(sample(lut, v, v, v)) for v in range(0, 256, 3)]
    drops = sum(1 for a, b in zip(ys, ys[1:]) if b < a - 0.6)
    # 动态范围（5% → 95%）
    lo = luma(sample(lut, 13, 13, 13))
    hi = luma(sample(lut, 242, 242, 242))
    dr = hi - lo
    # 色相偏移：红黄绿青蓝品 六个主色
    shifts = []
    for base_h, rgb in ((0, (200, 40, 40)), (60, (200, 190, 40)), (120, (50, 180, 60)),
                        (180, (40, 180, 190)), (240, (40, 70, 200)), (300, (180, 40, 170))):
        o = sample(lut, *rgb)
        h = hue_of(o)
        if h is not None:
            d = (h - base_h + 180) % 360 - 180
            shifts.append(d)
    max_shift = max(abs(s) for s in shifts) if shifts else 0
    rows.append((fn[:-4], drops, dr, max_shift))

print(f'{"name":22s} {"反转":>4s} {"动态范围":>8s} {"最大色相偏":>10s}  判定')
bad = 0
for name, drops, dr, ms in rows:
    flag = 'OK'
    if drops > 0:
        flag = '★反转'
        bad += 1
    elif dr < 180:
        flag = '★范围窄'
        bad += 1
    print(f'{name:22s} {drops:4d} {dr:8.0f} {ms:9.0f}°  {flag}')
print(f'\n{len(rows)} 张，异常 {bad} 张')
