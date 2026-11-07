#!/bin/sh
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT=$(CDPATH= cd -- "$HERE/../.." && pwd)
NX_CC=${NX_CC:-arm-linux-gnueabi-gcc}
NX_ROOTFS=${NX_ROOTFS:-/opt/nxks2/rootfs-112}
mkdir -p "$HERE/build"
"$NX_CC" -O0 -Wall -Wextra -Werror -Wno-misleading-indentation \
    -mfloat-abi=soft -fno-stack-protector -fno-pic -no-pie \
    -D_TIME_BITS=32 -D_FILE_OFFSET_BITS=32 -I"$ROOT/test_server/sysarch/inc" \
    -nostdlib -nostartfiles -Wl,-e,_start -Wl,--dynamic-linker=/lib/ld-linux.so.3 \
    -Wl,--allow-shlib-undefined -Wl,-rpath-link,"$NX_ROOTFS/lib" \
    -o "$HERE/build/nx_lutload.arm" "$HERE/nx_lutload.c" \
    "$ROOT/test_server/filmlab/src/crt0_arm.S" "$NX_ROOTFS/lib/libc-2.13.so" "$NX_ROOTFS/lib/librt.so.1" -lgcc
sha256sum "$HERE/build/nx_lutload.arm"
mkdir -p "$ROOT/scripts/lut"
cp "$HERE/build/nx_lutload.arm" "$ROOT/scripts/lut/nx_lutload.arm"
