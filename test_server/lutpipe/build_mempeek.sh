#!/bin/sh
# build_mempeek.sh —— 交叉编译只读物理内存探针（不安装，产物留 build/）
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT=$(CDPATH= cd -- "$HERE/../.." && pwd)
NX_CC=${NX_CC:-arm-linux-gnueabi-gcc}
NX_ROOTFS=${NX_ROOTFS:-/opt/nxks2/rootfs-112}
mkdir -p "$HERE/build"
"$NX_CC" -O0 -Wall -Wextra -Werror \
    -mfloat-abi=soft -fno-stack-protector -fno-pic -no-pie \
    -D_TIME_BITS=32 -D_FILE_OFFSET_BITS=32 \
    -nostdlib -nostartfiles -Wl,-e,_start -Wl,--dynamic-linker=/lib/ld-linux.so.3 \
    -Wl,--allow-shlib-undefined -Wl,-rpath-link,"$NX_ROOTFS/lib" \
    -o "$HERE/build/nx_mempeek.arm" "$HERE/nx_mempeek.c" \
    "$ROOT/test_server/filmlab/src/crt0_arm.S" "$NX_ROOTFS/lib/libc-2.13.so" -lgcc
sha256sum "$HERE/build/nx_mempeek.arm"
