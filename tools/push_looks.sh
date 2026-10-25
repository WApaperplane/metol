#!/bin/bash
# push_looks.sh —— 把本地 LUT 批次推到相机 /mnt/mmc/looks，带备份与全量校验
#
# 用法:
#   tools/push_looks.sh                       # 默认推 E:/NXWA/_pushstage/looks
#   tools/push_looks.sh <本地目录> [远端目录]
#   tools/push_looks.sh --check               # 只做连通性 + 机端现状，不写任何东西
#
# 纪律（踩过的坑）：
#   · 相机休眠时 ping 可能通 33%，但 21/22/23 全 CLOSED —— 必须按快门唤醒
#   · 推完要 sync + sleep 2 再点数，SD 目录项有延迟
#   · 必须全量 md5 核对，不能只看文件数
#   · 旧文件要先删，tar 解包只覆盖不清理，旧表会残留成"幽灵条目"
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(dirname "$HERE")
KEY=${NX_SSH_KEY:-$ROOT/test_server/dropbear/ssh/nx500_ed25519}
HOST=${NXHOST:-192.168.0.106}
PORT=${NX_SSH_PORT:-22}
BB=/opt/usr/nx-ks/busybox

SSH=(ssh -p "$PORT" -i "$KEY" -o IdentitiesOnly=yes
     -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null
     -o ConnectTimeout=8 -o LogLevel=ERROR "root@$HOST")

rc() { "${SSH[@]}" "$@" 2>&1; }

# ---------- 连通性 ----------
echo "[0] 连通性 $HOST:$PORT"
if ! rc 'echo PING_OK' | grep -q PING_OK; then
    echo "  ✗ ssh 不可达。相机很可能在休眠（特征：ping 少量通、21/22/23 全 CLOSED）。"
    echo "    请按一次快门唤醒，等 5 秒后重跑本脚本。"
    exit 1
fi
echo "  ✓ ssh 通"

SRC=${1:-E:/NXWA/_pushstage/looks}
DST=${2:-/mnt/mmc/looks}

if [ "${1:-}" = "--check" ]; then
    echo "[check] 机端 $DST"
    rc "ls $DST/*.bin 2>/dev/null | wc -l; du -sh $DST 2>/dev/null; \
        df -h /mnt/mmc | tail -1"
    exit 0
fi

if [ ! -d "$SRC" ]; then echo "本地目录不存在：$SRC"; exit 1; fi
N_LOCAL=$(ls "$SRC"/*.bin 2>/dev/null | wc -l)
echo "[1] 本地 $SRC：$N_LOCAL 张"

# ---------- 备份 ----------
BAK="${DST}_bak_$(date +%Y%m%d_%H%M)"
echo "[2] 备份机端 → $BAK"
rc "if [ -d $DST ]; then cp -r $DST $BAK && echo BAK_OK; else echo NO_DST; fi" | sed 's/^/  /'

# ---------- 清理 ----------
echo "[3] 清理旧 *.bin"
rc "$BB sh -c 'rm -f $DST/*.bin; ls $DST/*.bin 2>/dev/null | wc -l'" | sed 's/^/  剩余 /'

# ---------- 推送 ----------
echo "[4] 推送"
tar cf - -C "$(dirname "$SRC")" "$(basename "$SRC")" \
    | "${SSH[@]}" "mkdir -p '$DST' && $BB tar xf - -C '$(dirname "$DST")' && echo PUSH_OK" 2>&1 \
    | sed 's/^/  /'

# ---------- sync 后点数 ----------
echo "[5] sync + 等 SD 落盘"
rc 'sync; sleep 2; echo SYNCED' | sed 's/^/  /'
N_REMOTE=$(rc "ls $DST/*.bin 2>/dev/null | wc -l" | tr -d ' \r')
echo "  机端 $N_REMOTE 张（本地 $N_LOCAL）"

# ---------- 全量 md5 ----------
echo "[6] 全量 md5 核对"
L_SUM=$(cd "$SRC" && cat $(ls *.bin | sort) | md5sum | cut -d' ' -f1)
R_SUM=$(rc "cd $DST && cat \$(ls *.bin | sort) | $BB md5sum" | cut -d' ' -f1)
echo "  本地 $L_SUM"
echo "  机端 $R_SUM"

if [ "$N_REMOTE" != "$N_LOCAL" ]; then
    echo "  ✗ 数量不符，中止（旧文件可能没删干净）"; exit 2
fi
if [ "$L_SUM" != "$R_SUM" ]; then
    echo "  ✗ md5 不符，传输损坏"; exit 3
fi
echo "  ✓ $N_LOCAL 张全量一致"
echo ""
echo "机端生效方式：NXUI「LUT 滤镜」里选一张；apply 后需半按一次快门才进 SRAM（reload 是禁区）。"
