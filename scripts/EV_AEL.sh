#!/bin/bash
#=====================================================================
# EV_AEL.sh —— EV + AEL → 打开 FilmLab 配方菜单（mod_gui 路径）
#=====================================================================
# ★ 2026-10-08（上机轨 U2）换绑说明：
#   本槽位原为社区脚本「长录像 + 黑屏遮挡」（机上备份 /opt/usr/nx-ks/EV_AEL.sh.orig）。
#   起因：用户实测「双击 FN 触发 mod 菜单」不成立 ⇒ 需要一个确定可用的机身入口。
#
# ★ 触发条件（keyscan 规则 A）：【按住 EV 键，再按 AEL 键】
#   keyscan.c: if (ev_pressed == 1 && code != NXKEY_EV && value == 1)
#                  sprintf(shell_name, "EV_%s", nxkeyname[code]);
#   ⇒ 文件名必须恰好是 EV_AEL.sh（AEL 有 nxkeyname 表项）。
#
# ★ 为什么走 mod_gui 而不是自绘 UI（2026-10-08 实测结论）：
#   自绘全屏 EFL 窗口在单核 NX500 上会把整机拖死（720x480 时相机卡死，只能物理重启）。
#   而 mod_gui 已证「可见 + 不卡」。
#
# ★★★ 2026-10-10 提速版（用户反馈：「菜单弹出要两秒多，确实偏慢」）
#   旧链路 = 【串行 + 硬等】：
#       st 切屏(~0.2s) → sleep 1（★ 1 秒纯白等）→ mkgui(~1s，每次都全量重建) → mod_gui
#      ≈ 2.2 s
#   新链路：
#      ① 切屏【后台发】，不再同步等
#      ② mkgui【带缓存】—— 配方/页号/当前项都没变就直接返回（≈0；见 filmlab.sh mkgui）
#      ③ 只留一个 0.4 秒「屏幕切换余量」（EV_AEL_DELAY 可调；=0 则完全不等）
#      ≈ 0.5 s（首次/改配方后 ≈ 0.6s，因为那时确实要重建菜单）
#   ★ 提速的大头不在 sleep，而在 mkgui：它原来每行配方要 fork 3 次进程（echo|tr|sed），
#     18 行 = 54 次 fork —— 单核 ARM 上一次 fork 十几毫秒，这就是那"第二秒"。
#=====================================================================
BB=/opt/usr/nx-ks/busybox
D=/opt/usr/nx-ks

# ---- ★ 机型闸门：FilmLab 为 NX500 专属（prefman PW 偏移只在 NX500 1.12 实证）----
#   NX1 上退回社区原版「长录像+黑屏遮挡」脚本，零行为变化。
#   绝不把未经实机的 prefman 偏移写到 NX1 上。
if ! /bin/grep -q '^NX500$' /etc/version.info; then
    [ -x /opt/usr/nx-ks/EV_AEL.community.sh ] && exec /opt/usr/nx-ks/EV_AEL.community.sh "$@"
    exit 0
fi

# 独立 UI（NXUI）。2026-11-10 起默认可用：旧的「必须 enable 才可用」门禁
# 从来没进过 release 包，导致用户装完只能看到 mod_gui 的老 popup；现在只有
# 显式 `nxui.sh disable` 才会落到下面的 mod_gui 分支。排查用 `nxui.sh diag`。
if [ -x "$D/nxui.sh" ] && "$D/nxui.sh" available; then
    "$D/nxui.sh" filmlab
    exit $?
fi

# ---- 同槽重复触发 ⇒ 关掉（做成开关，免得开了关不掉）----
if $BB pidof mod_gui > /dev/null 2>&1; then
    $BB killall -q mod_gui
    exit 0
fi

# ---- ★ 切 LCD：后台发，不阻塞 ----
#   社区惯例：不切的话窗口起在 EVF 上，后屏看不见。
#   注：实机 getusr MONITOROUT 返回 "Unkonwn Operation"，判断恒为真 ⇒ 每次都切（无害）
{ st app bb lcd on; st app disp lcd; } > /dev/null 2>&1 &

# ---- 配方菜单：只在源变化时重建；命中缓存时 <100ms ----
[ -x "$D/filmlab.sh" ] && "$D/filmlab.sh" mkgui > /dev/null 2>&1

# ---- 屏幕切换余量（原版为 1s 同步等待；这里 0.4s）----
#   调快：EV_AEL_DELAY=0.2 ；若发现窗口起在 EVF 上，就调大到 0.8
$BB sleep ${EV_AEL_DELAY:-0.4}

# ---- 起配方菜单：gui_filmlab1b = 配方列表页（由 mkgui 从 SD 卡配方库生成）----
#   nice +15：让相机主进程优先（社区约定，别跟拍照抢 CPU）
nice -n +15 $D/mod_gui $D/gui_filmlab1b &
exit 0
