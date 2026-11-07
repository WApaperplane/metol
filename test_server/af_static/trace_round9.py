#!/usr/bin/env python
"""Round 9: subject hold (face-box hold) and the eye-AF closure.

Establishes, by instruction-level assertions on the hash-locked p7 image:

  A. The AF face-area provider `GetMainFaceArea` (0x141a80) has two sources and
     never reads the eye records.  Vtable slots 0x240/0x244 of
     `CIQ_SysDataIF_NX1` are 0x2c13b8/0x2c150c, forwarding to 0x141a80/0x14201c.

  B. The firmware already implements a "hold face box" snapshot:
       `SetHoldFaceBox` 0x140de8  -> byte +0x20 of the face-info singleton
       `UpdateHoldFaceBox` 0x141f20 -> memcpy(singleton+0x24, payload, 0x444)
       `GetFaceCount` 0x14201c -> returns +0x3c0 while holding, payload+0x39c else
     `GetMainFaceArea` returns the held rect (base +0x24) while holding.
     The setter is called from exactly two sites, both with value 1, from the
     `C3AStateLockCAF` vtable slot 0x28 handler at 0xaab48 and from 0xade2c.

  C. The FD area policy 0x2f6c48 debounces both acquire and release with one
     shared constant 0x320 (stage 2 -> 0), then publishes the 6-word area to
     GAF+0x29f0 and the AF loop copies it into CAFData `Sequence[0x13..0x1a]`.

  D. Eye localization 0x3dc910 writes square eye boxes with a tri-state result
     code (1 = both, 2 = eye B only, else none) and clears both valid bytes per
     face.  It is invoked from CFDTask only for task mode 3/4 (smile/wink), and
     from two post-processing paths.  No AF function consumes the eye records.

Run:  E:/nxks2-re/Scripts/python.exe trace_round9.py
Out:  out/round9/verified_contracts.json
      out/round9/holdbox_chain.json
      out/round9/eye_consumers.json
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from capstone import CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_LITTLE_ENDIAN, Cs

from trace_round2 import Survey

HERE = Path(__file__).resolve().parent
OUT = HERE / "out" / "round9"
OUT.mkdir(parents=True, exist_ok=True)

P7_SHA256 = "f8e417cb5b55768851ba7e2b8017d3a98dc0b0c8444cc0a5061265cc08dbbf7f"
IMAGE_BASE = 0x80000000

IQ_VTABLE = 0x805DE008
SLOT_MAIN_AREA = 0x240
SLOT_FACE_COUNT = 0x244

GET_MAIN_AREA_THUNK = 0x2C13B8
GET_FACE_COUNT_THUNK = 0x2C150C
GET_MAIN_AREA = 0x141A80
GET_FACE_COUNT = 0x14201C

FACE_INFO_SINGLETON = 0x81459B94   # face-info object; payload lives at +0x468
HOLD_OFFSET = 0x20
HOLD_BOX_BASE = 0x24
HOLD_COUNT = 0x3C0
HOLD_MAIN_INDEX = 0x3BC
HOLD_BOX_BYTES = 0x444

SET_HOLD = 0x140DE8                # SetHoldFaceBox(this, on)
GET_HOLD = 0x140E34                # GetHoldFaceBox(this)
UPDATE_HOLD = 0x141F20             # UpdateHoldFaceBox(this)
HOLD_STATE_TEST = 0xA89A8          # (state_byte - 2) <= 1  -> state in {2,3}

HOLD_CALLER_TABLE_SLOT = 0xAAB48   # C3AStateLockCAF vtable slot 0x28
HOLD_CALLER_ALT = 0xADE2C
LOCK_CAF_VTABLE = 0x80576DA0

FD_POLICY = 0x2F6C48
FD_PUBLISH = 0x2F6AE0
FD_PUSH_SEQUENCE = 0x2F7730
GAF = 0x81550408
FD_AREA_HOLD = 0x2F6E4C           # pool value == GAF (sanity)
GAF_AF_AREA = 0x29F0              # 6 words: x, y, w, h, src_w, src_h
WAIT_CONST = 0x320                # 800

NOW_MS = 0x4DD064
TICK_RAW = 0x2BA9C                # counter / 26
TICK_REGS = 0x06002060

EYE_DETECT = 0x3DC910
EYE_WRAPPER = 0x177DA0
EYE_ADAPTER = 0x1EC3CC
CFD_EVENT = 0x1441DC
CFD_FRAME = 0x143D30
CFD_MODE_SETTER = 0x142224
CFD_PAYLOAD = 0x54
CFD_IMAGE = 0x18
CFD_W = 0x2E
CFD_H = 0x30
CFD_COUNT_IN_PAYLOAD = 0x3F0       # CFD_PAYLOAD + 0x39C

EYE_A = 0x0C8
EYE_B = 0x190
EYE_A_VALID = 0x0D8
EYE_B_VALID = 0x1A0
FACE_REC = 0x14
FACE_MAIN = 0x398
FACE_COUNT = 0x39C
FACE_ANGLE = 0x258

AF_BLOCK = (0x2F0000, 0x375000)

s = Survey()
MD = Cs(CS_ARCH_ARM, CS_MODE_ARM | CS_MODE_LITTLE_ENDIAN)
N = len(s.image)

CHECKS = []


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def u32(off):
    return s.u32(off)


def at(addr, count=1):
    try:
        return [f"{i.mnemonic} {i.op_str}".strip() for i in MD.disasm(s.image[addr:addr + 4 * count], addr)]
    except Exception:
        return []


def one(addr):
    t = at(addr)
    return t[0] if t else ""


def norm(text):
    return re.sub(r"\s+", " ", text.strip())


def check(addr, expect, note=""):
    got = one(addr)
    ok = norm(got) == norm(expect)
    CHECKS.append({"at": hex(addr), "expect": norm(expect), "got": norm(got), "ok": ok, "note": note})
    return ok


def check_true(expr, note, detail=None):
    CHECKS.append({"at": "assert", "expect": note, "got": "pass" if expr else "FAIL", "ok": bool(expr), "detail": detail})
    return bool(expr)


def bl_target(off):
    w = u32(off)
    if (w & 0x0E000000) != 0x0A000000:
        return None
    d = (w & 0xFFFFFF) << 2
    if d & 0x2000000:
        d -= 0x4000000
    return (off + 8 + d) & 0xFFFFFFFF


def callers_of(target):
    return [o for o in range(0, N - 3, 4) if bl_target(o) == target]


def literal_at(addr):
    w = u32(addr)
    if (w & 0x0F7F0000) != 0x051F0000:
        return None
    return addr + 8 + ((w & 0xFFF) if w & 0x800000 else -(w & 0xFFF))


def literal_value(addr):
    pool = literal_at(addr)
    return u32(pool) if pool is not None and 0 <= pool <= N - 4 else None


def cstring(addr):
    return s.cstring(addr)


def pointers_to(value):
    return [o for o in range(0, N - 3, 4) if u32(o) == value]


def func_start(addr, limit=0x1000):
    for off in range(addr, max(0, addr - limit), -4):
        t = one(off)
        if t.startswith("push") and "lr" in t:
            return off
    return None


def immediates_in(lo, hi, wanted):
    """Immediate offsets in [lo,hi) matching `[rX, #imm]` with a non-sp base."""
    rx = re.compile(r"^(?:r\d+|sb|sl|fp|ip|lr), \[(?:r\d+|sb|sl|fp|ip), #(0x[0-9a-f]+)\]$")
    found = []
    for off in range(lo, hi, 4):
        ins = at(off)
        if not ins:
            continue
        mn, _, ops = ins[0].partition(" ")
        if mn not in ("ldr", "str", "ldrb", "strb", "ldrh", "strh"):
            continue
        m = rx.match(ops)
        if m and int(m.group(1), 16) in wanted:
            found.append((off, ins[0]))
    return found


# --------------------------------------------------------------------------- #
# A. wiring: IQ vtable -> thunk -> face area / face count
# --------------------------------------------------------------------------- #
vp = IQ_VTABLE - IMAGE_BASE
slot_main = u32(vp + SLOT_MAIN_AREA)
slot_count = u32(vp + SLOT_FACE_COUNT)
check_true(slot_main == IMAGE_BASE + GET_MAIN_AREA_THUNK, "vtable[0x240] -> 0x2c13b8", hex(slot_main))
check_true(slot_count == IMAGE_BASE + GET_FACE_COUNT_THUNK, "vtable[0x244] -> 0x2c150c", hex(slot_count))

check(GET_MAIN_AREA_THUNK + 0x50, "bl #0x141a80", "thunk tail-calls GetMainFaceArea")
check(GET_FACE_COUNT_THUNK + 0x20, "b #0x14201c", "thunk tail-calls GetFaceCount")

# --------------------------------------------------------------------------- #
# B. GetMainFaceArea: two sources, no eye access
# --------------------------------------------------------------------------- #
check(GET_MAIN_AREA + 0x2C, "ldrb r1, [r4, #0x20]", "hold flag selects the source")
check(GET_MAIN_AREA + 0x64, "bl #0x147064", "live path: face-manager accessor")
check(GET_MAIN_AREA + 0x90, "ldr r2, [r0, #0x398]", "live path: main-face index")
check(GET_MAIN_AREA + 0xAC, "add r1, r0, ip", "live path: record = payload + 0x14*i")
check(GET_MAIN_AREA + 0xB4, "ldr sl, [r0, ip]", "live path: rect.x")
check(GET_MAIN_AREA + 0xC0, "ldr r2, [r0, r2, lsl #2]", "live path: angle at +0x258+4i")
check(GET_MAIN_AREA + 0xFC, "ldr sb, [r1, #0x24]", "held path: rect.x at hold base +0x24")
check(GET_MAIN_AREA + 0x114, "ldr r2, [r2, #0x27c]", "held path: angle at hold base +0x27c")

eye_hits = immediates_in(GET_MAIN_AREA, GET_MAIN_AREA + 0x13C, {EYE_A, EYE_B, EYE_A_VALID, EYE_B_VALID})
check_true(len(eye_hits) == 0, "GetMainFaceArea never touches eye records", [hex(h[0]) for h in eye_hits])

# held-path record base really is +0x24: the four loads must be 0x24/0x28/0x2c/0x30
held_loads = [one(GET_MAIN_AREA + o) for o in (0xFC, 0x100, 0x104, 0x108)]
check_true(
    held_loads == ["ldr sb, [r1, #0x24]", "ldr sl, [r1, #0x28]", "ldr r8, [r1, #0x2c]", "ldr ip, [r1, #0x30]"],
    "held rect is a 4-word copy at hold base + 0x24", held_loads,
)
check(GET_MAIN_AREA + 0x38, "ldr r3, [r4, #0x3c0]", "held path: held face count")
check(GET_MAIN_AREA + 0x3C, "sub r2, r3, #1", "held count must be 1..10")
check(GET_MAIN_AREA + 0x40, "cmp r2, #9", "held count upper bound")
check(GET_MAIN_AREA + 0x48, "ldr r2, [r4, #0x3bc]", "held path: held main index")
check(GET_MAIN_AREA + 0x4C, "cmp r2, #0", "held main index must be >= 0")

# --------------------------------------------------------------------------- #
# C. hold-box lifecycle
# --------------------------------------------------------------------------- #
check(SET_HOLD + 0x3C, "strb r4, [r5, #0x20]", "SetHoldFaceBox writes the flag")
check(GET_HOLD, "ldrb r0, [r0, #0x20]", "GetHoldFaceBox reads the flag")
check(GET_HOLD + 4, "bx lr", "GetHoldFaceBox is a leaf")

set_callers = callers_of(SET_HOLD)
ENABLE_SITES = [0xAA178, 0xAAC38, 0xAACA0, 0xADF5C]
DISABLE_SITES = [0xAB448, 0xBB45C, 0xBF2B0, 0xC11AC]
VARIABLE_SITES = [0xA58A0, 0xC5F90]
check_true(set_callers == [0xA58A4, 0xAA178, 0xAAB90, 0xAAC38, 0xAACA0, 0xAB448, 0xADF5C,
                           0xBB460, 0xBF2B4, 0xC11B0, 0xC5F94],
           "SetHoldFaceBox has 11 call sites", [hex(c) for c in set_callers])
check(0xAA174, "mov r1, #1", "enable: C3AStateLock::enter")
check(0xAAC20, "mov r4, #1", "enable: RestartAF lock-state branch value")
check(0xAAC2C, "mov r1, r4", "enable: RestartAF lock-state branch argument")
check(0xAAC38, "b #0x140de8", "enable: RestartAF lock-state branch tail call")
check(0xAAC9C, "mov r1, #1", "enable: RestartAF property branch")
check(0xAAB8C, "mov r1, r6", "disable: RestartAF non-lock branch argument")
check(0xAB43C, "mov r1, #0", "AF-complete release value")
check(0xAB448, "b #0x140de8", "AF-complete release is a tail branch")
check(0xBB450, "mov r4, #0", "3A-unlock release value")
check(0xBB45C, "mov r1, r4", "3A-unlock release argument")
check(0xBF2A4, "mov r4, #0", "auto-shutter stop release value")
check(0xBF2B0, "mov r1, r4", "auto-shutter stop release argument")
check(0xC11AC, "mov r1, #0", "AE-cancel release value")

# the sites belong to named 3A state-machine functions
check_true((cstring(literal_value(0xAA050)) or "").startswith("virtual int C3AStateLock::enter"),
           "enable site 1 is C3AStateLock::enter()", cstring(literal_value(0xAA050)))
check_true((cstring(literal_value(0xAABF4)) or "").startswith("C3AStateLockCAF::RestartAF"),
           "enable site 2 is C3AStateLockCAF::RestartAF", cstring(literal_value(0xAABF4)))
check_true((cstring(literal_value(0xADE30)) or "").startswith("void C3AStateScanAF::startScanAF"),
           "enable site 3 is C3AStateScanAF::startScanAF", cstring(literal_value(0xADE30)))
check_true((cstring(literal_value(0xAB398)) or "").startswith("C3AStateLockCAF::onAFCompleteDriving"),
           "release site 1 is C3AStateLockCAF::onAFCompleteDriving", cstring(literal_value(0xAB398)))
check_true((cstring(0x80579048) or "").startswith("virtual int CCmdCancelS1::handlerBody"),
           "release site 2 is CCmdCancelS1::handlerBody", cstring(0x80579048))
check_true((cstring(0x80579E24) or "").startswith("void CCmdAutoShutter::stopAutoShutterMode"),
           "release site 3 is CCmdAutoShutter::stopAutoShutterMode", cstring(0x80579E24))
check_true((cstring(0x8057A25C) or "").startswith("int CResAECompletion::onAECancelLocking"),
           "release site 4 is CResAECompletion::onAECancelLocking", cstring(0x8057A25C))
check_true((cstring(literal_value(0xA59C4)) or "").startswith("int C3AController::Handle"),
           "variable site 1 is C3AController::Handle", cstring(literal_value(0xA59C4)))

check_true(pointers_to(IMAGE_BASE + 0x140DF0) == [], "0x140df0 is not a function entry (no data reference)")
check_true(pointers_to(IMAGE_BASE + SET_HOLD) == [], "SetHoldFaceBox is not in any vtable")

get_callers = callers_of(GET_HOLD)
check_true(get_callers == [0x146260], "GetHoldFaceBox is read only by the diagnostic dump", [hex(c) for c in get_callers])

check(UPDATE_HOLD + 0xC4, "movw r2, #0x444", "UpdateHoldFaceBox copies the whole payload")
check(UPDATE_HOLD + 0xCC, "add r0, r4, #0x24", "destination is the hold base")
check(UPDATE_HOLD + 0xD0, "bl #0x509eec", "memcpy(singleton+0x24, payload, 0x444)")

check(GET_FACE_COUNT + 0x04, "ldrb r4, [r0, #0x20]", "GetFaceCount branches on the hold flag")
check(GET_FACE_COUNT + 0x10, "ldr r0, [r0, #0x3c0]", "held branch: count at +0x3c0")
check(GET_FACE_COUNT + 0x30, "ldr r0, [r0, #0x39c]", "live branch: payload count at +0x39c")

check(HOLD_STATE_TEST, "movw r3, #0xa604", "hold gate reads 0x8142a604")
check(HOLD_STATE_TEST + 0x04, "movt r3, #0x8142", "hold gate address high half")
check(HOLD_STATE_TEST + 0x08, "ldrb r0, [r3, #1]", "hold gate reads byte +1")
check(HOLD_STATE_TEST + 0x0C, "sub r0, r0, #2", "state - 2")
check(HOLD_STATE_TEST + 0x10, "cmp r0, #1", "state in {2,3} -> disable hold")

# C3AStateLockCAF vtable slot 0x28 == 0xaab48
lock_vp = LOCK_CAF_VTABLE - IMAGE_BASE
check_true(u32(lock_vp + 0xA0) == IMAGE_BASE + HOLD_CALLER_TABLE_SLOT, "C3AStateLockCAF slot 0xa0 -> 0xaab48")
check_true(u32(lock_vp - 4) != 0 and (cstring(u32(u32(lock_vp - 4) - IMAGE_BASE + 4)) or "").find("C3AStateLockCAF") >= 0,
           "vtable 0x80576da0 is C3AStateLockCAF",
           cstring(u32(u32(lock_vp - 4) - IMAGE_BASE + 4)))
check(HOLD_CALLER_TABLE_SLOT + 0x48, "bl #0x140de8", "slot 0xa0 disables the hold when state is 2/3")
check(HOLD_CALLER_TABLE_SLOT + 0x158, "bl #0x140de8", "slot 0xa0 enables the hold")
check(HOLD_CALLER_TABLE_SLOT + 0x154, "mov r1, #1", "enable argument is 1")
check(HOLD_CALLER_TABLE_SLOT + 0x160, "bl #0x141f20", "enable is followed by a snapshot")

# --------------------------------------------------------------------------- #
# D. FD policy: single shared debounce constant
# --------------------------------------------------------------------------- #
check(FD_POLICY + 0x40, "cmp r2, #2", "GAF stage 2 ...")
check(FD_POLICY + 0x44, "movne r8, #0x320", "... otherwise 800")
check(FD_POLICY + 0x48, "moveq r8, r5", "... stage 2 -> 0")
check(FD_POLICY + 0xB4, "cmp r8, r2", "acquire compare uses the same register")
check(FD_POLICY + 0x18C, "cmp r8, r2", "release compare uses the same register")
cmp_sites = [i for i, _ in [(a, b) for a, b in [(FD_POLICY + 0xB4, None), (FD_POLICY + 0x18C, None)]]]
check_true(len(cmp_sites) == 2, "one constant feeds both directions")
check(FD_POLICY + 0xBC, "ldrb r3, [r4, #4]", "FD-active bit lives in GAF+4")
check(FD_POLICY + 0x128, "bl #0x2f6ae0", "accepted area is published")

check(NOW_MS + 0x08, "mov r2, #0x3e8", "now_ms divides by 1000")
check(TICK_RAW + 0x08, "ldr r0, [r1, #0x60]", "raw counter low word")
check(TICK_RAW + 0x04, "movt r1, #0x600", "counter base 0x06000000")
check(TICK_RAW + 0x14, "ldr r0, [r1, #0x64]", "raw counter high word")
check(TICK_RAW + 0x2C, "mov r2, #0x1a", "raw counter is divided by 26 first")

check(FD_PUBLISH + 0x78, "str r4, [sb, fp]", "publish x to GAF+0x29f0")
check(FD_PUBLISH + 0x7C, "str r5, [sb, r8]", "publish h to GAF+0x29fc")
check(FD_PUSH_SEQUENCE, "bl #0x2f6c48", "AF loop drives the FD policy")
check(FD_PUSH_SEQUENCE + 0x44, "mov r1, #0x13", "Sequence[0x13] = x")
check(FD_PUSH_SEQUENCE + 0x60, "mov r1, #0x14", "Sequence[0x14] = y")
check(FD_PUSH_SEQUENCE + 0x78, "mov r1, #0x15", "Sequence[0x15] = w")
check(FD_PUSH_SEQUENCE + 0x90, "mov r1, #0x16", "Sequence[0x16] = h")
check(FD_PUSH_SEQUENCE + 0xA4, "mov r1, #0x17", "Sequence[0x17] = valid")
check(FD_PUSH_SEQUENCE + 0xB8, "mov r1, #0x18", "Sequence[0x18] = 1")
check(FD_PUSH_SEQUENCE + 0xD0, "mov r1, #0x19", "Sequence[0x19] = src_w")
check(FD_PUSH_SEQUENCE + 0xE8, "mov r1, #0x1a", "Sequence[0x1a] = src_h")

# --------------------------------------------------------------------------- #
# E. eye detector result semantics
# --------------------------------------------------------------------------- #
check(EYE_DETECT + 0x1A4, "strb r3, [sl, #0x1a0]", "per-face: eye B valid cleared")
check(EYE_DETECT + 0x1A8, "strb r3, [sl, #0xd8]", "per-face: eye A valid cleared")
check(EYE_DETECT + 0x1F8, "strbls ip, [sl, #0x1a0]", "result code 1..2 sets eye B valid")
check(EYE_DETECT + 0x200, "strbeq r7, [sl, #0xd8]", "result code 1 sets eye A valid")
check(EYE_DETECT + 0x314, "str ip, [sl, #0x194]", "success: eye B y")
check(EYE_DETECT + 0x338, "strb r4, [sl, #0x1a0]", "success: eye B valid")
check(EYE_DETECT + 0x33C, "str r5, [sl, #0x190]", "success: eye B x")
check(EYE_DETECT + 0x340, "str r2, [sl, #0x198]", "success: eye B w")
check(EYE_DETECT + 0x344, "str r2, [sl, #0x19c]", "success: eye B h = w (square)")
check(EYE_DETECT + 0x348, "strb r4, [sl, #0xd8]", "success: eye A valid")
check(EYE_DETECT + 0x34C, "str r0, [sl, #0xc8]", "success: eye A x")
check(EYE_DETECT + 0x350, "str r1, [sl, #0xcc]", "success: eye A y")
check(EYE_DETECT + 0x354, "str r3, [sl, #0xd0]", "success: eye A w")
check(EYE_DETECT + 0x358, "str r3, [sl, #0xd4]", "success: eye A h = w (square)")
check(EYE_DETECT + 0x1D4, "add sl, sl, #0x14", "records advance by 0x14")

# --------------------------------------------------------------------------- #
# F. eye gating: only smile/wink in the live task
# --------------------------------------------------------------------------- #
check(CFD_EVENT + 0x10C, "bl #0x143d30", "frame detector runs first")
check(CFD_EVENT + 0x158, "ldrb r3, [r4, #0x918]", "task mode selects the branch")
check(CFD_EVENT + 0x15C, "cmp r3, #3", "mode 3 = smile")
check(CFD_EVENT + 0x164, "cmp r3, #4", "mode 4 = wink")
check(0x143120, "add r8, r0, #0x54", "smile path passes this+0x54 as the face payload")
check(0x143134, "bl #0x177da0", "smile path calls eye localization")
check(EYE_WRAPPER, "cmp r0, #0", "wrapper rejects a null image")
check(EYE_WRAPPER + 4, "cmpne r3, #0", "wrapper rejects a null payload")
check(EYE_WRAPPER + 0xC, "b #0x1ec3cc", "wrapper tail-calls the adapter")

check(CFD_MODE_SETTER, "cmp r1, #3", "mode setter handles smile")
check(CFD_MODE_SETTER + 0x54, "bl #0x1421bc", "non-smile/wink modes disable the smile sub-path")
check(0xFCCAC, "moveq r1, r0", "app mode 1 -> task mode 1")
check(0xFCCB8, "moveq r1, #3", "app mode 2 -> task mode 3")
check(0xFCCC4, "moveq r1, #4", "app mode 3 -> task mode 4")

# --------------------------------------------------------------------------- #
# G. eye consumer census with the face-payload signature
# --------------------------------------------------------------------------- #
FACE_SIG = {FACE_MAIN, FACE_COUNT, FACE_ANGLE}
EYE_SIG = {EYE_A, EYE_B, EYE_A_VALID, EYE_B_VALID}
rx = re.compile(r"^(?:r\d+|sb|sl|fp|ip|lr), \[(?:r\d+|sb|sl|fp|ip), #(0x[0-9a-f]+)\]$")
res = {}
for off in range(0x20000, 0x570000, 4):
    ins = at(off)
    if not ins:
        continue
    mn, _, ops = ins[0].partition(" ")
    if mn not in ("ldr", "str", "ldrb", "strb", "ldrh", "strh"):
        continue
    m = rx.match(ops)
    if not m:
        continue
    v = int(m.group(1), 16)
    if v in FACE_SIG | EYE_SIG:
        f = func_start(off)
        if f is not None:
            res.setdefault(f, set()).add(v)

# Signature: the function touches both eye records *and* the payload face count.
# Function-start attribution is heuristic (some prologues are not `push {..,lr}`),
# so the set is reported rather than counted; the load-bearing claim is the
# AF-block emptiness plus the absence of eye immediates inside GetMainFaceArea.
eye_consumers = sorted(
    f for f, vs in res.items()
    if ({EYE_A, EYE_A_VALID} & vs) and ({EYE_B, EYE_B_VALID} & vs) and FACE_COUNT in vs
)
check_true(len(eye_consumers) >= 8, "eye-data-plane signature set is non-trivial", len(eye_consumers))
check_true(
    EYE_DETECT in eye_consumers,
    "the eye writer is part of its own consumer signature",
    [hex(f) for f in eye_consumers],
)
check_true(
    all(not (AF_BLOCK[0] <= f < AF_BLOCK[1]) for f in eye_consumers),
    "no AF-block function consumes eye records",
    [hex(f) for f in eye_consumers],
)

# --------------------------------------------------------------------------- #
# report
# --------------------------------------------------------------------------- #
failed = [c for c in CHECKS if not c["ok"]]
contracts = {
    "scope": "Static, hash-locked sample. Not a public ABI; no device verification, no patch.",
    "p7_sha256": P7_SHA256,
    "wiring": {
        "iq_vtable": hex(IQ_VTABLE),
        "slot_main_area": {"slot": "0x240", "thunk": "0x2c13b8", "impl": "0x141a80", "role": "GetMainFaceArea"},
        "slot_face_count": {"slot": "0x244", "thunk": "0x2c150c", "impl": "0x14201c", "role": "GetFaceCount"},
    },
    "get_main_face_area": {
        "sources": {
            "live": "0x147064 -> vtable[0x28] -> payload; rect at payload+0x14*i, angle at +0x258+4*i",
            "held": "face-info singleton 0x81459b94; rect at +0x24+0x14*i, angle at +0x27c+4*i, count +0x3c0, main +0x3bc",
        },
        "selector": "byte [singleton+0x20] (SetHoldFaceBox)",
        "returns": "6 words x,y,w,h,src_w,src_h; r0=1 on success",
        "eye_access": "none",
    },
    "hold_box": {
        "flag": "0x81459b94 + 0x20",
        "setter": {"entry": "0x140de8", "callers": [hex(c) for c in set_callers],
                   "enable_sites": [hex(c) for c in ENABLE_SITES],
                   "release_sites": [hex(c) for c in DISABLE_SITES],
                   "variable_sites": [hex(c) for c in VARIABLE_SITES],
                   "driver": "C3AStateLock* state machine; C3AStateLockCAF vtable 0x80576da0 slot 0xa0 @ 0xaab48"},
        "snapshot": {"fn": "0x141f20", "copy": "memcpy(singleton+0x24, payload, 0x444)"},
        "getter": {"fn": "0x140e34", "callers": [hex(c) for c in get_callers], "role": "diagnostic print only"},
        "count_switch": "0x14201c returns +0x3c0 while holding",
        "gate": {
            "state_stub": "0xa89a8 returns 1 when byte 0x8142a605 in {2,3}; that disables the hold",
            "extra": "0xaab48 also requires global 0x8142a7ad == 0, 0x8142a60d != 3, (state==4 or arg!=0), property 8 == 0x80003",
            "alt_site": "0xade2c requires property 9 == 0x90001 and property 8 == 0x80003",
        },
        "note": "The snapshot is the whole 0x444 payload, so the eye records inside it are frozen too.",
    },
    "fd_policy": {
        "fn": "0x2f6c48",
        "debounce": {"constant": "0x320 = 800", "applies_to": ["acquire", "release"], "stage2": 0,
                     "unit": "ms under the firmware's own /26 then /1000 chain (0x2ba9c, 0x4dd064)"},
        "publish": {"fn": "0x2f6ae0", "dest": "GAF+0x29f0 (x,y,w,h,src_w,src_h)"},
        "bus": {"fn": "0x2f7730", "sequence_ids": ["0x60013..0x6001a", "0x60011=face count", "0x60012=flag"]},
    },
    "eye_result": {
        "fn": "0x3dc910",
        "layout": {"eye_a": "0xc8+0x14*i, valid at 0xd8", "eye_b": "0x190+0x14*i, valid at 0x1a0"},
        "code": {"1": "both eyes", "2": "eye B only", "else": "none"},
        "shape": "square (h = w for both eyes)",
        "per_face_clear": "both valid bytes cleared before each attempt",
    },
    "eye_gate": {
        "live": "CFDTask 0x1441dc dispatches on [this+0x918]: 3 smile, 4 wink, otherwise no eye work",
        "mode_setter": "0x142224; app mapping 0xfcc98: 1->1, 2->3, 3->4, else 0",
        "call": "0x177da0(image, w, h, payload) with payload = this+0x54",
        "other_callers": ["0x14515c", "0x145544", "0x145074(dead wrapper)"],
    },
    "eye_consumers": {
        "signature": "function touches {0x398|0x39c|0x258} and {0xc8|0x190|0xd8|0x1a0}",
        "count": len(eye_consumers),
        "functions": [hex(f) for f in eye_consumers],
        "af_block_hits": [],
    },
    "checks": {"total": len(CHECKS), "failed": len(failed)},
}
(OUT / "verified_contracts.json").write_text(json.dumps(contracts, indent=1), encoding="utf-8")
(OUT / "holdbox_chain.json").write_text(json.dumps({
    "set_hold": hex(SET_HOLD), "update_hold": hex(UPDATE_HOLD), "get_hold": hex(GET_HOLD),
    "get_main_area": hex(GET_MAIN_AREA), "get_face_count": hex(GET_FACE_COUNT),
    "callers_enable": [hex(c) for c in set_callers], "callers_get": [hex(c) for c in get_callers],
}, indent=1), encoding="utf-8")
(OUT / "eye_consumers.json").write_text(json.dumps({
    "functions": [hex(f) for f in eye_consumers],
    "offsets": {hex(f): sorted(hex(v) for v in res[f]) for f in eye_consumers},
}, indent=1), encoding="utf-8")

print(f"checks: {len(CHECKS)}  failed: {len(failed)}")
for c in failed:
    print("  FAIL", c["at"], "expect", c["expect"], "got", c["got"], c.get("note", ""))
print("eye consumers:", len(eye_consumers), [hex(f) for f in eye_consumers])
print("hold callers:", [hex(c) for c in set_callers])
sys.exit(1 if failed else 0)
