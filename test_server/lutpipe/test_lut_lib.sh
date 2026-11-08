#!/bin/bash
# test_lut_lib.sh — 在 WSL 里跑真脚本、真路径，验证 lut.sh 的库管理与混合动词。
#
# 只搭一个假的机身树（/opt/usr/nx-ks + /mnt/mmc/looks），工具用 shell 桩：
# 库存/排序/缓存的逻辑全在 lut.sh 里，那才是被测对象；混合数学本身由
# test_lutmix.py 在 qemu 下逐字节验过。
#
# 用法（WSL）: bash test_lut_lib.sh [repo_root]
set -u

REPO=${1:-/mnt/e/NXWA/nx500-modding-work}
D=/opt/usr/nx-ks
LAB=/mnt/mmc/looks
ST=/mnt/mmc/lut/state
CV=$ST/cv
TRASH=$LAB/_trash
pass=0; fail=0

ok()   { pass=$((pass+1)); printf 'PASS %s\n' "$1"; }
bad()  { fail=$((fail+1)); printf 'FAIL %s\n' "$1"; }
check(){ if eval "$2"; then ok "$1"; else bad "$1  [${3:-}]"; fi; }

if [ -d "$LAB" ] && [ ! -f "$LAB/.lutlib-test" ]; then
    echo "REFUSE: $LAB 里已有真实内容，不做破坏性测试" >&2; exit 1
fi

rm -rf "$LAB" "$ST"; mkdir -p "$LAB" "$ST" "$D/lut" "$TRASH"
: > "$LAB/.lutlib-test"

# busybox 垫片：把 $BB applet 直接交给系统的同名命令
cat > "$D/busybox" <<'EOF'
#!/bin/sh
# Camera BusyBox -x is broken; do not let a host grep mask that dependency.
if [ "$1" = grep ] && [ "${2:-}" = -qx ]; then exit 1; fi
exec "$@"
EOF
chmod +x "$D/busybox"

# ---- 工具桩 ----
cat > "$D/lut/nx_slotwrite.arm" <<'EOF'
#!/bin/sh
case "$1" in
  read)    head -c 19712 /dev/zero > "$3"; echo 'SLOT dumped' ;;
  write)   cp "$3" "$NX_TEST_LAST_TABLE"; echo 'READBACK ok' ;;
  restore) echo 'READBACK ok' ;;
  *)       exit 9 ;;
esac
EOF
cat > "$D/lut/nx_regtabwrite.arm" <<'EOF'
#!/bin/sh
case "$1" in
  status) echo 'VIEW4'; echo 'STILL6'; echo 'BV12' ;;
  *)      echo 'READBACK ok' ;;
esac
EOF
cat > "$D/lut/cube2lut.arm" <<'EOF'
#!/bin/sh
# 桩：写一个可辨认的表，模拟 0.478 s 的转换
printf 'CONVERTED-FROM-%s' "$1" > "$2"
head -c 19712 /dev/zero >> "$2"
echo '=== done ==='
EOF
cat > "$D/lut/lutmix.arm" <<'EOF'
#!/bin/sh
if [ "$1" = "--identity" ]; then head -c 19712 /dev/zero > "$2"; echo '=== done ==='; exit 0; fi
printf 'MIX %s %s %s %s\n' "$1" "$2" "$3" "$4" >> /tmp/lutlib-mix.log
head -c 19712 /dev/zero > "$4"
echo '=== done ==='
EOF
# 秒切引擎桩：记录每次调用，可按 NX_TEST_KICK_FAIL 模拟失败
cat > "$D/lut/nx_lutload.arm" <<'EOF'
#!/bin/sh
printf '%s %s\n' "$1" "$2" >> /tmp/lutlib-kick.log
if [ "${NX_TEST_KICK_FAIL:-0}" = 1 ]; then
    echo 'REFUSE unsupported slot'
    exit 2
