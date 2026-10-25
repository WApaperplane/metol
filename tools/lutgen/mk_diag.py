#!/usr/bin/env python3
"""mk_diag.py —— 生成机上解表诊断表（唯一需要上机的一步）

背景：本地表在冷色域 dHue 全在 ±7° 内（cool_probe.py 已证），槽内字节与
本地文件 md5 完全一致（cool_blue = e9ac2955…），但实机冷色偏品红/紫。
⇒ 引擎对表的「解释方式」与生成假设不一致。

本脚本造几张判读无歧义的探针表。判读方法见 --help 输出。

用法:
  python mk_diag.py --out ../looks_diag          # 生成全套到指定目录

★ 生成后用 lut.sh apply 套上，拍同一个场景看画面。
"""
import argparse
import pathlib

N = 17
GRID = [i * 16 for i in range(16)] + [255]


def luma(r, g, b):
    return 0.299 * r + 0.587 * g + 0.114 * b


def build(fn):
    buf = bytearray()
    for bi in range(N):
        for gi in range(N):
            for ri in range(N):
                out = fn(GRID[ri], GRID[gi], GRID[bi])
                buf += bytes((max(0, min(255, int(round(out[0])))),
                              max(0, min(255, int(round(out[1])))),
                              max(0, min(255, int(round(out[2])))), 0))
    buf += b'\0' * 60
    assert len(buf) == 19712, len(buf)
    return bytes(buf)


# ---- 1) 三色条：按亮度分段输出纯 R / G / B -------------------------------
def stripes(r, g, b):
    l = luma(r, g, b)
    if l < 85:
        return (255, 0, 0)
    if l < 170:
        return (0, 255, 0)
    return (0, 0, 255)


# ---- 2) 单轴探针：输出只跟输入的一个通道有关，用来查轴序 -------------------
def axis_r(r, g, b):
    return (r, 0, 0)


def axis_g(r, g, b):
    return (0, g, 0)


def axis_b(r, g, b):
    return (0, 0, b)


# ---- 3) 冷色极限：把偏蓝的输入推到饱和深蓝，看能不能出蓝 -------------------
def cool_pure(r, g, b):
    """输入蓝>红 且 蓝>绿 ⇒ 强制输出饱和蓝；其余保持原样。
    如果上机后"蓝区"仍然发品红，说明引擎在 B 通道上有硬限制或轴序不对。"""
    if b > r and b > g:
        return (20, 80, 235)
    return (r, g, b)


# ---- 4) 恒等但 B 减半：查 B 通道是否被正确读入 -----------------------------
def b_half(r, g, b):
    return (r, g, b * 0.5)


TABLES = {
    "zz_diag_stripes": (stripes, "按亮度输出 纯红(<85) / 纯绿(85-170) / 纯蓝(>170)"),
    "zz_diag_axis_r": (axis_r, "输出只取输入 R 通道，画面应呈红色明暗（错误轴序会变灰/绿/蓝）"),
    "zz_diag_axis_g": (axis_g, "输出只取输入 G 通道，画面应呈绿色明暗"),
    "zz_diag_axis_b": (axis_b, "输出只取输入 B 通道，画面应呈蓝色明暗"),
    "zz_diag_cool": (cool_pure, "偏蓝输入强制成饱和深蓝，验证蓝冷色能否产生"),
    "zz_diag_bhalf": (b_half, "恒等但 B 减半，整幅应明显偏黄（若不偏黄则 B 通道未被读入）"),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="../looks_diag")
    args = ap.parse_args()
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, (fn, desc) in TABLES.items():
        p = out / f"{name}.bin"
        p.write_bytes(build(fn))
        print(f"{p}  {p.stat().st_size}B   {desc}")
    print(f"\n共 {len(TABLES)} 张，全部 19712B（4913×4 + 60 pad），可直接 lut.sh apply")


if __name__ == "__main__":
    main()
