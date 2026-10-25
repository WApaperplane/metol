#!/bin/bash
# nx-looks-sync.sh —— 本地 looks/ 与机端 LUT 库的一致性核查 / 修复
#
# 用法:
#   ./nx-looks-sync.sh check          # 只读：数量 + 全量 md5 比对（默认命令）
#   ./nx-looks-sync.sh fix            # 只修「同名但内容不符」，绝不补「缺失」
#   ./nx-looks-sync.sh fix --add      # 额外把缺失的也补推（仅在你确认是丢文件时用）
#
# ★ 机端比本地少，默认视为**用户主动删减**，不自动补推。
#   2026-10-25 踩过：把用户手工下架的 41 张当成 exfat 丢文件补了回去。
#   缺失清单只报告，不动手。
#
# 环境变量:
#   NXHOST        相机 IP（默认 192.168.0.106）
#   NX_REMOTE_DIR 机端 LUT 目录（默认 /mnt/mmc/looks，即 lut.sh 里的 LAB）
#   NX_SSH_PORT / NX_SSH_KEY  透传给 nx-ssh.sh
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(dirname "$HERE")
LOCAL_DIR=${NX_LOCAL_DIR:-$ROOT/looks}
REMOTE_DIR=${NX_REMOTE_DIR:-/mnt/mmc/looks}
HOST=${NXHOST:-192.168.0.106}
SSH_SH=$HERE/nx-ssh.sh
BB=/opt/usr/nx-ks/busybox
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

die() { echo "ERROR: $*" >&2; exit 1; }
[ -d "$LOCAL_DIR" ] || die "本地目录不存在: $LOCAL_DIR"
[ -f "$SSH_SH" ] || die "缺少 $SSH_SH"

ssh_cmd() { NXHOST=$HOST bash "$SSH_SH" cmd "$@"; }

# 本地 md5：Git Bash 的 md5sum 会在文件名前加 '*'（文本模式标记），统一剥掉
local_md5() {
    ( cd "$LOCAL_DIR" && md5sum -- *.bin 2>/dev/null | awk '{f=$2; sub(/^\*/,"",f); print $1" "f}' | sort -k2 )
}

remote_md5() {
    ssh_cmd "cd '$REMOTE_DIR' 2>/dev/null || { echo NO_DIR; exit 0; }; \
             for f in *.bin; do [ -f \"\$f\" ] && $BB md5sum \"\$f\"; done; \
             echo '---DF---'; df -k '$REMOTE_DIR' | $BB tail -1" 2>/dev/null
}

report() {
    # $1=本地清单 $2=机端清单
    python_from_files "$1" "$2"
}

python_from_files() {
    local lf=$1 rf=$2
    local py
    for c in python python3 py; do command -v "$c" >/dev/null 2>&1 && { py=$c; break; }; done
    if [ -z "${py:-}" ]; then
        # 无 python 时退化为 diff
        echo "[warn] 未找到 python，退化为纯文本 diff"
        diff <(sort -k2 "$lf") <(sort -k2 "$rf") || true
        return
    fi
    "$py" - "$lf" "$rf" <<'PY'
import sys
def load(p):
    d={}
    for line in open(p, encoding='utf-8', errors='replace'):
        s=line.strip()
        if not s or s.startswith('---'): continue
        parts=s.split()
        if len(parts)==2 and parts[1].endswith('.bin'):
            d[parts[1]]=parts[0]
    return d
loc=load(sys.argv[1]); rem=load(sys.argv[2])
miss=sorted(set(loc)-set(rem)); extra=sorted(set(rem)-set(loc))
diff=sorted(k for k in set(loc)&set(rem) if loc[k]!=rem[k])
print(f"本地 {len(loc)} 张 | 机端 {len(rem)} 张")
if not (miss or extra or diff):
    print(f"RESULT: SYNC_OK  机端 {len(rem)} 张与本地一致")
else:
    if not diff:
        tag="DIFF_ONLY"
        note="（机端与本地是子集/超集关系，多为有意增删）"
    else:
        tag="SYNC_BAD"
        note=""
    print(f"RESULT: {tag}  缺失 {len(miss)} / 多余 {len(extra)} / 内容不符 {len(diff)} {note}")
    for m in miss: print("  缺失  ", m)
    for e in extra: print("  多余  ", e)
    for d in diff: print("  不符  ", d, f"local={loc[d][:8]} remote={rem[d][:8]}")
PY
}

case "${1:-check}" in
check)
    remote_md5 > "$TMP/rem.txt"
    if grep -q NO_DIR "$TMP/rem.txt"; then die "机端目录不存在: $REMOTE_DIR"; fi
    grep -v -E '^(---DF---|[0-9]+ +[0-9]+$|Filesystem)' "$TMP/rem.txt" > "$TMP/rem_clean.txt"
    echo "=== 机端 $REMOTE_DIR ==="
    grep -A1 'DF---' "$TMP/rem.txt" | tail -1 | awk '{printf "df: %d KB used / %d KB total (%.1f%%)\n",$3,$2,($3*100/$2)}' 2>/dev/null || true
    local_md5 > "$TMP/loc.txt"
    echo "=== 比对 ==="
    report "$TMP/loc.txt" "$TMP/rem_clean.txt"
    ;;
fix)
    ADD=${2:-}
    remote_md5 > "$TMP/rem.txt"
    grep -v -E '^(NO_DIR|---DF---|[0-9]+ +[0-9]+$|Filesystem)' "$TMP/rem.txt" > "$TMP/rem_clean.txt"
    local_md5 > "$TMP/loc.txt"
    echo "=== 推送前状态 ==="
    report "$TMP/loc.txt" "$TMP/rem_clean.txt"
    # 只挑「同名但内容不符」的推；缺失默认不动（可能是用户主动删的）
    if [ "$ADD" = "--add" ]; then
        SEL=$(cut -d' ' -f1 "$TMP/loc.txt")
        echo "包含缺失文件（--add）…"
    else
        SEL=$(python_from_files "$TMP/loc.txt" "$TMP/rem_clean.txt" 2>/dev/null | \
              awk '/^  不符/{print $2}')
        if [ -z "$SEL" ]; then
            echo "没有内容不符的文件，机端缺失部分按「用户主动删减」处理，不补推。"
            echo "（确属丢文件请用: $0 fix --add）"
            exit 0
        fi
        echo "仅重推内容不符的 $(echo "$SEL" | wc -l) 张…"
    fi
    # 用一份临时精选目录推，避免整目录覆盖
    mkdir -p "$TMP/sel"
    for f in $SEL; do [ -f "$LOCAL_DIR/$f" ] && cp "$LOCAL_DIR/$f" "$TMP/sel/"; done
    NXHOST=$HOST bash "$SSH_SH" push "$TMP/sel" "$REMOTE_DIR/" >/dev/null 2>&1 \
        || die "push 失败"
    echo "sync + 落盘验证（drop_caches 后重读）…"
    ssh_cmd "sync; sleep 2; echo 3 > /proc/sys/vm/drop_caches 2>/dev/null; \
             cd '$REMOTE_DIR' && for f in *.bin; do $BB md5sum \"\$f\"; done" > "$TMP/post.txt" 2>/dev/null
    echo "=== 推送后状态 ==="
    report "$TMP/loc.txt" "$TMP/post.txt"
    ;;
*)
    sed -n '2,20p' "$0"; exit 2 ;;
esac
