#!/usr/bin/env bash
#=====================================================================
# lut_sd.sh — 在 PC 侧（读卡器）审计并修复相机 SD 卡上的 LUT 还原点
#=====================================================================
# 背景：面板「还原失败」= lut.sh off 非 0 退出。它写的四份日志
#       (off-view/still/bv/slot.log) 都在 SD 卡的 lut/state 下，
#       所以不联网、不进相机，把卡插读卡器就能定位。
#
# 用法：
#   bash tools/lut_sd.sh                 # 自动找卡，只读审计
#   bash tools/lut_sd.sh /f              # 指定卡根（Git Bash 的 /f = F:\）
#   bash tools/lut_sd.sh /f --fix        # 审计 + 修复（改卡前先备份）
#
# --fix 只做三件事，全部是文件级、可逆：
#   1. lut/state/a18_orig.bin 被污染/尺寸不对 -> 换成已知原厂基线
#   2. nxwa_regtab_20261018/{still6,bv12}_orig.bin 缺失 -> 用固件原厂值重建
#   3. 清掉 lut/state/ready、keep（否则下次 apply 会再次覆盖原厂备份）
#=====================================================================
set -u

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(dirname "$HERE")
FACTORY="$ROOT/scripts/lut/factory"
FACTORY_A18="$FACTORY/a18_orig.bin"
FACTORY_MD5=4c0cc78c
SLOT_LEN=19712

SD=
FIX=0
for a in "$@"; do
    case "$a" in
        --fix) FIX=1 ;;
        -*) ;;
        *) SD=$a ;;
    esac
done

if [ -z "$SD" ]; then
    for d in /c /d /e /f /g /h /i /j /k; do
        [ -d "$d" ] || continue
        if [ -d "$d/lut/state" ] || [ -d "$d/nxwa_regtab_20261018" ]; then SD=$d; break; fi
    done
fi
if [ -z "$SD" ]; then
    echo "ERR 找不到 SD 卡根目录（没有 lut/state 也没有 nxwa_regtab_20261018）"
    echo "     手动指定：bash tools/lut_sd.sh /f"
    exit 2
fi
SD=${SD%/}          # 去掉末尾斜杠，否则 rel() 的 ${1#$SD/} 会拼出双斜杠匹配不上

ST=$SD/lut/state
BAK=$SD/nxwa_regtab_20261018
NKS=$SD/nx-ks
rel() { echo "${1#$SD/}"; }
fails=0
pass() { echo "PASS  $*"; }
bad()  { echo "FAIL  $*"; fails=$((fails + 1)); }
warn() { echo "WARN  $*"; }
info() { echo "INFO  $*"; }
fsize() { stat -c%s "$1" 2>/dev/null || echo 0; }
md8() { md5sum "$1" 2>/dev/null | cut -c1-8; }

echo "SD 根: $SD"
echo
echo "=== 1. 目录 ==="
for d in "$ST" "$BAK" "$NKS"; do
    if [ -d "$d" ]; then pass "$(rel "$d")"; else warn "$(rel "$d") 不存在"; fi
done

echo
echo "=== 2. 还原点 a18_orig.bin ==="
# 2026-11-13 起 lut.sh 把还原点挪到 /tmp/lut/state（tmpfs）：A18 是易失内存，
# 重启就回原厂，备份本来不需要跨开机。卡上还有这个文件 = 旧版布局，要单独看。
if [ -f "$ST/a18_orig.bin" ]; then
    sz=$(fsize "$ST/a18_orig.bin"); m=$(md8 "$ST/a18_orig.bin")
    if [ "$sz" = 0 ]; then
        bad "0 字节：这就是 off 报 FAIL short source file 的原因；删掉它并升级到新版 lut.sh"
    elif [ "$sz" = "$SLOT_LEN" ]; then
        case "${m:-none}" in
            "$FACTORY_MD5") pass "19712B md5=$m（旧版布局，内容=原厂基线）" ;;
            *) warn "19712B md5=$m ≠ 原厂 —— 旧版布局下还原会落到非原厂内容" ;;
        esac
    else
        bad "尺寸=$sz（应为 $SLOT_LEN）"
    fi
