"""Real X11 events + controlled subprocess backend, on host and ARM builds."""
from pathlib import Path
import os
import subprocess
import tempfile
import time

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"

def run_interaction(prefix, env, label):
    with tempfile.TemporaryDirectory(prefix="nxui-ui-") as temp:
        root = Path(temp); (root / "auto").mkdir()
        calls = root / "calls"
        engine = root / "engine.sh"
        engine.write_text('#!/bin/sh\nprintf "%s %s\\n" "$1" "$2" >> "$NXUI_CALLS"\nsleep 0.45\nexit "${NXUI_FAIL:-0}"\n')
        env = dict(env, NXUI_CALLS=str(calls))
        def launch(*args):
            log = root / f"run-{time.monotonic_ns()}.log"
            stream = log.open("w")
            p = subprocess.Popen(prefix + ["--live", "--root", str(root), "--engine", str(engine), "--recipes", str(OUT / "recipes.txt"), "--lifetime-ms", "7000"] + list(args), env=env, stdout=stream, stderr=subprocess.STDOUT)
            try:
                for _ in range(50):
                    if "READY" in log.read_text(): return p, stream, log
                    if p.poll() is not None: raise AssertionError(log.read_text())
                    time.sleep(.05)
                raise AssertionError("UI did not initialize\n" + log.read_text())
            except BaseException:
                p.terminate(); p.wait(timeout=5); stream.close(); raise
        def send(*args):
            subprocess.run([str(OUT / "test_input")] + list(args), env=env, check=True, timeout=5)
        def finish(p, stream, log):
            try:
                assert p.wait(timeout=6) == 0, log.read_text()
                return log.read_text()
            finally:
                if p.poll() is None: p.kill(); p.wait()
                stream.close()
        p, stream, log = launch()
        try:
            send("key", "Right", "3"); time.sleep(.35)
            send("key", "Right", "2"); time.sleep(1.1)
            lines = calls.read_text().splitlines()
            # Only the final item of each burst may reach the backend.
            keys = [line.split("|", 1)[0] for line in (OUT / "recipes.txt").read_text().splitlines()]
            assert lines == [f"preview {keys[3]}", f"preview {keys[5]}"], lines
            # Explicitly tapping the highlighted recipe must reapply it, since
            # physical camera controls may have changed ISP state in between.
            send("click", "350", "60", "5"); time.sleep(.9)
            assert calls.read_text().splitlines() == lines + [f"preview {keys[5]}"], calls.read_text()
            # 还原按钮在第三列（中心 x=448）：PW 的"还原"必须真的把 neutral 交给引擎。
            # 先等上一次 preview 的后端结束 —— 有子进程在跑时按钮只会提示"请稍候"。
            time.sleep(1.2)
            send("click", "448", "157", "5")
            deadline = time.time() + 4
            while time.time() < deadline:
                if calls.read_text().splitlines()[-1].startswith("neutral"):
                    break
                time.sleep(.05)
            assert calls.read_text().splitlines()[-1].startswith("neutral"), (calls.read_text(), lines, log.read_text()[-600:])
            # A row that is already applied saves straight to flash, so move the
            # selection first: saving then has to go through apply + commit.
            send("key", "Right"); time.sleep(.15)
            # Save row sits at y=144..170（24 标题 + 60 条 + 16 状态 + 16 滚动条 + 间距）。
            # 10-19 加滚动条后面板从 192 加到 208，按钮行整体下移 21px。
            # x=272, not 350: the row now has four buttons (‹ 上一个 / 保存并关闭 /
            # 还原 / 下一个 ›), so each column is (720-24-3*8)/4 = 168 px wide and
            # "保存并关闭" spans 188..356.
            send("click", "272", "157", "5")
            text = finish(p, stream, log)
            assert calls.read_text().splitlines()[-1] == f"commit {keys[6]}", (calls.read_text(), text)
            assert "ok=1" in text
        finally:
            if p.poll() is None: p.terminate(); p.wait(timeout=6)
            stream.close()
        calls.unlink(); env["NXUI_FAIL"] = "7"
        p, stream, log = launch()
        try:
            send("key", "Right"); time.sleep(1.2)
            assert len(calls.read_text().splitlines()) == 1, "Failure caused retry loop"
            send("key", "Escape")
            assert "ok=0" in finish(p, stream, log)
        finally:
            if p.poll() is None: p.terminate(); p.wait(timeout=6)
            stream.close()
        env.pop("NXUI_FAIL"); calls.unlink()
        generated = Path(f"/tmp/gui_br.nxui-test-{os.getpid()}-{label}")
        (root / "gui_ini.NX500").write_text("button|子菜单|@/opt/usr/nx-ks/gui_settings.NX500\ncheckbox|测试开关|demo.sh\n" + f"button|动态菜单|@{generated}\n")
        (root / "gui_settings.NX500").write_text("button|返回|@/opt/usr/nx-ks/gui_ini.NX500\n")
        (root / "br_menu.sh").write_text(f'#!/bin/bash\necho PREPARE >> "$NXUI_CALLS"\nsync;sync;sync\nprintf "button|返回|@/opt/usr/nx-ks/gui_ini.NX500\\n" > {generated}\n')
        (root / "sync").write_text('#!/bin/sh\necho UNEXPECTED_SYNC >> "$NXUI_CALLS"\nexit 9\n')
        (root / "sync").chmod(0o755)
        for name, action in [("demo.sh", "ON"), ("off_demo.sh", "OFF")]:
            file = root / name
            file.write_text(f'#!/bin/sh\necho {action} >> "$NXUI_CALLS"\n'); file.chmod(0o755)
        p, stream, log = launch("--menu", "gui_ini.NX500")
        try:
            send("click", "535", "65"); time.sleep(.8)
            assert (root / "auto/demo.sh").exists(), log.read_text()
            send("click", "535", "65"); time.sleep(.8)
            assert not (root / "auto/demo.sh").exists(), log.read_text()
            assert calls.read_text().splitlines() == ["ON", "OFF"]
            assert not generated.exists(), "Submenu work ran before it was requested"
            send("click", "160", "125"); time.sleep(.8)
            assert calls.read_text().splitlines() == ["ON", "OFF", "PREPARE"]
            assert f"MENU file={generated}" in log.read_text(), log.read_text()
            send("click", "160", "65"); time.sleep(.2)
            send("click", "160", "65"); time.sleep(.2)
            assert "gui_settings.NX500" in log.read_text()
            send("key", "Escape"); finish(p, stream, log)
        finally:
            if p.poll() is None: p.terminate(); p.wait(timeout=6)
            stream.close()
            generated.unlink(missing_ok=True)
    print(f"PASS {label}: real X11 input, coalescing, serialized apply, save, failure, checkbox on/off, submenu")


