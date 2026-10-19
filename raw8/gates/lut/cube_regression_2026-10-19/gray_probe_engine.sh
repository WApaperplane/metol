#!/bin/sh
# @gate script=lut.sh opens=rwdirect one_shot=0 gate=none pconly=0
#=====================================================================
# lut.sh — 3D LUT 滤镜，独立于 filmlab
#=====================================================================
# 设计（2026-10-19，正常事件重载）：
#   · sRGB 下 OLED 开启选 View4[1]，关闭选 View4[3]，两项必须同时更新。
#   · 写入当前未加载的 A18/A19，再切换 OLED 设置并恢复原值，让 P7 正常加载。
#   · 成功条件包含实际 load_addr 回读，不能只检查登记表或状态文件。
#   · AdobeRGB / 原厂智能滤镜分支尚未验证，apply 明确拒绝。
#   · A18/A19 各有原厂备份（a18_orig.bin / a19_orig.bin），off 两个都还原
#     （A19 是双槽时代的遗留工作槽，可能被写过，所以一并还原）
#   · 不调用裸寄存器 reload；正常事件结束后保留用户原来的 OLED 设置。
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
CAP=/usr/bin/st
TD=$D/lut                       # 工具目录（随包安装：scripts/lut -> /opt/usr/nx-ks/lut）
LAB=/mnt/mmc/lcg135549              # 滤镜库：*.cube / *.bin
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

current_slot() {
    if [ -f "$ST/active" ]; then
        read -r active < "$ST/active"
        case "$active" in a18|a19) echo "$active"; return 0 ;; esac
    fi
    # 兼容单槽版本的状态文件。
    [ -f "$ST/current" ] && { echo a18; return 0; }
    echo ""
}

oled_restore=
locked=0
cleanup() {
    if [ -n "$oled_restore" ]; then
        "$CAP" cap capdtm setusr 108 "$oled_restore" >> "$ST/refresh.log" 2>&1
    fi
    [ "$locked" = 0 ] || $BB rmdir "$ST/.lock"
}

lock_writer() {
    $BB mkdir -p "$ST" || die "cannot create $ST"
    $BB mkdir "$ST/.lock" 2>/dev/null || die "another LUT operation is running"
    locked=1
    trap cleanup EXIT
    trap 'exit 1' HUP INT TERM
}

userdata() {
    "$CAP" cap capdtm getusr "$1" | $BB tr -d '\000\r'
}

prepare_refresh() {
    [ -x "$CAP" ] || die "missing camera settings command"
    value=$(userdata 108)
    case "$value" in
        *'OLEDCOLOR_OFF (0x6c0000)'*) oled=0x6c0000; other_oled=0x6c0001 ;;
        *'OLEDCOLOR_ON (0x6c0001)'*) oled=0x6c0001; other_oled=0x6c0000 ;;
        *) die "cannot read OLED colour setting" ;;
    esac
}

check_view_mode() {
    value=$(userdata 50)
    case "$value" in *'COLORSPACE_SRGB (0x320000)'*) ;; *) die "LUT switching currently requires sRGB" ;; esac
    value=$(userdata 62)
    case "$value" in *'SMARTFILTERTYPE_OFF (0x3e0000)'*) ;; *) die "turn off the camera Smart Filter before applying a LUT" ;; esac
}

loaded_slot() {
    # status is read-only; the fifth field is the actual EP load source.
    set -- $($BB grep '^REGS: 0x' "$1")
    [ "$#" = 6 ] || return 1
    printf '%s\n' "$5"
}

refresh_view() {
    oled_restore=$oled
    "$CAP" cap capdtm setusr 108 "$other_oled" > "$ST/refresh.log" 2>&1 || return 1
    $BB sleep 1
    "$CAP" cap capdtm setusr 108 "$oled" >> "$ST/refresh.log" 2>&1 || return 1
    $BB sleep 1
    value=$(userdata 108)
    case "$value" in *"($oled)"*) oled_restore= ;; *) return 1 ;; esac
    "$REGT" status > "$ST/loaded.log" 2>&1 || return 1
}