else
    info "卡上没有 —— 新版把还原点放 /tmp/lut/state（tmpfs），这是正常的"
fi

echo
echo "=== 3. 登记表原厂备份 ==="
if [ -d "$BAK" ]; then
    for e in still6_orig.bin:24 bv12_orig.bin:48; do
        f=${e%:*}; want=${e#*:}
        if [ -f "$BAK/$f" ]; then
            sz=$(fsize "$BAK/$f")
            if [ "$sz" = "$want" ]; then pass "$f ${sz}B md5=$(md8 "$BAK/$f")"; else bad "$f 尺寸=$sz（应为 $want）"; fi
        else
            bad "$f 缺失（这张表永远不会被还原）"
        fi
    done
else
    warn "nxwa_regtab_20261018 不在这个根下（若只打包了 lut/ 就是正常的；off-still/off-bv.log 里有 READBACK ok 即说明真卡上有）"
fi

echo
echo "=== 4. off 日志（这是判「还原失败」的主证据） ==="
if [ -d "$ST/last-failure" ]; then
    echo "--- 新版：失败时特意落盘到卡的证据目录 lut/state/last-failure/"
    for f in "$ST"/last-failure/*.log; do
        [ -f "$f" ] || continue
        echo "  --- ${f##*/}  ($(fsize "$f")B)"
        grep -E 'FAIL|ERR|REFUSE|READBACK|readback|stray' "$f" 2>/dev/null | head -n 6 | sed 's/^/    /'
    done
fi
n=0
for f in "$ST"/off-view.log "$ST"/off-still.log "$ST"/off-bv.log "$ST"/off-slot.log "$ST"/off-lutptr.log "$ST"/previous-off.log; do
    [ -f "$f" ] || continue
    n=$((n + 1))
    echo "--- ${f##*/}  ($(fsize "$f")B)"
    sed -n '1,40p' "$f"
done
if [ "$n" = 0 ]; then
    bad "一份 off 日志都没有 → off 在写之前就退了：工具缺失/无执行位，或 lut_video.sh 抢锁 die"
else
    if grep -q 'FAIL\|ERR\|REFUSE' "$ST"/off-*.log 2>/dev/null; then
        echo
        echo ">>> 命中的失败行："
        grep -n 'FAIL\|ERR\|REFUSE' "$ST"/off-*.log 2>/dev/null
    fi
    if grep -q 'READBACK ok' "$ST"/off-slot.log 2>/dev/null; then
        pass "off-slot.log 有 READBACK ok（A18 已写回并校验通过）"
    fi
fi

echo
echo "=== 5. 状态残留 ==="
[ -f "$ST/ready" ]   && warn "ready 残留：下次 apply 的 begin 会先 off，若再失败就把当时 A18 当原厂 dump，永久污染备份" || pass "无 ready 残留"
[ -f "$ST/keep" ]    && warn "keep 残留（半按保留通道）" || :
[ -f "$ST/current" ] && info "current = $(cat "$ST/current" 2>/dev/null)" || :

echo
echo "=== 5b. exFAT 重复目录项（这张卡的已知病） ==="
dupn=$(ls "$ST" 2>/dev/null | grep -cE '^[A-Za-z_.]+-[0-9]+$')
if [ "${dupn:-0}" -gt 0 ]; then
    warn "state 里有 $dupn 个 name-N 副本（chkdsk 批量改名的产物）。这说明同名目录项已积累过 $dupn 条"
    echo "        清理方式：整目录改名重建，别逐条删（exFAT 无簇引用计数，删一条会释放簇链）"
else
    pass "没有 name-N 副本"
fi

echo
echo "=== 6. pwrlog 时间轴 ==="
if [ -f "$NKS/pwrlog.txt" ]; then
    grep -i 'LUT' "$NKS/pwrlog.txt" 2>/dev/null | tail -n 8
    info "全文: $(rel "$NKS")/pwrlog.txt"
else
    warn "pwrlog.txt 不存在（正式版不带）"
fi

