#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""color_def.py — 反推一张 LUT 的「色彩定义」，纯标准库，零依赖。

用途：不问「这表像不像 Portra」，只问「这表把哪些色相往哪推、冷暖怎么分配」。
原厂表（samsung_a00/01/02）本身就是三星对色彩的定义，用它当基准反查我们的表。

度量全部在 CIELAB(D65) 里做，因为冷暖有严格定义：
    b* > 0 = 黄（暖）｜b* < 0 = 蓝（冷）
    a* > 0 = 红       ｜a* < 0 = 绿
「调子偏暖」不是 R 高，是 b* 上移。用 R/G 比值判冷暖必然把饱和度误判成色温
（这正是 audit.py warm_red 只能当粗筛的原因）。

四组签名
--------
1. gray      灰轴 17 点的 L*/a*/b*         → 白点、黑点、中间调的冷暖基线
2. ring      24 色相 × 4 种 (s,v) 条件的 dHue/dSat/dL/dB*  → 色相环怎么被重排
3. envelope  每色相可达的最高输出饱和      → 色彩密度上限（三星的蓝封顶现象）
4. split     暗部/中间调/高光的 b* 差      → 冷暖是否按亮度分层（电影调色手法）

用法：
  python tools/lutgen/color_def.py                      # 原厂三张 + 全部 look 的摘要
  python tools/lutgen/color_def.py --ring samsung_a00    # 单表的完整色相环
  python tools/lutgen/color_def.py --ring samsung_a00,kodak_portra400 --blue
  python tools/lutgen/color_def.py --json out.json
