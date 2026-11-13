#!/bin/sh
# @gate script=lut_doctor.sh opens=r one_shot=1 gate=none pconly=0
#=====================================================================
# lut_doctor.sh — 面板「还原失败 · 详情见日志」的现场取证
#=====================================================================
# 只读：不写相机内存、不改任何状态文件、不动滤镜库。
#
#   sh /opt/usr/nx-ks/lut_doctor.sh          # 或 /mnt/mmc/lut_doctor.sh
#
# 判读：每个 FAIL 都是能单独让 `lut.sh off` 返回非 0 的阻塞项；
#       WARN 是风险项，不必然失败。最后一行的 VERDICT 给结论。
#
# 为什么需要它：off 的失败信息散在四处 ——
#   · 工具缺失/丢执行位     -> need_tools die，日志里只有一行 ERR
#   · lut_video.sh 抢不到锁  -> die 得更早，一个字节都没还原
#   · 三项 restore 任一 rc=1 -> 部分成功，面板只报一句「还原失败」
#   · 面板 30s 超时 SIGKILL  -> 脚本没有机会打印任何东西
# 前两类连 off-*.log 都不会生成，所以必须从外部把证据收齐。
#=====================================================================
set -u

D=/opt/usr/nx-ks
BB=$D/busybox
ST=/tmp/nx/lut                   # 新版：还原点/日志/标志在 tmpfs
PD=/mnt/mmc/lut/state            # 持久区：order / cv，以及失败时的 last-failure
OLD=/mnt/mmc/lut/state           # 旧版布局备份位置（兼容检查）
BAK=/mnt/mmc/nxwa_regtab_20261018
SLOT=0x81119F00
ENGREG=0x2082b00c
SLOT_LEN=19712
# 2026-11-08 恢复出来的原厂 A18 基线（_lut_community_20261108/recovered_factory_a18.bin）
FACTORY_MD5=4c0cc78c

fails=0
pass() { echo "PASS  $*"; }
bad()  { echo "FAIL  $*"; fails=$((fails + 1)); }
warn() { echo "WARN  $*"; }
info() { echo "INFO  $*"; }
md8()  { m=$($BB md5sum "$1" 2>/dev/null); [ -n "${m:-}" ] && echo "$m" | $BB cut -c1-8; }
fsize() { s=$($BB wc -c < "$1" 2>/dev/null | $BB tr -d ' '); echo "${s:-0}"; }

echo "=== 1. tools  (off 的第一道门：缺失或无 +x 直接 die) ==="
for t in nx_slotwrite.arm nx_regtabwrite.arm nx_lutload.arm nx_lutptr.arm; do
    p=
    for d in "$D/lut" /mnt/mmc/lut; do
        if [ -x "$d/$t" ]; then p=$d/$t; break; fi
    done
    if [ -n "$p" ]; then
        # 光看 [ -x ] 不够：PC 上可能放着同名 shell stub（本机真有），会假装工具在。
        # 真工具都是 4KB 以上的静态 ARM 二进制，几百字节的一定是假的。
        _psz=$(fsize "$p")
        if [ "${_psz:-0}" -lt 4000 ]; then
            bad "$t 只有 ${_psz}B，是个 stub 不是真工具: $p"
        else
            pass "$t  ${_psz}B  $p"
        fi
    else
        q=
        for d in "$D/lut" /mnt/mmc/lut; do
            if [ -f "$d/$t" ]; then q=$d/$t; break; fi
        done
        if [ -n "$q" ]; then
            bad "$t 存在但没有执行位: $q  -> chmod +x"
        else
            bad "$t 在 $D/lut 和 /mnt/mmc/lut 都找不到"
        fi
    fi
done

