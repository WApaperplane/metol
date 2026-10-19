#!/bin/bash
# bench_font_cache.sh — 判定 fontconfig 缓存在相机 ABI 下是否真的生效
#
# 关键变量只有两个：cachedir 是否可写、fonts.conf 的 mtime 是否稳定。
# 每次运行都在同一个缓存目录上连跑 3 次：
#   第 1 次 = 冷（真机重启后第一次开面板）
#   第 2/3 次 = 热（缓存命中）
# 若 1→2 没有明显下降，说明缓存写不进去或立刻失效，此时只能靠裁剪字体。
#
# 用法: bash bench_font_cache.sh [rootfs]
set -u
cd "$(dirname "$0")"
RF=${1:-/opt/nxks2/rootfs-112}
REPO=$(cd ../.. && pwd)
BASE=$RF/tmp/fontsub

# nxui 需要一个 X 服务器（--snapshot 也要连）；用仓库自带的 Xvfb，
# 它需要 xvfb_local_paths.so 把 /tmp/.X11-unix 重定向到可写位置。
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

run_one() {  # $1=label $2=fontdir $3=fontfile-or-empty
    label=$1; dir=$2; font=$3
    d=$BASE/c-$label
    rm -rf "$d"; mkdir -p "$d/cache"
    if [ -n "$font" ]; then
        cp "$font" "$d/font.ttf"
        src=/tmp/fontsub/c-$label
    else
        src=/usr/share/fonts
    fi
    cat > "$d/fonts.conf" <<EOF
<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig><dir>$src</dir><cachedir>/tmp/fontsub/c-$label/cache</cachedir></fontconfig>
EOF
    printf '%-14s' "$label"
    for i in 1 2 3; do
        # 快照写到宿主的 out/：qemu 的 -L 只在 rootfs 里有同名路径时改写，
        # 否则回落到原路径。rootfs 的 /tmp/fontsub 属 root 且 755，普通用户
        # fopen 会静默失败（snapshot() 不检查返回值）。
        rm -f "$PWD/out/bench-$label.ppm"
        out=$(LC_ALL=C FONTCONFIG_FILE=/tmp/fontsub/c-$label/fonts.conf \
              qemu-arm-static -L "$RF" out/nxui.arm \
              --root "$REPO/scripts" --recipes /tmp/fontsub/recipes.txt \
              --snapshot "$PWD/out/bench-$label.ppm" 2>&1)
        fm=$(printf '%s\n' "$out" | sed -n 's/.*font_ms=\([0-9]*\).*/\1/p')
        ff=$(printf '%s\n' "$out" | sed -n 's/.*process_ms=\([0-9]*\).*/\1/p')
        rc=$(printf '%s\n' "$out" | sed -n 's/.*READY.*recipes=\([0-9]*\).*/\1/p')
        printf '  run%d font=%sms first=%sms rec=%s' "$i" "${fm:-?}" "${ff:-?}" "${rc:-?}"
    done
    n=$(ls "$d/cache" 2>/dev/null | wc -l)
    printf '  cachefiles=%s\n' "$n"
}

run_one orig      ""                        ""
run_one gb2312    ""                        "$BASE/font-sub-gb2312.ttf"
run_one panel     ""                        "$BASE/font-sub-panel.ttf"
