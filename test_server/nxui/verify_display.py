"""Render the native and camera-ABI binaries in an isolated X server.

No camera connection, firmware writes, or host package installation.
"""
from pathlib import Path
import ctypes
import json
import os
import subprocess
import time
from test_interaction import run_interaction, run_lut_interaction
from test_performance import run_performance
from test_service_interaction import run_service_interaction

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
OUT = HERE / "out"
RF = Path(os.environ.get("NXUI_ROOTFS", "/opt/nxks2/rootfs-112"))
env = os.environ.copy()
env.update(DISPLAY=":97", LC_ALL="C", LD_LIBRARY_PATH=str(OUT / "deps/usr/lib/x86_64-linux-gnu"))
fontconf = OUT / "fonts.conf"
fontconf.write_text(f'<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd"><fontconfig><dir>{RF}/usr/share/fonts</dir><cachedir>{OUT}/font-cache</cachedir></fontconfig>')
env["FONTCONFIG_FILE"] = str(fontconf)
# For qemu, the ARM font library and its dependencies must come from the camera.
armenv = env.copy()
armenv["LD_LIBRARY_PATH"] = f"{RF}/usr/lib:{RF}/lib"
data = json.loads((REPO / "scripts/filmlab/recipes.json").read_text())
recipes = OUT / "recipes.txt"
fields = ("R_COLOR", "G_COLOR", "B_COLOR", "HUE", "SATURATION", "SHARPNESS", "CONTRAST")
recipes.write_text("".join("|".join([k, v["label"]] + [str(v[f]) for f in fields]) + "\n" for k, v in data["recipes"].items()))
# LUT 面板的条目来自 /mnt/mmc/looks，名字是英文（Film-Luts 的命名风格）。
# 用固定 8 条替身：形状与真实列表一致（key 与 label 相同、7 个占位值）。
looks = OUT / "looks.txt"
looks.write_text("".join(f"look{i:02d}|Look {i:02d}|0|0|0|0|0|0|0\n" for i in range(8)))
serverlog = (OUT / "xvfb.log").open("w")
serverenv = env.copy()
serverenv.update(LD_PRELOAD=str(OUT / "xvfb_local_paths.so"), NXUI_XKB_BINDIR=str(OUT / "deps/usr/bin"))
server = subprocess.Popen([str(OUT / "deps/usr/bin/Xvfb"), ":97", "-screen", "0", "720x480x24", "-nolisten", "tcp", "-ac", "-fp", str(OUT / "deps/usr/share/fonts/X11/misc")], env=serverenv, stdout=serverlog, stderr=subprocess.STDOUT)
try:
    time.sleep(.5)
    if server.poll() is not None: raise RuntimeError((OUT / "xvfb.log").read_text())
    records = []
    for name, prefix, runenv in [("host", [str(OUT / "nxui")], env), ("arm", ["qemu-arm-static", "-L", str(RF), str(OUT / "nxui.arm")], armenv)]:
        if os.environ.get("NXUI_VERIFY_TARGET") and name != os.environ["NXUI_VERIFY_TARGET"]: continue
        for mode in ("filmlab", "lut", "menu"):
            shot = OUT / f"{name}-{mode}.ppm"
            table = looks if mode == "lut" else recipes
            args = prefix + ["--root", str(REPO / "scripts"), "--recipes", str(table), "--snapshot", str(shot)]
            if mode == "lut": args += ["--lut"]
            if mode == "menu": args += ["--menu", "gui_ini.NX500"]
            result = subprocess.run(args, env=runenv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=20)
            (OUT / f"{name}-{mode}.log").write_bytes(result.stdout)
            if result.returncode: raise RuntimeError(result.stdout.decode(errors="replace"))
            header, shape, depth, pixels = shot.read_bytes().split(b"\n", 3)
            assert header == b"P6" and shape == (b"720 336" if mode == "menu" else b"720 208")
            assert len(set(pixels)) > 12, f"Empty render: {name}/{mode}"
            records.append({"target": name, "mode": mode, "shape": shape.decode(), "result": "PASS"})
        # Idle verification: elapsed time must not cause a continuous redraw loop.
        result = subprocess.run(prefix + ["--root", str(REPO / "scripts"), "--recipes", str(recipes), "--lifetime-ms", "1500"], env=runenv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=20)
        text = result.stdout.decode(errors="replace")
        (OUT / f"{name}-idle.log").write_text(text)
        assert result.returncode == 0, text
        import re
        rendered = int(re.search(r"EXIT renders=(\d+)", text)[1])
        assert rendered <= 4, text
        records.append({"target": name, "mode": "idle", "renders_in_1500ms": rendered, "result": "PASS"})
        run_interaction(prefix, runenv, name)
        records.append({"target": name, "mode": "interaction", "result": "PASS"})
        run_lut_interaction(prefix, runenv, name)
        records.append({"target": name, "mode": "lut-interaction", "result": "PASS"})
        run_service_interaction(prefix, runenv, name)
        records.append({"target": name, "mode": "service-interaction", "result": "PASS"})
        perf = run_performance(prefix, runenv, name)
        records.append({"target": name, "mode": "performance", "cases": perf, "result": "PASS"})
    # Focus handoff: the panel must give the keyboard back to the camera window.
    # The camera has no window manager, so nothing else restores it.
    focus = subprocess.run(["python3", str(HERE / "test_focus.py")], env=env, timeout=120,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (OUT / "focus-run.log").write_bytes(focus.stdout)
    if focus.returncode:
        raise RuntimeError(focus.stdout.decode(errors="replace"))
    records.append({"target": "host", "mode": "focus-handoff", "result": "PASS"})
    (OUT / "display-results.json").write_text(json.dumps(records, ensure_ascii=False, indent=2))
    print(json.dumps(records, ensure_ascii=False, indent=2))
finally:
    server.terminate()
    try: server.wait(timeout=5)
    except subprocess.TimeoutExpired: server.kill(); server.wait()
    serverlog.close()
