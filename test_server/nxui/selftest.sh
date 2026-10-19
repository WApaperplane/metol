#!/bin/sh
# selftest.sh — 装完后确认面板能在真机上起来（不写状态文件，1.5 秒自退）
D=/opt/usr/nx-ks
export DISPLAY=:0 LC_ALL=C
export FONTCONFIG_FILE=$D/nxui/fonts.conf
export NXUI_STATE_DIR=/tmp/nxui-selftest
$D/nxui/nxui.arm --root $D --recipes /mnt/mmc/filmlab/recipes.txt \
    --engine $D/filmlab.sh --live --lifetime-ms 1500 > /mnt/mmc/nxui_selftest.log 2>&1
echo "filmlab_rc=$?" >> /mnt/mmc/nxui_selftest.log

# LUT 模式：列表来自 lut.sh list（与 nxui.sh 里的生成方式一致）
mkdir -p /tmp/nxui-selftest
sh $D/lut.sh list > /tmp/look.names 2>/dev/null || echo "LUTLIST_FAIL" >> /mnt/mmc/nxui_selftest.log
: > /tmp/look.rec
while IFS= read -r name; do
    [ -n "$name" ] || continue
    printf '%s|%s|0|0|0|0|0|0|0\n' "$name" "$name" >> /tmp/look.rec
done < /tmp/look.names
$D/nxui/nxui.arm --root $D --recipes /tmp/look.rec --engine $D/lut.sh \
    --lut --live --lifetime-ms 1500 >> /mnt/mmc/nxui_selftest.log 2>&1
echo "lut_rc=$?" >> /mnt/mmc/nxui_selftest.log
echo done >> /mnt/mmc/nxui_selftest.log
