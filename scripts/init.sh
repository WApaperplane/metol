#!/bin/bash
waitforvideo() {
	while [[ "${hevc[1]}" == "ON" ]]; do
		sleep 1;
		hevc=($(st pmu show | grep hevc)); 
	done
}
hevc=($(st pmu show | grep hevc)); 
if [[ "${hevc[1]}" == "ON" ]]; then 
	/opt/usr/nx-ks/popup_timeout  "警告: 视频模式下不加载模块!" 5
	waitforvideo
fi
export HIB=a
export EVAS_FONT_DPI=72
export EINA_LOG_LEVELS=ecore_x:4,evas_main:1
export HISTSIZE=1000
export GTK_IM_MODULE_FILE=/opt/etc/gtk-2.0/gtk.immodules
export LD_LIBRARY_PATH=:/usr/lib:/usr/lib/driver
export ECORE_IMF_MODULE=isf
export ECORE_INPUT_TIMEOUT_FIX=0
export PATH="/usr/share/scripts:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/opt/usr/devel/usr/sbin:/opt/usr/devel/usr/bin:/opt/usr/devel/sbin:/opt/usr/devel/bin"
export EINA_LOG_DLOG_ENABLE=1
export XMODIFIERS=@im=SCIM
export EINA_LOG_LEVEL=1
export SCIM_MODULE_PATH=/opt/apps/scim/lib/scim-1.0
export ECORE_INPUT_FIX=1
export XDG_CACHE_HOME=/tmp/.cache
export EVAS_GL_NO_BLACKLIST=1
export DISPLAY=:0
export GTK_IM_MODULE=scim
export EINA_LOG_SYSLOG_ENABLE=0
export ELM_PROFILE=mobile
export SHELL="/bin/sh"
export SHLVL="2"
export TERM="vt102"
export USER="root"
export LOGNAME="root"
export MULTISENSE_SND_PLAYER="tizen_snd_player"
nice -n +15 /opt/usr/nx-ks/keyscan /dev/event0 /dev/event1 /opt/usr/nx-ks/ &
# ---- dropbear ssh：加密远程登录（端口 22，root 公钥认证）----
# 构建见 test_server/dropbear/README.md（glibc 2.13 sysroot + 直链机身 libc，-O0）
# --disable-syslog ⇒ 没有 -E/-l 开关，日志只能走 stderr，故 -F + setsid + 重定向落盘
DB=/opt/usr/nx-ks/dropbear
BB=/opt/usr/nx-ks/busybox
if [ -f "$DB/dropbear" ]; then
	# SD 卡 FAT 丢可执行位，cp -ar 后必须是 0644 ⇒ 这里兜底（不能只信 [ -x ]）
	chmod +x "$DB/dropbear" "$DB/dropbearkey" "$DB/sftp-server" "$DB/run.sh" 2>/dev/null
	# host key：p14 刷机保留，但首次装包要现生成
	if [ ! -f "$DB/dropbear_ed25519_host_key" ]; then
		"$DB/dropbearkey" -t ed25519 -f "$DB/dropbear_ed25519_host_key" >/dev/null 2>&1
	fi
	# authorized_keys：/root -> /opt/home/root 在 p11，刷机被重写 ⇒ 每次开机从 p14 恢复
	if [ -f "$DB/authorized_keys" ]; then
		mkdir -p /root/.ssh 2>/dev/null
		cp -f "$DB/authorized_keys" /root/.ssh/authorized_keys 2>/dev/null
		chmod 700 /root/.ssh 2>/dev/null
		chmod 600 /root/.ssh/authorized_keys 2>/dev/null
	fi
	if [ -z "$($BB pidof dropbear 2>/dev/null)" ]; then
		$BB setsid "$DB/run.sh" -F -B -p 22 \
			-r "$DB/dropbear_ed25519_host_key" >>/tmp/db.log 2>&1 </dev/null &
	fi
fi
sync
sync
sync
