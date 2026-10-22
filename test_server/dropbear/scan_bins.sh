#!/bin/bash
# scan_bins.sh —— 三个构建的静态指标横评（-O0 / -O2 / -O2+armv7a）
set -uo pipefail
R=/mnt/e/NXWA/nx500-modding-work/test_server/dropbear
T=/tmp/sc
mkdir -p "$T"
printf '%-22s %9s %8s %7s %7s %7s %7s\n' "构建" "size" "insns" "VFP" "ldrd" "movw" "glibc"
for pair in "out:-O0" "out-O2:-O2" "out-test:-O2+armv7a"; do
    d=${pair%%:*}; tag=${pair##*:}
    b="$R/$d/dropbear.arm"
    [ -f "$b" ] || { printf '%-22s %s\n' "$tag" "缺失"; continue; }
    arm-linux-gnueabi-objdump -d "$b" > "$T/d.txt" 2>/dev/null
    sz=$(stat -c %s "$b")
    ins=$(grep -cE '^ +[0-9a-f]+:' "$T/d.txt")
    vfp=$(grep -cE '^ +[0-9a-f]+: +[0-9a-f ]+v[a-z]' "$T/d.txt")
    ldrd=$(grep -cE '\b(ldrd|strd)\b' "$T/d.txt")
    movw=$(grep -cE '\b(movw|movt)\b' "$T/d.txt")
    gv=$(arm-linux-gnueabi-readelf -V "$b" | grep -oE 'GLIBC_[0-9.]+' | sort -u -V | tr '\n' ',' )
    printf '%-22s %9s %8s %7s %7s %7s %7s\n' "$tag" "$sz" "$ins" "$vfp" "$ldrd" "$movw" "$gv"
done
echo
echo "=== VFP/NEON 明细（应为空）==="
grep -E '^ +[0-9a-f]+: +[0-9a-f ]+v[a-z]' "$T/d.txt" | head -5
echo "(以上若为空 = 无硬件浮点指令)"
