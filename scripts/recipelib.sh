#!/bin/sh
# @gate script=recipelib.sh opens=rwdirect one_shot=0 gate=none pconly=0
#=====================================================================
# recipelib.sh — FilmLab 配方库的机内增删与排序（recipes.json 块级手术）
#=====================================================================
# 为什么不维护一份「顺序表」：配方的唯一真相是 recipes.json。多一层
# order 文件就多一个会与 JSON 不一致的状态，而面板读的 recipes.txt 又
# 是从 JSON 生成的——三份状态迟早对不上。这里直接对 JSON 做块级重排，
# 顺序就是文件里的顺序。
#
# 安全约定：
#   · 每次写之前先备份到 _backup/（保留最近 10 份），出错一律从备份回滚
#   · 写入是 .tmp → mv（同卷 rename），断电不会留下半截 JSON
#   · 改完立刻重新 export，recipes.txt 与 JSON 同步；export 解析出的条目数
#     必须等于预期，否则回滚（这一步是真正的格式校验，比数括号可靠）
#   · 删除是物理删除（配方不是二进制表，可从 git / 备份恢复）；写盘前
#     面板会做二次确认
#
# 用法：
#   recipelib.sh list                 按文件顺序列出 key
#   recipelib.sh move <key> up|down|top
#   recipelib.sh del <key>
#   recipelib.sh verify               结构体检（条目数 / 花括号 / recipes.txt）
#   recipelib.sh backup               手动备份一份
#   recipelib.sh restore <backup>     从备份恢复（只接受 _backup/ 下的文件名）
#=====================================================================
set -u

D=/opt/usr/nx-ks
BB=$D/busybox
LAB=/mnt/mmc/filmlab
RECIPE=$LAB/recipes.json
TXT=$LAB/recipes.txt
BAKDIR=$LAB/_backup
KEEP=10
ENGINE=$D/filmlab.sh

die() { echo "ERR $*"; exit 1; }

