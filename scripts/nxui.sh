#!/bin/sh
# Independent Nuklear UI launcher. Installed binary/config live under nxui/.
#
# Startup cost here is dominated by process creation: on this camera a fork +
# exec of the dynamic busybox costs roughly 10-25 ms, and the old script spent
# a dozen of them before the panel could map. Everything a shell builtin can do
# is therefore done in-process:
#   grep '^NX500$' -> read loop      mkdir -p -> skipped when the dir exists
#   nice -n 15     -> nxui sets an absolute priority 19 itself
#   lut.sh list pipeline -> one lut.sh run plus builtins
D=/opt/usr/nx-ks
BB=$D/busybox
BIN=$D/nxui/nxui.arm
LAB=/mnt/mmc/filmlab
LOOKS=/mnt/mmc/looks
read NXUI_LAUNCH_UPTIME nxui_unused < /proc/uptime
export NXUI_LAUNCH_UPTIME

is_nx500() {
    while IFS= read -r line; do
        [ "$line" = NX500 ] && return 0
    done < /etc/version.info 2>/dev/null
    return 1
}
case "${1:-filmlab}" in
  disable)
    rm -f "$D/nxui/enabled"
    $BB killall -q -TERM nxui.arm 2>/dev/null
    exit 0 ;;
  enable)
    [ -x "$BIN" ] && is_nx500 || exit 1
    : > "$D/nxui/enabled"
    exit 0 ;;
  stop)
    $BB killall -q -TERM nxui.arm 2>/dev/null
    exit 0 ;;
  available)
    [ -x "$BIN" ] && [ -f "$D/nxui/enabled" ] && is_nx500
    exit $? ;;
  menu|filmlab|lut|demo|list) MODE=${1:-filmlab} ;;
  *) echo 'nxui.sh menu|filmlab|demo|list|stop|enable|disable|available'; exit 2 ;;
esac
[ -x "$BIN" ] || exit 1
is_nx500 || exit 1
if $BB pidof nxui.arm >/dev/null 2>&1; then
    $BB killall -q -TERM nxui.arm
    exit 0
fi
# The FILMLAB table is shared by the menu and the strip. Hash once; unchanged
# recipes need no shell parser, rewrite to the SD card, or extra process.
# LUT mode reads its recipes from the look library instead, so it skips both
# the hash and the file read entirely.
if [ "$MODE" != lut ]; then
    [ -d "$LAB" ] || mkdir -p "$LAB"
    SIG=$($BB cksum "$LAB/recipes.json") || exit 1
    OLD_SIG=
    [ ! -f /tmp/nxui-export.sig ] || read -r OLD_SIG < /tmp/nxui-export.sig
    if [ ! -s "$LAB/recipes.txt" ] || [ "$SIG" != "$OLD_SIG" ]; then
        "$D/filmlab.sh" export > /tmp/nxui-export.log 2>&1 || exit 1
        printf '%s\n' "$SIG" > /tmp/nxui-export.sig
    fi
fi
if [ "$MODE" = menu ]; then
    "$D/gen_menu.sh" >/dev/null 2>&1
    # Bitrate/ramp menus are generated only when entered, without global sync.
fi
$BB killall -q mod_gui 2>/dev/null
export DISPLAY=:0
export LC_ALL=C
# fontconfig rescans every font to rebuild its cache when the cache directory is
# not writable, and the stock camera config names no <cachedir> at all. That
# scan is 215-260 ms of a ~300 ms first frame. Point it at the card instead:
# measured 202 ms -> 25 ms on the second launch (qemu-arm, camera ABI).
[ -d /mnt/mmc/nxui/fc-cache ] || mkdir -p /mnt/mmc/nxui/fc-cache
[ -f "$D/nxui/fonts.conf" ] && export FONTCONFIG_FILE="$D/nxui/fonts.conf"
# 记住上次打开时停在哪一项（配方 slug / look 名，不是序号）。目录已由上面的
# fc-cache 建好；写失败只是下次从头开始，不影响面板。
export NXUI_STATE_DIR=/mnt/mmc/nxui
# Xft uses fontconfig, so Chinese can use the existing Samsung TTF.
set -- --root "$D" --recipes "$LAB/recipes.txt" --engine "$D/filmlab.sh"
if [ "$MODE" = menu ]; then set -- "$@" --menu gui_ini.NX500; fi
if [ "$MODE" = lut ]; then
    # LUT 模式：滤镜库来自 lut.sh，执行器也是 lut.sh（apply / off）
    # The look list only changes when a file is added or removed, and that
    # updates the directory mtime, so a second open costs one stat instead of
    # another pass over the exFAT folder.
    LU=/tmp/nxui-look
    if [ ! -s "$LU.rec" ] || [ "$LOOKS" -nt "$LU.stamp" ]; then
        sh "$D/lut.sh" list > "$LU.names" 2>/dev/null || exit 1
        # 9 字段配方格式：key|label|7 个占位值（LUT 不使用 PW 分量）。
        # Done with shell builtins: the old awk cost another process.
        : > "$LU.rec"
        while IFS= read -r name; do
            [ -n "$name" ] || continue
            printf '%s|%s|0|0|0|0|0|0|0\n' "$name" "$name" >> "$LU.rec"
        done < "$LU.names"
        : > "$LU.stamp"
    fi
    [ -s "$LU.rec" ] || exit 1
    set -- --root "$D" --recipes "$LU.rec" --engine "$D/lut.sh" --lut
fi
if [ "$MODE" = demo ]; then set -- "$@" --dry-run; else set -- "$@" --live; fi
# Keep lifetime/kill handling in the UI: close waits for an in-flight apply.
# A separate session prevents telnet disconnect from terminating an apply halfway.
# ★ 不能写成 "$BB" setsid "$BB" "$BIN"：setsid 只 exec 一个 PROG，多套一层 BB
#   会让 busybox 把 nxui.arm 当 applet 名 → "applet not found"，面板静默不启动。
#   （旧版能跑是因为中间还有 `nice -n 15` 这层 applet；删掉 nice 后暴露。）
$BB setsid "$BIN" "$@" >> /tmp/nxui.log 2>&1 &
exit 0
