# -*- coding: utf-8 -*-
"""Leica L-Log 表补一段 V-Log→sRGB 解码，才能吃显示参考输入。

为什么需要这一步
----------------
`L-Log_to_Classic_VLog.cube` 的输出仍是 **V-Log 编码**（文件名里的 VLog 指的是
输出域，不是输入域），它是给松下 LUT2 槽串联用的。直接接在 S2V 后面得到的是
"Standard → V-Log"，对比度只剩 0.73/0.65，在相机 JPEG 上就是发灰。

所以补最后一段：V-Log 码值 → 线性 V-Gamut → XYZ D65 → 线性 sRGB → sRGB 编码。
常数取松下 V-Log 参考手册（与 V-Log-Alchemy 的 vlog_to_linear 一致）。
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cube_import as ci
import native_codec as nc
from colour_metrics import metrics
from similarity_audit import apply_slot, de00, load_native, probe_set, rgb_to_lab, REPO

# 松下 V-Log
CUT, B_, C_, D_ = 0.181, 0.00873, 0.241514, 0.598206

# V-Gamut (Panasonic) 原色 -> XYZ D65
V_GAMUT = ((0.730, 0.280), (0.165, 0.840), (0.100, -0.030))
D65 = (0.3127, 0.3290)


def vlog_to_linear(v):
    v = np.asarray(v, dtype=float)
    return np.where(v < CUT, (v - 0.125) / 5.6,
                    np.power(10.0, (v - D_) / C_) - B_)


def rgb_to_xyz(prim, white):
    xr, yr = prim[0]; xg, yg = prim[1]; xb, yb = prim[2]
    xw, yw = white
    Xw, Yw, Zw = xw / yw, 1.0, (1 - xw - yw) / yw
    M = np.array([[xr / yr, xg / yg, xb / yb],
                  [1.0, 1.0, 1.0],
                  [(1 - xr - yr) / yr, (1 - xg - yg) / yg, (1 - xb - yb) / yb]])
    S = np.linalg.solve(M, np.array([Xw, Yw, Zw]))
    return M * S


def srgb_encode(x):
    x = np.clip(x, 0.0, 1.0)
    return np.where(x <= 0.0031308, 12.92 * x, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def vlog_to_srgb(vlog_rgb):
    lin_vgamut = vlog_to_linear(np.clip(vlog_rgb, 0.0, 1.0))
    xyz = lin_vgamut @ rgb_to_xyz(V_GAMUT, D65).T
    lin_srgb = xyz @ np.linalg.inv(rgb_to_xyz(((0.64, 0.33), (0.30, 0.60), (0.15, 0.06)), D65)).T
    return srgb_encode(lin_srgb)


def main():
    src = Path(r'E:\NXWA\_lutweb\std_out')
    out = Path(r'E:\NXWA\_lutweb\stage2')
    out.mkdir(parents=True, exist_ok=True)
    existing = {p.stem: load_native(p) for p in sorted((REPO / 'looks').glob('*.bin'))}
    pts, _ = probe_set()
    ex_lab = {k: rgb_to_lab(apply_slot(pts, v)) for k, v in existing.items()}

    print('%-18s %6s %6s %6s | %-20s %6s' % ('name', 'sat', 'contr', 'warm', 'nearest', 'dE00'))
    for stem, f in (('leica_classic', 'LeicCla.cube'), ('leica_natural', 'LeicNat.cube')):
        n, nodes = ci.parse_cube(src / f)
        vlog = nodes / 255.0                       # Standard -> 已是 V-Log 域
        fixed = vlog_to_srgb(vlog) * 255.0
        raw = nc.compile_uniform_rgb(fixed.tolist(), n, boundary='linear')
        target = out / (stem + '.bin')
        target.write_bytes(raw)
        nc.record_native(target, raw)
        view = np.frombuffer(raw[:19652], np.uint8).reshape(17, 17, 17, 4)[:, :, :, :3].astype(float)
        m = metrics(view)
        lab = rgb_to_lab(apply_slot(pts, view))
        d, near = min(((float(np.median(de00(lab, el))), k) for k, el in ex_lab.items()))
        print('%-18s %6.1f %6.2f %6.2f | %-20s %6.2f  %s' %
              (stem, m['saturation'], m['contrast'], m['warmth'], near, d,
               'DISTINCT' if d > 3.112 else 'DUPLICATE'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
