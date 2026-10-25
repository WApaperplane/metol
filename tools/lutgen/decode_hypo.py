#!/usr/bin/env python3
"""decode_hypo.py —— 机上解表假设的判别（只读）

问题（2026-10-25）：本地表在冷色域 dHue 全在 ±7° 内（cool_probe 已证），
实机却"没有一张能给蓝冷色，冷调一律偏品红/紫"。说明引擎读取方式与
生成假设不一致。本脚本把各种「错法」都算一遍，看谁能复现该现象。

判别要求同时满足两条：
  ① 冷色域 dHue 明显 > 0（蓝往紫滑）
  ② 暖色域（肤色/暖光）dHue 基本不变（用户只抱怨冷色）

用法: python decode_hypo.py [--dir looks] [--top 12]
"""
import argparse
import colorsys
import math
import pathlib

N = 17
TABLE = 19652
ROOT = pathlib.Path(__file__).resolve().parent.parent.parent


def load(p):
    return pathlib.Path(p).read_bytes()[:TABLE]


def sample(lut, fr, fg, fb):
    """fr/fg/fb ∈ [0,16] 浮点坐标，三线性插值。"""
    def coord(f):
        if f <= 0:
            return 0, 0, 0.0
        if f >= 16:
            return 16, 16, 0.0
        i = int(f)
        return i, i + 1, f - i

    r0, r1, tr = coord(fr)
    g0, g1, tg = coord(fg)
    b0, b1, tb = coord(fb)
    acc = [0.0, 0.0, 0.0]
    for ri, wr in ((r0, 1 - tr), (r1, tr)):
        for gi, wg in ((g0, 1 - tg), (g1, tg)):
            for bi, wb in ((b0, 1 - tb), (b1, tb)):
                w = wr * wg * wb
                if w <= 0:
                    continue
                o = ((bi * N + gi) * N + ri) * 4
                acc[0] += lut[o] * w
                acc[1] += lut[o + 1] * w
                acc[2] += lut[o + 2] * w
    return acc


def srgb_to_lin(c):
    c /= 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def lin_to_srgb(c):
    v = 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055
    return max(0.0, min(255.0, v * 255.0))


def hsv(r, g, b):
    h, s, v = colorsys.rgb_to_hsv(max(0, min(255, r)) / 255.0,
                                  max(0, min(255, g)) / 255.0,
                                  max(0, min(255, b)) / 255.0)
    return h * 360.0, s, v


def dHue(hin, hout):
    d = hout - hin
    while d > 180:
        d -= 360
    while d < -180:
        d += 360
    return d


# ---------- 各种解码假设 ----------
def hy_normal(lut, r, g, b):
    """基准：按 sRGB 编码值直接查表（= 生成时的假设）"""
    return sample(lut, r * 16 / 255, g * 16 / 255, b * 16 / 255)


def hy_linear_in(lut, r, g, b):
    """引擎把输入当线性值查表，输出直接当 sRGB 看（少一次传递函数）"""
    lr, lg, lb = srgb_to_lin(r), srgb_to_lin(g), srgb_to_lin(b)
    return sample(lut, lr * 16, lg * 16, lb * 16)


def hy_linear_both(lut, r, g, b):
    """输入当线性、输出再转回 sRGB（引擎内部线性工作流）"""
    lr, lg, lb = srgb_to_lin(r), srgb_to_lin(g), srgb_to_lin(b)
    o = sample(lut, lr * 16, lg * 16, lb * 16)
    return [lin_to_srgb(c / 255.0) for c in o]


def hy_swap_rg(lut, r, g, b):
    """索引里 R/G 次序颠倒"""
    return sample(lut, g * 16 / 255, r * 16 / 255, b * 16 / 255)


def hy_swap_rb(lut, r, g, b):
    """索引里 R/B 次序颠倒（等价于按 BGR 存、RGB 读）"""
    return sample(lut, b * 16 / 255, g * 16 / 255, r * 16 / 255)


def hy_swap_gb(lut, r, g, b):
    """索引里 G/B 次序颠倒"""
    return sample(lut, r * 16 / 255, b * 16 / 255, g * 16 / 255)


