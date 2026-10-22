#!/bin/bash
# analyze_opt.sh —— 静态对比 -O0 / -O2（不刷机、不上机，纯编译产物分析）
#   1) 热点算法文件：两个级别各编一次，数指令条数 → 证明收益来源
#   2) 全量 -O2 产物：扫危险指令（VFP/NEON、ldrd/strd）+ GLIBC 版本需求 → 证明安全性
set -uo pipefail
ROOT=/mnt/e/NXWA/nx500-modding-work/test_server/dropbear
SYS=$ROOT/dl/sysroot-g213
GCCINC=$(arm-linux-gnueabi-gcc -print-file-name=include)
SRC=/tmp/dropbear-build          # build_dropbear.sh 留下的源码树
TMP=/tmp/optan
mkdir -p "$TMP"

EXTRA=${1:-}
CF="-nostdinc -isystem $SYS/usr/include -isystem $SYS/usr/include/arm-linux-gnueabi \
 -isystem $GCCINC -U_TIME_BITS -D_TIME_BITS=32 \
 -U_FILE_OFFSET_BITS -D_FILE_OFFSET_BITS=32 -mfloat-abi=soft -fno-pic -fno-stack-protector $EXTRA"

echo "===== 1. 热点算法：指令条数 -O0 vs -O2 ====="
printf '%-42s %8s %8s %7s\n' "文件" "-O0" "-O2" "缩减"
total0=0; total2=0
for f in \
    libtomcrypt/src/ciphers/chacha20.c \
    libtomcrypt/src/mac/poly1305/poly1305.c \
    libtomcrypt/src/hashes/sha2/sha256.c \
    libtomcrypt/src/ciphers/aes/aes.c \
    libtommath/bn_mp_mul.c \
    src/packet.c \
    src/svr-chansession.c \
    src/common-channel.c ; do
    [ -f "$SRC/$f" ] || continue
    n0=$(arm-linux-gnueabi-gcc -O0 $CF -I"$SRC" -I"$SRC/src" -I"$SRC/libtomcrypt/src/headers" -I"$SRC/libtommath" -DHAVE_CONFIG_H -c "$SRC/$f" -o "$TMP/a.o" 2>/dev/null && \
         arm-linux-gnueabi-objdump -d "$TMP/a.o" | grep -cE '^ +[0-9a-f]+:' || echo 0)
    n2=$(arm-linux-gnueabi-gcc -O2 $CF -I"$SRC" -I"$SRC/src" -I"$SRC/libtomcrypt/src/headers" -I"$SRC/libtommath" -DHAVE_CONFIG_H -c "$SRC/$f" -o "$TMP/b.o" 2>/dev/null && \
         arm-linux-gnueabi-objdump -d "$TMP/b.o" | grep -cE '^ +[0-9a-f]+:' || echo 0)
    if [ "$n0" -gt 0 ]; then
        pct=$(( (n0 - n2) * 100 / n0 ))
        printf '%-42s %8s %8s %6s%%\n' "$(basename $f)" "$n0" "$n2" "$pct"
        total0=$((total0+n0)); total2=$((total2+n2))
    fi
done
[ "$total0" -gt 0 ] && printf '%-42s %8s %8s %6s%%\n' "合计" "$total0" "$total2" "$(( (total0-total2)*100/total0 ))"

echo
echo "===== 2. -O2 全量产物：危险指令扫描 ====="
for bin in "$ROOT/out-O2/dropbear.arm" "$ROOT/out/dropbear.arm"; do
    [ -f "$bin" ] || { echo "$(basename $(dirname $bin)): 缺失"; continue; }
    echo "--- $(dirname $bin | xargs basename) ---"
    ls -l "$bin" | awk '{printf "  size      : %s bytes\n", $5}'
    arm-linux-gnueabi-objdump -d "$bin" > "$TMP/dis.txt" 2>/dev/null
    vfp=$(grep -cE '^\s+[0-9a-f]+:\s+[0-9a-f]+\s+v[a-z]' "$TMP/dis.txt")
    ldrd=$(grep -cE '\b(ldrd|strd|ldrex|strex)\b' "$TMP/dis.txt")
    # ARM 有自己的 ldrd，Thumb2 也有；分开数
    insn=$(grep -cE '^\s+[0-9a-f]+:' "$TMP/dis.txt")
    printf "  insns     : %s\n" "$insn"
    printf "  VFP/NEON  : %s  (%s)\n" "$vfp" "$([ "$vfp" = 0 ] && echo 无硬件浮点指令 || echo '⚠ 出现硬件浮点')"
    printf "  ldrd/strd : %s  (%s)\n" "$ldrd" "$([ "$ldrd" = 0 ] && echo 无未对齐风险 || echo '注意：8字节访问需对齐')"
    printf "  glibc ver : %s\n" "$(arm-linux-gnueabi-readelf -V "$bin" | grep -oE 'GLIBC_[0-9.]+' | sort -u -V | tr '\n' ' ')"
    printf "  NEEDED    : %s\n" "$(arm-linux-gnueabi-readelf -d "$bin" | grep NEEDED | sed 's/.*\[//;s/\]//' | tr '\n' ' ')"
done

echo
echo "===== 3. 编译器默认 -mfpu（决定 NEON 能否被自动向量化用到）====="
arm-linux-gnueabi-gcc -Q --help=target 2>/dev/null | grep -E '^\s+-m(fpu|float-abi|arch|thumb)' | head -6
