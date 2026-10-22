#!/bin/bash
# drill_autostart.sh —— 自启等价演练（不改 init.sh，只把它里面的 dropbear 段原样跑一次）
#
# 目的：证明「机端 init.sh 末段」这段**真实字节**能在没有遗留进程的环境下把 dropbear 拉起来，
#       且 nice=0、端口 22 在听。真机重启无法远程完成，这是最接近的等价验证。
#
# 注意：本脚本会杀掉当前所有 dropbear（含自己这条 ssh 会话），必须 setsid 分离运行：
#       /opt/usr/nx-ks/busybox setsid /tmp/drill_autostart.sh &
#       结果写 /tmp/drill.log，稍后重新连上来看。

LOG=/tmp/drill.log
BB=/opt/usr/nx-ks/busybox
SRC=/opt/usr/nx-ks/init.sh

: > "$LOG"
echo "== drill start $(date) ==" >> "$LOG"
echo "src md5: $(md5sum "$SRC" | cut -d' ' -f1)" >> "$LOG"

# 1) 抽出「# ---- dropbear ssh」到文件末尾的整段，字节级原样
sed -n '/---- dropbear ssh/,$p' "$SRC" > /tmp/block.sh
echo "block bytes: $(wc -c < /tmp/block.sh)" >> "$LOG"
echo "block head: $(head -1 /tmp/block.sh)" >> "$LOG"

# 2) 清空遗留进程（pidof 守卫要求为空，否则它会跳过启动）
for p in $($BB pidof dropbear 2>/dev/null); do kill "$p" 2>/dev/null; done
i=0
while [ -n "$($BB pidof dropbear 2>/dev/null)" ] && [ $i -lt 10 ]; do
	sleep 1
	i=$((i + 1))
done
echo "after kill: [$(  $BB pidof dropbear 2>/dev/null)] (waited ${i}s)" >> "$LOG"

# 3) 原样执行该段
. /tmp/block.sh >> "$LOG" 2>&1
sleep 3

# 4) 判据
PID=$($BB pidof dropbear 2>/dev/null | head -1)
echo "new pid: [${PID}]" >> "$LOG"
if [ -n "$PID" ]; then
	echo "nice: $(awk '{print $19}' /proc/"$PID"/stat 2>/dev/null)" >> "$LOG"
	echo "ppid: $(awk '{print $4}' /proc/"$PID"/stat 2>/dev/null)" >> "$LOG"
fi
echo "listen: $($BB netstat -ltn 2>/dev/null | grep ':22 ')" >> "$LOG"
echo "db.log tail:" >> "$LOG"
$BB tail -3 /tmp/db.log >> "$LOG" 2>&1
if [ -n "$PID" ]; then
	echo "RESULT: PASS" >> "$LOG"
else
	echo "RESULT: FAIL" >> "$LOG"
fi
echo "== drill end $(date) ==" >> "$LOG"
