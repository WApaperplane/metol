#!/bin/bash
# bench_host.sh — 主机侧可复现基准：启动 / 首帧 / 单帧绘制 / 空闲唤醒
# 用法: bash bench_host.sh [menu|strip] [runs] [display]
#   默认使用 WSLg 的 :0（窗口会真的出现在桌面上，可肉眼确认）
# 依赖: build.sh host 已产出 out/nxui 与 out/recipes.txt
set -u
cd "$(dirname "$0")"
MODE=${1:-menu}
RUNS=${2:-5}
DISPLAY_ID=${3:-:0}

export LD_LIBRARY_PATH="$PWD/out/deps/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export FONTCONFIG_FILE="$PWD/out/fonts.conf"
export DISPLAY="$DISPLAY_ID"

ARGS="--dry-run --recipes out/recipes.txt"
if [ "$MODE" = menu ]; then
    ARGS="$ARGS --menu gui_ini.NX500 --root ../../scripts"
fi

tmp=$(mktemp)
for _ in $(seq 1 "$RUNS"); do
    timeout 20 ./out/nxui $ARGS --lifetime-ms 900 2>&1 | grep -E 'INIT|FIRST_FRAME|EXIT' >>"$tmp"
done

python3 - "$tmp" <<'PY'
import re, sys, statistics
rows = {}
for line in open(sys.argv[1]):
    for key, val in re.findall(r'(\w+)=(-?\d+)', line):
        rows.setdefault(key, []).append(int(val))
print(f"{'metric':<16}{'min':>7}{'median':>9}{'max':>7}{'n':>4}")
for key in ("recipes_ms","display_ms","font_ms","backend_ms","map_ms","process_ms","launch_ms","draw_ms","max_draw_ms","elapsed_ms","wakeups"):
    if key in rows:
        v = rows[key]
        print(f"{key:<16}{min(v):>7}{statistics.median(v):>9.0f}{max(v):>7}{len(v):>4}")
PY
rm -f "$tmp"
