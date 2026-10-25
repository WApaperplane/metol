#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_luts.py — 生成三星 NX500 (DRIMe5) 硬件 3D LUT 表

设计格式：display-referred RGB；机端输出必须通过 native_codec 编译为 Cr,Cb,Y。
  17^3 格点，每项 4 字节 {Cr,Cb,Y,pad=0}
  index = ((Y*17 + Cb)*17 + Cr) * 4   ← Cr 变化最快
  格点值 = [0,16,32,...,240,255]       ← 前 16 步 16，末步 15
  identity 不能证明三轴是 RGB；见 LUT_COLORSPACE_REGRESSION_REVIEW_2026-10-25.md。

管线（gamma 域为主，白平衡与串扰在 linear 域）：
  linear → WB → 逐层 gamma → S 曲线 → 高光滚降 → 提升+色罩
         → 染料串扰 → 色相选择性(饱和/旋转) → clamp
         → 暖色保护(削 R) → 量化 → 冷色保护(蓝区饱和封顶)
"""

import json
import math
import os
import struct
import sys
from native_codec import compile_rgb, record_native

N = 17
GRID = [16 * i for i in range(16)] + [255]
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))          # tools/lutgen → 仓库根
OUT_BIN = os.path.join(REPO, 'looks')                  # 直接写发布物目录
OUT_CUBE = os.path.join(HERE, 'cube')                  # .cube 中间产物（不入库）
WARM_GUARD = 0.0      # 默认关闭，改由 auto_warm() 闭环反算（见下）；配方可显式覆盖
WARM_HUEW = 60.0      # 色相窗口半宽（度）。>0 用余弦淡出，边界处 R 不突变
WARM_VSOFT = True     # v 门槛软化，避免红轴低端亮度倒挂
WARM_CUT = 0.15       # 单点最大削幅，占该点 R 的比例（1.0 = 不限制）
WARM_LIFT = 0.0       # 削幅还给 G 的比例；0.51 ≈ 亮度守恒。默认 0：实测会过冲（见文档）
COOL_CAP = 0.0        # 旧的蓝区饱和硬封顶，默认关（由第 10 步色域映射取代）
COOL_HMIN = 190.0     # 冷色保护色相范围（度）
COOL_HMAX = 270.0
WARM_GAIN = 1.0 / 6.4  # 实测：warm_guard +0.45 ⇒ 肤色 dHue 约 +2.9°，故 1°/0.156


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
# 色相锚点插值核宽。σ=38 时 h=30 处锚点 30 的自身权重只有 36%（其余来自 0/60/330
# 的溢出）⇒ 8 个锚点实际只有 3–4 个有效自由度，填 ±5° 的 hue_rot 出来的位移是
# ±1.5°。这是「填了参数但看不出效果」的直接原因。σ=20 时自身权重升到 53%，
# 相邻锚点仍能平滑过渡（30° 间隔下重叠 25%）。
HUE_SIGMA = 20.0

# ---------- 饱和包络（从原厂实测反推） ----------
# 原厂 samsung_a00 在 h=230 的饱和映射实测：
#   v=1.00:  0.70→0.58  0.80→0.62  0.90→0.67  0.95→0.69  1.00→0.71
#   v=0.85:  0.70→0.67  0.80→0.74  0.90→0.81  0.95→0.84  1.00→0.87
#   v=0.70:  0.70→0.74  0.80→0.83  0.90→0.91  0.95→0.94  1.00→0.98
#   v=0.50:  0.70→0.77  0.80→0.85  0.90→0.91  0.95→0.94  1.00→0.97
# 两个规律：压缩量随 v 急剧增强（v≤0.70 几乎不压，v=1 压到 0.71），且随 s 增强。
# 拟合 s_out = s·(1 − A·w(v)·s)，w=((v−0.70)/0.30)^1.3，A 按色相：
#   h∈[150,330]（青蓝紫）A=0.29 → 三个蓝端角点全部落在 .71（实测 .709）
#   h=0/122（红绿）A=0.036 → .964（实测 .968）
# 误差：h=230 全表 ≤0.023（v=1.0）/ ≤0.068（v=0.5）。
# ★ 这套模型解释了两件过去做错的事：
#   ① 原厂不压色域天花板（s_max 仍 0.93–1.00），只压高亮高饱和的极端点；
#   ② 旧 cool_guard 用 v 无关的硬截断 min(s,0.70)，把内部点一起压平
#      （蓝区输出饱和取值数 11 vs 原厂 39），蓝天渐变因此塌成一块平色。
SAT_A_COOL = 0.29     # 青蓝紫段压缩系数
SAT_V_KNEE = 0.65     # 起压亮度（0.65 才能让 v=0.70 时留 2% 压缩，对齐原厂 1.00→0.98）
SAT_V_EXP = 1.3       # 压缩随 v 增长的幂次


def sat_ceiling(h, v, s):
    """按明度与色相压缩饱和。v≤0.70 原样返回（暗部色相辨识度低，压了只会发闷）。"""
    d = abs((h - 240.0 + 180.0) % 360.0 - 180.0)
    if d <= 90.0:
        A = SAT_A_COOL
    else:
        A = SAT_A_COOL * max(0.0, 1.0 - (d - 90.0) / 60.0) ** 3
    if v <= SAT_V_KNEE or A <= 0.0:
        return s
    w = ((v - SAT_V_KNEE) / (1.0 - SAT_V_KNEE)) ** SAT_V_EXP
    return s * (1.0 - A * w * s)


# ---------- Lab 分离色调 ----------
# 为什么要在 Lab 里做：冷暖的严格定义是 b*（+黄/暖，−蓝/冷）。旧参数用 fog/shadow/high
# 的 R/G/B 小数直接往归一化值上加，量级 0.002–0.012 ⇒ 只相当于 0.5–3 个 8bit 级，
# gray_gap 中位 4。原厂 samsung 是 69–79。整个「胶片味道」的大半在这一层。
# 换成 Lab 里的 (b*暗部, b*高光, a*暗部, a*高光) 四个数后，参数即目标，不再靠试。
_M_RGB2XYZ = ((0.4124564, 0.3575761, 0.1804375),
              (0.2126729, 0.7151522, 0.0721750),
              (0.0193339, 0.1191920, 0.9503041))
_M_XYZ2RGB = ((3.2404542, -1.5371385, -0.4985314),
              (-0.9692660, 1.8760108, 0.0415560),
              (0.0556434, -0.2040259, 1.0572252))


def rgb_to_lab01(r, g, b):
    """r,g,b ∈0..1 → (L*, a*, b*) D65。"""
    r, g, b = srgb_to_lin(r), srgb_to_lin(g), srgb_to_lin(b)
    m = _M_RGB2XYZ
    x = (m[0][0] * r + m[0][1] * g + m[0][2] * b) / 0.95047
    y = m[1][0] * r + m[1][1] * g + m[1][2] * b
    z = (m[2][0] * r + m[2][1] * g + m[2][2] * b) / 1.08883

    def f(t):
        return t ** (1 / 3.0) if t > 0.008856 else 7.787 * t + 16 / 116.0
    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def lab01_to_rgb(L, a, bb):
    """(L*, a*, b*) → r,g,b ∈0..1，越界钳制。"""
    fy = (L + 16) / 116.0
    fx = fy + a / 500.0
    fz = fy - bb / 200.0

    def g(t):
        return t ** 3 if t ** 3 > 0.008856 else (t - 16 / 116.0) / 7.787
    x, y, z = g(fx) * 0.95047, g(fy), g(fz) * 1.08883
    m = _M_XYZ2RGB
    out = []
    for i in range(3):
        v = m[i][0] * x + m[i][1] * y + m[i][2] * z
        out.append(lin_to_srgb(0.0 if v < 0 else (1.0 if v > 1 else v)))
    return out[0], out[1], out[2]


def blue_converge(h, s, amount):
    """青与品红同时向蓝收束 —— 原厂最独特的一个算子。

    原厂 samsung_a00 实测：C(0,255,255)→(74,182,254) dHue **+22.8°**、
    M(255,0,255)→(182,74,254) dHue **−22.8°**、B(0,0,255) 不动。
    两个方向严格对称，因为它把青和品红都往 240° 拉。三张原厂表都是 22.5–25.8°，
    说明这是固定设计而非个例。

    形状：三角窗，峰在 |h−240|=60（即 180/300），零点在 240 和 150/330，
    因此 h=150 与 h=330 处不产生突变。

    ★ 权重是饱和度不是明度（第一次实现按 (1−0.85v) 衰减，v≈1 的角点直接归零，
      青完全不转 —— 但原厂 C 角点 v=0.996 却转 +22.8°）。正确的对应关系是：
        C 角点 (s=1.00) → +22.8° ｜ hi-lit (s=0.85) → +4.2° ｜ 天空 (s≈0.5) → 0
      用 `max(0,(s−0.75)/0.25)^1.5`：s=1 → 1.0，s=0.85 → 0.354，s≤0.75 → 0。
      因此它只作用在「高饱和+高亮」的色域边界上，中间调一格不碰。
    """
    if amount <= 0.0:
        return 0.0
    d = abs((h - 240.0 + 180.0) % 360.0 - 180.0)
    if d >= 90.0:
        return 0.0
    # ★ s 权重必须平缓：第一版用 ((s−0.75)/0.25)^1.5，在 s=0.75–1.0 之间斜率过大，
    #   相邻格点 s 差 0.1 就会让转角差 14° ⇒ cool_* 五张 jump_ratio 冲到 13–15（阈值 8），
    #   实机上会看到蓝色色带。改成 ((s−0.55)/0.45)^2：s=1→1、s=0.85→0.44、s=0.70→0.11、
    #   s≤0.55→0，过渡区间扩大到 0.45 且平方段连续可导。
    k = max(0.0, (s - 0.55) / 0.45) ** 2
    if k <= 0.0:
        return 0.0
    w = d / 60.0 if d <= 60.0 else (90.0 - d) / 30.0
    sign = 1.0 if ((h - 240.0) % 360.0) > 180.0 else -1.0
    return sign * amount * w * k


def apply_split(r, g, b, split, chroma_keep=0.55):
    """split = (b_dark, b_light, a_dark, a_light)。按 L* 二次权重分配，饱和度高的格点少动。

    chroma_keep：色度权重。高饱和处的色偏会被自身颜色盖住，硬加 b* 只会推脏，
    所以按 C/(C+C0) 衰减，C0=35 时 s≈0.5 的肤色仍有 60% 效果、纯色基本不动。
    """
    bd, bl, ad, al = split
    L, a, bb = rgb_to_lab01(r, g, b)
    wd = ((100.0 - L) / 100.0) ** 2
    wl = (L / 100.0) ** 2
    C = math.hypot(a, bb)
    k = chroma_keep + (1.0 - chroma_keep) * (35.0 / (35.0 + C))
    a += (ad * wd + al * wl) * k
    bb += (bd * wd + bl * wl) * k
    return lab01_to_rgb(L, a, bb)

def hue_weight(h, anchor, sigma=None):
    sigma = HUE_SIGMA if sigma is None else sigma
    d = abs((h - anchor + 180.0) % 360.0 - 180.0)
    return math.exp(-(d * d) / (2.0 * sigma * sigma))


def hue_lookup(h, table):
    """table: {anchor: value}，饱和乘数（基线 1.0）。

    ★ 这个函数原先是 `num/den`，den 下溢时返回 **0.0** —— 但它是乘数语义，
      返回 0 等于把饱和度清零。σ=20 之后必然触发：h=12° 的橙色到蓝锚点 240°
      距离 228°，exp(−228²/800) 直接下溢，den=0 ⇒ 返回 0 ⇒ (255,48,0) 输出成
      (249,249,249) 纯白。cool_blue 有 204 个格点对因此跳变 200+ 级。
      这是「大块橙色/肤色变灰白」的直接原因。

    ★ 同时不能用朴素归一化：单锚点表在整圈色相上都会给满值（{240:1.18} 在 h=12
      也给 1.18）。改成 `1 + Σw(v−1)/max(1,Σw)`：
        锚点上 Σw=1 → 给满；锚点之间 Σw>1 → 加权平均（不塌陷）；
        远处 Σw<1 → 按 Σw 线性衰减到 1.0（不污染）。
    """
    if not table:
        return 1.0
    num = den = 0.0
    for a, v in table.items():
        w = hue_weight(h, a)
        num += w * (v - 1.0)
        den += w
    if den < 1e-9:
        return 1.0
    return 1.0 + num / max(1.0, den)


def hue_shift(h, table):
    """table: {anchor: degrees}，高斯加权叠加。用于「偏移」语义（hue_rot，基线 0）。

    ★ 不能复用 hue_lookup：归一化会让只有单个锚点的表在整圈色相上全局生效 ——
      `hue_rot {120: -3}`（只想让绿偏黄）在 h=220 的蓝区也硬加 −3°，Portra400 的
      天空因此无端偏暖（实测贡献 dB* +2.2）。改成带截断的加权和：距锚点 70° 以外
      权重 < 0.05 直接丢弃，偏移归零。
    """
    if not table:
        return 0.0
    tot = 0.0
    for a, v in table.items():
        w = hue_weight(h, a, 34.0)
        if w < 0.05:
            continue
        tot += w * v
    return tot


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

    # 6.5) 分离色调（Lab 域）：胶片味道的主层。
    #      彩色负片的橙 mask 让暗部偏暖，反转片无 mask 则中性偏冷；Kodachrome 的
    #      K-14 是暖棕，Eterna 是青绿阴影。这些都表现为「b* 随 L* 变化」——
    #      用 Lab 直接给目标值，比用 fog/shadow 的 RGB 小数猜要可靠得多。
    split = p.get('split', None)
    if split:
        r, g, b = apply_split(r, g, b, split)

    # 7) 色相选择性：饱和 + 旋转（按 chroma 加权，中性灰不受影响）
    #
    #    ★ ring 参数化（(A, phi, C, k)）取代 8 锚点 hue_rot：
    #      dHue(h, v) = (A·sin(h−phi) + C) · max(0, 1 − k·v)
    #      为什么换：hue_lookup 用 σ=38° 高斯对 8 个锚点归一化，h=30 时锚点 30 的
    #      自身权重只有 36%（其余来自 0/60/330 的溢出）⇒ 8 个锚点实际只有 3–4 个
    #      有效自由度，做不出原厂 h=150 的 +40° 峰（150 不在任何锚点上）。
    #      三星原厂实测就是这条曲线的形状：a00 暗部 A≈35 phi≈60 C≈5 k≈0.79
    #      （暗部极差 71°、亮部 12°，比值 5.9×）。全库 60+ 张表的暗/亮梯度都在
    #      0.7–1.2，就是缺了 k 这一维 —— 亮部反倒比暗部转得多，方向是反的。
    sat_m = p.get('sat', 1.0)
    sat_h = p.get('sat_hues', {})
    rot_h = p.get('hue_rot', {})
    ring = p.get('ring', None)
    if sat_m != 1.0 or sat_h or rot_h or ring or p.get('bconv', 0.0) > 0.0:
        h, s, v = rgb_to_hsv(r, g, b)
        if s > 1e-4:
            m = sat_m * (hue_lookup(h, sat_h) if sat_h else 1.0)
            # 暗部保护：v 小时把 m 拉回 1，否则 s*m 打满 1.0 会让最小通道直接归零，
            # 暗部变成死黑、色阶断裂（2026-10-25 体检：velvia50 有 2253 个
            # 输入全非零的格点被压成 0）。只削暗部的额外饱和，中间调不动。
            if v < 0.25:
                m = 1.0 + (m - 1.0) * (v / 0.25)
            s = min(0.98, max(0.0, s * m))
            if ring:
                A, phi, cz, kk = ring
                h = h + (A * math.sin(math.radians(h - phi)) + cz) * max(0.0, 1.0 - kk * v)
            elif rot_h:
                h = h + hue_shift(h, rot_h)
            h = h + blue_converge(h, s, p.get('bconv', 0.0))
            r, g, b = hsv_to_rgb(h, s, v)

    # 8) 暖色保护：红橙高饱和区把 R 往 G 收一点。
    #    动机（2026-10-25 实机排查）：老批次 LUT 在室内暖光/人像上"偏红"，
    #    根因是高饱和表把暖色整体推向红端（灰轴反而是中性甚至偏蓝）。
    #    只削"红超出绿"的那部分，不改色相中心，风格与饱和度保留。
    #
    #    参数（配方级可覆盖）：
    #      warm_guard 强度。0 = 关闭；旧批次 0.30，2026-10-25 提到 0.45
    #      warm_smin  起削饱和度门槛（肤色 s 常在 0.25-0.45，0.15 = 覆盖到肤色）
    #      warm_pow   权重曲线指数（0.45 = 门槛附近也给足权重）
    #      warm_huew  色相窗口半宽（度）。0 = 旧版硬判 h≤50 或 h≥330；
    #                 >0 改用余弦淡出（边界处 R 不突变，但 30-50° 的权重会下降）
    #      warm_cut   单点最大削幅占该点 R 的比例（1.0 = 不封顶）
    #      warm_lift  削掉的 R 有多少比例还给 G（0 = 纯削暗，0.5 ≈ 亮度守恒）。
    #                 ★ 纯削 R 会把肤色整体压暗 10-12%（dLum -0.19 → -0.30），
    #                 还一半给 G 后色相照样回正而亮度基本不变。
    wg = p.get('warm_guard', WARM_GUARD)
    wsm = p.get('warm_smin', 0.30)          # 起削饱和度门槛；肤色 s 常在 0.25-0.45
    wpw = p.get('warm_pow', 0.7)            # 权重曲线指数
    whw = p.get('warm_huew', WARM_HUEW)     # 0 = 旧版硬边界
    wcap = p.get('warm_cut', WARM_CUT)      # 最大削幅占 R 的比例，1.0 = 不限制
    wlift = p.get('warm_lift', WARM_LIFT)   # 削幅还给 G 的比例，0 = 纯削暗
    vsoft = p.get('warm_vsoft', WARM_VSOFT)
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
            ex = r - g
            cut = ex * wg * w
            # 按 R 的比例封顶，不能按绝对量 —— 绝对量在低亮度处会压平红轴（曾致非单调）
            if wcap < 1.0:
                cut = min(cut, r * wcap)
            # 削幅上限必须连带 lift 一起算：还 G 之后 R 不能反被 G 追上，
            # 否则色相越过中性变黄绿（wg=0.9 + lift=0.51 时必然发生）。
            if wlift > 0.0:
                cut = min(cut, (r - g) / (1.0 + wlift))
            if cut > 0.0:
                r -= cut
                if wlift > 0.0:
                    # 亮度守恒：luma = .299R + .587G，Δluma ≈ -.299·cut + .587·(wlift·cut)
                    # ⇒ wlift = 0.51 时 Δluma ≈ 0。色相仍向黄侧移动（R 降 G 升）。
                    g += cut * wlift

    # 9) 量化
    out = []
    for v in (r, g, b):
        q = int(v * 255.0 + 0.5)
        out.append(0 if q < 0 else (255 if q > 255 else q))

    # 10) 饱和包络：按明度与色相压缩（取代旧的 cool_guard 硬截断）
    #     标定自原厂 samsung_a00 的 h=230 实测曲线（见文件头 SAT_* 注释）。
    #     旧 cool_guard 是 v 无关的 min(s,0.70)，把蓝天渐变压成一块平色；
    #     新模型只在 v>0.70 起压，v=1 的蓝端角点压到 0.715（原厂 0.709），
    #     而 v=0.7 的中间调几乎不碰（0.98 vs 原厂 0.98）。
    #     sat_env=0 可关；cool_guard 保留供逐张覆盖。
    if p.get('sat_env', 1.0) > 0.0 and max(out) > 0:
        h, s, v = rgb_to_hsv(out[0] / 255.0, out[1] / 255.0, out[2] / 255.0)
        if s > 1e-4:
            s2 = sat_ceiling(h, v, s)
            if abs(s2 - s) > 1e-5:
                r2, g2, b2 = hsv_to_rgb(h, max(0.0, min(1.0, s2)), v)
                out = [min(255, max(0, int(x * 255.0 + 0.5))) for x in (r2, g2, b2)]

    cg = p.get('cool_guard', COOL_CAP)
    if cg > 0.0 and max(out) > 0:
        h, s, v = rgb_to_hsv(out[0] / 255.0, out[1] / 255.0, out[2] / 255.0)
        if s > cg and COOL_HMIN <= h <= COOL_HMAX:
            r2, g2, b2 = hsv_to_rgb(h, cg, v)
            out = [min(255, max(0, int(x * 255.0 + 0.5))) for x in (r2, g2, b2)]

    return bytes(out) + b'\0'


def build_rgb(p):
    """Legacy RGB design grid for colour design only; never load into the camera."""
    buf = bytearray()
    for bi in range(N):
        for gi in range(N):
            for ri in range(N):
                buf += apply_film((GRID[ri], GRID[gi], GRID[bi]), p)
    buf += b'\0' * 60          # 槽尾 pad：19652B 表 + 60B = 19712B（步长 0x4D00）
    return bytes(buf)


def build(p):
    """Compile RGB design into the native Cr,Cb,Y input AND output coordinates."""
    return compile_rgb(build_rgb(p))


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
                o = apply_film((ri * 255.0 / (N-1), gi * 255.0 / (N-1),
                                bi * 255.0 / (N-1)), p)
                lines.append('%.6f %.6f %.6f' % (o[0] / 255, o[1] / 255, o[2] / 255))
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(lines) + '\n')


# 参数库已全部迁到 films.json（唯一源，可调参）；旧的内置 FILMS 兜底字典已删除，
# 因为它会和 films.json 漂移 —— 曾残留下架表的参数，误用会把已下架的表重新生成回来。


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


SKIN_PROBES = ((200, 150, 130), (196, 144, 118), (176, 132, 106))


def skin_dhue(p):
    """三个肤色点的平均 dHue（度）。正 = 偏黄，负 = 偏红。"""
    tot = 0.0
    for c in SKIN_PROBES:
        o = apply_film(c, p)
        h1, _, _ = rgb_to_hsv(c[0] / 255.0, c[1] / 255.0, c[2] / 255.0)
        h2, s2, _ = rgb_to_hsv(o[0] / 255.0, o[1] / 255.0, o[2] / 255.0)
        if s2 < 0.05:
            continue
        tot += (h2 - h1 + 180.0) % 360.0 - 180.0
    return tot / len(SKIN_PROBES)


def auto_warm(p, target=0.5, iters=8):
    """闭环反算 warm_guard：测该表自己的肤色 dHue，按偏差定量，不用全局常数。

    ★ 为什么必须闭环（2026-10-25 实测）：
      WARM_GUARD 做常数 0.45 时，canon_portrait 在 wg=0 本来是 +0.7°（完全不偏红），
      被硬推到 +3.6° 并压暗 2.4 级 —— 一张肖像表把脸色推黄，方向是反的；
      leica_m9 从 +3.8° 推到 +7.0°，雪上加霜；只有 velvia50 这种本来就 −3.4° 的修对了。
      同一常数作用在各表差异极大的偏差上，方向不可控。

    ★ 为什么必须迭代（同日实测）：一次线性外推不够。warm_guard 的实测增益随表而变
      （split 把肤色基线推暖后，同样的 wg 产生的 dHue 大不相同：kchrome25 外推 0.86
      实际冲到 +8.8°，而标定值是 6.4°/单位）。改成每轮测一次、按残差小步修正。

    只修「偏红」（dh < target），不修偏黄 —— 暖偏是反转片/金胶片的特征，不该抹。
    配方显式给 warm_guard 时尊重配方。
    """
    if 'warm_guard' in p:
        return dict(p)
    p0 = dict(p)
    wg = 0.0
    for _ in range(iters):
        p0['warm_guard'] = wg
        dh = skin_dhue(p0)
        err = target - dh
        if abs(err) < 0.35:
            break
        if wg <= 0.0 and err < 0:          # 本来就偏黄，一档都不加
            break
        wg = min(1.0, max(0.0, wg + err * WARM_GAIN))
    p0['warm_guard'] = wg
    return p0


def load_films():
    """读 films.json（唯一参数源）。缺文件直接报错 —— 不再有内置兜底。"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'films.json')
    if not os.path.isfile(path):
        raise SystemExit('缺 tools/lutgen/films.json：参数库是唯一源，请从仓库恢复后重跑')
    raw = json.load(open(path, encoding='utf-8'))
    out = {}
    for name, v in raw.items():
        if name.startswith('_'):
            continue
        p = {}
        for pk, pv in v.items():
            if pk in ('sat_hues', 'hue_rot'):
                p[pk] = {int(h): float(x) for h, x in pv.items()}
            elif pk in ('shadow', 'high', 'fog', 'gamma', 'wb', 'split'):
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
        # 有 split 的表由 Lab 目标直接控制冷暖，fit_gray 只管老的 fog/shadow/high 路径，
        # 不要在 split 表上跑（它会把已经设好的分离色调当成超限去收敛）
        if p.get('split'):
            p2, gap = p, measure(p)[0]
        else:
            p2, gap = fit_gray(p, limit)
        p2 = auto_warm(p2)
        data = build(p2)
        assert len(data) == 19712, (name, len(data))
        with open(os.path.join(OUT_BIN, name + '.bin'), 'wb') as f:
            f.write(data)
        record_native(os.path.join(OUT_BIN, name + '.bin'), data)
        write_cube(p2, os.path.join(OUT_CUBE, name + '.cube'))
        g, w, k, sd, kd = measure(p2)
        rows.append((name, g, w, k, sd, kd, skin_dhue(p2), p2.get('warm_guard', 0.0)))

    print(f'{"name":22s} {"灰轴":>4s}  {"白点":>13s}  {"肤色ΔS":>6s} {"天ΔS":>6s} {"肤色dHue":>8s} {"wg":>5s}  判定')
    for name, g, w, k, sd, kd, dh, wg in sorted(rows, key=lambda r: r[1]):
        lv = 'safe' if g <= 12 else ('mild' if g <= 25 else 'strong')
        print(f'{name:22s} {g:4d}  {str(w):>13s}  {sd:+6.2f} {kd:+6.2f} {dh:+8.1f} {wg:5.2f}  {lv}')
    print(f'\n共 {len(rows)} 张，输出 {OUT_BIN} / {OUT_CUBE}')


if __name__ == '__main__':
    main()
