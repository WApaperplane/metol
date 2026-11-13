#!/bin/sh
# nxstore.sh — NXWA 模组统一存储层（被 source，不单独执行）
#=====================================================================
# 起因：2026-11-11 a18_orig.bin 变成 0 字节，导致「还原原厂」永久失败。
# 查下去发现 state 目录里堆了 556 个 order-N 副本 —— chkdsk 把同一批
# 同名目录项批量改名的结果。exFAT 不回收旧目录项、删除也不做簇引用计数，
# 而模组里每个脚本都在用 `mv -f .tmp 目标` 覆盖状态文件 —— 2026-11-14 的
# 机上对照实验坐实了：原地重写不泄漏，**覆盖式 rename 每次留一个旧目录项**。
# 换卡治不了，systemd 也管不到文件系统。
#
# 这一层把规则固定下来：
#   1. 重启就该忘的东西 → /tmp（tmpfs），一个字节都不碰 SD
#   2. 必须跨开机的 → 才落 SD，且只走 nx_put（tmp → sync → 校验 → rm+mv）
#   3. 内容没变就不写（nx_put_str 先比对）—— 这是砍写入量的主力
#   4. 日志是往一个文件追加，不是每次新建同名文件
#   5. NX_TRACE=1 时每次 SD 写都打到 stderr，谁在写卡一查便知
#
# 用法（脚本顶部）：
#   . /opt/usr/nx-ks/nxstore.sh
#   ST=$(nx_ram filmlab)/cur.idx        # 易失状态
#   nx_put /tmp/x.bin /mnt/mmc/x.bin    # 持久文件，原子替换
#   nx_put_str "$v" /mnt/mmc/x.idx      # 持久小值，相同则跳过
#   nx_log lut "applied $name"
#=====================================================================

case "$0" in
    */nxstore.sh|nxstore.sh) echo "nxstore.sh 是被 source 的库，不单独执行" >&2; exit 2 ;;
esac

[ -n "${NXSTORE_LOADED:-}" ] && return 0
NXSTORE_LOADED=1

NX_RAM=${NX_RAM:-/tmp/nx}
NX_SD=${NX_SD:-/mnt/mmc}
NX_BB=${NX_BB:-/opt/usr/nx-ks/busybox}
[ -x "$NX_BB" ] || NX_BB=/bin/busybox
NX_LOG_MAX=${NX_LOG_MAX:-65536}

