#!/bin/bash
# nx-ssh.sh —— 通过 dropbear ssh 操作 NX 相机（加密替代 telnet）
#
# 用法:
#   ./nx-ssh.sh                 # 交互 shell
#   ./nx-ssh.sh cmd '<命令>'     # 执行命令
#   ./nx-ssh.sh push <本地路径> [远端目录]   # 目录/文件 → 相机
#   ./nx-ssh.sh pull <远端路径> [本地目录]   # 相机 → 本地
#   ./nx-ssh.sh tunnel [本地端口] [目标]      # 端口转发，默认 8080 → 127.0.0.1:80（相机 web UI）
#   ./nx-ssh.sh info            # 连通性 + 版本 + 端口自检
#
# 环境变量: NXHOST(默认 192.168.0.106) NX_SSH_PORT(22) NX_SSH_KEY
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(dirname "$HERE")
KEY=${NX_SSH_KEY:-$ROOT/test_server/dropbear/ssh/nx500_ed25519}
HOST=${NXHOST:-192.168.0.106}
PORT=${NX_SSH_PORT:-22}
BB=/opt/usr/nx-ks/busybox

if [ ! -f "$KEY" ]; then
    echo "私钥不存在: $KEY" >&2
    exit 1
fi

SSH=(ssh -p "$PORT" -i "$KEY" -o IdentitiesOnly=yes
     -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null
     -o ConnectTimeout=10 -o LogLevel=ERROR "root@$HOST")

case "${1:-shell}" in
shell)
    exec "${SSH[@]}"
    ;;
cmd)
    shift
    "${SSH[@]}" "$@"
    ;;
push)
    src=${2:?需要本地路径}
    dst=${3:-/opt/usr/nx-ks/}
    tar cf - -C "$(dirname "$src")" "$(basename "$src")" \
        | "${SSH[@]}" "mkdir -p '$dst' && $BB tar xf - -C '$dst' && echo PUSH_OK"
    ;;
pull)
    src=${2:?需要远端路径}
    dst=${3:-.}
    mkdir -p "$dst"
    "${SSH[@]}" "cd '$(dirname "$src")' && $BB tar cf - '$(basename "$src")'" \
        | tar xf - -C "$dst" && echo PULL_OK
    ;;
tunnel)
    # 相机 80 端口是 Tizen web UI（「NX 远程控制器」），8080 无服务。
    # 用 -L 搬到本机：浏览器/手机访问 localhost:<本地端口> 即可，不用记相机 IP。
    lport=${2:-8080}
    target=${3:-127.0.0.1:80}
    echo "本机 127.0.0.1:$lport  ->  相机 $target    (Ctrl-C 断开)"
    exec "${SSH[@]}" -N -L "$lport:$target"
    ;;
info)
    # pid 取最小者 = 守护进程（pidof 会把每个在线会话的子进程也列出来）
    # nice 直接打出来：19 就说明有人绕开 run.sh 起了 dropbear，速率会腰斩
    "${SSH[@]}" "B=/opt/usr/nx-ks/busybox; ALL=\$(\$B pidof dropbear); \
P=\$(echo \$ALL | tr ' ' '\n' | sort -n | head -1); \
echo host=\$(hostname) kernel=\$(uname -r); \
echo sshd=\$(/opt/usr/nx-ks/dropbear/dropbear -V 2>&1 | head -1); \
echo \"pid=\$P (daemon) sessions=\$((\$(echo \$ALL | wc -w) - 1)) nice=\$(awk '{print \$19}' /proc/\$P/stat)\"; \
\$B netstat -ltn | grep ':$PORT '; \
echo uptime=\$(cut -d' ' -f1 /proc/uptime)s"
    ;;
*)
    sed -n '2,14p' "$0"
    exit 2
    ;;
esac
