"""Round 7: the sysdata parameter array -- 184 named slots, and the reason no
field ever had a discoverable writer.

Rounds 5 and 6 kept failing to find a producer for IQ+0x1c0 and IQ+0x2e4. The
reason is structural, not search depth: every sysdata slot is written through a
single virtual `SetParameter(id, value)` whose store address is computed from
the id. Per-offset `str [rX, #0x1c0]` scans can never see it.

Findings asserted here:
  * the class behind vtable 0x805de008 is CIQ_SysDataIF_NX1 (RTTI name string)
  * its layout is { vptr; u32 slot[184] @ +0x04 .. +0x2E3; metadata @ +0x2E4 }
  * slot 0x00c is GetParameter(id): `id <= 0xB7 ? this[id + 1] : -1`
  * slot 0x010 is GetParameter(id, out *) and slot 0x014 is SetParameter(id, value),
    whose store is `this[id + 1] = value` -- a computed offset
  * the ctor memsets exactly 184 * 4 = 0x2E0 bytes starting at +0x04, which is the
    array and nothing else
  * the 184-entry eIQ_ID_* pointer table at 0x5758e0 is that enum, in array order,
    so id i lives at offset 4 + 4 * i. Round 6 called this table "dead"; the
    binding is positional and needs no xrefs
  * IQ+0x1c0 is eIQ_ID_APP_MODE (id 111) and IQ+0x1ec is eIQ_ID_3D_MODE (id 122),
    IQ+0x1f0 is eIQ_ID_3D_AUTO_MODE (id 123)
  * the 0x3b1858 store to `[r4, #0x1c0]` is a decoy: it belongs to
    CIQ_ParamInfo_NX1 (vtable 0x805dea00) and writes its own argument block, not
    the sysdata array

Read-only over the hash-locked official p7. No camera access, no patching.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_LITTLE_ENDIAN

from trace_round2 import EXPECTED, Survey

OUT = Path(__file__).resolve().parent / "out/round7"
IMAGE_SIZE = 0xB84280

VT_SYSDATA = 0x805DE008          # CIQ_SysDataIF_NX1 primary vtable
VT_PARAMINFO = 0x805DEA00        # CIQ_ParamInfo_NX1 primary vtable
SINGLETON = 0x81561CF4           # constructed by 0x2c01bc
FAST_PTR_GLOBAL = 0x815502A8     # +4 holds singleton + 4, i.e. &slot[0]
AF_STATE_BYTE = 0x81550408

SLOT_DTOR_PURE = 0x000
SLOT_GET = 0x00C
SLOT_GET_OUT = 0x010
SLOT_SET = 0x014
SLOT_APP_MODE_DISPATCH = 0x018

NAME_TABLE = 0x5758E0
SLOT_COUNT = 184
ARRAY_BASE = 0x04
ARRAY_BYTES = SLOT_COUNT * 4      # 0x2E0
META_BASE = ARRAY_BASE + ARRAY_BYTES   # 0x2E4

CHECKS = [
    # --- vptr installer (slot 0x000) --------------------------------------
    (0x2BFF08, "ldr", "r3, [pc, #4]"),
    (0x2BFF0C, "str", "r3, [r0]"),
    (0x2BFF10, "bx", "lr"),
    # --- GetParameter(id) (slot 0x00c) -----------------------------------
    (0x2BFF1C, "cmp", "r1, #0xb7"),
    (0x2BFF20, "addls", "r1, r0, r1, lsl #2"),
    (0x2BFF24, "ldrls", "r0, [r1, #4]"),
    (0x2BFF28, "mvnhi", "r0, #0"),
    # --- GetParameter(id, out*) (slot 0x010) -----------------------------
    (0x2BFF38, "ldrls", "r3, [r1, #4]"),
    (0x2BFF40, "strls", "r3, [r2]"),
    (0x2BFF3C, "movls", "r0, #1"),
    # --- SetParameter(id, value) (slot 0x014) ----------------------------
    (0x2BFF4C, "push", "{r4, r5, r6, lr}"),
    (0x2BFF50, "cmp", "r1, #0xb7"),
    (0x2BFF64, "add", "r1, r0, r1, lsl #2"),
    (0x2BFF68, "str", "r2, [r1, #4]"),
    (0x2BFF70, "cmp", "r4, #5"),
    (0x2BFF80, "bics", "r3, r4, #2"),
    (0x2BFFD4, "bl", "#0x2ac660"),
    # --- ctor -------------------------------------------------------------
    (0x2C012C, "ldr", "r3, [pc, #0x84]"),
    (0x2C0134, "str", "r3, [r0]"),
    (0x2C015C, "add", "r5, r0, #4"),
    (0x2C0190, "mov", "r2, #0x2e0"),
    (0x2C0194, "mov", "r0, r5"),
    (0x2C0198, "bl", "#0x50a114"),
    (0x2C01A8, "str", "r2, [r4, #0xf4]"),
    (0x2C01AC, "str", "r5, [r3, #4]"),
    # --- APP_MODE dispatcher and the 3D gates ----------------------------
    (0x2C0230, "ldr", "r3, [r0, #0x1c0]"),
    (0x2C023C, "ldr", "r1, [r0, #0x2b4]"),
    (0x2C0240, "ldr", "r2, [r0, #0x1ec]"),
    (0x2C0ED8, "ldr", "r3, [r0, #0x1ec]"),
    (0x2C0EE4, "cmpeq", "r3, #1"),
    (0x2C1000, "ldr", "r0, [r0, #0x1ec]"),
    (0x2C1008, "cmpeq", "r0, #1"),
    # --- the decoy --------------------------------------------------------
    (0x3B12F4, "mov", "r4, r1"),
    (0x3B1858, "str", "r1, [r4, #0x1c0]"),
    (0x3B19DC, "mov", "r3, #0xb"),
    (0x3B19F4, "str", "r3, [r4, #0x1ec]"),
]

# ids whose meaning gets pinned in this round, by array index.
NAMED = {
    0: "eIQ_ID_AF_MODE",
    1: "eIQ_ID_AF_MOVIE_MODE",
    2: "eIQ_ID_AF_AREA",
    3: "eIQ_ID_AF_MF_ASSIST_MODE",
    4: "eIQ_ID_AF_ASSIST_LAMP",
    5: "eIQ_ID_AF_LOCK_STATUS",
    36: "eIQ_ID_METERING_MODE",
    37: "eIQ_ID_MOVIE_AE",
    39: "eIQ_ID_FLASH_MODE",
    40: "eIQ_ID_FLASH_WIRELESS_SYNC",
    52: "eIQ_ID_FLASH_WIRELESS_MS_GROUPC",
    58: "eIQ_ID_FLASH_EV_EV",
    60: "eIQ_ID_BRACKET_NUMBER",
    65: "eIQ_ID_AV_SETTING",
    68: "eIQ_ID_IDEPTH",
    107: "eIQ_ID_CWB_R_GAIN",
    108: "eIQ_ID_CWB_B_GAIN",
    109: "eIQ_ID_CWB_G_GAIN",
    110: "eIQ_ID_OLED_COLOR",
    111: "eIQ_ID_APP_MODE",
    112: "eIQ_ID_FRAMING_MODE",
    113: "eIQ_ID_ROTATION_POSITION",
    115: "eIQ_ID_SHOOTING_MODE",
    122: "eIQ_ID_3D_MODE",
    123: "eIQ_ID_3D_AUTO_MODE",
    126: "eIQ_ID_WIFI_MODE",
    155: "eIQ_ID_SMARTART_COLORTEMP_LEVEL",
    156: "eIQ_ID_SMART_PRO_MODE",
    162: "eIQ_ID_TV_SETTING_LIMIT",
    169: "eIQ_ID_CONTI_CAPTURING",
    172: "eIQ_ID_AUTOSHUTTER_SUBMODE",
    177: "eIQ_ID_VIDEO_OUT",
    183: "eIQ_ID_SHUTTER_KEY_STATE",
}

# Metadata block after the array: written only by the ctor and slot 0x0c4.
META_DEFAULTS = {
    0x2E4: 0x00, 0x2E8: 0x00, 0x2EC: 0x01, 0x2F0: 0x00, 0x2F4: 0x40,
    0x2F8: 0x70, 0x2FC: 0x00, 0x300: 0x50, 0x304: 0xA0, 0x308: 0x00,
    0x30C: 0x00, 0x310: 0x00, 0x314: 0x00, 0x318: 0x6E,
}


def pool_of(s, at):
    word = s.u32(at)
    assert (word & 0x0F7F0000) == 0x051F0000, hex(at)
    imm = word & 0xFFF
    if not (word & 0x00800000):
        imm = -imm
    return at + 8 + imm


def typeinfo_name(s, vtable):
    """RTTI name of the class owning `vtable` (Itanium layout: -8 offset, -4 ti)."""
    ti = s.u32(vtable - 0x80000000 - 4)
    name_ptr = s.u32(ti - 0x80000000 + 4)
    text = s.cstring(name_ptr)
    assert text is not None and text[0].isdigit()
    return ti, int(text[:len(text) - len(text.lstrip("0123456789"))]), text


def slot_target(s, vtable, slot):
    return s.u32(vtable - 0x80000000 + slot) - 0x80000000


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

    # --- vtable identity --------------------------------------------------
    ti_sys, len_sys, name_sys = typeinfo_name(s, VT_SYSDATA)
    ti_par, len_par, name_par = typeinfo_name(s, VT_PARAMINFO)
    assert (ti_sys, name_sys) == (0x805DE2C4, "17CIQ_SysDataIF_NX1"), (hex(ti_sys), name_sys)
    assert (ti_par, name_par) == (0x805DEA48, "17CIQ_ParamInfo_NX1"), (hex(ti_par), name_par)
    assert len_sys == len(name_sys) - 2 and len_par == len(name_par) - 2

    # --- layout arithmetic: the array is exactly 184 words -----------------
    assert ARRAY_BYTES == 0x2E0 and META_BASE == 0x2E4
    assert s.u32(pool_of(s, 0x2C012C)) == VT_SYSDATA      # ctor literal
    assert s.u32(pool_of(s, 0x2BFF08)) == VT_SYSDATA      # vptr installer literal
    assert pool_of(s, 0x2C012C) == 0x2C01B8
    assert pool_of(s, 0x2BFF08) == 0x2BFF14
    assert s.u32(pool_of(s, 0x2C006C)) == AF_STATE_BYTE
    assert s.u32(pool_of(s, 0x2BFF9C)) == AF_STATE_BYTE
    assert s.u32(pool_of(s, 0x2BFFCC)) == FAST_PTR_GLOBAL

    # --- the accessor vtable ----------------------------------------------
    slots = {}
    for slot in range(0, 0x600, 4):
        target = s.u32(VT_SYSDATA - 0x80000000 + slot)
        if not (0x80000000 <= target < 0x80000000 + IMAGE_SIZE):
            break
        slots[slot] = target - 0x80000000
    assert len(slots) == 166
    assert slots[SLOT_DTOR_PURE] == 0x2BFF08
    assert slots[SLOT_GET] == 0x2BFF1C
    assert slots[SLOT_GET_OUT] == 0x2BFF30
    assert slots[SLOT_SET] == 0x2BFF4C
    assert slots[SLOT_APP_MODE_DISPATCH] == 0x2C0220
    # Round 6 scanned 0x2c0000..0x2c2000 for stores. Get/Set/vptr install all sit
    # just below that window, which is why that scan produced "no writer".
    below = {sl: t for sl, t in slots.items() if t < 0x2C0000}
    assert sorted(below) == [0x000, 0x008, 0x00C, 0x010, 0x014], sorted(below)
    assert min(slots.values()) == 0x2BFF08 and max(slots.values()) == 0x2C17FC

    # --- the enum: 184 names, positional binding --------------------------
    names = [(m.start(), m.group().decode()) for m in
             re.finditer(rb"eIQ_ID_[ -~]{2,60}", s.image)]
    assert len(names) == SLOT_COUNT, len(names)
    ptrs = [s.u32(NAME_TABLE + i * 4) - 0x80000000 for i in range(SLOT_COUNT)]
    assert ptrs == [off for off, _ in names], "name table order must match string order"
    labels = [n for _, n in names]
    for idx, expected in NAMED.items():
        assert labels[idx] == expected, (idx, labels[idx], expected)

    field_map = [{"id": i, "id_hex": hex(i), "offset": hex(ARRAY_BASE + 4 * i),
                  "name": labels[i]} for i in range(SLOT_COUNT)]
    assert field_map[111]["offset"] == "0x1c0"
    assert field_map[122]["offset"] == "0x1ec"
    assert field_map[123]["offset"] == "0x1f0"

    # --- typed accessors prove the naming: WB gains get their own slots ----
    def single_bodies():
        getters, setters = {}, {}
        for slot, target in slots.items():
            ins = list(md.disasm(s.image[target:target + 16], target, count=4))
            if len(ins) >= 2 and ins[1].mnemonic == "bx":
                body = ins[0]
                if body.mnemonic == "ldr" and body.op_str.startswith("r0, [r0, #"):
                    getters[slot] = int(body.op_str.split("#")[1].rstrip("]"), 16)
                if body.mnemonic == "str" and body.op_str.startswith("r1, [r0, #"):
                    setters[slot] = int(body.op_str.split("#")[1].rstrip("]"), 16)
        return getters, setters

    getters, setters = single_bodies()
    assert (getters[0x1B4], getters[0x1B8], getters[0x1BC]) == (0x1B0, 0x1B8, 0x1B4)
    assert (setters[0x1C0], setters[0x1C4], setters[0x1C8]) == (0x1B0, 0x1B8, 0x1B4)
    wb = [labels[(off - ARRAY_BASE) // 4] for off in (0x1B0, 0x1B4, 0x1B8)]
    assert wb == ["eIQ_ID_CWB_R_GAIN", "eIQ_ID_CWB_B_GAIN", "eIQ_ID_CWB_G_GAIN"], wb

    # --- the strongest corroboration: five consecutive slots, five consecutive
    # fields. Slots 0x1fc..0x20c read +0x04, +0x08, +0x0c, +0x10, +0x14 in order,
    # which is only possible if slot stride maps 1:1 onto array slot stride.
    af_cluster = {0x1FC: 0x2C1084, 0x200: 0x2C10A4, 0x204: 0x2C10C8,
                  0x208: 0x2C10EC, 0x20C: 0x2C10F4}
    for slot, target in af_cluster.items():
        assert slots[slot] == target, (hex(slot), hex(slots[slot]), hex(target))
    af_fields = []
    for slot in sorted(af_cluster):
        body = next(md.disasm(s.image[slots[slot]:slots[slot] + 4], slots[slot], count=1))
        assert body.mnemonic == "ldr" and body.op_str.startswith("r"), body.op_str
        af_fields.append(int(body.op_str.split("#")[1].rstrip("]"), 16))
    assert af_fields == [0x04, 0x08, 0x0C, 0x10, 0x14], af_fields
    af_names = [labels[(off - ARRAY_BASE) // 4] for off in af_fields]
    assert af_names == ["eIQ_ID_AF_MODE", "eIQ_ID_AF_MOVIE_MODE", "eIQ_ID_AF_AREA",
                        "eIQ_ID_AF_MF_ASSIST_MODE", "eIQ_ID_AF_ASSIST_LAMP"], af_names
    # the metadata block starts exactly where the array ends
    assert min(setters.values()) >= META_BASE or min(setters.values()) == 0x1B0
    assert sorted(off for off in setters.values() if off >= META_BASE) == \
        [0x2E4, 0x2E8, 0x2EC, 0x2F0, 0x2F4, 0x2F8, 0x2FC, 0x304, 0x308, 0x30C,
         0x310, 0x314, 0x318]

    # --- ctor defaults: read the stores straight out of the image ---------
    # A tiny constant tracker is enough for the 0x2c0128 body: it only ever
    # loads immediates into r1/r3 and stores those two registers.
    const = {}
    defaults = {}
    for off in range(0x2C0128, 0x2C0198, 4):
        ins = next(md.disasm(s.image[off:off + 4], off, count=1))
        if ins.mnemonic in ("mov", "mvn") and ins.op_str.startswith("r") and "#" in ins.op_str:
            reg, imm_txt = ins.op_str.split(", #")
            value = int(imm_txt, 0)
            const[reg] = (~value & 0xFFFFFFFF) if ins.mnemonic == "mvn" else value
            continue
        if ins.mnemonic == "movw" and "#" in ins.op_str:
            reg, imm_txt = ins.op_str.split(", #")
            const[reg] = int(imm_txt, 0)
            continue
        if ins.mnemonic == "str" and ins.op_str.startswith("r") and "[r0, #" in ins.op_str:
            reg = ins.op_str.split(",")[0]
            offset = int(ins.op_str.split("#")[1].rstrip("]"), 16)
            assert reg in const, (hex(off), ins.op_str)
            defaults[offset] = const[reg]
            continue
        # anything else that writes a tracked register invalidates it
        written = ins.op_str.split(",")[0]
        if written in const:
            const.pop(written)
    assert defaults == META_DEFAULTS, {hex(k): hex(v) for k, v in defaults.items()}

    # --- the decoy: 0x3b12e4 is a CIQ_ParamInfo_NX1 method ----------------
    assert slots[SLOT_GET] == 0x2BFF1C
    assert slot_target(s, VT_PARAMINFO, 0x2C) == 0x3B12E4
    assert slots[0x2C] != 0x3B12E4, "the two classes must not share slot 0x2c"
    # slot 0x2c of the other vtable is a different function entirely
    assert slots[0x2C] == 0x2C0468
    # inside 0x3b12e4 the base register is the second argument, not `this`
    assert slot_target(s, VT_PARAMINFO, 0x30) == 0x3B12B4

    facts = {
        "p7_sha256": EXPECTED,
        "scope": "Static observations for the hash-locked sample. Not a public ABI, not a patch.",
        "classes": {
            "CIQ_SysDataIF_NX1": {
                "vtable": hex(VT_SYSDATA),
                "typeinfo": hex(ti_sys),
                "typeinfo_name": name_sys,
                "slots": len(slots),
                "code_range": [hex(min(slots.values())), hex(max(slots.values()))],
                "singleton": hex(SINGLETON),
                "singleton_accessor": "0x2c01bc (double-checked lazy init via guard 0x81561cf0)",
                "array_fast_pointer": {
                    "global": hex(FAST_PTR_GLOBAL + 4),
                    "value": "singleton + 4, i.e. &slot[0]",
                    "written_at": "0x2c01ac in the constructor",
                },
            },
            "CIQ_ParamInfo_NX1": {
                "vtable": hex(VT_PARAMINFO),
                "typeinfo": hex(ti_par),
                "typeinfo_name": name_par,
                "slots": 13,
                "ctor": "0x2c44c4 / 0x2c4500",
                "note": "a different class; its methods never touch the sysdata array",
            },
            "CIQ_Thread_IPC": {
                "typeinfo": "0x805de9ec",
                "typeinfo_name": "14CIQ_Thread_IPC",
                "relationship_to_CIQ_ParamInfo_NX1": "unresolved; the typeinfo records a "
                                                     "base pointer at +0xc pointing at 0x805dea48",
            },
        },
        "object_layout": {
            "vptr": "0x000",
            "slot_array": {"base": "0x004", "count": SLOT_COUNT, "stride": 4,
                           "end": "0x2e3", "bytes": hex(ARRAY_BYTES)},
            "metadata": {"base": hex(META_BASE),
                         "fields": {hex(k): {"ctor_default": hex(v),
                                             "readers": "0x2c02xx-0x2c0dxx"}
                                    for k, v in META_DEFAULTS.items()},
                         "setters": {hex(k): hex(v) for k, v in
                                     sorted((s_, o) for s_, o in setters.items()
                                            if o >= META_BASE)},
                         "meaning": "+0x2e4 is a boolean that switches 10 getters from "
                                    "the live slot value to the shadow value in "
                                    "+0x2e8..+0x318; see slot 0x028 (+0x2f4 vs "
                                    "+0x108 AV_SETTING) and slot 0x038 (+0x30c vs 0)"},
            "zeroed_by_ctor": "0x2c0198 calls 0x50a114(dst = this + 4, 0, 0x2e0), i.e. "
                              "exactly the array, then overwrites +0xf4 with -1",
        },
        "virtual_accessors": {
            "slot_0x000": {"address": "0x2bff08", "body": "str <vptr>, [r0]; bx lr",
                           "role": "vptr installer, also used by derived ctors"},
            "slot_0x00c": {"address": "0x2bff1c",
                           "body": "if (id > 0xb7) return -1; return this[id + 1];",
                           "role": "GetParameter(id)"},
            "slot_0x010": {"address": "0x2bff30",
                           "body": "if (id > 0xb7) return -1; *out = this[id + 1]; "
                                   "return 1;",
                           "role": "GetParameter(id, out *)"},
            "slot_0x014": {"address": "0x2bff4c",
                           "body": "if (id > 0xb7) return -1; this[id + 1] = value; "
                                   "then side effects",
                           "role": "SetParameter(id, value)",
                           "consequence": "the only generic writer of the 184 slots; "
                                          "the store offset is computed from id, so no "
                                          "per-offset str scan can find it. This is the "
                                          "structural reason rounds 5 and 6 could not "
                                          "locate a producer for +0x1c0 or +0x2e4.",
                           "side_effects": {
                               "id_0_or_2": "AF_MODE / AF_AREA: calls 0x2ac660(global, 1)",
                               "id_5": "AF_LOCK_STATUS: two-line log "
                                       "('SET AF LOCK STATUS (%d)' / group variant), "
                                       "bit 5 update in AF state byte 0x81550408, then "
                                       "0x2c311c / 0x2c3198 when the AF phase is 3",
                               "value_3": "when the AF state byte has bit 5 clear and "
                                          "phase == 3, logs via 0x34ca08",
                           }},
        },
        "field_map": field_map,
        "corroboration": {
            "af_cluster": {
                "slots": {hex(k): hex(v) for k, v in af_cluster.items()},
                "fields": [hex(x) for x in af_fields],
                "names": af_names,
                "reading": "five consecutive vtable slots read five consecutive array "
                           "slots in order. Slot stride 4 and field stride 4 line up "
                           "1:1, so the positional binding is not an assumption.",
            },
            "wb_triplets": {
                "getters": {"0x1b4": "+0x1b0", "0x1b8": "+0x1b8", "0x1bc": "+0x1b4"},
                "setters": {"0x1c0": "+0x1b0", "0x1c4": "+0x1b8", "0x1c8": "+0x1b4"},
                "names": wb,
                "reading": "CWB R/G/B gains have dedicated typed getters and setters, "
                           "in the same R,G,B order on both sides",
            },
            "id_36_via_slot_0x20": "slot 0x020 branches on +0x2e4 and falls back to "
                                   "+0x94, which is id 36 eIQ_ID_METERING_MODE",
            "id_65_via_slot_0x28": "slot 0x028 substitutes +0x2f4 for +0x108, which is "
                                   "id 65 eIQ_ID_AV_SETTING; the ctor default 0x40 is "
                                   "therefore a default AV value",
            "id_111_outside_the_class": "0x383380 builds the constant 0x6f, reads it "
                                        "through slot 0x010 and compares with 1 -- the "
                                        "same id and the same accessor, from unrelated "
                                        "code",
        },
        "named_offsets": {
            hex(ARRAY_BASE + 4 * idx): {"id": idx, "name": nm}
            for idx, nm in sorted(NAMED.items())
        },
        "round6_corrections": {
            "eIQ_ID_table_is_dead": "wrong. The 184 pointers are not a dispatch table "
                                    "and need no xrefs: GetParameter indexes the object "
                                    "by enum value, so name table order == slot order. "
                                    "id i <-> offset 4 + 4i.",
            "iq_0x1c0_unnamed": "+0x1c0 is eIQ_ID_APP_MODE (id 111). The 28-entry "
                                "dispatch at 0x2c0220 is an APP_MODE selector that also "
                                "reads AUTOSHUTTER_SUBMODE (id 172) into r1 and "
                                "3D_MODE (id 122) into r2.",
            "iq_0x1ec_unnamed": "+0x1ec is eIQ_ID_3D_MODE (id 122) and +0x1f0 is "
                                "eIQ_ID_3D_AUTO_MODE (id 123). Every '== 1' gate is a "
                                "3D-mode gate.",
            "why_no_writer": "the class region actually starts at 0x2bff08; the round 6 "
                             "scan window 0x2c0000-0x2c2000 excluded the generic "
                             "SetParameter, and direct stores do not exist by design.",
        },
        "nx500_consequence": {
            "3d_mode": "NX500 has no 3D lens, so eIQ_ID_3D_MODE stays at its ctor value 0. "
                       "All four '== 1' consumers (0x2c0edc, 0x2c1008, and the gated "
                       "dispatch entries) therefore always take the non-3D path. The "
                       "zero writer count is a product decision, not dead code from a "
                       "build accident.",
            "app_mode": "eIQ_ID_APP_MODE is a live value: 22 sites build the constant "
                        "0x6f in r1 before a vtable call, and 0x383380 reads it through "
                        "slot 0x010 and compares with 1.",
            "3d_mode_queries": "17 sites build the constant 0x7a, so the 3D feature is "
                               "compiled in and actively queried; it simply never reads "
                               "as 1 on this body.",
        },
        "decoys": {
            "0x3b1858": {
                "instruction": "str r1, [r4, #0x1c0]",
                "why_it_looks_right": "it is the only store to offset 0x1c0 in a "
                                      "function that also writes 0x304 / 0x30c / 0x318",
                "why_it_is_wrong": "r4 = the second argument (set at 0x3b12f4), and the "
                                   "function is slot 0x2c of CIQ_ParamInfo_NX1 "
                                   "(vtable 0x805dea00), not of CIQ_SysDataIF_NX1. Its "
                                   "+0x1bc..+0x1c8 are a negated mirror of its own "
                                   "+0xd0..+0xdc (0x100-a, -b, -c, 0x100-d), and its "
                                   "+0x1ec = 0xb is a literal, not 3D_MODE.",
            },
        },
        "limitations": [
            "No live camera execution; all of this is static",
            "The metadata block +0x2e4..+0x318 is still unnamed; only its switching "
            "behaviour is established",
            "The value domain of the APP_MODE dispatcher (0..0x29, default 0x24) is not "
            "named; only its inputs are pinned",
            "Whether CIQ_Thread_IPC derives from CIQ_ParamInfo_NX1 is unresolved; the "
            "typeinfo chain is 5 words and does not decode cleanly here",
        ],
    }

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "verified_contracts.json").write_text(
        json.dumps(facts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "sysdata_map.tsv").write_text(
        "id\tid_hex\toffset\tname\n" +
        "".join(f"{r['id']}\t{r['id_hex']}\t{r['offset']}\t{r['name']}\n"
                for r in field_map),
        encoding="utf-8")

    print(f"Verified {len(evidence)} instructions")
    print(f"vtable {VT_SYSDATA:#x} = {name_sys} ({len(slots)} slots, "
          f"code {min(slots.values()):#x}..{max(slots.values()):#x})")
    print(f"vtable {VT_PARAMINFO:#x} = {name_par}")
    print(f"layout: vptr | {SLOT_COUNT} x u32 @ +0x04..+0x2e3 | metadata @ +0x2e4")
    print(f"Get/Set live at {slots[SLOT_GET]:#x} / {slots[SLOT_SET]:#x}, "
          f"below the round 6 scan window")
    print(f"+0x1c0 = {labels[111]}   +0x1ec = {labels[122]}   +0x1f0 = {labels[123]}")


if __name__ == "__main__":
    main()
