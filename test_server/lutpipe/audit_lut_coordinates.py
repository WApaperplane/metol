#!/usr/bin/env python3
"""Offline coordinate audit; never connects to or writes to a camera.

Compare the RGB-neutral diagonal with a C1/C2/Y-neutral axis in the verified
A2 image. C1/C2 names deliberately leave Cb/Cr ordering unresolved. Optional
camera snapshots must equal the corresponding image bytes. Generated probes
are hypotheses for a later controlled experiment, not a production converter.
"""
import argparse
import hashlib
import json
from pathlib import Path

SLOT_LEN = 0x4D00
TABLE_LEN = 17 ** 3 * 4
IMAGE_MD5 = "712c6fd0a49371ec05ce94c367b0d5c7"
SLOTS = {"a13": 0x897BC0, "a17": 0x8AAFC0, "a18": 0x8AFCC0}


def level(i):
    return min(i * 16, 255)


def entry(data, a, b, c):
    off = ((c * 17 + b) * 17 + a) * 4
    return list(data[off:off + 3])


def summarize(data):
    neutral = [entry(data, 8, 8, k) for k in range(17)]
    rgb_diag = [entry(data, k, k, k) for k in range(17)]
    return {
        "sha256": hashlib.sha256(data).hexdigest(),
        "c1c2y_neutral_axis": neutral,
        "c1c2y_neutral_matches": sum(
            got == [128, 128, level(k)] for k, got in enumerate(neutral)),
        "rgb_diagonal": rgb_diag,
        "rgb_neutral_matches": sum(
            got == [level(k)] * 3 for k, got in enumerate(rgb_diag)),
        "entry_padding_all_zero": all(data[i] == 0 for i in range(3, TABLE_LEN, 4)),
        "tail_matches_native_pattern": (
            data[TABLE_LEN:] == data[TABLE_LEN - 4:TABLE_LEN] * 3 + bytes(48)),
    }


def make_probe(constant_y=None):
    data = bytearray()
    for c in range(17):
        for _b in range(17):
            for _a in range(17):
                data.extend((128, 128, level(c) if constant_y is None else constant_y, 0))
    data.extend(data[-4:] * 3 + bytes(48))
    return bytes(data)


def illustrative_rgb(c1, c2, y):
    """BT.601-derived full-range example, NOT a measured camera matrix.

    Swapping Cb/Cr leaves these examples unchanged because c1 == c2.
    """
    cb, cr = c1 - 128, c2 - 128
    vals = (y + 1.402 * cr,
            y - 0.344136 * cb - 0.714136 * cr,
            y + 1.772 * cb)
    return [max(0, min(255, round(v))) for v in vals]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--image", type=Path, required=True)
    ap.add_argument("--a13-snapshot", type=Path)
    ap.add_argument("--a18-snapshot", type=Path)
    ap.add_argument("--out-dir", type=Path, help="Optional local JSON and probe output")
    args = ap.parse_args()
    image = args.image.read_bytes()
    image_md5 = hashlib.md5(image).hexdigest()
    if image_md5 != IMAGE_MD5:
        ap.error("image is not the verified A2 baseline: " + image_md5)
    report = {
        "image": str(args.image.resolve()), "image_md5": image_md5,
        "scope": "offline only; no camera state observed or modified",
        "interpretation": "C1/C2/Y is a candidate; Cb/Cr order and range are unverified",
        "slots": {}, "probes": {},
        "illustrative_bt601_full_range": {
            str(q): illustrative_rgb(q, q, q) for q in (0, 64, 128, 255)},
    }
    for name, off in SLOTS.items():
        data = image[off:off + SLOT_LEN]
        if len(data) != SLOT_LEN:
            ap.error("truncated slot: " + name)
        info = summarize(data)
        info["file_offset"] = hex(off)
        snapshot = getattr(args, name + "_snapshot", None)
        if snapshot:
            actual = snapshot.read_bytes()
            info["snapshot"] = str(snapshot.resolve())
            info["snapshot_sha256"] = hashlib.sha256(actual).hexdigest()
            info["snapshot_matches_image"] = actual == data
            if actual != data:
                ap.error("snapshot differs from image: " + str(snapshot))
        if not (info["c1c2y_neutral_matches"] == 17
                and info["entry_padding_all_zero"]
                and info["tail_matches_native_pattern"]):
            ap.error("native coordinate/padding premise failed: " + name)
        report["slots"][name] = info
        print(f"{name}: C1/C2/Y axis {info['c1c2y_neutral_matches']}/17; "
              f"RGB diagonal {info['rgb_neutral_matches']}/17; "
              f"snapshot={info.get('snapshot_matches_image', 'not supplied')}")
    if args.out_dir:
        args.out_dir.mkdir(parents=True, exist_ok=True)
        for name, data in (
                ("candidate_c1c2y_grayscale.bin", make_probe()),
                ("candidate_c1c2y_white.bin", make_probe(255))):
            (args.out_dir / name).write_bytes(data)
            report["probes"][name] = {
                "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                "status": "generated offline; not deployed or visually verified",
            }
        (args.out_dir / "audit.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("Local evidence:", args.out_dir.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
