"""Verify phase/contrast arbitration checkpoints in the official NX500 p7.

Reads firmware only. Emits evidence, not a firmware patch. Small A32 windows
are inspection context and must not be interpreted as function boundaries.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct

from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_LITTLE_ENDIAN


FIRMWARE = Path("E:/NXWA/fw/v1.12/NX500_v1.12.bin")
EXPECTED = "f8e417cb5b55768851ba7e2b8017d3a98dc0b0c8444cc0a5061265cc08dbbf7f"
OUT = Path(__file__).resolve().parent / "out/priority"

# Human-reviewed sites; assertions prevent silently applying the notes to a
# different sample. These are evidence checks, not a complete CFG or emulator.
CHECKPOINTS = [
    (0x348D18, "bl", "#0x348ad0", "Initial direction selection tries phase initialization"),
    (0x348D1C, "cmp", "r0, #0", "Test whether phase initialization handled the request"),
    (0x348D20, "bne", "#0x348ecc", "Handled phase path exits before subsequent contrast selection"),
    (0x348934, "bl", "#0x3480f0", "Initial phase main calls calculation/arbitration"),
    (0x3484DC, "bl", "#0x347fe4", "A branch invokes phase direct-drive helper with r1=1"),
    (0x3485E8, "movw", "r2, #0x106", "Initial arbitration can select phase-only state"),
    (0x34871C, "movw", "r1, #0x306", "Initial arbitration has a final-driveless exit"),
    (0x348720, "bl", "#0x33b820", "Pass final-driveless state to state helper"),
    (0x349CA8, "bl", "#0x33cae0", "Dispatcher invokes phase final-driveless handler"),
    (0x33CB40, "movw", "r1, #0x80a", "Final-driveless handler selects terminal state"),
    (0x33CB44, "bl", "#0x33b820", "Pass terminal state to state helper"),
    (0x344784, "movw", "r2, #0x101", "Phase NG fallback selects contrast initial-direction state"),
    (0x34779C, "movw", "r2, #0x106", "Contrast sequence may switch back to phase-only"),
    (0x347DE0, "bl", "#0x34757c", "Before-execute hook calls reverse-transition check"),
    (0x340764, "cmp", "r2, #2", "Wait-peak branch bounds its incremented retry counter"),
    (0x340768, "bgt", "#0x3407a8", "Counter above two selects USE CONTRAST AF(#2)"),
]

# These exact literal loads connect labels to executable sites. Peak OK/NG
# here must not automatically be relabeled as a contrast-detection peak.
LITERALS = [
    (0x343AE0, 0x8074D43C, "PAF Ini:dir_ok(dif %d > thr %d)spd %d ToCAF\n"),
    (0x343B38, 0x8074D46C, "PAF Ini:dir_ok(dif %d <= thr %d) ToCAF\n"),
    (0x3447BC, 0x8074D770, "PAF Only:ToCAF(Peak NG, Comp=0)\n"),
    (0x3477C4, 0x8074DD9C, "CAF:ToPAFOnly(Peak OK)\n"),
    (0x34076C, 0x8074C998, "PAF DIR : WAIT PEAK ... (%d)"),
    (0x3407A8, 0x8074C9B8, "USE CONTRAST AF(#2)"),
    (0x3407BC, 0x8074C9CC, "USE CONTRAST AF(#4)"),
    (0x3407FC, 0x8074C9E0, "USE CONTRAST AF(#1)"),
    (0x348724, 0x8074C7C4, "::: SET eSEQ_STATE_FINAL_DRIVELESS"),
    (0x33CAF0, 0x806250D0, "processPhaseAfFinalDriveless"),
]


def main():
    with FIRMWARE.open("rb") as source:
        header = struct.unpack("<4s8s16s16sbI15s", source.read(64))
        assert header[0] == b"SLP\0" and header[4] == 10
        parts = [struct.unpack("<IIII8s", source.read(24)) for _ in range(header[4])]
        length, _, offset, _, _ = parts[5]
        source.seek(offset)
        image = source.read(length)
    digest = hashlib.sha256(image).hexdigest()
    assert digest == EXPECTED, digest
    disassembler = Cs(CS_ARCH_ARM, CS_MODE_ARM | CS_MODE_LITTLE_ENDIAN)

    def u32(address):
        return struct.unpack_from("<I", image, address)[0]

    def instruction(address):
        return next(disassembler.disasm(image[address:address + 4], address, count=1))

    records = []
    for address, mnemonic, operands, interpretation in CHECKPOINTS:
        decoded = instruction(address)
        assert (decoded.mnemonic, decoded.op_str) == (mnemonic, operands), hex(address)
        records.append({
            "chunk_offset": hex(address), "bytes": decoded.bytes.hex(),
            "instruction": f"{mnemonic} {operands}", "interpretation": interpretation,
            "context": [f"{ins.address:08x} {ins.mnemonic} {ins.op_str}" for ins in
                        disassembler.disasm(image[address - 16:address + 20], address - 16)],
        })
    literals = []
    for address, expected_pointer, expected_text in LITERALS:
        word = u32(address)
        assert (word & 0x0F7F0000) == 0x051F0000, hex(address)
        displacement = word & 0xFFF
        pool = address + 8 + (displacement if word & 0x800000 else -displacement)
        pointer = u32(pool)
        assert pointer == expected_pointer, hex(address)
        raw = image[pointer - 0x80000000:].split(b"\0", 1)[0]
        actual_text = raw.decode("ascii")
        assert actual_text == expected_text, (hex(address), actual_text)
        literals.append({"instruction_offset": hex(address), "pool_offset": hex(pool),
                         "runtime_pointer": hex(pointer), "text": actual_text})
    OUT.mkdir(parents=True, exist_ok=True)
    result = {
        "source": str(FIRMWARE), "part_index": 5, "chunk_offset": hex(offset),
        "chunk_size": length, "chunk_sha256": digest,
        "scope": "A32 checkpoint and literal verification; human-reviewed path interpretation",
        "limitations": ["No camera execution or usage-frequency measurement",
                        "No complete mode/lens/recording-resolution matrix",
                        "No proof that phase-only paths stop evaluating contrast statistics",
                        "Peak labels are not sufficient to identify the underlying signal"],
        "checkpoints": records, "literal_references": literals,
    }
    destination = OUT / "verified_checkpoints.json"
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Verified {len(records)} instructions and {len(literals)} literal references: {destination}")


if __name__ == "__main__":
    main()
