#!/bin/bash
# bench_font_sizes.sh — 量化各候选字体的打开成本（codepoints / query_ms）
#
# 背景：NXUI 首帧里字体是最大单项。fontprobe 已证明成本跟 **cmap 码点数**
# 相关而不是文件字节数，所以做子集才有意义。这个脚本把候选摆在一起，
# 直接给"裁到多少码点 -> 多少毫秒"的对应关系。
#
# 用法: bash bench_font_sizes.sh [rootfs]
#
# ⚠ 当前在 qemu-arm + 相机 rootfs 上 FcFreeTypeQuery 返回 NULL，表格会是空的。
# 想拿数字请用 bench_font_tiers.sh 的 INIT font_ms（真实打开路径，含校验），
# 这个探针留给真机分项：它把 query / charset / FT_New_Face 拆开报。
set -u
cd "$(dirname "$0")"
RF=${1:-/opt/nxks2/rootfs-112}
PROBE=out/fontprobe.arm
[ -f "$PROBE" ] || { echo "missing $PROBE; run build_fontprobe.sh"; exit 1; }

printf '%-28s %10s %10s %9s %9s\n' font bytes codepoints query_ms charset_ms
for f in out/font/SDIC_GP_US_20120720.ttf \
         out/font/font-sub-gbk.ttf \
         out/font/font-sub-gb2312.ttf \
         out/font/font-sub-panel.ttf; do
    [ -f "$f" ] || continue
    out=$(LC_ALL=C qemu-arm-static -L "$RF" "$PROBE" "$f" 3 2>&1)
    printf '%-28s %10s %10s %9s %9s\n' \
        "$(basename "$f")" \
        "$(printf '%s\n' "$out" | sed -n 's/^bytes=//p')" \
        "$(printf '%s\n' "$out" | sed -n 's/^codepoints=//p')" \
        "$(printf '%s\n' "$out" | sed -n 's/^query_ms=//p')" \
        "$(printf '%s\n' "$out" | sed -n 's/^charset_ms=//p')"
done
