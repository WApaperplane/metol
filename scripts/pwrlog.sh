#!/bin/sh
# pwrlog.sh — 把「关机前最后一刻」留在 SD 上（2.88.0-nxwa.15.1 debug 版专用）
#
# 为什么需要它（2026-11-10）：
#   有用户在「挑选 LUT」过程中遇到相机自己走关机画面断电。这个现象只可能是
#   di-camera-app 的受控关机（电源键 / power_timer 自动关机 / 低电 / 镜头或
#   快门错 / 拔卡），但关机后 /tmp 全丢、dlog 也没接，事后什么都没有。
#   本脚本每 5 min 往 SD 追加一行状态（PWRLOG_PERIOD 可覆盖；2026-11-13 从 30 s
#   调高——SD 卡是 exFAT，写得太勤对卡本身就不友好，而关机取证不需要分钟级粒度）；下次开机第一件事就是把上一次的尾巴抄进
#   同一份日志。关机 → 再开 → `pwrlog.sh dump` 就能看到断在哪一步。
#
# 采样项（全部只读，不碰相机状态）：
#   up     /proc/uptime 秒数
#   pwr    APPPREF_POWER_SAVE（0x230）—— 自动关机定时器的设置值
#   cap    APPPREF_CAP_POWER_OFF_STATUS（0xc2c4）—— 上一次关机的分类，开机时读
#   ssh    :0016 是否在监听
#   ui     nxui.arm 是否在跑（LUT/FilmLab 面板）
#   lut    /tmp/nx/lut/current（当前落地的表；旧版在 /mnt/mmc/lut/state/current）
#
# 用法：
#   pwrlog.sh boot    开机调用：记一条 BOOT + 上一次断电前的尾巴
#   pwrlog.sh start   起后台采样（幂等，同一时刻只会有一个）
#   pwrlog.sh stop
#   pwrlog.sh once    采一条（调试用）
#   pwrlog.sh note <文本>   追加一条带时间戳的事件（lut.sh 的 apply/off 用）
#   pwrlog.sh dump [n]      打印最后 n 行（默认 40）
#
# 日志：/mnt/mmc/nx-ks/pwrlog.txt（超过 200 KB 时只保留最后 100 KB，避免写爆卡）
set -u

D=/opt/usr/nx-ks
BB=$D/busybox
LOG=/mnt/mmc/nx-ks/pwrlog.txt
PID=/tmp/nxwa-pwrlog.pid
PERIOD=${PWRLOG_PERIOD:-300}
PREFMAN=$(command -v prefman 2>/dev/null || echo /usr/bin/prefman)

mkdir -p /mnt/mmc/nx-ks 2>/dev/null

stamp() { $BB date +%H:%M:%S 2>/dev/null; }

uptime_s() {
    up=$($BB cut -d' ' -f1 /proc/uptime 2>/dev/null)
    echo "${up%%.*}"
}

pref() {
    v=$("$PREFMAN" get 0 "$1" l 2>/dev/null | $BB awk '/value *= */{print $3; exit}')
    echo "${v:-?}"
}

ssh_listening() {
    [ -r /proc/net/tcp ] || { echo 0; return; }
    $BB awk '$4 == "0A" && $2 ~ /:0016$/ { found = 1 } END { print (found ? 1 : 0) }' /proc/net/tcp
}

ui_running() {
    $BB ps -o args 2>/dev/null | $BB grep -q '[n]xui.arm' && echo 1 || echo 0
}

lut_current() {
    # 2026-11-13：current 已迁到 tmpfs（见 scripts/lut.sh 顶部），SD 上的旧路径
    # 只在"升级后没重启、老会话还在写"时可能有值，作为兜底保留。
    for _c in /tmp/nx/lut/current /mnt/mmc/lut/state/current; do
        if [ -s "$_c" ]; then $BB head -1 "$_c"; return 0; fi
    done
    echo "-"
}

sample() {
    printf '%s|up=%s|pwr=%s|ssh=%s|ui=%s|lut=%s\n' \
        "$(stamp)" "$(uptime_s)" "$(pref 0x230)" "$(ssh_listening)" \
        "$(ui_running)" "$(lut_current)"
}

rotate() {
    [ -f "$LOG" ] || return 0
    sz=$($BB wc -c < "$LOG" 2>/dev/null | $BB tr -d ' ')
    [ -n "${sz:-}" ] || return 0
    [ "$sz" -gt 204800 ] || return 0
    $BB tail -c 102400 "$LOG" > "$LOG.tmp" 2>/dev/null \n        && { # exFAT 不覆盖式 rename：旧目录项会留在原地（2026-11-14 机上实测，每次 +1）
             $BB rm -f "$LOG" 2>/dev/null; $BB mv -f "$LOG.tmp" "$LOG"; }
}

case "${1:-once}" in
    boot)
        rotate
        {
            printf '=== BOOT %s (up=%s) ===\n' "$(stamp)" "$(uptime_s)"
            printf '%s|CAP_POWER_OFF_STATUS=%s|POWER_SAVE=%s|DISPLAY_SAVE=%s\n' \
                "$(stamp)" "$(pref 0xc2c4)" "$(pref 0x230)" "$(pref 0x22c)"
            printf 'prev tail:\n'
            $BB tail -3 "$LOG" 2>/dev/null | $BB grep -v '^prev tail:$' | $BB sed 's/^/  /'
        } >> "$LOG" 2>&1
        exit 0
        ;;
    loop)
        # 内部动词：真正干活的循环，由 start 用 setsid 拉起。
        # 独占锁：setsid 的 $! 不一定是循环自己的 pid，靠 pid 文件判会重复起。
        exec 9>/tmp/nxwa-pwrlog.lock
        $BB flock -n 9 || exit 0
        while :; do
            rotate
            sample >> "$LOG" 2>/dev/null
            $BB sleep "$PERIOD"
        done
        ;;
    start)
        if [ -s "$PID" ]; then
            p=$(cat "$PID" 2>/dev/null)
            case "$p" in
                ''|*[!0-9]*) : ;;
                *) [ -r "/proc/$p/cmdline" ] && exit 0 ;;
            esac
        fi
        $BB setsid sh "$0" loop >>/dev/null 2>&1 &
        echo $! > "$PID"
        exit 0
        ;;
    stop)
        [ -s "$PID" ] && kill "$(cat "$PID" 2>/dev/null)" 2>/dev/null
        # pid 文件可能记的是 setsid 包装进程 ⇒ 再按 cmdline 扫一遍
        for d in /proc/[0-9]*; do
            p=${d#/proc/}
            [ -r "$d/cmdline" ] || continue
            case "$($BB tr '\000' ' ' < "$d/cmdline" 2>/dev/null)" in
                *pwrlog.sh*loop*) kill "$p" 2>/dev/null ;;
            esac
        done
        $BB rm -f "$PID"
        exit 0
        ;;
    note)
        shift
        [ $# -gt 0 ] || exit 2
        printf '%s|NOTE|%s\n' "$(stamp)" "$*" >> "$LOG" 2>/dev/null
        exit 0
        ;;
    once)
        rotate
        sample >> "$LOG" 2>/dev/null
        $BB tail -1 "$LOG"
        ;;
    dump)
        n=${2:-40}
        case "$n" in ''|*[!0-9]*) n=40 ;; esac
        $BB tail -n "$n" "$LOG" 2>/dev/null
        ;;
    *)
        echo "usage: pwrlog.sh boot|start|stop|once|note <text>|dump [n]"
        exit 2
        ;;
esac
