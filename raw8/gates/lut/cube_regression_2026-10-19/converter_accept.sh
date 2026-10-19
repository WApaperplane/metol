#!/bin/sh
BB=/opt/usr/nx-ks/busybox
OUT=${0%/*}
set -- $($BB md5sum "$OUT/cube2lut.arm")
[ "$1" = 2d94e76f4e917ce73d9ffad960a48c64 ] || exit 2
$BB chmod 755 "$OUT/cube2lut.arm"
for name in hp5 fuji400h; do
    "$OUT/cube2lut.arm" "/mnt/mmc/looks/$name.cube" "$OUT/${name}_new.bin" || exit 3
    /mnt/mmc/lut/cube2lut.arm "/mnt/mmc/looks/$name.cube" "$OUT/${name}_old.bin" || exit 4
    $BB cmp -s "$OUT/${name}_old.bin" "/mnt/mmc/looks/$name.bin" || exit 5
    $BB md5sum "$OUT/${name}_new.bin" "$OUT/${name}_old.bin"
done
echo CONVERTER_ONDEVICE_PASS
$BB sync
