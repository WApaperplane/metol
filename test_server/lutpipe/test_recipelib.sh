#!/bin/bash
# test_recipelib.sh — 在 WSL 里用真脚本、真 JSON 验证配方库的机内增删排序。
#
# 关键判据不是「文件变了」，而是「export 出来的扁平表仍然可被 nxui 加载」：
# recipes.txt 的可用行数必须等于配方数，否则角色互换（回滚）。
#
# 用法（WSL）: sh test_recipelib.sh [repo_root]
set -u

REPO=${1:-/mnt/e/NXWA/nx500-modding-work}
D=/opt/usr/nx-ks
LAB=/mnt/mmc/filmlab
pass=0; fail=0
ok()   { pass=$((pass+1)); printf 'PASS %s\n' "$1"; }
bad()  { fail=$((fail+1)); printf 'FAIL %s  [%s]\n' "$1" "${2:-}"; }
check(){ if eval "$2"; then ok "$1"; else bad "$1" "${3:-}"; fi; }

if [ -d "$LAB" ] && [ ! -f "$LAB/.recipelib-test" ]; then
    echo "REFUSE: $LAB 里已有真实内容" >&2; exit 1
fi
rm -rf "$LAB"; mkdir -p "$LAB" "$D"
: > "$LAB/.recipelib-test"

cat > "$D/busybox" <<'EOF'
#!/bin/sh
if [ "$1" = sleep ]; then exit 0; fi
exec "$@"
EOF
chmod +x "$D/busybox"
cp "$REPO/scripts/filmlab.sh" "$D/filmlab.sh"
cp "$REPO/scripts/recipelib.sh" "$D/recipelib.sh"
cp "$REPO/scripts/filmlab/recipes.json" "$LAB/recipes.json"
sh "$D/filmlab.sh" export > /dev/null 2>&1 || { echo "export 预跑失败"; exit 1; }

L="sh $D/recipelib.sh"
total=$($L list | wc -l | tr -d ' ')
echo "库内配方 $total 条"

# ---- 1. 初始状态 ----
check "list 条数与 JSON 一致" '[ "$total" = 79 ]' "$total"
check "第一条是 portra400" '[ "$($L list | head -1)" = portra400 ]'
check "verify 通过" '$L verify | grep -qx OK'

# ---- 2. 排序 ----
$L move gold200 top > /dev/null
check "move top" '[ "$($L list | head -1)" = gold200 ]'
check "move 后条数不变" '[ "$($L list | wc -l | tr -d " ")" = "$total" ]'
check "move 后 recipes.txt 仍同步" '$L verify | grep -qx OK'
$L move gold200 down > /dev/null
check "move down" '[ "$($L list | sed -n 2p)" = gold200 ]'
$L move gold200 up > /dev/null
check "move up" '[ "$($L list | head -1)" = gold200 ]'
check "JSON 仍是合法结构（括号平衡）" '$L verify | grep -q "BRACES  {"'

# ---- 3. 删除 ----
before=$($L list | wc -l | tr -d ' ')
$L del tmp_nonexistent > /dev/null 2>&1
check "删不存在的键返回错误" '[ $? -ne 0 ]'
$L del _note > /dev/null 2>&1
check "拒绝删除内部键" '[ $? -ne 0 ]'
victim=$($L list | tail -1)
$L del "$victim" > /dev/null
check "删除后条数 -1" '[ "$($L list | wc -l | tr -d " ")" = "$((before - 1))" ]'
check "被删的键不在列表里" '! $L list | grep -qx "$victim"'
check "删除后 recipes.txt 仍同步" '$L verify | grep -qx OK'
check "删除前留了备份" '[ "$(ls "$LAB/_backup"/recipes-*.json | wc -l | tr -d " ")" -ge 1 ]'

# ---- 4. 顺序真的落在文件里（重开一次读同一份 JSON） ----
first=$($L list | head -1)
second=$($L list | sed -n 2p)
$L move "$first" down > /dev/null
check "落盘顺序：原第一变成第二" '[ "$($L list | sed -n 2p)" = "$first" ]'
check "原第二升到第一" '[ "$($L list | head -1)" = "$second" ]'

# ---- 5. 恢复 ----
bak=$(ls -r "$LAB/_backup"/recipes-*.json | head -1 | xargs -n1 basename)
$L restore "$bak" > /dev/null
check "restore 成功且 verify 通过" '$L verify | grep -qx OK'
$L restore ../etc/passwd > /dev/null 2>&1
check "拒绝路径穿越恢复" '[ $? -ne 0 ]'

# ---- 6. 通过 filmlab.sh 转发的入口 ----
check "filmlab.sh lib list 与直调一致" '[ "$(sh "$D/filmlab.sh" lib list | head -1)" = "$($L list | head -1)" ]'

# ---- 7. 备份上限 ----
i=0; while [ $i -lt 12 ]; do $L backup > /dev/null; i=$((i + 1)); done
nb=$(ls "$LAB/_backup"/recipes-*.json | wc -l | tr -d ' ')
check "备份只保留最近 10 份" '[ "$nb" -le 10 ]' "$nb"

rm -rf "$LAB"
printf '\n%d PASS / %d FAIL\n' "$pass" "$fail"
[ "$fail" = 0 ]
