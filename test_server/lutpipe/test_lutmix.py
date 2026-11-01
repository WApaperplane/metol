#!/usr/bin/env python3
"""Guard lutmix.arm: the on-camera crossfade must equal the arithmetic reference.

The ARM binary is static and self-contained, so it can actually be executed
here under qemu-arm-static -- this is a real run, not a fixture comparison.

Checks:
  1. --identity reproduces the hardware grid {0,16,...,240,255} on all axes
  2. s=0 / s=1000 return the endpoints bit-exact (no rounding drift)
  3. s=500 matches round((a+b)/2) on every one of the 19,652 table bytes
  4. the 60-byte tail is last-entry x3 + zeros
  5. bad input (short file, permille > 1000) is refused, not guessed

Run (WSL): python3 test_lutmix.py
"""
import os
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
BIN = HERE / "build" / "lutmix.arm"
QEMU = shutil.which("qemu-arm-static") or shutil.which("qemu-arm")

TABLE_LEN = 19652
SLOT_LEN = 19712
TAIL_LEN = SLOT_LEN - TABLE_LEN
N = 17
LEVEL = [(i * 16 if i < N - 1 else 255) for i in range(N)]


def identity_bytes():
    out = bytearray(SLOT_LEN)
    for y in range(N):
        for cb in range(N):
            for cr in range(N):
                o = ((y * N + cb) * N + cr) * 4
                out[o + 0] = LEVEL[cr]
                out[o + 1] = LEVEL[cb]
                out[o + 2] = LEVEL[y]
                out[o + 3] = 0
    return fix_tail(out)


def fix_tail(t):
    for i in range(12):
        t[TABLE_LEN + i] = t[TABLE_LEN - 4 + (i & 3)]
    for i in range(TABLE_LEN + 12, SLOT_LEN):
        t[i] = 0
    return bytes(t)


def blend(a, b, permille):
    out = bytearray(SLOT_LEN)
    for i in range(TABLE_LEN):
        out[i] = (a[i] * (1000 - permille) + b[i] * permille + 500) // 1000
    return fix_tail(out)


def run(*args):
    return subprocess.run([QEMU, str(BIN)] + [str(a) for a in args],
                          capture_output=True)


def main():
    if not BIN.exists():
        print("SKIP lutmix.arm not built")
        return 0
    if not QEMU:
        print("SKIP no qemu-arm")
        return 0
    failures = []
    tmp = Path(tempfile.mkdtemp(prefix="lutmix-"))

    # 1. identity
    target = tmp / "identity.bin"
    r = run("--identity", target)
    if r.returncode != 0:
        failures.append("identity run failed: %s" % r.stdout.decode(errors="replace"))
    else:
        got = target.read_bytes()
        if got != identity_bytes():
            failures.append("identity mismatch")
        if b"=== done ===" not in r.stdout:
            failures.append("identity: no done marker")

    # pick two real tables from the shipped library
    lib = REPO / "looks"
    picks = [p for p in sorted(lib.glob("*.bin")) if p.stat().st_size == SLOT_LEN][:2]
    if len(picks) < 2:
        print("SKIP need two shipped .bin tables")
        return 0
    a_raw, b_raw = picks[0].read_bytes(), picks[1].read_bytes()
    a, b = a_raw[:TABLE_LEN], b_raw[:TABLE_LEN]

    for permille in (0, 137, 500, 863, 1000):
        out = tmp / ("mix%d.bin" % permille)
        r = run(picks[0], picks[1], permille, out)
        if r.returncode != 0:
            failures.append("mix %d failed: %s" % (permille, r.stdout.decode(errors="replace")))
            continue
        got = out.read_bytes()
        if len(got) != SLOT_LEN:
            failures.append("mix %d length %d" % (permille, len(got)))
            continue
        want = blend(a, b, permille)
        if got != want:
            diff = [i for i in range(SLOT_LEN) if got[i] != want[i]]
            failures.append("mix %d differs at %d bytes, first %d: %d != %d"
                            % (permille, len(diff), diff[0], got[diff[0]], want[diff[0]]))
        if got[TABLE_LEN:] != want[TABLE_LEN:]:
            failures.append("mix %d tail" % permille)

    # endpoints must be bit-exact copies
    for permille, src in ((0, a_raw), (1000, b_raw)):
        out = tmp / ("end%d.bin" % permille)
        run(picks[0], picks[1], permille, out)
        if out.read_bytes()[:TABLE_LEN] != src[:TABLE_LEN]:
            failures.append("endpoint %d is not a bit-exact copy" % permille)

    # 2. refusals
    short = tmp / "short.bin"
    short.write_bytes(b"\x00" * 100)
    r = run(short, picks[1], 500, tmp / "x.bin")
    if r.returncode == 0:
        failures.append("100-byte input was accepted")
    r = run(picks[0], picks[1], 1001, tmp / "x.bin")
    if r.returncode == 0:
        failures.append("permille 1001 was accepted")
    r = run()
    if r.returncode == 0:
        failures.append("no-argument run succeeded")

    shutil.rmtree(tmp, ignore_errors=True)
    if failures:
        print("FAIL")
        for f in failures:
            print("  -", f)
        return 1
    print("PASS lutmix: identity + 5 blends + endpoints + 3 refusals")
    return 0


if __name__ == "__main__":
    sys.exit(main())
