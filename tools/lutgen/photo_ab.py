#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""photo_ab.py — 真实照片口径的冷暖/品红检验。

为什么不看灰卡：灰卡的 a*/b* 只反映 split toning，反映不了「整张照片看着发粉」。
发粉通常是「高饱和区红多黄少 + 整体低饱和」共同作用，只有真实色分布才看得出。

指标：
  dA  = 全图 a* 均值变化（正 = 往红/品红，负 = 往绿）
  dB  = 全图 b* 均值变化（正 = 往黄/暖，负 = 往蓝/冷）
  MI  = dA − dB  （品红指数：正 = 变粉/变品红，负 = 变黄绿）
  dL  = L* 均值变化
  dS  = 饱和度均值变化

用法（需要 numpy + Pillow，装在 E:/NXWA/.venv）:
  E:/NXWA/.venv/Scripts/python.exe photo_ab.py                 # looks/ 全部
  E:/NXWA/.venv/Scripts/python.exe photo_ab.py --dir <目录>
  E:/NXWA/.venv/Scripts/python.exe photo_ab.py --only kodak_portra400,fuji_velvia50
"""
import argparse
import os
import sys

import numpy as np
from PIL import Image

BASE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(BASE))
sys.path.insert(0, BASE)
from preview_photos import apply_lut, load_lut          # noqa: E402

PHOTOS = os.path.join(REPO, '..', '_photos')


def lab_stats(a):
    """a: (h,w,3) uint8 → (L均值, a均值, b均值, 饱和均值)。"""
    f = a.astype(np.float32) / 255.0
    lin = np.where(f <= 0.04045, f / 12.92, ((f + 0.055) / 1.055) ** 2.4)
    r, g, b = lin[:, :, 0], lin[:, :, 1], lin[:, :, 2]
    x = (0.4124564 * r + 0.3575761 * g + 0.1804375 * b) / 0.95047
    y = 0.2126729 * r + 0.7151522 * g + 0.0721750 * b
    z = (0.0193339 * r + 0.1191920 * g + 0.9503041 * b) / 1.08883

    def f_(t):
        return np.where(t > 0.008856, np.cbrt(t), 7.787 * t + 16 / 116.0)
    fx, fy, fz = f_(x), f_(y), f_(z)
    L = 116 * fy - 16
    A = 500 * (fx - fy)
    B = 200 * (fy - fz)
    mx = a.max(axis=2).astype(np.float32)
    mn = a.min(axis=2).astype(np.float32)
    S = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1), 0)
    return float(L.mean()), float(A.mean()), float(B.mean()), float(S.mean())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dir')
    ap.add_argument('--only')
    ap.add_argument('--photos')
    ap.add_argument('--width', type=int, default=240)
    ap.add_argument('--limit', type=int, default=16)
    a = ap.parse_args()

    looks = a.dir or os.path.join(REPO, 'looks')
    pdir = a.photos or PHOTOS
    files = sorted(f for f in os.listdir(pdir)
                   if f.lower().endswith(('.jpg', '.jpeg', '.png')))[:a.limit]
    if not files:
        print('没有照片：', pdir)
        return 2

    imgs = []
    for f in files:
        im = Image.open(os.path.join(pdir, f)).convert('RGB')
        h = max(1, int(im.height * a.width / float(im.width)))
        imgs.append(np.asarray(im.resize((a.width, h), Image.LANCZOS)))
    base = [lab_stats(x) for x in imgs]
    bL = np.mean([x[0] for x in base])
    bA = np.mean([x[1] for x in base])
    bB = np.mean([x[2] for x in base])
    bS = np.mean([x[3] for x in base])
    print('原图基线：L* %.1f  a* %+.1f  b* %+.1f  饱和 %.3f   （%d 张）'
          % (bL, bA, bB, bS, len(imgs)))
    print()

    names = sorted(f[:-4] for f in os.listdir(looks) if f.endswith('.bin'))
    if a.only:
        want = {s.strip() for s in a.only.split(',')}
        names = [n for n in names if n in want]

    rows = []
    for n in names:
        p = os.path.join(looks, n + '.bin')
        if not os.path.isfile(p):
            continue
        lut = load_lut(p)
        st = [lab_stats(apply_lut(x.astype(np.float32), lut)) for x in imgs]
        L = np.mean([x[0] for x in st])
        A = np.mean([x[1] for x in st])
        B = np.mean([x[2] for x in st])
        S = np.mean([x[3] for x in st])
        rows.append((n, L - bL, A - bA, B - bB, S - bS))

    # ★ 不能用品红指数 = dA−dB：黑白表会把原图的黄暖抹成 0，MI 算出来 +8.9，
    #   但它明明是中性灰。判品红必须看**输出绝对值**，关键是「黄余量」B_out − A_out：
    #   > +3 黄暖正常；0 ~ +3 偏冷/寡淡；< 0 才是真的缺黄（观感发粉/发品红）。
    print('%-22s %7s %7s %8s %6s %6s  %s'
          % ('表', 'A*出', 'B*出', '黄余量', 'dL*', 'dSat', '判读'))
    print('-' * 78)
    for n, dL, dA, dB, dS in sorted(rows, key=lambda r: (r[2] - r[3])):
        ao, bo = bA + dA, bB + dB
        yl = bo - ao
        tag = ''
        if abs(ao) < 0.6 and abs(bo) < 0.6:
            tag = '（中性，不判）'
        elif yl < 0:
            tag = '★缺黄→品红'
        elif yl < 2.5:
            tag = '偏粉/寡淡'
        elif yl > 12:
            tag = '过黄'
        print('%-22s %+7.1f %+7.1f %+8.1f %+6.1f %+6.3f  %s'
              % (n, ao, bo, yl, dL, dS, tag))
    return 0


if __name__ == '__main__':
    sys.exit(main())
