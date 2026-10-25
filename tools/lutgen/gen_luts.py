#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_luts.py — 生成三星 NX500 (DRIMe5) 硬件 3D LUT 表

输出格式（与 looks/*.bin / identity17.bin 一致，已用 identity 表逐项验证）：
  17^3 格点，每项 4 字节 {R,G,B,pad=0}
  index = ((B*17 + G)*17 + R) * 4      ← R 变化最快
  格点值 = [0,16,32,...,240,255]       ← 前 16 步 16，末步 15
  通道坐标 = RGB（对应 Cfg bits[1:0]=SelCbCr=0）

管线（gamma 域为主，白平衡与串扰在 linear 域）：
  linear → WB → 逐层 gamma → S 曲线 → 高光滚降 → 提升+色罩
         → 染料串扰 → 色相选择性(饱和/旋转) → clamp
"""

import json
import math
import os
import struct
import sys

N = 17
GRID = [16 * i for i in range(16)] + [255]
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))          # tools/lutgen → 仓库根
OUT_BIN = os.path.join(REPO, 'looks')                  # 直接写发布物目录
OUT_CUBE = os.path.join(HERE, 'cube')                  # .cube 中间产物（不入库）
WARM_GUARD = 0.30     # 默认暖色保护强度；配方可用 warm_guard 覆盖（0 = 关闭）


# ---------- 色彩基础 ----------
def srgb_to_lin(v):
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def lin_to_srgb(v):
    v = 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)
    return 12.92 * v if v <= 0.0031308 else 1.055 * (v ** (1 / 2.4)) - 0.055


def s_curve(x, c):
    """平滑对比：端点固定，c>0 加对比。"""
    if c == 0.0:
        return x
    return x + c * x * (1.0 - x) * (2.0 * x - 1.0) * 2.0


def shoulder(x, k):
    """高光滚降：k>0 压缩高光，端点固定。"""
    if k == 0.0:
        return x
    return x * (1.0 + k) / (1.0 + k * x)


def rgb_to_hsv(r, g, b):
    mx = max(r, g, b)
    mn = min(r, g, b)
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


def hsv_to_rgb(h, s, v):
    h = h % 360.0
    c = v * s
    x = c * (1 - abs((h / 60.0) % 2 - 1))
    m = v - c
    if h < 60:
        r, g, b = c, x, 0
    elif h < 120:
        r, g, b = x, c, 0
    elif h < 180:
        r, g, b = 0, c, x
    elif h < 240:
        r, g, b = 0, x, c
    elif h < 300:
        r, g, b = x, 0, c
    else:
        r, g, b = c, 0, x
    return r + m, g + m, b + m


HUES = [0, 30, 60, 120, 180, 240, 285, 330]      # 红 橙 黄 绿 青 蓝 紫 品


def hue_weight(h, anchor, sigma=38.0):
    d = abs((h - anchor + 180.0) % 360.0 - 180.0)
    return math.exp(-(d * d) / (2.0 * sigma * sigma))


def hue_lookup(h, table):
    """table: {anchor: value}，按高斯权重归一化插值。"""
    if not table:
        return 0.0
    num = 0.0
    den = 0.0
    for a, v in table.items():
        w = hue_weight(h, a)
        num += w * v
        den += w
    if den < 1e-9:
        return 0.0
    return num / den


# ---------- 单点变换 ----------
def apply_film(rgb8, p):
    """rgb8: (r,g,b) 0..255 输入 → (r,g,b,pad) 输出字节"""
    r, g, b = (v / 255.0 for v in rgb8)

    # 1) 白平衡（linear 域）
    lr, lg, lb = srgb_to_lin(r), srgb_to_lin(g), srgb_to_lin(b)
    wb = p.get('wb', (1.0, 1.0, 1.0))
    lr, lg, lb = lr * wb[0], lg * wb[1], lb * wb[2]
    r, g, b = lin_to_srgb(lr), lin_to_srgb(lg), lin_to_srgb(lb)

    # 2) 逐层 gamma（模拟三层感光度差异）
    gr, gg, gb = p.get('gamma', (1.0, 1.0, 1.0))
    r = r ** gr if gr != 1.0 else r
    g = g ** gg if gg != 1.0 else g
    b = b ** gb if gb != 1.0 else b

    # 3) 对比 S 曲线
    c = p.get('contrast', 0.0)
    r, g, b = s_curve(r, c), s_curve(g, c), s_curve(b, c)

    # 4) 高光滚降
    sh = p.get('shoulder', 0.0)
    r, g, b = shoulder(r, sh), shoulder(g, sh), shoulder(b, sh)

    # 5) 提升 + 色罩（fog = 片基色）+ 分离色调（暗部/高光各自着色）
    lift = p.get('lift', 0.0)
    fog = p.get('fog', (0.0, 0.0, 0.0))
    r = lift + r * (1.0 - lift) + fog[0]
    g = lift + g * (1.0 - lift) + fog[1]
    b = lift + b * (1.0 - lift) + fog[2]

    sh_t = p.get('shadow', None)
    hi_t = p.get('high', None)
    if sh_t or hi_t:
        luma = 0.299 * r + 0.587 * g + 0.114 * b
        if luma < 0.0:
            luma = 0.0
        elif luma > 1.0:
            luma = 1.0
        sw = (1.0 - luma) ** 2
        hw = luma ** 2
        sh = sh_t or (0.0, 0.0, 0.0)
        hi = hi_t or (0.0, 0.0, 0.0)
        r += sh[0] * sw + hi[0] * hw
        g += sh[1] * sw + hi[1] * hw
        b += sh[2] * sw + hi[2] * hw

    # 6) 染料串扰（3x3，对角 1 - 2k）
    k = p.get('crosstalk', 0.0)
    if k > 0.0:
        m = p.get('xt', None)
        if m is None:
            m = ((1 - 2 * k, k, k), (k, 1 - 2 * k, k), (k, k, 1 - 2 * k))
        r, g, b = (m[0][0] * r + m[0][1] * g + m[0][2] * b,
                   m[1][0] * r + m[1][1] * g + m[1][2] * b,
                   m[2][0] * r + m[2][1] * g + m[2][2] * b)

    r = 0.0 if r < 0 else (1.0 if r > 1 else r)
    g = 0.0 if g < 0 else (1.0 if g > 1 else g)
    b = 0.0 if b < 0 else (1.0 if b > 1 else b)

    # 7) 色相选择性：饱和 + 旋转（按 chroma 加权，中性灰不受影响）
    sat_m = p.get('sat', 1.0)
    sat_h = p.get('sat_hues', {})
    rot_h = p.get('hue_rot', {})
    if sat_m != 1.0 or sat_h or rot_h:
        h, s, v = rgb_to_hsv(r, g, b)
        if s > 1e-4:
            m = sat_m * (hue_lookup(h, sat_h) if sat_h else 1.0)
            # 暗部保护：v 小时把 m 拉回 1，否则 s*m 打满 1.0 会让最小通道直接归零，
            # 暗部变成死黑、色阶断裂（2026-10-25 体检：velvia50 有 2253 个
            # 输入全非零的格点被压成 0）。只削暗部的额外饱和，中间调不动。
            if v < 0.25:
                m = 1.0 + (m - 1.0) * (v / 0.25)
            s = min(0.98, max(0.0, s * m))
            if rot_h:
                h = h + hue_lookup(h, rot_h)
            r, g, b = hsv_to_rgb(h, s, v)

    # 8) 暖色保护：红橙高饱和区把 R 往 G 收一点。
    #    动机（2026-10-25 实机排查）：老批次 LUT 在室内暖光/人像上"偏红"，
    #    根因是高饱和表把暖色整体推向红端（灰轴反而是中性甚至偏蓝）。
    #    只削"红超出绿"的那部分，不改色相中心，风格与饱和度保留。
    #
    #    下面是"加强模式"的可选参数，默认全部关闭 ⇒ 输出与旧版逐字节一致
    #    （已用 md5 全量回归验证）。要调强修正时再打开，别默认改：
    #      warm_huew  色相窗口半宽（度）。0 = 旧版硬判 h≤50 或 h≥330；
    #                 >0 改用余弦淡出（边界处 R 不突变，但 30-50° 的权重会下降）
    #      warm_vsoft v 门槛软化。True 时权重乘 min(1,v/0.14)，消除
    #                 (32,0,0) 不削而 (48,0,0) 削造成的红轴亮度倒挂
    #      warm_excap 单点最大削幅（归一化单位）。1.0 = 不封顶；0.22 可防纯红被整块削暗
    wg = p.get('warm_guard', WARM_GUARD)
    wsm = p.get('warm_smin', 0.30)          # 起削饱和度门槛；肤色 s 常在 0.25-0.45
    wpw = p.get('warm_pow', 0.7)            # 权重曲线指数
    whw = p.get('warm_huew', 0.0)           # 0 = 旧版硬边界
    wcap = p.get('warm_excap', 1.0)         # 1.0 = 不封顶
    vsoft = p.get('warm_vsoft', False)
    if wg > 0.0:
        h, s, v = rgb_to_hsv(r, g, b)
        hard = (h <= 50.0 or h >= 330.0)
        if whw > 0.0:
            hh = h if h <= 180.0 else h - 360.0
            hwv = math.cos(math.pi * hh / (2.0 * whw)) ** 2 if abs(hh) < whw else 0.0
        else:
            hwv = 1.0 if hard else 0.0
        if hwv > 0.0 and s > wsm and v > 0.14:
            w = hwv * ((s - wsm) / (1.0 - wsm)) ** wpw
            if vsoft:
                w *= min(1.0, v / 0.14)
            ex = (r - g) if wcap >= 1.0 else min(r - g, wcap)
            if ex > 0.0 and w > 0.0:
                r -= ex * wg * w

    # 9) 输出
    out = []
    for v in (r, g, b):
        q = int(v * 255.0 + 0.5)
        out.append(0 if q < 0 else (255 if q > 255 else q))
    return bytes(out) + b'\0'


def build(p):
    buf = bytearray()
    for bi in range(N):
        for gi in range(N):
            for ri in range(N):
                buf += apply_film((GRID[ri], GRID[gi], GRID[bi]), p)
    buf += b'\0' * 60          # 槽尾 pad：19652B 表 + 60B = 19712B（步长 0x4D00）
    return bytes(buf)


# ---------- 自检 ----------
def measure(p):
    grays = []
    for i in range(N):
        v = GRID[i]
        o = apply_film((v, v, v), p)
        grays.append(max(o[0], o[1], o[2]) - min(o[0], o[1], o[2]))
    gray_gap = max(grays)
    # 白点 / 黑点
    w = apply_film((255, 255, 255), p)
    k = apply_film((0, 0, 0), p)
    # 中间调饱和度变化（用 (200,120,120) 近肤色与 (60,120,200) 天空）
    def sat(o):
        mx, mn = max(o[:3]), min(o[:3])
        return 0 if mx == 0 else (mx - mn) / mx
    skin_in, skin_out = (200, 150, 130), apply_film((200, 150, 130), p)
    sky_in, sky_out = (80, 130, 200), apply_film((80, 130, 200), p)
    skin_ds = sat(skin_out) - sat(skin_in)
    sky_ds = sat(sky_out) - sat(sky_in)
    return gray_gap, tuple(w[:3]), tuple(k[:3]), skin_ds, sky_ds


def write_cube(p, path):
    lines = ['TITLE "Metol film LUT"', 'LUT_3D_SIZE %d' % N,
             'DOMAIN_MIN 0.0 0.0 0.0', 'DOMAIN_MAX 1.0 1.0 1.0', '']
    for bi in range(N):
        for gi in range(N):
            for ri in range(N):
                o = apply_film((GRID[ri], GRID[gi], GRID[bi]), p)
                lines.append('%.6f %.6f %.6f' % (o[0] / 255, o[1] / 255, o[2] / 255))
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(lines) + '\n')


# ---------- 参数库 ----------
W = 30
R_, O_, Y_, G_, C_, B_, P_, M_ = 0, 30, 60, 120, 180, 240, 285, 330

FILMS = {
    # ===== 富士 =====
    'fuji_velvia50': dict(contrast=0.30, shoulder=0.18, sat=1.34,
                          sat_hues={G_: 1.18, B_: 1.14, R_: 1.10, O_: 1.05},
                          hue_rot={G_: -5, C_: -4, B_: 3}, gamma=(0.99, 1.0, 1.02),
                          crosstalk=0.02, max_gray=12),
    'fuji_velvia100': dict(contrast=0.26, shoulder=0.16, sat=1.28,
                           sat_hues={G_: 1.15, B_: 1.12, R_: 1.08},
                           hue_rot={G_: -4, C_: -3}, crosstalk=0.02, max_gray=12),
    'fuji_provia100f': dict(contrast=0.20, shoulder=0.14, sat=1.14,
                            sat_hues={G_: 1.05, B_: 1.08}, hue_rot={B_: 2},
                            crosstalk=0.02, max_gray=12),
    'fuji_astia100f': dict(contrast=0.10, shoulder=0.20, sat=1.02, lift=0.008,
                           sat_hues={R_: 0.95, O_: 0.96, G_: 0.96},
                           fog=(0.004, 0.002, 0.004), crosstalk=0.02, max_gray=12),
    'fuji_proneg_std': dict(contrast=-0.06, shoulder=0.22, sat=0.92, lift=0.014,
                            sat_hues={G_: 0.95, B_: 0.97}, gamma=(1.0, 1.0, 1.03),
                            crosstalk=0.03, max_gray=12),
    'fuji_proneg_hi': dict(contrast=0.10, shoulder=0.16, sat=1.04, lift=0.008,
                           sat_hues={G_: 1.0, B_: 1.02}, crosstalk=0.025, max_gray=12),
    'fuji_superia400': dict(contrast=0.12, shoulder=0.16, sat=1.06, lift=0.012,
                            sat_hues={G_: 1.16, C_: 1.12, B_: 1.04, R_: 0.97},
                            hue_rot={G_: -6, C_: -3}, fog=(0.0, 0.006, 0.002),
                            crosstalk=0.03, max_gray=12),
    'fuji_superia400p': dict(contrast=0.14, shoulder=0.15, sat=1.10, lift=0.010,
                             sat_hues={G_: 1.12, C_: 1.06, R_: 1.02},
                             hue_rot={G_: -4}, fog=(0.006, 0.006, 0.0),
                             crosstalk=0.03, max_gray=12),
    'fuji_eterna500': dict(contrast=-0.10, shoulder=0.26, sat=0.80, lift=0.020,
                           sat_hues={G_: 1.0, C_: 1.10, B_: 1.05, R_: 0.85},
                           hue_rot={C_: -6, B_: 6}, fog=(0.0, 0.010, 0.014),
                           crosstalk=0.035, max_gray=12),
    'fuji_classicchrome': dict(contrast=0.16, shoulder=0.14, sat=0.86, lift=0.010,
                               sat_hues={R_: 0.92, O_: 0.92, G_: 1.0, B_: 0.94},
                               hue_rot={C_: -4, B_: -3}, fog=(0.0, 0.004, 0.012),
                               crosstalk=0.03, max_gray=12),
    'fuji_400h': dict(contrast=0.04, shoulder=0.22, sat=0.94, lift=0.016,
                      sat_hues={G_: 1.06, C_: 1.08, R_: 0.94},
                      hue_rot={C_: -4}, fog=(0.002, 0.008, 0.006),
                      crosstalk=0.03, max_gray=12),

    # ===== 柯达：Portra / 负片 =====
    'kodak_portra160': dict(contrast=0.02, shoulder=0.22, sat=0.94, lift=0.014,
                            sat_hues={O_: 1.02, R_: 1.0, G_: 0.97, B_: 0.98},
                            fog=(0.008, 0.004, 0.004), gamma=(1.0, 1.0, 1.015),
                            crosstalk=0.03, max_gray=12),
    'kodak_portra400': dict(contrast=0.04, shoulder=0.22, sat=0.96, lift=0.014,
                            sat_hues={O_: 1.06, R_: 1.02, G_: 0.96, B_: 0.98},
                            hue_rot={G_: -3}, fog=(0.010, 0.004, 0.002),
                            gamma=(1.0, 0.995, 1.015), crosstalk=0.03, max_gray=12),
    'kodak_portra800': dict(contrast=0.06, shoulder=0.24, sat=0.90, lift=0.018,
                            sat_hues={O_: 1.06, G_: 0.94, B_: 0.96},
                            fog=(0.012, 0.005, 0.002), crosstalk=0.035, max_gray=12),
    'kodak_portra400vc': dict(contrast=0.10, shoulder=0.18, sat=1.12, lift=0.010,
                              sat_hues={O_: 1.08, R_: 1.06, G_: 0.98, B_: 1.02},
                              fog=(0.010, 0.004, 0.002), crosstalk=0.03, max_gray=12),
    'kodak_portra400nc': dict(contrast=0.02, shoulder=0.22, sat=0.88, lift=0.016,
                              sat_hues={G_: 0.96, B_: 0.98},
                              fog=(0.006, 0.004, 0.006), crosstalk=0.03, max_gray=12),
    'kodak_gold200': dict(contrast=0.10, shoulder=0.18, sat=1.04, lift=0.012,
                          sat_hues={Y_: 1.14, O_: 1.10, G_: 1.06, B_: 0.92},
                          hue_rot={Y_: -3, G_: -3}, fog=(0.010, 0.008, 0.0),
                          crosstalk=0.03, max_gray=12),
    'kodak_ultramax400': dict(contrast=0.14, shoulder=0.16, sat=1.14, lift=0.010,
                              sat_hues={B_: 1.12, M_: 1.08, R_: 1.04, Y_: 1.0},
                              hue_rot={B_: 4}, fog=(0.008, 0.004, 0.006),
                              crosstalk=0.03, max_gray=12),
    # ===== 柯达：反转 / 经典 =====
    'kodak_ektar100': dict(contrast=0.24, shoulder=0.14, sat=1.26, lift=0.006,
                           sat_hues={R_: 1.14, B_: 1.16, C_: 1.06, G_: 1.0},
                           hue_rot={B_: -3, R_: -2}, fog=(0.004, 0.002, 0.004),
                           crosstalk=0.025, max_gray=12),
    'kodak_e100': dict(contrast=0.22, shoulder=0.14, sat=1.10, lift=0.006,
                       sat_hues={B_: 1.10, C_: 1.06, R_: 1.02},
                       fog=(0.002, 0.002, 0.006), crosstalk=0.025, max_gray=12),
    'kodak_kchrome64': dict(contrast=0.26, shoulder=0.12, sat=1.16, lift=0.006,
                            sat_hues={R_: 1.18, B_: 1.12, O_: 1.08, G_: 0.96},
                            hue_rot={R_: -4, B_: -4, G_: 3},
                            fog=(0.006, 0.002, 0.008), crosstalk=0.035, max_gray=12),
    'kodak_kchrome25': dict(contrast=0.32, shoulder=0.10, sat=1.22, lift=0.004,
                            sat_hues={R_: 1.22, B_: 1.14, G_: 0.94},
                            hue_rot={R_: -5, B_: -5}, fog=(0.006, 0.002, 0.009),
                            crosstalk=0.04, max_gray=12),

    # ===== AGFA =====
    'agfa_vista200': dict(contrast=0.08, shoulder=0.18, sat=1.08, lift=0.012,
                          sat_hues={R_: 1.14, M_: 1.10, G_: 1.02, B_: 0.94},
                          hue_rot={R_: 4, G_: -3, Y_: -4}, fog=(0.014, 0.004, 0.006),
                          crosstalk=0.035, max_gray=12),
    'agfa_ultra100': dict(contrast=0.16, shoulder=0.14, sat=1.24, lift=0.008,
                          sat_hues={R_: 1.20, M_: 1.14, G_: 1.04, B_: 0.92},
                          hue_rot={R_: 5, Y_: -5}, fog=(0.012, 0.004, 0.006),
                          crosstalk=0.03, max_gray=12),
    'agfa_rsx200': dict(contrast=0.20, shoulder=0.14, sat=1.10, lift=0.008,
                        sat_hues={B_: 1.14, C_: 1.08, R_: 0.96, O_: 0.94},
                        hue_rot={B_: -3}, fog=(0.0, 0.004, 0.012),
                        crosstalk=0.03, max_gray=12),

    # ===== 佳能 Picture Style =====
    'canon_standard': dict(contrast=0.14, shoulder=0.14, sat=1.12, lift=0.008,
                           sat_hues={R_: 1.08, O_: 1.06, G_: 1.02, B_: 1.0},
                           fog=(0.004, 0.002, 0.002), crosstalk=0.02, max_gray=12),
    'canon_faithful': dict(contrast=0.04, shoulder=0.16, sat=0.96, lift=0.006,
                           crosstalk=0.015, max_gray=12),
    'canon_landscape': dict(contrast=0.18, shoulder=0.14, sat=1.20, lift=0.006,
                            sat_hues={B_: 1.20, C_: 1.18, G_: 1.14, R_: 0.96, O_: 0.94},
                            hue_rot={B_: -3, G_: -3}, fog=(0.0, 0.004, 0.008),
                            crosstalk=0.02, max_gray=12),
    'canon_portrait': dict(contrast=0.06, shoulder=0.20, sat=1.02, lift=0.012,
                           sat_hues={O_: 1.10, R_: 1.06, G_: 0.94, B_: 0.96},
                           fog=(0.008, 0.004, 0.004), crosstalk=0.025, max_gray=12),
    'canon_5dclassic': dict(contrast=0.12, shoulder=0.18, sat=1.06, lift=0.010,
                            sat_hues={R_: 1.10, O_: 1.08, G_: 0.98, B_: 0.98},
                            hue_rot={R_: 2, C_: -4}, fog=(0.010, 0.004, 0.004),
                            gamma=(1.0, 1.0, 1.02), crosstalk=0.03, max_gray=12),

    # ===== 徕卡 =====
    'leica_m9': dict(contrast=0.18, shoulder=0.16, sat=1.10, lift=0.008,
                     sat_hues={R_: 1.14, O_: 1.10, G_: 1.04, B_: 0.96},
                     hue_rot={R_: 3, C_: -5}, fog=(0.010, 0.004, 0.006),
                     crosstalk=0.03, max_gray=12),
    'leica_m240': dict(contrast=0.10, shoulder=0.18, sat=1.02, lift=0.008,
                       sat_hues={B_: 1.06, G_: 0.98},
                       hue_rot={C_: -3}, fog=(0.002, 0.004, 0.008),
                       crosstalk=0.025, max_gray=12),
    'leica_m10': dict(contrast=0.20, shoulder=0.14, sat=1.08, lift=0.006,
                      sat_hues={R_: 1.06, B_: 1.04},
                      fog=(0.004, 0.002, 0.004), crosstalk=0.02, max_gray=12),

    # ===== 宝丽来 / instax =====
    'polaroid_600': dict(contrast=-0.08, shoulder=0.30, sat=0.82, lift=0.030,
                         sat_hues={C_: 1.14, B_: 1.08, R_: 0.92, O_: 0.92},
                         hue_rot={C_: -8, B_: 6}, fog=(0.0, 0.016, 0.020),
                         crosstalk=0.04, max_gray=16),
    'polaroid_sx70': dict(contrast=-0.12, shoulder=0.32, sat=0.76, lift=0.034,
                          sat_hues={C_: 1.10, R_: 0.90, O_: 0.94},
                          hue_rot={C_: -6, Y_: -5}, fog=(0.020, 0.014, 0.004),
                          crosstalk=0.045, max_gray=16),
    'polaroid_itype': dict(contrast=-0.02, shoulder=0.26, sat=0.88, lift=0.024,
                           sat_hues={C_: 1.10, B_: 1.06, O_: 0.94},
                           hue_rot={C_: -5}, fog=(0.004, 0.012, 0.014),
                           crosstalk=0.035, max_gray=14),
    'polaroid_expired': dict(contrast=-0.14, shoulder=0.34, sat=0.70, lift=0.040,
                             sat_hues={Y_: 1.18, G_: 1.14, B_: 0.80, M_: 0.84},
                             hue_rot={Y_: -6, B_: 8}, fog=(0.022, 0.020, 0.0),
                             crosstalk=0.05, max_gray=22),
    'instax_mini': dict(contrast=0.02, shoulder=0.22, sat=0.96, lift=0.018,
                        sat_hues={O_: 1.10, R_: 1.06, C_: 1.04, B_: 0.94},
                        hue_rot={C_: -4}, fog=(0.012, 0.006, 0.004),
                        crosstalk=0.03, max_gray=12),
}


def fit_gray(p, limit):
    """灰轴落差超限时，等比收敛色偏（fog / shadow / high 相对均值的偏差）。"""
    p = dict(p)
    for _ in range(14):
        gap = measure(p)[0]
        if gap <= limit:
            return p, gap
        for key in ('fog', 'shadow', 'high'):
            t = p.get(key)
            if t:
                m = sum(t) / 3.0
                p[key] = tuple(m + (v - m) * 0.82 for v in t)
    return p, measure(p)[0]


def load_films():
    """优先读 films.json（可调参），否则用内置 FILMS。"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'films.json')
    if not os.path.isfile(path):
        return FILMS
    raw = json.load(open(path, encoding='utf-8'))
    out = {}
    for name, v in raw.items():
        if name.startswith('_'):
            continue
        p = {}
        for pk, pv in v.items():
            if pk in ('sat_hues', 'hue_rot'):
                p[pk] = {int(h): float(x) for h, x in pv.items()}
            elif pk in ('shadow', 'high', 'fog', 'gamma', 'wb'):
                p[pk] = tuple(float(x) for x in pv)
            elif pk == 'max_gray':
                p[pk] = int(pv)
            else:
                p[pk] = float(pv)
        out[name] = p
    return out


def main():
    global OUT_BIN, OUT_CUBE, WARM_GUARD
    argv = sys.argv[1:]
    if '--out' in argv:
        d = argv[argv.index('--out') + 1]
        OUT_BIN = os.path.join(d, 'bin')
        OUT_CUBE = os.path.join(d, 'cube')
    if '--warm-guard' in argv:
        WARM_GUARD = float(argv[argv.index('--warm-guard') + 1])
    only = None
    if '--only' in argv:
        only = {s.strip() for s in argv[argv.index('--only') + 1].split(',')}

    films = load_films()
    if only:
        films = {k: v for k, v in films.items() if k in only}
    os.makedirs(OUT_BIN, exist_ok=True)
    os.makedirs(OUT_CUBE, exist_ok=True)
    rows = []
    for name, p in films.items():
        limit = p.get('max_gray', 12)
        p2, gap = fit_gray(p, limit)
        data = build(p2)
        assert len(data) == 19712, (name, len(data))
        with open(os.path.join(OUT_BIN, name + '.bin'), 'wb') as f:
            f.write(data)
        write_cube(p2, os.path.join(OUT_CUBE, name + '.cube'))
        g, w, k, sd, kd = measure(p2)
        rows.append((name, g, w, k, sd, kd))

    print(f'{"name":22s} {"灰轴":>4s}  {"白点":>13s}  {"黑点":>11s}  {"肤色ΔS":>6s} {"天ΔS":>6s}  判定')
    for name, g, w, k, sd, kd in sorted(rows, key=lambda r: r[1]):
        lv = 'safe' if g <= 12 else ('mild' if g <= 25 else 'strong')
        print(f'{name:22s} {g:4d}  {str(w):>13s}  {str(k):>11s}  {sd:+6.2f} {kd:+6.2f}  {lv}')
    print(f'\n共 {len(rows)} 张，输出 {OUT_BIN} / {OUT_CUBE}')


if __name__ == '__main__':
    main()