patch_view() {
    "$REGT" patch1 "$1" > "$ST/view1.log" 2>&1 || return 1
    "$REGT" patch "$1" > "$ST/view.log" 2>&1 || return 1
    "$REGT" status > "$ST/patched.log" 2>&1 || return 1
    line=$($BB grep '^VIEW4 ' "$ST/patched.log")
    set -- $line
    [ "$#" = 6 ] && [ "$4" = "$tgt_lower" ] && [ "$6" = "$tgt_lower" ]
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
    lock_writer
    ensure_both
    echo "OK backups ready ($ST)"
    ;;

apply)
    name=${2:-}
    [ -n "$name" ] || die "usage: lut.sh apply <name>"
    case "$name" in */*|.|..|*'
'*) die "invalid LUT name" ;; esac
    need_tools
    [ -d "$LAB" ] || die "no $LAB"

    src=
    [ -f "$LAB/$name.cube" ] && src=$LAB/$name.cube
    [ -z "$src" ] && [ -f "$LAB/$name.bin" ] && src=$LAB/$name.bin
    [ -n "$src" ] || die "not found: $name (.cube or .bin)"

    lock_writer
    prepare_refresh
    check_view_mode

    # 先确保两个槽的原厂备份都在，再决定写哪个槽
    ensure_both

    "$REGT" status > "$ST/before.log" 2>&1 || die "cannot read current load source"
    loaded=$(loaded_slot "$ST/before.log") || die "cannot parse current load source"
    case "$loaded" in
        0x81119f00) tgt=$SLOT_A19; tgt_lower=0x8111ec00; tname=a19 ;;
        0x8111ec00|0x81115200|0x81101e00) tgt=$SLOT_A18; tgt_lower=0x81119f00; tname=a18 ;;
        *) die "unexpected active LUT branch ($loaded); no slot written" ;;
    esac
    echo "SLOT $tname ($tgt), previous load=$loaded"

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

    # 新表写入当前未加载的工作槽，回读通过后才切登记项。
    "$SLOTW" write "$tgt" "$table" > "$ST/write.log" 2>&1 \
        || { cat "$ST/write.log"; die "slot write failed"; }
    $BB grep -q 'READBACK ok' "$ST/write.log" || { cat "$ST/write.log"; die "slot write not verified"; }

    # 两条登记表都指向目标槽；still 首次用 still-set（会备份），之后 still-write
    patch_view "$tgt" || die "view registry did not take $tgt (requires patch1 support)"
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

    refresh_view || die "camera refresh failed; see $ST/refresh.log"
    loaded=$(loaded_slot "$ST/loaded.log") || die "cannot verify refreshed load source"
    [ "$loaded" = "$tgt_lower" ] || die "camera still loads $loaded, expected $tgt_lower"
    printf '%s\n' "$tname"  > "$ST/active"
    printf '%s\n' "$name"   > "$ST/current"
    echo "OK applied $name"
    echo "LOADED $loaded; OLED restored to $oled"
    ;;

off)
    need_tools
    lock_writer
    prepare_refresh
    if [ ! -f "$ST/a18_orig.bin" ] && [ ! -f "$ST/a19_orig.bin" ]; then
        echo "OK nothing to restore"
        exit 0
    fi
    rc=0
    "$REGT" patch1 0x81101e00 > "$ST/off-view1.log" 2>&1 || rc=1
    "$REGT" restore > "$ST/off-view.log" 2>&1 || rc=1
    if [ -f "$STILLBAK" ]; then
        "$REGT" still-restore > "$ST/off-still.log" 2>&1 || rc=1
    fi
    # 两个槽都还原：A19 是双槽时代的遗留工作槽，可能被写过
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
    refresh_view || die "factory tables restored but camera refresh failed"
    loaded=$(loaded_slot "$ST/loaded.log") || die "cannot verify factory load source"
    case "$loaded" in
        0x81119f00|0x8111ec00) die "camera still loads a work slot after off ($loaded)" ;;
    esac
    $BB rm -f "$ST/active" "$ST/current" "$ST/ready" "$ST/keep"
    echo "OK restored (view1=A13, view3=A17, still=original, A18+A19=original)"
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