echo
echo "=== 7. lut 工具是否随卡 ==="
for t in nx_slotwrite.arm nx_regtabwrite.arm nx_lutload.arm; do
    hit=
    for d in "$SD/scripts/lut" "$SD/lut"; do
        [ -f "$d/$t" ] && { hit=$d/$t; break; }
    done
    if [ -n "$hit" ]; then pass "$t 在 $(rel "$hit")"; else warn "$t 不在卡上（该卡只作运行介质，工具在机身 /opt/usr/nx-ks/lut）"; fi
done

if [ "$FIX" = 1 ]; then
    echo
    echo "=== FIX ==="
    ts=$(date +%Y%m%d-%H%M%S)
    mkdir -p "$ST" "$BAK"

    if [ -f "$FACTORY_A18" ]; then
        cur=$(md8 "$ST/a18_orig.bin" 2>/dev/null || echo none)
        if [ "$cur" != "$FACTORY_MD5" ]; then
            [ -f "$ST/a18_orig.bin" ] && cp -f "$ST/a18_orig.bin" "$ST/a18_orig.bin.bak-$ts"
            cp -f "$FACTORY_A18" "$ST/a18_orig.bin"
            echo "FIXED a18_orig.bin <- 原厂基线 $(md8 "$ST/a18_orig.bin")（旧的存为 .bak-$ts）"
        else
            echo "SKIP  a18_orig.bin 已是原厂基线"
        fi
    else
        echo "ERR   缺 $FACTORY_A18，无法恢复 a18_orig.bin"
    fi

    # 这两组值是 2026-11-08 off 成功后 nx_regtabwrite status 打出的原厂状态，
    # 已随包放在 scripts/lut/factory/；缺失时用内联值重建同一份内容。
    u32le() { local h=$1; printf "\\x${h:6:2}\\x${h:4:2}\\x${h:2:2}\\x${h:0:2}"; }
    if [ ! -f "$BAK/still6_orig.bin" ] || [ "$(fsize "$BAK/still6_orig.bin")" != 24 ]; then
        [ -f "$FACTORY/still6_orig.bin" ] && cp -f "$FACTORY/still6_orig.bin" "$BAK/still6_orig.bin" || \
        { u32le 81119f00; u32le 81115200; u32le 8111ec00; u32le 8110b800; u32le 81106b00; u32le 81110500; } > "$BAK/still6_orig.bin"
        echo "FIXED still6_orig.bin 重建 24B $(md8 "$BAK/still6_orig.bin")"
    else
        echo "SKIP  still6_orig.bin 已在"
    fi
    if [ ! -f "$BAK/bv12_orig.bin" ] || [ "$(fsize "$BAK/bv12_orig.bin")" != 48 ]; then
        [ -f "$FACTORY/bv12_orig.bin" ] && cp -f "$FACTORY/bv12_orig.bin" "$BAK/bv12_orig.bin" || \
        { u32le 8116c000; u32le 81175a00; u32le 81167300; u32le 81170d00; u32le 81184100; u32le 810fd100
          u32le 81188e00; u32le 81101e00; u32le 8115d900; u32le 8117a700; u32le 81162600; u32le 8117f400; } > "$BAK/bv12_orig.bin"
        echo "FIXED bv12_orig.bin 重建 48B $(md8 "$BAK/bv12_orig.bin")"
    else
        echo "SKIP  bv12_orig.bin 已在"
    fi

    for f in ready keep; do
        if [ -f "$ST/$f" ]; then rm -f "$ST/$f" && echo "FIXED 删除 $f"; fi
    done
    sync 2>/dev/null
    echo
    echo "下一步：拔卡插回相机 -> 开机 -> 面板「还原原厂」"
fi

echo
if [ "$FIX" = 1 ]; then
    echo "VERDICT 已完成 FIX（上面的 FAIL 是修复前状态）。再跑一次不带 --fix 确认，然后插回相机试还原。"
elif [ "$fails" -eq 0 ]; then
    echo "VERDICT 卡上未发现阻塞项"
    echo "        若仍报失败，先确认机上 /opt/usr/nx-ks/lut/*.arm 有执行位再试"
else
    echo "VERDICT $fails 项阻塞问题，见上 FAIL"
    echo "        加 --fix 可修「还原点缺失/被污染」和「原厂登记表缺失」两类"
fi
