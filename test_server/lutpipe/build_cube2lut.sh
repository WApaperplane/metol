#!/bin/sh
# @gate script=build_cube2lut.sh opens=none one_shot=1 gate=none pconly=1
# .cube -> 19712B slot table converter (runs on camera, no libc).
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
NX_CC=${NX_CC:-arm-linux-gnueabi-gcc}
mkdir -p "$HERE/build"
"$NX_CC" -O0 -Wall -Wextra -Werror -nostdlib -static -fno-builtin \
    -fno-stack-protector -fno-pic -no-pie -fomit-frame-pointer \
    -marm -mfloat-abi=soft -Wl,-e,_start \
    -o "$HERE/build/cube2lut.arm" "$HERE/cube2lut.c"
md5sum "$HERE/build/cube2lut.arm"
