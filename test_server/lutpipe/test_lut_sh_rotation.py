#!/usr/bin/env python3
"""Run the actual LUT shell with simulated settings events and registry/slot IO.

A slot/registry write does not update the simulated hardware load source; only
an official settings event can do that. No camera or device IO is performed.
Set NXWA_SH to a POSIX shell executable on Windows.
"""
from pathlib import Path
import os
import shutil
import signal
import subprocess
import tempfile
import time
import unittest

PRODUCT = Path(__file__).resolve().parents[2] / 'scripts' / 'lut.sh'
SH = os.environ.get('NXWA_SH') or shutil.which('sh')
A18, A19 = '0x81119f00', '0x8111ec00'

def posix(path):
    value = Path(path).as_posix()
    return '/' + value[0].lower() + value[2:] if os.name == 'nt' else value

SLOT = r'''
printf 'SLOT %s %s\n' "$1" "$2" >> "$NXWA_TEST_ROOT/calls"
case "$1" in
  read) head -c 19712 /dev/zero > "$3"; echo 'SLOT dumped' ;;
  *) [ "${NXWA_TEST_WRITE_FAIL:-0}" = 0 ] || exit 7; echo 'READBACK ok' ;;
esac
'''
REGISTRY = r'''
root=$NXWA_TEST_ROOT
printf 'REGT %s\n' "$*" >> "$root/calls"
case "$1" in
  patch1)
    [ "${NXWA_TEST_OLD_WRITER:-0}" = 0 ] || exit 0
    printf '%s\n' "$2" | tr A-F a-f > "$root/view1" ;;
  patch) printf '%s\n' "$2" | tr A-F a-f > "$root/view3" ;;
  restore) echo 0x81115200 > "$root/view3" ;;
  still-set|still-write) echo "STILL6 after : $2"; echo 'READBACK ok' ;;
  status)
    echo "VIEW4 : 0x810fd100 $(cat "$root/view1") 0x81106b00 $(cat "$root/view3")"
    echo 'STILL6: 0x81119f00 0x81115200 0x8111ec00 0x8110b800 0x81106b00 0x81110500'
    echo "REGS: 0x00000001 0x00000100 0x00000000 $(cat "$root/load") 0x00000000" ;;
esac
'''
SETTINGS = r'''
root=$NXWA_TEST_ROOT
printf 'CAP %s\n' "$*" >> "$root/calls"
case "$3:$4" in
  getusr:108)
    [ "${NXWA_TEST_READ_FAIL:-0}" = 0 ] || exit 1
    if [ "$(cat "$root/oled")" = 0x6c0001 ]; then
      printf '\000UserData is OLEDCOLOR_ON (0x6c0001)\n'
    else printf '\000UserData is OLEDCOLOR_OFF (0x6c0000)\n'; fi ;;
  getusr:50)
    if [ "${NXWA_TEST_ADOBE:-0}" = 1 ]; then echo 'UserData is COLORSPACE_ADOBERGB (0x320001)'
    else echo 'UserData is COLORSPACE_SRGB (0x320000)'; fi ;;
  getusr:62) echo 'UserData is SMARTFILTERTYPE_OFF (0x3e0000)' ;;
  setusr:108)
    echo "$5" > "$root/oled"
    if [ "${NXWA_TEST_NO_LOAD:-0}" = 0 ]; then
      case "$5" in 0x6c0001) cat "$root/view1" ;; *) cat "$root/view3" ;; esac > "$root/load"
    fi
    echo 'UserData is set' ;;
  *) exit 2 ;;
esac
'''
PREFERENCES = r'''
[ "${NXWA_TEST_READ_FAIL:-0}" = 0 ] || exit 1
case "$3" in
  0x0a704) echo "value = $(cat "$NXWA_TEST_ROOT/oled_pref") (0x0)" ;;
  0x0a3d0) echo "value = ${NXWA_TEST_SMART:-0} (0x0)" ;;
  *) exit 2 ;;
esac
'''

