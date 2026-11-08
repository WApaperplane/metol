#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""web_regen.py —— 按实测相机曲线重新生成 G'MIC 胶片表（不是重采样旧 bin）。

与 web_import.py 的区别只有一步：在 64³ RGB 域先把输入轴按实测 h 重映射，
再交给 native_codec 转 17³ CrCbY。三个通道一起映射，因此不会出现
「只改亮度、色度仍按 sRGB」的不匹配。

h（相机码值 → sRGB 输入域）来自 2026-11-08 的实测：
- 中段斜率 log2(码值)/EV = 0.809（DR 15 点扫描）
- 肩部 6 档 ISO 扫描：EV+2 起压缩，+3.3 处 237，软肩无硬 clip
- 绝对锚点用中灰（v=128 ↔ sRGB 128），未用灰卡验证

用法:
  python web_regen.py --only kodak_2383 fuji_velvia50
  python web_regen.py --all
"""
import argparse
import pathlib
import sys

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from web_import import CACHE, MANIFEST, decode, to_slot  # noqa: E402

H17 = [2, 34, 55, 71, 85, 97, 107, 117, 128, 142, 157, 174, 190, 205, 222, 240, 255]
XS = [i * 16 if i < 16 else 255 for i in range(17)]
_codes = np.arange(64) * 255.0 / 63
_mapped = np.interp(_codes, np.array(XS, float), np.array(H17, float))
H64 = np.round(_mapped / 255.0 * 63).astype(np.int32)


def regen(name: str) -> bytes:
    cat, preset, _mode, _label = MANIFEST[name]
    png = CACHE / f"{cat}__{preset}.png"
    if not png.is_file():
        raise FileNotFoundError(png)
    cube = decode(png)
    return to_slot(cube[np.ix_(H64, H64, H64)])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--out", default=str(HERE / "webstage_regen"))
    a = ap.parse_args()
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    names = list(MANIFEST) if a.all else (a.only or [])
    if not names:
        raise SystemExit("需要 --only <name...> 或 --all")
    ok = 0
    for n in names:
        try:
            b = regen(n)
        except KeyError:
            print(f"SKIP {n}: 不在 MANIFEST")
            continue
        except FileNotFoundError as e:
            print(f"SKIP {n}: 缓存缺失 {e}")
            continue
        (out / f"{n}.bin").write_bytes(b)
        print(f"{n:<24} {len(b)} bytes")
        ok += 1
    print(f"完成 {ok}/{len(names)} -> {out}")


if __name__ == "__main__":
    main()
