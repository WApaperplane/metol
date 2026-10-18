#!/bin/bash
#=====================================================================
# EV_MOBILE.sh —— EV+WiFi 槽位 = LUT 滤镜入口（2026-10-18 改写）
#=====================================================================
# 变更说明：
#   · 原来的作用（起 telnetd + ftpd + 显示 IP）已移除 ——
#     主菜单里的 `telnet_toggle.sh` 已覆盖该职能，且每次按 EV+WiFi
#     都把 telnetd/ftpd 重起一遍没有意义。
#   · 现在只做一件事：打开 LUT 滤镜面板（NXUI 的 lut 模式）。
#   · 原版脚本备份在 /opt/usr/nx-ks/nxui/backup-lut-20261018/EV_MOBILE.sh
#=====================================================================
D=/opt/usr/nx-ks
BB=$D/busybox

if [ -x "$D/nxui.sh" ] && "$D/nxui.sh" available; then
    "$D/nxui.sh" lut
    exit $?
fi

# NXUI 不可用（未安装或已 disable）时给个提示，不再回退去起服务
if [ -x "$D/popup_timeout" ]; then
    nice -n +10 "$D/popup_timeout" " LUT: NXUI 未启用 " 3
fi
exit 1
