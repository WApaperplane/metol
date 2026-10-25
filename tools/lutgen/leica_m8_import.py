# -*- coding: utf-8 -*-
"""PictureFX Leica M8 Camera Standard（免费，25³ HaldCLUT）-> 原生槽表 + 度量。

来源：https://marcrphoto.wordpress.com/2023/07/14/... （作者 Marc / PictureFX）
      直链 Google Drive，文件名 PictureFX-LeicaM8-Camera-Standard-125.png
      Hald 层级 5：125² = 25³。

布局用 ImageMagick `hald:` 定义：flat index i = y*W + x，
r = i%C、g = (i//C)%C、b = i//C²（C = 25）。注意 W=125 不是 C 的整数倍，
所以一行里会跨多个 g 值——这不是 tile 布局，是线性条带。
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import native_codec as nc
from colour_metrics import metrics
from similarity_audit import apply_slot, de00, load_native, probe_set, rgb_to_lab, REPO

PNG = Path(r'E:\NXWA\_lutweb\leica_m8\PictureFX-LeicaM8-Camera-Standard-125.png')
OUT = Path(__file__).resolve().parent / 'audit_out' / 'signature'
OUT.mkdir(parents=True, exist_ok=True)


def decode(png, level=25):
    a = np.asarray(Image.open(png).convert('RGB')).astype(np.float32)
    if a.shape[0] * a.shape[1] != level ** 3:
        raise ValueError('size %s does not hold a %d^3 cube' % (a.shape, level))
    flat = a.reshape(-1, 3)
    i = np.arange(level ** 3)
    cube = np.empty((level, level, level, 3), np.float32)
    cube[i % level, (i // level) % level, i // (level * level)] = flat[i]
    return cube


def to_slot(cube):
    n = cube.shape[0]
    return nc.compile_uniform_rgb(cube.transpose(2, 1, 0, 3).reshape(-1, 3).tolist(), n)


def main():
    cube = decode(PNG)
    raw = to_slot(cube)
    (OUT / 'leica_m8.bin').write_bytes(raw)
    view = np.frombuffer(raw[:19652], np.uint8).reshape(17, 17, 17, 4)[:, :, :, :3].astype(float)
    m = metrics(view)
    print('PictureFX Leica M8 -> 原生槽 %d B' % len(raw))
    for k, v in m.items():
        print('   %-12s %.2f' % (k, v))

    pts, _ = probe_set()
    lab = rgb_to_lab(apply_slot(pts, view))
    ex = {p.stem: load_native(p) for p in sorted((REPO / 'looks').glob('*.bin'))}
    d = sorted(((float(np.median(de00(lab, rgb_to_lab(apply_slot(pts, v))))), k)
                for k, v in ex.items()))[:5]
    print('   最像的现有表：')
    for val, k in d:
        print('      %.3f  %s' % (val, k))
    print('   （若最小 dE00 仍 >3.112，说明它与现有 82 张都不重）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
