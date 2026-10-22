#!/bin/bash
# nx-ssh.sh —— 通过 dropbear ssh 操作 NX 相机（加密替代 telnet）
#
# 用法:
#   ./nx-ssh.sh                 # 交互 shell
#   ./nx-ssh.sh cmd '<命令>'     # 执行命令
#   ./nx-ssh.sh push <本地路径> [远端目录]   # 目录/文件 → 相机
#   ./nx-ssh.sh pull <远端路径> [本地目录]   # 相机 → 本地
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
info)
    "${SSH[@]}" "echo host=\$(hostname) kernel=\$(uname -r); \
echo sshd=\$(/opt/usr/nx-ks/dropbear/dropbear -V 2>&1 | head -1); \
echo pid=\$(/opt/usr/nx-ks/busybox pidof dropbear); \
/opt/usr/nx-ks/busybox netstat -ltn | grep ':$PORT '; \
echo uptime=\$(cut -d' ' -f1 /proc/uptime)s"
    ;;
*)
    sed -n '2,14p' "$0"
    exit 2
    ;;
esac
