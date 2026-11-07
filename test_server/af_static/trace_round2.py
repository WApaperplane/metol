"""Local, reproducible second-pass AF navigation and evidence extraction.

All offsets are chunk file offsets. Historical decompiler chunks are hints;
cross-references below are re-read from the current official firmware bytes.
"""
from __future__ import annotations

import bisect
import hashlib
import json
from pathlib import Path
import re
import struct


ROOT = Path("E:/NXWA")
OUT = Path(__file__).resolve().parent / "out/round2"
EXPECTED = "f8e417cb5b55768851ba7e2b8017d3a98dc0b0c8444cc0a5061265cc08dbbf7f"


class Survey:
    def __init__(self):
        with (ROOT / "fw/v1.12/NX500_v1.12.bin").open("rb") as f:
            meta = struct.unpack("<4s8s16s16sbI15s", f.read(64))
            assert meta[0] == b"SLP\0" and meta[4] == 10
            parts = [struct.unpack("<IIII8s", f.read(24)) for _ in range(meta[4])]
            length, _, off, _, _ = parts[5]
            f.seek(off)
            self.image = f.read(length)
        assert hashlib.sha256(self.image).hexdigest() == EXPECTED
        self.functions = []
        for line in Path("E:/ghidra_out/52_pseudocode_index.txt").read_text(encoding="utf-8").splitlines():
            c = line.split("\t")
            if len(c) >= 3 and c[0].startswith("0x"):
                self.functions.append((int(c[0], 16), int(c[1]), c[2]))
        self.functions.sort()
        self.starts = [f[0] for f in self.functions]
        self.chunks = {}
        source = Path("E:/ghidra_out/53_all_pseudocode.c").read_text(encoding="utf-8", errors="replace")
        for chunk in re.split(r"(?=^// ====)", source, flags=re.M):
            m = re.match(r"// ==== (\S+) @ (0x[0-9a-f]+) size=(\d+)", chunk)
            if m:
                self.chunks[int(m[2], 16)] = chunk

    def u32(self, off):
        return struct.unpack_from("<I", self.image, off)[0]

    def cstring(self, address):
        off = address - 0x80000000 if address >= 0x80000000 else address
        if not 0 <= off < len(self.image):
            return None
        raw = self.image[off:off + 500].split(b"\0", 1)[0]
        if not raw or any(x not in (9, 10, 13) and not 32 <= x < 127 for x in raw):
            return None
        return raw.decode("ascii")

    def owner(self, off):
        i = bisect.bisect_right(self.starts, off) - 1
        if i >= 0:
            start, size, name = self.functions[i]
            if off < start + size:
                return {"start": hex(start), "size_hint": size, "name_hint": name}
        return None

    def xrefs(self, values=(), calls=()):
        values = set(values)
        calls = set(calls)
        hits = []
        for off in range(0, min(0x570000, len(self.image)) - 3, 4):
            word = self.u32(off)
            if word >> 28 == 15:
                continue
            if (word & 0x0F7F0000) == 0x051F0000:
                pool = off + 8 + ((word & 0xFFF) if word & 0x800000 else -(word & 0xFFF))
                if 0 <= pool <= len(self.image) - 4:
                    value = self.u32(pool)
                    if value in values:
                        hits.append({"kind": "A32_LDR_literal", "at": hex(off), "pool": hex(pool), "value": hex(value), "owner_hint": self.owner(off)})
            if (word & 0x0E000000) == 0x0A000000:
                delta = (word & 0xFFFFFF) << 2
                if delta & 0x2000000:
                    delta -= 0x4000000
                target = (off + 8 + delta) & 0xFFFFFFFF
                if target in calls:
                    hits.append({"kind": "BL" if word & 0x1000000 else "B", "at": hex(off), "target": hex(target), "owner_hint": self.owner(off)})
        return hits

    def matching_functions(self, pattern):
        rx = re.compile(pattern)
        out = []
        for start, chunk in self.chunks.items():
            if rx.search(chunk):
                lines = chunk.splitlines()
                matches = [(i, line) for i, line in enumerate(lines) if rx.search(line)]
                out.append({"function": hex(start), "matches": matches})
        return out


