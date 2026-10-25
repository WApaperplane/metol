#!/usr/bin/env python3
"""cool_probe.py —— 冷色域色相体检（只读，不改任何表）

动机（2026-10-25）：实机观察「没有一张表能给出蓝冷色，冷调一律偏品红/紫」。
本脚本直接在 .bin 表上取冷色输入，算输出的 hue 位移，判断紫化是
「表本身的行为」还是「机上解表问题」。

判据：
  dHue > 0   ⇒ 蓝往紫/品红方向滑（hue 240 → 270 → 300）
  dHue < 0   ⇒ 蓝往青方向滑（hue 240 → 210 → 180）
冷色域取 hue∈[195,265]、s∈[0.25,0.85]、v∈[0.30,0.80]。

用法：
  python cool_probe.py                     # 扫 looks/ 全部
  python cool_probe.py --dir some/dir
  python cool_probe.py --bin cool_blue.bin # 单表详表（含逐档分解）
  python cool_probe.py --top 20            # 只列紫化最严重的前 N
  python cool_probe.py --json out.json
"""
import argparse
import colorsys
import json
import math
import pathlib
import sys
from native_codec import rgb_grid_view

N = 17
GRID = [i * 16 for i in range(16)] + [255]
STEP = 19712
TABLE = 19652          # 4913 * 4
ROOT = pathlib.Path(__file__).resolve().parent.parent.parent


def load_lut(path):
    raw = rgb_grid_view(path)
    if len(raw) < TABLE:
        raise ValueError(f"{path}: 长度 {len(raw)} < {TABLE}")
    return raw[:TABLE]


def at(lut, r8, g8, b8):
    """三线性插值取值 —— 必须插值。17 格点直接取最近点会把输出量化到 16 级，
    色相抖动可达 ±15°，测出来的全是量化噪声（identity17 也会报出几十度偏差）。"""
    def coord(v):
        v = max(0.0,min(255.0,v))
        i0 = min(15,int(v // 16))
        return i0, i0 + 1, (v-GRID[i0])/(GRID[i0+1]-GRID[i0])

    r0, r1, tr = coord(r8)
    g0, g1, tg = coord(g8)
    b0, b1, tb = coord(b8)

    def px(ri, gi, bi):
        o = ((bi * N + gi) * N + ri) * 4
        return lut[o], lut[o + 1], lut[o + 2]

    acc = [0.0, 0.0, 0.0]
    for ri, wr in ((r0, 1.0 - tr), (r1, tr)):
        if wr <= 0.0 and ri != r0:
            continue
        for gi, wg in ((g0, 1.0 - tg), (g1, tg)):
            if wg <= 0.0 and gi != g0:
                continue
            for bi, wb in ((b0, 1.0 - tb), (b1, tb)):
                if wb <= 0.0 and bi != b0:
                    continue
                w = wr * wg * wb
                if w <= 0.0:
                    continue
                p = px(ri, gi, bi)
                acc[0] += p[0] * w
                acc[1] += p[1] * w
                acc[2] += p[2] * w
    return acc[0], acc[1], acc[2], 0


def hsv(r, g, b):
    h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
    return h * 360.0, s, v


def hue_delta(hin, hout):
    d = hout - hin
    while d > 180.0:
        d -= 360.0
    while d < -180.0:
        d += 360.0
    return d


def probes():
    """冷色探针：hue 195..265 × s 3 档 × v 3 档。"""
    out = []
    for h in (195, 210, 225, 240, 255, 265):
        for s in (0.30, 0.55, 0.80):
            for v in (0.35, 0.55, 0.78):
                r, g, b = colorsys.hsv_to_rgb(h / 360.0, s, v)
                out.append((h, s, v, round(r * 255), round(g * 255), round(b * 255)))
    return out


def score(lut):
    """返回冷色域的加权 dHue / dSat / dLum，权重按输入饱和度。"""
    tot_w = 0.0
    dh = ds = dl = 0.0
    rows = []
    for hin, sin, vin, r8, g8, b8 in probes():
        ro, go, bo, _ = at(lut, r8, g8, b8)
        hout, sout, vout = hsv(ro, go, bo)
        # 输出几乎无彩（被压成灰）时色相无意义，权重降低
        w = sin * (1.0 if sout > 0.08 else 0.25)
        d = hue_delta(hin, hout)
        dh += d * w
        ds += (sout - sin) * w
        dl += (vout - vin) * w
        tot_w += w
        rows.append((hin, sin, vin, (r8, g8, b8), (ro, go, bo), d, sout - sin, vout - vin))
    if tot_w <= 0:
        return 0.0, 0.0, 0.0, rows
    return dh / tot_w, ds / tot_w, dl / tot_w, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(ROOT / "looks"))
    ap.add_argument("--bin")
    ap.add_argument("--top", type=int, default=0)
    ap.add_argument("--json")
    args = ap.parse_args()

    if args.bin:
        p = pathlib.Path(args.bin)
        if not p.is_absolute():
            p = pathlib.Path(args.dir) / args.bin
        lut = load_lut(p)
        dh, ds, dl, rows = score(lut)
        print(f"=== {p.name} === 冷色域 dHue={dh:+.2f}° dSat={ds:+.3f} dLum={dl:+.3f}\n")
        print(f"{'inH':>5} {'s':>4} {'v':>4}  {'IN rgb':>15}  {'OUT rgb':>15}  {'dHue':>7} {'dSat':>6} {'dLum':>6}")
        for hin, sin, vin, i, o, d, dsv, dlv in rows:
            print(f"{hin:>5} {sin:>4.2f} {vin:>4.2f}  {str(i):>15}  {str(o):>15}  {d:>+7.2f} {dsv:>+6.3f} {dlv:>+6.3f}")
        return

    d = pathlib.Path(args.dir)
    files = sorted(d.glob("*.bin"))
    if not files:
        sys.exit(f"没有找到 *.bin: {d}")
    res = []
    for p in files:
        try:
            lut = load_lut(p)
        except ValueError as e:
            print(f"[skip] {e}", file=sys.stderr)
            continue
        dh, ds, dl, _ = score(lut)
        res.append({"name": p.stem, "dHue": dh, "dSat": ds, "dLum": dl})
    res.sort(key=lambda x: -x["dHue"])

    print(f"冷色域体检：{d}  共 {len(res)} 张")
    print("dHue>0 = 蓝往紫滑（品红倾向）；dHue<0 = 蓝往青滑\n")
    print(f"{'表名':<26} {'dHue':>8} {'dSat':>8} {'dLum':>8}  判读")
    shown = res[: args.top] if args.top else res
    for r in shown:
        if r["dHue"] >= 20:
            tag = "★ 严重紫化"
        elif r["dHue"] >= 10:
            tag = "紫化明显"
        elif r["dHue"] >= 4:
            tag = "轻微紫化"
        elif r["dHue"] <= -20:
            tag = "严重偏青"
        elif r["dHue"] <= -4:
            tag = "偏青"
        else:
            tag = "接近中性"
        print(f"{r['name']:<26} {r['dHue']:>+8.2f} {r['dSat']:>+8.3f} {r['dLum']:>+8.3f}  {tag}")

    if args.json:
        pathlib.Path(args.json).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n已写 {args.json}")


if __name__ == "__main__":
    main()
