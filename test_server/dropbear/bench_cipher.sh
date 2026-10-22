#!/bin/bash
# bench_cipher.sh —— 横向对比 SSH cipher 的实测吞吐（相机 → 本机）
#
# 用法: ./bench_cipher.sh [文件大小MB] [重复次数]
# 说明: 先造一份不可压缩的随机文件推到相机，再按不同 cipher 反复拉取到 /dev/null。
#       压缩已在编译期关闭，故测到的纯是「加密 + 协议 + 网络」成本。
#       相机是单核 A9 且常态饱和，瓶颈在 CPU ⇒ cipher 选择对速率影响明显。
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(dirname "$(dirname "$HERE")")
KEY=${NX_SSH_KEY:-$ROOT/test_server/dropbear/ssh/nx500_ed25519}
HOST=${NXHOST:-192.168.0.106}
PORT=${NX_SSH_PORT:-22}
SIZE=${1:-4}
REPS=${2:-3}
REMOTE=/opt/usr/nx-ks/bench.bin
BB=/opt/usr/nx-ks/busybox

SSH=(ssh -p "$PORT" -i "$KEY" -o IdentitiesOnly=yes
     -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null
     -o ConnectTimeout=10 -o LogLevel=ERROR "root@$HOST")

# 1) 造数据（本地随机，一次性推送）
if ! "${SSH[@]}" "[ -f $REMOTE ] && [ \$($BB stat -c %s $REMOTE) -eq $((SIZE*1024*1024)) ]" 2>/dev/null; then
    echo "== 造 ${SIZE}MB 测试文件并推送 =="
    TMP=$(mktemp -d)
    head -c $((SIZE*1024*1024)) /dev/urandom > "$TMP/bench.bin"
    tar cf - -C "$TMP" bench.bin | "${SSH[@]}" "$BB tar xf - -C /opt/usr/nx-ks/ && sync"
    rm -rf "$TMP"
fi

now_ms() { date +%s%3N; }

printf '%-34s %8s %8s %8s\n' cipher run1 run2 run3
echo "---------------------------------------------------------------"
for C in chacha20-poly1305@openssh.com aes128-ctr aes256-ctr; do
    line=""
    ok=1
    for i in $(seq 1 "$REPS"); do
        t0=$(now_ms)
        if ! "${SSH[@]}" -c "$C" "cat $REMOTE" > /dev/null 2>/dev/null; then ok=0; break; fi
        t1=$(now_ms)
        ms=$((t1 - t0))
        # MB/s = SIZE*1000/ms
        line="$line $(awk -v s="$SIZE" -v m="$ms" 'BEGIN{printf "%7.2f", s*1000/m}')"
    done
    if [ "$ok" = 1 ]; then
        printf '%-34s%s MB/s\n' "$C" "$line"
    else
        printf '%-34s  (不支持/失败)\n' "$C"
    fi
done