def main():
    OUT.mkdir(exist_ok=True)
    s = Survey()
    strings = {}
    for term in ["[ME]processing time = %dms", "System Time %8dms", "EyeDetection Error", "FD DETECTED: WAIT STABLE TIME", "FD LOST: WAIT STABLE TIME", "AF mode is changed"]:
        off = s.image.find(term.encode())
        if off >= 0:
            start = s.image.rfind(b"\0", 0, off) + 1
            strings[term] = {"string_start": hex(start), "text": s.cstring(start), "xrefs": s.xrefs(values=[0x80000000 + start])}
    targets = [0x34e9c8, 0x34ea28, 0x141a80, 0x14201c, 0x177790, 0x36ecc4, 0x2ae128, 0x2ae19c,
               0x143740, 0x1438d8, 0x143d30, 0x1430ec, 0x143230, 0x177da0, 0x1ec3cc, 0x3dc910,
               0x36f634, 0x36f13c, 0x36f4f0, 0x33bfcc]
    findings = {"p7_sha256": EXPECTED, "code_scan_limit": "0x570000; linear instruction candidates require manual confirmation", "strings": strings, "direct_branches": s.xrefs(calls=targets), "state_absolute_refs": s.matching_functions(r"DAT_81550464"), "tracking_threshold_consumers": s.matching_functions(r"param_1 \+ 0x15[048c]\)"), "global_literal_refs": s.xrefs(values=[0x81550408])}
    # Resolve the actual system-interface vtable used by the face AF path.
    vptr = s.u32(0x2c01b8)
    vp = vptr - 0x80000000
    ti = s.u32(vp - 4) - 0x80000000
    findings["sysdata_vtable"] = {"constructor": "0x2c0128", "vptr": hex(vptr), "typeinfo_name": s.cstring(s.u32(ti + 4)), "slots": {hex(slot): hex(s.u32(vp + slot) - 0x80000000) for slot in [0x22c, 0x230, 0x234, 0x238, 0x23c, 0x240, 0x244, 0x24c]}}
    contracts = {
        "scope": "Static observations for the hash-locked sample. Not a public ABI, patch, or live memory map.",
        "p7_sha256": EXPECTED,
        "af_state": {"global_reference": "0x81550408", "phase_offset": "0x5c", "phases": {"1": {"name": "onStartSlowAF", "writer": "0x2ae150"}, "2": {"name": "onStartS0AF", "writer": "0x2ae1c4"}, "3": {"name": "onStartS1", "writer": "0x2ae334"}}, "wait_selection": {"instruction": "0x2f6c8c", "S0_AF": 0, "other_phases": 800, "unit": "clock units; counter is divided by 26 and then 1000, physical clock rate not independently confirmed"}},
        "tracking_parameters": {
            "initialization_base": hex(s.u32(0x29b8a0)),
            "initialization_function": "0x29b4e4",
            "ng": {"gaf_offset": "0x44", "initializer_offset": "0x22c", "initial": 8, "store": "0x29b56c", "object_offset": "0x150", "consumer": "0x3514a0"},
            "small": {"gaf_offset": "0x48", "initializer_offset": "0x230", "initial": 4, "store": "0x29b500", "object_offset": "0x158", "consumer": "not resolved; do not claim this is an effective tuning control"},
            "ok": {"gaf_offset": "0x4c", "initializer_offset": "0x234", "initial": 4, "store": "0x29b504", "object_offset": "0x154", "consumer": "0x351034"},
            "default_note": "Initial values in code, not observed current camera values. SMALL and OK share the MOV #4 at 0x29b4f8."
        },
        "main_face_selection": {"function": "0x143740", "ranking_helper": "0x14360c", "input_metrics": ["squared face-center distance to frame center", "face width times height"], "preference": {"closer_center_rank": 6, "larger_area_rank": 3}, "selection": "maximum combined ordinal-rank score; first index wins equal scores", "main_index_store": "0x1438c4", "note": "No selected-subject identity term was found in this scoring function; preceding geometry matching/smoothing does exist at 0x1438d8."},
        "face_info_partial_layout": {
            "record_size": "0x14", "max_faces_observed": 10, "payload_size": "0x444",
            "face_rectangles": "0x000 + face_index * 0x14: x,y,width,height at +0,+4,+8,+0xc",
            "eye_array_a": "0x0c8 + face_index * 0x14: x,y,width,height,+0x10 valid byte",
            "eye_array_b": "0x190 + face_index * 0x14: x,y,width,height,+0x10 valid byte",
            "face_angle_array": "0x258 + face_index * 4; interpreted as orientation by eye processing",
            "main_face_index": "0x398", "face_count": "0x39c",
            "eye_writes": ["0x3dcc48", "0x3dcc4c", "0x3dcc58", "0x3dcc5c"],
            "validity_caveat": "Base face detection clears eye-valid bytes. Eye records are not guaranteed fresh or valid in ordinary face-only mode. A/B are not established anatomical left/right."
        },
        "live_eye_path": {"event_handler": "0x1441dc", "frame_detector": "0x143d30", "smile": "0x1430ec", "wink": "0x143230", "shared_eye_wrapper": "0x177da0", "eye_adapter": "0x1ec3cc", "eye_algorithm": "0x3dc910", "payload": "CFDTask this + 0x54", "mode_gates": {"task_mode": "this+0x918: 3=Smile branch, 4=Wink branch", "smile_enable": "this+0x945", "wink_enable": "this+0x946", "smile_capture_guard": "this+0x947", "wink_capture_guard": "this+0x948"}, "capture_note": "Eye computation is before expression checking and capture notification guards. This is not authorization to enable automatic capture or execute these paths."},
        "af_face_output": {"vtable": findings["sysdata_vtable"], "adapter": "0x2c13b8", "face_getter": "0x141a80", "output_words": ["x", "y", "width", "height", "source_width", "source_height"], "separate_output": "orientation and face count via other pointers", "note": "The current getter takes the main face rectangle, not either eye array."},
        "high_speed_prediction": {"entry": "0x33bfcc ExecuteExposurePredictContiH", "selector": "0x36f634", "selected_value": 1, "selection_instruction": "0x33bff0", "route_1": "0x36f4f0 -> 0x36ea08 linear + correction", "route_0": "0x36f13c -> latest value for <2 samples, linear for 2, 0x36ecc4 second order for >=3", "reachability_scope": "In the scanned A32 direct-call region, selector 0x36f634 has only the 0x33bfcc caller. This does not rule out indirect dispatch."},
        "manual_spans": {"0x143740": "0x198", "0x3dc910": "0x390", "0x2c13b8": "0x9c", "0x2c1454": "0xb8", "0x177da0": "0x18", "0x1ec3cc": "0x18"},
        "tailcall_note": "The historical decompiler inlines 0x143740 into 0x1438d8, and 0x3dc910 into 0x1423dc. Use actual tail-branch targets and manual spans, not pseudocode text length, as code-location evidence."
    }
    # Validate that initializer base arithmetic points to the same three GAF fields.
    init_base = s.u32(0x29b8a0)
    for field in contracts["tracking_parameters"].values():
        if isinstance(field, dict) and "initializer_offset" in field:
            assert init_base + int(field["initializer_offset"], 16) == 0x81550408 + int(field["gaf_offset"], 16)
    contracts["observation_sites"] = {hex(a): s.image[a:a + 4].hex() for a in [0x1438c4, 0x2f6c8c, 0x29b4f8, 0x29b500, 0x29b504, 0x29b558, 0x29b56c, 0x33bff0]}
    (OUT / "navigation.json").write_text(json.dumps(findings, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "contracts.json").write_text(json.dumps(contracts, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"out": str(OUT), "strings": strings, "sysdata_vtable": findings["sysdata_vtable"], "direct_branch_candidates": len(findings["direct_branches"])}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
