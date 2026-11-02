#!/bin/sh
# @gate script=lut.sh opens=rwdirect one_shot=0 gate=none pconly=0
#=====================================================================
# lut.sh — 3D LUT 滤镜（改登记表 + 写空闲槽 A18），独立于 filmlab
#=====================================================================
# 设计（2026-10-18 实机定案）：
#   · 表放 A18（0x81119F00，A17 的邻居槽），原地写入，重启即复原
#   · View4[1]/[3] + Still6[6] + BV12[12] 全部指向 A18 ⇒ 取景器与成片都生效
#     （Still 有两条互斥分支，见 apply 段注释；两条都要改）
#   · 与 filmlab 互不干扰：filmlab 走 PW 7 维标量（档位池 0xdc..0xe2），
#     本脚本走 3D LUT 槽 + 登记表；两者可叠加
#   · begin 备份、off 还原；apply 不覆盖首次备份
#
# 库管理（2026-11-01 新增）：
#   · 顺序与收藏存在 $ST/order（SD 卡），一行一条，`*` 前缀 = 收藏
#   · 删除是「移到 looks/_trash/」而不是 rm：exFAT 删同名文件会释放簇链，
#     且重复目录项无法逐条清理，移动可逆、可由 PC 侧回收
#   · list 输出顺序 = order 文件顺序；未登记的条目按名字追加在后面
#
# 用法：
#   lut.sh list                 列出滤镜库（按 order 顺序，隐藏 _ 开头）
#   lut.sh list --fav           只列收藏
#   lut.sh apply <name>         应用（.cube 自动转换）
#   lut.sh begin                预检 + 备份（不写相机内存）
#   lut.sh off                  还原
#   lut.sh status               当前状态
#   lut.sh fav <name>           收藏/取消收藏（新收藏排到最前）
#   lut.sh move <name> up|down|top   调整顺序
#   lut.sh del <name>           移到 _trash/（不物理删除）
#   lut.sh index                重建 order（清掉已消失的条目）
#   lut.sh mix <A> <B> <0-100>  两表交叉混合：0=A，100=B
#   lut.sh strength <name> <0-100>   强度混合：0=原厂，100=该 look
#   lut.sh stock                dump 原厂 A17 到 looks/_stock_A17.bin（强度 0 端）
#=====================================================================
set -u

D=/opt/usr/nx-ks
BB=$D/busybox
TD=$D/lut                       # 工具目录（随包安装：scripts/lut -> /opt/usr/nx-ks/lut）
LAB=/mnt/mmc/looks              # 滤镜库：*.cube / *.bin
TRASH=$LAB/_trash               # 下架区（不是删除）
ST=/mnt/mmc/lut/state           # 备份与状态（放 SD，随卡走）
SLOT=0x81119F00                 # A18
STOCK_SLOT=0x81115200           # A17 原厂表（强度 0 端基准）
BAKDIR=/mnt/mmc/nxwa_regtab_20261018   # 原厂登记表备份（Still6 / BV12）
STILLBAK=$BAKDIR/still6_orig.bin
BVBAK=$BAKDIR/bv12_orig.bin
ORD=$ST/order                   # 库顺序 + 收藏
CV=$ST/cv                       # .cube → native 转换缓存（混合时反复用同一张）

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
MIX=$(pick_tool lutmix.arm)

die() { echo "ERR $*"; exit 1; }

need_tools() {
    [ -n "$SLOTW" ] && [ -x "$SLOTW" ] || die "missing nx_slotwrite.arm (looked in $TD and /mnt/mmc/lut)"
    [ -n "$REGT" ]  && [ -x "$REGT" ]  || die "missing nx_regtabwrite.arm (looked in $TD and /mnt/mmc/lut)"
}

# ---------- 屏幕色彩（OLED_COLOR）随之开关 ----------
# 2026-10-25 对照使用屏幕色彩关闭的分支，并保存/恢复用户原设置。
# 旧 Noir 偏绿/品红已由 RGB 设计被直接作为 CrCbY 表消费复现并修正；
# identity 中性、RGB 三分量相等都不能证明原生格式或后段处理正确。
# 保留此开关管理以沿用已验证的分支，不把 OLED 当成已经确认的偏色根因。
# 首次 apply 记下用户原值，off 时还原；prefman 不可用则静默跳过，不阻塞主流程。
PREFMAN=$(command -v prefman 2>/dev/null || echo /usr/bin/prefman)

