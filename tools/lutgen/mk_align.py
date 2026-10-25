#!/usr/bin/env python3
"""mk_align.py —— 输出口径对齐（电平 + 暗部色度）

背景（2026-10-25）：木一指出「其他颜色口径和黑白电平都得对齐，否则就是会很怪」，
并实测 kodachrome 暗部严重发绿。ref_profile.py 量出的差异：

  维度        原厂 samsung_a00   我们（中位）    处理
  黑点        10.3               0–4            抬到 black
  白点        206                255            压到 white（B 通道更高，原厂 228）
  暗部饱和    0.48               0.62–0.75      乘 dark_sat 系数

暗部饱和高 40% 是"暗部发绿"的根：中性暗部不发绿（实测 G 比 max 低 3），
但暗部任何一点绿成分都被放大约一倍。

用法:
  python mk_align.py --src ../../looks/kodak_kchrome64.bin --out ../../looks_diag/zz_al.bin
  python mk_align.py --src ../../looks/x.bin --out y.bin --no-dark       # 只对电平
  python mk_align.py --src ../../looks/x.bin --out y.bin --no-level      # 只对暗部
"""
import argparse
import colorsys
import pathlib

TABLE = 19652
PAD = 60


def clamp8(x):
    return 0 if x < 0 else (255 if x > 255 else int(x + 0.5))


def align(raw, black, white_rg, white_b, dark_k, dark_v, do_level, do_dark, args_gamma=1.0):
    buf = bytearray(raw[:TABLE])

    # ① 暗部色度压制：HSV 域，v<dark_v 时把 s 乘系数（v=0 处最深，线性过渡到 1）
    if do_dark and dark_k < 1.0:
        for o in range(0, TABLE, 4):
            r, g, b = buf[o] / 255.0, buf[o + 1] / 255.0, buf[o + 2] / 255.0
            h, s, v = colorsys.rgb_to_hsv(r, g, b)
            if v >= dark_v or s < 1e-4:
                continue
            k = dark_k + (1.0 - dark_k) * (v / dark_v)      # v=0 → dark_k，v=dark_v → 1
            r2, g2, b2 = colorsys.hsv_to_rgb(h, s * k, v)
            buf[o] = clamp8(r2 * 255)
            buf[o + 1] = clamp8(g2 * 255)
            buf[o + 2] = clamp8(b2 * 255)

    # ② 电平：端点对齐 0→black、255→white
    #    --gamma 1.0 = 线性（整幅变暗，中灰 128→~102）
    #    --gamma <1  = 保中灰（f(0.5)=0.64 时中灰不动，代价是整体对比度降低）
    if do_level:
        wr = (white_rg, white_rg, white_b)
        g = args_gamma
        for ch in range(3):
            span = wr[ch] - black
            for o in range(ch, TABLE, 4):
                x = buf[o] / 255.0
                buf[o] = clamp8(black + span * (x ** g))

    return bytes(buf) + (raw[TABLE:TABLE + PAD] if len(raw) >= TABLE + PAD else b'\0' * PAD)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--black", type=float, default=9.0)
    ap.add_argument("--white-rg", type=float, default=195.0)
    ap.add_argument("--white-b", type=float, default=195.0,
                    help="B 通道白点。默认与 R/G 一致；原厂高光偏蓝靠 228 实现，但线性套到全段会让中灰偏蓝 18 级，不建议")
    ap.add_argument("--dark-k", type=float, default=0.80, help="暗部饱和系数（原厂 0.48/我们 0.60≈0.80）")
    ap.add_argument("--dark-v", type=float, default=0.30)
    ap.add_argument("--gamma", type=float, default=1.0,
                    help="电平曲线：1.0 线性（整幅变暗）；0.644 保中灰（对比度降低）")
    ap.add_argument("--no-level", action="store_true")
    ap.add_argument("--no-dark", action="store_true")
    args = ap.parse_args()

    raw = pathlib.Path(args.src).read_bytes()
    out = align(raw, args.black, args.white_rg, args.white_b,
                args.dark_k, args.dark_v, not args.no_level, not args.no_dark, args.gamma)
    pathlib.Path(args.out).write_bytes(out)

    # 前后对照
    def px(d, r, g, b):
        def i(v):
            return min(16, max(0, int(round(v * 16 / 255.0))))
        o = ((i(b) * 17 + i(g)) * 17 + i(r)) * 4
        return tuple(d[o:o + 3])

    print(f"{args.out}  ({len(out)}B)")
    print(f"\n{'点':<18} {'原':>16} {'新':>16}")
    for nm, (r, g, b) in {"黑(0,0,0)": (0, 0, 0), "白(255)": (255, 255, 255),
                          "中灰(128)": (128, 128, 128), "纯蓝(0,0,255)": (0, 0, 255),
                          "暗红(60,20,20)": (60, 20, 20), "暗绿(20,50,20)": (20, 50, 20),
                          "肤色(200,150,130)": (200, 150, 130)}.items():
        print(f"{nm:<18} {str(px(raw, r, g, b)):>16} {str(px(out, r, g, b)):>16}")


if __name__ == "__main__":
    main()