_nx_mkdir() { [ -d "$1" ] || $NX_BB mkdir -p "$1" 2>/dev/null; }
# 取目录名：没有斜杠的相对路径返回 "."，不能把文件名当目录去 mkdir
_nx_dirname() { case "$1" in */*) printf '%s' "${1%/*}";; *) printf '.';; esac; }
_nx_size()  {
    if [ -f "$1" ]; then
        _nx_s=$($NX_BB wc -c < "$1" 2>/dev/null | $NX_BB tr -d ' ')
        printf '%s' "${_nx_s:-0}"
    else
        printf '0'
    fi
}

# ---- 路径 -----------------------------------------------------------
# 易失：tmpfs，重启即清。状态、还原点、日志、临时表全放这里。
nx_ram() {
    _nx_d=$NX_RAM/${1:-state}
    _nx_mkdir "$_nx_d"
    printf '%s\n' "$_nx_d"
}

# 持久：SD。只给真正要跨开机的东西用（库、配置、用户资产）。
nx_sd() {
    _nx_d=$NX_SD/${1:-}
    _nx_mkdir "$_nx_d"
    printf '%s\n' "${_nx_d%/}"
}

# ---- 覆盖写入：必须先删目标，再 rename -------------------------------
# ★ 2026-11-14 机上对照实验（/mnt/mmc/_xfer/sdtest.sh，每种写法各跑 10 次）：
#     原地 `>` 重写            → 目录里 1 个同名项（不泄漏）
#     `mv -f tmp 目标`（覆盖） → 目录里 11 个同名项（每次写 +1）
#     `rm 目标; mv tmp 目标`   → 目录里 1 个同名项（不泄漏）
#   结论：这张 exFAT 的 rename 不是原子替换 —— 目标已存在时旧目录项原样留着。
#   所以「原子替换」这个动作必须以 rm 打头。state 目录里那 556 个 order-N
#   不是「高频重写」造成的，是「高频 mv -f 覆盖」造成的（每次开面板 +1）。
nx_swap() {
    _nx_src=${1:-}; _nx_dst=${2:-}
    [ -n "$_nx_src" ] && [ -n "$_nx_dst" ] || return 1
    [ -f "$_nx_src" ] || return 1
    _nx_mkdir "$(_nx_dirname "$_nx_dst")"
    $NX_BB rm -f "$_nx_dst" 2>/dev/null
    if ! $NX_BB mv -f "$_nx_src" "$_nx_dst" 2>/dev/null; then
        # 目标刚被删、改名又失败 —— 至少把内容拷回去，不留空档
        $NX_BB cp -f "$_nx_src" "$_nx_dst" 2>/dev/null
        $NX_BB rm -f "$_nx_src" 2>/dev/null
        return 1
    fi
    return 0
}

# ---- 持久写：原子 + 校验 -------------------------------------------
# 先写同目录 .tmp，确认字节数一致、sync 落盘后再顶替。
# 任何一步失败都保留原文件、清掉 .tmp —— 绝不会出现"目标被清空但没写进去"。
nx_put() {
    _nx_src=${1:-}; _nx_dst=${2:-}
    [ -n "$_nx_src" ] && [ -n "$_nx_dst" ] || return 1
    [ -f "$_nx_src" ] || return 1
    _nx_mkdir "$(_nx_dirname "$_nx_dst")"
    _nx_tmp="$_nx_dst.tmp"
    $NX_BB cp -f "$_nx_src" "$_nx_tmp" 2>/dev/null || return 1
    _nx_a=$(_nx_size "$_nx_src")
    _nx_b=$(_nx_size "$_nx_tmp")
    if [ "$_nx_a" = 0 ] || [ "$_nx_a" != "$_nx_b" ]; then
        $NX_BB rm -f "$_nx_tmp" 2>/dev/null
        return 1
    fi
    $NX_BB sync 2>/dev/null
    nx_swap "$_nx_tmp" "$_nx_dst" || return 1
    [ "${NX_TRACE:-0}" = 1 ] && echo "NXPUT $_nx_dst ($_nx_a B)" >&2
    return 0
}

# 小值持久写：内容一样就当成功返回，不产生任何写入。
nx_put_str() {
    _nx_v=${1:-}; _nx_dst=${2:-}
    [ -n "$_nx_dst" ] || return 1
    if [ -f "$_nx_dst" ]; then
        _nx_old=$(cat "$_nx_dst" 2>/dev/null)
        [ "$_nx_old" = "$_nx_v" ] && return 0
    fi
    _nx_mkdir "$(_nx_dirname "$_nx_dst")"
    printf '%s\n' "$_nx_v" > "$_nx_dst.tmp" 2>/dev/null || return 1
    $NX_BB sync 2>/dev/null
    nx_swap "$_nx_dst.tmp" "$_nx_dst" || return 1
    [ "${NX_TRACE:-0}" = 1 ] && echo "NXPUT $_nx_dst = $_nx_v" >&2
    return 0
}

# 读持久小值，不存在返回默认值
nx_get_str() {
    _nx_d=${2:-}
    if [ -n "$_nx_d" ] && [ -f "$_nx_d" ]; then _nx_o=$(cat "$_nx_d" 2>/dev/null); printf '%s\n' "$_nx_o"; else printf '%s\n' "${1:-}"; fi
}

# ---- 日志：单文件追加 -----------------------------------------------
# 不用 `> xxx.log`：同名文件被反复重写正是 exFAT 重复目录项的来源。
nx_log() {
    if [ $# -ge 2 ]; then _nx_ch=$1; shift; else _nx_ch=main; fi
    _nx_dir=$NX_RAM/log
    _nx_mkdir "$_nx_dir"
    _nx_f="$_nx_dir/$_nx_ch.log"
    _nx_sz=$(_nx_size "$_nx_f")
    if [ "$_nx_sz" -gt "$NX_LOG_MAX" ]; then
        $NX_BB tail -c $((NX_LOG_MAX / 2)) "$_nx_f" > "$_nx_f.t" 2>/dev/null \
            && nx_swap "$_nx_f.t" "$_nx_f"
    fi
    printf '%s %s\n' "$(date '+%m-%d %H:%M:%S' 2>/dev/null)" "$*" >> "$_nx_f" 2>/dev/null
}

# 失败时把日志落到 SD，供拔卡取证。成功路径永远不调用它。
nx_log_persist() {
    _nx_ch=${1:-main}
    _nx_src="$NX_RAM/log/$_nx_ch.log"
    [ -f "$_nx_src" ] || return 1
    _nx_mkdir "$NX_SD/nx-failure"
    nx_put "$_nx_src" "$NX_SD/nx-failure/$_nx_ch.log"
}

nx_log_tail() { $NX_BB tail -n "${2:-5}" "$NX_RAM/log/${1:-main}.log" 2>/dev/null; }

# ---- 易失状态 -------------------------------------------------------
nx_st_get() {
    _nx_k=${1:-}
    [ -n "$_nx_k" ] || return 1
    _nx_f=$NX_RAM/state/$_nx_k
    if [ -f "$_nx_f" ]; then cat "$_nx_f" 2>/dev/null; else printf '%s\n' "${2:-}"; fi
}

nx_st_set() {
    _nx_k=${1:-}
    [ -n "$_nx_k" ] || return 1
    _nx_mkdir "$NX_RAM/state"
    printf '%s\n' "${2:-}" > "$NX_RAM/state/$_nx_k" 2>/dev/null
}

# ---- 自查 -----------------------------------------------------------
# 打印当前划分和占用；NX_TRACE=1 可配合看实时写入来源。
nx_report() {
    _r=$($NX_BB du -sk "$NX_RAM" 2>/dev/null | $NX_BB awk '{print $1}')
    _p=$($NX_BB du -sk "$NX_SD/lut/state" 2>/dev/null | $NX_BB awk '{print $1}')
    echo "RAM  $NX_RAM  ${_r:-0} KB  (volatile, cleared on reboot)"
    echo "SD   $NX_SD/lut/state  ${_p:-0} KB  (persistent)"
    _n=$(ls "$NX_RAM/log" 2>/dev/null | $NX_BB wc -l | $NX_BB tr -d ' ')
    echo "LOGS ${_n:-0} channel(s) in $NX_RAM/log"
}
