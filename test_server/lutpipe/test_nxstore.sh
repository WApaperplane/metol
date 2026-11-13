#!/bin/bash
# test_nxstore.sh — nxstore.sh 存储层的回归测试（在 WSL/桌面 Linux 上跑）
#
# 这一层是 2026-11-13 存储解耦的地基：lut.sh / filmlab.sh / nxui.sh 全靠它
# 把「易失状态」和「持久状态」分开，并且保证落盘是 tmp→sync→校验→rename。
# 之前只在现场用临时脚本验过一次，仓库里没有回归 —— 改一行就可能把
# 「原子替换」悄悄退化成裸 mv，而现场只有 exFAT 掉电时才会发现。
#
# 用法（WSL）: bash test_nxstore.sh [repo_root]
set -u

REPO=${1:-/mnt/e/NXWA/nx500-modding-work}
LIB=$REPO/scripts/nxstore.sh
T=$(mktemp -d /tmp/nxstore-test.XXXXXX)
pass=0; fail=0

ok()   { pass=$((pass+1)); printf 'PASS %s\n' "$1"; }
bad()  { fail=$((fail+1)); printf 'FAIL %s\n' "$1"; }
check(){ if eval "$2"; then ok "$1"; else bad "$1  [${3:-}]"; fi; }

cleanup() { chmod -R u+w "$T" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT

[ -f "$LIB" ] || { echo "REFUSE: 找不到 $LIB" >&2; exit 1; }

# busybox 垫片：真机用 $D/busybox，这里让 applet 直接落到宿主同名命令。
# 注意不要用宿主 grep 顶替相机 busybox 的 -qx 缺陷 —— nxstore 不依赖 grep -x。
SHIM=$T/busybox
cat > "$SHIM" <<'EOF'
#!/bin/sh
exec "$@"
EOF
chmod +x "$SHIM"

export NX_RAM=$T/ram
export NX_SD=$T/sd
export NX_BB=$SHIM
unset NXSTORE_LOADED NX_TRACE NX_LOG_MAX

# ---- 1. 自我保护 ----
"$SHIM" sh "$LIB" >/dev/null 2>&1; rc=$?
check "被直接执行时拒绝（exit 2）" '[ "$rc" = 2 ]' "rc=$rc"

export NX_RAM NX_SD NX_BB
# shellcheck disable=SC1090
. "$LIB"
check "source 后 NXSTORE_LOADED=1" '[ "${NXSTORE_LOADED:-}" = 1 ]'
. "$LIB"        # 二次 source 必须幂等（set -u 下重复定义会炸）
check "重复 source 幂等" '[ "$(nx_ram x)" = "$NX_RAM/x" ]'

# ---- 2. 路径 ----
mkdir -p "$NX_RAM" "$NX_SD"
check "nx_ram 建目录并回显" '[ "$(nx_ram lut)" = "$NX_RAM/lut" ] && [ -d "$NX_RAM/lut" ]'
check "nx_ram 默认子目录" '[ "$(nx_ram)" = "$NX_RAM/state" ]'
check "nx_sd 建目录无尾斜杠" '[ "$(nx_sd looks)" = "$NX_SD/looks" ] && [ -d "$NX_SD/looks" ]'

# ---- 3. nx_put：原子替换 ----
printf 'AAAA' > "$T/src1"
nx_put "$T/src1" "$T/dst/deep/1.bin"; rc=$?
check "nx_put 正常返回 0" '[ "$rc" = 0 ]' "rc=$rc"
check "nx_put 自动建父目录" '[ -f "$T/dst/deep/1.bin" ]'
check "nx_put 内容一致" '[ "$(cat "$T/dst/deep/1.bin")" = AAAA ]'
check "nx_put 不留 .tmp" '[ -z "$(find "$T/dst" -name "*.tmp")" ]'

printf 'BBBB' > "$T/dst/deep/2.bin"
nx_put "$T/nonexist" "$T/dst/deep/2.bin"; rc=$?
check "源不存在时返回 1" '[ "$rc" = 1 ]'
check "源不存在时不碰目标" '[ "$(cat "$T/dst/deep/2.bin")" = BBBB ]'

: > "$T/empty"
nx_put "$T/empty" "$T/dst/deep/2.bin"; rc=$?
check "拒绝写 0 字节（最关键的一条）" '[ "$rc" = 1 ]' "rc=$rc"
check "0 字节源不破坏旧目标" '[ "$(cat "$T/dst/deep/2.bin")" = BBBB ]'
check "0 字节源不留 .tmp" '[ ! -e "$T/dst/deep/2.bin.tmp" ]'

# 写失败（目标目录不可写）必须保留旧文件
if [ "$(id -u)" != 0 ]; then
    mkdir -p "$T/ro"; printf 'OLD' > "$T/ro/f"; chmod a-w "$T/ro"
    nx_put "$T/src1" "$T/ro/f" >/dev/null 2>&1; rc=$?
    check "目标不可写时返回 1" '[ "$rc" = 1 ]' "rc=$rc"
    check "目标不可写时旧内容存活" '[ "$(cat "$T/ro/f")" = OLD ]'
    chmod u+w "$T/ro"
else
    echo "SKIP 目标不可写用例（root 身份下 chmod 拦不住）"
fi

# ---- 4. nx_put_str：内容不变零写入 ----
nx_put_str "hello" "$T/sd/v.idx"; rc=$?
check "nx_put_str 首次写入" '[ "$rc" = 0 ] && [ "$(cat "$T/sd/v.idx")" = hello ]'
mt1=$(stat -c %y "$T/sd/v.idx" 2>/dev/null)
NX_TRACE=1 nx_put_str "hello" "$T/sd/v.idx" 2>"$T/trace1"
check "内容相同不产生写入（NX_TRACE 无 NXPUT）" '! grep -q NXPUT "$T/trace1"'
check "内容相同 mtime 不变" '[ "$(stat -c %y "$T/sd/v.idx" 2>/dev/null)" = "$mt1" ]'
NX_TRACE=1 nx_put_str "world" "$T/sd/v.idx" 2>"$T/trace2"
check "内容变化才写，且留痕" '[ "$(cat "$T/sd/v.idx")" = world ] && grep -q NXPUT "$T/trace2"'

# ---- 5. nx_get_str ----
check "nx_get_str 读回" '[ "$(nx_get_str dflt "$T/sd/v.idx")" = world ]'
check "nx_get_str 缺失时给默认值" '[ "$(nx_get_str dflt "$T/sd/none")" = dflt ]'

# ---- 6. nx_log：单文件追加 + 轮转 ----
NX_LOG_MAX=2048
for i in $(seq 1 60); do nx_log t "line-$i-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"; done
sz=$(wc -c < "$NX_RAM/log/t.log")
check "日志轮转后不超过上限的 1.5 倍" '[ "$sz" -le 3072 ]' "size=$sz"
check "日志保留最新一行" 'tail -1 "$NX_RAM/log/t.log" | grep -q "line-60"'
check "日志不产生同名副本" '[ "$(ls "$NX_RAM/log" | grep -c .)" = 1 ]' "$(ls "$NX_RAM/log")"
nx_log "nochannel-here"
check "无频道参数落 main.log" 'grep -q "nochannel-here" "$NX_RAM/log/main.log"'

# ---- 7. 失败取证 ----
mkdir -p "$NX_RAM/log"
printf 'boom\n' > "$NX_RAM/log/fail.log"
nx_log_persist fail; rc=$?
check "nx_log_persist 落 SD" '[ "$rc" = 0 ] && [ -f "$NX_SD/nx-failure/fail.log" ]'

# ---- 8. 易失状态 ----
check "nx_st_get 默认值" '[ "$(nx_st_get k d0)" = d0 ]'
nx_st_set k v1
check "nx_st_set/get 往返" '[ "$(nx_st_get k)" = v1 ]'
nx_st_set k ""
check "nx_st_set 空值" '[ "$(nx_st_get k X)" = "" ]'
nx_st_set "" v >/dev/null 2>&1; rc=$?
check "空 key 拒绝" '[ "$rc" = 1 ]'

# ---- 9. 覆盖写的实现约束（exFAT 实测结论，见 nx_swap 注释）----
# 这台相机的 exFAT 在 rename 到已存在名字时**不替换旧目录项**，每次写留一具尸体
# （机上对照实验：mv -f 覆盖 10 次 → 11 个同名项）。WSL 的 ext4 复现不了这个，
# 所以这里只锁实现形状：必须 rm 在前、mv 在后，且 nx_put 两个函数都走 nx_swap。
check "nx_swap 已定义" 'command -v nx_swap >/dev/null 2>&1'
sw=$(sed -n '/^nx_swap()/,/^}/p' "$LIB")
check "nx_swap 先 rm 目标" 'echo "$sw" | grep -q "rm -f \"\$_nx_dst\""'
r_lno=$(printf '%s\n' "$sw" | grep -n 'rm -f "\$_nx_dst"' | cut -d: -f1)
m_lno=$(printf '%s\n' "$sw" | grep -n 'mv -f "\$_nx_src"' | cut -d: -f1)
check "nx_swap 再 mv（rm 在 mv 之前）" \
      '[ -n "$r_lno" ] && [ -n "$m_lno" ] && [ "$r_lno" -lt "$m_lno" ]' "rm=$r_lno mv=$m_lno"
check "nx_put 走 nx_swap 而不是裸 mv" 'sed -n "/^nx_put()/,/^}/p" "$LIB" | grep -q "nx_swap"'
check "nx_put_str 走 nx_swap" 'sed -n "/^nx_put_str()/,/^}/p" "$LIB" | grep -q "nx_swap"'

printf '\n%d PASS / %d FAIL\n' "$pass" "$fail"
[ "$fail" = 0 ]