"""
import argparse
import json
import math
import os
import sys
from native_codec import space_for, sample_rgb, NATIVE

N = 17
GRID = [16 * i for i in range(16)] + [255]
BASE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(BASE))
LOOKS = os.path.join(REPO, 'looks')


# ---------- 色彩空间 ----------
def srgb_lin(v):
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def rgb_to_lab(r, g, b):
    """r,g,b: 0..255 → L*, a*, b* (D65)。"""
    r, g, b = srgb_lin(r / 255.0), srgb_lin(g / 255.0), srgb_lin(b / 255.0)
    x = 0.4124564 * r + 0.3575761 * g + 0.1804375 * b
    y = 0.2126729 * r + 0.7151522 * g + 0.0721750 * b
    z = 0.0193339 * r + 0.1191920 * g + 0.9503041 * b
    x, y, z = x / 0.95047, y / 1.00000, z / 1.08883

    def f(t):
        return t ** (1.0 / 3.0) if t > 0.008856 else 7.787 * t + 16.0 / 116.0
    fx, fy, fz = f(x), f(y), f(z)
    return 116.0 * fy - 16.0, 500.0 * (fx - fy), 200.0 * (fy - fz)


def rgb_to_hsv(r, g, b):
    r, g, b = r / 255.0, g / 255.0, b / 255.0
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
    return h * 60.0, d / mx if mx > 0 else 0.0, mx


def hsv_to_rgb255(h, s, v):
    h = h % 360.0
    c = v * s
    x = c * (1 - abs((h / 60.0) % 2 - 1))
    m = v - c
    if h < 60:
        rr, gg, bb = c, x, 0
    elif h < 120:
        rr, gg, bb = x, c, 0
    elif h < 180:
        rr, gg, bb = 0, c, x
    elif h < 240:
        rr, gg, bb = 0, x, c
    elif h < 300:
        rr, gg, bb = x, 0, c
    else:
        rr, gg, bb = c, 0, x
    return (rr + m) * 255.0, (gg + m) * 255.0, (bb + m) * 255.0


def dhue(a, b):
    return (b - a + 180.0) % 360.0 - 180.0


# ---------- 读表与插值 ----------
class Lut:
    def __init__(self, path):
        with open(path, 'rb') as source:
            raw = source.read()
        if len(raw) not in (19712, 19652):
            raise ValueError('%s 长度 %d 异常' % (path, len(raw)))
        self.v = raw[:N * N * N * 4]
        self.space = space_for(path, raw)
        self.name = os.path.splitext(os.path.basename(path))[0]

    def at(self, r, g, b):
        """三线性插值，与机身/驱动一致。"""
        if self.space == NATIVE:
            return sample_rgb(self.v, self.space, (r,g,b))
        fi = []
        for c in (r, g, b):
            c = 0.0 if c < 0 else (255.0 if c > 255 else c)
            # 末段 240→255 跨 15 而非 16，f=(255-240)/15=1.0 正好命中末格点
            i = min(N - 2, int(c // 16))
            lo = GRID[i]
            fi.append((i, (c - lo) / (GRID[i + 1] - lo)))
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


# ---------- 1. 灰轴 ----------
def gray(lut):
    rows = []
    for i in range(N):
        v = GRID[i]
        o = lut.at(v, v, v)
        L, a, b = rgb_to_lab(*o)
        rows.append((v, o, L, a, b))
    return rows


# ---------- 2. 色相环 ----------
RING = [0, 15, 30, 45, 60, 90, 120, 150, 180, 195, 210, 225, 240, 255, 270, 285, 300, 315, 330, 345]
CONDS = [('lo-dark', 0.40, 0.35), ('lo-lit', 0.40, 0.80),
         ('hi-dark', 0.85, 0.35), ('hi-lit', 0.85, 0.80)]


def ring(lut, h_list=RING, conds=CONDS):
    out = {}
    for label, s, v in conds:
        rows = []
        for h in h_list:
            i = hsv_to_rgb255(h, s, v)
            o = lut.at(*i)
            ih, isv, iv = rgb_to_hsv(*i)
            oh, osv, ov = rgb_to_hsv(*o)
            Lin, ain, bin_ = rgb_to_lab(*i)
            Lout, aout, bout = rgb_to_lab(*o)
            rows.append({
                'h': h, 'dh': dhue(ih, oh) if max(o) - min(o) > 3 else 0.0,
                's_in': round(isv, 3), 's_out': round(osv, 3),
                'ds': round(osv - isv, 3), 'dl': round(Lout - Lin, 2),
                'dlab': [round(aout - ain, 2), round(bout - bin_, 2)],
                'db': round(bout - bin_, 2),
            })
        out[label] = rows
    return out


# ---------- 3. 饱和包络 ----------
def envelope(lut, h_list=RING, v=0.9):
    """输入 s=0.95 的各色相，输出饱和 + 输出可用的最高饱和。"""
    rows = []
    for h in h_list:
        i = hsv_to_rgb255(h, 0.95, v)
        o = lut.at(*i)
        oh, osv, _ = rgb_to_hsv(*o)
        # 该色相附近实际塞满的最高饱和：扫描网格里 hue 相近的格点
        best = 0.0
        for b in range(N):
            for g in range(N):
                for r in range(N):
                    k = (((b * N) + g) * N + r) * 4
                    cr, cg, cb = lut.v[k], lut.v[k + 1], lut.v[k + 2]
                    if max(cr, cg, cb) - min(cr, cg, cb) < 8:
                        continue
                    ch, cs, _ = rgb_to_hsv(cr, cg, cb)
                    if abs(dhue(h, ch)) <= 15.0 and cs > best:
                        best = cs
        rows.append((h, round(osv, 3), round(best, 3)))
    return rows


# ---------- 4. 冷暖分层 ----------
def split(lut, nbin=6):
    """按输出 L* 分箱统计 b* 的中位数 —— 冷暖是否随亮度分层。"""
    buckets = {}
    for b in range(N):
        for g in range(N):
            for r in range(N):
                k = (((b * N) + g) * N + r) * 4
                cr, cg, cb = lut.v[k], lut.v[k + 1], lut.v[k + 2]
                if max(cr, cg, cb) - min(cr, cg, cb) > 14:      # 只统计近中性
                    continue
                L, a, bb = rgb_to_lab(cr, cg, cb)
                if L < 6 or L > 96:
                    continue
                i = int(L / (100.0 / nbin))
                buckets.setdefault(i, []).append((L, a, bb))
    rows = []
    for i in sorted(buckets):
        v = buckets[i]
        v.sort()
        med = v[len(v) // 2]
        rows.append((round(med[0], 1), round(sum(x[1] for x in v) / len(v), 2),
                     round(sum(x[2] for x in v) / len(v), 2), len(v)))
    return rows


# ---------- 主色角点 ----------
CORNERS = [('R', 255, 0, 0), ('Y', 255, 255, 0), ('G', 0, 255, 0), ('C', 0, 255, 255),
           ('B', 0, 0, 255), ('M', 255, 0, 255),
           ('YL', 200, 190, 40), ('SKIN', 200, 150, 130), ('SKY', 80, 130, 200),
           ('FOLIAGE', 70, 100, 50), ('DARK', 40, 35, 30), ('HI-WARM', 240, 230, 210)]


def corners(lut):
    rows = []
    for tag, r, g, b in CORNERS:
        o = lut.at(r, g, b)
        ih, isv, _ = rgb_to_hsv(r, g, b)
        oh, osv, _ = rgb_to_hsv(*o)
        Lin, ain, bin_ = rgb_to_lab(r, g, b)
        Lout, aout, bout = rgb_to_lab(*o)
        rows.append((tag, (r, g, b), tuple(int(round(x)) for x in o),
                     round(dhue(ih, oh), 1) if max(o) - min(o) > 3 else 0.0,
                     round(osv - isv, 3), round(Lout - Lin, 1), round(bout - bin_, 1)))
    return rows


def fmt_row(vals, widths):
    return ' '.join(str(v).rjust(w) if not isinstance(v, str) else v.ljust(w)
                    for v, w in zip(vals, widths))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ring', help='逗号分隔的表名，打印完整色相环')
    ap.add_argument('--dir')
    ap.add_argument('--json')
    a = ap.parse_args()

    global LOOKS
    if a.dir:
        LOOKS = os.path.abspath(a.dir)

    def path(n):
        return os.path.join(LOOKS, n + '.bin')

    names = sorted(f[:-4] for f in os.listdir(LOOKS) if f.endswith('.bin'))

    # ---- 摘要：冷暖基线 ----
    print('【冷暖基线】灰轴 b*（+黄/暖，-蓝/冷）｜a*（+红，-绿）｜L* 落差')
    print('  %-22s %7s %7s %7s %7s %7s %7s  %s' %
          ('name', 'L*黑', 'L*白', 'b*暗', 'b*中', 'b*亮', 'a*中', '暖-冷斜率'))
    summ = {}
    for n in names:
        lut = Lut(path(n))
        gr = gray(lut)
        sp = split(lut)
        if len(sp) < 3:
            continue
        b_mid = sp[len(sp) // 2]
        # 暖-冷斜率：b*(高光) - b*(暗部)，>0 高光偏暖（分离色调），<0 相反
        slope = sp[-1][2] - sp[0][2]
        summ[n] = {'lab': [[round(x, 2) for x in g[2:]] for g in gr],
                   'split': sp, 'slope': round(slope, 2),
                   'b_mid': b_mid[2], 'a_mid': b_mid[1]}
        print('  %-22s %7.1f %7.1f %+7.2f %+7.2f %+7.2f %+7.2f   %+6.2f' %
              (n, gr[0][2], gr[-1][2], sp[0][2], b_mid[2], sp[-1][2], b_mid[1], slope))

    # ---- 色相环 ----
    if a.ring:
        for n in a.ring.split(','):
            n = n.strip()
            if not os.path.isfile(path(n)):
                print('\n缺表：', n)
                continue
            lut = Lut(path(n))
            print('\n【色相环】%s  dHue（负=向红/黄侧转）｜dS ｜dL*｜dB*' % n)
            rg = ring(lut)
            for label, _, _ in CONDS:
                print('  -- %s --' % label)
                print('   %5s %7s %7s %7s %6s' % ('h_in', 'dHue', 'dS', 'dL*', 'dB*'))
                for r in rg[label]:
                    print('   %5d %+7.1f %+7.3f %+7.1f %+6.1f' %
                          (r['h'], r['dh'], r['ds'], r['dl'], r['db']))
            print('  -- 饱和包络 (v=0.90) --')
            print('   %5s %8s %8s' % ('h_in', 's_out', 's_max'))
            for h, so, sm in envelope(lut):
                print('   %5d %8.3f %8.3f' % (h, so, sm))
            print('  -- 主色角点 --')
            print('   %-8s %-16s %-16s %7s %7s %6s %6s' %
                  ('tag', 'in', 'out', 'dHue', 'dS', 'dL*', 'dB*'))
            for tag, i, o, d, ds, dl, db in corners(lut):
                print('   %-8s %-16s %-16s %+7.1f %+7.3f %+6.1f %+6.1f' %
                      (tag, str(i), str(o), d, ds, dl, db))

    if a.json:
        with open(a.json, 'w', encoding='utf-8') as f:
            json.dump(summ, f, ensure_ascii=False, indent=1)
        print('\n→ %s' % a.json)
    return 0


if __name__ == '__main__':
    sys.exit(main())
