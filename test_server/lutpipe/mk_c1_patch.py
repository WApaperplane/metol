#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mk_c1_patch.py — C1「一槽替换」p7 补丁/SLP 包生成器（T6 离线产物 · 2026-10-16）

设计依据：FILMLAB_LUT_NATIVE_UI_GOALS_2026-10-16 §4/§5（T6：离线产物保留 A2 既有改动；
         精确差异、原字节和 SLP 校验齐备）+ T4_TABLE_SOURCE_CONSUMPTION（消费链/登记表/负证据）

做什么：
  基线 = **A2 p7 镜像**（`p7_a2.bin`，含 A1+A2 全部改动）⇒ 天然「保留 A2 既有改动」；
  把镜像内**静态池的一个槽**（19712B = 19652B 表 + 60B 填充）替换为指定表（默认：数学恒等表）；
  生成：p7 镜像 + 精确差异清单 + 原字节快照 + （可选）SLP 包（容器基线 = A2 的 SLP 包，重算 JAMCRC + 版本升）。

★ 为什么用 identity 作 C1 测试表（默认）：画面变化明显（「移除风格处理」，U6 §3.2 判据）；
  离线可精确生成（4913/4913 严格恒等，本工具 `--make-identity` 自产）。

用法:
  # 1) 只做 p7 层（快）：默认槽 A12（0x80892EC0，「标准」——与运行时 0x810FD100 内容一致的槽）
  python mk_c1_patch.py --out E:/NXWA/fw/v1.12/c1 --write

  # 2) 连 SLP 包一起做（352MB 容器，内存 ~1.4GB）
  python mk_c1_patch.py --out E:/NXWA/fw/v1.12/c1 --write --slp --version 1.18

  # 3) 换槽 / 换表
  python mk_c1_patch.py --slot SB12 --table-file /path/slot.bin --out ... --write
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import struct
import sys

SLOT = 0x4D00
TABLE = 4913 * 4                      # 19652
PAD = SLOT - TABLE                    # 60
SLOT_BASE = {"A": 0x808592C0, "B": 0x808B9AC0}
COUNTS = {"A": 20, "B": 22}

A2_BASE_DEFAULT = r"E:/NXWA/fw/v1.12/a2/p7_a2.bin"
A2_SLP_DEFAULT = r"E:/NXWA/fw/v1.12/a2/slp_a2_p7_v117.bin"
P7_IDX = 5

# A2 特征（用于「保留 A2 既有改动」的自检；来自 A2_PATCH_DESIGN_2026-10-14 §1）
A2_FEATURES = [
    (0x510B0, bytes.fromhex("1301ffea"), "① 越界分支重定向 → 0x11504"),
    (0x4CD30, bytes.fromhex("fe11ffeb"), "③ 外部写包装改道 → A2 块 0x11530"),
]
A2_BLOCK_OFF = 0x11530               # ④ A2 块（应为非零）
# A2 四处改动点（A2_PATCH_DESIGN_2026-10-14 §1）；须与基线逐字节一致（= 保留 A2 改动）
A2_SITES = [0x510B0, 0x11504, 0x4CD30, 0x11530]


def level(i):
    return 255 if i == 16 else i * 16


def make_identity_slot():
    """生成严格 identity 表槽（19712B）：item(r,g,b) = (level(r),level(g),level(b),0)"""
    buf = bytearray(TABLE)
    for b in range(17):
        for g in range(17):
            for r in range(17):
                o = ((b * 17 + g) * 17 + r) * 4
                buf[o] = level(r)
                buf[o + 1] = level(g)
                buf[o + 2] = level(b)
                buf[o + 3] = 0
    # 填充：末项 ×3 + 48×0
    last = bytes(buf[4912 * 4:4912 * 4 + 4])
    buf += last * 3 + b"\x00" * 48
    assert len(buf) == SLOT
    return bytes(buf)


def diff_regions(a, b, limit=20):
    regions, total = [], 0
    n = min(len(a), len(b))
    i = 0
    while i < n:
        if a[i] != b[i]:
            j = i
            while j < n and a[j] != b[j]:
                j += 1
            total += j - i
            if len(regions) < limit:
                regions.append((i, j))
            i = j
        else:
            i += 1
    return regions, total