# 与面板同口径：'_' 开头是内部键（_note），不允许外部增删
valid_key() {
    case "$1" in
        ''|_*) return 1 ;;
        */*|*\\*|*..*|*'|'*|*';'*|*'$'*|*'`'*|*'"'*) return 1 ;;
    esac
    return 0
}

[ -f "$RECIPE" ] || die "no $RECIPE"

# ---- 块级手术 ----
# IN: JSON 全文；OUT: 重排/删块后的 JSON
# act=list 只输出块 key（按文件顺序），不改文件
surgery() {
    act=${1:-list}; want=${2:-}; dir=${3:-}
    $BB awk -v act="$act" -v want="$want" -v dir="$dir" '
        function ltrim(s) { sub(/^[ \t]+/, "", s); return s }
        { line[NR] = $0 }
        END {
            # 1. 定位 recipes 段（到 presets 之前）
            rstart = 0; rend = 0
            for (i = 1; i <= NR; i++) {
                if (rstart == 0 && line[i] ~ /"recipes"[ \t]*:/) { rstart = i; continue }
                if (rstart > 0 && line[i] ~ /"presets"[ \t]*:/) { rend = i; break }
            }
            if (rstart == 0) { print "ERR: no recipes section" > "/dev/stderr"; exit 3 }
            if (rend == 0) rend = NR + 1

            # 2. 收集块：[起始行, 结束行]
            nb = 0; inb = 0
            for (i = rstart + 1; i < rend; i++) {
                if (!inb && line[i] ~ /^[ \t]*"[^"]*"[ \t]*:[ \t]*\{[ \t]*$/) {
                    k = line[i]; sub(/^[ \t]*"/, "", k); sub(/".*$/, "", k)
                    nb++; bk[nb] = k; bs[nb] = i; be[nb] = i; inb = 1; continue
                }
                if (inb) {
                    be[nb] = i
                    if (line[i] ~ /^[ \t]*\}[ \t]*,?[ \t]*$/) inb = 0
                }
            }
            if (nb == 0) { print "ERR: no recipe blocks" > "/dev/stderr"; exit 3 }
            if (inb) { print "ERR: unterminated block " bk[nb] > "/dev/stderr"; exit 3 }

            maxbe = be[1]
            for (i = 2; i <= nb; i++) if (be[i] > maxbe) maxbe = be[i]

            if (act == "list") {
                for (i = 1; i <= nb; i++) if (bk[i] !~ /^_/) print bk[i]
                exit 0
            }
            if (act == "count") { print nb; exit 0 }

            # 3. 目标位置
            pos = 0
            for (i = 1; i <= nb; i++) if (bk[i] == want) { pos = i; break }
            if (pos == 0) { print "ERR: no such recipe: " want > "/dev/stderr"; exit 4 }

            for (i = 1; i <= nb; i++) perm[i] = i
            if (act == "del") {
                # 删除：把 pos 挪到末尾之外
                for (i = pos; i < nb; i++) perm[i] = i + 1
                nb--
            } else if (act == "move") {
                # perm[] 是「输出第 i 位取原第几个块」
                if (dir == "top" && pos > 1) {
                    perm[1] = pos
                    for (i = 2; i <= pos; i++) perm[i] = i - 1
                } else if (dir == "up" && pos > 1) {
                    perm[pos] = pos - 1; perm[pos - 1] = pos
                } else if (dir == "down" && pos < nb) {
                    perm[pos] = pos + 1; perm[pos + 1] = pos
                }
            }

            # 4. 输出：头 / 块前区 / 块 / 块后区 / 尾
            for (i = 1; i <= rstart; i++) print line[i]
            for (i = rstart + 1; i < bs[1]; i++) print line[i]
            for (p = 1; p <= nb; p++) {
                b = perm[p]
                for (j = bs[b]; j <= be[b]; j++) {
                    s = line[j]
                    if (j == be[b]) {
                        sub(/,[ \t]*$/, "", s)          # 统一去掉尾逗号
                        if (p < nb) s = s ","          # 统一补，最后一块不补
                    }
                    print s
                }
            }
            for (i = maxbe + 1; i < rend; i++) print line[i]   # 段收尾（含 "}," ）
            for (i = rend; i <= NR; i++) print line[i]
        }
    ' "$RECIPE"
}

# ---- 备份 ----
backup_now() {
    $BB mkdir -p "$BAKDIR"
    ts=$($BB date +%Y%m%d-%H%M%S 2>/dev/null || echo manual)
    seq=0
    for existing in "$BAKDIR/recipes-$ts-"*.json; do
        [ -f "$existing" ] || continue
        n=${existing##*-}; n=${n%.json}
        n=$(printf '%s' "$n" | $BB sed 's/^0*//')
        case "$n" in *[!0-9]*) continue ;; esac
        [ "${n:-0}" -lt "$seq" ] || seq=$((${n:-0} + 1))
    done
    suffix=$(printf '%06d' "$seq")
    dest=$BAKDIR/recipes-$ts-$suffix.json
    cp "$RECIPE" "$dest" || die "backup failed"
    # 只留最近 KEEP 份
    n=0
    for f in $($BB ls -r "$BAKDIR"/recipes-*.json 2>/dev/null); do
        n=$((n + 1))
        [ $n -gt $KEEP ] && $BB rm -f "$f"
    done
    echo "$dest"
}

# 条目数：走同一个块解析器。别用 grep 数 `"key": {` —— 那会把
# `"recipes": {` 和 `"presets": {` 也算进去（79 → 81 的实测坑）。
count_keys() {
    v=$(surgery count 2>/dev/null | $BB head -1 | $BB tr -d ' ')
    case "$v" in ''|*[!0-9]*) echo 0 ;; *) echo "$v" ;; esac
}

re_export() {
    [ -x "$ENGINE" ] || return 0
    sh "$ENGINE" export > /tmp/recipelib-export.log 2>&1 || return 1
    return 0
}

