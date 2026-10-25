#!/usr/bin/env python3
"""mk_ycc.py —— 把 RGB 表转成 YCbCr 表（验证「引擎按 YCbCr 解表」假设）

2026-10-25 现场证据链：
  · identity17 走纯线性电平映射（out = 9 + 0.729·v，通道独立、不可能改色相）
    上机后「整个画面变绿」⇒ 引擎没有按 RGB 读这三个字节
  · 按 (Y, Cr, Cb) 解读推演，四条独立观测全部命中：
      黑(0,0,0)      → (0,135,0)    绿      ← 对应「整幅变绿」
      白(255,255,255)→ (255,120,255) 品红   ← 对应「偏品红紫」
      天蓝(100,150,200)→(131,59,228)  紫     ← 对应「蓝冷色出不来」
      cool 冷区(20,80,235)→(0,17,210) 蓝     ← 对应 zz_diag_cool「冷色区纯蓝」

用法:
  python mk_ycc.py --src ../../looks/identity17.bin --order ycrcb --out x.bin
  python mk_ycc.py --src ../../looks/identity17.bin --order ycbcr --out y.bin
  python mk_ycc.py --src ../../looks/cool_blue.bin  --order ycrcb --out z.bin
"""
import argparse
import pathlib

TABLE = 19652
PAD = 60

# BT.601 full-range。相机 ISP 常用 601；709 的系数差别在 2% 级，先用 601 判方向
def rgb2ycc(r, g, b, m="601"):
    if m == "709":
        y = 0.2126 * r + 0.7152 * g + 0.0722 * b
        cr = 0.5 * r - 0.4542 * g - 0.0458 * b + 128.0
        cb = -0.1146 * r - 0.3854 * g + 0.5 * b + 128.0
    else:
        y = 0.299 * r + 0.587 * g + 0.114 * b
        cr = 0.5 * r - 0.418688 * g - 0.081312 * b + 128.0
        cb = -0.168736 * r - 0.331264 * g + 0.5 * b + 128.0
    return y, cr, cb


def clamp8(x):
    return 0 if x < 0 else (255 if x > 255 else int(x + 0.5))


def convert(raw, order, m):
    buf = bytearray(raw[:TABLE])
    for o in range(0, TABLE, 4):
        r, g, b = buf[o], buf[o + 1], buf[o + 2]
        y, cr, cb = rgb2ycc(r, g, b, m)
        if order == "ycrcb":
            t = (y, cr, cb)
        elif order == "ycbcr":
            t = (y, cb, cr)
        else:
            raise SystemExit("order 只能是 ycrcb / ycbcr")
        buf[o], buf[o + 1], buf[o + 2] = clamp8(t[0]), clamp8(t[1]), clamp8(t[2])
    return bytes(buf) + (raw[TABLE:TABLE + PAD] if len(raw) >= TABLE + PAD else b'\0' * PAD)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--order", default="ycrcb", choices=["ycrcb", "ycbcr"])
    ap.add_argument("--matrix", default="601", choices=["601", "709"])
    args = ap.parse_args()
    raw = pathlib.Path(args.src).read_bytes()
    out = convert(raw, args.order, args.matrix)
    pathlib.Path(args.out).write_bytes(out)

    def enc(d, r, g, b):
        def i(v):
            return min(16, max(0, int(round(v * 16 / 255.0))))
        o = ((i(b) * 17 + i(g)) * 17 + i(r)) * 4
        return tuple(d[o:o + 3])

    print(f"{args.out}  ({len(out)}B, order={args.order}, BT.{args.matrix})")
    print(f"\n{'输入':<18} {'RGB 原值':>16} {'YCbCr 编码后':>18}")
    for nm, (r, g, b) in {"黑": (0, 0, 0), "灰128": (128, 128, 128), "白": (255, 255, 255),
                          "红": (255, 0, 0), "绿": (0, 255, 0), "蓝": (0, 0, 255),
                          "天蓝(100,150,200)": (100, 150, 200)}.items():
        print(f"{nm:<18} {str(enc(raw, r, g, b)):>16} {str(enc(out, r, g, b)):>18}")


if __name__ == "__main__":
    main()
