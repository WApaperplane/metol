#!/usr/bin/env python3
"""双 LUT 强度：验证「不写新引擎也能做」的那条路。

结论先行：把两个强度换成 (比例 r, 总强度 s) 之后，

    T = A17 + min(s,1) · [ mix(A, B, r) − A17 ]

正好等于「先 mix 再 strength」。两次 `lutmix` 调用就能算完，一个新二进制都不用
写，两个动词也都已经在 `lut.sh` 里。

本脚本在 qemu 下真跑两次 lutmix，逐字节对齐 Python 参考：

  1. M3 路径（mix → strength）与两步参考全等
  2. M2 路径（blend → blend）与两步参考全等
  3. α+β ≤ 1 时 M3 与 M1（偏移叠加）数学等价，差异 ≤ 1 级
  4. 边界：s=0 回到原厂表、s=1000 等于纯 mix 结果

Run (WSL): python3 test_dual_strength.py
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
BIN = HERE / "build" / "lutmix.arm"
STOCK = HERE / "build" / "_stock_A17.bin"
QEMU = shutil.which("qemu-arm-static") or shutil.which("qemu-arm")

TABLE_LEN = 19652
SLOT_LEN = 19712


def load(path):
    raw = Path(path).read_bytes()
    return raw[:TABLE_LEN] if len(raw) == SLOT_LEN else raw


def blend(a, b, permille):
    return bytes((a[i] * (1000 - permille) + b[i] * permille + 500) // 1000
                 for i in range(TABLE_LEN))


def fix_tail(t):
    t = bytearray(t)
    if len(t) < SLOT_LEN:
        t.extend(b"\0" * (SLOT_LEN - len(t)))
    for i in range(12):
        t[TABLE_LEN + i] = t[TABLE_LEN - 4 + (i & 3)]
    for i in range(TABLE_LEN + 12, SLOT_LEN):
        t[i] = 0
    return bytes(t)


def qemu(*args):
    return subprocess.run([QEMU, str(BIN)] + [str(a) for a in args], capture_output=True)


def main():
    if not BIN.exists():
        print("SKIP lutmix.arm not built")
        return 0
    if not QEMU:
        print("SKIP no qemu-arm")
        return 0
    if not STOCK.exists():
        print("SKIP build/_stock_A17.bin 缺失（从相机 /mnt/mmc/looks/ 取回）")
        return 0

    base = load(STOCK)
    lib = REPO / "looks"
    picks = [p for p in sorted(lib.glob("*.bin")) if p.stat().st_size == SLOT_LEN][:2]
    if len(picks) < 2:
        print("SKIP need two shipped .bin tables")
        return 0
    a, b = load(picks[0]), load(picks[1])
    tmp = Path(tempfile.mkdtemp(prefix="dualstr-"))
    failures = []

    # 把原厂表写成 19,712 的槽镜像，好让 lutmix 直接吃
    base_slot = tmp / "base.bin"
    base_slot.write_bytes(fix_tail(bytes(base[:TABLE_LEN])))

    def run_mix(src_a, src_b, permille, out):
        r = qemu(src_a, src_b, permille, out)
        if r.returncode != 0:
            failures.append("mix %s %s %d: %s"
                            % (src_a.name, src_b.name, permille,
                               r.stdout.decode(errors="replace")))
            return None
        return out.read_bytes()[:TABLE_LEN]

    # ── 1/2. 两条路径都等于「两步参考」 ──
    grid = [(250, 250), (500, 500), (750, 250), (250, 750), (1000, 500), (500, 1000)]
    for wa, wb in grid:
        s = wa + wb
        r_p = int(round(wb * 1000.0 / s))
        s_p = min(s, 1000)

        # M3: mix(A,B,r) 再 strength(base, ·, s)
        mid = tmp / "mid.bin"
        got_mid = run_mix(picks[0], picks[1], r_p, mid)
        if got_mid is None:
            continue
        if got_mid != blend(a, b, r_p):
            failures.append("M3 step1 r=%d 与参考不符" % r_p)
        out3 = tmp / "out3.bin"
        got3 = run_mix(base_slot, mid, s_p, out3)
        if got3 is None:
            continue
        want3 = blend(blend(a, b, r_p), base, 1000 - s_p)  # 从 mid 向 base 回走，等价 base + s·(mid−base)
        if got3 != want3:
            failures.append("M3 step2 s=%d 与参考不符" % s_p)

        # 与「理想单步」比较：T = base + s/1000 * (mid - base)
        ideal = bytes(max(0, min(255, base[i] + int(round((blend(a, b, r_p)[i] - base[i]) * s_p / 1000.0))))
                      for i in range(TABLE_LEN))
        drift = max(abs(got3[i] - ideal[i]) for i in range(TABLE_LEN))
        if drift > 1:
            failures.append("M3 两步取整漂移 %d 级 (wa=%d wb=%d)" % (drift, wa, wb))

        # ── 3. α+β ≤ 1000 时与 M1 等价 ──
        if s <= 1000:
            m1 = bytes(max(0, min(255, int(round(base[i]
                                  + (a[i] - base[i]) * wa / 1000.0
                                  + (b[i] - base[i]) * wb / 1000.0))))
                       for i in range(TABLE_LEN))
            d1 = max(abs(got3[i] - m1[i]) for i in range(TABLE_LEN))
            if d1 > 1:
                failures.append("α+β≤1 时 M3 与 M1 差了 %d 级 (wa=%d wb=%d)" % (d1, wa, wb))

    # ── 4. 边界：s=0 必须逐字节回到原厂表，s=1000 必须等于纯 mix 结果 ──
    mid = tmp / "b_mid.bin"
    if run_mix(picks[0], picks[1], 500, mid) is not None:
        out = tmp / "b_out.bin"
        got = run_mix(base_slot, mid, 0, out)
        if got is not None and got != bytes(base[:TABLE_LEN]):
            failures.append("s=0 没有回到原厂表")
        got = run_mix(base_slot, mid, 1000, out)
        if got is not None and got != bytes(blend(a, b, 500)):
            failures.append("s=1000 不等于纯 mix 结果")

    if failures:
        for f in failures:
            print("FAIL", f)
        print("%d FAIL" % len(failures))
        return 1
    print("PASS dual strength: mix→strength 两次调用 == 两步参考，M3/M1 在 α+β≤1 时等价")
    return 0


if __name__ == "__main__":
    sys.exit(main())
