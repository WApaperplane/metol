"""Exercise launch caching and the physical-key entry without camera commands."""
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

class LauncherTests(unittest.TestCase):
    def test_cache_refresh_and_quick_key_path(self):
        with tempfile.TemporaryDirectory(prefix="nxui-launch-") as folder:
            root = Path(folder); lab = root / "lab"; lab.mkdir(); (root / "nxui").mkdir()
            version = root / "version"; version.write_text("NX500\n1.12\n")
            log = root / "calls"
            def script(name, source):
                path = root / name; path.write_text("#!/bin/sh\n" + source); path.chmod(0o755)
            script("busybox", '''cmd="$1"; shift
case "$cmd" in
pidof) exit 1 ;;
killall) exit 0 ;;
setsid) exec "$@" ;;
nice) shift 2; exec "$@" ;;
cksum) exec cksum "$@" ;;
*) echo "$cmd: applet not found" >&2; exit 127 ;;
esac
''')
            script("nxui/nxui.arm", 'echo UI >> "$CALLS"\n')
            script("filmlab.sh", f'echo EXPORT >> "$CALLS"\necho test > "{lab}/recipes.txt"\n')
            script("gen_menu.sh", 'echo MAIN >> "$CALLS"\n')
            script("br_menu.sh", 'echo UNEXPECTED_PREPARE >> "$CALLS"\n')
            launcher = (REPO / "scripts/nxui.sh").read_text().replace("/tmp/nxui", str(root / "nxui-tmp")).replace("/mnt/mmc/nxui", str(root / "card")).replace("/opt/usr/nx-ks", str(root)).replace("/mnt/mmc/filmlab", str(lab)).replace("/etc/version.info", str(version))
            script("nxui.sh", launcher)
            (root / "nxui/enabled").touch()
            recipe = lab / "recipes.json"; recipe.write_text("first")
            env = dict(os.environ, CALLS=str(log))
            def run(mode):
                result = subprocess.run(["sh", str(root / "nxui.sh"), mode], env=env, capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            run("menu"); run("menu"); run("filmlab")
            self.assertEqual(log.read_text().splitlines().count("EXPORT"), 1)
            self.assertNotIn("UNEXPECTED_PREPARE", log.read_text())
            # ★ 启动器是 `setsid ... &` 后立即 exit 0，只看 returncode 抓不到
            #   "busybox 把 nxui.arm 当 applet" 这类静默失败。必须断言二进制真被执行。
            time.sleep(0.3)
            self.assertGreaterEqual(log.read_text().splitlines().count("UI"), 1,
                                    "launcher must actually exec nxui.arm")
            recipe.write_text("other")  # same byte count; hash must detect a content change
            run("filmlab")
            self.assertEqual(log.read_text().splitlines().count("EXPORT"), 2)
            (lab / "recipes.txt").unlink(); run("filmlab")
            self.assertEqual(log.read_text().splitlines().count("EXPORT"), 3)
            key = (REPO / "scripts/EV_EV.sh").read_text().replace("/opt/usr/nx-ks", str(root))
            script("EV_EV.sh", key)
            result = subprocess.run(["bash", str(root / "EV_EV.sh")], env=env, capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(log.read_text().splitlines().count("MAIN"), 3)

if __name__ == "__main__": unittest.main(verbosity=2)
