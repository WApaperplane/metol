#!/bin/sh
BB=/opt/usr/nx-ks/busybox
OUT=${0%/*}
NAME=$1
case "$NAME" in hp5_candidate|fuji400h_candidate) ;; *) exit 1 ;; esac
/bin/sh /opt/usr/nx-ks/lut.sh off || exit 2
restore() {
    [ -f /mnt/mmc/lut/state/current ] || return 0
    read -r now < /mnt/mmc/lut/state/current
    if [ "$now" = "$NAME" ]; then /bin/sh /opt/usr/nx-ks/lut.sh off; fi
}
trap restore EXIT HUP INT TERM
/bin/sh "$OUT/lut.sh" apply "$NAME" || exit 3
/mnt/mmc/lut/nx_regtabwrite.arm status
echo "CANDIDATE_ACTIVE $NAME"
$BB sync
$BB sleep 180
restore
trap - EXIT HUP INT TERM
echo "CANDIDATE_DONE $NAME"
$BB sync
