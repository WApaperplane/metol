#!/usr/bin/env python3
"""Cross-check nx_regtabdump.c constants against the A2 reference image.

The dumper compares camera memory against arrays compiled into it, so a typo
in one of those arrays would turn a good read into a false MISMATCH. This test
re-derives every expected word from the reference image and fails on drift.

Offline only: reads the local image, never touches a camera.
"""
import re
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "nx_regtabdump.c"
IMAGE = Path("E:/NXWA/fw/v1.12/a2/p7_a2.bin")
MD5_A2 = "712c6fd0a49371ec05ce94c367b0d5c7"

ARRAYS = {
    "ctrl_expect": 0x11620,
    "view_expect": 0x3837F0,
    "still_expect": 0x382C5C,
    "bv_expect": 0x382B00,
}


def source_text():
    return SOURCE.read_text(encoding="utf-8")


def parse_array(name):
    pattern = re.compile(
        r"static const unsigned int %s\[\d+\]\s*=\s*\{(.*?)\};" % name, re.S)
    match = pattern.search(source_text())
    if not match:
        raise AssertionError("array %s not found in nx_regtabdump.c" % name)
    body = match.group(1)
    values = re.findall(r"0x([0-9A-Fa-f]{8})[uU]?", body)
    return [int(v, 16) for v in values]


def parse_define(name):
    match = re.search(r"#define\s+%s\s+(0x[0-9A-Fa-f]+|[0-9]+)[uU]?" % name, source_text())
    if not match:
        raise AssertionError("define %s not found" % name)
    token = match.group(1)
    return int(token, 16) if token.lower().startswith("0x") else int(token, 10)


class RegistryDumpConstants(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not IMAGE.exists():
            raise unittest.SkipTest("reference image not present: %s" % IMAGE)
        cls.image = IMAGE.read_bytes()

    def test_image_identity(self):
        import hashlib
        self.assertEqual(hashlib.md5(self.image).hexdigest(), MD5_A2)

    def test_expected_words_match_image(self):
        for name, offset in ARRAYS.items():
            expected = parse_array(name)
            self.assertTrue(expected, "%s parsed empty" % name)
            actual = [int.from_bytes(self.image[offset + 4 * i:offset + 4 * i + 4], "little")
                      for i in range(len(expected))]
            self.assertEqual(expected, actual,
                             "%s drifts from image at 0x%08X" % (name, offset))

    def test_array_lengths_match_registry_sizes(self):
        self.assertEqual(len(parse_array("view_expect")), 4)
        self.assertEqual(len(parse_array("still_expect")), 6)
        self.assertEqual(len(parse_array("bv_expect")), 12)
        self.assertEqual(len(parse_array("ctrl_expect")), 4)

    def test_offsets_are_word_aligned_and_inside_mapped_page(self):
        size = parse_define("TAB_SIZE")
        base = parse_define("TAB_ADDR")
        for name in ("VIEW_AT", "STILL_AT", "BV_AT"):
            offset = parse_define(name)
            self.assertEqual(offset & 3, 0, "%s not word aligned" % name)
            self.assertLess(offset + 4, size, "%s outside mapped window" % name)
        self.assertEqual(base & 0xFFF, 0)

    def test_absolute_addresses_match_t4_registry(self):
        """Second, independent source: the absolute VAs recorded in T4."""
        base = parse_define("TAB_ADDR")
        expected = {"VIEW_AT": 0x803837F0, "STILL_AT": 0x80382C5C, "BV_AT": 0x80382B00}
        for name, absolute in expected.items():
            self.assertEqual(base + parse_define(name), absolute,
                             "%s resolves to the wrong absolute address" % name)

    def test_control_probe_address_matches_loop(self):
        base = parse_define("CTRL_ADDR")
        item = parse_define("CTRL_ITEM")
        self.assertEqual(base & 0xFFF, 0)
        self.assertLess(item - base, parse_define("CTRL_PAGE"))

    def test_dumper_is_read_only(self):
        text = source_text()
        self.assertNotIn("O_RDWR", text)
        self.assertNotIn("PROT_WRITE", text)
        self.assertNotIn("ioctl(", text)
        self.assertIn("O_RDONLY | O_SYNC", text)
        self.assertIn("PROT_READ", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
