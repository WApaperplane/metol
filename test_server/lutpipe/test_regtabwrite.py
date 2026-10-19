#!/usr/bin/env python3
"""Guards for nx_regtabwrite.c: one word, one target, always reversible.

This tool writes to camera memory, so the invariants are checked from source
plus the reference image rather than trusted by inspection.
"""
import re
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "nx_regtabwrite.c"
IMAGE = Path("E:/NXWA/fw/v1.12/a2/p7_a2.bin")
MD5_A2 = "712c6fd0a49371ec05ce94c367b0d5c7"

SLOT_LEN = 0x4D00
BLOCK_A = 0x8592C0


def text():
    return SOURCE.read_text(encoding="utf-8")


def define(name):
    match = re.search(r"#define\s+%s\s+(0x[0-9A-Fa-f]+|[0-9]+)[uU]?" % name, text())
    if not match:
        raise AssertionError("define %s missing" % name)
    token = match.group(1)
    return int(token, 16) if token.lower().startswith("0x") else int(token, 10)


def slot_offset(index, block="A"):
    base = {"A": 0x8592C0, "B": 0x8B9AC0}[block]
    return base + index * SLOT_LEN


class RegistryWriterGuards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not IMAGE.exists():
            raise unittest.SkipTest("reference image not present")
        cls.image = IMAGE.read_bytes()

    def test_single_target_offset(self):
        self.assertEqual(define("VIEW3_OFF"), define("VIEW_AT") + 12)
        self.assertEqual(define("TAB_ADDR") + define("VIEW3_OFF"), 0x803837FC)

    def test_view4_third_entry_is_a17_in_image(self):
        offset = define("TAB_ADDR") + define("VIEW_AT") - 0x80000000
        words = [int.from_bytes(self.image[offset + 4 * i:offset + 4 * i + 4], "little")
                 for i in range(4)]
        self.assertEqual(words[3], define("VAL_A17"))
        self.assertEqual(words[0], 0x810FD100)
        self.assertEqual(words[1], 0x81101E00)
        self.assertEqual(words[2], 0x81106B00)

    def test_replacement_slot_exists_in_image(self):
        """A18 and A19 must both be real slots inside the relocation window."""
        for name, index in (("VAL_A18", 18), ("VAL_A19", 19)):
            value = define(name)
            file_offset = value - 0x80000000 - 0x86A240
            self.assertEqual(file_offset, slot_offset(index), name)
            self.assertLessEqual(file_offset + SLOT_LEN, len(self.image), name)
            self.assertTrue(any(self.image[file_offset:file_offset + SLOT_LEN]), name)

    def test_view_path_writes_exactly_one_word(self):
        body = text()
        self.assertEqual(body.count("tab[VIEW3_OFF >> 2] = target;"), 1,
                         "the View path must write a single word")
        # The Still path may only write through its loop index.
        self.assertNotIn("tab[(STILL_AT >> 2)] = ", body)

    def test_refuses_unexpected_current_value(self):
        body = text()
        self.assertIn("REFUSE", body)
        self.assertIn("before != expect", body)

    def test_all_modes_present(self):
        body = text()
        for mode in ('"status"', '"probe"', '"patch"', '"patch12"', '"restore"', '"still-set"', '"still-restore"'):
            self.assertIn(mode, body)

    def test_restore_is_the_exact_inverse_of_patch(self):
        body = text()
        self.assertIn('{ expect = 0xFFFFFFFFu; target = slot; }', body)
        self.assertIn('{ expect = 0xFFFFFFFFu; target = VAL_A17; }', body)

    def test_still_path_uses_the_requested_slot(self):
        """Both registry paths must honour the caller's slot, not hardcode A18."""
        body = text()
        self.assertIn("tab[(STILL_AT >> 2) + i] = slot;", body)
        self.assertNotIn("tab[(STILL_AT >> 2) + i] = VAL_A18;", body)
        self.assertIn("do_write(argv[1], slot)", body)
        self.assertIn("do_still(argv[1], slot)", body)

    def test_window_delta_verified(self):
        self.assertIn("window_delta", text())

    def test_no_firmware_or_partition_access(self):
        body = text()
        self.assertNotIn("mmcblk", body)
        # "No ioctl" appears in the header comment; only a call would matter.
        self.assertNotIn("ioctl(", body)
        # The only SD path allowed is the Still6 backup file.
        paths = set(re.findall(r'"(/mnt/mmc[^"]*)"', body))
        self.assertEqual(paths, {"/mnt/mmc/nxwa_regtab_20261018/still6_orig.bin"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
