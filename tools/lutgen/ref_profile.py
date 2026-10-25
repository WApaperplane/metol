#!/usr/bin/env python3
"""ref_profile.py —— 口径画像：拿原厂表当标尺，量出全库的越界项

背景（2026-10-25）：蓝区饱和修好后，木一指出「其他颜色口径和黑白电平都得对齐，
否则就是会很怪」，并实测 kodachrome 暗部严重发绿。
本脚本把「口径」拆成四个可量的维度，逐表与原厂 samsung_a00 对比：

  ① 电平   黑点亮度 / 白点亮度          ← 原厂 9 / 195(R,G) 228(B)
  ② 色相饱和上限  各色相在 s=0.85 时的输出饱和度  ← 原厂按色相不同
  ③ 明度饱和曲线  各明度段的输出饱和度  ← 暗部是否被过饱和放大
  ④ 暗部色度      v=0.15 处的平均 chroma  ← 暗部染色（"暗部发绿"的入口）

用法:
  python ref_profile.py                     # 全库 vs 原厂
  python ref_profile.py --bin kodak_kchrome64
"""
import argparse
import colorsys
import pathlib

N = 17
TABLE = 19652
ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
REF = "samsung_a00"

HUES = [0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330]
VLV = [0.15, 0.35, 0.55, 0.80]


def load(p):
    return pathlib.Path(p).read_bytes()[:TABLE]


def sample(lut, r, g, b):
    """三线性插值，输入 8bit。"""
    def coord(v):
        f = v * 16.0 / 255.0
        if f <= 0:
            return 0, 0, 0.0
        if f >= 16:
            return 16, 16, 0.0
        i = int(f)
        return i, i + 1, f - i

    r0, r1, tr = coord(r)
    g0, g1, tg = coord(g)
    b0, b1, tb = coord(b)
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


def hsv(r, g, b):
    h, s, v = colorsys.rgb_to_hsv(max(0, min(255, r)) / 255.0,
                                  max(0, min(255, g)) / 255.0,
                                  max(0, min(255, b)) / 255.0)
    return h * 360.0, s, v


def profile(lut):
    out = {}
    lo = sample(lut, 0, 0, 0)
    hi = sample(lut, 255, 255, 255)
    out["black"] = sum(lo) / 3.0
    out["white"] = sum(hi) / 3.0
    # ② 各色相饱和上限（s_in=0.85, v=0.55）
    hs = {}
    for h in HUES:
        r, g, b = colorsys.hsv_to_rgb(h / 360.0, 0.85, 0.55)
        o = sample(lut, r * 255, g * 255, b * 255)
        hs[h] = hsv(*o)[1]
    out["hue_sat"] = hs
    # ③ 各明度段饱和（色相 0/120/240 平均）
    vs = {}
    for v in VLV:
        vals = []
        for h in (0, 120, 240):
            r, g, b = colorsys.hsv_to_rgb(h / 360.0, 0.60, v)
            o = sample(lut, r * 255, g * 255, b * 255)
            vals.append(hsv(*o)[1])
        vs[v] = sum(vals) / 3.0
    out["v_sat"] = vs
    # ④ 暗部色度
    ch = []
    for h in HUES:
        r, g, b = colorsys.hsv_to_rgb(h / 360.0, 0.60, 0.15)
        o = sample(lut, r * 255, g * 255, b * 255)
        _, s, _ = hsv(*o)
        ch.append(s)
    out["dark_sat"] = sum(ch) / len(ch)
    return out


def fmt_hue_row(hs):
    return " ".join(f"{hs[h]:.2f}" for h in HUES)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(ROOT / "looks"))
    ap.add_argument("--bin")
    args = ap.parse_args()
    d = pathlib.Path(args.dir)

    # 标尺恒从仓库 looks/ 取原厂表，与 --dir 无关
    ref = profile(load(ROOT / "looks" / f"{REF}.bin"))
    print(f"标尺 = {REF}（原厂槽镜像）")
    print(f"  黑点 {ref['black']:.1f}   白点 {ref['white']:.1f}   暗部饱和度 {ref['dark_sat']:.2f}")
    print(f"  色相饱和上限: {fmt_hue_row(ref['hue_sat'])}")
    print(f"  明度饱和: " + "  ".join(f"v{v}={ref['v_sat'][v]:.2f}" for v in VLV))
    print(f"  （色相列顺序 {HUES}）\n")

    names = [args.bin] if args.bin else [p.stem for p in sorted(d.glob("*.bin"))]
    names = [n for n in names if n != REF]
    rows = []
    for n in names:
        p = d / f"{n}.bin"
        if not p.exists():
            continue
        pr = profile(load(p))
        over_h = [h for h in HUES if pr["hue_sat"][h] > ref["hue_sat"][h] + 0.12]
        rows.append((n, pr, over_h))
    rows.sort(key=lambda r: -(r[1]["dark_sat"] - ref["dark_sat"]))

    print(f"{'表':<22} {'黑点':>5} {'白点':>5} {'暗部饱和':>8} {'超标色相（>原厂+0.12）':<28} 明度饱和 v0.15/0.55")
    for n, pr, over in rows:
        flag = ",".join(str(h) for h in over) if over else "-"
        print(f"{n:<22} {pr['black']:>5.1f} {pr['white']:>5.1f} {pr['dark_sat']:>8.2f} {flag:<28} "
              f"{pr['v_sat'][0.15]:.2f}/{pr['v_sat'][0.55]:.2f}")


if __name__ == "__main__":
    main()
