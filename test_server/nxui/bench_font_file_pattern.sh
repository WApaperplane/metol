#!/bin/bash
# bench_font_file_pattern.sh — XftFontOpenName 能否直接吃 FC_FILE
#
# 为什么需要：fontconfig 扫描一个 <dir> 时会为目录里每个字体文件建 pattern，
# 也就是说只要原厂那份 10.7 MB 的 SDIC 还在搜索路径上，每次 XftFontOpenName
# 都要为它付 147 ms（bench_font_dirs.sh: mod-system 235 ms vs mod-only 52 ms）。
# 所以生产配置必须只留子集字体目录。这样一来"缺字回退"就没有 fontconfig
# 路径可走了 —— 除非能按文件直接打开。
#
# 用法: bash bench_font_file_pattern.sh [rootfs]
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

[ -f "$BASE/mod-only/fonts.conf" ] || { echo "run bench_font_dirs.sh first"; exit 1; }

try() {  # $1=label $2=font spec
    label=$1; spec=$2
    printf '%-16s' "$label"
    for i in 1 2; do
        out=$(LC_ALL=C FONTCONFIG_FILE=/tmp/fontdirs/mod-only/fonts.conf \
              qemu-arm-static -L "$RF" out/nxui.arm \
              --root "$REPO/scripts" --recipes /tmp/fontdirs/recipes.txt \
              --font "$spec" \
              --snapshot "$PWD/out/bench-file-$label-$i.ppm" 2>&1)
        fm=$(printf '%s\n' "$out" | sed -n 's/.*font_ms=\([0-9]*\).*/\1/p')
        bad=$(printf '%s\n' "$out" | grep -c 'font unavailable')
        printf ' font=%sms nf=%s' "${fm:-?}" "$bad"
    done
    echo
}

try family-only "NXUI_CJK:pixelsize=19"
try file-pattern ":file=/usr/share/fonts/SDIC_GP_US_20120720.ttf:pixelsize=19"
try file-family   "SDIC_GP_US:file=/usr/share/fonts/SDIC_GP_US_20120720.ttf:pixelsize=19"
