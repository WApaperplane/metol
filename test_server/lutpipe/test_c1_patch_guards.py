"""Rejected C1 inputs must never produce firmware artifacts."""
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

import mk_c1_patch


class C1GuardTests(unittest.TestCase):
    def reject(self, slot="A17", table=b"", valid_hash=True):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base, source, output = root / "base.bin", root / "table.bin", root / "output"
            base.write_bytes(b"invalid base fixture")
            source.write_bytes(table)
            argv = ["mk_c1_patch.py", "--base", str(base), "--slot", slot,
                    "--table-file", str(source), "--out", str(output), "--write"]
            hash_mock = Mock()
            hash_mock.hexdigest.return_value = "712c6fd0a49371ec05ce94c367b0d5c7"
            with contextlib.ExitStack() as stack:
                stack.enter_context(patch.object(sys, "argv", argv))
                stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
                if valid_hash:
                    stack.enter_context(patch.object(mk_c1_patch.hashlib, "md5", return_value=hash_mock))
                with self.assertRaises(ValueError):
                    mk_c1_patch.main()
            self.assertFalse(output.exists())

    def test_wrong_base_hash(self):
        self.reject(valid_hash=False)

    def test_short_table(self):
        self.reject(table=b"short")

    def test_malformed_slot(self):
        self.reject(slot="SB12")

    def test_nonzero_rgb_padding(self):
        table = bytearray(mk_c1_patch.SLOT)
        table[3] = 1
        self.reject(table=table)


if __name__ == "__main__":
    unittest.main()
