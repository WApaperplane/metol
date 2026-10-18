#!/usr/bin/env python3
"""Offline original-instruction MMIO trace, not a DMA/cache/timing simulation."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct


HERE = Path(__file__).resolve().parent
A2_MD5 = "712c6fd0a49371ec05ce94c367b0d5c7"


def audit(image):
    image = Path(image).resolve()
    digest = hashlib.md5(image.read_bytes()).hexdigest()
    if digest != A2_MD5:
        raise ValueError("expected the verified A2 image")
    spec = importlib.util.spec_from_file_location("lut0_original_instructions",
                                                HERE.parent / "isp" / "3dlut_qemu.py")
    emu_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(emu_module)
    emu_module.P7 = str(image)
    results = []
    for before in (0x100, 0x1100):
        emu = emu_module.P7Emu()
        emu.mu.mem_write(emu_module.REG_BLOCK + 4, struct.pack("<I", before))
        rc, writes, _, stubs, calls = emu.call(0x4A5C44, [0x81115200, 0, 1, 0])
        pc = emu.mu.reg_read(emu_module.UC_ARM_REG_PC)
        if isinstance(rc, str) or pc != (0x7EFFFFFF & ~3):
            raise ValueError(f"emulation did not return: rc={rc}, pc={pc:#x}")
        after = struct.unpack("<I", emu.mu.mem_read(emu_module.REG_BLOCK + 4, 4))[0]
        reg_writes = [{"offset": hex(a - emu_module.REG_BLOCK), "value": hex(v), "bytes": s}
                      for a, s, v in writes]
        load_pulse = any(a == emu_module.REG_BLOCK + 8 and v & 0x100 for a, _, v in writes)
        source = any(a == emu_module.REG_BLOCK + 12 and v == 0x81115200 for a, _, v in writes)
        if not load_pulse or not source or (after >> 4) & 3:
            raise ValueError("expected load source, Load pulse and sel=0")
        results.append({"cfg_before": hex(before), "cfg_after": hex(after),
                        "sel_before": (before >> 4) & 3, "sel_after": (after >> 4) & 3,
                        "return_register": hex(rc), "return_pc": hex(pc),
                        "load_pulse_written": load_pulse, "reg_writes": reg_writes,
                        "stubs_hit": stubs,
                        "watched_calls": [{"offset": hex(off), "name": name,
                                           "args": [hex(a) for a in args]}
                                          for off, name, args in calls]})
    return {"scope": "offline_original_instructions_with_MMIO_memory_and_explicit_stubs",
            "image_md5": digest, "entry": "0x804a5c44", "source": "0x81115200",
            "hardware_consumption_verified": False, "dma_completion_verified": False,
            "still_timing_verified": False, "scenarios": results}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--image", type=Path, required=True)
    ap.add_argument("--json", type=Path, required=True)
    args = ap.parse_args()
    if args.json.resolve() in (args.image.resolve(), Path(__file__).resolve(),
                                HERE.parent / "isp" / "3dlut_qemu.py"):
        ap.error("output must not overwrite an input")
    report = audit(args.image)
    args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for row in report["scenarios"]:
        print(f"PASS cfg={row['cfg_before']}->{row['cfg_after']}, "
              "sel=0->0, Load source and pulse written; hardware DMA not simulated")


if __name__ == "__main__":
    main()
