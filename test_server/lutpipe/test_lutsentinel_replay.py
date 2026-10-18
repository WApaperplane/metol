"""Compile real sentinel logic with mocked IO; this does not emulate hardware DMA."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


class SentinelReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cc = shutil.which("cc") or shutil.which("gcc")
        if not cc:
            raise unittest.SkipTest("requires a local C compiler (run in WSL)")
        cls.temp = tempfile.TemporaryDirectory(prefix="nxwa-sentinel-replay-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.exe = Path(cls.temp.name) / "sentinel-replay"
        source = Path(__file__).with_name("fixtures") / "lutsentinel_host.c"
        subprocess.run([cc, "-O0", "-Wall", "-Wextra", "-Werror", str(source),
                        "-o", str(cls.exe)], check=True, capture_output=True, text=True)

    def replay(self, sel):
        p = subprocess.run([str(self.exe), "--sel", str(sel), "--count", "4", "--quiet"],
                           capture_output=True, text=True, timeout=5, check=True)
        m = re.search(r"HARNESS op_init_calls=(\d+) simulated_reloads=(\d+) "
                      r"table_generation=(\d+) cfg=0x([0-9a-f]+)", p.stdout)
        self.assertIsNotNone(m, p.stdout)
        return tuple(int(v, 16 if i == 3 else 10) for i, v in enumerate(m.groups())), p.stdout

    def test_sel0_does_nothing_when_p7_reloads_lut0_without_changing_selection(self):
        values, output = self.replay(0)
        self.assertEqual(values[:3], (0, 4, 4))
        self.assertNotIn("rc=0", output)

    def test_sel1_reacts_to_same_selection_trace_by_calling_op_init(self):
        values, output = self.replay(1)
        self.assertEqual(values[:3], (4, 4, 4))
        self.assertEqual(output.count("rc=0"), 4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