oled_save() {
    [ -x "$PREFMAN" ] || return 0
    [ -f "$ST/oled_orig" ] && return 0
    "$PREFMAN" get 0 0x0a704 l 2>/dev/null \
        | $BB awk '/value *= */{print $3; exit}' > "$ST/oled_orig" 2>/dev/null
    [ -s "$ST/oled_orig" ] || echo 1 > "$ST/oled_orig"
    return 0
}

oled_put() {
    [ -x "$PREFMAN" ] || return 0
    "$PREFMAN" set 0 0x0a704 l "$1" >/dev/null 2>&1
    return 0
}

oled_restore() {
    [ -f "$ST/oled_orig" ] || return 0
    v=$($BB tr -dc '0-9' < "$ST/oled_orig" 2>/dev/null)
    [ -n "$v" ] && oled_put "$v"
    $BB rm -f "$ST/oled_orig"
    echo "OK screen-color restored to ${v:-1}"
    return 0
}

# ---------- 库顺序 ----------
# 名称合法性：面板会把名字原样当参数传回来，所以这里也要挡住路径与
# shell 元字符（与 nxui 的 nx_key_valid 同口径）。'_' 开头是内部项
# （_stock_A17 / _trash），不参与列表与排序。
valid_name() {
    case "$1" in
        '') return 1 ;;
        _*) return 1 ;;
        */*|*\\*|*..*|*'|'*|*';'*|*'$'*|*'`'*) return 1 ;;
    esac
    return 0
}

# 重建 order：已登记且仍存在的保持顺序与星标，新文件按名字追加，消失的丢弃。
order_sync() {
    [ -d "$LAB" ] || return 0
    $BB mkdir -p "$ST"
    $BB ls "$LAB" 2>/dev/null | $BB grep -E '\.(cube|bin)$' \
        | $BB sed 's/\.[^.]*$//' | $BB grep -v '^_' | $BB sort -u > "$ST/.names"
    if [ -s "$ORD" ]; then
        $BB awk '
            FILENAME==ARGV[1] { have[$0]=1; next }
            { k=$0; sub(/^\*/,"",k)
              if (!(k in have) || (k in seen)) next
              seen[k]=1; print }
        ' "$ST/.names" "$ORD" > "$ST/.order.1"
        $BB awk '
            FILENAME==ARGV[1] { k=$0; sub(/^\*/,"",k); seen[k]=1; next }
            { if (($0 in seen) || ($0 ~ /^_/)) next; print }
        ' "$ST/.order.1" "$ST/.names" > "$ST/.order.new"
        $BB cat "$ST/.order.new" >> "$ST/.order.1"
        $BB rm -f "$ST/.order.new"
    else
        : > "$ST/.order.1"
        while IFS= read -r n; do
            [ -n "$n" ] && printf '%s\n' "$n" >> "$ST/.order.1"
        done < "$ST/.names"
    fi
    $BB mv -f "$ST/.order.1" "$ORD"
    $BB rm -f "$ST/.names"
    return 0
}

# order 里的星标条目数（收藏是「前排」而不是另一个筛选维度）
order_fav_count() {
    [ -f "$ORD" ] || { echo 0; return 0; }
    $BB grep -c '^\*' "$ORD" 2>/dev/null || echo 0
}

# Camera BusyBox 1.20.2 grep -x fails on exact lines; compare literal keys.
order_has() {
    $BB awk -v k="$1" '$0==k {found=1} END {exit !found}' "$ORD"
}

# ---------- 表路径解析（.cube 走缓存） ----------
# 输出 native 表路径。混合/强度要反复用同一张表，每次重转 0.478 s 太贵，
# 所以按 cksum 缓存：源文件没变就不重转。
# 同名 .cube 优先（与 apply 一致），否则用 .bin。
table_of() {
    n=$1
    src=
    [ -f "$LAB/$n.cube" ] && src=$LAB/$n.cube
    [ -z "$src" ] && [ -f "$LAB/$n.bin" ] && src=$LAB/$n.bin
    [ -n "$src" ] || return 1
    case "$src" in
        *.bin) echo "$src"; return 0 ;;
    esac
    [ -x "$CUBE" ] || die "missing $CUBE"
    $BB mkdir -p "$CV"
    sum=$($BB cksum "$src" 2>/dev/null | $BB awk '{print $1 "-" $2}')
    cache=$CV/$n.bin
    if [ ! -s "$cache" ] || [ "$(cat "$CV/$n.sum" 2>/dev/null)" != "$sum" ]; then
        "$CUBE" "$src" "$cache" > "$ST/convert.log" 2>&1 \
            || { cat "$ST/convert.log"; return 1; }
        $BB grep -q '=== done ===' "$ST/convert.log" \
            || { cat "$ST/convert.log"; return 1; }
        printf '%s\n' "$sum" > "$CV/$n.sum"
    fi
    echo "$cache"
    return 0
}