def run_lut_interaction(prefix, env, label):
    """LUT 面板的「还原原厂」必须真的调用引擎的 off；滚动条拖动/点轨道必须真的换项。

    这条链与 PW 的 neutral 分开：LUT 走 lut.sh off（写槽 + 两张登记表），
    PW 走 filmlab.sh neutral（直推中性），两条都由按钮触发，但命令不同、
    前提也不同。只测一条会漏掉另一条的回归。

    滚动条用 nk_slider_float 时拖动是断的（滑块 26px、每步 99px，
    鼠标一离开滑块 hover 判定就失败），所以这里必须发真的 motion。
    """
    import tempfile
    with tempfile.TemporaryDirectory(prefix="nxui-lutui-") as temp:
        root = Path(temp); (root / "auto").mkdir()
        calls = root / "calls"
        engine = root / "engine.sh"
        engine.write_text('#!/bin/sh\nprintf "%s %s\n" "$1" "$2" >> "$NXUI_CALLS"\nexit 0\n')
        engine.chmod(0o755)
        env = dict(env, NXUI_CALLS=str(calls))
        log = root / f"run-{time.monotonic_ns()}.log"
        stream = log.open("w")
        p = subprocess.Popen(prefix + ["--live", "--lut", "--root", str(root), "--engine", str(engine),
                                       "--recipes", str(OUT / "looks.txt"), "--lifetime-ms", "6000"],
                             env=env, stdout=stream, stderr=subprocess.STDOUT)
        try:
            for _ in range(60):
                if "READY" in log.read_text(): break
                if p.poll() is not None: raise AssertionError(log.read_text())
                time.sleep(.05)
            else:
                raise AssertionError("UI did not initialize\n" + log.read_text())
            envs = dict(env, DISPLAY=env["DISPLAY"])
            # LUT 面板没有 PW 分量行，但仍有一行滚动条：四列同上 168px 宽，
            # 按钮行 y ≈ 123..149。"还原原厂"是第三列（LUT 多了"保存并关闭"，
            # 列序：上一个 / 保存并关闭 / 还原原厂 / 下一个）。
            subprocess.run([str(OUT / "test_input"), "click", "448", "136", "60"], env=envs, check=True, timeout=5)
            deadline = time.time() + 4
            while time.time() < deadline:
                lines = calls.read_text().splitlines() if calls.exists() else []
                if lines and lines[-1].startswith("off"): break
                time.sleep(.05)
            lines = calls.read_text().splitlines() if calls.exists() else []
            assert lines and lines[-1].startswith("off"), (lines, log.read_text()[-600:])
            # 滚动条拖动：LUT 面板滚动条在 y≈102..118（轨道 12..708，滑块宽 30）。
            # 拖到 480px ⇒ 比例 (480-27)/(696-30)=0.68 ⇒ 第 5 项（0 基），
            # 共 8 项。只发 press/release 的 click 测不出 motion 链；
            # 只断言"变了"也测不出"松手位置才是终点"（10Hz 会合并中间帧）。
            subprocess.run([str(OUT / "test_input"), "drag", "20", "110", "480", "110", "10"],
                           env=envs, check=True, timeout=8)
            deadline = time.time() + 5
            while time.time() < deadline:
                lines = calls.read_text().splitlines() if calls.exists() else []
                if lines and lines[-1].startswith("apply"): break
                time.sleep(.05)
            lines = calls.read_text().splitlines() if calls.exists() else []
            assert lines and lines[-1] == "apply look05", (lines, log.read_text()[-600:])
            # 点轨道任意位置也应跳过去（触摸屏上比拖更常用）：680px ⇒ 第 7 项。
            subprocess.run([str(OUT / "test_input"), "click", "680", "110", "60"], env=envs, check=True, timeout=5)
            deadline = time.time() + 5
            while time.time() < deadline:
                lines = calls.read_text().splitlines() if calls.exists() else []
                if lines and lines[-1] == "apply look07": break
                time.sleep(.05)
            lines = calls.read_text().splitlines() if calls.exists() else []
            assert lines and lines[-1] == "apply look07", (lines, log.read_text()[-600:])
            subprocess.run([str(OUT / "test_input"), "key", "Escape"], env=envs, check=True, timeout=5)
            assert p.wait(timeout=8) == 0, log.read_text()
        finally:
            if p.poll() is None: p.terminate(); p.wait(timeout=6)
            stream.close()
    print(f"PASS {label}: LUT restore button calls engine off + scrollbar drag/tap")
