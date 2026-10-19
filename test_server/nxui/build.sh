#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
RF=${NXUI_ROOTFS:-/opt/nxks2/rootfs-112}
MODE=${1:-all}
mkdir -p out
INC="$PWD/out/deps/usr/include"
[ -f "$INC/X11/Xlib.h" ] || { echo 'Run bash prepare_dev.sh first'; exit 1; }
COMMON=(-std=c99 -O0 -Wall -Wextra -Wno-unused-function -Wno-unused-parameter
    -I"$INC" -I"$INC/freetype2" -fno-stack-protector)
if [ "$MODE" != arm ]; then
    gcc "${COMMON[@]}" nxui.c nxui_model.c nxui_services.c -o out/nxui -Lout/deps/usr/lib/x86_64-linux-gnu \
        -l:libX11.so.6 -l:libXft.so.2 -l:libfontconfig.so.1 -l:libfreetype.so.6
    gcc -std=c99 -O0 -Wall -Wextra -Werror nxui_model.c test_model.c -o out/test_model
    out/test_model
    gcc -std=c99 -O0 -Wall -Wextra -Werror nxui_services.c test_services.c -o out/test_services
    out/test_services
    gcc -std=c99 -O0 -Wall -Wextra -Werror -I"$INC" test_input.c -l:libX11.so.6 -o out/test_input
fi
if [ "$MODE" != host ]; then
    arm-linux-gnueabi-gcc "${COMMON[@]}" -U_TIME_BITS -D_TIME_BITS=32 \
        -U_FILE_OFFSET_BITS -D_FILE_OFFSET_BITS=32 -mfloat-abi=soft -fno-pic -no-pie \
        -nostdlib -nostartfiles -Wl,-e,_start -Wl,--dynamic-linker=/lib/ld-linux.so.3 \
        -Wl,--allow-shlib-undefined -Wl,-rpath-link,"$RF/usr/lib" -Wl,-rpath-link,"$RF/lib" \
        nxui.c nxui_model.c nxui_services.c ../filmlab/src/crt0_arm.S \
        "$RF/usr/lib/libX11.so.6" "$RF/usr/lib/libXft.so.2" "$RF/usr/lib/libfontconfig.so.1" \
        "$RF/lib/libc-2.13.so" "$RF/lib/librt.so.1" -lgcc -o out/nxui.arm
    arm-linux-gnueabi-readelf -d out/nxui.arm > out/needed.txt
    arm-linux-gnueabi-readelf -V out/nxui.arm > out/versions.txt
    if grep -E 'NEEDED.*(elementary|evas|ecore|edje)' out/needed.txt; then
        echo 'Unexpected EFL dependency'; exit 1
    fi
    if grep -Eq 'GLIBC_2\.(1[4-9]|[2-9][0-9])' out/versions.txt; then
        echo 'Runtime newer than camera glibc 2.13'; exit 1
    fi
    ls -lh out/nxui.arm
    arm-linux-gnueabi-gcc "${COMMON[@]}" -U_TIME_BITS -D_TIME_BITS=32 \
        -U_FILE_OFFSET_BITS -D_FILE_OFFSET_BITS=32 -mfloat-abi=soft -fno-pic -no-pie \
        -nostdlib -nostartfiles -Wl,-e,_start -Wl,--dynamic-linker=/lib/ld-linux.so.3 \
        -Wl,--allow-shlib-undefined -Wl,-rpath-link,"$RF/usr/lib" -Wl,-rpath-link,"$RF/lib" \
        test_input.c ../filmlab/src/crt0_arm.S "$RF/usr/lib/libX11.so.6" \
        "$RF/lib/libc-2.13.so" "$RF/lib/librt.so.1" -lgcc -o out/test_input.arm
    mkdir -p ../../scripts/nxui
    cp out/nxui.arm ../../scripts/nxui/nxui.arm
    cp vendor/LICENSE ../../scripts/nxui/NUKLEAR-LICENSE
fi
