#!/bin/bash
renice -n -10 -p $$  > /dev/null
# ★ 2026-11-14：预填「当前值」而不是写死的 180。
#   原版固定 180 会让用户以为当前就是 180（实际开机默认由 auto/a_init.sh 决定），
#   改完一度以为"已经改过了"。读 systemctl 环境里 a_init 设的那份。
case "$1" in
  4K-ProQ) CURV=$(systemctl show-environment | grep '^Pro4K=' | cut -d= -f2) ;;
  HD-ProQ) CURV=$(systemctl show-environment | grep '^ProHD=' | cut -d= -f2) ;;
  4K-HQ)   CURV=$(systemctl show-environment | grep '^Hq4K=' | cut -d= -f2) ;;
  HD-HQ)   CURV=$(systemctl show-environment | grep '^HqHD=' | cut -d= -f2) ;;
  VGA-HQ)  CURV=$(systemctl show-environment | grep '^HqVGA=' | cut -d= -f2) ;;
  *)       CURV="" ;;
esac
case "$CURV" in ''|*[!0-9]*) CURV=80 ;; esac
br=$(/opt/usr/nx-ks/popup_entry "$1 的码率:" "应用修改" 取消 "$CURV" number)
[[  "$br" == "" ]] && exit
#check if selected br is available
avail_br=(35 40 45 50 55 60 65 70 75 80 85 90 95 100 110 120 130 140 150 160 170 180 190 200 210 220 230 240 250 260 270 280 290 300 310 320 400)
[[ " ${avail_br[@]} " =~ " $br " ]] ||  { $(/opt/usr/nx-ks/popup_timeout  " [  Value Not Available  ] " 3);  exit ; }
case "$1" in
4K-ProQ)  /opt/usr/nx-ks/pokemon pro1 $br; systemctl set-environment Pro4K=$br
    ;;
HD-ProQ) /opt/usr/nx-ks/pokemon pro2 $br; /opt/usr/nx-ks/pokemon pro3 $br; systemctl set-environment ProHD=$br
    ;;
4K-HQ)  /opt/usr/nx-ks/pokemon hq1 $br; systemctl set-environment Hq4K=$br
    ;;
HD-HQ) /opt/usr/nx-ks/pokemon hq2 $br; /opt/usr/nx-ks/pokemon hq3 $br; /opt/usr/nx-ks/pokemon hq4 $br; systemctl set-environment HqHD=$br
   ;;
VGA-HQ) /opt/usr/nx-ks/pokemon hq5 $br; /opt/usr/nx-ks/pokemon hq6 $br; systemctl set-environment HqVGA=$br
   ;;
*)
;;
esac
sync;sync;sync
/opt/usr/nx-ks/br_up.sh
/opt/usr/nx-ks/popup_timeout  " [ Bitrates Updated  ] " 2
killall -q mod_gui
exit
