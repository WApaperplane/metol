#!/bin/sh
# tc.sh — NX500 TC 曲线（p7 内部 19 节点表）切换
#
# 用法:
#   tc.sh status            读源表，判断是否原厂，打印 Y[9] 与描述符
#   tc.sh list              列出 /mnt/mmc/tc/*.tcy 及其 Y[9]
#   tc.sh set <name|file>   应用曲线（.tcy 或内置名）
#   tc.sh off               恢复原厂
#
# 曲线文件格式: 19 行十进制，0..1023，严格递增，首 0 尾 1023；
#              空行与 # 开头行忽略。
#
# 安全: 地址链每次重新解析；写入后逐项回读；任何失败恢复原厂。
# 限制: 仅 NX500 1.12；改的是运行态内存，重启自动回到原厂。

set -u
B=/opt/usr/nx-ks/busybox
SRC=0x8062f71c
DIR=/mnt/mmc/tc
P0_PTR=0x817dccbc
PARAM_SIG=0x8062f5f8
GAMMA_VTBL=0x8062f6b0
GAMMA_OFF=0x170
DIRTY_OFF=4
CACHE_OFF=0xe8c

STOCK="0 16 36 64 105 156 223 305 397 500 606 704 786 860 918 960 991 1019 1023"
LOCK=/tmp/nxwa-tc.lock
LOCKED=0
NEEDS_RESTORE=0

die() { echo "ERR=$1"; exit "${2:-1}"; }

resolve() {
    P0=$($B devmem $P0_PTR 32) || die NO_DEV
    [ "$((P0))" -ge "$((0x81000000))" ] && [ "$((P0))" -lt "$((0x83fff000))" ] && [ "$((P0 % 4))" -eq 0 ] || die NO_PARAM
    sig=$($B devmem $((P0)) 32) || die READ_FAIL
    [ "$((sig))" -eq "$((PARAM_SIG))" ] || die BAD_PARAM_SIG
    G=$($B devmem $((P0 + GAMMA_OFF)) 32) || die READ_FAIL
    [ "$((G))" -ge "$((0x81000000))" ] && [ "$((G))" -lt "$((0x83fff000))" ] && [ "$((G % 4))" -eq 0 ] || die NO_GAMMA
    vt=$($B devmem $((G)) 32) || die READ_FAIL
    [ "$((vt))" -eq "$((GAMMA_VTBL))" ] || die BAD_GAMMA_VTBL
}

read_src() {
    i=0
    out=""
    while [ $i -lt 19 ]; do
        v=$($B devmem $((SRC + i * 4)) 32) || die READ_FAIL
        out="$out $((v))"
        i=$((i + 1))
    done
    echo "$out" | sed 's/^ //'
}

write_curve() {
    # $1 = 19 个空格分隔的值
    i=0
    for v in $1; do
        $B devmem $((SRC + i * 4)) 32 "$v" || return 1
        i=$((i + 1))
    done
    return 0
}

refresh_and_check() {
    # $1 = 目标 19 值；成功 0，失败 1
    # 不注入按键。轮询源表、完整缓存和描述符；未消费不能报告成功。
    $B devmem $((G + DIRTY_OFF)) 32 0xffffffff || return 1
    n=0
    while [ $n -lt 20 ]; do
        i=0; ok=1
        for v in $1; do
            c=$($B devmem $((G + CACHE_OFF + i * 4)) 32) || return 1
            s=$($B devmem $((SRC + i * 4)) 32) || return 1
            [ "$((c))" -eq "$v" ] && [ "$((s))" -eq "$v" ] || ok=0
            i=$((i + 1))
        done
        d=$($B devmem $((G + DIRTY_OFF)) 32) || return 1
        [ "$((d))" -ne "$((0xffffffff))" ] && [ "$ok" -eq 1 ] && return 0
        sleep 0.05
        n=$((n + 1))
    done
    return 1
}

cleanup() {
    status=$?
    trap - EXIT HUP INT TERM
    if [ "$NEEDS_RESTORE" -eq 1 ]; then
        if write_curve "$STOCK" && refresh_and_check "$STOCK"; then
            echo RESTORED=1
        else
            echo RESTORED=0
            status=4
        fi
    fi
    [ "$LOCKED" -eq 0 ] || $B rmdir "$LOCK" || status=4
    exit "$status"
}

