#!/bin/sh
set -e
BB=/opt/usr/nx-ks/busybox
OUT=${0%/*}
L=/opt/usr/nx-ks/lut.sh
S=/mnt/mmc/lut/nx_slotwrite.arm
R=/mnt/mmc/lut/nx_regtabwrite.arm
ST=/mnt/mmc/lut/state
n=0
check() {
    n=$((n+1))
    /bin/sh "$L" apply "$1"
    if [ -f "/mnt/mmc/looks/$1.cube" ]; then
        $BB grep -q 'SPACE CrCbY' "$ST/convert.log"
        $BB cmp -s "$ST/current.bin" "/mnt/mmc/looks/$1.bin"
    fi
    "$R" status > "$OUT/final_status_$n.txt"
    $BB cat "$OUT/final_status_$n.txt"
    read -r active < "$ST/active"
    case "$active" in a18) addr=0x81119F00 ;; a19) addr=0x8111EC00 ;; *) exit 3 ;; esac
    "$S" read "$addr" "$OUT/final_slot_$n.bin"
    $BB cmp -s "$OUT/final_slot_$n.bin" "/mnt/mmc/looks/$1.bin"
    $BB md5sum "$OUT/final_slot_$n.bin"
    echo "PASS_APPLY $1 $active"
}
check hp5
check fuji400h
check bw_acros100
/bin/sh "$L" off
"$R" status > "$OUT/final_off.txt"
$BB cat "$OUT/final_off.txt"
"$S" read 0x81119F00 "$OUT/final_a18_off.bin"
"$S" read 0x8111EC00 "$OUT/final_a19_off.bin"
$BB cmp -s "$OUT/final_a18_off.bin" "$ST/a18_orig.bin"
$BB cmp -s "$OUT/final_a19_off.bin" "$ST/a19_orig.bin"
echo PASS_OFF_ORIGINAL
check fuji400h
echo COLOURSPACE_FINAL_PASS_FUJI_ACTIVE
$BB sync