# 写入 + 校验 + 失败回滚。$1 = 候选文件，$2 = 期望条目数
commit() {
    cand=$1; expect=$2
    bak=$3
    cp "$cand" "$RECIPE.tmp" || die "cannot stage"
    # # exFAT 不覆盖式 rename：旧目录项会留在原地（2026-11-14 机上实测，每次 +1）
    $BB rm -f "$RECIPE" 2>/dev/null
    $BB mv -f "$RECIPE.tmp" "$RECIPE" || die "cannot replace $RECIPE"
    got=$(count_keys)
    if [ "$got" != "$expect" ]; then
        cp "$bak" "$RECIPE"
        re_export
        die "count mismatch after write: $got != $expect (rolled back)"
    fi
    if ! re_export; then
        cp "$bak" "$RECIPE"; re_export
        die "export failed (rolled back to $bak)"
    fi
    # export 出的扁平表行数必须等于配方数 —— 这才是真正的格式判据
    if [ -s "$TXT" ]; then
        lines=$($BB grep -c . "$TXT" 2>/dev/null | $BB tr -d ' ')
        # recipes.txt 头部有注释行，只数配方行（key|label|...）
        rows=$($BB awk -F'|' 'NF>=9 && $2 != "" {n++} END{print n+0}' "$TXT")
        if [ "$rows" != "$expect" ]; then
            cp "$bak" "$RECIPE"; re_export
            die "recipes.txt has $rows usable rows, expected $expect (rolled back)"
        fi
    fi
    return 0
}

case "${1:-list}" in
list)
    surgery list
    ;;

move)
    key=${2:-}; dir=${3:-up}
    valid_key "$key" || die "bad key"
    case "$dir" in up|down|top) ;; *) die "usage: recipelib.sh move <key> up|down|top" ;; esac
    before=$(count_keys)
    bak=$(backup_now)
    cand=$BAKDIR/.cand
    surgery move "$key" "$dir" > "$cand" || { $BB rm -f "$cand"; die "surgery failed"; }
    commit "$cand" "$before" "$bak"
    $BB rm -f "$cand"
    echo "OK moved $key $dir"
    ;;

del)
    key=${2:-}
    valid_key "$key" || die "bad key"
    before=$(count_keys)
    bak=$(backup_now)
    cand=$BAKDIR/.cand
    surgery del "$key" > "$cand" || { $BB rm -f "$cand"; die "surgery failed"; }
    commit "$cand" "$((before - 1))" "$bak"
    $BB rm -f "$cand"
    echo "OK deleted $key (backup: $bak)"
    ;;

verify)
    n=$(count_keys)
    open=$($BB grep -o '{' "$RECIPE" | $BB wc -l | $BB tr -d ' ')
    close=$($BB grep -o '}' "$RECIPE" | $BB wc -l | $BB tr -d ' ')
    echo "RECIPES $n"
    echo "BRACES  { $open  } $close"
    if [ "$open" != "$close" ]; then echo "ERR unbalanced braces"; exit 1; fi
    if [ -s "$TXT" ]; then
        rows=$($BB awk -F'|' 'NF>=9 && $2 != "" {n++} END{print n+0}' "$TXT")
        echo "TXT     $rows rows"
        [ "$rows" = "$n" ] || { echo "ERR recipes.txt out of sync (run: filmlab.sh export)"; exit 1; }
    fi
    echo "OK"
    ;;

backup)
    echo "OK $(backup_now)"
    ;;

restore)
    f=${2:-}
    [ -n "$f" ] || die "usage: recipelib.sh restore <recipes-YYYYmmdd-HHMMSS.json>"
    case "$f" in */*|*..*) die "只有 _backup/ 下的文件名可以恢复" ;; esac
    [ -f "$BAKDIR/$f" ] || die "not found: $BAKDIR/$f"
    # Stage before backup pruning; the selected snapshot may be the oldest.
    cand=$BAKDIR/.restore
    cp "$BAKDIR/$f" "$cand" || die "cannot stage restore"
    expect=$(RECIPE="$cand"; count_keys)
    [ "$expect" -gt 0 ] || die "invalid restore snapshot"
    cur=$(backup_now)
    commit "$cand" "$expect" "$cur"
    $BB rm -f "$cand"
    echo "OK restored $f (previous state kept at $cur)"
    ;;

*)
    echo "usage: recipelib.sh list|move <key> up|down|top|del <key>|verify|backup|restore <file>"
    exit 2
    ;;
esac
