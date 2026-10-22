#!/bin/sh
# run.sh —— 以 nice=0 启动 dropbear
#
# ★ 为什么需要这一层（2026-10-23 实测）：
#   Tizen 把 telnetd 及其 shell 设成 nice=19（busybox nice 不带参数打印出来就是 19），
#   dropbear 从 telnet shell 启动会继承 19；而 di-camera-app 是 nice=-10。
#   单核 A9 常态饱和（load 2.5）时，优先级差 29 级 ⇒ dropbear 只能拿到约 13% CPU，
#   传输被压在 800KB/s 上下，把 -O2 省下来的指令数完全吃掉。
#
# 用 renice 设「绝对值」而不是 nice -n（相对值）：
#   - 从 telnet(19) 启动时，nice -n -19 恰好等于 0
#   - 但从 init.sh 启动时父进程 nice 是 0，nice -n -19 会变成 -19（最高优先级）⇒ 会抢爆相机主业务
#   renice 0 无论继承什么都是 0，是安全的。
BB=/opt/usr/nx-ks/busybox
D=/opt/usr/nx-ks/dropbear

$BB renice 0 -p $$ >/dev/null 2>&1
exec "$D/dropbear" "$@"
