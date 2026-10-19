#!/bin/bash
# build_fontprobe.sh — 交叉编译 fontprobe.arm（相机 ABI）
# 用法: bash build_fontprobe.sh   （在 WSL NXKS2 里跑）
set -euo pipefail
cd "$(dirname "$0")"
RF=${NXUI_ROOTFS:-/opt/nxks2/rootfs-112}
INC="$PWD/out/deps/usr/include"
[ -f "$INC/fontconfig/fcfreetype.h" ] || { echo 'missing fontconfig headers; run prepare_dev.sh'; exit 1; }

arm-linux-gnueabi-gcc -std=c99 -O0 -Wall -Wextra -Wno-unused-function \
    -I"$INC" -I"$INC/freetype2" \
    -U_TIME_BITS -D_TIME_BITS=32 -U_FILE_OFFSET_BITS -D_FILE_OFFSET_BITS=32 \
    -mfloat-abi=soft -fno-pic -no-pie -nostdlib -nostartfiles \
    -Wl,-e,_start -Wl,--dynamic-linker=/lib/ld-linux.so.3 \
    -Wl,--allow-shlib-undefined \
    -Wl,-rpath-link,"$RF/usr/lib" -Wl,-rpath-link,"$RF/lib" \
    fontprobe.c ../filmlab/src/crt0_arm.S \
    "$RF/usr/lib/libfontconfig.so.1" "$RF/usr/lib/libfreetype.so.6" \
    "$RF/lib/libc-2.13.so" "$RF/lib/librt.so.1" -lgcc -o out/fontprobe.arm

arm-linux-gnueabi-readelf -d out/fontprobe.arm | grep NEEDED
ls -l out/fontprobe.arm
