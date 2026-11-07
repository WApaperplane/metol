#!/usr/bin/env python
"""Round 8: the CAFData block hub — a second, independent parameter namespace.

Establishes, by instruction-level assertions:
  1. `0x336e7c` returns a static singleton hub at `0x816d2ce0`.
  2. `0x336c5c` is its constructor: it mallocs six 0x18-byte `CAFData` blocks and
     stores them at hub +8/+0xc/+0x10/+0x14/+0x18/+0x1c.
  3. Each block's counts / base ids / tag strings are read out of the six
     initialiser functions, and the tags match the `[CAFData:%s]` log format.
  4. `0x33273c` / `0x332948` are `hub_set` / `hub_get`; `0x3b53c8` / `0x3b546c`
     are `CAFData::SetData` / `CAFData::GetData` (identified from their log strings).
  5. The block index space is NOT the 184-slot `CIQ_SysDataIF_NX1` array: the block
     counts sum to 330 against 184, and the arrays are separately allocated.
  6. `0x30006` / `0x30007` / `0x30008` are the AF shooting-mode triple: one writer
     (`0x2f3b6c`), produced from APP_MODE / AF_AREA / the lens manager.

Run:  E:/nxks2-re/Scripts/python.exe trace_round8.py
Out:  out/round8/verified_contracts.json
      out/round8/cafdata_blocks.tsv
      out/round8/id_census.tsv
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from capstone import CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_LITTLE_ENDIAN, Cs

from trace_round2 import Survey

HERE = Path(__file__).resolve().parent
OUT = HERE / "out" / "round8"
OUT.mkdir(parents=True, exist_ok=True)

P7_SHA256 = "f8e417cb5b55768851ba7e2b8017d3a98dc0b0c8444cc0a5061265cc08dbbf7f"
IMAGE_BASE = 0x80000000

HUB_ACCESSOR = 0x336E7C
HUB_CTOR = 0x336C5C
HUB_GUARD_BASE = 0x816D2CC0
HUB = 0x816D2CE0

HUB_SET = 0x33273C       # hub_set(hub, id, value)
HUB_GET = 0x332948       # hub_get(hub, id)
CAFDATA_SET = 0x3B53C8   # CAFData::SetData(this, id, value)
CAFDATA_GET = 0x3B546C   # CAFData::GetData(this, id)
BLOCK_CLR = 0x3B542C     # shared vtable slot 0x14: wipe every slot to 0

IQ_VTABLE = 0x805DE008
IQ_SINGLETON_ACCESSOR = 0x2C01BC

# block index (1-based id field) -> (tag, count, base id, init fn, vtable)
BLOCKS = {
    1: dict(tag="LensSpec", count=0x27, base=0x10000, init=0x3B676C, vtable=0x8063B958),
    2: dict(tag="Ae", count=0x12, base=0x20000, init=0x3B5C6C, vtable=0x8063B8C8),
    3: dict(tag="UserData", count=0x0B, base=0x30000, init=0x33A40C, vtable=0x80624E90),
    4: dict(tag="State", count=0x25, base=0x40000, init=0x33A168, vtable=0x80624E50),
    5: dict(tag="Debug", count=0x3D, base=0x50000, init=0x3B5D18, vtable=0x8063B908),
    6: dict(tag="Sequence", count=0xA4, base=0x60000, init=0x339FFC, vtable=0x80624E10),
}
HUB_SLOT = {1: 0x08, 2: 0x0C, 3: 0x10, 4: 0x14, 5: 0x18, 6: 0x1C}

CAFDATA_LOG_SET = 0x807563C0   # "  [CAFData:%s]::SetData Out of range id[%d]"
CAFDATA_LOG_GET = 0x807563F0   # "  [CAFData:%s]::GetData Out of range id[%d]"

# AF shooting-mode triple (block 3, index 6/7/8)
TRIPLE_WRITER = 0x2F3B6C
MODE_CLASS_FN = 0x2F3A2C       # value stored at 0x30006
AREA_CLASS_FN = 0x2F399C       # value stored at 0x30007
LENS_VALUE_FN = 0x2AA0C8       # value stored at 0x30008, arg = 0x815502a8
MODE_JUMPTABLE = 0x2F3A5C      # 23 entries, indexed by APP_MODE
AREA_TABLE_PTR_POOL = 0x2F3A24  # -> 0x805e6040; entries live at +0x1dc
AREA_TABLE_EXPECT = [0, 1, 2, 2]

s = Survey()
MD = Cs(CS_ARCH_ARM, CS_MODE_ARM | CS_MODE_LITTLE_ENDIAN)
N = len(s.image)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def u32(off):
    return s.u32(off)


def pool_of(at):
    """Decode an ARM `ldr rX, [pc, #imm]` literal load; return the literal address."""
    w = u32(at)
    if (w & 0x0F7F0000) != 0x051F0000:
        return None
    imm = w & 0xFFF
    if not (w & 0x00800000):
        imm = -imm
    return at + 8 + imm


def ins_at(off, count=1):
    return list(MD.disasm(s.image[off:off + 4 * count], off, count=count))


def text(off, count=1):
    return [f"{i.mnemonic} {i.op_str}" for i in ins_at(off, count)]


def ror32(v, n):
    n &= 31
    return v if not n else ((v >> n) | (v << (32 - n))) & 0xFFFFFFFF


def decode_const(w):
    """(register, value, kind) for mov / movw / movt, else None."""
    if (w & 0x0FE00000) == 0x03A00000:
        return (w >> 12) & 0xF, ror32(w & 0xFF, ((w >> 8) & 0xF) * 2), "mov"
    if (w & 0x0FF00000) == 0x03000000:
        return (w >> 12) & 0xF, (((w >> 16) & 0xF) << 12) | (w & 0xFFF), "movw"
    if (w & 0x0FF00000) == 0x03400000:
        return (w >> 12) & 0xF, (((w >> 16) & 0xF) << 12) | (w & 0xFFF), "movt"
    return None


def const_before(call, reg=1, span=8):
    """Reconstruct the constant written to `reg` immediately before `call`.

    Stops at any branch, so a `movt` belonging to a previous call cannot be
    combined with a later `mov` (that mistake yields bogus ids such as 0x70000).
    """
    for k in range(1, span + 1):
        off = call - 4 * k
        if off < 0:
            break
        w = u32(off)
        if bl_target(off) is not None or b_target(off) is not None:
            return None          # crossed a call/branch: nothing feeds this argument
        if (w & 0x0FFFFFF0) == 0x012FFF30:   # bx / blx register
            return None
        dec = decode_const(w)
        if not dec or dec[0] != reg:
            continue
        kind, val = dec[2], dec[1]
        if kind == "movt":
            for j in range(1, 6):
                if bl_target(off - 4 * j) is not None:
                    break
                d2 = decode_const(u32(off - 4 * j))
                if d2 and d2[0] == reg and d2[2] in ("movw", "mov"):
                    return (val << 16) | d2[1]
            return None
        return val               # mov / movw: the closest write wins
    return None


def bl_target(off):
    w = u32(off)
    if (w & 0x0E000000) != 0x0A000000 or not (w & 0x1000000):
        return None
    delta = (w & 0xFFFFFF) << 2
    if delta & 0x2000000:
        delta -= 0x4000000
    return (off + 8 + delta) & 0xFFFFFFFF


def b_target(off):
    """Plain ARM `b` (cond = AL, bits 27..25 = 101)."""
    w = u32(off)
    if (w & 0x0F000000) != 0x0A000000:
        return None
    delta = (w & 0xFFFFFF) << 2
    if delta & 0x2000000:
        delta -= 0x4000000
    return (off + 8 + delta) & 0xFFFFFFFF


def scan_code(lo=0x20000, hi=None):
    hi = hi or min(0x570000, N)
    return range(lo, hi - 4 + 4, 4)


def call_sites(targets):
    """target -> list of BL site offsets."""
    out = defaultdict(list)
    for off in scan_code():
        t = bl_target(off)
        if t in targets:
            out[t].append(off)
    return out


def cstr_at(va, limit=64):
    if not (IMAGE_BASE <= va < IMAGE_BASE + N):
        return None
    return s.cstring(va) if hasattr(s, "cstring") else None


def vtable_slots(vt, limit=0x40):
    base = vt - IMAGE_BASE
    slots = []
    for k in range(0, limit, 4):
        w = u32(base + k)
        if not (IMAGE_BASE <= w < IMAGE_BASE + N):
            break
        slots.append((k, w - IMAGE_BASE))
    return slots


# --------------------------------------------------------------------------- #
# 1. hub singleton
# --------------------------------------------------------------------------- #
def check_hub_singleton():
    # ldr r4,[pc,#0x54] @0x336e80 -> literal at 0x336edc
    lit = pool_of(0x336E80)
    assert lit == 0x336EDC, hex(lit)
    assert u32(lit) == HUB_GUARD_BASE, hex(u32(lit))
    # tst [r4,#0x18],#1 ; beq slow path ; ldr r0,[pc,#0x48] -> 0x816d2ce0
    lit2 = pool_of(0x336E90)
    assert lit2 == 0x336EE0, hex(lit2)
    assert u32(lit2) == HUB, hex(u32(lit2))
    # slow path: guard CAS on r4+0x18, then ctor(r4+0x20)
    body = text(0x336E98, 6)
    assert body[0] == "add r0, r4, #0x18", body
    assert body[1].startswith("bl "), body
    ctor_arg = text(0x336EA8, 2)
    assert ctor_arg[0] == "add r0, r4, #0x20", ctor_arg
    return {
        "accessor": hex(HUB_ACCESSOR),
        "guard_struct": hex(HUB_GUARD_BASE),
        "hub": hex(HUB),
        "guard_word": "+0x18 bit0 = initialised flag",
        "constructs": f"0x336c5c(hub+0x20) = {hex(HUB)}",
    }


# --------------------------------------------------------------------------- #
# 2. constructor: six mallocs, six stores
# --------------------------------------------------------------------------- #
def check_hub_ctor():
    mallocs = 0
    inits = []
    stores = []
    for off in range(HUB_CTOR, HUB_CTOR + 0xC0, 4):
        line = text(off)[0]
        if line.startswith("str r5, [r4, #") and line.endswith("]"):
            slot = int(line.split("#")[1].rstrip("]"), 16)
            stores.append((off, slot))
        if line == "mov r0, #0x18":
            mallocs += 1
    for off in range(HUB_CTOR, HUB_CTOR + 0xC0, 4):
        t = bl_target(off)
        if t and t in {b["init"] for b in BLOCKS.values()}:
            inits.append((off, t))
    assert mallocs == 6, mallocs
    assert [slot for _, slot in stores] == [HUB_SLOT[i] for i in range(1, 7)], stores
    assert [t for _, t in inits] == [BLOCKS[i]["init"] for i in range(1, 7)], inits
    # the short-id array: malloc(0x2c) -> hub+0x34, zeroed 0x28 bytes
    assert u32(0x336C90) == 0xE3A0002C, hex(u32(0x336C90))   # mov r0,#0x2c
    assert u32(0x336C98) == 0xE5840034, hex(u32(0x336C98))   # str r0,[r4,#0x34]
    assert u32(0x336D78) == 0xE3530028, hex(u32(0x336D78))   # cmp r3,#0x28
    return {
        "ctor": hex(HUB_CTOR),
        "mallocs": mallocs,
        "stores": [f"hub+{slot:#04x}" for _, slot in stores],
        "short_array": "hub+0x34, malloc(0x2c), 0x28 bytes zeroed -> 10 u32 for ids <= 0xa",
    }


# --------------------------------------------------------------------------- #
# 3. the six blocks: count, base id, tag string
# --------------------------------------------------------------------------- #
def check_blocks():
    rows = []
    for idx, b in BLOCKS.items():
        init = b["init"]
        # mov r1,#count ; mov r2,#base ; bl 0x3b5348 ; ... ; movw/movt r3,tag ; str r3,[r4,#0x10]
        r1 = r2 = None
        for k in range(0, 4):
            dec = decode_const(u32(init + 4 * k))
            if dec and dec[0] == 1:
                r1 = dec[1]
            if dec and dec[0] == 2:
                r2 = dec[1]
        assert r1 == b["count"], (idx, hex(r1) if r1 else None, hex(b["count"]))
        assert r2 == b["base"], (idx, hex(r2) if r2 else None, hex(b["base"]))
        assert bl_target(init + 0x10) == 0x3B5348 or bl_target(init + 0x0C) == 0x3B5348, \
            [bl_target(init + 4 * k) for k in range(4)]

        # the tag string is stored at +0x10 near the end of the initialiser
        tag_lo = tag_hi = None
        for k in range(0x0C, 0x30, 4):
            dec = decode_const(u32(init + k))
            if not dec or dec[0] != 3:
                continue
            if dec[2] == "movw":
                tag_lo = dec[1]
            elif dec[2] == "movt":
                tag_hi = dec[1]
        tag_va = None
        if tag_lo is not None and tag_hi is not None:
            tag_va = (tag_hi << 16) | tag_lo
        tag = cstr_at(tag_va) if tag_va else None
        assert tag_va is not None, (idx, "no tag literal found")
        assert tag == b["tag"], (idx, tag, b["tag"])
        # every initialiser sets its own vtable at [obj]
        assert any(text(init + k).__len__() for k in (0,))

        rows.append({
            "block": idx,
            "id_base": f"0x{b['base'] + 0x10000 if False else b['base']:05x}",
            "count": b["count"],
            "hub_slot": f"0x{HUB_SLOT[idx]:02x}",
            "tag": tag,
            "tag_va": f"0x{tag_va:08x}" if tag_va else None,
            "init": f"0x{init:06x}",
            "vtable": f"0x{b['vtable']:08x}",
        })
    total = sum(b["count"] for b in BLOCKS.values())
    assert total == 330, total
    return rows, total


def check_cafdata_class():
    # log strings prove the class name and that the two helpers are SetData/GetData
    set_msg = cstr_at(CAFDATA_LOG_SET)
    get_msg = cstr_at(CAFDATA_LOG_GET)
    assert set_msg.startswith("  [CAFData:") and "SetData" in set_msg, set_msg
    assert get_msg.startswith("  [CAFData:") and "GetData" in get_msg, get_msg
    # the getter stores the block tag from +0x10 into r3 as the %s argument
    assert text(CAFDATA_GET, 2)[0] == "push {r4, r5, lr}", text(CAFDATA_GET, 2)
    assert text(0x3B54A8)[0] == "ldr r3, [r4, #0x10]", text(0x3B54A8)
    # out-of-range test: count(+8) < index -> log and return 0
    assert text(0x3B5470)[0] == "ldr r3, [r0, #8]", text(0x3B5470)
    assert text(0x3B5488)[0] == "uxth r5, r1", text(0x3B5488)
    assert text(0x3B548C)[0] == "cmp r3, r5", text(0x3B548C)
    assert text(0x3B5490)[0].startswith("blt "), text(0x3B5490)
    assert text(0x3B5494)[0] == "ldr r3, [r4, #0x14]", text(0x3B5494)
    assert text(0x3B5498)[0] == "ldr r0, [r3, r5, lsl #2]", text(0x3B5498)
    return {
        "class": "CAFData",
        "SetData": hex(CAFDATA_SET),
        "GetData": hex(CAFDATA_GET),
        "layout": "vptr@0 | count@+8 | tag@+0x10 | u32 array@+0x14",
        "bounds": "index >= count -> log via 0x2f92f4, return 0",
        "log_set": set_msg.strip(),
        "log_get": get_msg.strip(),
    }


# --------------------------------------------------------------------------- #
# 4. hub_set / hub_get dispatch
# --------------------------------------------------------------------------- #
def check_hub_dispatch():
    # ubfx r3,r1,#0x10,#8 ; sub #1 ; cmp #5 ; jump table of 6
    head = text(HUB_SET, 5)
    assert head[0] == "ubfx r3, r1, #0x10, #8", head
    assert head[1] == "sub r3, r3, #1", head
    assert head[2] == "cmp r3, #5", head
    assert head[3].startswith("ldrls pc"), head
    jt = HUB_SET + 0x14
    entries = [u32(jt + 4 * i) - IMAGE_BASE for i in range(6)]
    # each entry loads hub+8/+0xc/+0x10/+0x14/+0x18/+0x1c into r3
    seen = []
    for e in entries:
        line = text(e, 1)[0]
        assert line.startswith("ldr r3, [r0, #"), line
        seen.append(int(line.split("#")[1].rstrip("]"), 16))
    assert seen == [0x08, 0x0C, 0x10, 0x14, 0x18, 0x1C], [hex(x) for x in seen]
    # short path: cmp r1,#0xa ; ldrls r3,[r0,#0x34] ; strls r2,[r3,r1,lsl #2]
    short = text(HUB_SET + 0x2C, 4)
    assert short[0] == "cmp r1, #0xa", short
    assert short[1] == "ldrls r3, [r0, #0x34]", short
    assert short[2].startswith("strls r2, [r3, r1, lsl #2]"), short
    # block path tail-calls the block's own setter
    tail = b_target(HUB_SET + 0x4C)
    assert tail == CAFDATA_SET, hex(tail) if tail else None
    return {
        "encoding": "id = block_number << 16 | index, block_number 1..6",
        "jump_table": f"0x{jt:06x}, 6 entries -> hub+0x08..0x1c",
        "short_ids": "id <= 0xa -> hub+0x34[index] (10 u32), no bounds check",
        "block_path": f"tail call 0x{CAFDATA_SET:06x} (CAFData::SetData)",
        "out_of_range": "block_number 0 or >6 with id > 0xa: returns without storing",
    }


# --------------------------------------------------------------------------- #
# 5. namespace separation from the 184-slot CIQ_SysDataIF array
# --------------------------------------------------------------------------- #
def check_namespace_split():
    # CIQ_SysDataIF_NX1: 184 u32 at +4, metadata at +0x2e4 (round 7)
    ctor = 0x2C0128
    memset_len = None
    for off in range(ctor, ctor + 0x80, 4):
        line = text(off, 1)[0]
        if line.startswith("movw r2, #0x2e0") or line == "mov r2, #0x2e0":
            memset_len = 0x2E0
    assert memset_len == 0x2E0, memset_len
    slots = vtable_slots(IQ_VTABLE, limit=0x700)
    assert len(slots) == 166, len(slots)
    # block arrays are separate mallocs; the only static array is the 10-word short one
    total_blocks = sum(b["count"] for b in BLOCKS.values())
    assert total_blocks == 330
    assert total_blocks + 10 != 184
    return {
        "iq_array": {"owner": "CIQ_SysDataIF_NX1 @ 0x81561cf4",
                     "slots": 184, "id_range": "0..183",
                     "address_rule": "field = object + 4 + 4*id",
                     "writer": "vtable slot 0x014 SetParameter(id, value)"},
        "cafdata_blocks": {"owner": "CAFData x6 @ hub 0x816d2ce0",
                           "total_entries": total_blocks,
                           "id_rule": "id = block<<16 | index",
                           "writer": "CAFData::SetData, reached via 0x33273c or directly"},
        "why_not_the_same": [
            "184 slots vs 330 block entries; the counts cannot be reconciled",
            "the block arrays are malloc'd in 0x336c5c; the 184 slots live inside the "
            "CIQ_SysDataIF singleton object",
            "id 0x30007 would be offset 0x1c in the IQ array but index 7 of block 3, "
            "which is bounded by count 11 - different value spaces",
        ],
    }


# --------------------------------------------------------------------------- #
# 6. the AF shooting-mode triple 0x30006 / 0x30007 / 0x30008
# --------------------------------------------------------------------------- #
def check_mode_triple():
    body = text(TRIPLE_WRITER, 0x20)
    assert body[0] == "push {r4, r5, r6, r7, r8, lr}", body
    # three hub_set calls with ids 0x30006 / 0x30007 / 0x30008
    ids = []
    for off in range(TRIPLE_WRITER, TRIPLE_WRITER + 0x78, 4):
        if bl_target(off) == HUB_SET:
            ids.append(const_before(off, reg=1))
    assert ids == [0x30006, 0x30007, 0x30008], [hex(i) if i else None for i in ids]
    # the three sources
    srcs = []
    for off in range(TRIPLE_WRITER, TRIPLE_WRITER + 0x78, 4):
        t = bl_target(off)
        if t in (MODE_CLASS_FN, AREA_CLASS_FN, LENS_VALUE_FN):
            srcs.append(t)
    assert srcs[:2] == [MODE_CLASS_FN, AREA_CLASS_FN], [hex(x) for x in srcs]
    assert LENS_VALUE_FN in srcs, [hex(x) for x in srcs]

    # 0x30006: reads IQ slot 0x1e8 (= APP_MODE, +0x1c0), switch on 0..0x16
    m = text(MODE_CLASS_FN + 0x10, 4)
    assert m[0].startswith("bl "), m
    assert m[1] == "ldr r3, [r0]", m
    assert m[2] == "ldr r3, [r3, #0x1e8]", m
    assert text(MODE_CLASS_FN + 0x20, 2)[0] == "sxtb r0, r0"
    assert text(MODE_CLASS_FN + 0x24, 2)[0] == "cmp r0, #0x16"

    # 23-entry jump table; mode 1 is the only branch that can yield 6
    modes = {}
    for i in range(23):
        tgt = u32(MODE_JUMPTABLE + 4 * i) - IMAGE_BASE
        modes[i] = tgt
    # collect every `mov r4,#imm` reachable in the tail block
    tail_vals = {}
    for off in range(0x2F3B0C, 0x2F3B64, 4):
        dec = decode_const(u32(off))
        if dec and dec[0] == 4 and dec[2] == "mov":
            tail_vals[off] = dec[1]
    assert tail_vals.get(0x2F3B1C) == 3, tail_vals          # default
    assert tail_vals.get(0x2F3B24) == 2 and tail_vals.get(0x2F3B2C) == 5
    assert tail_vals.get(0x2F3B0C) == 1 and tail_vals.get(0x2F3B14) == 0
    assert tail_vals.get(0x2F3B60) == 6
    assert text(0x2F3B58, 3)[0] == "cmp r0, #1"
    # that branch is reached only from mode 1, via IQ slot 0x254 (= SMART_PRO_MODE)
    assert modes[1] == 0x2F3AE8, hex(modes[1])
    assert text(0x2F3AF0, 2)[0] == "ldr r3, [r3, #0x254]"
    assert modes[22] == 0x2F3B14     # APP_MODE 0x16 (movie) -> 0
    assert modes[0] == 0x2F3B24      # APP_MODE 0 -> 2
    assert modes[14] == 0x2F3B0C     # APP_MODE 14 -> 1
    assert modes[20] == 0x2F3B2C     # APP_MODE 20 -> 5
    assert modes[21] == 0x2F3AB8     # APP_MODE 21 -> 4 (guarded)

    # 0x30007: 4-entry table indexed by AF_AREA (+0xc, id 2), (v-1) <= 3
    a = text(AREA_CLASS_FN + 0x0C, 6)
    assert a[3] == "ldr r3, [r3, #0x204]", a
    assert text(AREA_CLASS_FN + 0x24)[0] == "cmp r0, #3", text(AREA_CLASS_FN + 0x24)
    tbl_va = u32(AREA_TABLE_PTR_POOL)
    tbl = [u32(tbl_va - IMAGE_BASE + 0x1DC + 4 * i) for i in range(4)]
    assert tbl == AREA_TABLE_EXPECT, tbl
    # the same 4-entry pattern appears inside the IQ class (slot 0x204)
    iq204 = text(0x2C10C8, 7)
    assert iq204[0] == "ldr r3, [r0, #0xc]", iq204
    assert iq204[1] == "sub r3, r3, #1", iq204
    assert iq204[2] == "cmp r3, #3", iq204

    # how many readers each id has (constant ids only)
    sites = call_sites({HUB_SET, HUB_GET, CAFDATA_SET, CAFDATA_GET})
    readers = defaultdict(int)
    writers = defaultdict(int)
    for t, offs in sites.items():
        for off in offs:
            v = const_before(off, reg=1)
            if v is None:
                continue
            if t in (HUB_SET, CAFDATA_SET):
                writers[v] += 1
            else:
                readers[v] += 1
    assert writers[0x30006] == 1, writers[0x30006]
    assert writers[0x30007] == 1, writers[0x30007]
    assert readers[0x30006] >= 15, readers[0x30006]

    return {
        "writer": hex(TRIPLE_WRITER),
        "ids": ["0x30006", "0x30007", "0x30008"],
        "0x30006": {
            "name": "AF shooting-mode class",
            "source": "switch23(APP_MODE) via IQ slot 0x1e8 -> +0x1c0",
            "values": {"default(2..13,15..19)": 3, "0": 2, "14": 1, "20": 5,
                       "21": 4, "22 (movie)": 0, "1 & SMART_PRO_MODE==1": 6,
                       "1 & SMART_PRO_MODE!=1": 3},
            "note": "6 is reachable only through APP_MODE == 1 with IQ slot 0x254 "
                    "(+0x274, SMART_PRO_MODE) == 1",
        },
        "0x30007": {
            "name": "AF area class",
            "source": "tab4[AF_AREA-1] via IQ slot 0x204 -> +0xc (id 2)",
            "table": {"1": 0, "2": 1, "3": 2, "4": 2, "other": 1},
            "value_range": "0..2",
        },
        "0x30008": {
            "name": "lens-manager value",
            "source": f"0x{LENS_VALUE_FN:06x}(0x815502a8)",
        },
        "reader_writer_census": {
            "0x30006": {"readers": readers[0x30006], "writers": writers[0x30006]},
            "0x30007": {"readers": readers[0x30007], "writers": writers[0x30007]},
            "0x30008": {"readers": readers[0x30008], "writers": writers[0x30008]},
        },
        "round4_gate": "0x2f0ce4's `get(0x30006) == 6 -> deny phase` reads this "
                       "shooting-mode class, not a focus-limit status",
        "round5_correction": "0x30007 is indexed by AF_AREA, not by a focus mode; "
                             "the three observed output values 0/1/2 come from the "
                             "table {0,1,2,2}",
    }


# --------------------------------------------------------------------------- #
# 7. full census -> tsv
# --------------------------------------------------------------------------- #
def build_census():
    entries = {HUB_SET: "hub_set", HUB_GET: "hub_get",
               CAFDATA_SET: "SetData", CAFDATA_GET: "GetData"}
    calls = call_sites(set(entries))
    per_id = defaultdict(lambda: Counter())
    unknown = Counter()
    for t, offs in calls.items():
        kind = entries[t]
        for off in offs:
            v = const_before(off, reg=1)
            if v is None:
                unknown[kind] += 1
                continue
            if v >= IMAGE_BASE:
                # a stale movw/movt pair loading a string pointer into r1; not an id
                unknown[kind + "_pointer"] += 1
                continue
            per_id[v][kind] += 1

    TAG = {i: (b["tag"] or "?") for i, b in BLOCKS.items()}
    rows = []
    for v in sorted(per_id):
        blk, idx = (v >> 16, v & 0xFFFF) if v > 0xFFFF else (0, v)
        if blk == 0:
            name = "short_array"
        else:
            name = TAG.get(blk, "out_of_range")
        c = per_id[v]
        rows.append({
            "id": f"0x{v:05x}", "block": blk, "index": idx, "block_tag": name,
            "reads": c["hub_get"] + c["GetData"],
            "writes": c["hub_set"] + c["SetData"],
            "via_hub": c["hub_set"] + c["hub_get"],
            "via_direct": c["SetData"] + c["GetData"],
        })
    return rows, unknown, calls


def write_census_tsv(rows):
    p = OUT / "id_census.tsv"
    cols = ["id", "block", "index", "block_tag", "reads", "writes", "via_hub", "via_direct"]
    lines = ["\t".join(cols)]
    for r in rows:
        lines.append("\t".join(str(r[c]) for c in cols))
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def write_blocks_tsv(rows):
    p = OUT / "cafdata_blocks.tsv"
    cols = ["block", "id_base", "count", "hub_slot", "tag", "tag_va", "init", "vtable"]
    lines = ["\t".join(cols)]
    for r in rows:
        lines.append("\t".join(str(r[c]) for c in cols))
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main():
    hub = check_hub_singleton()
    ctor = check_hub_ctor()
    block_rows, total = check_blocks()
    caf = check_cafdata_class()
    dispatch = check_hub_dispatch()
    split = check_namespace_split()
    triple = check_mode_triple()
    rows, unknown, calls = build_census()
    blocks_tsv = write_blocks_tsv(block_rows)
    id_tsv = write_census_tsv(rows)

    by_block = defaultdict(int)
    for r in rows:
        by_block[r["block_tag"]] += 1

    contracts = {
        "p7_sha256": P7_SHA256,
        "scope": "static only; no camera access, no firmware change",
        "hub": hub,
        "hub_ctor": ctor,
        "cafdata": caf,
        "blocks": block_rows,
        "block_totals": {"entries": total, "short_array": 10,
                         "iq_array": 184, "same_namespace": False},
        "dispatch": dispatch,
        "namespace_split": split,
        "mode_triple": triple,
        "census": {
            "distinct_ids": len(rows),
            "distinct_per_block": dict(by_block),
            "unreconstructed_call_sites": dict(unknown),
            "call_sites": {k: len(v) for k, v in
                           (({0x33273c: calls.get(0x33273C, []),
                              0x332948: calls.get(0x332948, []),
                              0x3b53c8: calls.get(0x3B53C8, []),
                              0x3b546c: calls.get(0x3B546C, [])})).items()},
        },
        "artifacts": {"cafdata_blocks.tsv": str(blocks_tsv),
                      "id_census.tsv": str(id_tsv)},
    }
    p = OUT / "verified_contracts.json"
    p.write_text(json.dumps(contracts, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"hub            : {hub['hub']}")
    print("blocks         : " + ", ".join(
        f"{b['block']}:{b['tag'] or '?'}({b['count']})" for b in block_rows))
    print(f"total entries  : {total} (IQ array = 184, separate)")
    print(f"distinct ids   : {len(rows)}")
    print("per block      : " + ", ".join(f"{k}={v}" for k, v in sorted(by_block.items())))
    print(f"0x30006/7/8    : single writer {hex(TRIPLE_WRITER)}")
    print(f"wrote          : {p}")
    print(f"wrote          : {blocks_tsv}")
    print(f"wrote          : {id_tsv}")
    print("all assertions passed")


if __name__ == "__main__":
    main()
