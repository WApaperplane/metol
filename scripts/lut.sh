#!/bin/sh
# @gate script=lut.sh opens=rwdirect one_shot=0 gate=none pconly=0
#=====================================================================
# lut.sh — 3D LUT 滤镜（双槽交替 + 两张登记表），独立于 filmlab
#=====================================================================
# 设计（2026-10-19 修订，v3）：
#   · 两个工作槽 A18 / A19 交替使用，每次 apply 换到另一个槽
#       A18 = 0x81119F00（A17 的邻居槽）
#       A19 = 0x8111EC00（原厂 Still6[2] 的目标槽）
#     ⇒ 登记表那 4 字节每次切换都会变。旧版固定 A18，第二次起
#       View4[3] 已经是 A18，patch 直接 "already at target" 不写，
#       p7 没有"源变了"的信号，且新表是在正被引用的槽上逐字节覆盖。
#   · View4[3] 与 Still6 六项同时指向当前工作槽 ⇒ 取景器与成片都生效
#   · 两槽各有独立原厂备份（a18_orig.bin / a19_orig.bin），off 两个都还原
#   · apply 不触发硬件 Load（裸写 +0x00c 会花屏，见 3DLUT_API_GUIDE）
#     ⇒ 写完由用户半按一次快门，让 p7 自己走完选表流程
#   · 与 filmlab 互不干扰：filmlab 走 PW 7 维标量（档位池 0xdc..0xe2）
#
# 用法：
#   lut.sh list                 列出滤镜库
#   lut.sh begin                只补两槽的原厂备份（不碰登记表）
#   lut.sh apply <name>         应用（.cube 自动转换），自动换到另一槽
#   lut.sh off                  还原两槽 + 两张登记表
#   lut.sh status               当前 look、当前槽、备份状态
#=====================================================================
set -u
export LC_ALL=C          # deterministic glob order for `list`

D=/opt/usr/nx-ks
BB=$D/busybox
TD=$D/lut                       # 工具目录（随包安装：scripts/lut -> /opt/usr/nx-ks/lut）
LAB=/mnt/mmc/looks              # 滤镜库：*.cube / *.bin
ST=/mnt/mmc/lut/state           # 备份与状态（放 SD，随卡走）
SLOT_A18=0x81119F00
SLOT_A19=0x8111EC00
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
CUBE=$(pick_tool cube2lut.arm)

die() { echo "ERR $*"; exit 1; }

need_tools() {
    [ -n "$SLOTW" ] && [ -x "$SLOTW" ] || die "missing nx_slotwrite.arm (looked in $TD and /mnt/mmc/lut)"
    [ -n "$REGT" ]  && [ -x "$REGT" ]  || die "missing nx_regtabwrite.arm (looked in $TD and /mnt/mmc/lut)"
}

# 当前槽：a18 / a19 / 空。老版本（固定 A18）只写了 current，没有 active，
# 这种状态按"占用 A18"处理，让第一次新版 apply 换到 A19，避免原地改写。
current_slot() {
    s=
    [ -f "$ST/active" ] && read -r s < "$ST/active"
    case "$s" in a18|a19) echo "$s"; return 0 ;; esac
    if [ -f "$ST/current" ]; then echo a18; return 0; fi
    echo ""
}

# 补某一槽的原厂备份；已存在就不覆盖（首次备份必须是原厂内容）
ensure_backup() {
    addr=$1; file=$2; tag=$3
    [ -f "$file" ] && return 0
    "$SLOTW" read "$addr" "$file" > "$ST/backup-$tag.log" 2>&1 || return 1
    $BB grep -q 'SLOT dumped' "$ST/backup-$tag.log" || return 1
    return 0
}

ensure_both() {
    $BB mkdir -p "$ST" || die "cannot create $ST"
    ensure_backup "$SLOT_A18" "$ST/a18_orig.bin" a18 || die "A18 backup failed"
    ensure_backup "$SLOT_A19" "$ST/a19_orig.bin" a19 || die "A19 backup failed"
    # 旧版遗留标记：新语义下没有"退出即还原"，这两个文件不再有意义
    $BB rm -f "$ST/ready" "$ST/keep"
}

case "${1:-status}" in
list)
    # Pure shell. The previous ls|grep|sed|sort pipeline created four extra
    # processes (~10-25 ms each on this camera) every time the panel opened.
    # Glob order under LC_ALL=C is byte order, i.e. what sort -u used to give.
    [ -d "$LAB" ] || die "no $LAB"
    seen='|'
    for f in "$LAB"/*.cube "$LAB"/*.bin; do
        [ -f "$f" ] || continue
        n=${f##*/}
        n=${n%.*}
        case "$seen" in *"|$n|"*) continue ;; esac
        seen="$seen$n|"
        printf '%s\n' "$n"
    done
    ;;

