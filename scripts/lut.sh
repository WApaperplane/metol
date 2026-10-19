#!/bin/sh
# @gate script=lut.sh opens=rwdirect one_shot=0 gate=none pconly=0
#=====================================================================
# lut.sh — 3D LUT 滤镜（改登记表 + 写空闲槽 A18），独立于 filmlab
#=====================================================================
# 设计（2026-10-18 实机定案）：
#   · 表放 A18（0x81119F00，A17 的邻居槽），原地写入，重启即复原
#   · View4[3] 与 Still6[6] 同时指向 A18 ⇒ 取景器与成片都生效
#   · 与 filmlab 互不干扰：filmlab 走 PW 7 维标量（档位池 0xdc..0xe2），
#     本脚本走 3D LUT 槽 + 登记表；两者可叠加
#   · begin 备份、off 还原；apply 不覆盖首次备份
#
# 用法：
#   lut.sh list                 列出滤镜库
#   lut.sh begin                预检 + 备份（不写相机内存）
#   lut.sh apply <name>         应用（.cube 自动转换）
#   lut.sh off                  还原
#   lut.sh status               当前状态
#=====================================================================
set -u

D=/opt/usr/nx-ks
BB=$D/busybox
TD=$D/lut                       # 工具目录（随包安装：scripts/lut -> /opt/usr/nx-ks/lut）
LAB=/mnt/mmc/looks              # 滤镜库：*.cube / *.bin
ST=/mnt/mmc/lut/state           # 备份与状态（放 SD，随卡走）
SLOT=0x81119F00                 # A18
STILLBAK=/mnt/mmc/nxwa_regtab_20261018/still6_orig.bin

# 工具查找：优先随包安装的 $TD，其次手工部署的 /mnt/mmc/lut
pick_tool() {
    for d in "$TD" /mnt/mmc/lut; do
        [ -x "$d/$1" ] && { echo "$d/$1"; return 0; }
    done
    return 1
}
SLOTW=$(pick_tool nx_slotwrite.arm)
REGT=$(pick_tool nx_regtabwrite.arm)
REGT1=$(pick_tool nx_regtabwrite1.arm) || REGT1=
CUBE=$(pick_tool cube2lut.arm)

die() { echo "ERR $*"; exit 1; }

need_tools() {
    [ -n "$SLOTW" ] && [ -x "$SLOTW" ] || die "missing nx_slotwrite.arm (looked in $TD and /mnt/mmc/lut)"
    [ -n "$REGT" ]  && [ -x "$REGT" ]  || die "missing nx_regtabwrite.arm (looked in $TD and /mnt/mmc/lut)"
}

case "${1:-status}" in
list)
    [ -d "$LAB" ] || die "no $LAB"
    $BB ls "$LAB" 2>/dev/null | $BB grep -E '\.(cube|bin)$' | $BB sed 's/\.[^.]*$//' | $BB sort -u
    ;;

begin)
    need_tools
    $BB mkdir -p "$ST" || die "cannot create $ST"
    # 每次进入都重新取一份"当前状态"作为本次会话的还原点。
    # 但有两种例外：
    #   · 上次是半按关闭（keep 标记）⇒ 用户要保留这个 look，沿用同一份备份
    #   · 上次异常退出（ready 残留但无 keep）⇒ 先还原，避免把已改状态当原厂
    if [ -f "$ST/ready" ]; then
        if [ -f "$ST/keep" ]; then
            $BB rm -f "$ST/keep"
            echo "OK resumed (look kept, previous backup reused)"
            exit 0
        fi
        sh "$0" off > "$ST/previous-off.log" 2>&1
    fi
    "$SLOTW" read "$SLOT" "$ST/a18_orig.bin" > "$ST/begin.log" 2>&1 \
        || { cat "$ST/begin.log"; die "slot backup failed"; }
    $BB grep -q 'SLOT dumped' "$ST/begin.log" || { cat "$ST/begin.log"; die "slot backup not confirmed"; }
    : > "$ST/ready"
    echo "OK backup written to $ST/a18_orig.bin"
    ;;

