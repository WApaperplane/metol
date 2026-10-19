"""bench_font_display.py — 用真实 nxui.arm 量字体裁剪对首帧的影响。

和 bench_host.sh 的区别：这个跑相机 ABI（qemu-arm）并在隔离 Xvfb 里渲染，
所以 font_ms 可以和 out/arm-*.log 里的线上预算直接比较。

每个候选字体准备一个只含它的 fontconfig 目录（family 名都是 SDIC_GP_US，
靠目录隔离选择），跑 --snapshot 后读 INIT 行并保留 PPM 做像素比对。

用法: python3 bench_font_display.py [rootfs]
"""
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
OUT = HERE / "out"
RF = Path(sys.argv[1] if len(sys.argv) > 1 else os.environ.get("NXUI_ROOTFS", "/opt/nxks2/rootfs-112"))
CAND = RF / "tmp/fontsub"

env = os.environ.copy()
env.update(DISPLAY=":97", LC_ALL="C",
           LD_LIBRARY_PATH=str(OUT / "deps/usr/lib/x86_64-linux-gnu"))
armenv = env.copy()
armenv["LD_LIBRARY_PATH"] = f"{RF}/usr/lib:{RF}/lib"

# 配方表：nxui 需要 9 字段
import json
data = json.loads((REPO / "scripts/filmlab/recipes.json").read_text())
recipes = CAND / "recipes.txt"
fields = ("R_COLOR", "G_COLOR", "B_COLOR", "HUE", "SATURATION", "SHARPNESS", "CONTRAST")
recipes.write_text("".join("|".join([k, v["label"]] + [str(v[f]) for f in fields]) + "\n"
                           for k, v in data["recipes"].items()))


def prepare(name: str, font: Path | None) -> Path:
    """建一个只含该字体的 fontconfig 目录，返回 conf 路径。"""
    folder = CAND / name
    folder.mkdir(parents=True, exist_ok=True)
    if font:
        shutil.copyfile(font, folder / "font.ttf")
        target = f"/tmp/fontsub/{name}"
    else:
        target = "/usr/share/fonts"
    conf = folder / "fonts.conf"
    conf.write_text('<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd">'
                    f'<fontconfig><dir>{target}</dir>'
                    f'<cachedir>/tmp/fontsub/{name}/cache</cachedir></fontconfig>')
    return conf


variants = [("orig", None),
            ("sub-gb2312", CAND / "font-sub-gb2312.ttf"),
            ("sub-panel", CAND / "font-sub-panel.ttf")]

serverlog = (OUT / "xvfb.log").open("w")
serverenv = env.copy()
serverenv.update(LD_PRELOAD=str(OUT / "xvfb_local_paths.so"),
                 NXUI_XKB_BINDIR=str(OUT / "deps/usr/bin"))
server = subprocess.Popen(
    [str(OUT / "deps/usr/bin/Xvfb"), ":97", "-screen", "0", "720x480x24",
     "-nolisten", "tcp", "-ac", "-fp", str(OUT / "deps/usr/share/fonts/X11/misc")],
    env=serverenv, stdout=serverlog, stderr=subprocess.STDOUT)
try:
    time.sleep(.5)
    if server.poll() is not None:
        raise RuntimeError((OUT / "xvfb.log").read_text())

    print(f"{'variant':<12}{'bytes':>11}{'cold_ms':>9}{'warm_ms':>9}{'draw_ms':>9}")
    shots = {}
    for name, font in variants:
        conf = prepare(name, font)
        ran = armenv.copy()
        ran["FONTCONFIG_FILE"] = f"/tmp/fontsub/{name}/fonts.conf"
        shot = CAND / f"{name}.ppm"
        times = []
        for attempt in ("cold", "warm"):
            if attempt == "cold":
                # 冷缓存 = 没有任何 fontconfig 缓存文件，等价于真机重启后第一次开面板
                shutil.rmtree(CAND / name / "cache", ignore_errors=True)
            if shot.exists():
                shot.unlink()
            proc = subprocess.run(
                ["qemu-arm-static", "-L", str(RF), str(OUT / "nxui.arm"),
                 "--root", str(REPO / "scripts"), "--recipes", f"/tmp/fontsub/recipes.txt",
                 "--snapshot", f"/tmp/fontsub/{name}.ppm"],
                env=ran, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
            text = proc.stdout.decode(errors="replace")
            if proc.returncode:
                print(f"{name:<12} FAILED rc={proc.returncode}\n{text}")
                times = []
                break
            fm = re.search(r"font_ms=(\d+)", text)
            times.append(int(fm[1]) if fm else -1)
            if attempt == "cold":
                dm = re.search(r"max_draw_ms=(\d+)", text)
                cold_draw = int(dm[1]) if dm else -1
                ff = re.search(r"process_ms=(\d+)", text)
                cold_first = int(ff[1]) if ff else -1
        if not times:
            continue
        size = font.stat().st_size if font else 10680224
        print(f"{name:<12}{size:>11,}{times[0]:>9}{times[1]:>9}{cold_draw:>9}   first(cold)={cold_first}")
        if shot.exists():
            shots[name] = shot.read_bytes()
            shutil.copyfile(shot, OUT / f"font-{name}.ppm")

    # 像素比对：同一字体裁剪前后，渲染应当逐字节一致
    base = shots.get("orig")
    for name, blob in shots.items():
        if name == "orig" or not base:
            continue
        same = blob == base
        print(f"pixels {name} vs orig: {'identical' if same else 'DIFFERENT'}")
finally:
    server.terminate()
    serverlog.close()