# ---------- 写槽 + 改三张登记表（apply 与 mix 共用） ----------
commit_table() {
    label=$1
    table=$2
    $BB mkdir -p "$ST"

    # 关屏幕色彩（理由见 oled_save 注释）。放在写槽之前，保证半按那一刻起 ISP
    # 只受 LUT 一层影响。
    oled_save
    oled_put 0

    # 首次进入时若未备份，先建立本次会话的还原点（不写 LUT）
    if [ ! -f "$ST/ready" ]; then
        sh "$0" begin || die "backup failed"
    fi

    "$SLOTW" write "$SLOT" "$table" > "$ST/write.log" 2>&1 \
        || { cat "$ST/write.log"; die "slot write failed"; }
    $BB grep -q 'READBACK ok' "$ST/write.log" || { cat "$ST/write.log"; die "slot write not verified"; }

    # View4 四项一次写全（色彩空间 × 屏幕色彩 四种组合都会命中）：
    #   [0] A12 AdobeRGB+开   [1] A13 sRGB+开
    #   [2] A14 AdobeRGB+关   [3] A17 sRGB+关
    # 只写 [1]/[3] 会让 AdobeRGB 下取景仍是原厂表。
    "$REGT" view-set "$SLOT" > "$ST/view.log" 2>&1 || { cat "$ST/view.log"; die "view registry write failed (stale nx_regtabwrite.arm?)"; }
    $BB grep -q 'READBACK ok' "$ST/view.log" || { cat "$ST/view.log"; die "view registry write not verified"; }
    # Still（成片）有两条互斥的选表分支（p7 0x80382B30）：
    #   +0x21 == 1（屏幕色彩开启）→ BV12 十二项
    #   否则                        → Still6 六项
    # 只改 Still6 会出现「取景有滤镜、照片没有」，所以两条都指向工作槽。
    $BB mkdir -p "$BAKDIR" || die "cannot create $BAKDIR"
    if [ -f "$STILLBAK" ]; then
        "$REGT" still-write "$SLOT" > "$ST/still.log" 2>&1
    else
        "$REGT" still-set  "$SLOT" > "$ST/still.log" 2>&1
    fi
    $BB grep -q 'READBACK ok' "$ST/still.log" || { cat "$ST/still.log"; die "still6 registry write failed"; }
    if [ -f "$BVBAK" ]; then
        "$REGT" bv-write "$SLOT" > "$ST/bv.log" 2>&1
    else
        "$REGT" bv-set  "$SLOT" > "$ST/bv.log" 2>&1
    fi
    $BB grep -q 'READBACK ok' "$ST/bv.log" || { cat "$ST/bv.log"; die "bv12 registry write failed (stale nx_regtabwrite.arm?)"; }

    # ★ 不自动触发硬件 Load。
    #   从 ARM 侧裸写 +0x00c + 脉冲会让 ISP 读到它"口袋体系"外的地址组合，
    #   表现为严重偏色花屏（3DLUT_API_GUIDE 的历史结论），且必须靠半按快门
    #   让 p7 自己走完选表流程才能复位。
    #   p7 只在自己的事件（半按/切档）里重新读取登记表，所以这里只改表与指针，
    #   由用户半按一次完成装载。半按在 LUT 模式下不会关闭面板。
    printf '%s\n' "$label" > "$ST/current"
    echo "OK applied $label"
    echo "NEXT half-press once (panel stays open)"
}

case "${1:-status}" in
list)
    [ -d "$LAB" ] || die "no $LAB"
    order_sync
    only_fav=0
    [ "${2:-}" = "--fav" ] && only_fav=1
    while IFS= read -r line; do
        [ -n "$line" ] || continue
        key=${line#\*}
        if [ $only_fav -eq 1 ]; then
            case "$line" in \**) ;; *) continue ;; esac
        fi
        echo "$key"
    done < "$ORD"
    ;;

