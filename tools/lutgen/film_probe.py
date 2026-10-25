#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""film_probe.py — 胶片表的对点测试：拿语义点位验「复刻成功没有」。

不问「像不像」，只问三件可测的事：

  1. IDENTITY  每张表在 13 个语义点位上把输入推了多远（dHue / dS / ΔL* / ΔB*）
  2. DISTINCT  两两表在同一组点位上的 ΔEab 均值。「平均 ΔE < 2 = 肉眼同一张表」，
               这是「没复刻成功」的硬定义 —— 真胶片之间的差异远大于此。
  3. GRAY      灰轴染色剖面。胶片的灰阶从来不是中性的（片基色 + 层间 H&D 差异），
               全库中位 4 级意味着这一层被完全抹掉了。

用法：
  python tools/lutgen/film_probe.py                     # 全库：灰轴 + 区分度 + 点位矩阵
  python tools/lutgen/film_probe.py --only portra400,fuji_velvia50 --detail
  python tools/lutgen/film_probe.py --pair portra400,kodak_ektar100
"""
import argparse
import math
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(BASE))
LOOKS = os.path.join(REPO, 'looks')
FACTORY = 'E:/NXWA/.tmp/cube_regression_2026-10-19'

N = 17
GRID = [16 * i for i in range(16)] + [255]

# 语义点位：覆盖肤色三档 / 天空两档 / 植被两档 / 暖色两档 / 重点色 / 中性三档
POINTS = [
    ('肤色-亮', (230, 190, 175)),
    ('肤色-中', (196, 150, 124)),
    ('肤色-深', (140, 98, 74)),
    ('天空-蓝', (86, 138, 200)),
    ('天空-阴', (176, 190, 204)),
    ('树叶',    (78, 108, 56)),
    ('草地',    (110, 132, 58)),
    ('夕照-暖', (240, 168, 118)),
    ('砖红',    (158, 86, 66)),
    ('品红',    (198, 92, 148)),
    ('中灰',    (128, 128, 128)),
    ('白',      (236, 232, 224)),
    ('黑',      (36, 30, 26)),
]


# 亲缘分组：同一族的真实胶片互相很接近（Portra 160/400/VC/NC），跨族差异大
# （Portra vs Velvia 是一眼可辨的两回事）。用实测 ΔE 对照这个先验，判「有没有把胶片分开」。
FAMILY = {
    'kodak-c41':   ['kodak_portra160', 'kodak_portra400', 'kodak_portra400vc',
                    'kodak_portra400nc', 'kodak_gold200', 'kodak_ultramax400',
                    'kodak_ektar100'],
    'kodak-slide': ['kodak_e100', 'kodak_kchrome25', 'kodak_kchrome64'],
    'fuji-c41':    ['fuji_superia400', 'fuji_superia400p', 'fuji_400h',
                    'fuji_proneg_std', 'fuji_proneg_hi'],
    'fuji-slide':  ['fuji_velvia50', 'fuji_velvia100', 'fuji_provia100f',
                    'fuji_astia100f'],
    'fuji-cine':   ['fuji_eterna500', 'fuji_classicchrome'],
    'agfa':        ['agfa_vista200', 'agfa_ultra100', 'agfa_rsx200'],
    'instant':     ['polaroid_600', 'polaroid_sx70', 'polaroid_itype',
                    'polaroid_expired'],
}


def lin(v):
    v = v / 255.0
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def lab(c):
    r, g, b = lin(c[0]), lin(c[1]), lin(c[2])
    x = 0.4124564 * r + 0.3575761 * g + 0.1804375 * b
    y = 0.2126729 * r + 0.7151522 * g + 0.0721750 * b
    z = 0.0193339 * r + 0.1191920 * g + 0.9503041 * b
    x, y, z = x / 0.95047, y, z / 1.08883

    def f(t):
        return t ** (1 / 3.0) if t > 0.008856 else 7.787 * t + 16 / 116.0
    fx, fy, fz = f(x), f(y), f(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def hsv(c):
    r, g, b = c[0] / 255.0, c[1] / 255.0, c[2] / 255.0
    mx, mn = max(r, g, b), min(r, g, b)
    d = mx - mn
    if d < 1e-9:
        return 0.0, 0.0, mx
    if mx == r:
        h = ((g - b) / d) % 6.0
    elif mx == g:
        h = (b - r) / d + 2.0
    else:
        h = (r - g) / d + 4.0
    return h * 60.0, d / mx, mx


def dhue(a, b):
    return (b - a + 180.0) % 360.0 - 180.0


class Lut:
    def __init__(self, path):
        raw = open(path, 'rb').read()
        self.v = raw[:N * N * N * 4]
        self.name = os.path.splitext(os.path.basename(path))[0]

    def at(self, r, g, b):
        fi = []
        for c in (r, g, b):
            c = 0.0 if c < 0 else (255.0 if c > 255 else c)
            i = min(N - 2, int(c // 16))
            fi.append((i, (c - GRID[i]) / (GRID[i + 1] - GRID[i])))
        (i0, fr), (i1, fg), (i2, fb) = fi
        out = [0.0, 0.0, 0.0]
        for db in (0, 1):
            wb = fb if db else 1.0 - fb
            for dg in (0, 1):
                wg = fg if dg else 1.0 - fg
                for dr in (0, 1):
                    wr = fr if dr else 1.0 - fr
                    k = (((min(N - 1, i2 + db) * N) + min(N - 1, i1 + dg)) * N
                         + min(N - 1, i0 + dr)) * 4
                    w = wr * wg * wb
                    out[0] += self.v[k] * w
                    out[1] += self.v[k + 1] * w
                    out[2] += self.v[k + 2] * w
        return out


def profile(lut):
    """13 个点位的 (dHue, dS, dL*, dB*) + 输出 Lab。"""
    rows = []
    for tag, p in POINTS:
        o = lut.at(*p)
        ih, isv, _ = hsv(p)
        oh, osv, _ = hsv(o)
        li, ai, bi = lab(p)
        lo, ao, bo = lab(o)
        rows.append({
            'tag': tag, 'in': p,
            'out': tuple(int(round(x)) for x in o),
            'dh': dhue(ih, oh) if max(o) - min(o) > 3 else 0.0,
            'ds': osv - isv, 'dl': lo - li, 'db': bo - bi,
            'lab': (lo, ao, bo),
        })
    return rows


def gray_profile(lut):
    out = []
    for i in range(N):
        v = GRID[i]
        c = lut.at(v, v, v)
        out.append((v, c, lab(c)))
    return out


def gray_gap(lut):
    return max(max(r[1]) - min(r[1]) for r in gray_profile(lut))


def de(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dir')
    ap.add_argument('--only')
    ap.add_argument('--detail', action='store_true')
    ap.add_argument('--pair', help='两张表逐点位对比：nameA,nameB')
    ap.add_argument('--top', type=int, default=12, help='区分度报告列前 N 对')
    a = ap.parse_args()

    global LOOKS
    if a.dir:
        LOOKS = os.path.abspath(a.dir)

    def load(n):
        # samsung_* 是只读参考表，强制走真镜像 —— looks/ 里那份曾被 retune_legacy 重算过
        if n.startswith('samsung_'):
            p = os.path.join(FACTORY, n + '.bin')
            if os.path.isfile(p):
                return Lut(p)
        p = os.path.join(LOOKS, n + '.bin')
        if os.path.isfile(p):
            return Lut(p)
        raise SystemExit('缺表：%s' % n)

    names = sorted(f[:-4] for f in os.listdir(LOOKS) if f.endswith('.bin'))
    if a.only:
        want = {s.strip() for s in a.only.split(',')}
        names = [n for n in names if n in want]

    # ---------- 逐点位对比 ----------
    if a.pair:
        na, nb = [s.strip() for s in a.pair.split(',')]
        la, lb = load(na), load(nb)
        pa, pb = profile(la), profile(lb)
        print('%-10s %-14s | %-22s | %-22s | %6s' %
              ('点位', '输入', na[:22], nb[:22], 'ΔEab'))
        des = []
        for x, y in zip(pa, pb):
            d = de(x['lab'], y['lab'])
            des.append(d)
            print('%-10s %-14s | %+5.1f° %+5.3f %+5.1f | %+5.1f° %+5.3f %+5.1f | %6.1f' %
                  (x['tag'], str(x['in']), x['dh'], x['ds'], x['dl'],
                   y['dh'], y['ds'], y['dl'], d))
        print('\n平均 ΔEab = %.1f ｜ 最大 %.1f ｜ >2 的点位 %d/%d' %
              (sum(des) / len(des), max(des), sum(1 for d in des if d > 2), len(des)))
        return 0

    # ---------- 全库 ----------
    luts = {n: Lut(os.path.join(LOOKS, n + '.bin')) for n in names}
    profs = {n: profile(l) for n, l in luts.items()}
    gaps = {n: gray_gap(l) for n, l in luts.items()}

    print('【灰轴染色 gray_gap】胶片味道的直接来源（原厂 samsung 69–79）')
    for n in ('samsung_a00', 'samsung_a01', 'samsung_a02'):
        try:
            print('  %-24s %4d' % (n, gray_gap(load(n))))
        except SystemExit:
            pass
    mine = {n: g for n, g in gaps.items() if not n.startswith('samsung_')}
    order = sorted(mine.items(), key=lambda kv: -kv[1])
    print('  %-24s %4d' % ('—— 我们的（降序）——', 0))
    for n, g in order[:a.top]:
        print('  %-24s %4d' % (n, g))
    print('  中位 %d ｜ 最大 %d ｜ ≤12 级 %d/%d 张' %
          (sorted(mine.values())[len(mine) // 2], order[0][1],
           sum(1 for g in mine.values() if g <= 12), len(mine)))

    # ---------- 区分度 ----------
    print('\n【区分度】两两表在 13 个点位上的平均 ΔEab —— <2 即肉眼同一张')
    pairs = []
    for i, x in enumerate(names):
        for y in names[i + 1:]:
            ds = [de(p['lab'], q['lab']) for p, q in zip(profs[x], profs[y])]
            pairs.append((sum(ds) / len(ds), x, y))
    pairs.sort()
    dup = [p for p in pairs if p[0] < 2.0]
    print('  共 %d 对 ｜ 平均 ΔE<2（重复）%d 对 ｜ <1（几乎相同）%d 对' %
          (len(pairs), len(dup), sum(1 for p in pairs if p[0] < 1.0)))

    # 亲缘分组：真胶片内部 / 跨系列，两档期望差距完全不同
    FAM = {}
    for fam, mem in FAMILY.items():
        for m in mem:
            FAM[m] = fam
    same = [d for d, x, y in pairs if FAM.get(x) and FAM.get(x) == FAM.get(y)]
    cross = [d for d, x, y in pairs if FAM.get(x) and FAM.get(y) and FAM[x] != FAM[y]]
    if same and cross:
        print('\n  【亲缘检验】同族应为 3–6，跨族应为 8–15（真实胶片的差异量级）')
        print('    同族对 %3d 个：平均 ΔE %.1f ｜ 中位 %.1f' %
              (len(same), sum(same) / len(same), sorted(same)[len(same) // 2]))
        print('    跨族对 %3d 个：平均 ΔE %.1f ｜ 中位 %.1f' %
              (len(cross), sum(cross) / len(cross), sorted(cross)[len(cross) // 2]))
        print('    区分比 = %.2f（跨族应 ≥ 同族的 2 倍）' %
              ((sum(cross) / len(cross)) / (sum(same) / len(same))))
        for fam in FAMILY:
            mem = [m for m in FAMILY[fam] if m in luts]
            if len(mem) < 2:
                continue
            intra = [de(p['lab'], q['lab']) for i, x in enumerate(mem) for y in mem[i + 1:]
                     for p, q in zip(profs[x], profs[y])]
            print('    %-14s %d 张，族内平均 ΔE %.1f' % (fam, len(mem), sum(intra) / len(intra)))

    print('\n  %-24s %-24s %6s  %s' % ('表 A', '表 B', 'ΔE', '关系'))
    for d, x, y in pairs[:a.top]:
        rel = '同族' if (FAM.get(x) and FAM.get(x) == FAM.get(y)) else (
            '跨族' if (FAM.get(x) and FAM.get(y)) else '')
        print('  %-24s %-24s %6.1f  %s' % (x, y, d, rel))

    # ---------- 点位矩阵 ----------
    if a.detail:
        for n in names:
            print('\n=== %s ===' % n)
            print('  %-10s %-16s %6s %6s %6s %6s' % ('点位', '输出', 'dHue', 'dS', 'dL*', 'dB*'))
            for r in profs[n]:
                print('  %-10s %-16s %+6.1f %+6.3f %+6.1f %+6.1f' %
                      (r['tag'], str(r['out']), r['dh'], r['ds'], r['dl'], r['db']))

    return 0


if __name__ == '__main__':
    sys.exit(main())
