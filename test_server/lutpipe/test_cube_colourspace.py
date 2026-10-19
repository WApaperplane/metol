#!/usr/bin/env python3
"""Execute the real ARM binary, compare against an independent float model."""
import hashlib
from pathlib import Path
import unittest
from arm_converter_emulator import run_converter
from cube_to_crcb_y import rgb, convert

ROOT = Path(__file__).resolve().parents[2]
BINARY = ROOT / "test_server/lutpipe/build/cube2lut.arm"
OLD = ROOT / "raw8/gates/lut/branch_trace_2026-10-19/lut__cube2lut.arm"
BATCH = Path("E:/NXWA/.tmp/upload")
ADDED = Path("E:/NXWA/.tmp/add")


def constant_cube(r, g, b):
    return ("LUT_3D_SIZE 2\n" + (f"{r} {g} {b}\n" * 8)).encode()


@unittest.skipUnless(BINARY.is_file() and OLD.is_file() and BATCH.is_dir() and ADDED.is_dir(),
                     "requires the built ARM converter and archived cube fixtures")
class ColourspaceTests(unittest.TestCase):
    def execute(self, source, **kw):
        result = run_converter(BINARY, source, **kw)
        self.assertEqual(result["rc"], 0, result["stdout"])
        data = result["output"]
        self.assertEqual(len(data), 19712)
        self.assertTrue(all(data[i] == 0 for i in range(3, 19652, 4)))
        if not kw.get("legacy"):
            self.assertEqual(data[19652:], data[19648:19652] * 3 + bytes(48))
        return data

    def test_constant_neutral_and_colour_corners(self):
        for source, expected in ((constant_cube(.5, .5, .5), bytes([128,128,128,0])),
                                 (constant_cube(1,0,0), bytes([255,85,76,0])),
                                 (constant_cube(0,0,1), bytes([107,255,29,0]))):
            with self.subTest(expected=list(expected)):
                self.assertEqual(self.execute(source)[:19652], expected * 4913)

    def test_hp5_has_neutral_chroma_at_every_node(self):
        data = self.execute((BATCH / "hp5.cube").read_bytes())
        self.assertTrue(all(data[i:i+2] == bytes([128,128]) for i in range(0,19652,4)))
        self.assertGreater(max(data[2:19652:4]) - min(data[2:19652:4]), 180)

    def test_two_live_candidates_match_float_reference_within_two_lsb(self):
        for name in ("hp5", "fuji400h"):
            with self.subTest(name=name):
                source = BATCH / (name + ".cube")
                actual = self.execute(source.read_bytes())
                expected = convert(rgb.parse_cube(source, order="rgb"))
                self.assertLessEqual(max(abs(a-b) for a,b in zip(actual,expected)), 2)

    def test_legacy_mode_exactly_preserves_previous_converter(self):
        self.assertEqual(hashlib.md5(OLD.read_bytes()).hexdigest(), "582b12f0cc9f04ca765a8989d664b580")
        for source in sorted(BATCH.glob("*.cube")):
            with self.subTest(name=source.name):
                baseline = run_converter(OLD, source.read_bytes())
                if baseline["rc"]:
                    self.skipTest("archived input unsupported by old converter")
                self.assertEqual(self.execute(source.read_bytes(), legacy=True), baseline["output"])

    def test_all_uploaded_cubes_match_float_model(self):
        for source in sorted(BATCH.glob("*.cube")) + sorted(ADDED.glob("*.cube")):
            with self.subTest(name=source.name):
                data = self.execute(source.read_bytes())
                expected = convert(rgb.parse_cube(source, order="rgb"))
                self.assertLessEqual(max(abs(a-b) for a,b in zip(data,expected)), 2)

    def test_bad_option_and_non_unit_domain_are_rejected_before_output(self):
        for source, extra in ((constant_cube(1,0,0), "--unknown"),
                              (b"DOMAIN_MAX 0.5 1 1\n" + constant_cube(1,0,0), None)):
            result = run_converter(BINARY, source, extra=extra)
            self.assertNotEqual(result["rc"], 0)
            self.assertIsNone(result["output"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
