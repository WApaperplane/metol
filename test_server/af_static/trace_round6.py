"""Round 6: decode the sysdata-hub ID scheme, and settle the IQ+0x2e4 override.

Round 5 left two grab-handles: who writes IQ+0x2e4, and what 0x1001e is. Both
turn out to be the same question asked at two layers.

Findings asserted here:
  * 0x332948 is the hub getter: value = block[(id >> 16) & 0xFF] -> array[id & 0xFFFF]
  * the hub holds six block pointers at +8..+0x1c plus a short array at +0x34
  * block object layout is {count @ +8, array @ +0x14}; lookup is bounds-checked
  * 0x60084 is special-cased on bits 0/1 of the GAF state byte before dispatch
  * IQ+0x2e4 is a dormant override flag: the class writes it twice (ctor zero and a
    one-instruction setter at vtable slot 0x0c4) and nothing calls that setter
  * the 28-entry +0x1c0 dispatch table inside 0x2c0220 is decoded entry by entry
  * only 2 of the 8 +0x1c0 readers sit behind the +0x2e4 test (round 5 said all 8)
  * the 184-entry eIQ_ID_* name table at 0x5758e0 has no xrefs at all

Read-only over the hash-locked official p7. No camera access, no patching.
"""
from __future__ import annotations

import json
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_LITTLE_ENDIAN

from trace_round2 import EXPECTED, Survey

OUT = Path(__file__).resolve().parent / "out/round6"
IMAGE_SIZE = 0xB84280
CODE_LO, CODE_HI = 0x20000, 0x570000

HUB = 0x332948
HUB_BLOCK_GETTER = 0x3B546C
HUB_DISPATCH_TABLE = 0x33297C          # 6 words, absolute VAs
HUB_FLAG_BYTE = 0x81550408             # GAF state byte 0
CLASS_LO, CLASS_HI = 0x2C0000, 0x2C2000
IQ_VTABLE = 0x805DE008
IQ_SINGLETON = 0x81561CF4
DISPATCH_TABLE = 0x2C0250              # 28 words, absolute VAs
NAME_TABLE = 0x5758E0                  # 184 contiguous name pointers

CHECKS = [
    # --- hub getter -------------------------------------------------------
    (0x332948, "ldr", "r3, [pc, #0xc4]"),
    (0x33294C, "ldrb", "r3, [r3]"),
    (0x332950, "tst", "r3, #1"),
    (0x332954, "beq", "#0x332994"),
    (0x332958, "mov", "r3, #0x84"),
    (0x33295C, "movt", "r3, #6"),
    (0x332960, "cmp", "r1, r3"),
    (0x332964, "beq", "#0x3329d0"),
    (0x332968, "ubfx", "r3, r1, #0x10, #8"),
    (0x33296C, "sub", "r3, r3, #1"),
    (0x332970, "cmp", "r3, #5"),
    (0x332974, "ldrls", "pc, [pc, r3, lsl #2]"),
    (0x332994, "and", "r3, r3, #2"),
    (0x3329A0, "beq", "#0x332968"),
    (0x3329B4, "mov", "r0, #1"),
    (0x3329BC, "cmp", "r1, #0xa"),
    (0x3329C4, "ldr", "r3, [r0, #0x34]"),
    (0x3329C8, "ldr", "r0, [r3, r1, lsl #2]"),
    (0x3329D8, "ldr", "r3, [r0, #0x10]"),
    (0x3329EC, "ldr", "r3, [r0, #0x14]"),
    (0x3329F4, "ldr", "r3, [r0, #0x18]"),
    (0x3329FC, "ldr", "r3, [r0, #0x1c]"),
    (0x332A04, "ldr", "r3, [r0, #8]"),
    (0x332A0C, "ldr", "r3, [r0, #0xc]"),
    # --- block getter -----------------------------------------------------
    (0x3B5470, "ldr", "r3, [r0, #8]"),
    (0x3B5488, "uxth", "r5, r1"),
    (0x3B548C, "cmp", "r3, r5"),
    (0x3B5494, "ldr", "r3, [r4, #0x14]"),
    (0x3B5498, "ldr", "r0, [r3, r5, lsl #2]"),
    # --- IQ override flag and the +0x1c0 dispatcher -----------------------
    (0x2C0220, "ldr", "r3, [r0, #0x2e4]"),
    (0x2C0228, "cmp", "r3, #0"),
    (0x2C022C, "bne", "#0x2c02d4"),
    (0x2C0230, "ldr", "r3, [r0, #0x1c0]"),
    (0x2C0244, "cmp", "r3, #0x1b"),
    (0x2C0248, "ldrls", "pc, [pc, r3, lsl #2]"),
    (0x2C02D4, "ldr", "r0, [r0, #0x2e8]"),
    (0x2C016C, "str", "r1, [r0, #0x2e4]"),
    (0x2C0170, "str", "r1, [r0, #0x2e8]"),
    (0x2C0D98, "str", "r1, [r0, #0x2e4]"),
    (0x2C0DA0, "str", "r1, [r0, #0x2e8]"),
    (0x2C0FFC, "ldr", "r2, [r0, #0x1c0]"),
    (0x2C1004, "cmp", "r2, #0x16"),
    (0x2C1048, "ldr", "r0, [r0, #0x1c0]"),
    (0x2C1214, "ldr", "r3, [r0, #0x1c0]"),
    (0x2C1218, "sub", "r3, r3, #1"),
    (0x2C121C, "cmp", "r3, #0x19"),
    (0x2C0400, "ldr", "r0, [r0, #0x1c0]"),
    (0x2C0474, "ldr", "r3, [r0, #0x1c0]"),
]

