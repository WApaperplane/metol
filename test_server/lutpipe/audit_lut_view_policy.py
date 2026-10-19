#!/usr/bin/env python3
"""Execute verified P7 policy instructions offline; no camera access.

Only DataManager reads are stubbed. The policy, getter, sender's bit mapping,
and final View4 selector execute original ARM instructions from the A2 image.
The sender is entered after its getter call with its two constructor-zeroed
flag bytes; no frame/DMA or complete backend lifecycle is simulated.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import (
    UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_PC,
    UC_ARM_REG_LR, UC_ARM_REG_SP,
)

IMAGE_MD5 = "712c6fd0a49371ec05ce94c367b0d5c7"
BASE, RAM, OBJ, STACK, STOP = 0x80000000, 0x90000000, 0x90001000, 0x90080000, 0x900FF000


def one(image, oled, adobe, mode, smart_filter=0):
    uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    uc.mem_map(BASE, (len(image) + 4095) & ~4095)
    uc.mem_write(BASE, image)
    uc.mem_map(RAM, 0x100000)
    uc.mem_write(OBJ + 0x2C, bytes([mode]))
    uc.mem_write(OBJ + 0x54, struct.pack("<I", 0))
    values = {0x6C: 0x6C0000 + oled, 0x32: 0x320000 + adobe,
              0x3E: 0x3E0000 + smart_filter}
    reads = []

    def hook(machine, address, size, _):
        if address == 0x80072128:
            machine.reg_write(UC_ARM_REG_R0, RAM + 0x4000)
            machine.reg_write(UC_ARM_REG_PC, machine.reg_read(UC_ARM_REG_LR))
        elif address == 0x80071EB4:
            key = machine.reg_read(UC_ARM_REG_R1)
            reads.append(key)
            machine.reg_write(UC_ARM_REG_R0, values[key])
            machine.reg_write(UC_ARM_REG_PC, machine.reg_read(UC_ARM_REG_LR))

    uc.hook_add(UC_HOOK_CODE, hook)
    uc.reg_write(UC_ARM_REG_SP, STACK)
    uc.reg_write(UC_ARM_REG_LR, STOP)
    uc.reg_write(UC_ARM_REG_R0, OBJ)
    uc.emu_start(0x800E9FF4, STOP, count=1000)
    if uc.reg_read(UC_ARM_REG_PC) != STOP:
        raise RuntimeError("policy failed to return")
    selection = struct.unpack("<I", uc.mem_read(OBJ + 0x54, 4))[0]
    uc.reg_write(UC_ARM_REG_LR, STOP)
    uc.reg_write(UC_ARM_REG_R0, OBJ)
    uc.emu_start(0x800E8524, STOP, count=10)
    if uc.reg_read(UC_ARM_REG_R0) != selection:
        raise AssertionError("getter mismatch")
    result = {"oled": oled, "adobe": adobe, "mode_byte": mode,
              "smart_filter": smart_filter, "userdata_reads": reads,
              "order_sheet_54": selection}
    if smart_filter != 0:
        result["view"] = "not evaluated: smart filters may use the dynamic path"
        return result

    # Original sender branch; SP+0x29/0x2a == parameter +0x21/+0x22.
    uc.mem_write(STACK + 0x29, b"\0\0")
    uc.reg_write(UC_ARM_REG_SP, STACK)
    uc.reg_write(UC_ARM_REG_R0, selection)
    uc.emu_start(0x801B3E08, 0x801B3E30, count=50)
    if uc.reg_read(UC_ARM_REG_PC) != 0x801B3E30:
        raise RuntimeError("sender branch failed to reach endpoint")
    c, d = uc.mem_read(STACK + 0x29, 2)
    uc.reg_write(UC_ARM_REG_R1, d)
    uc.reg_write(UC_ARM_REG_R2, c)
    uc.reg_write(UC_ARM_REG_LR, STOP)
    uc.emu_start(0x803837D0, STOP, count=20)
    slot = uc.reg_read(UC_ARM_REG_R0)
    slots = struct.unpack_from("<4I", image, 0x3837F0)
    result.update({"param_21": c, "param_22": d,
                   "view_index": slots.index(slot), "native_slot": hex(slot)})
    expected = (2 if adobe else 0) + (1 if oled and mode != 14 else 0)
    if selection != expected:
        raise AssertionError((result, expected))
    if result["view_index"] != {0: 3, 1: 1, 2: 2, 3: 0}[expected]:
        raise AssertionError(result)
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--image", type=Path, default=Path("E:/NXWA/fw/v1.12/a2/p7_a2.bin"))
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    image = args.image.read_bytes()
    if hashlib.md5(image).hexdigest() != IMAGE_MD5:
        ap.error("unexpected image")
    cases = []
    for mode in (0, 14):
        for adobe in (0, 1):
            for oled in (0, 1):
                case = one(image, oled, adobe, mode)
                cases.append(case)
                print(f"mode={mode} Adobe={adobe} OLED={oled}: "
                      f"order={case['order_sheet_54']} "
                      f"View4[{case['view_index']}]={case['native_slot']}")
    for sf in range(14, 19):
        case = one(image, 1, 0, 0, sf)
        if case["order_sheet_54"] != sf - 10:
            raise AssertionError(case)
        cases.append(case)
    report = {"image_md5": IMAGE_MD5, "mode": "offline original ARM execution",
              "stubbed": ["DataManager singleton", "DataManager getusr"],
              "limitations": ["not a camera capture", "no DMA or image simulation",
                              "sender constructor state is a fixture"],
              "passed": len(cases), "cases": cases}
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("PASS:", len(cases), "original-instruction cases")


if __name__ == "__main__":
    raise SystemExit(main())