echo
echo "=== 2. 还原点 a18_orig.bin ==="
if [ -f "$ST/a18_orig.bin" ]; then
    sz=$(fsize "$ST/a18_orig.bin")
    m=$(md8 "$ST/a18_orig.bin")
    if [ "$sz" = "$SLOT_LEN" ]; then
        pass "$ST/a18_orig.bin  ${sz}B  md5=$m"
    elif [ "$sz" = 0 ]; then
        bad "tmpfs 上的还原点是 0 字节：本次开机 apply 时备份被打断；off 会改用随包原厂基线写回 A18"
    else
        bad "尺寸=$sz（应为 $SLOT_LEN）"
    fi
    case "${m:-none}" in
        "$FACTORY_MD5") pass "备份内容 = 已知原厂基线" ;;
        *) warn "md5=$m ≠ 已知原厂 $FACTORY_MD5：还原会落到非原厂内容" ;;
    esac
elif [ -f "$OLD/a18_orig.bin" ]; then
    sz=$(fsize "$OLD/a18_orig.bin")
    if [ "$sz" = 0 ]; then
        bad "旧版布局的 $OLD/a18_orig.bin 是 0 字节（新版不再读它，可删）"
    else
        info "只有旧版布局的备份（${sz}B）；新版不读它，可删"
    fi
else
    info "本次开机还没有 apply 过 —— 没有还原点是正常的（A18 此刻就是原厂，重启后也自动复原）"
fi
# 还原点坏了以后的最后一道门：随包原厂基线。没有它，off 只能跳过 A18，
# 用户不重启相机就还是旧画面 —— 2026-11-11 那次"还原成功但没还原"就是这段。
for f in a18_orig.bin still6_orig.bin bv12_orig.bin; do
    if [ -s "$D/lut/factory/$f" ]; then
        pass "随包基线 $f $(fsize "$D/lut/factory/$f")B"
    else
        warn "随包基线缺 $D/lut/factory/$f —— 还原点损坏时没法兜底（apply 不受影响）"
    fi
done

echo
echo "=== 3. 登记表原厂备份 still6/bv12  (硬编码路径，丢了就静默跳过) ==="
[ -d "$BAK" ] || bad "目录 $BAK 不存在: still/bv 两项 restore 永远不会执行"
for e in still6_orig.bin:24 bv12_orig.bin:48; do
    f=${e%:*}
    want=${e#*:}
    if [ -f "$BAK/$f" ]; then
        sz=$(fsize "$BAK/$f")
        m=$(md8 "$BAK/$f")
        if [ "$sz" = "$want" ]; then
            pass "$f ${sz}B  md5=$m"
        else
            bad "$f 尺寸=$sz（应为 $want）: read_file 会短读 -> rc=1 -> 'ERR restore incomplete'"
        fi
    else
        bad "$f 缺失于 $BAK: 这张表不会被还原（静默跳过，面板仍报成功）"
    fi
done

echo
echo "=== 4. 硬件此刻的登记表 ==="
RGBT=
for d in "$D/lut" /mnt/mmc/lut; do
    if [ -x "$d/nx_regtabwrite.arm" ]; then RGBT=$d/nx_regtabwrite.arm; break; fi
done
if [ -n "$RGBT" ]; then
    "$RGBT" view-status  2>&1 | $BB head -n 2
    "$RGBT" still-status 2>&1 | $BB head -n 2
    "$RGBT" bv-status    2>&1 | $BB head -n 2
    echo "  （健康 off 之后 VIEW4 应为 0x810fd100 0x81101e00 0x81106b00 0x81115200）"
    echo "  （STILL6[0]=0x81119f00 在原厂 dump 里本来就是这样，不是故障）"
else
    warn "regtabwrite 不可执行，跳过"
fi

echo
echo "=== 5. 引擎指针 0x2082b00c ==="
cur=$($BB devmem $ENGREG 32 2>/dev/null | $BB tr 'A-F' 'a-f' | $BB tr -d ' ')
if [ -n "${cur:-}" ]; then
    info "$ENGREG = $cur"
    case "$cur" in
        0x81119f00) info "指向 A18 属正常（原厂 Still6[0] 也是 A18），不能据此判失败" ;;
        *) info "p7 已自行选了别的表；A18 内容仍应是原厂" ;;
    esac
else
    warn "devmem 读不到 $ENGREG"
fi

