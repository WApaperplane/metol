#!/bin/sh
set -e
BB=/opt/usr/nx-ks/busybox
OUT=${0%/*}
set -- $($BB md5sum "$OUT/lut.sh")
[ "$1" = b11a614971cb96abe561b4690be30aab ]
set -- $($BB md5sum "$OUT/regtab.arm")
[ "$1" = c0bd1f38c3cbb222690b82f5f393978d ]
/bin/sh -n "$OUT/lut.sh"
# Installation changes only the backend scripts/tools, leaving the UI intact.
for path in /opt/usr/nx-ks/lut.sh /mnt/mmc/lut/lut.sh /mnt/mmc/scripts/lut.sh; do
    $BB cp "$OUT/lut.sh" "$path.new"
    $BB chmod 755 "$path.new"
    $BB mv "$path.new" "$path"
    $BB md5sum "$path"
done
for dir in /opt/usr/nx-ks/lut /mnt/mmc/lut /mnt/mmc/scripts/lut; do
    [ -d "$dir" ] || continue
    case "$dir" in
        /opt/usr/nx-ks/lut) backup=reg_runtime_before.arm ;;
        /mnt/mmc/lut) backup=reg_sd_before.arm ;;
        *) backup=reg_mother_before.arm ;;
    esac
    [ ! -f "$dir/nx_regtabwrite.arm" ] || $BB cp "$dir/nx_regtabwrite.arm" "$OUT/$backup"
    $BB cp "$OUT/regtab.arm" "$dir/nx_regtabwrite.arm.new"
    $BB chmod 755 "$dir/nx_regtabwrite.arm.new"
    $BB mv "$dir/nx_regtabwrite.arm.new" "$dir/nx_regtabwrite.arm"
    $BB md5sum "$dir/nx_regtabwrite.arm"
done
/bin/sh /opt/usr/nx-ks/lut.sh status
/usr/bin/st cap capdtm getusr 108
echo DEPLOY_REFRESH_BACKEND_DONE
$BB sync
