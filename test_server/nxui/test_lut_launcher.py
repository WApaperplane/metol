"""LUT 模式启动器：列表生成、去重、缓存失效与参数传递（无相机）。

产品脚本硬编码相机路径，测试只把这些赋值替换到临时沙箱，并用记录型桩
替代 nxui.arm / lut.sh / busybox。对应 scripts/nxui.sh 的 lut 分支：
名称列表只随目录 mtime 变化而重建，避免每次开面板都扫 exFAT。
"""
from pathlib import Path
import os
import subprocess
import tempfile
import time
import unittest

REPO = Path(__file__).resolve().parents[2]


class LutLauncherTests(unittest.TestCase):
    def test_look_list_is_generated_deduped_and_cached(self):
        with tempfile.TemporaryDirectory(prefix="nxui-lut-") as folder:
            root = Path(folder)
            mod = root / "nx-ks"
            looks = root / "looks"
            (mod / "nxui").mkdir(parents=True)
            looks.mkdir()
            version = root / "version"
            version.write_text("NX500\n1.12\n")
            calls = root / "calls"

            def script(path: Path, body: str):
                path.write_text("#!/bin/sh\n" + body)
                path.chmod(0o755)

            # 记录每次被调用的参数，供断言使用
            script(mod / "nxui/nxui.arm", 'printf "%s\\n" "$*" >> "$CALLS"\n')
            script(mod / "busybox", '''cmd="$1"; shift
case "$cmd" in
pidof) exit 1 ;;
killall) exit 0 ;;
setsid) exec "$@" ;;
*) exec "$cmd" "$@" ;;
esac
''')
            # lut.sh 只负责打印名称（按目录真实内容，否则"新增 look 必须出现"
            # 这条断言永远测不到东西）；同时记录一次调用，用于验证缓存。
            script(mod / "lut.sh",
                   'echo LUTLIST >> "$CALLS"\n'
                   f'ls "{looks.as_posix()}" 2>/dev/null | sed "s/\\.[^.]*$//" '
                   '| awk "!seen[\\$0]++"\n')
            (mod / "nxui/enabled").touch()
            (root / "lab").mkdir()

            for name in ("alpha.cube", "alpha.bin", "beta.bin"):
                (looks / name).write_bytes(b"x")

            text = (REPO / "scripts/nxui.sh").read_text(encoding="utf-8")
            for old, new in (("/tmp/nxui", str(root / "tmp-nxui")),
                             ("/opt/usr/nx-ks", str(mod)),
                             ("/mnt/mmc/looks", str(looks)),
                             ("/mnt/mmc/filmlab", str(root / "lab")),
                             ("/mnt/mmc/nxui", str(root / "card")),
                             ("/etc/version.info", str(version))):
                self.assertIn(old, text, old)
                text = text.replace(old, new)
            launcher = root / "nxui.sh"
            launcher.write_text(text, encoding="utf-8")

            env = dict(os.environ, CALLS=str(calls))

            def run():
                proc = subprocess.run(["sh", str(launcher), "lut"], env=env,
                                      capture_output=True, text=True, timeout=10)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

            def wait_ui(timeout=3.0):
                """nxui.sh backgrounds the panel, so the stub records its argv a
                moment later. Poll instead of sleeping a fixed time."""
                deadline = time.time() + timeout
                while time.time() < deadline:
                    lines = calls.read_text().splitlines() if calls.exists() else []
                    if lines and "--lut" in lines[-1]:
                        return lines
                    time.sleep(0.02)
                self.fail(f"panel was not launched: {lines if calls.exists() else []}")

            run()
            arg_lines = wait_ui()
            rec = root / "tmp-nxui-look.rec"
            self.assertTrue(rec.exists())
            lines = rec.read_text().splitlines()
            # 去重（alpha 同时有 .cube 与 .bin）且保持 glob 顺序
            self.assertEqual([l.split("|")[0] for l in lines], ["alpha", "beta"])
            for line in lines:
                self.assertEqual(len(line.split("|")), 9, line)
                self.assertEqual(line.split("|")[1], line.split("|")[0])
            arg_lines = calls.read_text().splitlines()
            self.assertEqual(arg_lines.count("LUTLIST"), 1)
            self.assertIn("--lut", arg_lines[-1])
            self.assertIn(str(rec), arg_lines[-1])

            # 目录未变：不再调用 lut.sh，直接复用配方表
            run()
            self.assertEqual(calls.read_text().splitlines().count("LUTLIST"), 1)

            # 目录变化（新增 look）：必须重建，并让新名字出现。
            # 启动器用 `[ "$LOOKS" -nt "$LU.stamp" ]` 判缓存，秒级精度，
            # 同一秒内写完文件再跑会被判为"未变"，所以先跨过一秒。
            time.sleep(1.1)
            (looks / "gamma.cube").write_bytes(b"x")
            run()
            self.assertEqual(calls.read_text().splitlines().count("LUTLIST"), 2)
            self.assertIn("gamma", (root / "tmp-nxui-look.rec").read_text())


if __name__ == "__main__":
    unittest.main(verbosity=2)
