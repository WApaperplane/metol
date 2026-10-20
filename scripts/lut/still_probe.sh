#!/bin/sh
# @gate script=still_probe.sh opens=ro one_shot=1 gate=none pconly=0
#=====================================================================
# still_probe.sh — 只读诊断：取景器有 LUT、照片没有效果时先跑这个
#=====================================================================
# 判据链（p7 0x80382B30 选表实现）：
#   Still（JPEG）有两条互斥分支：
#     +0x21 == 1（屏幕色彩/OLED 开启）→ BV12 @0x80382B00 十二项
#     否则                            → Still6 @0x80382C5C 六项
#   只改 Still6 ⇒ 屏幕色彩开启的机器上取景正常、成片始终是原厂表。
#
# 本脚本只读：status 用 O_RDONLY 映射，getusr 只读设置，日志只读。
# 用法：sh still_probe.sh
#=====================================================================
set -u

D=/opt/usr/nx-ks
BB=$D/busybox
ST=/mnt/mmc/lut/state

pick() {
    for d in "$D/lut" /mnt/mmc/lut; do
        [ -x "$d/$1" ] && { echo "$d/$1"; return 0; }
    done
    return 1
}

REGT=$(pick nx_regtabwrite.arm) || { echo "ERR: nx_regtabwrite.arm not found"; exit 1; }
echo "tool: $REGT"
echo

echo "== 1) 三张登记表 + EP 寄存器 =="
OUT=$("$REGT" status 2>&1)
echo "$OUT"

count() { echo "$1" | $BB grep -o "$2" | $BB wc -l | $BB tr -d ' '; }

S=$(echo "$OUT" | $BB grep '^STILL6')
B=$(echo "$OUT" | $BB grep '^BV12')
V=$(echo "$OUT" | $BB grep '^VIEW4')

echo
echo "== 2) 相机设置（决定 Still 走哪条分支）=="
echo "OLEDCOLOR 108 : $(st cap capdtm getusr 108 2>/dev/null | $BB tr -d '\r')"
echo "COLORSPACE 50 : $(st cap capdtm getusr 50 2>/dev/null | $BB tr -d '\r')"
echo "SMARTFILTER 62: $(st cap capdtm getusr 62 2>/dev/null | $BB tr -d '\r')"

echo
echo "== 3) 上次 apply 的日志 =="
for f in write view view1 still bv; do
    p=$ST/$f.log
    [ -f "$p" ] || continue
    echo "-- $f.log"
    $BB grep -E 'READBACK|FAIL|REFUSE|bytes changed|stray|WRITE ' "$p" 2>/dev/null
done

echo
echo "== 4) 结论 =="
s18=$(count "$S" '81119f00')
b18=$(count "$B" '81119f00')
v18=$(count "$V" '81119f00')
echo "VIEW4  -> A18 : $v18 / 4"
echo "STILL6 -> A18 : $s18 / 6"
echo "BV12   -> A18 : $b18 / 12"
if [ "$s18" -eq 6 ] && [ "$b18" -eq 12 ]; then
    echo "RESULT: 两张 Still 表都指向工作槽 —— 登记表不是原因。"
    echo "        下一层：槽内容是否与 View 用的同一份表 / 拍照期是否重走选表。"
elif [ "$s18" -eq 6 ]; then
    echo "RESULT: 只有 Still6 被改，BV12 仍是原厂 ——"
    echo "        屏幕色彩开启时 Still 走 BV12，成片必然无效果（v8 缺陷）。"
    echo "        修复：更新 lut.sh + nx_regtabwrite.arm，再 apply 一次。"
elif [ "$s18" -eq 0 ]; then
    echo "RESULT: Still6 也没落地 —— apply 的 still 段失败，看上面 still.log。"
else
    echo "RESULT: 部分落地 —— 看 still.log 的 READBACK 与 stray 行。"
fi
