#!/usr/bin/env python3
"""Offline C1 verifier: explicit slot, expected image and complete readback.

No network, device access, partition writes or camera lifecycle changes.
Capture a readback separately with an authorized read-only acquisition tool.

Examples:
  c1_verify.py --readback p7.bin --expect a2
  c1_verify.py --readback p7.bin --slot A17 --expected-image p7_c1_a17.bin
  c1_verify.py --selftest --slot A17 --expected-image p7_c1_a17.bin
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

FW = Path("E:/NXWA/fw/v1.12")
A2_BIN = FW / "a2/p7_a2.bin"
C1_BIN = FW / "c1/p7_c1_a12.bin"
MD5_A2 = "712c6fd0a49371ec05ce94c367b0d5c7"
MD5_OFFICIAL = "5fc4824f5b6a6a3caca1f9104238b8ac"
SLOT_LEN = 0x4D00
B_OFF, BLK_OFF, BLK_LEN = 0x510B0, 0x11530, 80
REDIRECT = bytes.fromhex("1301ffea")


def md5b(data):
    return hashlib.md5(data).hexdigest()


def slot_offset(slot, image_size):
    if not re.fullmatch(r"[ABab][0-9]{1,2}", slot):
        raise ValueError("slot must be A00..A19 or B00..B21")
    block, index = slot[0].upper(), int(slot[1:])
    if index >= {"A": 20, "B": 22}[block]:
        raise ValueError("slot index is out of range")
    offset = {"A": 0x8592C0, "B": 0x8B9AC0}[block] + index * SLOT_LEN
    if offset + SLOT_LEN > image_size:
        raise ValueError("slot extends beyond the reference image")
    return offset


def validate_candidate(expected, base, slot):
    if len(expected) != len(base):
        raise ValueError("candidate and A2 reference lengths differ")
    offset = slot_offset(slot, len(base))
    if expected[:offset] != base[:offset] or expected[offset + SLOT_LEN:] != base[offset + SLOT_LEN:]:
        raise ValueError("candidate changes bytes outside the selected slot")
    if expected[offset:offset + SLOT_LEN] == base[offset:offset + SLOT_LEN]:
        raise ValueError("candidate does not change the selected slot")


def assess(cur, expected, base, slot, expect="c1"):
    offset = slot_offset(slot, len(base))
    if len(expected) != len(base):
        raise ValueError("reference image lengths differ")
    reference = base if expect == "a2" else expected
    complete = len(cur) >= len(reference)
    prefix = cur[:len(reference)]
    exact = complete and prefix == reference
    actual_slot = cur[offset:offset + SLOT_LEN]
    wanted_slot = reference[offset:offset + SLOT_LEN]
    slot_complete = len(actual_slot) == SLOT_LEN
    slot_ok = slot_complete and actual_slot == wanted_slot
    redirect_ok = cur[B_OFF:B_OFF + 4] == REDIRECT
    block_ok = (len(cur) >= BLK_OFF + BLK_LEN and
                cur[BLK_OFF:BLK_OFF + BLK_LEN] == base[BLK_OFF:BLK_OFF + BLK_LEN])
    matched = "truncated"
    if complete:
        if prefix == base:
            matched = "a2"
        elif prefix == expected:
            matched = "expected_candidate"
        elif md5b(prefix) == MD5_OFFICIAL:
            matched = "official_1.12"
        else:
            matched = "unknown"
    ok = (complete and matched in ("a2", "expected_candidate", "official_1.12")
          if expect == "any" else exact and redirect_ok and block_ok and slot_ok)
    return {"ok": bool(ok), "expect": expect, "matched": matched,
            "slot": f"{slot[0].upper()}{int(slot[1:]):02d}", "slot_file_offset": offset,
            "readback_bytes": len(cur), "evaluated_bytes": len(prefix),
            "required_image_bytes": len(reference), "complete": complete,
            "ignored_trailing_bytes": max(0, len(cur) - len(reference)),
            "readback_prefix_md5": md5b(prefix), "expected_prefix_md5": md5b(reference),
            "diff_vs_expected": (sum(a != b for a, b in zip(prefix, reference))
                                 if complete else None),
            "judge_A_image_prefix_exact": exact,
            "judge_B_redirect": redirect_ok, "judge_C_a2_block": block_ok,
            "judge_D_slot_expected": slot_ok, "slot_complete": slot_complete,
            "slot_md5": md5b(actual_slot) if slot_complete else None,
            "expected_slot_md5": md5b(wanted_slot),
            "hardware_consumption_verified": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--readback", type=Path, help="existing local readback; no new capture")
    mode.add_argument("--selftest", action="store_true")
    parser.add_argument("--slot", default="A12")
    parser.add_argument("--expected-image", "--image", type=Path)
    parser.add_argument("--table-file", type=Path)
    parser.add_argument("--base", type=Path, default=A2_BIN)
    parser.add_argument("--expect", choices=("c1", "a2", "any"), default="c1")
    parser.add_argument("--json", type=Path)
    args = parser.parse_args(argv)
    if args.selftest and args.json:
        parser.error("selftest must not write a readback evidence report")
    inputs = (args.readback, args.base, args.expected_image, args.table_file, C1_BIN)
    if args.json and args.json.resolve() in {p.resolve() for p in inputs if p is not None}:
        parser.error("JSON output must not overwrite a readback or reference input")
    base = args.base.read_bytes()
    if md5b(base) != MD5_A2:
        raise ValueError("A2 reference identity mismatch")
    offset = slot_offset(args.slot, len(base))
    image_path = args.expected_image
    if args.expect == "a2":
        if image_path is not None:
            parser.error("--expect a2 uses --base; omit --expected-image")
        expected = base
    else:
        if image_path is None:
            if args.slot.upper() != "A12":
                parser.error("non-A12 slot requires an explicit --expected-image")
            image_path = C1_BIN
        expected = image_path.read_bytes()
        validate_candidate(expected, base, args.slot)
    if args.table_file and args.table_file.read_bytes() != expected[offset:offset + SLOT_LEN]:
        raise ValueError("expected image slot does not match --table-file")
    if args.selftest:
        positive = assess(expected, expected, base, args.slot, args.expect)
        if not positive["ok"]:
            raise ValueError("selftest exact reference was rejected")
        if args.expect == "c1" and assess(base, expected, base, args.slot)["ok"]:
            raise ValueError("selftest incorrectly accepted unmodified A2")
        print("PASS: offline identity logic; no camera evidence produced")
        return 0
    report = assess(args.readback.read_bytes(), expected, base, args.slot, args.expect)
    report.update(source="offline_saved_readback", readback_path=str(args.readback.resolve()),
                  expected_image=str((image_path or args.base).resolve()))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"{'PASS' if report['ok'] else 'FAIL'}: {report['slot']}, matched={report['matched']}, "
          f"complete={report['complete']}, diff={report['diff_vs_expected']}")
    print("Firmware identity only; preview/JPEG consumption remains unverified.")
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        raise SystemExit(f"verification error: {error}")
