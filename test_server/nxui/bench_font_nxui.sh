#!/bin/bash
# bench_font_nxui.sh — 用真实 nxui.arm 量裁剪字体对首帧的影响
#
# 做法：为每个候选字体建独立 fontconfig 目录（family 名相同，靠目录隔离），
# 跑 nxui.arm --snapshot，取 INIT 的 font_ms，并保留 PPM 供像素比对。
#
# 用法: bash bench_font_nxui.sh [rootfs]
set -euo pipefail
cd "$(dirname "$0")"
RF=${1:-/opt/nxks2/rootfs-112}
REPO=$(cd ../.. && pwd)
CAND=$RF/tmp/fontsub
[ -d "$CAND" ] || { echo "missing $CAND; run make_font_subset.py and copy"; exit 1; }

# 每个变体一个目录 + 自己的 fonts.conf
setup() {  # $1=dir $2=fontfile
    mkdir -p "$CAND/$1"
    cp "$2" "$CAND/$1/font.ttf"
    cat > "$CAND/$1/fonts.conf" <<EOF
<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig><dir>$CAND/$1</dir><cachedir>$CAND/$1/cache</cachedir></fontconfig>
EOF
}
setup sub-gb2312 "$CAND/font-sub-gb2312.ttf"
setup sub-panel "$CAND/font-sub-panel.ttf"

# 原厂字体作为基线：直接指系统目录
mkdir -p "$CAND/orig"
cat > "$CAND/orig/fonts.conf" <<EOF
<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig><dir>/usr/share/fonts</dir><cachedir>$CAND/orig/cache</cachedir></fontconfig>
EOF

RECIPES=$RF/tmp/fontsub/recipes.txt
python3 - "$REPO" "$RECIPES" <<'PY'
import json, sys
repo, out = sys.argv[1], sys.argv[2]
d = json.load(open(f"{repo}/scripts/filmlab/recipes.json"))
f = ("R_COLOR","G_COLOR","B_COLOR","HUE","SATURATION","SHARPNESS","CONTRAST")
with open(out, "w") as fh:
    for k, v in d["recipes"].items():
        fh.write("|".join([k, v["label"]] + [str(v[x]) for x in f]) + "\n")
PY

printf '%-12s %10s %9s %9s %9s\n' variant bytes font_ms query first
for v in orig sub-gb2312 sub-panel; do
    shot=$RF/tmp/fontsub/$v.ppm
    rm -f "$shot"
    out=$(LC_ALL=C FONTCONFIG_FILE=$CAND/$v/fonts.conf qemu-arm-static -L "$RF" out/nxui.arm \
        --root "$REPO/scripts" --recipes "$RECIPES" --snapshot "$shot" 2>&1) || { echo "$v FAILED"; echo "$out"; continue; }
    fm=$(printf '%s\n' "$out" | sed -n 's/.*font_ms=\([0-9]*\).*/\1/p')
    ff=$(printf '%s\n' "$out" | sed -n 's/.*process_ms=\([0-9]*\).*/\1/p')
    sz=$(stat -c %s "$CAND/$v/font.ttf" 2>/dev/null || echo 10680224)
    printf '%-12s %10s %9s %9s %9s\n' "$v" "$sz" "$fm" "$(printf '%s\n' "$out" | sed -n 's/.*recipes_ms=\([0-9]*\).*/\1/p')" "$ff"
    # 像素是否与原厂一致（同一字体、同一渲染路径，正常应完全相同）
    if [ -f "$shot" ]; then cp "$shot" "out/font-$v.ppm"; fi
done
