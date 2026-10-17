#!/bin/sh
# Independent Nuklear UI launcher. Installed binary/config live under nxui/.
D=/opt/usr/nx-ks
BB=$D/busybox
BIN=$D/nxui/nxui.arm
LAB=/mnt/mmc/filmlab
read NXUI_LAUNCH_UPTIME nxui_unused < /proc/uptime
export NXUI_LAUNCH_UPTIME
case "${1:-filmlab}" in
  disable)
    rm -f "$D/nxui/enabled"
    $BB killall -q -TERM nxui.arm 2>/dev/null
    exit 0 ;;
  enable)
    [ -x "$BIN" ] && /bin/grep -q '^NX500$' /etc/version.info || exit 1
    : > "$D/nxui/enabled"
    exit 0 ;;
  stop)
    $BB killall -q -TERM nxui.arm 2>/dev/null
    exit 0 ;;
  available)
    [ -x "$BIN" ] && [ -f "$D/nxui/enabled" ] && /bin/grep -q '^NX500$' /etc/version.info
    exit $? ;;
  menu|filmlab|demo|list) MODE=${1:-filmlab} ;;
  *) echo 'nxui.sh menu|filmlab|demo|list|stop|enable|disable|available'; exit 2 ;;
esac
[ -x "$BIN" ] || exit 1
/bin/grep -q '^NX500$' /etc/version.info || exit 1
if $BB pidof nxui.arm >/dev/null 2>&1; then
    $BB killall -q -TERM nxui.arm
    exit 0
fi
mkdir -p "$LAB"
# The table is shared by both views. Hash once; unchanged recipes need no shell
# parser, rewrite to the SD card, or additional export process at each launch.
SIG=$($BB cksum "$LAB/recipes.json") || exit 1
OLD_SIG=
[ ! -f /tmp/nxui-export.sig ] || read -r OLD_SIG < /tmp/nxui-export.sig
if [ ! -s "$LAB/recipes.txt" ] || [ "$SIG" != "$OLD_SIG" ]; then
    "$D/filmlab.sh" export > /tmp/nxui-export.log 2>&1 || exit 1
    printf '%s\n' "$SIG" > /tmp/nxui-export.sig
fi
if [ "$MODE" = menu ]; then
    "$D/gen_menu.sh" >/dev/null 2>&1
    # Bitrate/ramp menus are generated only when entered, without global sync.
fi
$BB killall -q mod_gui 2>/dev/null
export DISPLAY=:0
export LC_ALL=C
# Xft uses fontconfig, so Chinese can use the existing Samsung TTF.
set -- --root "$D" --recipes "$LAB/recipes.txt" --engine "$D/filmlab.sh"
if [ "$MODE" = menu ]; then set -- "$@" --menu gui_ini.NX500; fi
if [ "$MODE" = demo ]; then set -- "$@" --dry-run; else set -- "$@" --live; fi
# Keep lifetime/kill handling in the UI: close waits for an in-flight apply.
# A separate session prevents telnet disconnect from terminating an apply halfway.
$BB setsid "$BB" nice -n 15 "$BIN" "$@" >> /tmp/nxui.log 2>&1 &
exit 0
