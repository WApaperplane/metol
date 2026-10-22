#!/bin/sh
# test_autostart.sh —— 验证 init.sh 里 dropbear 段落能否把服务拉起来
# 做法：先杀掉现有实例，再原样执行 init.sh 的那一段（不重跑 keyscan / 环境变量）
BB=/opt/usr/nx-ks/busybox

old=$($BB pidof dropbear 2>/dev/null)
echo "== kill old [$old] =="
[ -n "$old" ] && { kill $old 2>/dev/null; sleep 1; }
rm -f /tmp/db.log

# ===== 以下与 init.sh 中 dropbear 段逐字相同 =====
DB=/opt/usr/nx-ks/dropbear
if [ -f "$DB/dropbear" ]; then
	chmod +x "$DB/dropbear" "$DB/dropbearkey" 2>/dev/null
	if [ ! -f "$DB/dropbear_ed25519_host_key" ]; then
		"$DB/dropbearkey" -t ed25519 -f "$DB/dropbear_ed25519_host_key" >/dev/null 2>&1
	fi
	if [ -f "$DB/authorized_keys" ]; then
		mkdir -p /root/.ssh 2>/dev/null
		cp -f "$DB/authorized_keys" /root/.ssh/authorized_keys 2>/dev/null
		chmod 700 /root/.ssh 2>/dev/null
		chmod 600 /root/.ssh/authorized_keys 2>/dev/null
	fi
	if [ -z "$($BB pidof dropbear 2>/dev/null)" ]; then
		$BB setsid "$DB/dropbear" -F -B -p 22 \
			-r "$DB/dropbear_ed25519_host_key" >>/tmp/db.log 2>&1 </dev/null &
	fi
fi
# ===== 段落结束 =====

sleep 2
echo "== new pid =="
$BB pidof dropbear 2>/dev/null || echo "(FAILED)"
echo "== log =="
cat /tmp/db.log 2>/dev/null
echo "== listen =="
$BB netstat -ltn 2>/dev/null | grep ":22 "
echo "== authkeys =="
ls -l /root/.ssh/authorized_keys 2>/dev/null
