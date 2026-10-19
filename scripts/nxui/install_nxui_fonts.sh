#!/bin/sh
# install_nxui_fonts.sh — 在相机上安装 NXUI 的子集字体与字体配置
#
# 幂等：重复执行只覆盖同名文件。字体是纯资源，nxui.arm 会在打开失败时
# 自动回退到按文件开系统字体，所以这个脚本失败也不会让面板起不来。
#
# 用法（相机上）:
#   sh /mnt/mmc/_xfer/20261019/install_nxui_fonts.sh [/mnt/mmc/_xfer/20261019]
set -eu
D=/opt/usr/nx-ks
SRC=${1:-/mnt/mmc/_xfer/20261019}
CACHE=/mnt/mmc/nxui/fc-cache

[ -f "$SRC/NXUI_CJK.ttf" ] || { echo "missing $SRC/NXUI_CJK.ttf"; exit 1; }
[ -f "$SRC/fonts.conf" ] || { echo "missing $SRC/fonts.conf"; exit 1; }

mkdir -p "$D/nxui/fonts" "$CACHE"
cp "$SRC/NXUI_CJK.ttf" "$D/nxui/fonts/NXUI_CJK.ttf.new"
cp "$SRC/fonts.conf" "$D/nxui/fonts.conf.new"
chmod 644 "$D/nxui/fonts/NXUI_CJK.ttf.new" "$D/nxui/fonts.conf.new"
mv -f "$D/nxui/fonts/NXUI_CJK.ttf.new" "$D/nxui/fonts/NXUI_CJK.ttf"
mv -f "$D/nxui/fonts.conf.new" "$D/nxui/fonts.conf"
sync
md5sum "$D/nxui/fonts/NXUI_CJK.ttf" "$D/nxui/fonts.conf"
echo "FONTS INSTALLED dir=$D/nxui/fonts cache=$CACHE"
