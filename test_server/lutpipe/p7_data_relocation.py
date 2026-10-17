#!/usr/bin/env python3
"""Offline audit of P7 initialized-data relocation and saved LUT memory dumps.

No camera access, device mapping, firmware writes, or register writes.
--emulate executes the original 0x80011620..0x80011640 copy loop and
0x803837D0 static View selector leaf. It does not emulate full boot,
DMA, cache coherence, or image processing.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path

BASE = 0x80000000
COPY_START = 0x11620
COPY_STOP = 0x11640
COPY_LITERALS = 0x11760
SLOT_SIZE = 0x4D00
TABLE_SIZE = 17 ** 3 * 4
# Exact ARM instructions: three PC-relative loads, prefetch, 64-byte VFP
# load/store, compare and backward branch. Reject an unrecognized loop.
COPY_WORDS = (
    0xE59F1138, 0xE59F2138, 0xE59F3138, 0xF5D1F0C0,
    0xECB10B10, 0xECA20B10, 0xE1520003, 0x3AFFFFFA,
)
POOLS = {
    "std": 0x810FD100,
    "mono": 0x81101E00,
    "cine": 0x81106B00,
    "skin": 0x81115200,
}


def digest(data):
    return {"bytes": len(data), "md5": hashlib.md5(data).hexdigest(),
            "sha256": hashlib.sha256(data).hexdigest()}


def relocation(image):
    if len(image) < COPY_LITERALS + 12:
        raise ValueError("image is too short for the copy loop and its literals")
    words = struct.unpack_from("<8I", image, COPY_START)
    if words != COPY_WORDS:
        raise ValueError("unrecognized initialized-data copy instructions")
    source, destination, end = struct.unpack_from("<3I", image, COPY_LITERALS)
    size = end - destination
    source_offset = source - BASE
    if (source_offset < 0 or size <= 0 or size % 64
            or source_offset + size > len(image)
            or source + size > destination or end > 0x100000000
            or source % 64 or destination % 64):
        raise ValueError("invalid, overlapping, truncated or unaligned copy range")
    delta = destination - source
    slots = []
    for block, start, count in (("A", 0x8592C0, 20), ("B", 0x8B9AC0, 22)):
        for i in range(count):
            offset = start + i * SLOT_SIZE
            runtime = BASE + offset + delta
            slots.append({"slot": f"{block}{i:02d}", "file_offset": offset,
                          "runtime": runtime,
                          "inside_copy": (source_offset <= offset
                                          and offset + SLOT_SIZE <= source_offset + size)})
    pointer_tables = []
    for name, offset, count in (("view_static", 0x3837F0, 4),
                                ("still_static", 0x382C5C, 6),
                                ("bv", 0x382B00, 12)):
        entries = []
        for index, runtime in enumerate(struct.unpack_from(f"<{count}I", image, offset)):
            matches = [slot["slot"] for slot in slots if slot["runtime"] == runtime]
            entries.append({"index": index, "runtime": runtime,
                            "source_file_offset": runtime - delta - BASE,
                            "static_slots": matches})
        pointer_tables.append({"name": name, "address": BASE + offset,
                               "entries": entries})
    return {"source": source, "source_offset": source_offset,
            "destination": destination, "end_exclusive": end,
            "size": size, "delta": delta, "slots": slots,
            "consumer_pointer_tables": pointer_tables,
            "copy_code": [{"address": BASE + COPY_START + i * 4,
                           "word": word} for i, word in enumerate(words)]}


def differences(before, after):
    if len(before) != len(after):
        raise ValueError("cannot compare unequal byte ranges")
    changed = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
    return {"bytes_changed": len(changed),
            "first_offset": changed[0] if changed else None,
            "last_offset": changed[-1] if changed else None}


def audit_dump(image, layout, data, address):
    if (not data or address < layout["destination"]
            or address + len(data) > layout["end_exclusive"]):
        raise ValueError("empty dump or dump outside the initialized-data range")
    offset = address - layout["delta"] - BASE
    expected = image[offset:offset + len(data)]
    comparison = differences(expected, data)
    result = {"address": address, "expected_file_offset": offset,
              **digest(data), **comparison,
              "exact_image_match": comparison["bytes_changed"] == 0, "pools": {}}
    for name, runtime in POOLS.items():
        start = runtime - address
        if start < 0 or start + SLOT_SIZE > len(data):
            result["pools"][name] = {"complete": False, "runtime": runtime}
            continue
        actual = data[start:start + SLOT_SIZE]
        source_offset = runtime - layout["delta"] - BASE
        original = image[source_offset:source_offset + SLOT_SIZE]
        result["pools"][name] = {
            "complete": True, "runtime": runtime,
            "expected_file_offset": source_offset,
            **digest(actual), **differences(original, actual),
            "padding_byte_nonzero_count": sum(v != 0 for v in actual[3:TABLE_SIZE:4]),
            "matching_static_slots": [slot["slot"] for slot in layout["slots"]
                                      if actual == image[slot["file_offset"]:
                                                         slot["file_offset"] + SLOT_SIZE]],
        }
    return result


def emulate_copy(image, layout):
    from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM
    from unicorn.arm_const import (UC_ARM_REG_C1_C0_2, UC_ARM_REG_FPEXC,
                                   UC_ARM_REG_PC, UC_ARM_REG_R0, UC_ARM_REG_R1,
                                   UC_ARM_REG_R2, UC_ARM_REG_LR)
    # The original loop has no external calls and no MMIO access. Map RAM only.
    if layout["end_exclusive"] > BASE + 0x2000000 or len(image) > 0x2000000:
        raise ValueError("copy exceeds the bounded emulation RAM window")
    uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    uc.mem_map(BASE, 0x2000000)
    uc.mem_write(BASE, image)
    uc.reg_write(UC_ARM_REG_C1_C0_2, 0xF00000)
    uc.reg_write(UC_ARM_REG_FPEXC, 0x40000000)
    uc.emu_start(BASE + COPY_START, BASE + COPY_STOP,
                 count=3 + (layout["size"] // 64) * 5 + 1, timeout=10_000_000)
    actual = bytes(uc.mem_read(layout["destination"], layout["size"]))
    expected = image[layout["source_offset"]:
                     layout["source_offset"] + layout["size"]]
    pc = uc.reg_read(UC_ARM_REG_PC)
    source_end = uc.reg_read(UC_ARM_REG_R1)
    destination_end = uc.reg_read(UC_ARM_REG_R2)
    # Execute the static View selector leaf itself, not singleton constructors
    # or conditional/dynamic selectors. This checks the four leaf outcomes only.
    selections = []
    for first, second, name in ((0, 0, "skin"), (1, 0, "cine"),
                                (0, 1, "mono"), (1, 1, "std")):
        uc.reg_write(UC_ARM_REG_R0, 0)
        uc.reg_write(UC_ARM_REG_R1, first)
        uc.reg_write(UC_ARM_REG_R2, second)
        uc.reg_write(UC_ARM_REG_LR, BASE + COPY_STOP)
        uc.emu_start(BASE + 0x3837D0, BASE + COPY_STOP, count=20)
        selected = uc.reg_read(UC_ARM_REG_R0)
        passed = selected == POOLS[name] and uc.reg_read(UC_ARM_REG_PC) == BASE + COPY_STOP
        selections.append({"r1": first, "r2": second, "pool": name,
                           "address": selected, "pass": passed,
                           "copied_table": digest(bytes(uc.mem_read(selected, SLOT_SIZE)))
                           if passed else None})
    return {"pass": pc == BASE + COPY_STOP and actual == expected
                    and all(s["pass"] for s in selections),
            "pc": pc, "source_end": source_end,
            "destination_end": destination_end,
            "copied": digest(actual), "stubs": [], "mmio_mapped": False,
            "static_view_selector": {"address": BASE + 0x3837D0,
                                     "selections": selections},
            "scope": "copy loop and static selector only; not full boot, cache, DMA or rendered effect"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--dump", type=Path, action="append", default=[])
    parser.add_argument("--dump-base", type=lambda x: int(x, 0), default=0x810F0000)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--emulate", action="store_true", help="requires unicorn")
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    image = args.image.read_bytes()
    layout = relocation(image)
    result = {"image": {"path": str(args.image.resolve()), **digest(image)},
              "relocation": layout, "dumps": [],
              "hardware_consumption_verified": False}
    if args.emulate:
        result["emulation"] = emulate_copy(image, layout)
        if not result["emulation"]["pass"]:
            raise ValueError("base copy emulation failed")
    for path in args.dump:
        result["dumps"].append({"path": str(path.resolve()),
                                **audit_dump(image, layout, path.read_bytes(), args.dump_base)})
    if args.candidate:
        candidate = args.candidate.read_bytes()
        candidate_layout = relocation(candidate)
        if candidate_layout != layout:
            raise ValueError("candidate changes relocation layout or instructions")
        change = differences(image, candidate)
        slot = next(s for s in layout["slots"] if s["slot"] == "A12")
        start = slot["file_offset"]
        only_a12 = (candidate[:start] == image[:start]
                    and candidate[start + SLOT_SIZE:] == image[start + SLOT_SIZE:])
        changed_slots = []
        covered_bytes = 0
        for item in layout["slots"]:
            offset = item["file_offset"]
            old_slot = image[offset:offset + SLOT_SIZE]
            new_slot = candidate[offset:offset + SLOT_SIZE]
            if old_slot != new_slot:
                slot_change = differences(old_slot, new_slot)
                covered_bytes += slot_change["bytes_changed"]
                changed_slots.append({**item, **slot_change, "new": digest(new_slot),
                                      "original": digest(old_slot)})
        result["candidate"] = {"path": str(args.candidate.resolve()),
                                **digest(candidate), **change,
                                "changes_confined_to_a12": only_a12,
                                "changed_slots": changed_slots,
                                "changes_confined_to_known_slots": covered_bytes == change["bytes_changed"],
                                "a12_runtime": slot["runtime"],
                                "a12": digest(candidate[start:start + SLOT_SIZE])}
        if args.emulate:
            result["candidate"]["emulation"] = emulate_copy(candidate, layout)
            if not result["candidate"]["emulation"]["pass"]:
                raise ValueError("candidate copy emulation failed")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"COPY 0x{layout['source']:08X} -> 0x{layout['destination']:08X} "
          f"size=0x{layout['size']:X} delta=0x{layout['delta']:X}")
    for item in result["dumps"]:
        print(f"{Path(item['path']).name}: {item['bytes']} bytes; "
              f"diff={item['bytes_changed']}")
    if "candidate" in result:
        print(f"candidate: diff={result['candidate']['bytes_changed']}; "
              f"slots={','.join(s['slot'] for s in result['candidate']['changed_slots'])}; "
              f"known slots only={result['candidate']['changes_confined_to_known_slots']}")
    if args.emulate:
        print("copy-loop emulation PASS (RAM copy only)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, ImportError) as error:
        raise SystemExit(f"audit failed: {error}")
