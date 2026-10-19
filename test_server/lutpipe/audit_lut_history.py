#!/usr/bin/env python3
"""Read local release archives and historical LUT artifacts; no device access.

This audit establishes which bytes changed across v6/v7. It makes no claim
about historical or current camera appearance. --out writes only local JSON.
"""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

FILES = (
    "scripts/lut.sh", "scripts/lut/cube2lut.arm",
    "scripts/lut/nx_slotwrite.arm", "scripts/lut/nx_regtabwrite.arm",
    "scripts/filmlab.sh", "scripts/nxui/nxui.arm",
)
EXPECTED_ZIPS = {
    "v6": "1f8cb2c85d79127347c1c42d7d6510e3",
    "v7": "ca590b6e6db881c9446512cdbca0cf1a",
}


def digest(data):
    return {"bytes": len(data), "md5": hashlib.md5(data).hexdigest(),
            "sha256": hashlib.sha256(data).hexdigest()}


def zip_member(z, suffix):
    names = [n for n in z.namelist() if n == suffix or n.endswith("/" + suffix)]
    if len(names) != 1:
        raise ValueError(f"ambiguous or absent archive member: {suffix}: {names}")
    return z.read(names[0])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workspace", type=Path,
                    default=Path(__file__).resolve().parents[3])
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    workspace = args.workspace.resolve()
    repo = Path(__file__).resolve().parents[2]
    report = {
        "scope": "offline byte comparisons; no camera access or visual verdict",
        "releases": {}, "release_file_equalities": {}, "artifact_pairs": {},
    }
    release_bytes = {}
    for version, number in (("v6", 6), ("v7", 7)):
        path = repo / f"dist/NX-WA-2.88.0-nxwa.{number}.zip"
        info = digest(path.read_bytes())
        if info["md5"] != EXPECTED_ZIPS[version]:
            ap.error("archive differs from historical release: " + str(path))
        info["path"] = str(path)
        with zipfile.ZipFile(path) as z:
            if z.testzip() is not None:
                ap.error("archive CRC failure: " + str(path))
            release_bytes[version] = {f: zip_member(z, f) for f in FILES}
            info["files"] = {f: digest(data)
                             for f, data in release_bytes[version].items()}
            info["manifest_header"] = zip_member(
                z, "NX-WA-MANIFEST.txt").decode("utf-8").splitlines()[:6]
        report["releases"][version] = info
    for f in FILES:
        same = release_bytes["v6"][f] == release_bytes["v7"][f]
        report["release_file_equalities"][f] = same
        print("v6 == v7:", same, f)
    pairs = {
        "acros_18_vs_19": (
            workspace / ".tmp/add/bw_acros100.bin", workspace / "_probe_bw.bin"),
        "negative17_vs_rgb_invert_archive": (
            workspace / "fw/v1.12/c1-a17-negative/negative17_slot.bin",
            repo / "raw8/gates/lut/cube2lut_2026-10-18/invert17_arm.bin"),
    }
    for name, (left, right) in pairs.items():
        a, b = left.read_bytes(), right.read_bytes()
        report["artifact_pairs"][name] = {
            "left": {"path": str(left), **digest(a)},
            "right": {"path": str(right), **digest(b)}, "equal": a == b,
        }
        print(name + ":", a == b, hashlib.md5(a).hexdigest())
    negative = pairs["negative17_vs_rgb_invert_archive"][0].read_bytes()
    identity = (repo / "raw8/gates/lut/cube2lut_2026-10-18/identity17_arm.bin").read_bytes()
    image = (workspace / "fw/v1.12/a2/p7_a2.bin").read_bytes()
    if hashlib.md5(image).hexdigest() != "712c6fd0a49371ec05ce94c367b0d5c7":
        ap.error("image is not the verified A2 baseline")
    native_a17 = image[0x8AAFC0:0x8AFCC0]
    body = 4913 * 4
    report["negative_provenance"] = {
        "body_equals_rgb_identity_complement": all(
            negative[i] == (0 if i % 4 == 3 else 255 - identity[i])
            for i in range(body)),
        "body_equals_native_a17_complement": all(
            negative[i] == (0 if i % 4 == 3 else 255 - native_a17[i])
            for i in range(body)),
    }
    zero_call = b"pw_direct 100 100 100 0 0 0 0 --yes"
    report["neutral_zero_call_present"] = {
        ver: zero_call in files["scripts/filmlab.sh"]
        for ver, files in release_bytes.items()
    }
    print("Negative provenance:", report["negative_provenance"])
    print("PW neutral zero call:", report["neutral_zero_call_present"])
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
        print("Evidence:", args.out.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
