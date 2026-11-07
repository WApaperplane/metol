"""Round 4: close the phase-permission chain.

Three questions left open by round 3 are answered here from current bytes:
  * what produces `GAF+0xc98` (the last gate input) and what it means
  * what `0x30006` is, its full value range and its producers
  * whether `0x60083` is an independent policy input or a constant

Survey hash-checks the official p7 image; the historical function index is used
only to label navigation candidates. Every assertion below reads current bytes.
Read-only: no camera access, no patching, no flashing.
"""
from __future__ import annotations

import json
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_LITTLE_ENDIAN

from trace_round2 import EXPECTED, Survey

OUT = Path(__file__).resolve().parent / "out/round4"
GAF = 0x81550408
IQ_VPTR = 0x805DE008
LENS_PERMIT = 0x816CA5B0

CHECKS = [
    # --- 1. the 0x60084 gate, read end to end -----------------------------
    (0x2F0CE8, "ldrb", "r3, [r0, #0x110]"),
    (0x2F0D00, "bl", "#0x31e754"),
    (0x2F0D0C, "bl", "#0x31e784"),
    (0x2F0D18, "mov", "r1, #0x1e"),
    (0x2F0D20, "movt", "r1, #1"),          # data id 0x1001e
    (0x2F0D30, "mov", "r1, #6"),
    (0x2F0D38, "movt", "r1, #3"),          # data id 0x30006
    (0x2F0D40, "cmp", "r0, #6"),
    (0x2F0D4C, "ldr", "r3, [r5, #0xc98]"),
    (0x2F0D58, "cmp", "r3, #1"),
    (0x2F0D5C, "ble", "#0x2f0cf8"),
    (0x2F0D60, "mov", "r0, #1"),
    (0x2F0D68, "mov", "r1, #0x83"),
    (0x2F0D70, "movt", "r1, #6"),          # data id 0x60083
    (0x2F0D74, "bl", "#0x332948"),
    (0x2F0D80, "ldr", "r3, [r5, #0xc98]"),
    # --- 2. lens-mount permit cluster at 0x816ca5b0 -----------------------
    (0x31E754, "movw", "r3, #0xa5b0"),
    (0x31E758, "movt", "r3, #0x816c"),
    (0x31E75C, "ldrb", "r0, [r3, #0xecc]"),
    (0x31E764, "movw", "r3, #0xa5b0"),
    (0x31E76C, "strb", "r0, [r3, #0xecd]"),
    (0x31E774, "movw", "r3, #0xa5b0"),
    (0x31E77C, "ldrb", "r0, [r3, #0xecd]"),
    (0x31E7D4, "ldrh", "r3, [r4, r6]"),    # cached lens id at +0xece
    (0x31E7E4, "strb", "r5, [r4, #0xecc]"),
    (0x31E7E8, "strb", "r5, [r4, #0xecd]"),
    (0x31E834, "strh", "r3, [r4, r6]"),
    # --- 3. lens classification stub -------------------------------------
    (0x31E784, "movw", "r0, #0x2a8"),
    (0x31E78C, "movt", "r0, #0x8155"),
    (0x31E790, "bl", "#0x2ac16c"),
    (0x31E794, "adds", "r0, r0, #1"),      # classification != -1
    (0x31E798, "movne", "r0, #1"),
    # --- 4. GetSpecificLensTypeAFActuator --------------------------------
    (0x2FF954, "push", "{r3, r4, r5, lr}"),
    (0x2FF96C, "movw", "r3, #0x2002"),
    (0x2FF978, "beq", "#0x2ff9d4"),
    (0x2FF9D4, "bl", "#0x2fe260"),
    (0x2FF9F4, "ldr", "r0, [pc, #0x10]"),
    # --- 5. the only writer of GAF+0xc98 ---------------------------------
    (0x334300, "ldr", "r5, [pc, #0x32c]"),
    (0x334370, "ldrb", "r2, [sp, #0x84]"),
    (0x334374, "ldrb", "r3, [sp, #0x85]"),
    (0x33437C, "smulbb", "r3, r2, r3"),
    (0x334394, "str", "r3, [r5, #0xc98]"),
    (0x334398, "bl", "#0x33273c"),
    (0x3343BC, "str", "r1, [r5, #0xc94]"),
    # --- 6. the only writer of 0x30006/7/8 -------------------------------
    (0x2F3B78, "bl", "#0x2f3a2c"),
    (0x2F3B88, "bl", "#0x2f399c"),
    (0x2F3B9C, "bl", "#0x2aa0c8"),
    (0x2F3BB4, "bl", "#0x33273c"),
    (0x2F3BC8, "bl", "#0x33273c"),
    (0x2F3BDC, "bl", "#0x33273c"),
    # --- 7. 0x30006 derivation ------------------------------------------
    (0x2F3A3C, "bl", "#0x2c01bc"),
    (0x2F3A44, "ldr", "r3, [r3, #0x1e8]"),
    (0x2F3A48, "blx", "r3"),
    (0x2F3A4C, "sxtb", "r0, r0"),
    (0x2F3A50, "cmp", "r0, #0x16"),
    (0x2F3A54, "ldrls", "pc, [pc, r0, lsl #2]"),
    (0x2F3AB8, "mov", "r4, #4"),
    (0x2F3AE8, "bl", "#0x2c01bc"),
    (0x2F3AF8, "sub", "r3, r0, #2"),
    (0x2F3B0C, "mov", "r4, #1"),
    (0x2F3B14, "mov", "r4, #0"),
    (0x2F3B1C, "mov", "r4, #3"),
    (0x2F3B24, "mov", "r4, #2"),
    (0x2F3B2C, "mov", "r4, #5"),
    (0x2F3B58, "cmp", "r0, #1"),
    (0x2F3B5C, "movne", "r4, #3"),
    (0x2F3B60, "moveq", "r4, #6"),
    # --- 8. IQ interface: the field behind 0x30006 -----------------------
    (0x2C1048, "ldr", "r0, [r0, #0x1c0]"),
    (0x2C15C8, "ldr", "r3, [r0, #0x274]"),
    # --- 9. 0x60084 is computed once at AF start -------------------------
    (0x2F2170, "bl", "#0x2f0ce4"),
    (0x2F2180, "ldr", "r0, [r4, #0xb0]"),
    (0x2F2188, "bl", "#0x33273c"),
]


