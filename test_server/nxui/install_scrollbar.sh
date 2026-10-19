#!/bin/sh
# install_scrollbar.sh — 2026-10-19 滚动条版 nxui.arm 落位（只换一个文件）
#
# 三个约束（沿用 install3.sh）：
#   1) telnet 输入行约 128 字符截断 ⇒ telnet 只发一条 "sh 本脚本"
#   2) telnet 断开整组收 SIGHUP ⇒ 用 busybox setsid 起，别让 cp 半途被杀
#   3) eMMC 写入慢 ⇒ 每步打点，靠 /mnt/mmc/install_scrollbar.log 判断进度
#
# ★ 必须同时更新 SD 母本 /mnt/mmc/scripts/nxui/nxui.arm：
#   引导器 install.sh 的增量同步是 cp -ar scripts/* → /opt/usr/nx-ks/（只覆盖不删除），
#   母本留旧版的话，下一次触发会把机身打回旧版。
set -u
B=/opt/usr/nx-ks
BK=$B/nxui/backup-scrollbar-20261019
SRC=/mnt/mmc/_xfer/nxui.arm
BB=$B/busybox
LOG=/mnt/mmc/install_scrollbar.log
WANT=cedc8305dd5fa506ab3c978dd802d9b7

mkdir -p "$BK"
exec >> "$LOG" 2>&1
echo "=== install_scrollbar $(date) ==="

# 备份：先删再拷，md5 自证（半截的 .prev 比没有更危险）
rm -f "$BK/nxui.arm.prev"
if cp "$B/nxui/nxui.arm" "$BK/nxui.arm.prev"; then
    echo "BACKUP $($BB md5sum "$BK/nxui.arm.prev")"
else
    echo "FAIL backup"
fi

install_one() {  # $1=源 $2=目标 $3=期望 md5
    [ -f "$1" ] || { echo "FAIL missing $1"; return 1; }
    rm -f "$2.new"
    cp "$1" "$2.new" || { echo "FAIL cp $2"; return 1; }
    got=$($BB md5sum "$2.new" | $BB cut -d' ' -f1)
    if [ "$got" != "$3" ]; then echo "FAIL md5 $2 got=$got"; rm -f "$2.new"; return 1; fi
    chmod 755 "$2.new"
    mv -f "$2.new" "$2" || { echo "FAIL mv $2"; return 1; }
    echo "INSTALL ok $2"
}

install_one "$SRC" "$B/nxui/nxui.arm"                "$WANT"
install_one "$SRC" "/mnt/mmc/scripts/nxui/nxui.arm"  "$WANT"
$BB sync

echo "--- final md5 ---"
$BB md5sum "$B/nxui/nxui.arm" /mnt/mmc/scripts/nxui/nxui.arm
echo "--- panel running? ---"
$BB ps | $BB grep -c '[n]xui.arm'
echo "=== done ==="
