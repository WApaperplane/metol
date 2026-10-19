#!/bin/sh
BB=/opt/usr/nx-ks/busybox
S=/mnt/mmc/lut/nx_slotwrite.arm
R=/mnt/mmc/lut/nx_regtabwrite.arm
OUT=${0%/*}
ST=/mnt/mmc/lut/state
original=__off__
[ ! -f "$ST/current" ] || read -r original < "$ST/current"
printf '%s\n' "$original" > "$OUT/original_name"
"$R" status > "$OUT/before.txt" || exit 3
"$S" read 0x81119F00 "$OUT/a18_before.bin" || exit 4
"$S" read 0x8111EC00 "$OUT/a19_before.bin" || exit 4
[ ! -f "$ST/current.bin" ] || $BB cp "$ST/current.bin" "$OUT/converted_before.bin" || exit 4
restore_original() {
    read -r now < "$ST/current"
    if [ "$now" = neutral_gray ]; then
        echo RESTORING_ORIGINAL_LOOK
        if [ "$original" = __off__ ]; then
            /bin/sh /opt/usr/nx-ks/lut.sh off
        else
            /bin/sh /opt/usr/nx-ks/lut.sh apply "$original"
        fi
    else
        echo "RESTORE_SKIPPED_USER_CHANGED_LOOK $now"
    fi
}
trap restore_original EXIT HUP INT TERM
echo GRAY_PROBE_BEGIN
/bin/sh "$OUT/lut.sh" apply neutral_gray || exit 5
"$R" status
/usr/bin/st cap capdtm getusr 108
echo NEUTRAL_GRAY_HOLD_ACTIVE
$BB sync
$BB sleep 180
restore_original
trap - EXIT HUP INT TERM
echo GRAY_PROBE_DONE
$BB sync