@unittest.skipUnless(SH and shutil.which('flock'), 'requires a POSIX shell and flock (run in WSL)')
class SwitchingTests(unittest.TestCase):
    def setUp(self):
        scratch = PRODUCT.parents[1] / '.tmp'
        scratch.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='nxwa-lut-refresh-', dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.mod = self.root / 'mod'
        self.tools = self.mod / 'lut'
        self.looks = self.root / 'looks'
        for p in (self.tools, self.looks): p.mkdir(parents=True)
        self.env = dict(os.environ, NXWA_TEST_ROOT=posix(self.root))
        self.env['PATH'] = str(Path(SH).parent) + os.pathsep + self.env['PATH']
        self.tool(self.tools / 'nx_slotwrite.arm', SLOT)
        self.tool(self.tools / 'nx_regtabwrite.arm', REGISTRY)
        self.tool(self.tools / 'cube2lut.arm', 'exit 9\n')
        self.tool(self.mod / 'busybox', 'if [ "$1" = sleep ]; then exit 0; fi\nexec "$@"\n')
        self.tool(self.root / 'st', SETTINGS)
        self.tool(self.root / 'prefman', PREFERENCES)
        for name in ('alpha', 'beta', 'gamma'):
            (self.looks / (name + '.bin')).write_bytes(bytes(19712))
        for name, value in (('view1', '0x81101e00'), ('view3', '0x81115200'),
                            ('load', '0x81101e00'), ('oled', '0x6c0001'), ('oled_pref', '1')):
            self.put(name, value)
        body = PRODUCT.read_text(encoding='utf-8')
        for old, new in {
            'D=/opt/usr/nx-ks': 'D=' + posix(self.mod),
            'CAP=/usr/bin/st': 'CAP=' + posix(self.root / 'st'),
            'PREF=/usr/bin/prefman': 'PREF=' + posix(self.root / 'prefman'),
            'LAB=/mnt/mmc/looks': 'LAB=' + posix(self.looks),
            'ST=/mnt/mmc/lut/state': 'ST=' + posix(self.root / 'state'),
            'STILLBAK=/mnt/mmc/nxwa_regtab_20261018/still6_orig.bin':
                'STILLBAK=' + posix(self.root / 'still6_orig.bin'),
        }.items():
            self.assertIn(old, body)
            body = body.replace(old, new)
        self.script = self.root / 'lut.sh'
        self.script.write_text(body, encoding='utf-8', newline='\n')

    @staticmethod
    def tool(path, body):
        path.write_text('#!/bin/sh\n' + body, encoding='utf-8', newline='\n')
        path.chmod(0o755)

    def put(self, name, value):
        (self.root / name).write_text(value + '\n', encoding='utf-8', newline='\n')

    def get(self, name):
        # A rejected run may exit before calling any stub, so no log exists yet.
        path = self.root / name
        return path.read_text().strip() if path.exists() else ''

    def run_lut(self, *args, ok=True):
        p = subprocess.run([SH, posix(self.script), *args], env=self.env,
                           capture_output=True, text=True, timeout=20)
        self.assertEqual(p.returncode == 0, ok, p.stdout + p.stderr)
        return p.stdout

    def test_three_switches_really_reload_alternating_slots(self):
        for name, slot in (('alpha', A18), ('beta', A19), ('gamma', A18)):
            self.assertIn('LOADED ' + slot, self.run_lut('apply', name))
            self.assertEqual(self.get('load'), slot)
            self.assertEqual(self.get('view1'), slot)
            self.assertEqual(self.get('view3'), slot)
            self.assertEqual(self.get('oled'), '0x6c0001')
        self.assertIn('ACTIVE gamma (slot a18)', self.run_lut('status'))

    def test_oled_off_is_supported_and_preserved(self):
        self.put('oled', '0x6c0000')
        self.put('oled_pref', '0')
        self.put('load', '0x81115200')
        self.run_lut('apply', 'alpha')
        self.assertEqual(self.get('load'), A18)
        self.assertEqual(self.get('oled'), '0x6c0000')

    def test_actual_load_overrides_stale_active_marker(self):
        (self.root / 'state').mkdir()
        self.put('state/active', 'a19')
        self.put('load', A18)
        self.run_lut('apply', 'alpha')
        self.assertEqual(self.get('load'), A19)

    def test_no_load_never_reports_success_or_commits_new_name(self):
        self.run_lut('apply', 'alpha')
        self.env['NXWA_TEST_NO_LOAD'] = '1'
        out = self.run_lut('apply', 'beta', ok=False)
        self.assertIn('camera still loads', out)
        self.assertNotIn('OK applied', out)
        self.assertEqual(self.get('state/current'), 'alpha')
        self.assertEqual(self.get('oled'), '0x6c0001')
        self.assertFalse((self.root / 'state/.lock').exists())

    def test_writer_without_patch1_is_rejected(self):
        self.env['NXWA_TEST_OLD_WRITER'] = '1'
        self.assertIn('requires patch1 support', self.run_lut('apply', 'alpha', ok=False))
        self.assertFalse((self.root / 'state/current').exists())

    def test_failed_slot_write_never_changes_registry_or_settings(self):
        self.env['NXWA_TEST_WRITE_FAIL'] = '1'
        self.run_lut('apply', 'alpha', ok=False)
        self.assertEqual(self.get('view1'), '0x81101e00')
        self.assertEqual(self.get('view3'), '0x81115200')
        self.assertNotIn('CAP cap capdtm setusr', self.get('calls'))

    def test_unsupported_profile_and_unreadable_setting_fail_before_slot_write(self):
        for flag in ('NXWA_TEST_SMART', 'NXWA_TEST_READ_FAIL'):
            with self.subTest(flag=flag):
                self.env[flag] = '1'
                self.run_lut('apply', 'alpha', ok=False)
                self.assertNotIn('SLOT write', self.get('calls'))
                del self.env[flag]

    def test_adobe_native_branch_is_rejected_before_slot_write(self):
        self.put('load', '0x81106b00')
        self.run_lut('apply', 'alpha', ok=False)
        self.assertNotIn('SLOT write', self.get('calls'))

    def test_interrupted_temporary_oled_value_returns_to_app_preference(self):
        self.put('oled', '0x6c0000')
        self.run_lut('apply', 'alpha')
        self.assertEqual(self.get('oled'), '0x6c0001')

    def test_off_restores_both_view_branches_and_reloads_factory(self):
        self.run_lut('apply', 'alpha')
        self.run_lut('apply', 'beta')
        self.run_lut('off')
        self.assertEqual(self.get('view1'), '0x81101e00')
        self.assertEqual(self.get('view3'), '0x81115200')
        self.assertEqual(self.get('load'), '0x81101e00')
        self.assertEqual(self.get('oled'), '0x6c0001')
        self.assertFalse((self.root / 'state/current').exists())
        self.assertIn('SLOT restore 0x81119F00', self.get('calls'))
        self.assertIn('SLOT restore 0x8111EC00', self.get('calls'))

    @unittest.skipUnless(os.name == 'posix', 'process-group kill fixture requires POSIX')
    def test_parallel_writer_is_refused_and_sigkill_releases_lock(self):
        self.tool(self.root / 'st', '''
if [ "${NXWA_TEST_HOLD:-0}" = 1 ]; then
    echo ready > "$NXWA_TEST_ROOT/holding"
    sleep 30
fi
''' + SETTINGS)
        env = dict(self.env, NXWA_TEST_HOLD='1')
        worker = subprocess.Popen([SH, posix(self.script), 'apply', 'alpha'], env=env,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  start_new_session=True)
        try:
            deadline = time.monotonic() + 3
            while not (self.root / 'holding').exists() and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertTrue((self.root / 'holding').exists())
            self.assertIn('another LUT operation', self.run_lut('apply', 'beta', ok=False))
            os.killpg(worker.pid, signal.SIGKILL)
            worker.communicate(timeout=3)
            # The lock inode remains. Its kernel lock must not survive death.
            self.assertTrue((self.root / 'state/.writer.lock').exists())
            self.run_lut('apply', 'beta')
            self.assertEqual(self.get('state/current'), 'beta')
        finally:
            if worker.poll() is None:
                os.killpg(worker.pid, signal.SIGKILL)
                worker.communicate(timeout=3)

if __name__ == '__main__':
    unittest.main(verbosity=2)
