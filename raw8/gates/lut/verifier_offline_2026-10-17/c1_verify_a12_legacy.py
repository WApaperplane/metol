#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""C1 一槽包（A12 槽 = identity）刷后验证 —— 只读。

与 a1_verify.py 的分工：a1_verify 的判据 2/3 是 A1/A2 专用点位，
拿它验 C1 会输出无意义的 FAIL。本工具专判 C1：

  判据 A  全集一致：/dev/mmcblk0p7 前 12,075,648 B == p7_c1_a12.bin
  判据 B  A2 重定向在位：0x510B0 == 13 01 ff ea
  判据 C  A2 分流块在位：0x11530 起 80 B == p7_a2.bin 同区
  判据 D  A12 槽已换：0x892EC0 起 19,712 B == identity（md5 235ad453…）

四个都不做假设：先落盘完整读回，再逐条判。判定结论只在读回后给出。

用法:
  python c1_verify.py 192.168.0.106                 # 上机
  python c1_verify.py --selftest                    # 离线自测（拿 C1 镜像冒充读回）
  python c1_verify.py 192.168.0.106 --expect a2     # 刷前基线确认
产出:
  raw8/gates/c1/<tag>_readback.bin + <tag>_readback.json
"""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

FW = Path("E:/NXWA/fw/v1.12")
C1_BIN = FW / "c1" / "p7_c1_a12.bin"
A2_BIN = FW / "a2" / "p7_a2.bin"

MD5_C1 = "b415ca76ab93ec44c9146cab59e27ba8"
MD5_A2 = "712c6fd0a49371ec05ce94c367b0d5c7"
MD5_OFFICIAL = "5fc4824f5b6a6a3caca1f9104238b8ac"
MD5_IDENT = "235ad45324c042d0bd4233513e1fca52"

SLOT_OFF = 0x892EC0
SLOT_LEN = 19712
B_OFF = 0x510B0
BLK_OFF = 0x11530
BLK_LEN = 80
REDIRECT = bytes.fromhex("1301ffea")
BYTES = 12075648

SD_DIR = "/opt/storage/sdcard"
REMOTE = SD_DIR + "/c1verify"
BB = "/opt/usr/nx-ks/busybox"


def md5b(b):
    return hashlib.md5(b).hexdigest()


def verdict_of(cur, ref_c1, ref_a2):
    h = md5b(cur[:BYTES])
    if h == MD5_C1:
        return "C1 在位（与包内镜像逐字节一致）", h
    if h == MD5_A2:
        return "仍是 A2 基线（未刷 / 刷入未生效）", h
    if h == MD5_OFFICIAL:
        return "官方 1.12（A2 与 C1 都不在）", h
    n = sum(1 for i in range(min(len(cur), BYTES)) if cur[i] != ref_c1[i])
    return "未知镜像（与 C1 差 %d 字节）" % n, h


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("host", nargs="?", default="selftest")
    ap.add_argument("--expect", choices=["c1", "a2", "any"], default="c1")
    ap.add_argument("--tag", default="post_flash")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    ref_c1 = C1_BIN.read_bytes()[:BYTES]
    ref_a2 = A2_BIN.read_bytes()[:BYTES]
    print("参照 C1   : %d B  md5 %s" % (len(ref_c1), md5b(ref_c1)))
    print("参照 A2   : %d B  md5 %s" % (len(ref_a2), md5b(ref_a2)))

    outdir = Path("raw8/gates/c1")
    outdir.mkdir(parents=True, exist_ok=True)
    local = outdir / ("%s_readback.bin" % args.tag)

    if args.selftest:
        print("== selftest：以 C1 镜像冒充读回，只验判定逻辑 ==")
        cur = ref_c1
        up = "selftest"
    else:
        sys.path.insert(0, "test_server/sysarch")
        from fwprobe import T
        from ftpx import ftp_get
        t = T(args.host, timeout=25)
        t.login()
        up = t.send("cat /proc/uptime", 4.0).strip()[:40]
        print("uptime    :", up)
        t.send("mkdir -p %s" % REMOTE, 3.0)
        t.send("rm -f %s/p7.bin" % REMOTE, 5.0)
        cnt = (BYTES + 4095) // 4096
        t.send("dd if=/dev/mmcblk0p7 of=%s/p7.bin bs=4096 count=%d 2>/dev/null" % (REMOTE, cnt), 60.0)
        print("remote md5:", t.send("%s md5sum %s/p7.bin 2>/dev/null | head -1" % (BB, REMOTE), 25.0).strip()[:90])
        t.close()
        print("FTP 拉回 ...")
        ok = False
        for a in range(3):
            if ftp_get(args.host, "/c1verify/p7.bin", str(local), timeout=900):
                ok = True
                break
            print("  重试", a + 1)
            time.sleep(3)
        if not ok:
            raise SystemExit("!! FTP 拉回失败，无法判定")
        cur = local.read_bytes()

    v, h = verdict_of(cur, ref_c1, ref_a2)
    n = min(len(cur), BYTES)
    diffs = sum(1 for i in range(n) if cur[i] != ref_c1[i])

    redir_ok = cur[B_OFF:B_OFF + 4] == REDIRECT
    blk_ok = cur[BLK_OFF:BLK_OFF + BLK_LEN] == ref_a2[BLK_OFF:BLK_OFF + BLK_LEN]
    slot = cur[SLOT_OFF:SLOT_OFF + SLOT_LEN]
    slot_md5 = md5b(slot)
    slot_is_ident = slot_md5 == MD5_IDENT
    slot_is_orig = slot == ref_a2[SLOT_OFF:SLOT_OFF + SLOT_LEN]

    print()
    print("---- 判据 ----")
    print("  读回 md5      : %s  (%d B)" % (h, len(cur)))
    print("  A 全集        : %s（与 C1 差 %d 处）" % ("PASS" if h == MD5_C1 else "FAIL", diffs))
    print("  B 0x510B0     : %s  %s" % (cur[B_OFF:B_OFF + 4].hex(), "PASS" if redir_ok else "FAIL"))
    print("  C 0x11530 块  : %s" % ("PASS" if blk_ok else "FAIL"))
    print("  D A12 槽      : %s  md5 %s（%s）"
          % ("PASS" if slot_is_ident else "FAIL", slot_md5,
             "identity" if slot_is_ident else ("A2 原样" if slot_is_orig else "未知内容")))
    print("  → %s" % v)

    if args.expect == "c1" and h != MD5_C1:
        print("  ⚠ 期望 C1 但读回不符 —— 不要继续做画面判定，先查刷机链")
    if args.expect == "a2" and h != MD5_A2:
        print("  ⚠ 期望 A2 基线但读回不符 —— 刷前状态不是已知基线，暂停改机")

    if not args.selftest:
        rec = dict(
            host=args.host, tag=args.tag, expect=args.expect, uptime=up,
            readback_md5=h, readback_bytes=len(cur),
            verdict=v, diff_vs_c1=diffs,
            judge_A_full=(h == MD5_C1),
            judge_B_redirect=redir_ok,
            judge_C_a2_block=blk_ok,
            judge_D_slot_identity=slot_is_ident,
            slot_md5=slot_md5,
        )
        jf = outdir / ("%s_readback.json" % args.tag)
        jf.write_text(json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8")
        print("  证据: %s" % jf)
    else:
        print("  (selftest 不落证据文件)")


if __name__ == "__main__":
    main()
