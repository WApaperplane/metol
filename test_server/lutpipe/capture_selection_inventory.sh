#!/bin/sh
# @gate script=capture_selection_inventory.sh opens=rdonly regs=0 one_shot=1
# Short inventory only; invoke through tools/nx-probe.py (SD log + FTP).
date
cat /proc/uptime /proc/loadavg /proc/sys/kernel/osrelease
ls -l /dev/mem /dev/drime5_ep
ls -l /mnt/mmc/nx_lutdump /mnt/mmc/epdump_3dlut /mnt/mmc/filmlab/lutapi.arm /mnt/mmc/filmlab/lutload.arm /mnt/mmc/filmlab/lut_backend.sh
ls -l /opt/usr/nx-ks/lutapi.arm /opt/usr/nx-ks/lutload.arm
md5sum /mnt/mmc/nx_lutdump /mnt/mmc/epdump_3dlut /mnt/mmc/filmlab/lutapi.arm /mnt/mmc/filmlab/lutload.arm /mnt/mmc/filmlab/lut_backend.sh
/opt/usr/nx-ks/busybox ps | /opt/usr/nx-ks/busybox grep -E 'di-camera-app|lutsentinel|nxui.arm'
st cap capdtm getusr 20
