"""C1 verification must distinguish A17, A12, incomplete and padded readbacks."""
import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from c1_verify import (B_OFF, BLK_OFF, REDIRECT, assess, main,
                       slot_offset, validate_candidate)


class C1VerifyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base = bytearray(0x8AFCC0)
        base[B_OFF:B_OFF + 4] = REDIRECT
        base[BLK_OFF:BLK_OFF + 80] = bytes(range(80))
        cls.base = bytes(base)
        cls.a17_offset = slot_offset("A17", len(base))
        candidate = bytearray(base)
        candidate[cls.a17_offset:cls.a17_offset + 4] = b"\xff\xff\xff\0"
        cls.candidate = bytes(candidate)

    def test_a17_negative_is_not_required_to_be_identity(self):
        report = assess(self.candidate, self.candidate, self.base, "a17")
        self.assertTrue(report["ok"])
        self.assertTrue(report["judge_D_slot_expected"])
        self.assertFalse(report["hardware_consumption_verified"])

    def test_a12_change_does_not_satisfy_a17(self):
        wrong = bytearray(self.base)
        a12 = slot_offset("A12", len(wrong))
        wrong[a12:a12 + 4] = b"\x11\x22\x33\0"
        report = assess(wrong, self.candidate, self.base, "A17")
        self.assertFalse(report["ok"])
        self.assertFalse(report["judge_D_slot_expected"])

    def test_short_matching_prefix_never_passes(self):
        report = assess(self.candidate[:-1], self.candidate, self.base, "A17")
        self.assertFalse(report["complete"])
        self.assertFalse(report["ok"])
        self.assertIsNone(report["diff_vs_expected"])

    def test_dd_padding_is_separately_reported(self):
        report = assess(self.candidate + bytes(3456), self.candidate, self.base, "A17")
        self.assertTrue(report["ok"])
        self.assertEqual(report["ignored_trailing_bytes"], 3456)
        self.assertEqual(report["evaluated_bytes"], len(self.candidate))

    def test_correct_slot_with_unexpected_code_change_fails(self):
        wrong = bytearray(self.candidate)
        wrong[0x200] ^= 1
        report = assess(wrong, self.candidate, self.base, "A17")
        self.assertTrue(report["judge_D_slot_expected"])
        self.assertFalse(report["ok"])
        self.assertEqual(report["diff_vs_expected"], 1)

    def test_expected_a2_is_a_successful_preflight(self):
        report = assess(self.base, self.candidate, self.base, "A17", expect="a2")
        self.assertTrue(report["ok"])
        self.assertEqual(report["matched"], "a2")

    def test_candidate_for_another_slot_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "outside"):
            validate_candidate(self.candidate, self.base, "A12")

    def test_bad_or_out_of_bounds_slot_is_rejected(self):
        for slot in ("../../A17", "A20", "B22", "A", "A19"):
            with self.assertRaises(ValueError):
                slot_offset(slot, len(self.base))

    def test_report_cannot_overwrite_input(self):
        with tempfile.TemporaryDirectory() as folder:
            data = Path(folder) / "readback.bin"
            data.write_bytes(b"preserve original evidence")
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    main(["--readback", str(data), "--json", str(data)])
            self.assertEqual(error.exception.code, 2)
            self.assertEqual(data.read_bytes(), b"preserve original evidence")


if __name__ == "__main__":
    unittest.main()
