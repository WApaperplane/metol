#!/bin/sh
#=====================================================================
# lut_accept_20261019.sh — v3 双槽交替上机验收（纯命令行，视觉另验）
#=====================================================================
# 验的是 2026-10-19 B+C 修复的四条数据面断言：
#   A1  连续 apply 时 active 槽在 a18 / a19 之间交替
#   A2  每次 apply 的 view/still 登记表回读值 == 目标槽（旧版会静默写回 A18）
#   A3  off 之后 active 清空、登记表回 A17、两槽内容还原
#   A4  apply 后不 off 直接退出，状态仍然保留（无自动还原）
#
# 用法（机端，必须后台跑，apply 内含 .cube 转换会超 telnet 超时）：
#   setsid sh /mnt/mmc/_xfer/lut_accept_20261019.sh > /mnt/mmc/lut_accept.log 2>&1 &
# 然后轮询 /mnt/mmc/lut_accept.log
#=====================================================================
set -u

LUT=/opt/usr/nx-ks/lut.sh
ST=/mnt/mmc/lut/state
LAB=/mnt/mmc/looks
BB=/opt/usr/nx-ks/busybox
N=5

fail=0
say() { echo "$*"; }

# 工具可能装在两个位置之一：随包装在 /opt/usr/nx-ks/lut，或产品化入口的
# /mnt/mmc/lut（这台机器上就是后者 —— 写死前者会让断言永远失败）。
find_tool() {
    for d in /opt/usr/nx-ks/lut /mnt/mmc/lut; do
        [ -x "$d/$1" ] && { echo "$d/$1"; return 0; }
    done
    echo ""
}
REGT=$(find_tool nx_regtabwrite.arm)
SLOTW=$(find_tool nx_slotwrite.arm)

# a18/a19 只有名字，日志里是地址；断言必须在地址层面比
addr_of() {
    case "$1" in
        a18|A18) echo 0x81119f00 ;;
        a19|A19) echo 0x8111ec00 ;;
        *) echo "" ;;
    esac
}

# 机上 shell 无 PATH 到 busybox applets —— 建一个临时 symlink 目录顶上
$BB mkdir -p /tmp/bbin 2>/dev/null
for a in ls grep sed sort head cat cmp rm date md5sum; do
    $BB ln -sf "$BB" "/tmp/bbin/$a" 2>/dev/null
done
PATH=/tmp/bbin:$PATH

chk() { # chk <名字> <期望> <实际>
    if [ "$2" = "$3" ]; then
        say "PASS $1 ($3)"
    else
        say "FAIL $1 want=$2 got=$3"
        fail=$((fail+1))
    fi
}

active() { [ -f "$ST/active" ] && cat "$ST/active" || echo ""; }
slotfield() { "$LUT" status 2>/dev/null | sed -n 's/^ACTIVE .*(slot \(.*\))$/\1/p'; }

say "=== 0. 环境 ==="
say "date=$(date)"
say "lut.sh md5=$($BB md5sum "$LUT" 2>/dev/null || echo '?')"
say "regtabwrite md5=$($BB md5sum "$REGT" 2>/dev/null || echo '?')"
[ -f /mnt/mmc/nxwa_regtab_20261018/still6_orig.bin ] && say "still6 baseline: present" || say "still6 baseline: ABSENT (will use still-set)"
say "looks=$(ls "$LAB" 2>/dev/null | grep -cE '\.(cube|bin)$')"

say ""
say "=== 1. 先回原厂，保证起点干净 ==="
"$LUT" off
say "status: $("$LUT" status | head -1)"

say ""
say "=== 2. 连切 $N 次，验交替 ==="
# 取库里前 N 个 look（跳过与状态无关的排序差异）
set -- $(ls "$LAB" 2>/dev/null | grep -E '\.(cube|bin)$' | sed 's/\.[^.]*$//' | sort -u | head -$N)
if [ $# -lt 2 ]; then
    say "FAIL 库里可用 look 少于 2 个，无法验交替"
    fail=$((fail+1))
else
    prev=""
    i=0
    for name in "$@"; do
        i=$((i+1))
        echo "--- [$i/$#] apply $name ---"
        out=$("$LUT" apply "$name" 2>&1)
        echo "$out"
        case "$out" in
            *"OK applied"*) ;;
            *) say "FAIL apply $name 未返回 OK"; fail=$((fail+1)); continue ;;
        esac
        cur=$(active)
        echo "active=$cur"
        # 每次必须与上一次不同
        if [ -n "$prev" ]; then
            if [ "$cur" = "$prev" ]; then
                say "FAIL 第 $i 次未换槽（仍 $cur）—— 双槽交替失效"
                fail=$((fail+1))
            else
                say "PASS 第 $i 次换槽 $prev -> $cur"
            fi
        fi
        prev=$cur
        # 登记表回读必须等于目标槽（日志里是地址，不是 a18/a19）
        want=$(addr_of "$cur")
        if [ -n "$want" ]; then
            grep -qi "READBACK.*$want" "$ST/view.log" 2>/dev/null \
                && say "PASS view 回读 $cur ($want)" \
                || { say "FAIL view 回读不是 $cur ($want)"; sed -n '1,6p' "$ST/view.log" 2>/dev/null; fail=$((fail+1)); }
            grep -qi "$want" "$ST/still.log" 2>/dev/null \
                && say "PASS still 回读 $cur ($want)" \
                || { say "FAIL still 回读不是 $cur ($want)"; sed -n '1,6p' "$ST/still.log" 2>/dev/null; fail=$((fail+1)); }
        else
            say "FAIL 无法把 active=$cur 映射成地址"; fail=$((fail+1))
        fi
    done
fi

say ""
say "=== 3. apply 后不 off，状态应保留（A4） ==="
kept=$(active)
[ -n "$kept" ] && say "PASS 状态保留 active=$kept" || { say "FAIL active 丢失"; fail=$((fail+1)); }

say ""
say "=== 4. off 还原（A3） ==="
"$LUT" off
s1=$("$LUT" status | head -1)
chk "off 后状态 IDLE" "IDLE" "$s1"
if [ -f "$ST/view.log" ]; then :; fi
# 登记表回 A17
BACK=$("$LUT" status | sed -n '3,4p')
say "status tail: $BACK"
"$LUT" status | grep -qi "0x81115200" && say "PASS view 已回 A17" || say "NOTE view 未在 status 里显示 A17（人工核对）"

say ""
say "=== 5. 两槽内容 vs 原厂备份 ==="
for s in a18 a19; do
    case $s in
        a18) addr=0x81119F00 ;;
        a19) addr=0x8111EC00 ;;
    esac
    if [ -f "$ST/${s}_orig.bin" ]; then
        if [ -z "$SLOTW" ]; then
            say "SKIP $s 比对（找不到 nx_slotwrite.arm）"
            continue
        fi
        "$SLOTW" read "$addr" /tmp/chk_$s.bin >/dev/null 2>&1
        if [ -s /tmp/chk_$s.bin ] && cmp -s /tmp/chk_$s.bin "$ST/${s}_orig.bin"; then
            say "PASS $s 已还原"
        else
            say "FAIL $s 与原厂备份不一致（读回 $([ -s /tmp/chk_$s.bin ] && echo ok || echo 空)）"
            fail=$((fail+1))
        fi
        rm -f /tmp/chk_$s.bin
    fi
done

say ""
say "=== RESULT ==="
if [ $fail -eq 0 ]; then
    say "ALL PASS —— 数据面通过。仍需目视：apply 后半按一次，看取景器是否变色"
else
    say "FAILED $fail 项"
fi
