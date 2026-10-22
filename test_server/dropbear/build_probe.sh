#!/bin/bash
# build_probe.sh —— 用「相机 ABI」编译 abi_probe.c
# 关键：用 glibc 2.13 的 sysroot（头文件 + crt1.o）配相机自带 libc-2.13.so，
#       否则宿主 crt1.o 会引入 GLIBC_2.34 需求、宿主 stat.h 不会生成 __xstat 重定向。
# 运行：wsl -d NXKS2 bash /mnt/e/NXWA/nx500-modding-work/test_server/dropbear/build_probe.sh
set -uo pipefail
cd "$(dirname "$0")"

SYS=/mnt/e/NXWA/nx500-modding-work/test_server/dropbear/dl/sysroot-g213
RF=/opt/nxks2/rootfs-112
GCCINC=$(arm-linux-gnueabi-gcc -print-file-name=include)
LIBDIR=$SYS/usr/lib/arm-linux-gnueabi
mkdir -p out

CC=arm-linux-gnueabi-gcc
CFLAGS=(-O0 -std=gnu99
    -nostdinc
    -isystem "$SYS/usr/include"
    -isystem "$SYS/usr/include/arm-linux-gnueabi"
    -isystem "$GCCINC"
    -U_TIME_BITS -D_TIME_BITS=32
    -U_FILE_OFFSET_BITS -D_FILE_OFFSET_BITS=32
    -mfloat-abi=soft -fno-pic -fno-stack-protector)

echo "== compile+link =="
$CC "${CFLAGS[@]}" \
    -nostartfiles -no-pie \
    -Wl,--dynamic-linker=/lib/ld-linux.so.3 \
    -Wl,--allow-shlib-undefined \
    -Wl,-rpath-link,"$RF/lib" -Wl,-rpath-link,"$RF/usr/lib" \
    "$LIBDIR/crt1.o" "$LIBDIR/crti.o" \
    abi_probe.c \
    -Wl,--start-group \
    "$RF/lib/libc-2.13.so" \
    "$LIBDIR/libc_nonshared.a" \
    "$RF/lib/libutil.so.1" \
    "$RF/lib/libcrypt.so.1" \
    "$RF/lib/libpthread.so.0" \
    "$RF/lib/librt.so.1" \
    -Wl,--end-group \
    -lgcc "$LIBDIR/crtn.o" \
    -o out/abi_probe.arm || { echo "LINK FAILED"; exit 1; }

echo "== size =="
ls -lh out/abi_probe.arm
echo "== NEEDED =="
arm-linux-gnueabi-readelf -d out/abi_probe.arm | grep -E 'NEEDED|RPATH|RUNPATH'
echo "== glibc 版本需求（必须都 <= 2.13）=="
arm-linux-gnueabi-readelf -V out/abi_probe.arm | grep -oE 'GLIBC_[0-9.]+' | sort -u -V
echo "== 未解析符号 =="
arm-linux-gnueabi-readelf -sW out/abi_probe.arm | awk '$7=="UND" && $8!="" {print "  "$8}' | head -30
