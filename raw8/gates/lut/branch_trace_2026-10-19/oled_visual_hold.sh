#!/bin/sh
# One minute visual comparison, then restore the previously observed ON value.
# No LUT content/registry writes. Slot reads only save private diagnostic files.
BB=/opt/usr/nx-ks/busybox
ST=/usr/bin/st
R=/mnt/mmc/lut/nx_regtabwrite.arm
S=/mnt/mmc/lut/nx_slotwrite.arm
OUT=${0%/*}
set -- $($BB md5sum "$R")
[ "$1" = c0bd1f38c3cbb222690b82f5f393978d ] || exit 2
set -- $($BB md5sum "$S")
[ "$1" = ed1708306d8110ef1950bef2843e4747 ] || exit 3
restore_original() {
    "$ST" cap capdtm setusr 108 0x6c0001
    $BB sleep 2
}
trap restore_original EXIT HUP INT TERM
echo VISUAL_BEGIN
"$S" read 0x81119F00 "$OUT/a18_before.bin"
"$S" read 0x81101E00 "$OUT/a13_before.bin"
"$ST" cap capdtm setusr 108 0x6c0000
$BB sleep 2
"$ST" cap capdtm getusr 108
"$R" status
echo OFF_HOLD_ACTIVE
$BB sync
$BB sleep 60
restore_original
"$ST" cap capdtm getusr 108
"$R" status
trap - EXIT HUP INT TERM
echo VISUAL_DONE_RESTORED_ON
$BB sync