begin)
    need_tools
    ensure_both
    echo "OK backups ready ($ST)"
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

    # 先确保两个槽的原厂备份都在，再决定写哪个槽
    ensure_both

    cur=$(current_slot)
    if [ "$cur" = a18 ]; then
        tgt=$SLOT_A19; tname=a19
    else
        tgt=$SLOT_A18; tname=a18
    fi
    echo "SLOT $tname ($tgt) previous=${cur:-none}"

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

    # 写槽（目标槽不是当前被引用的槽，覆盖期间 p7 即使 Load 也只读到旧表）
    "$SLOTW" write "$tgt" "$table" > "$ST/write.log" 2>&1 \
        || { cat "$ST/write.log"; die "slot write failed"; }
    $BB grep -q 'READBACK ok' "$ST/write.log" || { cat "$ST/write.log"; die "slot write not verified"; }

    # 两条登记表都指向目标槽；still 首次用 still-set（会备份），之后 still-write
    "$REGT" patch "$tgt" > "$ST/view.log" 2>&1 || { cat "$ST/view.log"; die "view registry write failed"; }
    # 回读值必须就是目标槽。旧版 nx_regtabwrite 不认槽参数、会硬写 A18，
    # 配上交替写 A19 就是"表写进去了但登记表指回 A18"——画面完全不动。
    if $BB grep -q 'READBACK' "$ST/view.log"; then
        $BB grep -qi "READBACK $tgt" "$ST/view.log" \
            || { cat "$ST/view.log"; die "view registry did not take $tgt (stale nx_regtabwrite.arm?)"; }
    fi
    if [ -f "$STILLBAK" ]; then
        "$REGT" still-write "$tgt" > "$ST/still.log" 2>&1
    else
        "$REGT" still-set  "$tgt" > "$ST/still.log" 2>&1
    fi
    $BB grep -q 'READBACK ok' "$ST/still.log" || { cat "$ST/still.log"; die "still registry write failed"; }
    $BB grep -qi "$tgt" "$ST/still.log" \
        || { cat "$ST/still.log"; die "still registry did not take $tgt (stale nx_regtabwrite.arm?)"; }

    # ★ 不自动触发硬件 Load（裸写 +0x00c + 脉冲会让 ISP 读到口袋外地址，
    #   表现为严重偏色花屏，只能靠半按让 p7 自己走完选表流程复位）。
    printf '%s\n' "$tname"  > "$ST/active"
    printf '%s\n' "$name"   > "$ST/current"
    echo "OK applied $name"
    echo "NEXT half-press once to let p7 load the table"
    ;;

off)
    need_tools
    if [ ! -f "$ST/a18_orig.bin" ] && [ ! -f "$ST/a19_orig.bin" ]; then
        echo "OK nothing to restore"
        exit 0
    fi
    rc=0
    "$REGT" restore > "$ST/off-view.log" 2>&1 || rc=1
    if [ -f "$STILLBAK" ]; then
        "$REGT" still-restore > "$ST/off-still.log" 2>&1 || rc=1
    fi
    # 两个槽都还原：交替使用意味着两个都可能被写过
    if [ -f "$ST/a18_orig.bin" ]; then
        "$SLOTW" restore "$SLOT_A18" "$ST/a18_orig.bin" > "$ST/off-a18.log" 2>&1 || rc=1
    fi
    if [ -f "$ST/a19_orig.bin" ]; then
        "$SLOTW" restore "$SLOT_A19" "$ST/a19_orig.bin" > "$ST/off-a19.log" 2>&1 || rc=1
    fi
    if [ $rc -ne 0 ]; then
        echo "ERR restore incomplete; see $ST/off-*.log"
        exit 1
    fi
    # 同样不自动 reload：登记表已回原厂，下一次 p7 自己的 Load 就取到原厂表。
    $BB rm -f "$ST/active" "$ST/current" "$ST/ready" "$ST/keep"
    echo "OK restored (view=A17, still=original, A18+A19=original)"
    ;;

status)
    need_tools
    if [ -f "$ST/current" ]; then
        read -r cur < "$ST/current"
        echo "ACTIVE $cur (slot $(current_slot))"
    else
        echo "IDLE"
    fi
    echo "BACKUP a18=$([ -f "$ST/a18_orig.bin" ] && echo present || echo absent) a19=$([ -f "$ST/a19_orig.bin" ] && echo present || echo absent)"
    "$REGT" status 2>/dev/null | $BB sed -n '2,3p'
    ;;

*)
    echo "usage: lut.sh list|begin|apply <name>|off|status"
    exit 2
    ;;
esac
