#!/bin/sh
# @gate script=nxfsck.sh opens=r one_shot=1 gate=none pconly=0
#=====================================================================
# nxfsck.sh — SD 目录健康巡检（只读，不删任何东西）
#=====================================================================
# 查三件事：
#   1. 重复目录项残骸：同时存在 X 和 X-N 就是 chkdsk 干过活的证据
#   2. 孤儿 .tmp：nxstore 的原子写残留，说明有进程死在 rename 之前
#   3. 目录文件数与分区余量
#
# 为什么要查：exFAT 不回收旧目录项、删除也不做簇引用计数，同名小文件被
# 反复 truncate+重写就会堆悬空项。堆到一定程度，open 成功但数据落到空闲簇，
# 读回来就是 0 字节 —— 2026-11-11 的 a18_orig.bin 事故就是这么来的。
#
# 用法：
#   sh nxfsck.sh                 # 查 /mnt/mmc
#   sh nxfsck.sh /path/to/sd     # 指定根
#=====================================================================
set -u

BB=/opt/usr/nx-ks/busybox
[ -x "$BB" ] || BB=
SD=${1:-/mnt/mmc}

warn=0
ok()   { echo "PASS  $*"; }
bad()  { echo "WARN  $*"; warn=$((warn + 1)); }
info() { echo "INFO  $*"; }

# 同时存在 X 与 X-N，则 X-N 是 chkdsk 改名的产物
scan_dups() {
    _d=$1
    [ -d "$_d" ] || return 0
    _n=0; _nf=0
    for _f in "$_d"/* "$_d"/.[!.]* ; do
        [ -e "$_f" ] || continue
        _nf=$((_nf + 1))
        case "${_f##*/}" in
            *-[0-9]*) _base=${_f%-*}
                      [ -e "$_base" ] && { _n=$((_n + 1)); } ;;
        esac
    done
    if [ "$_n" -gt 0 ]; then
        bad "${_d#$SD/}：$_n 个 name-N 副本 / 共 $_nf 项 —— 目录项已被反复改写"
        echo "        清理：整目录改名重建，别逐条 rm（exFAT 删一条就释放簇链）"
    elif [ "$_nf" -gt 40 ]; then
        bad "${_d#$SD/}：$_nf 项，偏多（正常应 < 20）"
    else
        ok "${_d#$SD/}：$_nf 项，无副本"
    fi
}

# 孤儿 .tmp（超过 1 小时没动）
scan_tmp() {
    _d=$1
    [ -d "$_d" ] || return 0
    _c=$($BB find "$_d" -maxdepth 1 -name '*.tmp' -mmin +60 2>/dev/null | $BB wc -l | $BB tr -d ' ')
    [ "${_c:-0}" -gt 0 ] && bad "${_d#$SD}：$_c 个孤儿 .tmp（原子写没走完就断了）"
    return 0
}

echo "SD 根: $SD"
echo
echo "=== 目录健康 ==="
for sub in lut/state lut/cv filmlab nxui nx-ks scripts/sd; do
    scan_dups "$SD/$sub"
    scan_tmp  "$SD/$sub"
done

echo
echo "=== 分区 ==="
$BB df -k "$SD" 2>/dev/null | $BB tail -n 2

echo
echo "=== 易失区（应该是空的或很小，重启会清） ==="
for d in /tmp/nx/lut /tmp/nx/filmlab /tmp/nx/nxui; do
    [ -d "$d" ] && info "$d  $($BB du -sk "$d" 2>/dev/null | $BB awk '{print $1}') KB"
done

echo
if [ "$warn" -eq 0 ]; then
    echo "VERDICT 目录干净"
else
    echo "VERDICT $warn 处需要处理，见上面 WARN"
fi