def hy_out_bgr(lut, r, g, b):
    """索引对，但输出三字节按 BGR 读"""
    o = sample(lut, r * 16 / 255, g * 16 / 255, b * 16 / 255)
    return [o[2], o[1], o[0]]


def hy_byteswap_out(lut, r, g, b):
    """输出 32bit 像素按字节反序读（RGBA → ABGR）"""
    o = sample(lut, r * 16 / 255, g * 16 / 255, b * 16 / 255)
    return [o[2], o[1], o[0]]          # 与 bgr 相同效果，保留占位便于区分


HYPS = [
    ("norm  编码域查表（生成假设）", hy_normal),
    ("linIn 输入当线性、输出当编码", hy_linear_in),
    ("linBs 输入线性 + 输出转回", hy_linear_both),
    ("swRG  索引 R/G 互换", hy_swap_rg),
    ("swRB  索引 R/B 互换", hy_swap_rb),
    ("swGB  索引 G/B 互换", hy_swap_gb),
    ("outBG 输出按 BGR 读", hy_out_bgr),
]

COOL = [(h, s, v) for h in (195, 210, 225, 240, 255, 265) for s in (0.35, 0.6, 0.85) for v in (0.35, 0.55, 0.78)]
WARM = [(h, s, v) for h in (15, 25, 35, 45) for s in (0.25, 0.45, 0.65) for v in (0.4, 0.6, 0.85)]


def score(lut, fn, probes):
    tot = dh = ds = 0.0
    for hin, sin, vin in probes:
        r, g, b = colorsys.hsv_to_rgb(hin / 360.0, sin, vin)
        r, g, b = r * 255, g * 255, b * 255
        o = fn(lut, r, g, b)
        hout, sout, _ = hsv(*o)
        w = sin * (1.0 if sout > 0.08 else 0.0)     # 无彩输出不计色相
        dh += dHue(hin, hout) * w
        ds += (sout - sin) * w
        tot += w
    return (dh / tot if tot else 0.0), (ds / tot if tot else 0.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(ROOT / "looks"))
    ap.add_argument("--top", type=int, default=10)
    args = ap.parse_args()

    files = sorted(pathlib.Path(args.dir).glob("*.bin"))
    files = [p for p in files if not p.stem.startswith("mono") and p.stem != "warm_sepia"]
    print(f"样本 {len(files)} 张（已剔除 mono_* 与 warm_sepia：输出无彩，hue 无意义）")
    print("判别要求：冷色 dHue 显著 > 0，同时暖色 dHue 接近 0\n")

    print(f"{'假设':<30} {'冷dHue中位':>11} {'暖dHue中位':>11} {'冷|dHue|>15 张数':>16} {'暖|dHue|>8 张数':>15}  判读")
    for label, fn in HYPS:
        cools, warms = [], []
        for p in files:
            lut = load(p)
            c, _ = score(lut, fn, COOL)
            w, _ = score(lut, fn, WARM)
            cools.append(c)
            warms.append(w)
        med = lambda xs: sorted(xs)[len(xs) // 2]
        nc = sum(1 for x in cools if abs(x) > 15)
        nw = sum(1 for x in warms if abs(x) > 8)
        verdict = ""
        if med(cools) > 10 and abs(med(warms)) < 8:
            verdict = "★ 同时满足两条"
        elif med(cools) > 10:
            verdict = "冷色偏紫，但暖色也错"
        print(f"{label:<30} {med(cools):>+11.2f} {med(warms):>+11.2f} {nc:>16} {nw:>15}  {verdict}")

    print(f"\n--- 逐表细看（前 {args.top} 张留机表 × 各假设的冷色 dHue）---")
    keep = ["cool_arctic", "cool_blue", "cool_mint", "cool_slate", "cool_steel",
            "fuji_astia100f", "kodak_portra400", "pentax_reversal", "style_matte", "ricoh_positive"]
    print(f"{'表':<20} " + " ".join(f"{l.split()[0]:>8}" for l, _ in HYPS))
    for name in keep:
        p = pathlib.Path(args.dir) / f"{name}.bin"
        if not p.exists():
            continue
        lut = load(p)
        row = " ".join(f"{score(lut, fn, COOL)[0]:>+8.2f}" for _, fn in HYPS)
        print(f"{name:<20} {row}")


if __name__ == "__main__":
    main()
