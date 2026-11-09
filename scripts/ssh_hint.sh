#!/bin/sh
# ssh_hint.sh — 远程登录提示（菜单「IP: x.x.x.x [SSH开]」那一行）
#
# 背景（2026-11-10 实测复盘）：
#   telnetd 二进制从来没进过 release 包 —— .gitignore 里一条裸 `telnetd` 规则
#   把 scripts/telnetd 挡在 git 之外，本地树里也没有它，于是每次打包都少这一个
#   文件。结果新装机上「Telnet 开/关」那一行只会去拉一个不存在的 $D/telnetd。
#   telnet/FTP 自 2026-11-02 起已退役，远程通路改为 dropbear ssh（22 端口）。
#   本脚本就是那条通知：菜单上显示状态，按下给连接串，顺便补齐 ssh 的启动。
#
# 判据用 /proc/net/tcp 的监听项（:0016 = 22），不用 pidof —— 相机 busybox 的
# pidof 行为在 2026-11-08 已经坑过一次，端口比进程名可靠。
#
# 用法：
#   ssh_hint.sh            打印状态与连接串
#   ssh_hint.sh --status   只打印「SSH开」/「SSH关」（gen_menu.sh 用）
#   ssh_hint.sh --ui       相机屏上弹窗（菜单按钮调用；没起就顺手拉起）
#   ssh_hint.sh --start    仅在没监听时拉起 dropbear，不弹窗
set -u

D=/opt/usr/nx-ks
BB=$D/busybox
DB=$D/dropbear
MODE=${1:-show}

ip_addr() {
    $BB ip addr ls 2>/dev/null | $BB awk '
        /inet/ && /mlan0/ {
            for (i = 1; i <= NF; i++)
                if ($i ~ /^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+\//) { sub(/\/.*/, "", $i); print $i; exit }
        }'
}

listening() {
    [ -r /proc/net/tcp ] || return 1
    $BB awk '$4 == "0A" && $2 ~ /:0016$/ { found = 1 } END { exit !found }' /proc/net/tcp
}

start_ssh() {
    listening && return 0
    [ -x "$DB/dropbear" ] || return 1
    # SD 卡 FAT 挂载会丢可执行位，cp -ar 之后是 0644 ⇒ 每次启动前补位
    chmod +x "$DB/dropbear" "$DB/dropbearkey" "$DB/sftp-server" "$DB/run.sh" 2>/dev/null
    [ -f "$DB/dropbear_ed25519_host_key" ] || \
        "$DB/dropbearkey" -t ed25519 -f "$DB/dropbear_ed25519_host_key" >/dev/null 2>&1
    if [ -f "$DB/authorized_keys" ]; then
        mkdir -p /root/.ssh 2>/dev/null
        cp -f "$DB/authorized_keys" /root/.ssh/authorized_keys 2>/dev/null
        chmod 700 /root/.ssh 2>/dev/null
        chmod 600 /root/.ssh/authorized_keys 2>/dev/null
    fi
    $BB setsid "$DB/run.sh" -F -B -p 22 \
        -r "$DB/dropbear_ed25519_host_key" >>/tmp/db.log 2>&1 </dev/null &
    i=0
    while [ "$i" -lt 20 ]; do
        listening && return 0
        i=$((i + 1))
        $BB sleep 0.1
    done
    listening
}

state() {
    if listening; then echo "SSH开"; else echo "SSH关"; fi
}

case "$MODE" in
    --status)
        state
        exit 0
        ;;
    --start)
        start_ssh && { echo "OK ssh listening on 22"; exit 0; }
        echo "ERR ssh not listening; see /tmp/db.log"
        exit 1
        ;;
    --ui|show) ;;
    *)
        echo "usage: ssh_hint.sh [--status|--ui|--start]"
        exit 2
        ;;
esac

[ "$MODE" = --ui ] && start_ssh

IP=$(ip_addr)
[ -n "${IP:-}" ] || IP="WiFi未开"
ST=$(state)

if [ "$MODE" = --ui ]; then
    if [ "$ST" = "SSH开" ]; then
        MSG="ssh root@$IP  空密码"
    else
        MSG="ssh 未启动 · 看 /tmp/db.log"
    fi
    if [ -x "$D/popup_timeout" ]; then
        "$D/popup_timeout" "$MSG" 5 >/dev/null 2>&1 &
    fi
    echo "SSH $ST ip=$IP"
    exit 0
fi

echo "state : $ST"
echo "ip    : $IP"
echo "login : ssh root@$IP   (端口 22，空密码；或把自己的公钥写进 $DB/authorized_keys)"
[ "$ST" = "SSH开" ] || echo "hint  : sh $D/ssh_hint.sh --start    # 或看 /tmp/db.log"
