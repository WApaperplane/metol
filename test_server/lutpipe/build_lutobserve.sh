#!/bin/sh
# @gate script=build_lutobserve.sh opens=rdonly one_shot=1 gate=none pconly=1
# Rebuild the bounded read-only collector with the existing ARM soft-float GCC.
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
NX_CC=${NX_CC:-arm-linux-gnueabi-gcc}
mkdir -p "$HERE/build"
"$NX_CC" -O0 -Wall -Wextra -Werror -nostdlib -static -fno-builtin \
    -fno-stack-protector -fno-pic -no-pie -fomit-frame-pointer \
    -marm -mfloat-abi=soft -Wl,-e,_start \
    -o "$HERE/build/lutobserve.arm" "$HERE/lutobserve.c"
md5sum "$HERE/build/lutobserve.arm"