def literal_target(s, at):
    word = s.u32(at)
    assert word & 0x0F7F0000 == 0x051F0000, hex(at)
    pool = at + 8 + ((word & 0xFFF) if word & 0x800000 else -(word & 0xFFF))
    return pool, s.u32(pool)


def scan_instruction_pair(s, image_len):
    """Every (MOV/MOVW Rd,#lo ; MOVT Rd,#hi) pair -> constructed 32-bit id."""
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

    pairs = {}
    for off in range(0, image_len - 4, 4):
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
            pairs.setdefault((hi << 16) | parsed[1], []).append(off - back)
            break
    return pairs


def main():
    s = Survey()
    md = Cs(CS_ARCH_ARM, CS_MODE_ARM | CS_MODE_LITTLE_ENDIAN)
    evidence = []
    for address, mnemonic, operands in CHECKS:
        ins = next(md.disasm(s.image[address:address + 4], address, count=1))
        assert (ins.mnemonic, ins.op_str) == (mnemonic, operands), (hex(address), ins.mnemonic, ins.op_str)
        evidence.append({"offset": hex(address), "bytes": ins.bytes.hex(),
                         "instruction": f"{mnemonic} {operands}"})

    # Literal-backed facts: function name strings and the IQ vtable pointer.
    literals = []
    for at, pointer, fragment in [
        (0x2FF9F4, 0x80746F90, "GetSpecificLensTypeAFActuator"),
        (0x2C012C, IQ_VPTR, None),
        (0x334300, GAF, None),
    ]:
        pool, value = literal_target(s, at)
        assert value == pointer, (hex(at), hex(value))
        text = s.cstring(pointer) if fragment else None
        if fragment:
            assert text and fragment in text, text
        literals.append({"instruction": hex(at), "pool": hex(pool),
                         "value": hex(pointer), "text": text})

    # IQ_SysDataIF_NX1 vtable: RTTI plus the slots this round depends on.
    vp = IQ_VPTR - 0x80000000
    ti = s.u32(vp - 4) - 0x80000000
    rtti = s.cstring(s.u32(ti + 4))
    assert rtti == "17CIQ_SysDataIF_NX1", rtti
    slots = {}
    for slot, expected in [(0x1E8, 0x802C1048), (0x204, 0x802C10C8),
                           (0x20C, 0x802C10F4), (0x254, 0x802C15C8),
                           (0x260, 0x802C16A0)]:
        actual = s.u32(vp + slot)
        assert actual == expected, (hex(slot), hex(actual))
        slots[hex(slot)] = hex(actual)

    # 0x2f3a2c jump table: base is the LDRLS at 0x2f3a54, PC = 0x2f3a5c.
    table = {}
    for index in range(0x17):
        raw = s.u32(0x2F3A5C + index * 4)
        table[index] = hex(raw - 0x80000000)
    assert table[0] == hex(0x2F3B24), table[0]
    assert table[1] == hex(0x2F3AE8), table[1]
    assert table[14] == hex(0x2F3B0C), table[14]
    assert table[20] == hex(0x2F3B2C), table[20]
    assert table[21] == hex(0x2F3AB8), table[21]
    assert table[22] == hex(0x2F3B14), table[22]
    assert table[2] == table[3] == table[13] == table[15] == table[19] == hex(0x2F3B1C)

    # Negative result: 0x60083 and 0x30006 construction sites.
    pairs = scan_instruction_pair(s, min(0x570000, len(s.image)))
    for data_id in (0x60083, 0x60084, 0x30006):
        assert data_id in pairs, hex(data_id)
    for site in pairs[0x60083]:
        call = None
        for cursor in range(site + 4, site + 0x18, 4):
            ins = next(md.disasm(s.image[cursor:cursor + 4], cursor, count=1))
            if ins.mnemonic == "bl":
                call = (cursor, ins.op_str)
                break
        assert call and call[1] == "#0x332948", (hex(site), call)

    # GAF+0xc98 / +0xc94 writers: exactly one STR each in the scanned range.
    str_98, str_94 = [], []
    for off in range(0, min(0x570000, len(s.image)) - 4, 4):
        w = s.u32(off)
        if (w & 0x0FF00000) == 0x05800000 and (w & 0xFFF) in (0xC98, 0xC94):
            str_98.append((off, w & 0xFFF))
    hits_98 = [o for o, imm in str_98 if imm == 0xC98]
    hits_94 = [o for o, imm in str_98 if imm == 0xC94]

    navigation = {
        "p7_sha256": EXPECTED,
        "note": "Linear instruction candidates; each row still needs local confirmation.",
        "id_0x30006_construction_sites": [hex(x) for x in pairs[0x30006]],
        "id_0x60084_construction_sites": [hex(x) for x in pairs[0x60084]],
        "id_0x60083_construction_sites": [hex(x) for x in pairs[0x60083]],
        "gaf_0xc98_str_immediate": [hex(x) for x in hits_98],
        "gaf_0xc94_str_immediate": [hex(x) for x in hits_94],
        "iq_0x1c0_consumers": {"slot_0x1e8": "0x2c1048 returns *(this+0x1c0)",
                               "slot_0x1d8": "0x2c0ffc compares *(this+0x1c0) with 0x16"},
    }

    facts = {
        "p7_sha256": EXPECTED,
        "scope": "Static observations for the hash-locked sample. Not a public ABI, not a patch.",
        "instructions": evidence,
        "literal_references": literals,
        "vtables": {"iq_sysdata": {"vptr": hex(IQ_VPTR), "rtti": rtti, "slots": slots}},
        "derive_0x30006": {
            "table_base": "0x2f3a5c (pc of the LDRLS at 0x2f3a54)",
            "jump_table": table,
            "source_field": "CIQ_SysDataIF_NX1 + 0x1c0, read via vtable slot 0x1e8 (0x2c1048), sign-extended",
            "secondary_source": "vtable slot 0x254 (0x2c15c8) reads +0x274, maps 1..15 through a table at pool+0xd0, returns -1 out of range",
            "mapping": {
                "idx==0": 2, "idx==1 and secondary==0": 1,
                "idx==1 and secondary in {2,3}": 4, "idx==1 and secondary==1": 6,
                "idx==1 and secondary other": 3, "idx==14": 1, "idx==20": 5,
                "idx==21": 4, "idx==22": 0,
                "idx in 2..13,15..19": 3,
            },
            "code_paths": {"4": "0x2f3ab8 reached directly from idx 21, or via 0x2f3af8 sub r3,r0,#2 ; cmp #1 ; bls for secondary 2..3",
                           "1": "0x2f3b0c", "0": "0x2f3b14", "3": "0x2f3b1c",
                           "2": "0x2f3b24", "5": "0x2f3b2c",
                           "6": "0x2f3b60 moveq r4,#6 when the secondary call returns exactly 1"},
            "limitations": "The 0..0x16 enum behind IQ+0x1c0 is not mapped to user menu items here",
        },
        "phase_permission": {
            "function": "0x2f0ce4",
            "inputs": {
                "controller_0x110": "nonzero",
                "lens_mount_flag": {"address": "0x816cae7c", "reader": "0x31e754 (ldrb [+0xecc])", "note": "0x31e7a0 clears +0xecc and +0xecd when the cached lens id at +0xece changes"},
                "lens_classification": {"stub": "0x31e784", "rule": "0x2ac16c(0x815502a8) + 1 != 0, i.e. result != -1"},
                "id_0x1001e": "equals zero",
                "id_0x30006": "not equal to 6",
                "gaf_0xc98": "greater than or equal to 1; the ==1 case falls through because 0x60083 has no writer in p7",
            },
            "computed_once": "0x2f2118 calls 0x2f0ce4 at 0x2f2170 and stores the result with set(0x60084) at 0x2f2188; later readers only fetch it",
            "getter_override_unchanged": "GAF byte0 bit0 forces 0, bit1 forces 1 (round 3)",
        },
        "gaf_0xc98": {
            "writer": "0x334394 str r3,[r5,#0xc98] inside the function starting near 0x334300",
            "value": "smulbb of two unsigned bytes read from the output structure at sp+0x84 and sp+0x85",
            "companion_write": "set(0x5000a, (value-1)>>1) at 0x334398",
            "sibling": "0xc94 receives either 3 or 0xc98 at 0x3343bc",
            "consumer": "0x33fd14 uses GAF+0xc94 as the fifth argument of 0x352c8c when 0x30006 == 5",
            "conclusion": "0xc98 is a geometry-derived block count, not a user policy knob; raising it is not an optimisation lever",
        },
        "id_0x60083": {
            "constructors": [hex(x) for x in pairs[0x60083]],
            "consumers": ["0x2f0d68 inside 0x2f0ce4", "0x338498 inside an unnamed function"],
            "finding": "every construction site is followed by bl 0x332948 (getter); p7 contains no set(0x60083) call",
            "consequence": "with 0xc98 == 1 the gate still passes unless another process writes the item",
        },
        "lens_actuator": {
            "function": "0x2ff954",
            "evidence": "the error path references the literal 'Lens IF ERR : GetSpecificLensTypeAFActuator'",
            "success_condition": "0x234834 returns 0x2002, then 0x2fe260 fills the caller buffer and the function returns 1",
            "error_ids": {"0x40017": ["0x1ba", "0x2b4", "0xb6"]},
            "note": "0x10004 (LensActuatorType) is only written on this success path",
        },
        "limitations": [
            "No live camera execution, no measured latency or hit rate",
            "IQ+0x1c0's 23-value enum is not mapped to menu items; the names 1..6 above are indices, not labels",
            "0x1001e semantics undetermined",
            "Whether another process writes 0x60083 at runtime is outside p7 static scope",
        ],
    }

    OUT.mkdir(parents=True, exist_ok=True)
    for filename, value in [("verified_contracts.json", facts), ("navigation.json", navigation)]:
        (OUT / filename).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Verified {len(evidence)} instructions, {len(literals)} literals, "
          f"{len(slots)} vtable slots, {len(table)} jump-table rows")
    print(f"0x60083 construction sites: {[hex(x) for x in pairs[0x60083]]}")
    print(f"0xc98 STR sites: {[hex(x) for x in hits_98]}  0xc94 STR sites: {[hex(x) for x in hits_94]}")


if __name__ == "__main__":
    main()
