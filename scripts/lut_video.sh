#!/bin/sh
# Per-boot video LUT watcher paired with LUT apply/off. Never toggles recording.
set -u
D=/opt/usr/nx-ks
B=$D/busybox
STATE=/tmp/nxwa-lut-video
PIDFILE=$STATE/pid
DURATION=$STATE/duration
LOG=$STATE/watch.log
BIN=
for d in "$D/lut" /mnt/mmc/lut; do
    [ -x "$d/nx_lutload.arm" ] && { BIN=$d/nx_lutload.arm; break; }
done
control_lock() {
    $B mkdir -p "$STATE" || return 1
    exec 9>"$STATE/control.lock"
    $B flock -n 9 || { echo 'ERR video controller is busy';return 1; }
}
alive() {
    [ -s "$PIDFILE" ] || return 1
    p=$(cat "$PIDFILE")
    case "$p" in ''|*[!0-9]*) return 1;; esac
    [ -r "/proc/$p/cmdline" ] && kill -0 "$p" 2>/dev/null || return 1
    args=$($B tr '\000' ' ' < "/proc/$p/cmdline")
    case "$args" in *nx_lutload.arm\ watch\ *) return 0;; *) return 1;; esac
}
stop_running() {
    if alive; then
        kill -TERM "$p" || return 1
        i=0
        while alive && [ "$i" -lt 20 ]; do i=$((i+1));sleep 0.1;done
        if alive; then echo 'ERR watcher is still stopping';return 1;fi
    fi
}
case "${1:-status}" in
on|start)
    control_lock || exit 1
    [ -n "$BIN" ] || { echo 'ERR nx_lutload.arm is missing'; exit 1; }
    seconds=${2:-0}
    case "$seconds" in ''|*[!0-9]*) echo 'ERR duration must be 0..3600 seconds (0=until LUT off)'; exit 2;; esac
    [ "$seconds" -ge 0 ] && [ "$seconds" -le 3600 ] || exit 2
    if alive; then
        old_duration=$(cat "$DURATION" 2>/dev/null || echo unknown)
        if [ "$old_duration" = "$seconds" ]; then echo "OK video LUT already on (pid=$p)";exit 0;fi
        stop_running || exit 1
    fi
    camera=$($B pidof di-camera-app)
    case "$camera" in ''|*[!0-9]*) echo 'ERR expected one camera process'; exit 1;; esac
    $B mkdir -p "$STATE" || exit 1
    [ -x /usr/bin/setsid ] || { echo 'ERR setsid is missing';exit 1; }
    /usr/bin/setsid "$BIN" watch "$camera" "$seconds" > "$LOG" 2>&1 < /dev/null 9>&- &
    p=$!;printf '%s\n' "$p" > "$PIDFILE"
    printf '%s\n' "$seconds" > "$DURATION"
    i=0
    while [ "$i" -lt 20 ]; do
        if $B grep -q '^READY ' "$LOG" && alive; then
            if [ "$seconds" = 0 ]; then echo 'OK video LUT follows LUT apply/off';else echo "OK video LUT on (expires in $seconds seconds)";fi
            exit 0
        fi
        if ! kill -0 "$p" 2>/dev/null; then cat "$LOG";exit 1;fi
        i=$((i+1));sleep 0.1
    done
    echo 'ERR watcher did not become ready';kill -TERM "$p" 2>/dev/null;exit 1
    ;;
off|stop)
    control_lock || exit 1
    stop_running || exit 1
    $B rm -f "$PIDFILE" "$DURATION"
    echo 'OK video LUT off';;
status)
    if alive; then echo "VIDEO on (pid=$p)";else echo 'VIDEO off';fi;;
*) echo 'usage: lut_video.sh on [0..3600 seconds]|off|status';exit 2;;
esac
