#!/bin/bash
# bench_font_tiers.sh — 字体链的行为与耗时（生产布局等价，冷 fontconfig 缓存）
#
# 默认两级：
#   NXUI_CJK（1.9 MB，按 family 开）：GB2312 全集
#   原厂 SDIC（10.7 MB，按文件开）：GB2312 以外的兜底
# 可选一级（实验档，要显式设 NXUI_FONT_MIN）：38 KB 面板子集，按文件开。
#
# 场景：
#   lut     英文 look 名（LUT 面板常态）       -> tier1
#   filmlab 仓库自带 recipes.json（21/68 中文） -> tier1
#   gblook  含 GB2312 汉字的 look 名           -> tier1
#   rare    含 GB2312 以外（龍）               -> tier2 原厂字体
#   menu    --menu 原厂菜单（全中文）           -> tier1
#   nomin   二级 family 开不出来（空 fonts 目录）-> tier2 兜底仍有画面
#   opt0    显式开一级子集（实验档）            -> tier0
#
# 每个场景跑 3 次取最小 first_ms：qemu 下的抖动接近 2 倍，单次数字不可用。
#
# 用法: bash bench_font_tiers.sh [rootfs]
set -u
cd "$(dirname "$0")"
RF=${1:-/opt/nxks2/rootfs-112}
REPO=$(cd ../.. && pwd)
B=$RF/tmp/fonttier
REPEAT=3

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
cp out/font/font-sub-gb2312.ttf "$B/fonts/NXUI_CJK.ttf"
cp out/font/font-sub-panel.ttf   "$B/fonts/NXUI_CJK_MIN.ttf"
cat > "$B/fonts.conf" <<EOF
<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig><dir>$B/fonts</dir><cachedir>$B/cache</cachedir></fontconfig>
EOF
cat > "$B/fonts-empty.conf" <<EOF
<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig><dir>$B/nothing</dir><cachedir>$B/cache</cachedir></fontconfig>
EOF

python3 - "$REPO" "$B" <<'PY'
import json, sys
repo, base = sys.argv[1], sys.argv[2]
d = json.load(open(f"{repo}/scripts/filmlab/recipes.json"))
def dump(path, labels):
    with open(path, "w") as fh:
        for key, label in labels:
            fh.write("|".join([key, label] + ["0"]*7) + "\n")
dump(f"{base}/recipes.txt", [(k, v["label"]) for k, v in d["recipes"].items()])
dump(f"{base}/looks.txt", [(f"look{i:02d}", n) for i, n in enumerate([
    "Portra 400", "Velvia 50", "Tri-X 400", "Ektar 100", "Provia 100F",
    "Gold 200", "Superia 400", "HP5 Plus", "Delta 3200", "Acros 100"])])
dump(f"{base}/looks-gb.txt", [("sunset", "日落暖调"), ("cold", "冷调青蓝")])
dump(f"{base}/looks-rare.txt", [("dragon", "龍之瞳")])
PY

probe() {  # $1=label $2=recipes $3=min font(optional, "" = 不开一级) $4=menu $5=conf
    label=$1; rec=$2; minfont=${3:-}; menu=${4:-}; conf=${5:-$B/fonts.conf}
    best_first=; best_font=; tier=?
    shot="$PWD/out/bench-tier-$label.ppm"
    for _ in $(seq $REPEAT); do
        rm -f "$shot"; rm -rf "$B/cache"   # 每轮都冷启：机上 fc-cache 写不出来，冷值才是现实
        args=(--root "$REPO/scripts" --recipes "$rec" --snapshot "$shot")
        [ -n "$menu" ] && args+=(--menu "$menu")
        if [ -n "$minfont" ]; then
            out=$(LC_ALL=C FONTCONFIG_FILE="$conf" NXUI_FONT_MIN="$minfont" \
                  qemu-arm-static -L "$RF" out/nxui.arm "${args[@]}" 2>&1)
        else
            out=$(LC_ALL=C FONTCONFIG_FILE="$conf" \
                  qemu-arm-static -L "$RF" out/nxui.arm "${args[@]}" 2>&1)
        fi
        t=$(printf '%s\n' "$out" | sed -n 's/.*nice=[0-9]* tier=\([0-9]\).*/\1/p' | head -1)
        f=$(printf '%s\n' "$out" | sed -n 's/.*process_ms=\([0-9]*\).*/\1/p' | head -1)
        fm=$(printf '%s\n' "$out" | sed -n 's/.*font_ms=\([0-9]*\).*/\1/p')
        [ -n "$t" ] && tier=$t
        if [ -n "$f" ] && { [ -z "$best_first" ] || [ "$f" -lt "$best_first" ]; }; then best_first=$f; fi
        if [ -n "$fm" ] && { [ -z "$best_font" ] || [ "$fm" -lt "$best_font" ]; }; then best_font=$fm; fi
        printf '%s\n' "$out" > "out/bench-tier-$label.log"
    done
    px=$(stat -c %s "$shot" 2>/dev/null || echo 0)
    printf '%-9s tier=%-2s font_ms=%-4s first_ms=%-4s ppm=%s\n' \
        "$label" "$tier" "${best_font:-?}" "${best_first:-?}" "$px"
}

probe lut     "$B/looks.txt"
probe filmlab "$B/recipes.txt"
probe gblook  "$B/looks-gb.txt"
probe rare    "$B/looks-rare.txt"
probe menu    "$B/looks.txt" "" gui_ini.NX500
probe nomin   "$B/looks.txt" "" "" "$B/fonts-empty.conf"
probe opt0    "$B/looks.txt" "$B/fonts/NXUI_CJK_MIN.ttf"
