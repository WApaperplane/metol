#!/bin/bash
renice -n -10 -p $$
[[ $(echo $(st cap capdtm getusr MONITOROUT) | grep LCD) > ""  ]] && /opt/usr/nx-ks/popup_timeout  " [ Initial Setup ... ] " 3 &
#############################################
# ★ 2026-11-14 默认码率下调（原 160/180/90/90/180）。
#   起因：GitHub Discussion 2026-11-12，ssam87 报「装 mod 后 SD 卡卡顿、无法录像」，
#   两张 NX500 + 同一张卡复现，换不带 mod 的卡就正常。
#   160 Mbps ≈ 20 MB/s 持续写入 —— 普通 UHS-I（Class 10 / U1）只有 10 MB/s，
#   写入缓冲一满就先是 UI 卡（"SD card lag"）再是录像 abort。原厂 4K Pro 约 60。
#   新默认留了提升但不越界：4K-Pro 80 / HD-Pro 100 / 4K-HQ 50 / HD-HQ 60 / VGA 40。
#   要回激进值：菜单「视频码率」逐档改（会持久化——br_set.sh 会重写本脚本），
#   或直接改下面这行后重新装机。
Pro4K=80; ProHD=100; Hq4K=50; HqHD=60; HqVGA=40 ; fps=4
#############################################
envbr="Pro4K=$Pro4K ProHD=$ProHD Hq4K=$Hq4K HqHD=$HqHD HqVGA=$HqVGA fps=$fps"
#
brr="$(/opt/usr/nx-ks/pokemonche pro1 $Pro4K) "
brr+="$(/opt/usr/nx-ks/pokemonche pro2 $ProHD) "
brr+="$(/opt/usr/nx-ks/pokemonche pro3 $ProHD) "
brr+="$(/opt/usr/nx-ks/pokemonche hq1 $Hq4K) "
brr+="$(/opt/usr/nx-ks/pokemonche hq2 $HqHD) "
brr+="$(/opt/usr/nx-ks/pokemonche hq3 $HqHD) "
brr+="$(/opt/usr/nx-ks/pokemonche hq4 $HqHD) "
brr+="$(/opt/usr/nx-ks/pokemonche hq5 $HqVGA) "
brr+="$(/opt/usr/nx-ks/pokemonche hq6 $HqVGA)"
#
$( sleep 7 && sync;sync;sync && /opt/usr/nx-ks/auto/a_init.sh && sync;sync;sync ) &
$( sleep 8 && /opt/usr/nx-ks/popup_timeout  " [ All Done - Enjoy ] " 3 ) &
#
sed -e "s/\${envbr}/""$envbr""/" -e "s/\${brr}/""$brr""/" -e "s/\${s}/"$s\ "/"  /opt/usr/nx-ks/init_auto.tp >  /opt/usr/nx-ks/auto/a_init.sh &
