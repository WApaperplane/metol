#!/usr/bin/env python3
"""mk_coolfix.py —— 蓝区降饱和修正（验证用）

发现（2026-10-25）：全库蓝角点饱和度中位 0.95，原厂 samsung_a00 只有 0.69。
把蓝推到 sRGB 蓝原色（0,0,255）在显示器上必然看起来偏紫 —— 这是「所有冷调表
都出不来蓝冷色、一律品红紫」的直接原因，与解表无关。

原厂做法：输入纯蓝 → 输出 (77,79,246)，饱和度 0.69，R/G 抬到 77/79。
本脚本对任意表做同样的事：在蓝区把饱和度封顶，保持色相与明度不变。

用法:
  python mk_coolfix.py --src ../../looks/cool_blue.bin --cap 0.70 --out xx.bin
  python mk_coolfix.py --src ../../looks/cool_blue.bin --cap 0.62 --hue -6 --out yy.bin
"""
import argparse
import colorsys
import pathlib

N = 17
GRID = [i * 16 for i in range(16)] + [255]
TABLE = 19652
PAD = 60


def work(src, cap, hue_shift, hmin, hmax, vmax=None):
    raw = pathlib.Path(src).read_bytes()
    buf = bytearray(raw[:TABLE])
    changed = 0
    for o in range(0, TABLE, 4):
        r, g, b = buf[o], buf[o + 1], buf[o + 2]
        h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
        hd = h * 360.0
        if not (hmin <= hd <= hmax) or s <= cap:
            continue
        s2 = cap
        h2 = (hd + hue_shift) % 360.0
        v2 = v if vmax is None else min(v, vmax)
        r2, g2, b2 = colorsys.hsv_to_rgb(h2 / 360.0, s2, v2)
        buf[o] = min(255, max(0, int(round(r2 * 255))))
        buf[o + 1] = min(255, max(0, int(round(g2 * 255))))
        buf[o + 2] = min(255, max(0, int(round(b2 * 255))))
        changed += 1
    return bytes(buf) + raw[TABLE:TABLE + PAD] if len(raw) >= TABLE + PAD else bytes(buf) + b'\0' * PAD, changed


def idx(r, g, b):
    return ((b * 17 + g) * 17 + r) * 4


def sat(o):
    mx, mn = max(o), min(o)
    return (mx - mn) / mx if mx else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--cap", type=float, default=0.70)
    ap.add_argument("--hue", type=float, default=0.0, help="蓝区色相附加旋转角度（负=往青）")
    ap.add_argument("--hmin", type=float, default=190.0)
    ap.add_argument("--hmax", type=float, default=270.0)
    ap.add_argument("--vmax", type=float, default=None)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    out, n = work(args.src, args.cap, args.hue, args.hmin, args.hmax, args.vmax)
    pathlib.Path(args.out).write_bytes(out)
    print(f"{args.out}  ({len(out)}B, 改动 {n} 个格点 = {n/4913*100:.1f}%)")
    src = pathlib.Path(args.src).read_bytes()
    print(f"\n{'输入点':<16} {'原':>18} {'新':>18}  饱和 原→新")
    for nm, (r, g, b) in {"纯蓝(0,0,255)": (0, 0, 16), "天蓝(90,140,199)": (6, 9, 12),
                          "青(40,159,199)": (3, 10, 12), "白(255)": (16, 16, 16)}.items():
        o = idx(r, g, b)
        a = tuple(src[o:o + 3])
        c = tuple(out[o:o + 3])
        print(f"{nm:<16} {str(a):>18} {str(c):>18}  {sat(a):.2f}→{sat(c):.2f}")


if __name__ == "__main__":
    main()
