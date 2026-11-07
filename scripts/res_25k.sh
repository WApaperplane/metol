#!/bin/sh
# res_25k.sh —— 2.5K 片门全开开关（UHD 档实际录制 2560x1440）
#
# 原理：di-camera-app 的 UHD 构造器里有两条立即数指令决定输出尺寸
#   0xe4428  mov r8,  #2160   (高)     原值 878ea0e3
#   0xe442c  mov r10, #3840   (宽)     原值 0faca0e3
# 改成 1440 / 2560 即为 2.5K：
#   0xe4428  5a8ea0e3   0xe442c  0aaca0e3
#
# 与既有 res_UHD2K.sh 的差别：
#   · 既有脚本只做「开」，取消勾选后内存指令仍是 2K，必须重启才恢复
#   · 本脚本 off 会立刻把两条指令写回原值，无需重启
#   · 带 status 判据，可随时查询当前实际档位
#
# 用法：
#   res_25k.sh            切换（on <-> off）
#   res_25k.sh on         开启
#   res_25k.sh off        关闭并恢复 UHD
#   res_25k.sh status     只查询
set -u
D=/opt/usr/nx-ks
B=$D/busybox
AUTO=$D/auto
PERSIST=$AUTO/res_UHD2K.sh

V_UHD_H=878ea0e3
V_UHD_W=0faca0e3
V_2K_H=5a8ea0e3
V_2K_W=0aaca0e3

pop() { [ -x "$D/popup_timeout" ] && "$D/popup_timeout" "$1" "${2:-2}" >/dev/null 2>&1; }

# 读两个地址，输出补齐 8 位的十六进制；失败输出空
read_pair() {
    pid=$($B pidof di-camera-app 2>/dev/null | $B awk '{print $1}')
    case "$pid" in ''|*[!0-9]*) return 1;; esac
    out=$($D/poker "$pid" 0xe4428 0xe442c 2>/dev/null) || return 1
    h=$($B echo "$out" | $B sed -n 's/^0xe4428:\([0-9a-fA-F]*\).*/\1/p')
    w=$($B echo "$out" | $B sed -n 's/^0xe442c:\([0-9a-fA-F]*\).*/\1/p')
    [ -n "$h" ] && [ -n "$w" ] || return 1
    # 补齐前导零（poker 会省略高位 0）
    h=$($B printf '%08s' "$h" | $B tr ' ' '0')
    w=$($B printf '%08s' "$w" | $B tr ' ' '0')
    $B echo "$h $w"
}

cur_state() {
    pair=$(read_pair) || { echo unknown; return; }
    set -- $pair
    if [ "$1" = "$V_2K_H" ] && [ "$2" = "$V_2K_W" ]; then echo on
    elif [ "$1" = "$V_UHD_H" ] && [ "$2" = "$V_UHD_W" ]; then echo off
    else echo other; fi
}

apply_on() {
    $D/resup UHD 2K >/dev/null 2>&1
    # 持久化：开机沿用同一脚本
    if [ -x "$D/res_UHD2K.sh" ] && [ ! -f "$PERSIST" ]; then
        $B cp "$D/res_UHD2K.sh" "$PERSIST" 2>/dev/null
        $B chmod +x "$PERSIST" 2>/dev/null
    fi
}

apply_off() {
    $D/resup UHD UHD >/dev/null 2>&1
    $B rm -f "$PERSIST" 2>/dev/null
    $B sync
}

cmd="${1:-toggle}"
case "$cmd" in
status)
    s=$(cur_state)
    case "$s" in
    on)    echo "2.5K 开 (2560x1440)" ;;
    off)   echo "2.5K 关 (UHD 3840x2160)" ;;
    other) echo "非标准值：$(read_pair)" ;;
    *)     echo "相机进程不可用" ;;
    esac
    ;;
on)
    apply_on; sleep 0.3
    s=$(cur_state)
    if [ "$s" = on ]; then pop "2.5K 片门全开 已开启
实际录制 2560x1440" 3; echo "OK on"
    else pop "切换失败（当前 $s）" 3; echo "ERR on state=$s"; exit 1; fi
    ;;
off)
    apply_off; sleep 0.3
    s=$(cur_state)
    if [ "$s" = off ]; then pop "2.5K 已关闭
恢复 UHD 3840x2160" 3; echo "OK off"
    else pop "恢复失败（当前 $s）" 3; echo "ERR off state=$s"; exit 1; fi
    ;;
toggle)
    s=$(cur_state)
    if [ "$s" = on ]; then exec "$0" off
    elif [ "$s" = off ]; then exec "$0" on
    else pop "无法识别当前档位
$(read_pair)" 3; echo "ERR unknown"; exit 1; fi
    ;;
*)
    echo "usage: $0 [on|off|status|toggle]"; exit 2
    ;;
esac