echo
echo "=== 6. 面板实际看到的结果（决定性证据） ==="
if [ -f /tmp/nxui.log ]; then
    $BB grep 'BACKEND kind=8' /tmp/nxui.log 2>/dev/null | $BB tail -n 3
    n=$($BB grep -c 'BACKEND kind=8' /tmp/nxui.log 2>/dev/null)
    [ "${n:-0}" = 0 ] && info "本次开机还没有 off 记录"
    echo "  （ok=1 => off 真的成功；elapsed_ms 接近 30000 => 被面板 30s 超时杀掉，改动可能只做了一半）"
else
    info "/tmp/nxui.log 不存在（本次开机没起过面板？）"
fi

echo
echo "=== 7. off 日志 ==="
found=0
for f in "$ST"/off-view.log "$ST"/off-still.log "$ST"/off-bv.log "$ST"/off-slot.log "$ST"/off-lutptr.log; do
    [ -f "$f" ] || continue
    found=1
    echo "--- ${f##*/}"
    $BB grep -E 'FAIL|ERR|REFUSE|readback|stray|READBACK|WARN' "$f" 2>/dev/null | $BB tail -n 4
done
[ "$found" = 0 ] && warn "tmpfs 里没有 off-*.log: 本次开机没点过还原，或 off 在写之前就退了"
# 重启后 tmpfs 已清空，唯一还在的是失败时特意落盘的那份
if [ -d "$PD/last-failure" ]; then
    echo "--- 上次失败落盘的证据 ($PD/last-failure/)"
    for f in "$PD"/last-failure/*.log; do
        [ -f "$f" ] || continue
        echo "  ${f##*/}: $($BB grep -E 'FAIL|ERR|REFUSE|READBACK|WARN' "$f" 2>/dev/null | $BB tail -n 2 | $BB tr '\n' ' ')"
    done
fi

echo
echo "=== 8. 录像 watcher 与锁 ==="
if [ -x "$D/lut_video.sh" ]; then
    sh "$D/lut_video.sh" status 2>&1
else
    bad "$D/lut_video.sh 缺失: lut.sh off 第二步就 die，整套还原不执行"
fi
if [ -s /tmp/nxwa-lut-video/pid ]; then
    info "watcher pid=$(cat /tmp/nxwa-lut-video/pid 2>/dev/null)"
fi
# 真跑一次非阻塞锁，比 --help 可靠（busybox 的 --help 会被部分 applet 当文件名）
if ( exec 9>/dev/null; $BB flock -n 9 ) 2>/dev/null; then
    pass "busybox flock 可用（control_lock 能工作）"
else
    bad "busybox flock 不可用: lut_video.sh 的 control_lock 恒失败 -> off 直接 die"
fi

echo
echo "=== 9. SD 卡健康 ==="
# 真身是 name-N 副本：raw/uniq 比不出来（名字本来就不同），只能按模式数
dupn=$($BB ls "$PD" 2>/dev/null | $BB grep -cE '^[A-Za-z_.]+-[0-9]+$')
if [ "${dupn:-0}" -gt 0 ]; then
    warn "$PD 里有 $dupn 个 name-N 副本（chkdsk 批量改名的产物）：整目录改名重建，别逐条 rm（exFAT 删一条就释放簇链）"
else
    pass "$PD 无 name-N 副本"
fi
$BB df -k /mnt/mmc 2>/dev/null | $BB tail -n 2

echo
echo "=== 10. 残留标志 ==="
[ -f "$ST/ready" ]   && warn "ready 残留: 上次没收尾，下次 apply 会先跑 off 并可能覆盖原厂备份"
[ -f "$ST/keep" ]    && info "keep 存在（半按保留通道）"
[ -f "$ST/current" ] && info "current = $(cat "$ST/current" 2>/dev/null)"
[ -f "$ST/oled_orig" ] && info "屏幕色彩原值 = $(cat "$ST/oled_orig" 2>/dev/null)"

echo
if [ "$fails" -eq 0 ]; then
    echo "VERDICT 没有阻塞性故障。重跑一次「还原原厂」，然后看: tail -5 /tmp/nxui.log"
else
    echo "VERDICT $fails 项阻塞故障，见上面 FAIL"
fi
