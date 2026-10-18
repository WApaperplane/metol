#!/bin/sh
# @gate script=look2slot.sh opens=rw one_shot=1 gate=none
# =====================================================================
# look2slot.sh — 把 SD 卡上的 .cube 批量转成 19,712 字节槽表（相机端）
# =====================================================================
# 只写文件，不碰任何寄存器、不碰 /dev/mem。转换失败的文件保持原样，
# 不影响同批其他文件。
#
# 目录: /mnt/mmc/filmlab/looks/
#   xxx.cube  ->  xxx.bin   (19712 B = 19652 表本体 + 60 B 零填充)
#
# 用法:
#   look2slot.sh              转换 looks/ 下所有 .cube
#   look2slot.sh -f           强制重转（忽略时间戳）
#   look2slot.sh <dir>        指定其他目录
#
# 输出表交给 nx_slotwrite.arm 写入空闲槽，再由 nx_regtabwrite.arm
# 改 View4[3] / Still6 指向它。
# =====================================================================

D=${NXWA_LOOK_DIR:-/mnt/mmc/filmlab/looks}
CONV=${NXWA_CUBE2LUT:-/opt/usr/nx-ks/cube2lut.arm}
SLOT_LEN=19712

FORCE=0
for a in "$@"; do
  case "$a" in
    -f) FORCE=1 ;;
    -*) echo "ERR: unknown option $a"; exit 2 ;;
    *)  D=$a ;;
  esac
done

[ -x "$CONV" ] || { echo "ERR: 缺转换器 $CONV"; exit 1; }
[ -d "$D" ] || { echo "ERR: 目录不存在 $D"; exit 1; }

BB=/opt/usr/nx-ks/busybox
[ -x "$BB" ] || BB=""

# 相机 PATH 上没有 busybox，优先用绝对路径的那份；没有则用系统同名命令
run() { if [ -n "$BB" ]; then "$BB" "$@"; else "$@"; fi; }

size_of() { run stat -c %s "$1" 2>/dev/null; }

ok=0; skip=0; bad=0
echo "=== look2slot: $D ==="

for c in "$D"/*.cube; do
  [ -f "$c" ] || continue
  base=${c%.cube}
  out=$base.bin
  name=${base##*/}

  if [ "$FORCE" -eq 0 ] && [ -f "$out" ] && [ ! "$c" -nt "$out" ]; then
    echo "SKIP  $name.bin (up to date)"
    skip=$((skip + 1))
    continue
  fi

  printf 'CONV  %s.cube ... ' "$name"
  "$CONV" "$c" "$out" > "$base.conv.log" 2>&1
  rc=$?

  if [ $rc -ne 0 ]; then
    echo "FAIL (rc=$rc)"
    run tail -n 2 "$base.conv.log" 2>/dev/null
    bad=$((bad + 1))
    continue
  fi

  n=$(size_of "$out")
  if [ "$n" != "$SLOT_LEN" ]; then
    echo "FAIL (size=$n, want $SLOT_LEN)"
    bad=$((bad + 1))
    continue
  fi

  grid=$(run grep 'GRID n' "$base.conv.log" 2>/dev/null | run sed 's/.*= //')
  echo "ok  grid=${grid}^3 -> 19712B"
  ok=$((ok + 1))
done

echo "--- converted=$ok skipped=$skip failed=$bad ---"
[ "$ok" -eq 0 ] && [ "$skip" -eq 0 ] && echo "NOTE: $D 下没有 .cube"
exit $([ "$bad" -eq 0 ] && echo 0 || echo 1)
