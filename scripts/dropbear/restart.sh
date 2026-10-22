#!/bin/sh
# restart.sh —— 重启 dropbear（换二进制 / 换端口后调用）
#   用法: sh /opt/usr/nx-ks/dropbear/restart.sh [端口，默认 22]
#   经 run.sh 启动，把继承自 telnet 的 nice=19 拉回 0（见 run.sh 注释）
BB=/opt/usr/nx-ks/busybox
D=/opt/usr/nx-ks/dropbear
PORT=${1:-22}

for p in $($BB pidof dropbear 2>/dev/null); do kill "$p" 2>/dev/null; done
sleep 1

chmod +x "$D/dropbear" "$D/dropbearkey" "$D/sftp-server" "$D/run.sh" 2>/dev/null
$BB setsid "$D/run.sh" -F -B -p "$PORT" \
	-r "$D/dropbear_ed25519_host_key" >>/tmp/db.log 2>&1 </dev/null &
sleep 2

pid=$($BB pidof dropbear 2>/dev/null | head -1)
echo "pid: $pid"
[ -n "$pid" ] && echo "nice: $(awk '{print $19}' /proc/$pid/stat 2>/dev/null)"
$BB netstat -ltn 2>/dev/null | grep ":$PORT "
echo "--- tail db.log ---"
$BB tail -3 /tmp/db.log 2>/dev/null
