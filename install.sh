#!/bin/bash
# ============================================================
# NX-KS2 智能引导器 (本文件放 SD 卡根目录, 被相机自动执行)
#
# 触发链(不可改, 相机固件行为):
#   SD 根 info.tg -> nx_cs.adj(内容固定为 "shell script /mnt/mmc/install.sh")
#   -> 相机 dfmsd 检测到后自动执行 /mnt/mmc/install.sh(即本文件), 无需任何按键
#
# 自动分派(按是否已安装):
#   [ 未安装 ] bluetoothd.orig 不存在 -> 全量安装(仅首次装机)
#       与经典 NX-KS 相同: 挂载蓝牙开机钩子 + cp -ar scripts -> /opt/usr/nx-ks
#   [ 已安装 ] bluetoothd.orig 存在   -> 增量同步(日常更新走这里, 安全)
#       只做 cp -ar /mnt/mmc/scripts/* 覆盖 /opt/usr/nx-ks/ (只覆盖不删除)
#       绝不触碰 bluetoothd 钩子, 绝不删除相机上已装文件, 永不"卸载"
#       需要卸载请用相机菜单里的 uninstall.sh(手动确认, 不会误触)
#
# 每次执行后只清理 SD 卡根的 3 个触发文件(info.tg / nx_cs.adj / 本脚本),
# SD 卡上的 scripts/ 母本【保留】, 你随时能在电脑上查看/编辑。
#
# 日常更新三步走(已装机器):
#   1. 电脑上把最新 scripts/ 拷进 SD 卡
#   2. 把 info.tg + nx_cs.adj + 本文件(仓库根的最新版)也拷进 SD 卡根
#   3. 插卡 -> 相机自动增量同步 -> 弹窗提示 -> 自动重启, 拔卡即可
# 全程不需要重刷固件, 也不会误触发卸载。
#
# 注意: 本文件为仓库根 install.sh 的新版。旧版"二象性"install.sh
#       (装过再跑=卸载) 已废弃, 请勿再使用。
# ============================================================

# ---- 确保在拍照界面(LCD 输出), 否则尝试切换 ----
[[ $(echo $(st cap capdtm getusr MONITOROUT) | grep LCD) > ""  ]] || { $( st app disp lcd ) &&  sleep 1 ; }
[[ $(echo $(st cap capdtm getusr MONITOROUT) | grep LCD) > ""  ]] || exit

# ---- 固件版本校验: NX500 1.12 / NX1 1.41 ----
VEROK=0
IS_NX1=0
{ /bin/grep -q '^NX500$' /etc/version.info && /bin/grep -q '^1.12$' /etc/version.info; } && VEROK=1
if { /bin/grep -q '^NX1$' /etc/version.info && /bin/grep -q '^1.41$' /etc/version.info; }; then
    VEROK=1; IS_NX1=1
fi
if [ "$VEROK" != "1" ]; then
    [ -x /mnt/mmc/scripts/popup_timeout ] && /mnt/mmc/scripts/popup_timeout " [  固件版本不支持  ] " 2 &
    exit 1
fi

POPUP=/mnt/mmc/scripts/popup_timeout
[ -x "$POPUP" ] || POPUP=/opt/usr/nx-ks/popup_timeout
# ★ popup_timeout 不是 .sh 文件, 上面的 *.sh chmod 兜底覆盖不到它
#   而 SD 卡 FAT 挂载常丢可执行位 -> 这里单独补, 否则后面所有弹窗静默失败
chmod +x "$POPUP" 2>/dev/null

if [ ! -x /usr/sbin/bluetoothd.orig ]; then
    # ================= 全量安装(仅首次装机) =================
    "$POPUP" " [  正在安装...  ] " 4 &
    mount -o remount,rw /
    mv /usr/sbin/bluetoothd /usr/sbin/bluetoothd.orig
    cat >/usr/sbin/bluetoothd << EOF
#!/bin/bash
if [ -x /opt/usr/nx-ks/init.sh ]; then
  /opt/usr/nx-ks/init.sh
