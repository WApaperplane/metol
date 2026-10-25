#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用真实照片渲染 LUT 对比图（检验实际观感，而非色卡数值）。

用法：
  python preview_photos.py <照片> <输出png> [lut名 ...]
  python preview_photos.py E:/NXWA/_photos/SAM_0001.JPG out.png ricoh_positive pentax_reversal
不指定 lut 名时渲染 looks/ 下全部（可用于回归检查）。

格点与硬件一致：[0,16,...,240,255]（前 16 段等距 16，末段 15），三线性插值。
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
LOOKS = os.path.join(REPO, 'looks')

N = 17
GRID = np.array([16 * i for i in range(16)] + [255], dtype=np.float64)
FONT = 'C:/Windows/Fonts/msyhbd.ttc'


def load_lut(path):
    raw = np.frombuffer(open(path, 'rb').read(), dtype=np.uint8)[:N * N * N * 4]
    tbl = raw.reshape(N, N, N, 4)[:, :, :, :3]      # [b][g][r][ch]
    return tbl.astype(np.float32)


def apply_lut(img, lut):
    """img: (h,w,3) float32 0..255 → (h,w,3) uint8"""
    ia, fa = [], []
    for c in range(3):
        v = img[:, :, c]
        i = np.clip(np.searchsorted(GRID, v, side='right') - 1, 0, N - 2)
        lo, hi = GRID[i], GRID[i + 1]
        ia.append(i)
        fa.append(np.clip((v - lo) / (hi - lo), 0.0, 1.0))
    r0, g0, b0 = ia
    fr, fg, fb = fa
    out = np.zeros_like(img)
    for db in (0, 1):
        wb = fb if db else 1.0 - fb
        for dg in (0, 1):
            wg = fg if dg else 1.0 - fg
            for dr in (0, 1):
                wr = fr if dr else 1.0 - fr
                ii = np.minimum(N - 1, r0 + dr)
                jj = np.minimum(N - 1, g0 + dg)
                kk = np.minimum(N - 1, b0 + db)
                out += lut[kk, jj, ii] * (wr * wg * wb)[:, :, None]
    return np.clip(out + 0.5, 0, 255).astype(np.uint8)


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    src, dst = sys.argv[1], sys.argv[2]
    names = sys.argv[3:]
    if not names:
        names = sorted(f[:-4] for f in os.listdir(LOOKS) if f.endswith('.bin')
                       and f != 'identity17.bin')

    im = Image.open(src).convert('RGB')
    tw = 620
    th = int(im.height * tw / im.width)
    im = im.resize((tw, th), Image.LANCZOS)
    arr = np.asarray(im, dtype=np.float32)

    cells = [('原图 ORIGINAL', np.asarray(im, dtype=np.uint8))]
    for n in names:
        p = os.path.join(LOOKS, n + '.bin')
        if not os.path.isfile(p):
            print('skip (missing):', n)
            continue
        cells.append((n, apply_lut(arr, load_lut(p))))

    cols = 3 if len(cells) > 4 else 2
    rows = (len(cells) + cols - 1) // cols
    bar, gap = 26, 4
    W = cols * tw + (cols + 1) * gap
    H = rows * (th + bar) + (rows + 1) * gap
    sheet = Image.new('RGB', (W, H), (22, 22, 24))
    try:
        font = ImageFont.truetype(FONT, 17)
    except Exception:
        font = ImageFont.load_default()
    d = ImageDraw.Draw(sheet)

    for idx, (label, buf) in enumerate(cells):
        cx = gap + (idx % cols) * (tw + gap)
        cy = gap + (idx // cols) * (th + bar + gap)
        sheet.paste(Image.fromarray(buf), (cx, cy + bar))
        d.text((cx + 4, cy + 4), label, fill=(235, 235, 235), font=font)

    sheet.save(dst)
    print(f'{dst}  {W}x{H}  {len(cells)} 格')
    return 0


if __name__ == '__main__':
    sys.exit(main())
