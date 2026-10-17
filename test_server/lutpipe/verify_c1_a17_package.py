#!/usr/bin/env python3
"""Offline validation of the A17 diagnostic; prepare a version-1.19 A2 rollback.

Never accesses the camera or writes a partition. Existing packages are checked,
not overwritten. The SLP version changes are deliberate; all payloads are checked.
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "test_server/slp"))
import slp_tool

FW = Path("E:/NXWA/fw/v1.12")
OUT = FW / "c1-a17-negative"
EVIDENCE = ROOT / "raw8/gates/lut/ondevice_selection_2026-10-17"


def hashes(path):
    data = path.read_bytes()
    return {"path": str(path.resolve()), "bytes": len(data),
            "md5": hashlib.md5(data).hexdigest(), "sha256": hashlib.sha256(data).hexdigest()}


def check_container(parts):
    assert len(parts) == 10
    for part in parts:
        assert slp_tool.crc_jamcrc(part["data"]) == part["crc32"], part["idx"]


def main():
    base = (FW / "a2/p7_a2.bin").read_bytes()
    candidate = (OUT / "p7_c1_a17.bin").read_bytes()
    readback = (EVIDENCE / "p7.bin").read_bytes()
    assert len(readback) == 2949 * 4096
    assert readback[:len(base)] == base
    assert hashlib.md5(base).hexdigest() == "712c6fd0a49371ec05ce94c367b0d5c7"
    offset, size = 0x8AAFC0, 0x4D00
    assert len(candidate) == len(base)
    assert candidate[:offset] == base[:offset]
    assert candidate[offset + size:] == base[offset + size:]
    assert (OUT / "a17.orig.bin").read_bytes() == base[offset:offset + size]
    negative = candidate[offset:offset + size]
    expected = bytearray()
    for b in range(17):
        for g in range(17):
            for r in range(17):
                expected.extend((255 - min(r * 16, 255), 255 - min(g * 16, 255),
                                 255 - min(b * 16, 255), 0))
    expected.extend(bytes(60))
    assert negative == expected
    base_path = FW / "a2/slp_a2_p7_v117.bin"
    candidate_path = OUT / "slp_c1_a17_v118.bin"
    official_path = Path("E:/tmp/NXWA-nx500_modding/.uploads/fw/nx500_v1.12.bin")
    bm, bp = slp_tool.parse(base_path, verbose=False)
    cm, cp = slp_tool.parse(candidate_path, verbose=False)
    om, op = slp_tool.parse(official_path, verbose=False)
    for parts in (bp, cp, op):
        check_container(parts)
    assert bm["version"] == "1.17" and cm["version"] == "1.18"
    assert bm["project"] == cm["project"] == om["project"] == "NX500"
    assert bm["version_date"] == cm["version_date"] == om["version_date"]
    assert bp[5]["data"] == base and cp[5]["data"] == candidate
    for i in range(10):
        if i != 5:
            assert cp[i]["data"] == bp[i]["data"] == op[i]["data"], i
        assert cp[i]["img_offset"] == bp[i]["img_offset"]
        assert cp[i]["img_len"] == bp[i]["img_len"]
    rollback_path = OUT / "slp_a2_restore_v119.bin"
    rm = dict(bm)
    rm["version"] = "1.19"
    rollback, warnings = slp_tool.build(rm, bp, rollback_path, write=False)
    assert not warnings, warnings
    original_slp = base_path.read_bytes()
    assert rollback[:4] == original_slp[:4] and rollback[12:] == original_slp[12:]
    if rollback_path.exists():
        assert rollback_path.read_bytes() == rollback
    else:
        rollback_path.write_bytes(rollback)
    rm2, rp = slp_tool.parse(rollback_path, verbose=False)
    assert rm2["version"] == "1.19"
    check_container(rp)
    assert all(a["data"] == b["data"] for a, b in zip(rp, bp))
    report = {"status": "offline_payload_checks_passed; not hardware acceptance",
              "on_camera_p7_a2_exact_match": True,
              "slot": "A17", "file_offset": offset, "runtime": 0x81115200,
              "changed_bytes": sum(a != b for a, b in zip(base, candidate)),
              "slot_outside_unchanged": True,
              "negative_table_md5": hashlib.md5(negative).hexdigest(),
              "candidate_only_partition_5_changed": True,
              "candidate_crcs_all_passed": True,
              "candidate_other_partitions_match_official": True,
              "rollback_only_version_header_changed": True,
              "rollback_hardware_acceptance_verified": False,
              "packages": [hashes(p) for p in (candidate_path, rollback_path, base_path, official_path)],
              "p7": hashes(OUT / "p7_c1_a17.bin")}
    output = ROOT / "test_server/lutpipe/logs/c1_a17_negative_package_2026-10-17.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("PASS: current A2 identity; A17-only change; all SLP CRCs; other nine payloads official")
    print("PASS: A2 rollback 1.19 payloads identical to A2 1.17; version header only")
    for package in report["packages"][:2]:
        print(Path(package["path"]).name, package["bytes"], package["md5"])


if __name__ == "__main__":
    main()
