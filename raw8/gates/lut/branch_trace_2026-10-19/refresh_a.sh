#!/bin/sh
BB=/opt/usr/nx-ks/busybox
R=/mnt/mmc/lut/nx_regtabwrite.arm
S=/mnt/mmc/lut/nx_slotwrite.arm
OUT=${0%/*}
LUT=$OUT/lut.sh
set -- $($BB md5sum "$R")
[ "$1" = c0bd1f38c3cbb222690b82f5f393978d ] || exit 2
set -- $($BB md5sum "$S")
[ "$1" = ed1708306d8110ef1950bef2843e4747 ] || exit 3
$BB cp /opt/usr/nx-ks/lut.sh "$OUT/runtime_before.sh" || exit 4
$BB cp /mnt/mmc/scripts/lut.sh "$OUT/mother_before.sh" || exit 4
$BB cp /mnt/mmc/lut/lut.sh "$OUT/sd_engine_before.sh" || exit 4
$BB cp -a /mnt/mmc/lut/state "$OUT/state_before" || exit 4
recover() {
    echo RECOVER_FACTORY
    /bin/sh "$LUT" off
}
trap recover EXIT HUP INT TERM
/bin/sh -n "$LUT" || exit 5
n=0
apply_one() {
    n=$((n+1))
    echo "PHASE_$n $1"
    /bin/sh "$LUT" apply "$1" || return 1
    "$R" status > "$OUT/status_$n.txt" || return 1
    $BB cat "$OUT/status_$n.txt"
    read -r active < /mnt/mmc/lut/state/active
    case "$active" in a18) addr=0x81119F00 ;; a19) addr=0x8111EC00 ;; *) return 1 ;; esac
    "$S" read "$addr" "$OUT/slot_$n.bin" || return 1
    $BB cmp -s "$OUT/slot_$n.bin" "/mnt/mmc/looks/$1.bin" || return 1
    $BB md5sum "$OUT/slot_$n.bin" "/mnt/mmc/looks/$1.bin"
    $BB cp /mnt/mmc/lut/state/refresh.log "$OUT/refresh_$n.log"
    echo "PASS_PHASE_$n $1 $active"
}
echo REFRESH_TEST_BEGIN
apply_one slide_astia100f || exit 6
apply_one slide_provia100f || exit 7
apply_one slide_astia100f || exit 8
echo OFF_TEST
/bin/sh "$LUT" off || exit 9
"$R" status > "$OUT/status_off.txt"
$BB cat "$OUT/status_off.txt"
"$S" read 0x81119F00 "$OUT/a18_off.bin" || exit 10
"$S" read 0x8111EC00 "$OUT/a19_off.bin" || exit 10
$BB cmp -s "$OUT/a18_off.bin" /mnt/mmc/lut/state/a18_orig.bin || exit 11
$BB cmp -s "$OUT/a19_off.bin" /mnt/mmc/lut/state/a19_orig.bin || exit 11
echo PASS_OFF_RESTORED
apply_one slide_astia100f || exit 12
trap - EXIT HUP INT TERM
echo REFRESH_TEST_PASS_ASTIA_ACTIVE
$BB sync
