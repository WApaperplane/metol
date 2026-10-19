#!/bin/sh
# install2.sh — 短命令友好的安装脚本（2026-10-19）
#
# 为什么单独一份：相机 telnet 的输入行大约 128 字符就被截断，长命令只会执行
# 到第一个分号前。所以安装逻辑全部放进脚本，telnet 侧只发一条
# `sh /mnt/mmc/_xfer/20261019/install2.sh`。
#
# 输出统一进 /mnt/mmc/install2.log（exec 重定向，不用 tee —— 机上 PATH 里没有 tee）。
set -u
B=/opt/usr/nx-ks
BK=$B/nxui/backup-lut-20261019
X=/mnt/mmc/_xfer/20261019
BB=$B/busybox
LOG=/mnt/mmc/install2.log

mkdir -p "$BK"
exec >> "$LOG" 2>&1

echo "=== install2 $(date) ==="

# 备份：只在 .prev 不存在时写，重复执行不会把新版当旧版备份
[ -f "$BK/nxui.arm.prev" ]           || cp "$B/nxui/nxui.arm"           "$BK/nxui.arm.prev"
[ -f "$BK/lut.sh.prev" ]             || cp "$B/lut.sh"                  "$BK/lut.sh.prev"
[ -f "$BK/nx_regtabwrite.arm.prev" ] || cp "$B/lut/nx_regtabwrite.arm"  "$BK/nx_regtabwrite.arm.prev"
[ -f "$BK/nxui.sh.prev" ]            || cp "$B/nxui.sh"                 "$BK/nxui.sh.prev"
[ -f "$BK/filmlab.sh.prev" ]         || cp "$B/filmlab.sh"              "$BK/filmlab.sh.prev"

# 装：先落 .new 再 mv，避免面板启动时读到半个文件
cp "$X/nxui.arm"           "$B/nxui/nxui.arm.new"           && mv -f "$B/nxui/nxui.arm.new"           "$B/nxui/nxui.arm"
cp "$X/lut.sh"             "$B/lut.sh.new"                  && mv -f "$B/lut.sh.new"                  "$B/lut.sh"
cp "$X/nx_regtabwrite.arm" "$B/lut/nx_regtabwrite.arm.new"  && mv -f "$B/lut/nx_regtabwrite.arm.new"  "$B/lut/nx_regtabwrite.arm"
cp "$X/nxui.sh"            "$B/nxui.sh.new"                 && mv -f "$B/nxui.sh.new"                 "$B/nxui.sh"
cp "$X/filmlab.sh"         "$B/filmlab.sh.new"              && mv -f "$B/filmlab.sh.new"              "$B/filmlab.sh"

chmod 755 "$B/nxui/nxui.arm" "$B/lut.sh" "$B/lut/nx_regtabwrite.arm" "$B/nxui.sh" "$B/filmlab.sh"
sync

echo "--- md5 ---"
$BB md5sum "$B/nxui/nxui.arm" "$B/lut.sh" "$B/lut/nx_regtabwrite.arm" "$B/nxui.sh" "$B/filmlab.sh"
echo "--- expect ---"
echo "8a7001d4e76335dce28545f31e6276f9  nxui.arm"
echo "813b6d22e33de436bfbb33716d3adeb2  lut.sh"
echo "896de680e99ae11c57082dfc6bf66913  nx_regtabwrite.arm"
echo "b0acc066a18c0e9da7f48d81a86e74ba  nxui.sh"
echo "48fe58a91bc2d919e48347d6991f81c7  filmlab.sh"
echo "--- backup ---"
ls -l "$BK"
echo "=== done ==="