fav)
    name=${2:-}
    valid_name "$name" || die "bad name"
    [ -d "$LAB" ] || die "no $LAB"
    order_sync
    if order_has "*$name"; then
        # 取消收藏：去掉星标，留在原位（不做位置回弹，用户调过的顺序不被打乱）
        $BB awk -v k="$name" '{ if ($0 == "*" k) print k; else print }' "$ORD" > "$ST/.o"
        $BB mv -f "$ST/.o" "$ORD"
        echo "OK unfav $name"
    else
        # 新收藏 = 排到最前（收藏是「前排」语义，不是筛选维度）
        $BB awk -v k="$name" 'BEGIN { print "*" k }
                              { if ($0 == k || $0 == "*" k) next; print }' "$ORD" > "$ST/.o"
        $BB mv -f "$ST/.o" "$ORD"
        echo "OK fav $name"
    fi
    ;;

move)
    name=${2:-}; dir=${3:-up}
    valid_name "$name" || die "bad name"
    order_sync
    order_has "$name" || order_has "*$name" \
        || die "not in library: $name"
    $BB awk -v k="$name" -v dir="$dir" '
        { line[NR]=$0; key[NR]=$0; sub(/^\*/,"",key[NR]) }
        END {
            pos=0
            for (i=1;i<=NR;i++) if (key[i]==k) { pos=i; break }
            if (dir=="top") {
                if (pos>1) { t=line[pos]; for (i=pos;i>1;i--) line[i]=line[i-1]; line[1]=t }
            } else if (dir=="up") {
                if (pos>1) { t=line[pos]; line[pos]=line[pos-1]; line[pos-1]=t }
            } else if (dir=="down") {
                if (pos<NR) { t=line[pos]; line[pos]=line[pos+1]; line[pos+1]=t }
            }
            for (i=1;i<=NR;i++) print line[i]
        }
    ' "$ORD" > "$ST/.o"
    $BB mv -f "$ST/.o" "$ORD"
    echo "OK moved $name $dir"
    ;;

index)
    [ -d "$LAB" ] || die "no $LAB"
    order_sync
    echo "OK order rebuilt: $($BB wc -l < "$ORD" | $BB tr -d ' ') entries, $(order_fav_count) fav"
    ;;

del)
    name=${2:-}
    valid_name "$name" || die "bad name"
    [ -d "$LAB" ] || die "no $LAB"
    moved=
    $BB mkdir -p "$TRASH"
    for ext in cube bin; do
        if [ -f "$LAB/$name.$ext" ]; then
            $BB mv -f "$LAB/$name.$ext" "$TRASH/$name.$ext" || die "cannot move $name.$ext"
            moved="$moved $name.$ext"
        fi
    done
    [ -n "$moved" ] || die "not found: $name (.cube or .bin)"
    $BB rm -f "$CV/$name.bin" "$CV/$name.sum" 2>/dev/null
    order_sync
    $BB awk -v k="$name" '{ if ($0 != k && $0 != "*" k) print }' "$ORD" > "$ST/.o"
    $BB mv -f "$ST/.o" "$ORD"
    # 正在生效的就是它 ⇒ 一并还原，否则登记表指向一张已下架的表
    if [ -f "$ST/current" ] && [ "$(cat "$ST/current")" = "$name" ]; then
        sh "$0" off >/dev/null 2>&1 && echo "OK active look removed, restored to factory"
    fi
    echo "OK trashed:$moved"
    echo "NEXT recover from $TRASH on a PC if this was a mistake"
    ;;

stock)
    need_tools
    [ -d "$LAB" ] || die "no $LAB"
    "$SLOTW" read "$STOCK_SLOT" "$LAB/_stock_A17.bin" > "$ST/stock.log" 2>&1 \
        || { cat "$ST/stock.log"; die "stock dump failed"; }
    $BB grep -q 'SLOT dumped' "$ST/stock.log" || { cat "$ST/stock.log"; die "stock dump not confirmed"; }
    echo "OK stock A17 dumped to $LAB/_stock_A17.bin ($($BB wc -c < "$LAB/_stock_A17.bin" | $BB tr -d ' ') bytes)"
    ;;

