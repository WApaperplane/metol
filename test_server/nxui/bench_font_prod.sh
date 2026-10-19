#!/bin/bash
# bench_font_prod.sh — 按生产布局验证子集字体：正常路径 + 缺字回退
#
# 生产布局：fonts.conf 里 <dir>/opt/usr/nx-ks/nxui/fonts</dir>，
# 子集字体 family=NXUI_CJK，nxui 默认就用它。
# 这里用 /tmp/fontprod 顶替该目录，其余等价。
#
# 两个场景：
#   正常   68 个英文 look 名  -> 走子集，font_ms 应 ~52
#   缺字   追加一个繁体 look 名 -> 必须触发 FONT fallback，宁可慢不能空白
#
# 用法: bash bench_font_prod.sh [rootfs]
set -u
cd "$(dirname "$0")"
RF=${1:-/opt/nxks2/rootfs-112}
REPO=$(cd ../.. && pwd)
BASE=$RF/tmp/fontprod

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
cat > "$BASE/fonts.conf" <<'EOF'
<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig>
  <dir>/tmp/fontprod/fonts</dir>
  <cachedir>/tmp/fontprod/cache</cachedir>
</fontconfig>
EOF

# 正常配方表
python3 - "$REPO" "$BASE/recipes.txt" <<'PY'
import json, sys
repo, out = sys.argv[1], sys.argv[2]
d = json.load(open(f"{repo}/scripts/filmlab/recipes.json"))
f = ("R_COLOR","G_COLOR","B_COLOR","HUE","SATURATION","SHARPNESS","CONTRAST")
with open(out, "w") as fh:
    for k, v in d["recipes"].items():
        fh.write("|".join([k, v["label"]] + [str(v[x]) for x in f]) + "\n")
PY
# 缺字配方表：龍 不在 GB2312
cp "$BASE/recipes.txt" "$BASE/recipes-cjk-rare.txt"
printf 'dragon|龍之瞳|0|0|0|0|0|0|0\n' >> "$BASE/recipes-cjk-rare.txt"

probe() {  # $1=label $2=recipes file $3=menu(optional)
    label=$1; rec=$2; menu=${3:-}
    printf '%-16s' "$label"
    shot="$PWD/out/bench-prod-$label.ppm"
    args="--root $REPO/scripts --recipes $rec --snapshot $shot"
    [ -n "$menu" ] && args="$args --menu $menu"
    out=$(LC_ALL=C FONTCONFIG_FILE=/tmp/fontprod/fonts.conf \
          qemu-arm-static -L "$RF" out/nxui.arm $args 2>&1)
    fm=$(printf '%s\n' "$out" | sed -n 's/.*font_ms=\([0-9]*\).*/\1/p')
    ff=$(printf '%s\n' "$out" | sed -n 's/.*process_ms=\([0-9]*\).*/\1/p')
    fb=$(printf '%s\n' "$out" | grep -c 'FONT fallback')
    miss=$(printf '%s\n' "$out" | grep -c 'font unavailable')
    printf 'font=%sms first=%sms fallback=%s unavailable=%s\n' "${fm:-?}" "${ff:-?}" "$fb" "$miss"
}

probe normal   /tmp/fontprod/recipes.txt
probe rare-glyph /tmp/fontprod/recipes-cjk-rare.txt
probe with-menu /tmp/fontprod/recipes.txt gui_ini.NX500
