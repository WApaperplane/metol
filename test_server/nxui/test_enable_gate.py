"""NXUI 启用门禁的回归测试（2026-11-10）。

背景：`nxui.sh available` 曾经要求 `/opt/usr/nx-ks/nxui/enabled` 存在，而这个
标记只有开发者 SOP 里的 `nxui.sh enable` 会创建，release 包从来没带过它。
结果每一版装完 `available` 恒假，EV+AEL / MENU 全部落到 mod_gui 的老 popup。
本测试锁死新语义：**默认可用，只有显式 `disable` 才关**。
"""
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

BUSYBOX = """#!/bin/sh
case "$1" in
pidof) exit 1 ;;
killall) exit 0 ;;
head) shift; exec head "$@" ;;
*) echo "$1: applet not found" >&2; exit 127 ;;
esac
"""


class EnableGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="nxui-gate-")
        root = Path(self.tmp.name)
        (root / "nxui").mkdir()
        version = root / "version"
        version.write_text("NX500\n1.12\n")

        bb = root / "busybox"
        bb.write_text(BUSYBOX)
        bb.chmod(0o755)

        arm = root / "nxui" / "nxui.arm"
        arm.write_text("#!/bin/sh\nexit 0\n")
        arm.chmod(0o755)

        source = (REPO / "scripts/nxui.sh").read_text()
        source = source.replace("/opt/usr/nx-ks", str(root)).replace("/etc/version.info", str(version))
        self.script = root / "nxui.sh"
        self.script.write_text(source)
        self.script.chmod(0o755)
        self.root = root

    def tearDown(self):
        self.tmp.cleanup()

    def run_verb(self, *args):
        return subprocess.run(["sh", str(self.script), *args],
                              capture_output=True, text=True, timeout=15)

    def test_fresh_install_is_available_without_any_marker(self):
        """装完就可用：没有 enabled、没有 disabled 时必须返回 0。"""
        self.assertFalse((self.root / "nxui" / "enabled").exists())
        self.assertFalse((self.root / "nxui" / "disabled").exists())
        r = self.run_verb("available")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_disable_writes_marker_and_blocks(self):
        r = self.run_verb("disable")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.root / "nxui" / "disabled").exists())
        self.assertEqual(self.run_verb("available").returncode, 1)

    def test_enable_clears_disable_marker(self):
        self.run_verb("disable")
        r = self.run_verb("enable")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse((self.root / "nxui" / "disabled").exists())
        self.assertEqual(self.run_verb("available").returncode, 0)

    def test_legacy_enabled_flag_is_ignored_not_required(self):
        """旧相机上遗留的 enabled 标记既不是必要条件，也不该让 disable 失效。"""
        (self.root / "nxui" / "enabled").touch()
        self.assertEqual(self.run_verb("available").returncode, 0)
        self.run_verb("disable")
        self.assertEqual(self.run_verb("available").returncode, 1)
        self.assertFalse((self.root / "nxui" / "enabled").exists(),
                         "disable 应顺手清掉旧语义的 enabled")

    def test_missing_binary_is_unavailable(self):
        (self.root / "nxui" / "nxui.arm").unlink()
        self.assertEqual(self.run_verb("available").returncode, 1)

    def test_diag_reports_gate(self):
        r = self.run_verb("diag")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("available: yes", r.stdout)
        self.assertIn("disabled : no", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
