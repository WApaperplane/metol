#!/usr/bin/env python3
"""Run the static ARM converter with in-memory Linux file/mmap syscalls.

No host commands, network, camera, or device nodes are exposed to the guest.
Only input.cube and output.bin can be opened. Requires Unicorn.
"""
from io import BytesIO
import struct
from pathlib import Path
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_INTR
from unicorn.arm_const import (
    UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R7, UC_ARM_REG_SP,
)


def run_converter(binary, source, legacy=False, extra=None):
    elf = Path(binary).read_bytes()
    if elf[:7] != b"\x7fELF\x01\x01\x01" or struct.unpack_from("<H", elf, 18)[0] != 40:
        raise ValueError("requires ELF32 little-endian ARM")
    entry, phoff = struct.unpack_from("<II", elf, 24)
    phsize, phnum = struct.unpack_from("<HH", elf, 42)
    segments = [struct.unpack_from("<8I", elf, phoff + i * phsize) for i in range(phnum)]
    segments = [s for s in segments if s[0] == 1]
    start = min(s[2] for s in segments) & ~4095
    end = (max(s[2] + s[5] for s in segments) + 4095) & ~4095
    uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    uc.mem_map(start, end - start)
    for s in segments:
        uc.mem_write(s[2], elf[s[1]:s[1] + s[4]])
    stack = 0x70000000
    uc.mem_map(stack, 0x100000)
    argv = ["cube2lut.arm", "input.cube", "output.bin"]
    if legacy:
        argv.append("--legacy-rgb")
    if extra is not None:
        argv.append(extra)
    pointers, cursor = [], stack + 0xFF000
    for arg in argv:
        encoded = arg.encode() + b"\0"
        pointers.append(cursor)
        uc.mem_write(cursor, encoded)
        cursor += len(encoded)
    sp = stack + 0xFE000
    uc.mem_write(sp, struct.pack("<" + "I" * (len(argv) + 2), len(argv), *pointers, 0))
    uc.reg_write(UC_ARM_REG_SP, sp)
    streams = {0: BytesIO(), 1: BytesIO(), 2: BytesIO()}
    output, opened = None, []
    state = {"heap": 0x40000000, "rc": None}

    def string(address):
        result = bytearray()
        for i in range(4096):
            v = bytes(uc.mem_read(address + i, 1))
            if v == b"\0":
                return result.decode()
            result.extend(v)
        raise RuntimeError("unterminated guest pathname")

    def syscall(machine, interrupt, _):
        nonlocal output
        n = machine.reg_read(UC_ARM_REG_R7)
        a, b, c = (machine.reg_read(reg) for reg in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2))
        if n == 1:
            state["rc"] = a
            machine.emu_stop()
            return
        if n == 5:
            name = string(a)
            opened.append((name, b))
            if name == "input.cube" and b == 0:
                stream = BytesIO(source)
            elif name == "output.bin" and b & 1:
                output = stream = BytesIO()
            else:
                raise RuntimeError("unexpected guest open: " + name)
            result = max(streams) + 1
            streams[result] = stream
        elif n == 3:
            data = streams[a].read(c)
            machine.mem_write(b, data)
            result = len(data)
        elif n == 4:
            result = streams[a].write(bytes(machine.mem_read(b, c)))
        elif n == 6:
            result = 0
        elif n == 19:
            offset = b if b < 0x80000000 else b - 0x100000000
            result = streams[a].seek(offset, c)
        elif n == 192:
            size = (b + 4095) & ~4095
            result = state["heap"]
            machine.mem_map(result, size)
            state["heap"] += size
        elif n == 91:
            result = 0
        else:
            raise RuntimeError("unexpected guest syscall: " + str(n))
        machine.reg_write(UC_ARM_REG_R0, result & 0xFFFFFFFF)

    uc.hook_add(UC_HOOK_INTR, syscall)
    uc.emu_start(entry, 0, count=100_000_000)
    if state["rc"] is None:
        raise RuntimeError("guest instruction budget exhausted")
    return {"rc": state["rc"], "output": output.getvalue() if output else None,
            "stdout": streams[1].getvalue().decode(), "opened": opened}