mix)
    a=${2:-}; b=${3:-}; pct=${4:-}
    valid_name "$a" || die "bad A"
    valid_name "$b" || die "bad B"
    case "$pct" in ''|*[!0-9]*) die "usage: lut.sh mix <A> <B> <0-100>" ;; esac
    [ "$pct" -le 100 ] || die "percent must be 0..100"
    need_tools
    [ -n "$MIX" ] && [ -x "$MIX" ] || die "missing lutmix.arm (looked in $TD and /mnt/mmc/lut)"
    ta=$(table_of "$a") || die "cannot resolve A: $a"
    tb=$(table_of "$b") || die "cannot resolve B: $b"
    $BB mkdir -p "$ST"
    perm=$((pct * 10))
    "$MIX" "$ta" "$tb" "$perm" "$ST/mix.bin" > "$ST/mix.log" 2>&1 \
        || { cat "$ST/mix.log"; die "lutmix failed"; }
    $BB grep -q '=== done ===' "$ST/mix.log" || { cat "$ST/mix.log"; die "lutmix not confirmed"; }
    commit_table "mix:${a}+${b}@${pct}%" "$ST/mix.bin"
    ;;

strength)
    name=${2:-}; pct=${3:-}
    valid_name "$name" || die "bad name"
    case "$pct" in ''|*[!0-9]*) die "usage: lut.sh strength <name> <0-100>" ;; esac
    [ "$pct" -le 100 ] || die "percent must be 0..100"
    need_tools
    [ -n "$MIX" ] && [ -x "$MIX" ] || die "missing lutmix.arm (looked in $TD and /mnt/mmc/lut)"
    # 0 端 = 原厂 A17（白点 206,207,240）。没有 dump 过就退到 identity，
    # 并在输出里说明——identity 是 255 白点，拉到 0% 会比平时更冷更亮。
    if [ -f "$LAB/_stock_A17.bin" ]; then
        base=$LAB/_stock_A17.bin
        base_label=stock
    else
        base=$ST/identity.bin
        if [ ! -s "$base" ]; then
            "$MIX" --identity "$base" > "$ST/identity.log" 2>&1 \
                || { cat "$ST/identity.log"; die "identity build failed"; }
        fi
        base_label=identity
        echo "WARN no _stock_A17.bin; 0% uses identity (colder/brighter than factory)"
        echo "HINT run: sh $0 stock"
    fi
    ta=$(table_of "$name") || die "cannot resolve: $name"
    $BB mkdir -p "$ST"
    perm=$((pct * 10))
    "$MIX" "$base" "$ta" "$perm" "$ST/mix.bin" > "$ST/mix.log" 2>&1 \
        || { cat "$ST/mix.log"; die "lutmix failed"; }
    $BB grep -q '=== done ===' "$ST/mix.log" || { cat "$ST/mix.log"; die "lutmix not confirmed"; }
    commit_table "strength:${name}@${pct}%($base_label)" "$ST/mix.bin"
    ;;

