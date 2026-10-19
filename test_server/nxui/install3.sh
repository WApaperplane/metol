#!/bin/sh
# install3.sh — 2026-10-19 安装（setsid 后台执行版）
#
# 三个约束决定了写法：
#   1) 相机 telnet 输入行约 128 字符就截断 ⇒ 逻辑全在脚本里，telnet 只发一条。
#   2) telnet 断开时整组会收 SIGHUP ⇒ 必须 setsid 脱离会话，否则 cp 半途被杀，
#      留下半个 .prev，后面 "[ -f .prev ] || cp" 就再也不会补。
#   3) eMMC 写入慢（460 KB 十几秒）⇒ 每步都打点，靠日志判断进度。
#
# 输出 /mnt/mmc/install3.log，用 FTP 取回。
set -u
B=/opt/usr/nx-ks
BK=$B/nxui/backup-lut-20261019
X=/mnt/mmc/_xfer/20261019
BB=$B/busybox
LOG=/mnt/mmc/install3.log

mkdir -p "$BK"
exec >> "$LOG" 2>&1

echo "=== install3 $(date) ==="

# 备份：先删再拷，然后用 md5 证明拷贝完整（半截的 .prev 比没有更危险）
backup() {  # $1=源 $2=备份
    [ -f "$1" ] || { echo "SKIP missing $1"; return 0; }
    rm -f "$2"
    cp "$1" "$2" || { echo "FAIL cp $1"; return 1; }
    a=$($BB md5sum "$1" | $BB cut -d' ' -f1)
    b=$($BB md5sum "$2" | $BB cut -d' ' -f1)
    if [ "$a" = "$b" ]; then echo "BACKUP ok $2"; else echo "FAIL backup mismatch $2"; return 1; fi
}
backup "$B/nxui/nxui.arm"           "$BK/nxui.arm.prev"
backup "$B/lut.sh"                  "$BK/lut.sh.prev"
backup "$B/lut/nx_regtabwrite.arm"  "$BK/nx_regtabwrite.arm.prev"
backup "$B/nxui.sh"                 "$BK/nxui.sh.prev"
backup "$B/filmlab.sh"              "$BK/filmlab.sh.prev"

# 安装：同样先校验再 mv，失败就保留旧文件不动
install_one() {  # $1=源 $2=目标 $3=期望 md5
    [ -f "$1" ] || { echo "FAIL missing $1"; return 1; }
    rm -f "$2.new"
    cp "$1" "$2.new" || { echo "FAIL cp $1"; return 1; }
    got=$($BB md5sum "$2.new" | $BB cut -d' ' -f1)
    if [ "$got" != "$3" ]; then echo "FAIL md5 $2 got=$got want=$3"; rm -f "$2.new"; return 1; fi
    chmod 755 "$2.new"
    mv -f "$2.new" "$2" || { echo "FAIL mv $2"; return 1; }
    echo "INSTALL ok $2"
}
install_one "$X/nxui.arm"           "$B/nxui/nxui.arm"          8a7001d4e76335dce28545f31e6276f9
install_one "$X/lut.sh"             "$B/lut.sh"                 813b6d22e33de436bfbb33716d3adeb2
install_one "$X/nx_regtabwrite.arm" "$B/lut/nx_regtabwrite.arm" 896de680e99ae11c57082dfc6bf66913
install_one "$X/nxui.sh"            "$B/nxui.sh"                b0acc066a18c0e9da7f48d81a86e74ba
install_one "$X/filmlab.sh"         "$B/filmlab.sh"             48fe58a91bc2d919e48347d6991f81c7

$BB sync
echo "--- final md5 ---"
$BB md5sum "$B/nxui/nxui.arm" "$B/lut.sh" "$B/lut/nx_regtabwrite.arm" "$B/nxui.sh" "$B/filmlab.sh"
echo "--- backup dir ---"
ls -l "$BK"
echo "=== done ==="
