#!/usr/bin/env python3
"""记住上次打开位置：跨进程持久化。

不连相机、不写真实卡片：NXUI_STATE_DIR 指到临时目录。三次真实进程：
  1) 按两次 Right（选中第 3 项）后退出 → 必须写出 last-filmlab，内容是第 3 项的 key；
  2) 再启动 → READY 行的 sel= 必须是 2（不是 0）；
  3) 把文件改成一个不存在的 key → 再启动 → sel= 必须回到 0。

第 3 条是重点：库会增删条目，序号会错位，所以存的是名字；名字没了就安静
回到第一项，绝不能停在一个不存在的条目上。

用法: python3 test_last_choice.py   （在 WSL 里跑，需要 out/ 已构建）
"""
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
OUT = HERE / "out"
RF = Path(os.environ.get("NXUI_ROOTFS", "/opt/nxks2/rootfs-112"))
DISPLAY = ":98"


def start_xvfb(env):
    serverenv = env.copy()
    serverenv.update(LD_PRELOAD=str(OUT / "xvfb_local_paths.so"),
                     NXUI_XKB_BINDIR=str(OUT / "deps/usr/bin"))
    log = (OUT / "xvfb-last.log").open("w")
    proc = subprocess.Popen(
        [str(OUT / "deps/usr/bin/Xvfb"), DISPLAY, "-screen", "0", "720x480x24",
         "-nolisten", "tcp", "-ac", "-fp", str(OUT / "deps/usr/share/fonts/X11/misc")],
        env=serverenv, stdout=log, stderr=subprocess.STDOUT)
    time.sleep(.5)
    if proc.poll() is not None:
        raise RuntimeError((OUT / "xvfb-last.log").read_text())
    return proc


def ready_sel(text):
    match = re.search(r"READY .*sel=(\d+)", text)
    return int(match.group(1)) if match else None


def main() -> int:
    if not (OUT / "recipes.txt").is_file():
        print("missing out/recipes.txt; run verify_display.py once", file=sys.stderr)
        return 2
    keys = [line.split("|", 1)[0] for line in (OUT / "recipes.txt").read_text().splitlines() if line]
    assert len(keys) >= 4, keys

    with tempfile.TemporaryDirectory(prefix="nxui-last-") as folder:
        state = Path(folder)
        engine = state / "engine.sh"
        engine.write_text("#!/bin/sh\necho ok\n")
        engine.chmod(0o755)
        env = os.environ.copy()
        env.update(DISPLAY=DISPLAY, LC_ALL="C", NXUI_STATE_DIR=str(state),
                   LD_LIBRARY_PATH=str(OUT / "deps/usr/lib/x86_64-linux-gnu"))
        base = [str(OUT / "nxui"), "--root", str(REPO / "scripts"),
                "--recipes", str(OUT / "recipes.txt"), "--engine", str(engine)]

        server = start_xvfb(env)
        try:
            # 1) 选中第 3 项（index 2），退出时必须落盘
            proc = subprocess.Popen(base + ["--live", "--lifetime-ms", "1400"],
                                    env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            time.sleep(.5)
            for _ in range(2):
                subprocess.run([str(OUT / "test_input"), "key", "Right"], env=env, check=True, timeout=5)
                time.sleep(.35)
            text = proc.communicate(timeout=10)[0].decode(errors="replace")
            assert proc.returncode == 0, text
            last = state / "last-filmlab"
            assert last.is_file(), f"state file missing\n{text}"
            assert last.read_text().strip() == keys[2], (last.read_text(), keys[2])

            # 2) 再启动：位置必须被恢复
            second = subprocess.run(base + ["--live", "--lifetime-ms", "300"],
                                    env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=15)
            second_text = second.stdout.decode(errors="replace")
            assert ready_sel(second_text) == 2, second_text

            # 3) 名字不存在：安静回到第一项
            last.write_text("no_such_recipe\n")
            third = subprocess.run(base + ["--live", "--lifetime-ms", "300"],
                                   env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=15)
            third_text = third.stdout.decode(errors="replace")
            assert ready_sel(third_text) == 0, third_text
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()
    print("PASS last choice: written, restored, and reset to 0 on unknown key")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