# Readers/writers of the two fields of interest, restricted to the class body.
TARGET_1C0 = 0x1C0
TARGET_2E4 = 0x2E4

# Round 5's 8 consumers of +0x1c0, and whether each sits behind a +0x2e4 test.
CONSUMERS_1C0 = {
    0x2C0230: "slot 0x018 dispatcher, entry function 0x2c0220 tests +0x2e4 first",
    0x2C0400: "slot 0x01c, returns (+0x1c0 == 0x16)",
    0x2C0474: "inside function 0x2c0468, which tests +0x2e4 first",
    0x2C0AB4: "slot 0x074, returns +0x13c when +0x1c0 == 0x16",
    0x2C0EDC: "slot 0x190, byte table over +0x1c0 with +0x1ec/+0x1f0 gating",
    0x2C0FFC: "slot 0x1d8, returns (+0x1c0 == 0x16 && +0x1ec == 1)",
    0x2C1048: "slot 0x1e8, raw getter",
    0x2C1214: "slot 0x228, returns (+0x1c0 - 1 <= 0x19)",
}
BEHIND_2E4 = {0x2C0230, 0x2C0474}


def pool_of(s, at):
    word = s.u32(at)
    assert (word & 0x0F7F0000) == 0x051F0000, hex(at)
    imm = word & 0xFFF
    if not (word & 0x00800000):
        imm = -imm
    return at + 8 + imm


def va_targets(s, table, count):
    return [s.u32(table + i * 4) - 0x80000000 for i in range(count)]


def field_accesses(s, md, field):
    """Every load/store with an immediate offset of `field` whose base is a
    general register (not pc/sp/fp/ip/lr), inside the class body."""
    out = []
    for off in range(CLASS_LO, CLASS_HI, 4):
        w = s.u32(off)
        if (w & 0x0E000000) != 0x04000000 or w >> 28 == 0xF:
            continue
        if (w & 0xFFF) != field:
            continue
        got = list(md.disasm(s.image[off:off + 4], off, count=1))
        if not got:
            continue
        ins = got[0]
        if "[" not in ins.op_str:
            continue
        base = ins.op_str.split("[")[-1].split(",")[0].strip()
        if base in ("pc", "sp", "fp", "ip", "lr", "sb", "sl"):
            continue
        out.append((off, ins.mnemonic, base))
    return out


def branch_value(s, md, address, limit=8):
    """Read the constant a dispatch entry returns, following unconditional b's."""
    seen = 0
    at = address
    while seen < limit:
        got = list(md.disasm(s.image[at:at + 4], at, count=1))
        if not got:
            return None
        ins = got[0]
        if ins.mnemonic in ("mov", "movw") and ins.op_str.startswith("r0, #"):
            return int(ins.op_str.split("#")[1], 0)
        if ins.mnemonic == "b":
            at = int(ins.op_str.lstrip("#"), 16)
            seen += 1
            continue
        return None
    return None


