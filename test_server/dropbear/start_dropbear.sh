#!/bin/sh
# start_dropbear.sh —— 启动 dropbear（先挂 2222 验证，避免与 Tizen 可能占用的 22 冲突）
#   -B  允许空密码登录（相机 root 无密码，/etc/passwd 里是 root::0:0）
#   -F  前台（配合 busybox setsid 脱离 telnet 会话，否则 telnet 断开收 SIGHUP 被杀）
#   注意：本构建 --disable-syslog，日志只能走 stderr，因此没有 -E 这个开关（默认就是 stderr）
D=/opt/usr/nx-ks/dropbear
BB=/opt/usr/nx-ks/busybox
LOG=/tmp/db.log
PORT=${1:-2222}

old=$($BB pidof dropbear 2>/dev/null)
[ -n "$old" ] && { kill $old 2>/dev/null; sleep 1; }

rm -f "$LOG"
$BB setsid "$D/dropbear" -F -B -p "$PORT" \
    -r "$D/dropbear_ed25519_host_key" >"$LOG" 2>&1 </dev/null &
sleep 2

echo "--- db.log ---"
cat "$LOG" 2>/dev/null
echo "--- pid ---"
$BB pidof dropbear 2>/dev/null || echo "(no process!)"
echo "--- listen :$PORT ---"
$BB netstat -ltn 2>/dev/null | grep ":$PORT "
