#!/usr/bin/env python3
"""Run the actual camera shell adapter against recording tools, without hardware.

Run in WSL: python3 test_lut_backend_shell.py
NXWA_BACKEND_SCRIPT can select a saved baseline to demonstrate regressions.
Only temporary fixture paths are written; no camera, mounts or device IO.
"""
import json
import importlib.util
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(os.environ.get("NXWA_BACKEND_SCRIPT", Path(__file__).with_name("lut_backend.sh")))


class ShellBackendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="nxwa-lut-shell-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.mod = self.root / "filmlab"
        self.luts = self.mod / "luts"
        self.luts.mkdir(parents=True)
        self.calls = self.root / "calls.txt"
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.env = dict(os.environ, NXWA_MOD_ROOT=str(self.root / "nx-ks"),
                        NXWA_LUT_MOD=str(self.mod), NXWA_TEST_CALLS=str(self.calls),
                        PATH=str(self.bin) + os.pathsep + os.environ["PATH"])
        self.tool(self.bin / "pidof", "exit 1\n")
        self.tool(self.bin / "ps", "exit 0\n")
        self.tool(self.mod / "lutpick.sh", r'''
printf '%s\n' "$@" >> "$NXWA_TEST_CALLS"
[ "${NXWA_TEST_APPLY_RC:-0}" = 0 ] || exit "$NXWA_TEST_APPLY_RC"
case "$*" in
  *--dry*) exit 0 ;;
esac
if [ "$1" = apply ]; then
  printf '%s\n' "$2" > "$NXWA_LUT_MOD/luts/current"
  case "$*" in *--ch0*) sel=0 ;; *) sel=1 ;; esac
  printf '%s\n' "$sel" > "$NXWA_LUT_MOD/luts/current.sel"
fi
''')
        self.tool(self.mod / "lutload.arm", r'''
printf '%s\n' "restore:$*" >> "$NXWA_TEST_CALLS"
exit "${NXWA_TEST_RESTORE_RC:-0}"
''')
        (self.luts / "demo.bin").write_bytes(bytes(19652))

    @staticmethod
    def tool(path, body):
        path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
        path.chmod(0o755)

    def run_backend(self, *args):
        result = subprocess.run([shutil.which("sh"), str(SCRIPT), *args],
                                env=self.env, capture_output=True, text=True, timeout=10)
        self.assertEqual(len(result.stdout.splitlines()), 1, result.stdout + result.stderr)
        return result.returncode, json.loads(result.stdout)

    def recorded(self):
        return self.calls.read_text().splitlines() if self.calls.exists() else []

    def test_apply_really_requests_lut1(self):
        rc, result = self.run_backend("apply", "demo")
        self.assertEqual(rc, 0)
        self.assertEqual(self.recorded(), ["apply", "demo", "--ch1"])
        self.assertEqual(result["sel_requested"], 1)
        self.assertFalse(result["hardware_verified"])
        self.assertEqual(result["guard"], 0)

    def test_dry_run_does_not_claim_preview_or_change_bookkeeping(self):
        rc, result = self.run_backend("apply", "demo", "--dry")
        self.assertEqual(rc, 0)
        self.assertEqual(self.recorded(), ["apply", "demo", "--ch1", "--dry"])
        self.assertTrue(result["dry"])
        self.assertFalse(result["hardware_verified"])
        self.assertFalse((self.luts / "current").exists())

    def test_legacy_bookkeeping_does_not_invent_a_channel(self):
        (self.luts / "current").write_text("demo\n")
        rc, result = self.run_backend("status")
        self.assertEqual(rc, 0)
        self.assertEqual(result["current"], "demo")
        self.assertIsNone(result["sel"])
        self.assertIsNone(result["sel_requested"])
        self.assertFalse(result["hardware_verified"])

    def test_lut0_is_explicit_and_status_preserves_requested_channel(self):
        rc, result = self.run_backend("apply", "demo", "--sel", "0")
        self.assertEqual(rc, 0)
        self.assertEqual(self.recorded(), ["apply", "demo", "--ch0"])
        self.assertEqual(result["sel_requested"], 0)
        self.assertFalse(result["still_verified"])
        rc, status = self.run_backend("status")
        self.assertEqual(rc, 0)
        self.assertIsNone(status["sel"])
        self.assertEqual(status["sel_requested"], 0)

    def test_lut0_dry_run_keeps_prior_channel(self):
        (self.luts / "current").write_text("demo\n")
        (self.luts / "current.sel").write_text("1\n")
        rc, result = self.run_backend("apply", "demo", "--dry", "--sel", "0")
        self.assertEqual(rc, 0)
        self.assertEqual(self.recorded(), ["apply", "demo", "--ch0", "--dry"])
        self.assertTrue(result["dry"])
        self.assertEqual((self.luts / "current.sel").read_text(), "1\n")

    def test_lut0_rejects_active_guard_before_calling_loader(self):
        self.tool(self.bin / "pidof", "echo 123\nexit 0\n")
        rc, result = self.run_backend("apply", "demo", "--sel", "0")
        self.assertNotEqual(rc, 0)
        self.assertEqual(result["error"], "guard_conflict")
        self.assertEqual(self.recorded(), [])

    def test_bad_channel_metadata_is_not_reported_as_a_channel(self):
        (self.luts / "current").write_text("demo\n")
        (self.luts / "current.sel").write_text("2\n")
        rc, result = self.run_backend("status")
        self.assertEqual(rc, 0)
        self.assertIsNone(result["sel_requested"])

    def test_apply_failure_is_not_success(self):
        self.env["NXWA_TEST_APPLY_RC"] = "7"
        rc, result = self.run_backend("apply", "demo")
        self.assertNotEqual(rc, 0)
        self.assertFalse(result["ok"])
        self.assertEqual(result["rc"], 7)
        self.assertFalse((self.luts / "current").exists())

    def test_rollback_restores_factory_without_loading_identity(self):
        (self.luts / "current").write_text("demo\n")
        (self.luts / "current.sel").write_text("0\n")
        rc, result = self.run_backend("rollback")
        self.assertEqual(rc, 0)
        self.assertTrue(result["ok"])
        self.assertFalse(result["identity_used"])
        self.assertEqual(self.recorded(), ["restore:restore"])
        self.assertFalse((self.luts / "current").exists())
        self.assertFalse((self.luts / "current.sel").exists())

    def test_restore_failure_preserves_bookkeeping(self):
        (self.luts / "current").write_text("demo\n")
        self.env["NXWA_TEST_RESTORE_RC"] = "9"
        rc, result = self.run_backend("rollback")
        self.assertNotEqual(rc, 0)
        self.assertFalse(result["ok"])
        self.assertEqual(result["restore_rc"], 9)
        self.assertEqual((self.luts / "current").read_text(), "demo\n")

    def test_table_missing_is_rejected_before_tool_call(self):
        rc, result = self.run_backend("apply", "missing")
        self.assertNotEqual(rc, 0)
        self.assertEqual(result["error"], "table_not_found")
        self.assertEqual(self.recorded(), [])

    def test_path_and_option_inputs_are_rejected_before_tool_call(self):
        for args in [("../demo",), ("demo", "--typo"), ("bad\nname",),
                     ("demo", "--sel"), ("demo", "--sel", "2"),
                     ("demo", "--sel", "0", "--sel", "1"),
                     ("demo", "--sel", "0", "--dry", "--typo")]:
            with self.subTest(args=args):
                rc, result = self.run_backend("apply", *args)
                self.assertNotEqual(rc, 0)
                self.assertFalse(result["ok"])
                self.assertEqual(self.recorded(), [])

    def test_remote_driver_keeps_table_name_as_one_shell_argument(self):
        spec = importlib.util.spec_from_file_location("nxwa_lut_driver", Path(__file__).with_name("lut_backend.py"))
        driver = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(driver)
        name = "demo; touch /tmp/unwanted"
        response = subprocess.CompletedProcess([], 0, stdout='{"ok":false}\n', stderr="")
        with mock.patch.object(driver.subprocess, "run", return_value=response) as invoke:
            self.assertEqual(driver.run_remote(["apply", name]), {"ok": False})
        command = invoke.call_args.args[0][-1]
        self.assertEqual(shlex.split(command), ["sh", "/mnt/mmc/filmlab/lut_backend.sh", "apply", name])

    def real_picker(self):
        """Use both production shells; replace only the ARM/device boundary."""
        shutil.copyfile(Path(__file__).with_name("lutpick.sh"), self.mod / "lutpick.sh")
        self.env["NXWA_BUSYBOX"] = str(self.bin / "busybox")
        self.tool(self.bin / "busybox", 'if [ "$1" = sleep ]; then exit 0; fi\nexec "$@"\n')
        self.tool(self.mod / "cmapick2.arm", '''
printf 'cmap:%s\\n' "$@" >> "$NXWA_TEST_CALLS"
[ "${NXWA_TEST_NO_HIT:-0}" = 1 ] || printf '4KB 粒度命中: 0x8f81e000 起\\n'
exit "${NXWA_TEST_PICK_RC:-0}"
''')
        self.tool(self.mod / "cmasafe.arm", '''
printf 'safe:%s\\n' "$@" >> "$NXWA_TEST_CALLS"
exit "${NXWA_TEST_SAFE_RC:-0}"
''')
        self.tool(self.mod / "lutapi.arm", '''
printf 'api:%s\\n' "$@" >> "$NXWA_TEST_CALLS"
exit "${NXWA_TEST_API_RC:-0}"
''')

    def test_real_picker_receives_lut0_and_writes_correct_bookkeeping(self):
        self.real_picker()
        rc, result = self.run_backend("apply", "demo", "--sel", "0")
        self.assertEqual(rc, 0)
        self.assertFalse(result["still_verified"])
        self.assertEqual(self.recorded(), ["cmap:--need19652", "safe:0x8f81e000",
                         "api:load", "api:" + str(self.luts / "demo.bin"),
                         "api:0x8f81e000", "api:0", "api:1", "api:17",
                         "api:2", "api:300", "api:0"])
        self.assertEqual((self.luts / "current.sel").read_text(), "0\n")

    def test_real_picker_default_lut1_reaches_api(self):
        self.real_picker()
        rc, _ = self.run_backend("apply", "demo")
        self.assertEqual(rc, 0)
        self.assertEqual(self.recorded()[5], "api:1")
        self.assertEqual((self.luts / "current.sel").read_text(), "1\n")

    def test_real_picker_dry_run_never_invokes_api(self):
        self.real_picker()
        rc, result = self.run_backend("apply", "demo", "--sel", "0", "--dry")
        self.assertEqual(rc, 0)
        self.assertTrue(result["dry"])
        self.assertEqual(self.recorded(), ["cmap:--need19652", "safe:0x8f81e000"])
        self.assertFalse((self.luts / "current").exists())
        self.assertFalse((self.luts / "current.sel").exists())

    def test_real_picker_off_dry_run_never_loads_identity(self):
        self.real_picker()
        (self.luts / "_identity.bin").write_bytes(bytes(19652))
        result = subprocess.run([shutil.which("sh"), str(self.mod / "lutpick.sh"),
                                 "off", "--dry"], env=self.env,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.recorded(), ["cmap:--need19652", "safe:0x8f81e000"])
        self.assertFalse((self.luts / "current").exists())

    def test_real_picker_rejects_missing_hit_before_safety_or_load(self):
        self.real_picker()
        self.env["NXWA_TEST_NO_HIT"] = "1"
        rc, result = self.run_backend("apply", "demo", "--sel", "0")
        self.assertNotEqual(rc, 0)
        self.assertFalse(result["ok"])
        self.assertEqual(self.recorded(), ["cmap:--need19652"])

    def test_real_picker_safety_rejection_never_loads(self):
        self.real_picker()
        self.env["NXWA_TEST_SAFE_RC"] = "4"
        rc, result = self.run_backend("apply", "demo", "--sel", "0")
        self.assertNotEqual(rc, 0)
        self.assertFalse(result["ok"])
        self.assertEqual(self.recorded(), ["cmap:--need19652", "safe:0x8f81e000"])

    def test_real_picker_api_failure_keeps_previous_channel(self):
        self.real_picker()
        (self.luts / "current").write_text("prior\n")
        (self.luts / "current.sel").write_text("1\n")
        self.env["NXWA_TEST_API_RC"] = "7"
        rc, result = self.run_backend("apply", "demo", "--sel", "0")
        self.assertNotEqual(rc, 0)
        self.assertFalse(result["ok"])
        self.assertEqual((self.luts / "current").read_text(), "prior\n")
        self.assertEqual((self.luts / "current.sel").read_text(), "1\n")

    def test_real_picker_rejects_channel_conflicts_and_typos(self):
        self.real_picker()
        for options in [("--ch0", "--ch1"), ("--typo",), ("--ch1", "--ch1")]:
            with self.subTest(options=options):
                result = subprocess.run([shutil.which("sh"), str(self.mod / "lutpick.sh"),
                                         "apply", "demo", *options], env=self.env,
                                        capture_output=True, text=True, timeout=10)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.recorded(), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