fi
EOF
    chmod +x /usr/sbin/bluetoothd
    mount -o remount,ro /
    sleep 5
    mkdir -p /opt/usr/nx-ks
    cp -ar /mnt/mmc/scripts/* /opt/usr/nx-ks/
    sync;sync;sync
    "$POPUP" " [ 安装完成 ] " 3
else
    # ================= 增量同步(日常更新, 安全) =================
    if [ ! -d /mnt/mmc/scripts ]; then
        "$POPUP" " [ 错误: SD 卡无 scripts/ ] " 3
        exit 1
    fi
    "$POPUP" " [  正在同步...  ] " 4 &
    # 停掉运行中的 web 遥控/键控进程, 保证覆盖后干净重启
    killall -q nx-remote-controller-daemon 2>/dev/null
    killall -q onscreen_rc 2>/dev/null
    killall -q nx-input-injector 2>/dev/null
    killall -q xev-nx 2>/dev/null
    # SD 母本全量覆盖相机内部运行副本(只覆盖不删除, 幂等可重复执行)
    cp -ar /mnt/mmc/scripts/* /opt/usr/nx-ks/
    sync;sync;sync
    "$POPUP" " [  同步完成  ] " 3
    sleep 1
fi

# ---- NX1 特判(两分支共用; 幂等) ----
if [ "$IS_NX1" = "1" ]; then
    [ -f /opt/usr/nx-ks/EV_EV.sh ] && mv -f /opt/usr/nx-ks/EV_EV.sh /opt/usr/nx-ks/EV_OK.sh
    [ -f /opt/usr/nx-ks/keyscan1 ]  && cp -f /opt/usr/nx-ks/keyscan1 /opt/usr/nx-ks/keyscan
fi

# ---- 补可执行位 (2026-10-05, 2026-10-06 修正) ----
# SD 卡上的文件来自 PC 拷贝, FAT/NTFS 挂载常丢可执行位 -> cp -ar 会原样保留 0644,
# 结果脚本在相机上直接 "Permission denied"。这里统一兜底, 幂等可重复执行。
#
# ★ 2026-10-06 修正: 原版只匹配 *.sh, 漏掉了大量【无扩展名】的可执行文件:
#   keyscan / mod_gui / popup_timeout / capdtm / thumb-cgi / push-cgi ...
#   这些才是装机后真正要跑的东西。漏 chmod => "装完了但没反应"。
#   现改为对 /opt/usr/nx-ks 下所有普通文件补位(chmod +x 对普通文件无害)。
for _f in /opt/usr/nx-ks/* /opt/usr/nx-ks/nx-rc/* /opt/usr/nx-ks/nx-rc/thumb/* /opt/usr/nx-ks/dicam/* /opt/usr/nx-ks/nxui/*; do
    [ -f "$_f" ] && chmod +x "$_f" 2>/dev/null
done
unset _f

# ---- ★ 运行时数据目录（2026-10-17 加入）----
# 一批老脚本把数据文件写死在 SD 的这两处（原版设计是 mod 整体放 /mnt/mmc/scripts/
# 再 cp 到 /opt/usr/nx-ks/）。只从 tar 解压到 /opt/usr/nx-ks/ 的部署不会创建它们，
# 结果是「对焦堆栈 / 对焦按钮 / EV 档位」保存静默失败（无报错、重启后回默认）。
# 幂等；已存在则不动，绝不覆盖用户数据。
mkdir -p /mnt/mmc/scripts /sdcard/presets 2>/dev/null
[ -f /mnt/mmc/scripts/focus_stack.cfg ] || printf '10\n6\n' > /mnt/mmc/scripts/focus_stack.cfg 2>/dev/null

# ---- ★ FilmLab（NX500 专属）：配方库种子 + 菜单生成（2026-10-08 加入）----
#   配方库在 SD 卡（/mnt/mmc/filmlab/recipes.json，插卡即可编辑，加配方不用改代码）
#   内部留只读种子（/opt/usr/nx-ks/filmlab/recipes.json，随 scripts/ 同步而来）
#   ★ 只在 SD 卡还没有配方库时复制 —— 绝不覆盖用户改过的配方
#   ★ 菜单由 mkgui 从配方库现场生成（幂等）；引擎缺失时整体跳过
if /bin/grep -q '^NX500$' /etc/version.info && [ -x /opt/usr/nx-ks/filmlab.sh ]; then
    mkdir -p /mnt/mmc/filmlab 2>/dev/null
    [ -f /mnt/mmc/filmlab/recipes.json ] || cp -f /opt/usr/nx-ks/filmlab/recipes.json /mnt/mmc/filmlab/recipes.json 2>/dev/null
    /opt/usr/nx-ks/filmlab.sh mkgui >/dev/null 2>&1
fi

# ---- ★ 拉起 telnet + ftpd (2026-10-06) ----
# ★ 必须放在上面的 chmod 兜底【之后】—— SD 卡 FAT 挂载丢可执行位时,
#   /mnt/mmc/scripts/onboard.sh 本身也是 0644, 直接调用会 Permission denied。
# 为什么必须有: 原来 telnet 只能从 mod 菜单的 "IP: ... [Telnet关]" 那一行开启,
# 而那行来自 gui_ini.NX500, 由 gen_menu.sh 在【菜单启动时】现场生成
# ⇒ 死锁: 菜单没生成 -> 没 telnet 开关 -> 连不上 -> 无法排查 -> 菜单更起不来。
# 本行把 telnet 从"mod 功能"降级成"装机副产品", 是本项目唯一的远程排查通路。
if [ -x /mnt/mmc/scripts/onboard.sh ]; then
    /mnt/mmc/scripts/onboard.sh
elif [ -x /opt/usr/nx-ks/onboard.sh ]; then
    /opt/usr/nx-ks/onboard.sh
fi

# ---- 清理 SD 卡根触发文件(防止忘拔卡导致下次开机重复执行); scripts/ 与 odt 文档保留 ----
killall dfmsd 2>/dev/null
rm -f /mnt/mmc/info.tg
rm -f /mnt/mmc/nx_cs.adj
rm -f /mnt/mmc/install.sh
sync;sync;sync
reboot
