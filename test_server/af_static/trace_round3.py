"""Read-only AF gate, retry-lifetime, execution-flag and vtable evidence.

Survey hash-checks the official image; its historical function index is used
only to label navigation candidates. Assertions below use current bytes.
"""
from __future__ import annotations

import json
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_LITTLE_ENDIAN

from trace_round2 import EXPECTED, Survey


OUT = Path(__file__).resolve().parent / "out/round3"
CHECKS = [
    # Lens actuator property -> data ID -> per-sequence boolean.
    (0x3B5E6C, "bl", "#0x2ff954"),
    (0x3B5F24, "mov", "r1, #4"),
    (0x3B5F28, "movt", "r1, #1"),
    (0x3B5F2C, "ldrb", "r2, [sp, #0x1c]"),
    (0x3B5F34, "bl", "#0x3b53c8"),
    (0x3B63C4, "mov", "r1, #4"),
    (0x3B63CC, "movt", "r1, #1"),
    (0x3B63D4, "bl", "#0x3b546c"),
    (0x34A3BC, "mov", "r1, #4"),
    (0x34A3C0, "movt", "r1, #1"),
    (0x34A3C8, "bl", "#0x332948"),
    (0x34A3CC, "adds", "r0, r0, #0"),
    (0x34A3D0, "movne", "r0, #1"),
    (0x34A3DC, "strb", "r0, [r4, #0x10c]"),
    # Reset is outside the full-reset conditional branch.
    (0x2ADAD4, "beq", "#0x2adb14"),
    (0x2ADB18, "mov", "r4, #0"),
    (0x2ADB38, "movw", "r6, #0x1f30"),
    (0x2ADB54, "str", "r4, [r3, r6]"),
    (0x2ADDB0, "bl", "#0x2adac8"),
    (0x2ADEC8, "bl", "#0x2adac8"),
    (0x2AE2EC, "bl", "#0x2adac8"),
    (0x2AE350, "bl", "#0x2adac8"),
    (0x2AE564, "b", "#0x2adac8"),
    (0x34A2A0, "str", "r5, [r4, #0x8c]"),
    # 0x60084 getter override precedence and ordinary policy producer.
    (0x332950, "tst", "r3, #1"),
    (0x332964, "beq", "#0x3329d0"),
    (0x332994, "and", "r3, r3, #2"),
    (0x3329B4, "mov", "r0, #1"),
    (0x3329D0, "mov", "r0, #0"),
    (0x2F2170, "bl", "#0x2f0ce4"),
    (0x2F2174, "mov", "r1, #0x84"),
    (0x2F217C, "movt", "r1, #6"),
    (0x2F2188, "bl", "#0x33273c"),
    # Four execution flags, identified by return registers and log arguments.
    (0x2F35A8, "mov", "r1, #1"),
    (0x2F35B4, "movt", "r1, #4"),
    (0x2F35C8, "mov", "r8, r0"),
    (0x2F35C0, "mov", "r1, #3"),
    (0x2F35C4, "movt", "r1, #4"),
    (0x2F35DC, "mov", "sl, r0"),
    (0x2F35D4, "mov", "r1, #5"),
    (0x2F35D8, "movt", "r1, #4"),
    (0x2F35EC, "adds", "r6, r0, #0"),
    (0x2F35E8, "mov", "r1, #2"),
    (0x2F35F0, "movt", "r1, #4"),
    (0x2F3604, "mov", "sb, r0"),
    (0x2F369C, "stm", "sp, {r7, r8, sl}"),
    (0x2F36A0, "str", "r6, [sp, #0xc]"),
    (0x2F36A4, "str", "sb, [sp, #0x10]"),
    # Separate movie sequence: gate -> arbitration -> direction/direct drive.
    (0x368918, "cmp", "r3, #0x10c"),
    (0x368AB0, "bl", "#0x367c74"),
    (0x367CA0, "mov", "r1, #0x84"),
    (0x367CA8, "movt", "r1, #6"),
    (0x367CAC, "bl", "#0x332948"),
    (0x367CB4, "bne", "#0x367da0"),
    (0x367DA4, "bl", "#0x366e90"),
    (0x366F30, "b", "#0x366d08"),
    (0x366F48, "b", "#0x366dc4"),
    (0x366D34, "movw", "r1, #0x121"),
    (0x366D68, "bl", "#0x365b70"),
    (0x366DEC, "mov", "r1, #0x120"),
    (0x366E30, "bl", "#0x33baec"),
]


