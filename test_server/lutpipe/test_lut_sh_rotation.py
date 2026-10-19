#!/usr/bin/env python3
"""Two-slot rotation guards for scripts/lut.sh, without a camera.

The product script hardcodes camera paths, so the test rewrites only the four
path assignments into a temporary sandbox and drives it with recording stubs.
Nothing here touches /opt/usr/nx-ks, /mnt/mmc or any device node.

Run: python3 test_lut_sh_rotation.py
"""
from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
PRODUCT = HERE.parents[1] / "scripts" / "lut.sh"

A18 = "0x81119F00"
A19 = "0x8111EC00"

SLOT_WRITE = r'''#!/bin/sh
mkdir -p "$(dirname "$NXWA_TEST_CALLS")"
printf 'SLOT %s %s\n' "$1" "$2" >> "$NXWA_TEST_CALLS"
case "$1" in
  read)
    yes "$2" | head -c 19712 > "$3"
    echo "SLOT dumped to output path"
    ;;
  *)
    echo "READBACK ok"
    ;;
esac
echo "=== done ==="
'''

REGT_WRITE = r'''#!/bin/sh
printf 'REGT %s\n' "$*" >> "$NXWA_TEST_CALLS"
case "$1" in
  status)
    echo "=== regtabwrite (single word, View4[3] only) ==="
    echo "VIEW4 : 0x810fd100 0x81101e00 0x81106b00 0x81115200"
    echo "STILL6: 0x81119f00 0x81115200 0x8111ec00 0x8110b800 0x81106b00 0x81110500"
    ;;
  patch)
    echo "READBACK $2"
    ;;
  still-set|still-write)
    echo "STILL6 after : $2 $2 $2 $2 $2 $2"
    echo "READBACK ok"
    ;;
  *)
    echo "READBACK ok"
    ;;
esac
echo "=== done ==="
'''


OLD_REGT = r'''#!/bin/sh
# Pre-rotation binary: ignores the slot argument and always writes A18.
case "$1" in
  patch) echo "READBACK 0x81119F00" ;;
  still-set|still-write) echo "STILL6 after : 0x81119f00"; echo "READBACK ok" ;;
  *) echo "READBACK ok" ;;
esac
echo "=== done ==="
'''


def materialise(root: Path) -> Path:
    text = PRODUCT.read_text(encoding="utf-8")
    # POSIX separators: a Windows path would lose its backslashes inside sh.
    root = Path(root)
    replacements = {
        "D=/opt/usr/nx-ks": "D=%s" % (root / "nx-ks").as_posix(),
        "LAB=/mnt/mmc/looks": "LAB=%s" % (root / "looks").as_posix(),
        "ST=/mnt/mmc/lut/state": "ST=%s" % (root / "state").as_posix(),
        "STILLBAK=/mnt/mmc/nxwa_regtab_20261018/still6_orig.bin":
            "STILLBAK=%s" % (root / "still6_orig.bin").as_posix(),
    }
    for old, new in replacements.items():
        if old not in text:
            raise AssertionError("assignment moved: %s" % old)
        text = text.replace(old, new)
    out = root / "lut.sh"
    out.write_text(text, encoding="utf-8")
    return out


class RotationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="nxwa-lut-rotation-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.mod = self.root / "nx-ks"
        self.tools = self.mod / "lut"
        self.looks = self.root / "looks"
        self.calls = self.root / "calls.txt"
        for d in (self.tools, self.looks):
            d.mkdir(parents=True)
        self.stub(self.tools / "nx_slotwrite.arm", SLOT_WRITE)
        self.stub(self.tools / "nx_regtabwrite.arm", REGT_WRITE)
        self.stub(self.tools / "cube2lut.arm", "#!/bin/sh\nexit 0\n")
        self.stub(self.mod / "busybox", '#!/bin/sh\nexec "$@"\n')
        for name in ("alpha", "beta", "gamma"):
            (self.looks / (name + ".bin")).write_bytes(bytes(19712))
        self.script = materialise(self.root)
        self.env = dict(os.environ, NXWA_TEST_CALLS=str(self.calls))

    @staticmethod
    def stub(path: Path, body: str):
        path.write_text(body, encoding="utf-8")
        path.chmod(0o755)

    def run_lut(self, *args):
        proc = subprocess.run(["sh", str(self.script), *args], capture_output=True,
                              text=True, env=self.env)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return proc.stdout

    def slots_written(self):
        if not self.calls.exists():
            return []
        out = []
        for line in self.calls.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if parts[:2] == ["SLOT", "write"]:
                out.append(parts[2])
        return out

    def calls_for(self, prefix):
        if not self.calls.exists():
            return []
        return [l for l in self.calls.read_text(encoding="utf-8").splitlines()
                if l.startswith(prefix)]

    def test_apply_alternates_slots(self):
        self.run_lut("apply", "alpha")
        self.run_lut("apply", "beta")
        self.run_lut("apply", "gamma")
        self.assertEqual(self.slots_written(), [A18, A19, A18])

    def test_registry_follows_the_slot_every_time(self):
        self.run_lut("apply", "alpha")
        self.run_lut("apply", "beta")
        patches = [l.split()[-1] for l in self.calls_for("REGT patch")]
        self.assertEqual(patches, [A18, A19])
        stills = [l.split()[-1] for l in self.calls_for("REGT still-")]
        self.assertEqual(stills, [A18, A19])

    def test_each_slot_is_backed_up_exactly_once(self):
        self.run_lut("apply", "alpha")
        self.run_lut("apply", "beta")
        self.run_lut("apply", "gamma")
        reads = self.calls_for("SLOT read")
        self.assertEqual(len(reads), 2, reads)
        self.assertTrue((self.root / "state" / "a18_orig.bin").exists())
        self.assertTrue((self.root / "state" / "a19_orig.bin").exists())
        self.assertEqual((self.root / "state" / "a18_orig.bin").stat().st_size, 19712)

    def test_off_restores_both_slots_and_both_registries(self):
        self.run_lut("apply", "alpha")
        self.run_lut("apply", "beta")
        self.calls.unlink()
        self.run_lut("off")
        restored = [l.split()[-1] for l in self.calls_for("SLOT restore")]
        self.assertEqual(restored, [A18, A19])
        self.assertEqual(len(self.calls_for("REGT restore")), 1)
        self.assertFalse((self.root / "state" / "active").exists())
        self.assertFalse((self.root / "state" / "current").exists())

    def test_status_reports_the_active_slot(self):
        self.run_lut("apply", "alpha")
        self.assertIn("slot a18", self.run_lut("status"))
        self.run_lut("apply", "beta")
        out = self.run_lut("status")
        self.assertIn("ACTIVE beta (slot a19)", out)
        self.assertIn("a18=present a19=present", out)

    def test_legacy_state_counts_as_a18(self):
        """A pre-rotation state/current without state/active must not be overwritten in place."""
        state = self.root / "state"
        state.mkdir()
        (state / "current").write_text("legacy\n", encoding="utf-8")
        (state / "ready").write_text("", encoding="utf-8")
        (state / "keep").write_text("", encoding="utf-8")
        self.run_lut("apply", "alpha")
        self.assertEqual(self.slots_written(), [A19])
        self.assertFalse((state / "ready").exists(), "stale ready marker must be dropped")
        self.assertFalse((state / "keep").exists(), "stale keep marker must be dropped")

    def test_stale_writer_is_rejected(self):
        """A regtabwrite that ignores the slot argument must fail loudly.

        Deploying the new lut.sh next to the old tool would otherwise write the
        table into A19 while pointing the registry back at A18 -- the panel
        would report success and the viewfinder would never change.
        """
        self.stub(self.tools / "nx_regtabwrite.arm", OLD_REGT)
        self.run_lut("apply", "alpha")          # target A18: old tool agrees
        proc = subprocess.run(["sh", str(self.script), "apply", "beta"],
                              capture_output=True, text=True, env=self.env)
        self.assertNotEqual(proc.returncode, 0, "stale writer must not pass")
        self.assertIn("stale nx_regtabwrite.arm", proc.stdout)

    def test_script_carries_no_hardcoded_restore_of_single_slot(self):
        body = PRODUCT.read_text(encoding="utf-8")
        self.assertNotRegex(body, re.compile(r'SLOTW"\s+restore"\s+"\$SLOT"'))
        self.assertIn("SLOT_A18", body)
        self.assertIn("SLOT_A19", body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
