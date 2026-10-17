"""Evidence-boundary checks for the offline relocation auditor."""
import struct
import unittest

from p7_data_relocation import (BASE, COPY_LITERALS, COPY_START, COPY_WORDS,
                                SLOT_SIZE, audit_dump, differences, relocation)


class RelocationAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        image = bytearray(0xB84280)
        struct.pack_into("<8I", image, COPY_START, *COPY_WORDS)
        struct.pack_into("<3I", image, COPY_LITERALS,
                         0x8079BDC0, 0x81006000, 0x813EE4C0)
        image[0x892EC0:0x892EC0 + SLOT_SIZE] = bytes([17]) * SLOT_SIZE
        cls.image = bytes(image)
        cls.layout = relocation(cls.image)

    def test_full_slot_mapping_uses_load_address_not_file_va(self):
        slots = {s["slot"]: s for s in self.layout["slots"]}
        self.assertTrue(all(s["inside_copy"] for s in slots.values()))
        self.assertEqual(slots["A12"]["runtime"], 0x810FD100)
        self.assertEqual(slots["A18"]["runtime"], 0x81119F00)

    def test_modified_loop_is_rejected(self):
        image = bytearray(self.image)
        image[COPY_START] ^= 1
        with self.assertRaisesRegex(ValueError, "instructions"):
            relocation(image)

    def test_truncated_source_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "truncated"):
            relocation(self.image[:-1])

    def test_out_of_range_and_empty_dumps_are_rejected(self):
        for data, address in ((b"", 0x810F0000),
                              (b"x", self.layout["end_exclusive"]),
                              (b"x", BASE)):
            with self.assertRaises(ValueError):
                audit_dump(self.image, self.layout, data, address)

    def test_partial_pool_is_not_reported_as_verified(self):
        result = audit_dump(self.image, self.layout, b"\x11" * 16, 0x810FD100)
        self.assertTrue(result["exact_image_match"])
        self.assertFalse(result["pools"]["std"]["complete"])

    def test_modification_is_reported_without_claiming_hardware_effect(self):
        data = bytearray([17]) * SLOT_SIZE
        data[100] = 18
        result = audit_dump(self.image, self.layout, data, 0x810FD100)
        self.assertFalse(result["exact_image_match"])
        self.assertEqual(result["bytes_changed"], 1)
        self.assertEqual(result["pools"]["std"]["matching_static_slots"], [])

    def test_unequal_comparison_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unequal"):
            differences(b"abc", b"ab")


if __name__ == "__main__":
    unittest.main()
