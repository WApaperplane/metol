"""Read-only NX500 AF survey. Never imports a camera control/network module.

Run with a Python environment containing pyelftools and capstone:
  E:/nxks2-re/Scripts/python.exe analyze.py --workspace E:/NXWA
The SLP chunk is read from the official package, not a patched p7 image.
Existing Ghidra function boundaries are used as navigation hints only.
"""
from __future__ import annotations

import argparse
import bisect
import hashlib
import json
from pathlib import Path
import re
import struct
import zlib

from elftools.elf.elffile import ELFFile


GROUPS = {
    "face": r"CFace|CFDTask|FaceDetection|FaceRecognition|FaceIF|main.?face|HoldFace|tracking_mode|FD_CPU|face.*(?:width|height|count)|Wink|Smile|eye|pupil|FD (?:AREA|DETECTED|LOST|is not working)|UPDATE FD|SKIP AF AREA|AF LOCKED",
    "tracking": r"ObjectTrack|ObjectInterface|COBJTask|LoseObject|TrackingOK|Segment_[ABC]|OBJ Tracking|OBJTask|ObjectTouch|ObjectCenter|Tracking Control Parameters|af multi algo tracking|small object chatter|FD is not working",
    "af": r"AF_PAF|CAFProcess|CAFSequence|AF_MOVIE|AF.*(?:Predict|Sensitivity|Speed|Face|Paf|PAF)|Paf.*(?:Rel|Mode)|PAF.*(?:REL|CONF|Predict)|[Ss]ensitivity|[Ww]obbl|[Hh]yster|[Pp]redict|CheckFdMultiArea|FocusBackLash|FocusingSpeed",
    "control": r"eIQ_ID_AF|eFOCUS_|eAF_MOVIE|E_CAP_CMD.*(?:AF|FACE|TRACK|FOCUS)|CAPTURE_COMMAND.*(?:AF|FACE|TRACK|FOCUS)|USERDATA_FACEDETECT|AFAREA_|AFMODE_|st cap (?:iq af|face|obj)|AF_RELEASE|AF_PRIORITY|MOV_AF_",
    "source": r"(?:AF/|Face/|ObjectTracking/).*(?:cpp|\.c)$",
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def elf_inventory(path):
    with path.open("rb") as f:
        elf = ELFFile(f)
        syms = {}
        sections = []
        for sec in elf.iter_sections():
            sections.append({"name": sec.name, "address": sec["sh_addr"], "offset": sec["sh_offset"], "size": sec["sh_size"]})
            if sec.name not in (".dynsym", ".symtab"):
                continue
            for sym in sec.iter_symbols():
                name = sym.name
                if re.search(r"(?:track|face|focus|af_|_af|afmode|afarea|afspeed|paf)", name, re.I) and not re.search(r"IMAGE_|osd_|elm_|evas_|efreet_|eet_|ecore_|SmartPanel|list_focus|grid.*focus|disk.*focus", name):
                    syms[name] = {"address": sym["st_value"], "size": sym["st_size"], "section": sym["st_shndx"], "type": sym["st_info"]["type"]}
        dynamic = elf.get_section_by_name(".dynamic")
        needed = [t.needed for t in dynamic.iter_tags() if t.entry.d_tag == "DT_NEEDED"] if dynamic else []
    return {"path": str(path), "sha256": digest(path.read_bytes()), "sections": sections, "needed": needed, "symbols": syms}


def load_boundaries(path):
    funcs = []
    if path.exists():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            cols = line.split("\t")
            if len(cols) >= 3 and cols[0].startswith("0x"):
                funcs.append((int(cols[0], 16), int(cols[1]), cols[2]))
    return sorted(funcs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", type=Path, default=Path("E:/NXWA"))
    ap.add_argument("--ghidra", type=Path, default=Path("E:/ghidra_out"))
    args = ap.parse_args()
    root = args.workspace
    out = Path(__file__).resolve().parent / "out"
    out.mkdir(exist_ok=True)
    firmware = root / "fw/v1.12/NX500_v1.12.bin"
    with firmware.open("rb") as f:
        metadata = struct.unpack("<4s8s16s16sbI15s", f.read(64))
        assert metadata[0] == b"SLP\0" and metadata[4] == 10
        parts = [struct.unpack("<IIII8s", f.read(24)) for _ in range(metadata[4])]
        length, header_crc, offset, magic, extra = parts[5]
        f.seek(offset)
        image = f.read(length)
    assert len(image) == length
    funcs = load_boundaries(args.ghidra / "52_pseudocode_index.txt")
    starts = [x[0] for x in funcs]

    def owner(addr):
        i = bisect.bisect_right(starts, addr) - 1
        if i >= 0 and addr < funcs[i][0] + funcs[i][1]:
            return {"address": hex(funcs[i][0]), "size": funcs[i][1], "name": funcs[i][2], "boundary_source": "historical Ghidra index; navigation hint"}
        return None

    strings = []
    by_value = {}
    for m in re.finditer(rb"[\x20-\x7e\t\r\n]{5,}", image):
        s = m.group().decode("ascii")
        groups = [g for g, pattern in GROUPS.items() if re.search(pattern, s, re.I)]
        if not groups:
            continue
        record = {"offset": hex(m.start()), "groups": groups, "text": s, "literal_loads": [], "pointer_slots": []}
        strings.append(record)
        by_value[m.start()] = record
        by_value[0x80000000 + m.start()] = record

    # Data words can be pointer slots. They are not automatically code xrefs.
    for off in range(0, len(image) - 3, 4):
        word = struct.unpack_from("<I", image, off)[0]
        if word in by_value:
            by_value[word]["pointer_slots"].append(hex(off))

    # A32 PC-relative LDR immediate with Rn=PC, I=0, P=1, W=0, L=1.
    # Scan only the historical code region; disassemble each chosen hit later.
    for off in range(0, min(len(image), 0x570000) - 3, 4):
        word = struct.unpack_from("<I", image, off)[0]
        if (word & 0x0F7F0000) != 0x051F0000 or word >> 28 == 15:
            continue
        imm = word & 0xFFF
        pool = off + 8 + (imm if word & 0x00800000 else -imm)
        if pool < 0 or pool + 4 > len(image):
            continue
        value = struct.unpack_from("<I", image, pool)[0]
        if value in by_value:
            by_value[value]["literal_loads"].append({"instruction": hex(off), "pool": hex(pool), "value": hex(value), "owner_hint": owner(off)})

    artifacts = {}
    for label, rel in {
        "app": "fw/v1.12/extract/di-camera-app/com.samsung.di-camera-app/bin/di-camera-app",
        "shell": "fw/v1.12/extract/usr-lib/libshell-command.so",
        "bridge": "fw/v1.12/extract/usr-lib/libmulticore-bridge.so",
        "udd5": "fw/v1.12/extract/usr-lib-d5/libudd5.so",
        "mcbtest": "fw/v1.12/extract/usr-bin/mcbtest",
    }.items():
        artifacts[label] = elf_inventory(root / rel)
    manifest = {"firmware": str(firmware), "firmware_sha256": digest(firmware.read_bytes()), "slp_chunk_index": 5, "chunk_offset": hex(offset), "chunk_length": length, "chunk_sha256": digest(image), "header_crc_raw": hex(header_crc), "zlib_crc32": hex(zlib.crc32(image)), "crc_note": "SLP header CRC convention has not been established; unequal values are recorded, not treated as corruption proof.", "artifacts": artifacts, "historical_ghidra": str(args.ghidra), "string_count": len(strings)}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "p7_af_strings.json").write_text(json.dumps(strings, ensure_ascii=False, indent=2), encoding="utf-8")
    for group in GROUPS:
        lines = ["file_offset\tliteral_loads\ttext"]
        for s in strings:
            if group in s["groups"]:
                loads = ",".join(x["instruction"] for x in s["literal_loads"])
                lines.append(s["offset"] + "\t" + loads + "\t" + s["text"].replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t"))
        (out / (group + ".tsv")).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(out), "strings": len(strings), "groups": {g: sum(g in x["groups"] for x in strings) for g in GROUPS}, "p7_sha256": digest(image)}, indent=2))


if __name__ == "__main__":
    main()