apply)
    name=${2:-}
    [ -n "$name" ] || die "usage: lut.sh apply <name>"
    need_tools
    [ -d "$LAB" ] || die "no $LAB"

    src=
    [ -f "$LAB/$name.cube" ] && src=$LAB/$name.cube
    [ -z "$src" ] && [ -f "$LAB/$name.bin" ] && src=$LAB/$name.bin
    [ -n "$src" ] || die "not found: $name (.cube or .bin)"

    $BB mkdir -p "$ST"

    # 首次进入时若未备份，先建立本次会话的还原点（不写 LUT）
    if [ ! -f "$ST/ready" ]; then
        sh "$0" begin || die "backup failed"
    fi

    # .cube 需要机上转换
    table=$src
    case "$src" in
        *.cube)
            [ -x "$CUBE" ] || die "missing $CUBE"
            table=$ST/current.bin
            "$CUBE" "$src" "$table" > "$ST/convert.log" 2>&1 \
                || { cat "$ST/convert.log"; die "cube conversion failed"; }
            $BB grep -q '=== done ===' "$ST/convert.log" || { cat "$ST/convert.log"; die "conversion not confirmed"; }
            ;;
    esac

    # 写槽（不覆盖首次备份）
    "$SLOTW" write "$SLOT" "$table" > "$ST/write.log" 2>&1 \
        || { cat "$ST/write.log"; die "slot write failed"; }
    $BB grep -q 'READBACK ok' "$ST/write.log" || { cat "$ST/write.log"; die "slot write not verified"; }

    # 两条登记表都指向 A18；still 首次用 still-set（会备份），之后 still-write
    "$REGT" patch > "$ST/view.log" 2>&1 || { cat "$ST/view.log"; die "view registry write failed"; }
    # sRGB 下 OLED 开启时取景器读 View4[1]（原厂 A13），关闭时读 [3]。
    # 本版只改 [3]，会漏掉开启状态，所以补写 [1]（工具缺失时跳过）。
    if [ -n "$REGT1" ]; then
        "$REGT1" patch1 "$SLOT" > "$ST/view1.log" 2>&1 || { cat "$ST/view1.log"; die "view4[1] write failed"; }
    fi
    if [ -f "$STILLBAK" ]; then
        "$REGT" still-write > "$ST/still.log" 2>&1
    else
        "$REGT" still-set  > "$ST/still.log" 2>&1
    fi
    $BB grep -q 'READBACK ok' "$ST/still.log" || { cat "$ST/still.log"; die "still registry write failed"; }

    # ★ 不自动触发硬件 Load。
    #   从 ARM 侧裸写 +0x00c + 脉冲会让 ISP 读到它"口袋体系"外的地址组合，
    #   表现为严重偏色花屏（3DLUT_API_GUIDE 的历史结论），且必须靠半按快门
    #   让 p7 自己走完选表流程才能复位。
    #   p7 只在自己的事件（半按/切档）里重新读取登记表，所以这里只改表与指针，
    #   由用户半按一次完成装载。半按在 LUT 模式下不会关闭面板。
    printf '%s\n' "$name" > "$ST/current"
    echo "OK applied $name"
    echo "NEXT half-press once (panel stays open)"
    ;;

off)
    need_tools
    if [ ! -f "$ST/a18_orig.bin" ]; then
        echo "OK nothing to restore"
        exit 0
    fi
    rc=0
    "$REGT" restore > "$ST/off-view.log" 2>&1 || rc=1
    if [ -n "$REGT1" ]; then
        "$REGT1" patch1 0x81101E00 > "$ST/off-view1.log" 2>&1 || rc=1
    fi
    if [ -f "$STILLBAK" ]; then
        "$REGT" still-restore > "$ST/off-still.log" 2>&1 || rc=1
    fi
    "$SLOTW" restore "$SLOT" "$ST/a18_orig.bin" > "$ST/off-slot.log" 2>&1 || rc=1
    if [ $rc -ne 0 ]; then
        echo "ERR restore incomplete; see $ST/off-*.log"
        exit 1
    fi
    # ★ 同样不自动 reload（理由见 apply 分支）。
    #   登记表已回原厂，下一次 p7 自己的 Load（半按/切档/拍照）就会取到原厂表。
    #   若此刻画面仍停在上一张表上，半按一次即可。
    $BB rm -f "$ST/ready" "$ST/current" "$ST/keep"
    echo "OK restored (view=A17, still=original, A18=original)"
    ;;

status)
    need_tools
    if [ -f "$ST/current" ]; then
        echo "ACTIVE $(cat "$ST/current")"
    else
        echo "IDLE"
    fi
    echo "BACKUP $([ -f "$ST/a18_orig.bin" ] && echo present || echo absent)"
    "$REGT" status 2>/dev/null | $BB sed -n '2,3p'
    ;;

*)
    echo "usage: lut.sh list|begin|apply <name>|off|status"
    exit 2
    ;;
esac
