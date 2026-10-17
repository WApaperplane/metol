"""Run the actual ARM collector with a fake syscall boundary, without hardware."""
import struct
import unittest
from pathlib import Path

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_INTR
from unicorn.arm_const import (UC_ARM_REG_PC, UC_ARM_REG_SP, UC_ARM_REG_R0,
                               UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
                               UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R7)


def run_collector(mode="snapshot", open_error=False, mmap_error=False):
    blob = (Path(__file__).parent / "build/lutobserve.arm").read_bytes()
    uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    uc.mem_map(0x10000, 0x20000)
    uc.mem_map(0x70000000, 0x10000)
    entry, phoff = struct.unpack_from("<II", blob, 24)
    phsize, phnum = struct.unpack_from("<HH", blob, 42)
    for i in range(phnum):
        kind, off, vaddr, _, size, _, _, _ = struct.unpack_from("<8I", blob, phoff + i * phsize)
        if kind == 1:
            uc.mem_write(vaddr, blob[off:off + size])
    uc.mem_write(0x70000100, b"lutobserve.arm\0")
    uc.mem_write(0x70000200, mode.encode() + b"\0")
    uc.mem_write(0x70008000, struct.pack("<4I", 2, 0x70000100, 0x70000200, 0))
    uc.reg_write(UC_ARM_REG_SP, 0x70008000)
    state = {"writes": [], "maps": [], "opens": [], "sleeps": 0, "clocks": 0, "exit": None}
    fake_ram = bytes(range(256)) * 1024

    def syscall(machine, interrupt, data):
        del interrupt, data
        number = machine.reg_read(UC_ARM_REG_R7)
        args = [machine.reg_read(r) for r in (UC_ARM_REG_R0, UC_ARM_REG_R1,
                UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_R4, UC_ARM_REG_R5)]
        rc = 0
        if number == 104:  # setitimer
            assert struct.unpack("<4I", machine.mem_read(args[1], 16)) == (0, 0, 120, 0)
        elif number == 5:  # open
            name = bytes(machine.mem_read(args[0], 32)).split(b"\0")[0]
            assert name == b"/dev/mem"
            assert args[1] & 3 == 0  # O_RDONLY only
            assert args[1] & 0x101000 == 0x101000  # O_SYNC
            state["opens"].append((name, args[1]))
            rc = -13 if open_error else 3
        elif number == 192:  # mmap2
            assert args[2] == 1 and args[3] == 1 and args[4] == 3
            assert (args[1], args[5]) in ((4096, 0x2082B), (0x40000, 0x810F0))
            state["maps"].append(args)
            if mmap_error:
                rc = -14
            else:
                # A high-bit user address must not be mistaken for -errno.
                machine.mem_map(0xB6000000, args[1])
                if args[1] == 4096:
                    machine.mem_write(0xB6000000, struct.pack("<5I", 1, 0x1100, 1, 0x81115200, 0))
                else:
                    machine.mem_write(0xB6000000, fake_ram)
                rc = 0xB6000000
        elif number == 263:  # clock_gettime32
            assert args[0] == 1
            ms = 100000 + state["clocks"] * 100
            state["clocks"] += 1
            machine.mem_write(args[1], struct.pack("<2I", ms // 1000, (ms % 1000) * 1000000))
        elif number == 162:  # nanosleep
            assert struct.unpack("<2I", machine.mem_read(args[0], 8)) == (0, 100000000)
            state["sleeps"] += 1
        elif number == 4:  # write; only stdout and stderr permitted
            assert args[0] in (1, 2)
            state["writes"].append((args[0], bytes(machine.mem_read(args[1], args[2]))))
            rc = args[2]
        elif number in (6, 91):  # close / munmap
            pass
        elif number == 1:
            state["exit"] = args[0]
            machine.emu_stop()
        else:
            raise AssertionError(f"unexpected syscall {number}")
        machine.reg_write(UC_ARM_REG_R0, rc & 0xFFFFFFFF)

    uc.hook_add(UC_HOOK_INTR, syscall)
    uc.emu_start(entry, 0, count=10_000_000, timeout=10_000_000)
    assert state["exit"] is not None, hex(uc.reg_read(UC_ARM_REG_PC))
    state["stdout"] = b"".join(b for fd, b in state["writes"] if fd == 1)
    return state


class LutObserveTests(unittest.TestCase):
    def test_snapshot_reads_only_fixed_registers(self):
        result = run_collector()
        self.assertEqual(result["exit"], 0)
        self.assertEqual(len(result["stdout"].splitlines()), 2)
        self.assertIn(b"0x81115200", result["stdout"])
        self.assertEqual(result["sleeps"], 0)

    def test_watch_is_bounded(self):
        result = run_collector("watch")
        self.assertEqual(result["exit"], 0)
        self.assertEqual(len(result["stdout"].splitlines()), 901)
        self.assertEqual(result["sleeps"], 899)
        self.assertEqual(len(result["maps"]), 1)

    def test_pool_dump_is_exact(self):
        result = run_collector("pools")
        self.assertEqual(result["exit"], 0)
        self.assertEqual(result["stdout"], bytes(range(256)) * 1024)

    def test_unknown_mode_cannot_open_memory(self):
        result = run_collector("write")
        self.assertEqual(result["exit"], 1)
        self.assertEqual(result["opens"], [])

    def test_open_failure_stops_before_mapping(self):
        result = run_collector(open_error=True)
        self.assertEqual(result["exit"], 1)
        self.assertEqual(result["maps"], [])

    def test_mmap_error_stops_before_sampling(self):
        result = run_collector(mmap_error=True)
        self.assertEqual(result["exit"], 1)
        self.assertEqual(result["clocks"], 0)
        self.assertEqual(result["stdout"], b"")


if __name__ == "__main__":
    unittest.main()
