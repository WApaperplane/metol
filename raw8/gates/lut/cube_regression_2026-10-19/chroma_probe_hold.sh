#!/bin/sh
BB=/opt/usr/nx-ks/busybox
OUT=${0%/*}
R=/mnt/mmc/lut/nx_regtabwrite.arm
/bin/sh /opt/usr/nx-ks/lut.sh off || exit 2
restore() {
    read -r now < /mnt/mmc/lut/state/current || return 0
    if [ "$now" = chroma_axis ]; then /bin/sh /opt/usr/nx-ks/lut.sh off; fi
}
trap restore EXIT HUP INT TERM
/bin/sh "$OUT/lut.sh" apply chroma_axis || exit 3
"$R" status
echo CHROMA_AXIS_HOLD_ACTIVE
$BB sync
$BB sleep 120
restore
trap - EXIT HUP INT TERM
echo CHROMA_AXIS_DONE
$BB sync
