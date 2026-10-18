#!/bin/sh
# @gate script=build_regtabwrite.sh opens=rwdirect one_shot=1 gate=none pconly=1
# Controlled single-word writer for the View4 registry entry (manual run only).
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
NX_CC=${NX_CC:-arm-linux-gnueabi-gcc}
mkdir -p "$HERE/build"
"$NX_CC" -O0 -Wall -Wextra -Werror -nostdlib -static -fno-builtin \
    -fno-stack-protector -fno-pic -no-pie -fomit-frame-pointer \
    -marm -mfloat-abi=soft -Wl,-e,_start \
    -o "$HERE/build/nx_regtabwrite.arm" "$HERE/nx_regtabwrite.c"
md5sum "$HERE/build/nx_regtabwrite.arm"
