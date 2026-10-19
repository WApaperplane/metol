#!/bin/sh
# Controlled Acros comparison with original Astia slot bytes restored afterwards.
# Official OLED setting changes trigger P7 loads; no direct MMIO or registry writes.
BB=/opt/usr/nx-ks/busybox
ST=/usr/bin/st
R=/mnt/mmc/lut/nx_regtabwrite.arm
S=/mnt/mmc/lut/nx_slotwrite.arm
OUT=${0%/*}
set -- $($BB md5sum "$R")
[ "$1" = c0bd1f38c3cbb222690b82f5f393978d ] || exit 2
set -- $($BB md5sum "$S")
[ "$1" = ed1708306d8110ef1950bef2843e4747 ] || exit 3
set -- $($BB md5sum /mnt/mmc/looks/bw_acros100.bin)
[ "$1" = 18f0e34bb5b13219863ee134ed1c6231 ] || exit 4
"$S" read 0x81119F00 "$OUT/a18_before.bin" || exit 5
set -- $($BB md5sum "$OUT/a18_before.bin")
[ "$1" = 922c10b02ae246527267da4f2675ed0b ] || exit 6
restore_original() {
    "$ST" cap capdtm setusr 108 0x6c0001
    $BB sleep 1
    "$S" restore 0x81119F00 "$OUT/a18_before.bin"
    "$ST" cap capdtm setusr 108 0x6c0000
    $BB sleep 1
    "$ST" cap capdtm setusr 108 0x6c0001
    $BB sleep 1
}
trap restore_original EXIT HUP INT TERM
echo ACROS_BEGIN
"$ST" cap capdtm setusr 108 0x6c0001
$BB sleep 1
"$S" write 0x81119F00 /mnt/mmc/looks/bw_acros100.bin || exit 7
"$ST" cap capdtm setusr 108 0x6c0000
$BB sleep 2
"$ST" cap capdtm getusr 108
"$R" status
echo ACROS_HOLD_ACTIVE
$BB sync
$BB sleep 60
restore_original
"$ST" cap capdtm getusr 108
"$R" status
trap - EXIT HUP INT TERM
echo ACROS_DONE_RESTORED_ASTIA_ON
$BB sync