write_guard() {
    $B mkdir "$LOCK" 2>/dev/null || die BUSY_LOCK 5
    LOCKED=1
    trap cleanup EXIT
    trap 'exit 129' HUP
    trap 'exit 130' INT
    trap 'exit 143' TERM
    pid=$($B pidof di-camera-app) || die NO_CAMERA
    case "$pid" in ''|*[!0-9]*) die NO_CAMERA ;; esac
    fds=$($B ls -l /proc/"$pid"/fd) || die NO_RECORDING_STATE
    if echo "$fds" | $B grep -ai 'l-w.*DCIM/.*\.mp4' >/dev/null; then die RECORDING 6; fi
    mode=$($B devmem 0x817dccb8 8) || die NO_MODE
    [ "$((mode))" -eq 1 ] || die UNSUPPORTED_MODE 6
}

validate() {
    # $1 = 19 个值；不合法返回 1 并打印原因
    n=0
    prev=-1
    for v in $1; do
        case "$v" in
        '' | *[!0-9]*) echo "ERR=BAD_VALUE:$v"; return 1 ;;
        esac
        [ "$v" -ge 0 ] && [ "$v" -le 1023 ] || { echo "ERR=OUT_OF_RANGE:$v"; return 1; }
        [ "$v" -gt "$prev" ] || { echo "ERR=NOT_STRICT:$n"; return 1; }
        prev=$v
        n=$((n + 1))
    done
    [ $n -eq 19 ] || { echo "ERR=BAD_COUNT:$n"; return 1; }
    first=$(echo $1 | cut -d' ' -f1)
    last=$(echo $1 | cut -d' ' -f19)
    [ "$first" -eq 0 ] || { echo "ERR=BAD_FIRST:$first"; return 1; }
    [ "$last" -eq 1023 ] || { echo "ERR=BAD_LAST:$last"; return 1; }
    return 0
}

load_curve() {
    # $1 = 名称或路径 → 输出 19 个值
    case "$1" in
    stock | off) echo "$STOCK"; return 0 ;;
    */*) f=$1 ;;
    *)
        if [ -f "$DIR/$1.tcy" ]; then
            f="$DIR/$1.tcy"
        else
            f="/opt/usr/nx-ks/tc/$1.tcy"
        fi
        ;;
    esac
    [ -f "$f" ] || { echo "ERR=NO_CURVE:$f"; return 1; }
    vals=$(grep -v '^[[:space:]]*#' "$f" 2>/dev/null | tr -d ' \t\r' | grep -v '^$' | tr '\n' ' ')
    echo "$vals"
}

cmd_status() {
    resolve
    cur=$(read_src) || die READ_FAIL
    d=$($B devmem $((G + DIRTY_OFF)) 32) || die READ_FAIL
    y9=$($B devmem $((SRC + 36)) 32) || die READ_FAIL
    if [ "$cur" = "$STOCK" ]; then
        echo "CURVE=stock"
    else
        echo "CURVE=custom"
    fi
    echo "Y9=$((y9))"
    echo "DIRTY=$d"
    echo "GAMMA=$G"
    echo "Y=$cur"
}

cmd_list() {
    for d in "$DIR" /opt/usr/nx-ks/tc; do
        [ -d "$d" ] || continue
        for f in "$d"/*.tcy; do
            [ -f "$f" ] || continue
            n=$(basename "$f" .tcy)
            y9=$(grep -v '^[[:space:]]*#' "$f" | tr -d ' \t\r' | grep -v '^$' | sed -n '10p')
            [ -n "$y9" ] || y9="?"
            echo "$n $y9 $d"
        done
    done
}

cmd_set() {
    [ $# -ge 1 ] || die USAGE
    vals=$(load_curve "$1")
    case "$vals" in
    ERR=*) echo "$vals"; exit 1 ;;
    esac
    validate "$vals" || exit 1
    write_guard
    resolve
    echo "TARGET=$1"
    NEEDS_RESTORE=1
    if ! write_curve "$vals"; then
        echo "ERR=WRITE_FAIL"
        exit 2
    fi
    if refresh_and_check "$vals"; then
        NEEDS_RESTORE=0
        echo "OK=1"
        echo "Y9=$($B devmem $((SRC + 36)) 32)"
        exit 0
    fi
    echo "ERR=REFRESH_FAIL"
    exit 3
}

case "${1:-status}" in
status) cmd_status ;;
list) cmd_list ;;
set) shift; cmd_set "$@" ;;
off) cmd_set stock ;;
*) echo "usage: tc.sh status|list|set <name|file>|off"; exit 64 ;;
esac
