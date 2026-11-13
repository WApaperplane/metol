#!/bin/bash
# 动态生成主菜单: 把当前 WiFi IP 与 Telnet 状态写进菜单标签。
# 由 menu.sh / loadgui.sh 在启动 mod_gui 前调用。
#
# 设计: gui_tpl.NX500 / gui_tpl.NX1 是模板(%%IP%% / %%TN%% 占位符),
# 生成结果覆盖 gui_ini.NX500 / gui_ini.NX1 —— mod_gui 按
# "目录参数 + gui_ini.机型" 读取, 覆盖它即可让每次开菜单都显示最新状态。
# 模板不存在时跳过生成, 保证菜单永远可用(防呆)。
#
# ★ 2026-10-10 提速版（菜单弹出慢的次要来源）：
#   ① IP 提取：原来 4 个进程（ip|grep|grep|cut|grep）⇒ 合成【1 个 awk】
#   ② 远程状态：原来 `ps -w | grep | grep` ⇒ 改 ssh_hint.sh --status（读 /proc/net/tcp 的监听项）
#   ③ 生成结果与现有 gui_ini 逐字节相同时【不写盘】（少一次 eMMC 写，且 mtime 稳定）
#
# ★ 2026-11-10：`%%TN%%` 的值从「Telnet开/关」改成「SSH开/关」。
#   telnetd 二进制从未进过 release 包（.gitignore 里裸 `telnetd` 规则），
#   新装机上那一行只能拉一个不存在的文件；telnet/FTP 已于 2026-11-02 退役，
#   远程通路是 dropbear ssh(22)。占位符名字保留，用户自定义模板不会失效。
BB=/opt/usr/nx-ks/busybox
D=/opt/usr/nx-ks

MODEL=$($BB head -1 /etc/version.info 2>/dev/null)
case "$MODEL" in
    NX1)
        TPL=/opt/usr/nx-ks/gui_tpl.NX1
        DST=/opt/usr/nx-ks/gui_ini.NX1
        ;;
    *)
        TPL=/opt/usr/nx-ks/gui_tpl.NX500
        DST=/opt/usr/nx-ks/gui_ini.NX500
        ;;
esac

[ -f "$TPL" ] || exit 0

# 当前 WiFi IP(mlan0) —— 单 awk 一次提取
IP=$($BB ip addr ls 2>/dev/null | $BB awk '
    /inet/ && /mlan0/ {
        for (i = 1; i <= NF; i++)
            if ($i ~ /^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+\//) { sub(/\/.*/, "", $i); print $i; exit }
    }')
[ -z "$IP" ] && IP="WiFi未开"

# 远程状态 —— ssh:22 是否在监听（端口比进程名可靠；pidof 在相机 busybox 上坑过）
if [ -x "$D/ssh_hint.sh" ]; then
    TN=$("$D/ssh_hint.sh" --status 2>/dev/null)
fi
[ -n "${TN:-}" ] || TN="SSH?"

TMP="$DST.tmp"
$BB sed -e "s/%%IP%%/$IP/g" -e "s/%%TN%%/$TN/g" "$TPL" > "$TMP" 2>/dev/null \
    || { $BB rm -f "$TMP"; exit 0; }

# 内容没变就别动它（省一次写盘；mtime 稳定 ⇒ 上层缓存更容易命中）
if [ -f "$DST" ] && $BB cmp -s "$TMP" "$DST"; then
    $BB rm -f "$TMP"
    exit 0
fi
# # exFAT 不覆盖式 rename：旧目录项会留在原地（2026-11-14 机上实测，每次 +1）
$BB rm -f "$DST" 2>/dev/null
mv -f "$TMP" "$DST"
exit 0