fi
echo 'OK DMA_RD_FINISH and processing mode verified'
EOF
chmod +x "$D"/lut/*.arm "$D/busybox"
cp "$REPO/scripts/lut.sh" "$D/lut.sh"
chmod +x "$D/lut.sh"

# ---- 库内容 ----
for n in zeta alpha beta gamma; do head -c 19712 /dev/zero > "$LAB/$n.bin"; done
printf 'LUT_3D_SIZE 2\n' > "$LAB/delta.cube"
head -c 19712 /dev/zero > "$LAB/_stock_A17.bin"     # 内部项：不进列表
L="sh $D/lut.sh"

# ---- 1. list 的默认顺序与隐藏规则 ----
out=$($L list)
check "list 按名字排序" '[ "$(echo "$out" | head -1)" = alpha ]' "$out"
check "list 隐藏 _ 开头" '! echo "$out" | grep -qx _stock_A17' "$out"
check "list 同名 .bin/.cube 只出现一次" '[ "$(echo "$out" | grep -c "^delta$")" = 1 ]' "$out"

# ---- 2. 收藏 ----
$L fav zeta >/dev/null
out=$($L list)
check "fav 排到最前" '[ "$(echo "$out" | head -1)" = zeta ]' "$out"
check "fav 写进 order 带星标" 'grep -qx "\*zeta" "$ST/order"'
check "list 不输出星标" 'echo "$out" | head -1 | grep -qv "\*"'
$L fav zeta >/dev/null
check "再 fav 一次取消收藏" '! grep -qx "\*zeta" "$ST/order"'
check "取消收藏后不跳位" '[ "$(echo "$($L list)" | head -1)" = zeta ]'

# ---- 3. 排序 ----
$L move beta top >/dev/null
check "move top" '[ "$($L list | head -1)" = beta ]'
$L move beta down >/dev/null
check "move down" '[ "$($L list | sed -n 2p)" = beta ]'
$L move beta up >/dev/null
check "move up" '[ "$($L list | head -1)" = beta ]'
$L move beta sideways >/dev/null 2>&1
check "非法方向不擅自动作" '[ "$($L list | head -1)" = beta ]'

# ---- 4. 下架 ----
$L del gamma >/dev/null
check "del 移到 _trash" '[ -f "$TRASH/gamma.bin" ]'
check "del 后原文件消失" '[ ! -f "$LAB/gamma.bin" ]'
check "del 后不在列表" '! $L list | grep -qx gamma'
check "del 后 order 里没有残留" '! grep -qx "gamma" "$ST/order"'
$L del nope >/dev/null 2>&1
check "del 不存在的名字返回错误" '[ $? -ne 0 ]'

# ---- 5. index 自愈 ----
head -c 19712 /dev/zero > "$LAB/omega.bin"       # 库外新增
$L index >/dev/null
check "index 收编新文件" '$L list | grep -qx omega'
rm -f "$LAB/omega.bin"
$L index >/dev/null
check "index 清掉已消失条目" '! $L list | grep -qx omega'

# ---- 6. test 与 .cube 转换缓存 ----
mv "$LAB/_stock_A17.bin" /tmp/lutlib-stock.bin
$L strength delta 40 > /tmp/lutlib-s1.log 2>&1
check "无 stock 时 strength 用 identity" 'grep -q "WARN no _stock_A17" /tmp/lutlib-s1.log'
check "identity 兜底表生成了" '[ -s "$ST/identity.bin" ]'
check "0 端标成 identity" 'grep -q "(identity)" "$ST/current"'
mv /tmp/lutlib-stock.bin "$LAB/_stock_A17.bin"
$L strength delta 40 > /dev/null 2>&1
check "有 stock 时 0 端用原厂表" 'grep -q "(stock)" "$ST/current"'
cp "$CV/delta.bin" /tmp/lutlib-cache1
$L strength delta 70 > /dev/null 2>&1
check "第二次不再重转（缓存文件未变）" 'cmp -s "$CV/delta.bin" /tmp/lutlib-cache1'
check "current 记录强度语义" 'grep -q "strength:delta@70%" "$ST/current"'

# ---- 7. 混合 ----
rm -f /tmp/lutlib-mix.log
$L mix alpha zeta 35 > /tmp/lutlib-m2.log 2>&1
check "mix 成功" '[ $? = 0 ]'
check "mix 传给引擎的是千分数" 'grep -q "350" /tmp/lutlib-mix.log'
check "mix 写进 current" 'grep -q "mix:alpha+zeta@35%" "$ST/current"'
$L mix alpha zeta 101 >/dev/null 2>&1
check "mix 拒绝 >100" '[ $? -ne 0 ]'
$L mix alpha zeta abc >/dev/null 2>&1
check "mix 拒绝非数字" '[ $? -ne 0 ]'

# ---- 7b. 双强度 blend：两步 lutmix，先 mix 出比例再 strength 出总强度 ----
rm -f /tmp/lutlib-mix.log
$L blend alpha 60 zeta 40 > /tmp/lutlib-b1.log 2>&1
check "blend 成功" '[ $? = 0 ]'
check "blend 调用了两次 lutmix" '[ "$(wc -l < /tmp/lutlib-mix.log)" = 2 ]'
# 这两条不能用 check：check 走 eval，$4 会在 eval 里被吃掉。直接 if。
if [ "$(sed -n 1p /tmp/lutlib-mix.log | awk '{print $4}')" = 600 ]; then
    ok "blend 第一步用比例千分数"
else
    bad "blend 第一步用比例千分数"
fi
if [ "$(sed -n 2p /tmp/lutlib-mix.log | awk '{print $4}')" = 400 ]; then
    ok "blend 第二步用总强度千分数"
else
    bad "blend 第二步用总强度千分数"
fi
check "blend 第二步的 0 端是原厂表" 'sed -n 2p /tmp/lutlib-mix.log | grep -q "_stock_A17"'
check "blend 写进 current" 'grep -q "blend:alpha+zeta r=60% s=40%" "$ST/current"'
check "blend 清掉了中间表" 'test ! -e /tmp/.lutblend.*'
$L blend alpha 60 zeta 101 >/dev/null 2>&1
check "blend 拒绝 s>100" '[ $? -ne 0 ]'
$L blend alpha 101 zeta 40 >/dev/null 2>&1
check "blend 拒绝 r>100" '[ $? -ne 0 ]'
$L blend alpha 60 >/dev/null 2>&1
check "blend 参数不全时拒绝" '[ $? -ne 0 ]'

# ---- 8. 非法名字 ----
$L del '../etc/passwd' >/dev/null 2>&1
check "拒绝路径穿越" '[ $? -ne 0 ]'
$L fav 'a|b' >/dev/null 2>&1
check "拒绝竖线" '[ $? -ne 0 ]'

# ---- 9. 正在使用的 look 被下架 ----
$L apply alpha >/dev/null 2>&1
$L del alpha >/dev/null 2>&1
check "下架当前 look 时自动还原" '[ ! -f "$ST/current" ]'

# ---- 10. 整库替换与空库（旧 order 没有任何存活条目） ----
for f in "$LAB"/*.bin "$LAB"/*.cube; do rm -f "$f"; done
head -c 19712 /dev/zero > "$LAB/replacement.bin"
check "整库替换仍收编新条目" '[ "$($L list)" = replacement ]'
rm -f "$LAB/replacement.bin"
check "空库清掉旧 order" '[ -z "$($L list)" ] && [ ! -s "$ST/order" ]'
head -c 19712 /dev/zero > "$LAB/reborn.bin"
check "清空后再加入可见" '[ "$($L list)" = reborn ]'

# ---- 11. 秒切：apply/off 自己触发 Load，不再要求半按快门 ----
rm -f /tmp/lutlib-kick.log
$L apply reborn > /tmp/lutlib-k1.log 2>&1
check "apply 调用了 nx_lutload" '[ "$(wc -l < /tmp/lutlib-kick.log 2>/dev/null)" = 1 ]' "$(cat /tmp/lutlib-kick.log 2>/dev/null)"
check "kick 的动词是 once" 'grep -q "^once " /tmp/lutlib-kick.log'
check "kick 的目标是工作槽 A18" 'grep -q "^once 0x81119F00$" /tmp/lutlib-kick.log'
check "apply 输出秒切成功" 'grep -q "OK instant switch" /tmp/lutlib-k1.log'

rm -f /tmp/lutlib-kick.log
LUT_NOKICK=1 $L apply reborn > /tmp/lutlib-k2.log 2>&1
check "LUT_NOKICK=1 时不调用 nx_lutload" '[ ! -s /tmp/lutlib-kick.log ]'
check "禁用秒切时提示半按" 'grep -q "half-press once" /tmp/lutlib-k2.log'

rm -f /tmp/lutlib-kick.log
NX_TEST_KICK_FAIL=1 $L apply reborn > /tmp/lutlib-k3.log 2>&1
check "kick 失败仍算 apply 成功" 'grep -q "OK applied" /tmp/lutlib-k3.log'
check "kick 失败给出后备提示" 'grep -q "WARN instant switch failed" /tmp/lutlib-k3.log'
check "kick 失败时不谎报秒切" '! grep -q "OK instant switch" /tmp/lutlib-k3.log'

rm -rf "$LAB" "$ST" /tmp/lutlib-*.log /tmp/lutlib-cache1
printf '\n%d PASS / %d FAIL\n' "$pass" "$fail"
[ "$fail" = 0 ]
