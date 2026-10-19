#!/bin/bash
# bench_font_panel.sh — 面板子集字体的首帧下界（生产布局等价）
#
# bench_font_prod.sh 量的是 GB2312 全集（53 ms）。这里量激进档：只含
# ASCII + nxui.c 里出现过的非 ASCII 字面量。它回答一个问题——
# "把字体再裁到 38 KB，font_ms 还能降多少"，代价是 look 名里出现生僻汉字
# 就得多走一次回退，所以只作下界参考，默认不生产使用。
#
# 用法: bash bench_font_panel.sh [rootfs]
set -u
cd "$(dirname "$0")"
RF=${1:-/opt/nxks2/rootfs-112}
REPO=$(cd ../.. && pwd)
B=$RF/tmp/fontmin

XPID=
if [ ! -e /tmp/.X11-unix/X97 ]; then
    LD_PRELOAD=$PWD/out/xvfb_local_paths.so \
    LD_LIBRARY_PATH=$PWD/out/deps/usr/lib/x86_64-linux-gnu \
    NXUI_XKB_BINDIR=$PWD/out/deps/usr/bin \
    ./out/deps/usr/bin/Xvfb :97 -screen 0 720x480x24 -nolisten tcp -ac \
        -fp "$PWD/out/deps/usr/share/fonts/X11/misc" > /tmp/xvfb97.log 2>&1 &
    XPID=$!
    sleep 1
fi
export DISPLAY=:97
trap '[ -n "$XPID" ] && kill $XPID 2>/dev/null' EXIT

rm -rf "$B"; mkdir -p "$B/fonts"
cp out/font/font-sub-panel.ttf "$B/fonts/font.ttf"
cat > "$B/fonts.conf" <<EOF
<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig><dir>$B/fonts</dir><cachedir>$B/cache</cachedir></fontconfig>
EOF

RECIPES=$RF/tmp/fontsub/recipes.txt
[ -f "$RECIPES" ] || python3 - "$REPO" "$RECIPES" <<'PY'
import json, sys
repo, out = sys.argv[1], sys.argv[2]
d = json.load(open(f"{repo}/scripts/filmlab/recipes.json"))
f = ("R_COLOR","G_COLOR","B_COLOR","HUE","SATURATION","SHARPNESS","CONTRAST")
with open(out, "w") as fh:
    for k, v in d["recipes"].items():
        fh.write("|".join([k, v["label"]] + [str(v[x]) for x in f]) + "\n")
PY

out=$(LC_ALL=C FONTCONFIG_FILE=$B/fonts.conf qemu-arm-static -L "$RF" out/nxui.arm \
    --root "$REPO/scripts" --recipes "$RECIPES" \
    --font "SDIC_GP_US_20120720:pixelsize=19" --snapshot "$PWD/out/bench-panel.ppm" 2>&1)
printf '%s\n' "$out" | grep -E '^(INIT|FIRST_FRAME|FONT|READY)' || printf '%s\n' "$out"