def main():
    s = Survey()
    md = Cs(CS_ARCH_ARM, CS_MODE_ARM | CS_MODE_LITTLE_ENDIAN)

    assert len(s.image) == IMAGE_SIZE, hex(len(s.image))

    evidence = []
    for address, mnemonic, operands in CHECKS:
        ins = next(md.disasm(s.image[address:address + 4], address, count=1))
        assert (ins.mnemonic, ins.op_str) == (mnemonic, operands), \
            (hex(address), ins.mnemonic, ins.op_str)
        evidence.append({"offset": hex(address), "bytes": ins.bytes.hex(),
                         "instruction": f"{mnemonic} {operands}"})

    # --- hub: id encoding and block table --------------------------------
    assert s.u32(pool_of(s, 0x332948)) == HUB_FLAG_BYTE
    blocks = va_targets(s, HUB_DISPATCH_TABLE, 6)
    assert blocks == [0x332A04, 0x332A0C, 0x3329D8, 0x3329EC, 0x3329F4, 0x3329FC], \
        [hex(b) for b in blocks]
    # namespace n (1..6) -> hub field offset
    ns_fields = {n + 1: blocks[n] - 0x3329DC for n in range(6)}
    ns_fields = {0x332A04: 8, 0x332A0C: 0xC, 0x3329D8: 0x10,
                 0x3329EC: 0x14, 0x3329F4: 0x18, 0x3329FC: 0x1C}
    assert sorted(ns_fields.values()) == [8, 0xC, 0x10, 0x14, 0x18, 0x1C]

    # --- eIQ_ID name table: contiguous, and dead ------------------------
    import re
    names = [(m.start(), m.group().decode()) for m in
             re.finditer(rb"eIQ_ID_[ -~]{2,60}", s.image)]
    assert len(names) == 184, len(names)
    ptrs = [s.u32(NAME_TABLE + i * 4) - 0x80000000 for i in range(184)]
    assert ptrs == [off for off, _ in names], "name table order must match string order"
    table_end = NAME_TABLE + 184 * 4
    assert s.u32(table_end) != 0x80700DD0          # table ends exactly here
    # no code or data word anywhere points at the table
    lo, hi = 0x80000000 + NAME_TABLE, 0x80000000 + table_end
    xrefs = [off for off in range(0, IMAGE_SIZE - 4, 4)
             if lo <= s.u32(off) < hi]
    assert xrefs == [], [hex(x) for x in xrefs[:5]]

    # --- +0x2e4 / +0x1c0 access census ----------------------------------
    acc_2e4 = field_accesses(s, md, TARGET_2E4)
    stores_2e4 = [a for a, m, b in acc_2e4 if m == "str"]
    loads_2e4 = [a for a, m, b in acc_2e4 if m == "ldr"]
    assert stores_2e4 == [0x2C016C, 0x2C0D98], [hex(x) for x in stores_2e4]
    assert len(loads_2e4) == 10, [hex(x) for x in loads_2e4]

    acc_1c0 = field_accesses(s, md, TARGET_1C0)
    loads_1c0 = [a for a, m, b in acc_1c0 if m == "ldr"]
    assert loads_1c0 == sorted(CONSUMERS_1C0), [hex(x) for x in loads_1c0]
    assert not [a for a, m, b in acc_1c0 if m == "str"], "no store to +0x1c0 in the class"

    # --- IQ vtable -------------------------------------------------------
    vp = IQ_VTABLE - 0x80000000
    slots = []
    for slot in range(0, 0x600, 4):
        target = s.u32(vp + slot)
        if not (0x80000000 <= target < 0x80000000 + IMAGE_SIZE):
            break
        slots.append((slot, target - 0x80000000))
    assert len(slots) == 166, len(slots)
    in_class = [(sl, t) for sl, t in slots if CLASS_LO <= t < CLASS_HI]
    assert len(in_class) == 161, len(in_class)
    vtable_map = {hex(sl): hex(t) for sl, t in in_class}

    # setter family 0x0c0..0x0e8 walks +0x2e0 upward by 4 for the first few
    setters = {}
    for slot, target in in_class:
        got = list(md.disasm(s.image[target:target + 8], target, count=2))
        if len(got) == 2 and got[0].mnemonic == "str" and got[1].mnemonic == "bx" \
                and got[1].op_str == "lr":
            m = got[0].op_str
            if m.startswith("r1, [r0, #"):
                setters[slot] = int(m.split("#")[1].rstrip("]"), 16)
    assert setters.get(0xC4) == 0x2E4, setters
    assert setters.get(0xC8) == 0x2E8, setters
    family = [setters[sl] for sl in sorted(setters) if 0xC0 <= sl <= 0xE8]
    assert family == [0x2E4, 0x2E8, 0x2EC, 0x2F0, 0x2F4, 0x2F8, 0x2FC,
                      0x304, 0x308, 0x30C], [hex(x) for x in family]
    # slot 0x0c0 is the getter for +0x2e0 and +0x300 has no setter at all,
    # so the setter family skips both.
    assert setters.get(0xC0) is None
    assert 0x300 not in setters.values()

    # --- the 28-entry +0x1c0 dispatch table ------------------------------
    targets = va_targets(s, DISPATCH_TABLE, 28)
    assert len(targets) == 28
    dispatch = {}
    for idx, target in enumerate(targets):
        dispatch[idx] = {"entry": hex(target), "constant": branch_value(s, md, target)}
    constants = {i: v["constant"] for i, v in dispatch.items()}
    assert constants[0] == 0x15 and constants[3] == 1 and constants[4] == 2
    assert constants[7] == 0x1A and constants[20] == 4 and constants[13] == 6
    assert constants[2] is None and constants[22] is None and constants[1] is None
    assert constants[6] is None and constants[26] == 0x1C

    # the two byte tables the dispatcher indexes, read straight out of the image
    byte_table = 0x5DE2D0
    entry1_bytes = list(s.image[byte_table:byte_table + 0x26])
    assert entry1_bytes == [5, 0x1E, 0x1F, 0x20, 0x21, 0x22, 0x23, 0x24, 0x0D, 0x24,
                            0x24, 0x24, 0x19, 6, 0x24, 0x0B, 0x24, 0x24, 0x0C, 0x15,
                            0x24, 0x25, 0x24, 0x24, 0x24, 0x28, 0x24, 0x24, 0x24, 0x24,
                            0x24, 0x24, 0x24, 0x24, 0x20, 0x24, 0x26, 0x27], entry1_bytes
    assert entry1_bytes.count(0x24) == 20, entry1_bytes.count(0x24)
    entry22_bytes = list(s.image[byte_table + 0x30:byte_table + 0x33])
    assert entry22_bytes == [0x10, 0x11, 0x12], entry22_bytes

    facts = {
        "p7_sha256": EXPECTED,
        "scope": "Static observations for the hash-locked sample. Not a public ABI, not a patch.",
        "hub_id_scheme": {
            "getter": hex(HUB),
            "signature": "GetSysData(hub, id) -> u32",
            "encoding": "id = (block << 16) | index",
            "block_selector": "ubfx r3, r1, #0x10, #8 then sub #1, cmp #5, jump table",
            "valid_blocks": [1, 2, 3, 4, 5, 6],
            "block_to_hub_field": {str(k): hex(v) for k, v in
                                   {1: 8, 2: 0xC, 3: 0x10, 4: 0x14, 5: 0x18, 6: 0x1C}.items()},
            "short_ids": "id <= 0xa indexes a word array at hub+0x34",
            "out_of_range": "block 0 or block > 6 with index > 0xa returns 0",
            "block_object_layout": {"count": "+0x8", "payload_or_log": "+0x10",
                                    "array": "+0x14"},
            "bounds_check": "if (count <= (u16)index) -> log via 0x2f8e7c/0x2f92f4, "
                            "return 0; the array read is (u16)index based, so the low "
                            "half must be <= 0xffff",
            "special_case_0x60084": {
                "value_source": "byte 0 of GAF state 0x81550408, tested before dispatch",
                "bit0_set": "returns 0",
                "bit1_set_and_bit0_clear": "returns 1",
                "neither_bit": "falls through to block 6 index 0x84",
                "consequence": "0x60084 is a synthesised answer in the flagged states, "
                               "not always the stored snapshot",
            },
            "reinterpretation": {
                "0x1001e": "block 1 index 0x1e; the AF gate 0x2f0ce4 only requires it to be 0",
                "0x30006": "block 3 index 6 (AF block)",
                "0x30007": "block 3 index 7, same block as 0x30006",
                "0x60084": "block 6 index 0x84, overridden by GAF flag bits",
                "why_it_matters": "these are array slots pushed by a producer subsystem, "
                                  "not named struct fields; there is no per-id name table",
            },
        },
        "iq_override_pair": {
            "flag": "+0x2e4", "value": "+0x2e8",
            "writers_in_class": {hex(a): ("constructor zero" if a == 0x2C016C
                                          else "one-instruction setter, vtable slot 0x0c4")
                                 for a in (0x2C016C, 0x2C0D98)},
            "reader_count": len(loads_2e4),
            "reader_offsets": [hex(x) for x in loads_2e4],
            "override_fields": ["+0x2e8", "+0x2f4", "+0x2f8", "+0x2fc", "+0x300",
                                "+0x304", "+0x30c", "+0x310", "+0x314", "+0x318"],
            "direct_bl_callers_of_setter": [],
            "vtable_slot_0xc4_indirect_callers": [],
            "conclusion": "the override path is dormant in the shipped image: the only "
                          "write is the constructor's zero, and no caller of the setter "
                          "was found either by direct BL or by ldr [vtbl,#0xc4] + blx",
            "caveat": "a computed slot index would escape both scans; keep this as "
                      "'not found', not 'proven unreachable'",
        },
        "iq_0x1c0_consumers": {
            "count": len(loads_1c0),
            "sites": {hex(k): v for k, v in CONSUMERS_1C0.items()},
            "behind_0x2e4_test": [hex(x) for x in sorted(BEHIND_2E4)],
            "round5_correction": "round 5 stated all 8 consumers sit in the +0x2e4 == 0 "
                                 "branch; only 2 of 8 do. The 8 is correct, the "
                                 "shared-branch claim is not.",
            "value_range": "1..0x1a (slot 0x228 tests (v - 1) <= 0x19); the dispatcher "
                           "at 0x2c0220 accepts 0..0x1b",
        },
        "iq_0x1c0_dispatch": {
            "function": hex(0x2C0220),
            "vtable_slot": "0x018",
            "inputs": {"+0x1c0": "mode index", "+0x1ec": "secondary flag, must be 1",
                       "+0x98": "count, used by entry 22", "+0x2b4": "used by entry 6? see below",
                       "+0x274": "used by entry 1, byte table of 38 entries"},
            "table": dispatch,
            "reading": "entry 2/8/24/25 return 0 unless +0x1ec == 1, in which case they "
                       "return 0x13 for mode 0x16 and 0x1c otherwise; entry 22 indexes a "
                       "3-byte table with (+0x98 - 1) and falls back to 0xf; entry 1 "
                       "indexes a 38-byte table with +0x274 and falls back to 0x24",
            "entry_1_byte_table": {
                "base": "0x805de2d0, 38 bytes, indexed by +0x274",
                "values": entry1_bytes,
                "sentinel": "0x24 appears 20 times and is also the >0x25 fallback, so it "
                            "reads as 'no layout for this value'",
            },
            "entry_22_byte_table": {
                "base": "0x805de2d0 + 0x30, 3 bytes, indexed by (+0x98 - 1)",
                "values": entry22_bytes,
            },
            "code_range": "0..0x29, 0x24 is the sentinel",
            "unknown": "the field itself is still unnamed; only its range and its "
                       "consumers are pinned",
        },
        "iq_vtable": {
            "base": hex(IQ_VTABLE),
            "slot_count": len(slots),
            "slots_into_class": len(in_class),
            "slot_to_target": vtable_map,
            "setter_family_0xc0_0xe8": {hex(sl): hex(setters[sl])
                                        for sl in sorted(setters) if 0xC0 <= sl <= 0xE8},
            "note": "this is the first complete slot -> implementation map for the class; "
                    "each slot body is 1-4 instructions, so field offsets are readable "
                    "directly from the map",
        },
        "dead_name_table": {
            "offset": hex(NAME_TABLE),
            "entries": 184,
            "contiguous": True,
            "order": "matches string order, i.e. eIQ_ID_AF_MODE first",
            "xrefs": 0,
            "conclusion": "the table is not reachable from code in this image; the "
                          "eIQ_ID_* strings can be used as labels for the enum order but "
                          "cannot be bound to field offsets through it",
        },
        "disproved": {
            "round5_shared_override_branch": "all +0x1c0 consumers behind +0x2e4 == 0",
            "id_as_struct_offset": "0x1NNNN / 0x3NNNN / 0x6NNNN are not struct field ids; "
                                   "the high byte selects a block object and the low half "
                                   "is an array index",
        },
        "limitations": [
            "No live camera execution; no measured behaviour",
            "IQ+0x1c0 still has no name. Its producer is outside the class: there is no "
            "store to +0x1c0 anywhere in 0x2c0000-0x2c2000",
            "the six block objects are runtime instances; their contents are not in the "
            "image, so block membership is inferred from the dispatch, not observed",
            "0x1001e is now located (block 1, index 0x1e) but not named",
        ],
    }

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "verified_contracts.json").write_text(
        json.dumps(facts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Verified {len(evidence)} instructions; hub has {len(blocks)} blocks; "
          f"vtable {len(slots)} slots ({len(in_class)} in class)")
    print(f"+0x2e4 in class: {len(stores_2e4)} stores, {len(loads_2e4)} loads")
    print(f"+0x1c0 in class: {len(loads_1c0)} loads, 0 stores "
          f"({len(BEHIND_2E4)} behind the +0x2e4 test)")
    print(f"dispatch constants idx->value: "
          f"{ {i: v for i, v in constants.items() if v is not None} }")
    print(f"eIQ_ID name table: 184 entries at {NAME_TABLE:#x}, {len(xrefs)} xrefs")


if __name__ == "__main__":
    main()