# 双 LUT 各自强度：两张表各有一个强度，但落到表上只有一步 ——
#   T = base + s * (mix(A,B,r) − base)        s = min(sa+sb, 100),  r = sb/(sa+sb)
# 这正是「归一加权」语义（docs/current/DUAL_STRENGTH_2026-11-02.md §2）：两张表
# 按比例混成一张，再整体按总强度施加。好处是任何组合都不会外推出 0..255，
# 且与 A/B 的顺序无关。两次 lutmix 调用，不需要新工具。
blend)
    a=${2:-}; ar=${3:-}; b=${4:-}; bs=${5:-}
    valid_name "$a" || die "bad A"
    valid_name "$b" || die "bad B"
    case "$ar" in ''|*[!0-9]*) die "usage: lut.sh blend <A> <r 0-100> <B> <s 0-100>" ;; esac
    case "$bs" in ''|*[!0-9]*) die "usage: lut.sh blend <A> <r 0-100> <B> <s 0-100>" ;; esac
    [ "$ar" -le 100 ] || die "r must be 0..100"
    [ "$bs" -le 100 ] || die "s must be 0..100"
    need_tools
    [ -n "$MIX" ] && [ -x "$MIX" ] || die "missing lutmix.arm (looked in $TD and /mnt/mmc/lut)"
    ta=$(table_of "$a") || die "cannot resolve A: $a"
    tb=$(table_of "$b") || die "cannot resolve B: $b"
    if [ -f "$LAB/_stock_A17.bin" ]; then
        base=$LAB/_stock_A17.bin
        base_label=stock
    else
        base=$ST/identity.bin
        base_label=identity
        if [ ! -s "$base" ]; then
            "$MIX" --identity "$base" > "$ST/identity.log" 2>&1 \
                || { cat "$ST/identity.log"; die "identity build failed"; }
        fi
        echo "WARN no _stock_A17.bin; 0 strength uses identity (colder/brighter than factory)"
        echo "HINT run: sh $0 stock"
    fi
    $BB mkdir -p "$ST"
    # 中间表放 /tmp（内存）：这是两次连续运算的临时产物，不该落到 exFAT 上。
    mid=/tmp/.lutblend.$$
    "$MIX" "$ta" "$tb" $((ar * 10)) "$mid" > "$ST/blend.log" 2>&1 \
        || { cat "$ST/blend.log"; $BB rm -f "$mid"; die "blend step1 (mix) failed"; }
    $BB grep -q '=== done ===' "$ST/blend.log" \
        || { cat "$ST/blend.log"; $BB rm -f "$mid"; die "blend step1 not confirmed"; }
    "$MIX" "$base" "$mid" $((bs * 10)) "$ST/mix.bin" > "$ST/blend.log" 2>&1 \
        || { cat "$ST/blend.log"; $BB rm -f "$mid"; die "blend step2 (strength) failed"; }
    $BB grep -q '=== done ===' "$ST/blend.log" \
        || { cat "$ST/blend.log"; $BB rm -f "$mid"; die "blend step2 not confirmed"; }
    $BB rm -f "$mid"
    commit_table "blend:${a}+${b} r=${ar}% s=${bs}%($base_label)" "$ST/mix.bin"
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
    table=$(table_of "$name") || die "not found: $name (.cube or .bin)"
    commit_table "$name" "$table"
    ;;

off)
    need_tools
    if [ ! -f "$ST/a18_orig.bin" ]; then
        echo "OK nothing to restore"
        exit 0
    fi
    rc=0
    # View4 四项写回原厂（[0]A12 [1]A13 [2]A14 [3]A17）
    "$REGT" view-restore > "$ST/off-view.log" 2>&1 || rc=1
    if [ -f "$STILLBAK" ]; then
        "$REGT" still-restore > "$ST/off-still.log" 2>&1 || rc=1
    fi
    if [ -f "$BVBAK" ]; then
        "$REGT" bv-restore > "$ST/off-bv.log" 2>&1 || rc=1
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
    oled_restore
    echo "OK restored (view=4 factory, still=BV12+Still6 factory, A18=original)"
    ;;

status)
    need_tools
    if [ -f "$ST/current" ]; then
        echo "ACTIVE $(cat "$ST/current")"
    else
        echo "IDLE"
    fi
    echo "BACKUP $([ -f "$ST/a18_orig.bin" ] && echo present || echo absent)"
    echo "STOCK  $([ -f "$LAB/_stock_A17.bin" ] && echo present || echo absent)"
    echo "LIB    $([ -f "$ORD" ] && $BB grep -c . "$ORD" 2>/dev/null || echo 0) entries, $([ -f "$ORD" ] && order_fav_count || echo 0) fav"
    "$REGT" status 2>/dev/null | $BB sed -n '2,4p'
    # 引擎实际指向哪个槽（0x2082b00c = 3DLUT 表指针）。
    # 注意：所有表都写在同一个槽 A18，所以指针恒为 A18，**不能**用它判断
    # "槽内容有没有被 p7 重新读入"——那要靠半按快门触发 View::_load。
    ENG=$($BB devmem 0x2082b00c 32 2>/dev/null | $BB tr 'A-F' 'a-f')
    if [ -n "$ENG" ]; then
        echo "ENGINE $ENG  (3DLUT 当前表指针)"
        echo "NOTE   apply 之后若没半按过快门，画面可能仍是上一张表"
    fi
    ;;

*)
    echo "usage: lut.sh list [--fav]|begin|apply <name>|off|status"
    echo "       lut.sh fav <name>|move <name> up|down|top|del <name>|index"
    echo "       lut.sh mix <A> <B> <0-100>|strength <name> <0-100>|stock"
    exit 2
    ;;
esac
