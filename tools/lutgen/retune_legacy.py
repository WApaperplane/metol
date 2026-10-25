#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""retune_legacy.py — 修正历史批次的 LUT 偏红

处理对象：looks/ 下**不在** tools/lutgen/films.json 里的表（即 10-20 批次），
gen_luts 产出的表不动（它们由参数源控制，改参数即可）。

两步校正，均可调：
  1) 灰轴中性化：按输入亮度采样该表的灰轴输出，扣掉通道间偏差（强度 GAIN）
  2) 暖色降压：色相 330..50°（红橙）且高饱和的格点，把 R 往 G 收一点（强度 WARM）

用法：
  python retune_legacy.py --dry          只报告，不写文件
  python retune_legacy.py --apply        写回 looks/（原表备份到 looks_legacy_backup/）

★ 幂等性：本脚本是"就地叠加"，对同一张表跑两次会削两次。要重做/加强修正，
  必须从基线重来：--src=looks_legacy_backup --warm=0.45 --out=/tmp/x
  （looks_legacy_backup/ 存的是 retune 之前的原始批）。直接 --apply 两次 = 错误用法。
"""
import json
import os
import shutil
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
LOOKS = os.path.join(REPO, 'looks')
FILMS = os.path.join(HERE, 'films.json')
BACKUP = os.path.join(REPO, 'looks_legacy_backup')

N = 17
GRID = np.array([16 * i for i in range(16)] + [255], dtype=np.float32)

GAIN = 0.0         # 灰轴中性化强度（默认关闭：老表的冷调是设计意图）
GAIN_HARD = 0.55   # 灰轴偏差 > HARD_TH 时启用的强度（明显过头才修）
HARD_TH = 20.0
WARM = 0.30        # 暖色降压强度
WARM_HUE = (330, 50)
SKIP_SUBSTR = ('warm_', 'sepia', 'mono_', 'identity', 'film_negative',
               'samsung_', 'cool_')   # samsung_* 是只读原厂参考表，cool_* 是 mk_coolfix 产物


def load_table(path):
    """→ (17,17,17,3) float，索引 [r][g][b]（按 R 变化最快还原）"""
    from native_codec import space_for, NATIVE
    if space_for(path) == NATIVE:
        raise ValueError('原生 CrCbY 表不能按 RGB 修改；请调整 RGB 配方后重新编译')
    d = np.frombuffer(open(path, 'rb').read(), dtype=np.uint8)[:N * N * N * 4]
    t = d.reshape(N, N, N, 4)[:, :, :, :3].astype(np.float32)
    return t.transpose(2, 1, 0, 3)          # [b][g][r] → [r][g][b]


def save_table(path, t):
    out = t.transpose(2, 1, 0, 3)            # [r][g][b] → [b][g][r]
    buf = np.zeros((N, N, N, 4), dtype=np.uint8)
    buf[:, :, :, :3] = np.clip(np.rint(out), 0, 255).astype(np.uint8)
    open(path, 'wb').write(buf.tobytes() + bytes(60))


def rgb_to_hsv_arr(rgb):
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx = rgb.max(-1)
    mn = rgb.min(-1)
    d = mx - mn
    h = np.zeros_like(mx)
    m = d > 1e-6
    idx = m & (mx == r)
    h[idx] = ((g[idx] - b[idx]) / d[idx]) % 6.0
    idx = m & (mx == g)
    h[idx] = (b[idx] - r[idx]) / d[idx] + 2.0
    idx = m & (mx == b)
    h[idx] = (r[idx] - g[idx]) / d[idx] + 4.0
    h *= 60.0
    s = np.where(mx > 0, d / np.maximum(mx, 1e-6), 0.0)
    return h, s, mx


def process(t):
    # 灰轴：输入 (v,v,v) → 输出 t[i,i,i]
    diag = np.array([t[i, i, i] for i in range(N)])           # (17,3)
    lum = diag.mean(1)                                        # 各格点的输出亮度
    bias = diag - lum[:, None]                                # 通道偏差 (17,3)
    spread = np.abs(bias[:, [0, 2]] - bias[:, [1, 1]]).max()
    gain = GAIN_HARD if spread > HARD_TH else GAIN

    out = t.copy()
    # --- 1) 灰轴中性化（只对明显过头的表） ---
    if gain > 0:
        vin = (GRID[:, None, None] + GRID[None, :, None] + GRID[None, None, :]) / 3.0 / 255.0
        pos = vin * (N - 1)                                   # 0..16 连续位置
        lo = np.clip(np.floor(pos).astype(int), 0, N - 2)
        fr = (pos - lo)[..., None]
        binterp = bias[lo] * (1 - fr) + bias[lo + 1] * fr      # (17,17,17,3)
        out -= binterp * gain

    # --- 2) 暖色降压：红橙高饱和区，把红超出绿的部分收掉一部分 ---
    h, s, v = rgb_to_hsv_arr(np.clip(out, 0, 255))
    inhue = ((h >= WARM_HUE[0]) | (h <= WARM_HUE[1])) & (s > 0.30) & (v > 35)
    excess = np.clip(out[..., 0] - out[..., 1], 0, None)
    # 饱和越高、色相越靠红，收得越多
    w = np.clip((s - 0.30) / 0.70, 0, 1) ** 0.7
    out[..., 0] = np.where(inhue, out[..., 0] - excess * WARM * w, out[..., 0])

    return np.clip(out, 0, 255)


def main():
    global WARM
    apply = '--apply' in sys.argv
    outdir = None
    src = LOOKS
    for a in sys.argv[1:]:
        if a.startswith('--out='):
            outdir = a.split('=', 1)[1]
        elif a.startswith('--src='):
            src = a.split('=', 1)[1]
        elif a.startswith('--warm='):
            WARM = float(a.split('=', 1)[1])
    protected = set(json.load(open(FILMS, encoding='utf-8')).keys())
    names = sorted(f[:-4] for f in os.listdir(src) if f.endswith('.bin'))
    legacy = [n for n in names if n not in protected and not any(k in n for k in SKIP_SUBSTR)]
    skipped = [n for n in names if n not in protected and any(k in n for k in SKIP_SUBSTR)]

    print('源目录: %s   warm=%.2f' % (src, WARM))
    print('受保护(gen_luts): %d  跳过(设计暖调/mono): %d  待处理: %d'
          % (len(protected), len(skipped), len(legacy)))
    if apply:
        os.makedirs(BACKUP, exist_ok=True)
    if outdir:
        os.makedirs(outdir, exist_ok=True)

    print('%-24s %14s %14s' % ('LUT', '灰轴偏差 R-G/B-G', '校正后'))
    for n in legacy:
        p = os.path.join(src, n + '.bin')
        t = load_table(p)
        diag0 = np.array([t[i, i, i] for i in range(N)])
        d0 = (diag0 - diag0.mean(1)[:, None])
        worst0 = np.abs(d0[:, [0, 2]] - d0[:, [1, 1]]).max()
        t2 = process(t)
        diag1 = np.array([t2[i, i, i] for i in range(N)])
        d1 = (diag1 - diag1.mean(1)[:, None])
        worst1 = np.abs(d1[:, [0, 2]] - d1[:, [1, 1]]).max()
        flag = '★' if worst0 > 4 else ' '
        print('%s%-23s %6.1f/%6.1f %10.1f' % (flag, n, d0[:, 0].mean() - d0[:, 1].mean(),
                                              d0[:, 2].mean() - d0[:, 1].mean(), worst1))
        if apply:
            # 目标恒为 looks/；backup 存的是 looks/ 的旧版（不是 src）
            dst = os.path.join(LOOKS, n + '.bin')
            if os.path.isfile(dst):
                shutil.copy2(dst, os.path.join(BACKUP, n + '.bin'))
            save_table(dst, t2)
        elif outdir:
            save_table(os.path.join(outdir, n + '.bin'), t2)

    if apply:
        print('\n已写回 %d 张，原表备份在 %s' % (len(legacy), BACKUP))
    else:
        print('\n[dry] 未写文件；加 --apply 生效')
    return 0


if __name__ == '__main__':
    sys.exit(main())
