"""Round 5: identify the enum behind the AF working-mode code, and check whether
the 6.4 MB data segment that rounds 1-4 never scanned changes any earlier result.

Findings asserted here:
  * p7 is 0xB84280 bytes; only 0x0-0x570000 was ever scanned before this round
  * the data segment carries the full enum-name tables (eIQ_ID_*, eFOCUS_MODE_*, ...)
  * IQ+0xc is eFOCUS_MODE (1..4) and 0x30007 is a three-level derivation of it
  * IQ+0x274 maps 15 raw values onto {0,1,2,3}, confirming round 4's 0x30006 table
  * GetSmartScene / GetSubSmartScene are stubs returning 1
  * every round-4 negative result survives a full-image rescan

Read-only over the hash-locked official p7. No camera access, no patching.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_LITTLE_ENDIAN

from trace_round2 import EXPECTED, Survey

OUT = Path(__file__).resolve().parent / "out/round5"
IMAGE_SIZE = 0xB84280
ENUM_BASE = 0x805DE4EC          # shared table base for slots 0x204 and 0x254
AF_SCRATCH_BASE = 0x805E6040    # table base used inside 0x2f399c

CHECKS = [
    (0x2C10C8, "ldr", "r3, [r0, #0xc]"),          # slot 0x204 reads IQ+0xc
    (0x2C10D4, "ldrls", "r2, [pc, #0xc]"),
    (0x2C10DC, "ldrls", "r0, [r3, #0x14]"),
    (0x2C15C8, "ldr", "r3, [r0, #0x274]"),        # slot 0x254 reads IQ+0x274
    (0x2C15D4, "ldrls", "r2, [pc, #0xc]"),
    (0x2C15DC, "ldrls", "r0, [r3, #0xd0]"),
    (0x2F39C0, "cmp", "r0, #3"),
    (0x2F39C4, "ldrls", "r2, [pc, #0x58]"),
    (0x2F39CC, "addls", "r3, r2, r0, lsl #2"),
    (0x2F39D0, "ldrls", "r4, [r3, #0x1dc]"),
    (0x2F3AF8, "sub", "r3, r0, #2"),
    (0x2F3AFC, "cmp", "r3, #1"),
    (0x2F3B00, "bls", "#0x2f3ab8"),
    (0x2F3B58, "cmp", "r0, #1"),
    (0x2F3B5C, "movne", "r4, #3"),
    (0x2F3B60, "moveq", "r4, #6"),
    (0x0FFCCC, "mov", "r0, #1"),                  # GetSmartScene stub
    (0x0FFCD0, "bx", "lr"),
    (0x0FFCD4, "mov", "r0, #1"),                  # GetSubSmartScene stub
    (0x0FFCD8, "bx", "lr"),
]


def literal_pool(s, at):
    word = s.u32(at)
    assert (word & 0x0C000000) == 0x04000000 and (word & 0x001F0000) == 0x001F0000, hex(at)
    imm = word & 0xFFF
    if not (word & 0x00800000):
        imm = -imm
    return at + 8 + imm


def main():
    s = Survey()
    md = Cs(CS_ARCH_ARM, CS_MODE_ARM | CS_MODE_LITTLE_ENDIAN)

    assert len(s.image) == IMAGE_SIZE, hex(len(s.image))

    evidence = []
    for address, mnemonic, operands in CHECKS:
        ins = next(md.disasm(s.image[address:address + 4], address, count=1))
        assert (ins.mnemonic, ins.op_str) == (mnemonic, operands), (hex(address), ins.mnemonic, ins.op_str)
        evidence.append({"offset": hex(address), "bytes": ins.bytes.hex(),
                         "instruction": f"{mnemonic} {operands}"})

    # --- table bases -----------------------------------------------------
    assert s.u32(literal_pool(s, 0x2C10D4)) == ENUM_BASE
    assert s.u32(literal_pool(s, 0x2C15D4)) == ENUM_BASE
    assert s.u32(literal_pool(s, 0x2F39C4)) == AF_SCRATCH_BASE

    def table(base, offset, count):
        return [s.u32(base + offset + i * 4 - 0x80000000) for i in range(count)]

    focus_mode_map = table(ENUM_BASE, 0x14, 4)          # IQ+0xc      1..4
    sub_mode_map = table(ENUM_BASE, 0xD0, 15)           # IQ+0x274    1..15
    af_class_map = table(AF_SCRATCH_BASE, 0x1DC, 4)     # index by slot-0x204 result

    assert focus_mode_map == [1, 2, 3, 4], focus_mode_map
    assert sub_mode_map == [0, -1 & 0xFFFFFFFF, -1 & 0xFFFFFFFF, -1 & 0xFFFFFFFF,
                            1, 2, -1 & 0xFFFFFFFF, -1 & 0xFFFFFFFF, -1 & 0xFFFFFFFF,
                            -1 & 0xFFFFFFFF, -1 & 0xFFFFFFFF, -1 & 0xFFFFFFFF,
                            -1 & 0xFFFFFFFF, -1 & 0xFFFFFFFF, 3], sub_mode_map
    assert af_class_map == [0, 1, 2, 2], af_class_map

    signed_sub = [v - (1 << 32) if v >= 0x80000000 else v for v in sub_mode_map]

    # --- enum names present in the data segment --------------------------
    names = {}
    for m in re.finditer(rb"[ -~]{4,200}", s.image):
        try:
            text = m.group().decode("ascii")
        except UnicodeDecodeError:
            continue
        names.setdefault(text, m.start())

    required = ["eFOCUS_MODE_SINGLE", "eFOCUS_MODE_CONTINUOUS", "eFOCUS_MODE_MANUAL",
                "eFOCUS_MODE_AUTO", "eAF_MOVIE_SPEED_FAST", "eAF_MOVIE_SPEED_NORMAL",
                "eAF_MOVIE_SPEED_SLOW", "eAF_MOVIE_SENSITIVITY_LEV1",
                "eAF_MOVIE_SENSITIVITY_LEV5", "eIQ_ID_AF_MODE", "eIQ_ID_AF_AREA",
                "eIQ_ID_AF_MULTIAREA", "eIQ_ID_AF_ZONEAREA", "FD_MODE_OFF",
                "MODE_TRACKING", "AF_SUCCESS"]
    for name in required:
        assert name in names, name

    enum_evidence = {name: hex(names[name]) for name in required}

    # --- full-image rescan of the round-4 negative results ---------------
    def ror32(v, n):
        n &= 31
        return v if not n else ((v >> n) | (v << (32 - n))) & 0xFFFFFFFF

    def mov_imm(w):
        if (w & 0x0FE00000) != 0x03A00000:
            return None
        return (w >> 12) & 0xF, ror32(w & 0xFF, ((w >> 8) & 0xF) * 2)

    def movw_imm(w):
        if (w & 0x0FF00000) != 0x03000000:
            return None
        return (w >> 12) & 0xF, (((w >> 16) & 0xF) << 12) | (w & 0xFFF)

    targets = {0x60083, 0x60084, 0x30006, 0x30007, 0x30008, 0x1001E, 0x10004}
    pairs = {}
    for off in range(0, IMAGE_SIZE - 4, 4):
        w = s.u32(off)
        if (w & 0x0FF00000) != 0x03400000:
            continue
        reg = (w >> 12) & 0xF
        hi = (((w >> 16) & 0xF) << 12) | (w & 0xFFF)
        for back in (4, 8):
            if off - back < 0:
                continue
            parsed = mov_imm(s.u32(off - back)) or movw_imm(s.u32(off - back))
            if not parsed or parsed[0] != reg:
                continue
            value = (hi << 16) | parsed[1]
            if value in targets:
                pairs.setdefault(value, []).append(off - back)
            break

    rescan = {hex(k): [hex(x) for x in v] for k, v in sorted(pairs.items())}
    for value, sites in pairs.items():
        for site in sites:
            assert site < 0x570000, (hex(value), hex(site))

    # --- 0xc98 / 0xc94 stores anywhere ----------------------------------
    stores = {}
    for off in range(0, IMAGE_SIZE - 4, 4):
        w = s.u32(off)
        if (w & 0x0FF00000) not in (0x05800000, 0x05C00000):
            continue
        if (w & 0xFFF) in (0xC98, 0xC94):
            stores.setdefault(w & 0xFFF, []).append(off)
    # 0x12e5b0 / 0x12e58c are STRB against an unrelated object in FUN_0012a440;
    # only the 0x334xxx pair stores into GAF.
    assert stores[0xC98] == [0x12E5B0, 0x334394], [hex(x) for x in stores[0xC98]]
    assert stores[0xC94] == [0x12E58C, 0x3343BC], [hex(x) for x in stores[0xC94]]

    facts = {
        "p7_sha256": EXPECTED,
        "scope": "Static observations for the hash-locked sample. Not a public ABI, not a patch.",
        "image": {
            "size": hex(IMAGE_SIZE),
            "code_segment": "roughly 0x020000-0x560000 (string runs per 64 KiB drop to 0 before 0x520000)",
            "data_segment": "0x560000-0xB84280 carries symbol and enum names",
            "earlier_tool_limit": "0x570000 in analyze.py, trace_round2/3/4; now superseded by full-image scans",
        },
        "tables": {
            "enum_table_base": hex(ENUM_BASE),
            "af_scratch_table_base": hex(AF_SCRATCH_BASE),
            "IQ_0xc_to_slot204": {"raw_1_to_4": focus_mode_map,
                                  "reading": "identity, so vtable slot 0x204 returns IQ+0xc for 1..4 and 0 otherwise"},
            "IQ_0x274_to_slot254": {"raw_1_to_15": signed_sub,
                                    "valid_raw": [1, 5, 6, 15],
                                    "valid_output": [0, 1, 2, 3]},
            "slot204_to_0x30007": {"index_0_to_3": af_class_map,
                                   "reading": "0x2f399c indexes this table by the slot-0x204 result; index > 3 falls back to 1"},
        },
        "id_0x30007": {
            "name_hypothesis": "AF drive class, derived from eFOCUS_MODE",
            "derivation": "v = eFOCUS_MODE(IQ+0xc); 0x30007 = TABLE[v] with TABLE=[0,1,2,2] and v>3 -> 1",
            "by_mode": {"SINGLE(raw 1)": 1, "CONTINUOUS(raw 2)": 2, "MANUAL(raw 3)": 2,
                        "AUTO(raw 4)": 1, "none/invalid(raw 0)": 0, "out_of_range(>4)": 1},
            "enum_names": {n: enum_evidence[n] for n in
                           ["eFOCUS_MODE_SINGLE", "eFOCUS_MODE_CONTINUOUS",
                            "eFOCUS_MODE_MANUAL", "eFOCUS_MODE_AUTO"]},
            "limitations": "Raw-value to enum-name binding assumes 1-based ordering by address; not proven from a table",
        },
        "id_0x30006_recheck": {
            "secondary_table": "IQ+0x274 maps to {0,1,2,3}; only raw 1,5,6,15 are valid",
            "consequence": "round 4's table stands: 4 comes from v in {2,3}, 6 from v == 1, everything else 3",
            "added": "idx 21 -> 4 and idx 22 -> 0 bypass the secondary call entirely",
        },
        "smart_scene": {
            "GetSmartScene": {"caller": "0x10f774", "tail": "0xffccc", "body": "mov r0,#1 ; bx lr"},
            "GetSubSmartScene": {"caller": "0x10f7cc", "tail": "0xffcd4", "body": "mov r0,#1 ; bx lr"},
            "finding": "both are stubs returning 1; the NX1 Smart Auto subsystem is not implemented on NX500 p7",
            "consequence": "IQ+0x1c0 is not fed by these stubs, so its 23-value enum has a different owner",
        },
        "video_af_parameters": {
            "speed_names": ["eAF_MOVIE_SPEED_INVALID", "eAF_MOVIE_SPEED_FAST",
                            "eAF_MOVIE_SPEED_NORMAL", "eAF_MOVIE_SPEED_SLOW"],
            "sensitivity_names": ["eAF_MOVIE_SENSITIVITY_INVALID", "eAF_MOVIE_SENSITIVITY_LEV1",
                                  "eAF_MOVIE_SENSITIVITY_LEV2", "eAF_MOVIE_SENSITIVITY_LEV3",
                                  "eAF_MOVIE_SENSITIVITY_LEV4", "eAF_MOVIE_SENSITIVITY_LEV5"],
            "note": "these are the two video AF knobs found in round 1; their value ranges are now named",
        },
        "full_image_rescan": {
            "purpose": "verify round 4's negative results survive a 12 MB scan",
            "construction_sites": rescan,
            "result": "every construction site lies below 0x570000, so the round-4 conclusions stand unchanged",
            "gaf_0xc98_stores": {"gaf": hex(0x334394), "unrelated_object": hex(0x12E5B0)},
            "gaf_0xc94_stores": {"gaf": hex(0x3343BC), "unrelated_object": hex(0x12E58C)},
        },
        "disproved": {
            "linear_iq_id_mapping": "assuming IF fields advance 4 bytes per eIQ_ID entry puts eIQ_ID_CWB_G_GAIN at +0x1c0; a white-balance gain cannot be a 23-value enum, so the assumption is rejected",
        },
        "limitations": [
            "No live camera execution; no measured hit rate or latency",
            "IQ+0x1c0's 23-value enum still has no name: it is not Smart Scene and not a linear IQ-ID slot",
            "0x1001e still unidentified",
            "Enum names are strings in the data segment; binding a name to a numeric value needs a table, not just adjacency",
        ],
    }

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "verified_contracts.json").write_text(
        json.dumps(facts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Verified {len(evidence)} instructions, {len(required)} enum names, "
          f"3 tables, {len(pairs)} data-item ids over the full {IMAGE_SIZE:#x}-byte image")
    print(f"IQ+0xc map {focus_mode_map} -> 0x30007 via {af_class_map}")
    print(f"IQ+0x274 valid raw {[i + 1 for i, v in enumerate(signed_sub) if v >= 0]} "
          f"-> {[v for v in signed_sub if v >= 0]}")


if __name__ == "__main__":
    main()
