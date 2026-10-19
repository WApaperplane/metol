#!/bin/bash
# bench_font_precedence.sh — 同 family 名时 fontconfig 选哪个目录的字体
#
# 若"子集字体目录在前"能稳定压过 /usr/share/fonts，就可以零代码替换
# （不动 nxui.c 的 --font 默认值）。否则必须给子集字体改 family 名并在
# 代码里回退。这个实验就是为了避免押注未定义行为。
#
# 用法: bash bench_font_precedence.sh [rootfs]
set -u
cd "$(dirname "$0")"
RF=${1:-/opt/nxks2/rootfs-112}
REPO=$(cd ../.. && pwd)
BASE=$RF/tmp/fontsub

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

# 子集字体目录（family 仍是 SDIC_GP_US）
mkdir -p "$BASE/prec/fonts"
cp "$BASE/font-sub-gb2312.ttf" "$BASE/prec/fonts/SDIC_sub.ttf"

probe() {  # $1=label $2=first-dir $3=second-dir
    label=$1; first=$2; second=$3
    d=$BASE/prec/$label
    rm -rf "$d"; mkdir -p "$d"
    cat > "$d/fonts.conf" <<EOF
<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig><dir>$first</dir><dir>$second</dir><cachedir>/tmp/fontsub/prec/$label/cache</cachedir></fontconfig>
EOF
    printf '%-22s' "$label"
    for i in 1 2 3; do
        out=$(LC_ALL=C FONTCONFIG_FILE=/tmp/fontsub/prec/$label/fonts.conf \
              qemu-arm-static -L "$RF" out/nxui.arm \
              --root "$REPO/scripts" --recipes /tmp/fontsub/recipes.txt \
              --snapshot "$PWD/out/bench-prec.ppm" 2>&1)
        fm=$(printf '%s\n' "$out" | sed -n 's/.*font_ms=\([0-9]*\).*/\1/p')
        printf ' %sms' "${fm:-?}"
    done
    echo
}

probe subset-first  /tmp/fontsub/prec/fonts /usr/share/fonts
probe system-first  /usr/share/fonts       /tmp/fontsub/prec/fonts
probe subset-only   /tmp/fontsub/prec/fonts /tmp/fontsub/prec/fonts