def main():
    ap = argparse.ArgumentParser(description="C1 一槽替换 p7/SLP 生成器（默认 dry-run）")
    ap.add_argument("--base", default=A2_BASE_DEFAULT, help="p7 基线（默认 A2 镜像）")
    ap.add_argument("--slot", default="A12", help="槽号：A00..A19 / B00..B21（默认 A12=0x80892EC0「标准」）")
    ap.add_argument("--table-file", default=None, help="现成槽文件（19712B）；缺省用内置 identity")
    ap.add_argument("--out", required=True, help="输出目录")
    ap.add_argument("--write", action="store_true", help="落盘（默认 dry-run）")
    ap.add_argument("--slp", action="store_true", help="同时构建 SLP 包（352MB 容器）")
    ap.add_argument("--slp-base", default=A2_SLP_DEFAULT)
    ap.add_argument("--version", default="1.18")
    a = ap.parse_args()

    fails = []

    def chk(ok, msg):
        print("[%s] %s" % ("OK  " if ok else "FAIL", msg))
        if not ok:
            fails.append(msg)
            raise ValueError(msg)  # Never write a candidate after a failed check.

    # ---- 0. 基线 ----
    with open(a.base, "rb") as source:
        base = source.read()
    print("p7 基线  : %s (%d B, md5 %s)" % (a.base, len(base), hashlib.md5(base).hexdigest()))
    chk(hashlib.md5(base).hexdigest() == "712c6fd0a49371ec05ce94c367b0d5c7",
        "基线 md5 == A2 镜像 712c6fd0…（保证含 A2 既有改动）")

    # ---- 1. 槽定位 ----
    chk(re.fullmatch(r"[ABab][0-9]{1,2}", a.slot) is not None, "槽号格式合法")
    blk, idx = a.slot[0].upper(), int(a.slot[1:])
    chk(blk in SLOT_BASE and 0 <= idx < COUNTS[blk], "槽号合法：%s" % a.slot)
    va = SLOT_BASE[blk] + idx * SLOT
    off = va - 0x80000000
    print("目标槽   : %s  VA %#010x  file_off %#x（长度 %d）" % (a.slot, va, off, SLOT))

    # ---- 2. 表 ----
    if a.table_file:
        with open(a.table_file, "rb") as source:
            tbl = source.read()
        chk(len(tbl) == SLOT, "表文件长度 == %d（实得 %d）" % (SLOT, len(tbl)))
        tbl_md5 = hashlib.md5(tbl).hexdigest()
    else:
        tbl = make_identity_slot()
        tbl_md5 = hashlib.md5(tbl).hexdigest()
        print("表        : 内置 identity（4913/4913 严格恒等）md5 %s" % tbl_md5)
    chk(not any(tbl[3:TABLE:4]), "4913 项 pad 字节全零")

    # ---- 3. 替换 + 原字节快照 ----
    snap = base[off:off + SLOT]
    assert len(snap) == SLOT
    new = bytearray(base)
    new[off:off + SLOT] = tbl
    new = bytes(new)
    print("原字节快照: %d B  md5 %s" % (len(snap), hashlib.md5(snap).hexdigest()))
    print("新 p7     : %d B  md5 %s" % (len(new), hashlib.md5(new).hexdigest()))

    # ---- 4. 自检：精确判据（槽外逐字节不变 + 槽内 == 目标表）+ A2 特征保留 ----
    head_same = base[:off] == new[:off]
    tail_same = base[off + SLOT:] == new[off + SLOT:]
    chk(head_same and tail_same,
        "目标槽之外逐字节不变（head %d B / tail %d B）" % (off, len(base) - off - SLOT))
    chk(new[off:off + SLOT] == tbl, "目标槽内容 == 目标表（md5 %s）" % tbl_md5)
    regions, total = diff_regions(base, new, limit=10 ** 9)
    inside = all(s >= off and e <= off + SLOT for s, e in regions)
    chk(inside, "全部差异均位于目标槽内（%d 处 / %d B）" % (len(regions), total))
    for s, e in regions[:5]:
        print("   差 %#x..%#x (%d B)" % (s, e, e - s))
    if len(regions) > 5:
        print("   …（共 %d 处）" % len(regions))
    for o, pat, desc in A2_FEATURES:
        chk(new[o:o + len(pat)] == pat, "A2 特征保留：%s" % desc)
    chk(any(new[A2_BLOCK_OFF:A2_BLOCK_OFF + 80]), "A2 块（0x11530）非零（保留）")
    for o in A2_SITES:
        chk(new[o:o + 16] == base[o:o + 16], "A2 改动点 %#x 与基线逐字节一致（保留）" % o)

    # ---- 5. 产物 ----
    os.makedirs(a.out, exist_ok=True)
    p7_out = os.path.join(a.out, "p7_c1_%s.bin" % a.slot.lower())
    snap_out = os.path.join(a.out, "%s.orig.bin" % a.slot.lower())
    js_out = os.path.join(a.out, "c1_bytepatch_%s.json" % a.slot.lower())
    spec = dict(
        tool="mk_c1_patch.py v1 · 2026-10-16",
        base=dict(path=a.base, md5=hashlib.md5(base).hexdigest(), size=len(base)),
        slot=dict(name=a.slot, va=hex(va), file_off=hex(off), size=SLOT),
        table=dict(kind=("identity" if not a.table_file else a.table_file), md5=tbl_md5),
        out=dict(path=p7_out, md5=hashlib.md5(new).hexdigest(), size=len(new)),
        diff=dict(regions_count=len(regions), total_bytes=total,
                  window=[hex(off), hex(off + SLOT)],
                  regions_head=[[hex(s), hex(e)] for s, e in regions[:20]],
                  note="全部差异均在 window 内；完整区间可由 mk_c1_patch.py 重算"),
        snapshot=dict(path=snap_out, md5=hashlib.md5(snap).hexdigest()),
        restore="Use the verified A2 SLP via the official update path; "
                "do not use this patched candidate as a rollback image. A2 baseline: %s" % a.base,
        note="C1 实验：静态池一槽替换；消费判定与回退见 T6_C1_SLOT_EXPERIMENT_2026-10-16.md",
    )

    if a.write:
        with open(p7_out, "wb") as f:
            f.write(new)
        with open(snap_out, "wb") as f:
            f.write(snap)
        with open(js_out, "w", encoding="utf-8") as f:
            json.dump(spec, f, ensure_ascii=False, indent=2)
        print("\n已落盘：\n  %s\n  %s\n  %s" % (p7_out, snap_out, js_out))
    else:
        print("\n(dry-run：未落盘；加 --write)")

    # ---- 6. SLP（可选）----
    if a.slp:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "slp"))
        import slp_tool  # noqa: E402
        print("\n---- SLP 打包 ----")
        meta, parts = slp_tool.parse(a.slp_base, verbose=False)
        print("容器     : %s（版本 %s，分区 %d）" % (a.slp_base, meta["version"], len(parts)))
        chk(parts[P7_IDX]["img_len"] == len(base),
            "容器 idx5 长度 == p7 基线（%d）" % parts[P7_IDX]["img_len"])
        newparts = [dict(p) for p in parts]
        newparts[P7_IDX] = dict(newparts[P7_IDX])
        newparts[P7_IDX]["data"] = new
        newmeta = dict(meta)
        newmeta["version"] = a.version
        slp_out = os.path.join(a.out, "slp_c1_%s_v%s.bin" % (a.slot.lower(), a.version.replace(".", "")))
        buf, warn = slp_tool.build(newmeta, newparts, slp_out, write=False)
        print("JAMCRC   : idx5 %08x → %08x" % (
            slp_tool.crc_jamcrc(base), slp_tool.crc_jamcrc(new)))
        print("容器     : %d B  md5 %s" % (len(buf), hashlib.md5(buf).hexdigest()))
        for w in warn:
            print("  [warn] %s" % w)
        if a.write:
            open(slp_out, "wb").write(buf)
            print("★ 已写 %s" % slp_out)
        else:
            print("(dry-run：未落盘)")

    print("\n== 结果：%s ==" % ("PASS（全部自检通过）" if not fails else "FAIL：%s" % fails))
    return 0 if not fails else 2


if __name__ == "__main__":
    sys.exit(main())
