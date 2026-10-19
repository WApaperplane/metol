#!/bin/sh
# Bounded setting-only A/B/A observation. Never writes LUT RAM or registries.
# Original state was read and recorded as OLEDCOLOR_ON (0x6c0001).
BB=/opt/usr/nx-ks/busybox
R=/mnt/mmc/lut/nx_regtabwrite.arm
ST=/usr/bin/st
set -- $($BB md5sum "$R")
[ "$1" = c0bd1f38c3cbb222690b82f5f393978d ] || exit 2
restore_original() {
    "$ST" cap capdtm setusr 108 0x6c0001
    $BB sleep 2
}
echo ABA_BEGIN
$BB cat /proc/uptime
"$ST" cap capdtm getusr 108
"$R" status
trap restore_original EXIT HUP INT TERM
echo B_OLED_OFF
"$ST" cap capdtm setusr 108 0x6c0000
$BB sleep 2
"$ST" cap capdtm getusr 108
"$R" status
echo A_RESTORE_ON
restore_original
"$ST" cap capdtm getusr 108
"$R" status
trap - EXIT HUP INT TERM
echo ABA_DONE
$BB sync
