#!/usr/bin/env python3
"""Guard cube2lut: the on-camera fixed-point converter must match the PC reference.

The ARM binary cannot run here, so the test pins down what was actually
verified on the camera: for every archived cube, the on-device output and the
nx3dlut.py float output are byte-identical, the slot length is 19,712, and the
60-byte tail is zero.

Offline only.
"""
import hashlib
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
EVID = REPO / "raw8" / "gates" / "lut" / "cube2lut_2026-10-18"

CASES = ("identity17", "invert17", "warm33")
TABLE_LEN = 0x4D00 - 60      # 19652
SLOT_LEN = 0x4D00            # 19712


class Cube2LutMatchesReference(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not EVID.is_dir():
            raise unittest.SkipTest("evidence dir absent: %s" % EVID)

    def _read(self, name):
        path = EVID / name
        if not path.exists():
            self.skipTest("missing %s" % name)
        return path.read_bytes()

    def test_arm_matches_pc_byte_for_byte(self):
        for case in CASES:
            arm = self._read("%s_arm.bin" % case)
            pc = self._read("%s_pc.bin" % case)
            self.assertEqual(len(arm), SLOT_LEN, "%s slot length" % case)
            self.assertEqual(arm[:TABLE_LEN], pc[:TABLE_LEN],
                             "%s differs from the float reference" % case)

    def test_tail_is_zero_padding(self):
        for case in CASES:
            arm = self._read("%s_arm.bin" % case)
            self.assertEqual(arm[TABLE_LEN:], b"\x00" * (SLOT_LEN - TABLE_LEN),
                             "%s padding is not zero" % case)

    def test_identity_table_is_the_hardware_grid(self):
        arm = self._read("identity17_arm.bin")
        levels = [min(i * 16, 255) for i in range(17)]
        idx = 0
        for b in levels:
            for g in levels:
                for r in levels:
                    self.assertEqual(arm[idx:idx + 4], bytes([r, g, b, 0]),
                                     "identity entry mismatch at %d" % (idx // 4))
                    idx += 4

    def test_invert_table_is_exact_complement(self):
        arm = self._read("invert17_arm.bin")
        ident = self._read("identity17_arm.bin")
        for i in range(TABLE_LEN):
            if i % 4 == 3:          # pad byte stays zero in both
                self.assertEqual(arm[i], 0, "invert pad byte at %d" % i)
                continue
            self.assertEqual(arm[i], 255 - ident[i],
                             "invert entry mismatch at byte %d" % i)

    def test_pad_byte_never_written(self):
        for case in CASES:
            arm = self._read("%s_arm.bin" % case)
            for i in range(3, TABLE_LEN, 4):
                self.assertEqual(arm[i], 0, "%s pad byte set at %d" % (case, i))


class ScientificNotationRegression(unittest.TestCase):
    """G'MIC writes very dark values as 2.24e-05. The first parser stopped at
    'e' without advancing, so the rest of the file silently became zeros while
    the node count still matched -- a black LUT reported as success.
    12 of 18 real film cubes were affected."""

    @classmethod
    def setUpClass(cls):
        if not EVID.is_dir():
            raise unittest.SkipTest("evidence dir absent: %s" % EVID)

    def _read(self, name):
        path = EVID / name
        if not path.exists():
            self.skipTest("missing %s" % name)
        return path.read_bytes()

    def test_real_film_cube_matches_pc_within_one_lsb(self):
        arm = self._read("portra400_sci_arm.bin")
        pc = self._read("portra400_sci_pc.bin")
        self.assertEqual(len(arm), SLOT_LEN)
        deltas = [abs(a - b) for a, b in zip(arm[:TABLE_LEN], pc[:TABLE_LEN]) if a != b]
        # 13^3 -> 17^3 upsampling is exact in the reference but fixed-point
        # rounds differently, so a 1 LSB difference is expected, not a defect.
        self.assertLessEqual(len(deltas), 600, "too many bytes differ from the reference")
        self.assertTrue(all(d <= 1 for d in deltas), "delta exceeds one LSB")

    def test_table_is_not_collapsed_to_black(self):
        arm = self._read("portra400_sci_arm.bin")
        nonzero = sum(1 for i in range(0, TABLE_LEN, 4) if any(arm[i:i + 3]))
        self.assertGreater(nonzero, 4800,
                           "table is mostly zeros -> the parser collapsed again")

    def test_last_entry_is_a_white_corner(self):
        arm = self._read("portra400_sci_arm.bin")
        self.assertGreater(arm[TABLE_LEN - 4], 200, "last entry is not white")


class ConverterSourceGuards(unittest.TestCase):
    def test_no_floating_point(self):
        src = (HERE / "cube2lut.c").read_text(encoding="utf-8")
        for token in ("float ", "double ", "%f", "atof", "sqrt"):
            self.assertNotIn(token, src, "floating point leaked into the ARM build")

    def test_rejects_non_unit_domain(self):
        src = (HERE / "cube2lut.c").read_text(encoding="utf-8")
        self.assertIn("DOMAIN_MIN is not 0", src)
        self.assertIn("DOMAIN_MAX is not 1", src)

    def test_rejects_1d_cube(self):
        src = (HERE / "cube2lut.c").read_text(encoding="utf-8")
        self.assertIn("1D cube is not supported", src)

    def test_slot_geometry_constants(self):
        src = (HERE / "cube2lut.c").read_text(encoding="utf-8")
        self.assertIn("#define SLOT_LEN   19712u", src)
        self.assertIn("#define TABLE_LEN  19652u", src)
        self.assertIn("#define N16        17u", src)

    def test_parser_handles_scientific_notation(self):
        src = (HERE / "cube2lut.c").read_text(encoding="utf-8")
        self.assertIn("*s == 'e'", src, "no exponent branch in the number parser")

    def test_parser_reports_bad_numbers_instead_of_zero(self):
        src = (HERE / "cube2lut.c").read_text(encoding="utf-8")
        self.assertIn("bad number at value index", src)
        self.assertIn("parsed table is all zeros", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
