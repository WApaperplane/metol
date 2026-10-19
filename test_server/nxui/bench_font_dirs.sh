#!/bin/bash
# bench_font_dirs.sh — fontconfig 里 <dir> 数量对打开成本的影响
#
# 生产 fonts.conf 现在列了两个 dir：mod 字体目录 + /usr/share/fonts。
# 后者只用来给"缺字回退"留一条路（family SDIC_GP_US）。这 35 ms 值不值得，
# 取决于它到底是目录扫描成本还是字体 query 成本。
#
# 用法: bash bench_font_dirs.sh [rootfs]
set -u
cd "$(dirname "$0")"
RF=${1:-/opt/nxks2/rootfs-112}
REPO=$(cd ../.. && pwd)
BASE=$RF/tmp/fontdirs

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

rm -rf "$BASE"; mkdir -p "$BASE/fonts"
cp out/font/font-sub-gb2312.ttf "$BASE/fonts/NXUI_CJK.ttf"

# 配方表：与生产一致
python3 - "$REPO" "$BASE/recipes.txt" <<'PY'
import json, sys
repo, out = sys.argv[1], sys.argv[2]
d = json.load(open(f"{repo}/scripts/filmlab/recipes.json"))
f = ("R_COLOR","G_COLOR","B_COLOR","HUE","SATURATION","SHARPNESS","CONTRAST")
with open(out, "w") as fh:
    for k, v in d["recipes"].items():
        fh.write("|".join([k, v["label"]] + [str(v[x]) for x in f]) + "\n")
PY

conf() {  # $1=name, rest=dir elements
    name=$1; shift
    d=$BASE/$name
    mkdir -p "$d"
    { printf '<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd">\n<fontconfig>\n'
      for x in "$@"; do printf '  <dir>%s</dir>\n' "$x"; done
      printf '  <cachedir>/tmp/fontdirs/%s/cache</cachedir>\n</fontconfig>\n' "$name"
    } > "$d/fonts.conf"
}

conf mod-only     /tmp/fontdirs/fonts
conf mod-system   /tmp/fontdirs/fonts /usr/share/fonts
conf mod-sysdir   /tmp/fontdirs/fonts /usr/share/fonts/X11

printf '%-14s %10s %10s %10s\n' config run1 run2 run3
for name in mod-only mod-system mod-sysdir; do
    printf '%-14s' "$name"
    for i in 1 2 3; do
        out=$(LC_ALL=C FONTCONFIG_FILE=/tmp/fontdirs/$name/fonts.conf \
              qemu-arm-static -L "$RF" out/nxui.arm \
              --root "$REPO/scripts" --recipes /tmp/fontdirs/recipes.txt \
              --snapshot "$PWD/out/bench-dirs-$name-$i.ppm" 2>&1)
        fm=$(printf '%s\n' "$out" | sed -n 's/.*font_ms=\([0-9]*\).*/\1/p')
        printf ' %9sms' "${fm:-?}"
    done
    echo
done
