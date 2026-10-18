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
                raise AssertionError("UI did not initialize")
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
            # A row that is already applied saves straight to flash, so move the
            # selection first: saving then has to go through apply + commit.
            send("key", "Right"); time.sleep(.15)
            # Save row sits at y=147..173 (24 title + 84 list + 16 status + 5 spacing).
            send("click", "350", "160", "5")
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