def main():
    s = Survey()
    md = Cs(CS_ARCH_ARM, CS_MODE_ARM | CS_MODE_LITTLE_ENDIAN)
    evidence = []
    for address, mnemonic, operands in CHECKS:
        ins = next(md.disasm(s.image[address:address + 4], address, count=1))
        assert (ins.mnemonic, ins.op_str) == (mnemonic, operands), (hex(address), ins.mnemonic, ins.op_str)
        evidence.append({"offset": hex(address), "bytes": ins.bytes.hex(),
                         "instruction": f"{mnemonic} {operands}"})

    literals = []
    for at, pointer, fragment in [
        (0x3B63E8, 0x807564D0, "LensActuatorType:%d"),
        (0x2F36B4, 0x807429A8, "isS0AF[%d] isRestart[%d] isMovie[%d] isStart[%d]"),
        (0x366D5C, 0x8062713C, "processPafDirCheck_Start"),
        (0x366E24, 0x80627158, "processPafDrive_Start"),
    ]:
        word = s.u32(at)
        assert word & 0x0F7F0000 == 0x051F0000
        pool = at + 8 + ((word & 0xFFF) if word & 0x800000 else -(word & 0xFFF))
        assert s.u32(pool) == pointer
        value = s.cstring(pointer)
        assert fragment in value
        literals.append({"instruction": hex(at), "pool": hex(pool),
                         "runtime_pointer": hex(pointer), "text": value})

    vtables = {}
    for name, pool, expected_vptr, expected_type, slots in [
        ("lens_spec", 0x3B679C, 0x8063B958, "15CAFDataLensSpec", {8: 0x3B5DE0, 12: 0x3B5D60}),
        ("rough_fine", 0x33CAA0, 0x80625078, "26CAFSequenceNxRoughFineScan", {8: 0x34A13C, 32: 0x349930}),
        ("rough_fine_movie", 0x3639BC, 0x80626E98, "31CAFSequenceNxRoughFineScanMovie", {8: 0x368B58, 32: 0x3686E8}),
    ]:
        vptr = s.u32(pool)
        assert vptr == expected_vptr
        vp = vptr - 0x80000000
        ti = s.u32(vp - 4) - 0x80000000
        actual_name = s.cstring(s.u32(ti + 4))
        assert actual_name == expected_type
        actual_slots = {hex(slot): hex(s.u32(vp + slot) - 0x80000000) for slot in slots}
        assert actual_slots == {hex(k): hex(v) for k, v in slots.items()}
        vtables[name] = {"vptr_literal_pool": hex(pool), "vptr": hex(vptr),
                         "rtti": actual_name, "slots_chunk_offsets": actual_slots}

    # Navigate only: constants and branch references can occur in data; the
    # historical owner is a hint. This is not a complete write-reference scan.
    retry_constants = []
    for off in range(0x270000, 0x380000, 4):
        word = s.u32(off)
        if word & 0x0FF00000 == 0x03000000 and (((word >> 4) & 0xF000) | (word & 0xFFF)) == 0x1F30:
            retry_constants.append({"offset": hex(off), "owner_hint": s.owner(off)})
    navigation = {"p7_sha256": EXPECTED,
                  "direct_reset_call_candidates": s.xrefs(calls=[0x2ADAC8]),
                  "retry_movw_candidates_0x270000_to_0x380000": retry_constants}
    facts = {
        "p7_sha256": EXPECTED, "scope": "Static observations, not a public ABI or patch",
        "instructions": evidence, "literal_references": literals, "vtables": vtables,
        "contracts": {
            "execution_ids": {"0x40001": "isS0AF", "0x40002": "isStart", "0x40003": "isRestart", "0x40005": "isMovie", "0x1000f": "wobb_possi (separate lens property)"},
            "phase_only_lens_gate": {"data_id": "0x10004", "data_label": "LensActuatorType",
                                     "producer": "0x3b5de0 reads output of 0x2ff954 into lens-spec data",
                                     "consumer": "0x34a3dc stores boolean(data != 0) at rough-fine object +0x10c",
                                     "limitations": "No physical actuator enum or per-lens enable recommendation established"},
            "phase_fallback_counter": {"base": "0x81550408", "offset": "0x1f30", "reset": "0x2adb54, unconditionally within 0x2adac8", "gate": "less than two in 0x348ad0 / 0x347bbc", "limitations": "Not a camera-lifetime count or a measured number of frames; AF restart may reset it"},
            "wait_peak_counter": {"object_offset": "0x8c", "reset": "rough-fine Initialize at 0x34a2a0; constructor also clears", "consumer": "0x3406dc"},
            "id_0x60084": {"producer": "0x2f0ce4 -> 0x2f2118 stores value",
                           "getter_override": "GAF byte0 bit0 forces zero; else bit1 forces one; else data lookup",
                           "ordinary_gate_inputs": ["controller +0x110 !=0", "0x31e754 global permit byte !=0", "0x31e784 lens classification !=-1", "ID 0x1001e ==0", "ID 0x30006 !=6", "GAF+0xc98 >1, or ==1 with ID 0x60083 ==0"],
                           "limitations": "Policy meaning of all input enums and ordinary gate writers remains partial"},
            "movie_phase_entry": {"dispatcher": "0x3686e8, state 0x10c -> 0x367c74",
                                  "gate": "ID 0x60084 !=0 -> 0x366e90 arbitration",
                                  "tails": {"0x366d08": "processPafDirCheck_Start, state 0x121", "0x366dc4": "processPafDrive_Start, state 0x120"},
                                  "limitations": "Per-resolution selection and movie retry/fallback policy not fully mapped; do not copy still thresholds"},
        },
        "limitations": ["No live camera execution, measured latency or success-rate evidence",
                        "Video resolution and AF-S/AF-C menu mapping not completed",
                        "Distinct movie vtable proves distinct handlers, not which handler every mode selects"],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    for filename, value in [("verified_contracts.json", facts), ("navigation.json", navigation)]:
        (OUT / filename).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Verified {len(evidence)} instructions, {len(literals)} literal references and {len(vtables)} vtables: {OUT}")


if __name__ == "__main__":
    main()
