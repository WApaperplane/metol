#!/bin/bash
#=====================================================================
# EV_MOBILE.sh —— EV+WiFi 槽位（本项目重写版，修掉社区原版的卡死）
#=====================================================================
# ★★★ 2026-10-07 14:30 ★★★ 用户实测："EV+WiFi 会卡死"
#
# ★★★ 卡死的直接原因（社区原版 backup_original/EV_MOBILE.sh 就有，与 UI 无关）：
#   netcheck(){
#       while [[ ! -z $IP ]]; do
#           IP=`ip addr ls|grep inet|grep mlan0|cut -d/ -f1|...`
#           sleep 2
#       done
#       cleanup
#   }
#   netcheck &                ← ★★ 后台无限循环，每 2 秒跑一次 ip addr ls
#
#   ⇒ ★★ 单核 NX500 上，这就是"按了 EV+WiFi 后相机变慢"的根因
#   ⇒ ★ 且 $IP 在函数内首次使用前未初始化（依赖全局），
#     不同 shell 下 [[ ! -z $IP ]] 行为不一致 ⇒ 可能立即退也可能永不退
#   ⇒ ★ 13:53 我换上的 nxfilmui（EFL 事件循环）在此之上再抢一层单核 ⇒ 卡死加剧
#
# ★★★ 本版的原则
#   ① ★★ 【安全】UI 不再挂这个槽位（它已导致卡死）
#   ② ★★ 修掉 netcheck 的无限循环：有界轮询、到时安静退出、★ 绝不 cleanup
#   ③ ★ 加互斥锁（替代原版脆弱的 ps|grep 计数）
#   ④ 保留社区本意：EV+WiFi = 开 telnetd + FTP + 屏幕显示 IP
#=====================================================================

BB=/opt/usr/nx-ks/busybox
D=/opt/usr/nx-ks
LOCK=/tmp/ev_mobile.lock

# ---- 互斥锁：已在跑就退出，不重复起 telnetd/ftpd/netcheck
if [ -f "$LOCK" ]; then
    OLDPID=$($BB cat "$LOCK" 2>/dev/null)
    if [ -n "$OLDPID" ] && kill -0 "$OLDPID" 2>/dev/null; then
        nice -n +10 $D/popup_timeout " Already Running " 2
        exit 0
    fi
fi
echo $$ > "$LOCK"
trap "$BB rm -f $LOCK 2>/dev/null" EXIT

IP=$($BB ip addr ls 2>/dev/null | $BB grep inet | $BB grep mlan0 \
     | $BB cut -d/ -f 1 \
     | $BB grep -o '[0-9]\{1,3\}\.[0-9]\{1,3\}\.[0-9]\{1,3\}\.[0-9]\{1,3\}')

showip() {
    [ -z "$IP" ] && IP="WiFi off"
    nice -n +10 $BB $D/popup_timeout " Telnet/FTP: $IP " 10 &
}

cleanup() {
    killall -q telnetd 2>/dev/null
    killall -q onscreen_rc 2>/dev/null
    $BB rm -f /tmp/ev_mobile.lock
}

initserv() {
    $BB telnetd &
    # ★ FTP 根 = /opt/storage/sdcard（实测 FTP 21 在此提供）
    ($BB tcpsvd -u root -vE 0.0.0.0 21 $BB ftpd -w -v /opt/storage/sdcard) &
    showip
}

#★★★ netcheck 重写：★ 有界轮询，绝不无限循环、绝不 cleanup
#   它只是"顺带监控"，不是这个槽位的核心功能
#  ⇒ 到时/无 IP 就安静退出；★ 绝不 cleanup（那会杀掉用户刚开的 telnet/FTP）
netcheck() {
    N=0
    while [ $N -lt 30 ]; do                    # ★ 最多 30 轮 ≈ 60 秒
        $BB ip addr ls 2>/dev/null | $BB grep inet | $BB grep -q mlan0 || break
        N=$((N + 1))
        $BB sleep 2
    done
    return 0
}

initserv
# ★ 后台跑监控，限制优先级，且它自己会结束（≤60 秒）
nice -n +19 netcheck &
exit 0
