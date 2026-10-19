#!/bin/bash
# bench_font.sh — 字体打开成本基准（相机 ABI / qemu-arm）
#
# 用法: bash bench_font.sh [font...]
#   不给参数时测 rootfs 里的原厂字体与一个 22 KB 的小字体作对照。
#   主机路径用 -L rootfs 对应的 guest 路径（/usr/share/fonts/...）。
set -u
cd "$(dirname "$0")"
RF=${NXUI_ROOTFS:-/opt/nxks2/rootfs-112}
P=${NXUI_FONTPROBE:-out/fontprobe.arm}

[ -x "$P" ] || { echo "missing $P; run build_fontprobe.sh"; exit 1; }

if [ "$#" -gt 0 ]; then
    FONTS=("$@")
else
    FONTS=("/usr/share/fonts/SDIC_GP_US_20120720.ttf"
           "/usr/share/fonts/TizenSansLaoRegular.ttf")
fi

printf '%-42s %10s %8s %9s %10s %9s\n' font bytes cps newface charset query
for f in "${FONTS[@]}"; do
    out=$(qemu-arm-static -L "$RF" "$P" "$f" 3 2>&1) || { echo "$f FAILED: $out"; continue; }
    b=$(printf '%s\n' "$out" | sed -n 's/^bytes=//p')
    c=$(printf '%s\n' "$out" | sed -n 's/^codepoints=//p')
    n=$(printf '%s\n' "$out" | sed -n 's/^newface_ms=//p')
    s=$(printf '%s\n' "$out" | sed -n 's/^charset_ms=//p')
    q=$(printf '%s\n' "$out" | sed -n 's/^query_ms=//p')
    printf '%-42s %10s %8s %9s %10s %9s\n' "$(basename "$f")" "$b" "$c" "$n" "$s" "$q"
done
