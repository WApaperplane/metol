#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_manifest.py —— 生成随包的定档清单 looks/MANIFEST.txt。

用途：
  * 把"这一版发的是哪 68 张、每张的 md5/size"钉死，供 `lut.sh verify` 对照；
  * 加/删/改任何一张表后必须重跑本脚本，否则 verify 会报 CHANGED —— 这是有意的：
    库的变更必须是显式动作，而不是某次拷贝顺手带进去的。

用法：
  python tools/lutgen/make_manifest.py            # 写入 looks/MANIFEST.txt
  python tools/lutgen/make_manifest.py --check    # 只比对，不写
"""
import hashlib
import pathlib
import sys
from datetime import date

REPO = pathlib.Path(__file__).resolve().parents[2]
LOOKS = REPO / "looks"
OUT = LOOKS / "MANIFEST.txt"


def md5(path: pathlib.Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def rows():
    out = []
    for p in sorted(LOOKS.glob("*.bin")):
        out.append((p.name, p.stat().st_size, md5(p)))
    return out


def render(items):
    head = [
        "# NX-WA look library — 定档清单 / frozen manifest",
        "# 生成: %s    条目: %d" % (date.today().isoformat(), len(items)),
        "# 格式: <md5>  <size>  <name>     校验: sh /opt/usr/nx-ks/lut.sh verify",
        "# 改库流程: 加/删/改 looks/*.bin -> python tools/lutgen/make_manifest.py -> 提交",
    ]
    body = ["%s  %8d  %s" % (h, s, n) for n, s, h in items]
    return "\n".join(head + body) + "\n"


def main():
    items = rows()
    text = render(items)
    if "--check" in sys.argv:
        if not OUT.exists():
            print("MISSING manifest")
            return 1
        same = OUT.read_text(encoding="utf-8") == text
        print("manifest:", "OK" if same else "DIFFERS", "| entries", len(items))
        return 0 if same else 2
    # 必须写 LF：相机 busybox 的 read 不会吃掉行尾 \r，
    # 一旦写成 CRLF，verify/prune 会把每个名字都当成不存在（2026-11-11 踩过）。
    OUT.write_bytes(text.encode("utf-8"))
    print("wrote %s (%d entries)" % (OUT, len(items)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
