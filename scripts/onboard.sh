#!/bin/bash
# ============================================================
# NX-KS2 onboard —— 装机后无条件拉起【远程登录】
#
# 存在的原因（2026-10-06）
# ----------------------
# 原来 telnet 只能从 mod 菜单里的 "IP: x.x.x.x [Telnet关]" 那一行开启，
# 而那行来自 gui_ini.NX500，而 gui_ini.NX500 由 gen_menu.sh 在【菜单启动时】现场生成。
#
# ⇒ 死锁：菜单没生成 → 没有开关 → 连不上 → 无法查问题 → 菜单更起不来
#
# 本脚本把远程登录从"mod 功能"降级成"装机副产品"：
# 只要 install.sh 跑完，至少有一条远程通路开着，不依赖 mod 其它部分是否正常。
# ★ 这是本项目唯一的远程排查通路，绝不能因为 mod 其它部件出错而失效。
#
# ★ 2026-11-10 改向：先 ssh，telnet 降级为老机器的兜底
# ------------------------------------------------------
# 2026-11-02 起 telnet/FTP 已退役，远程走 dropbear ssh(22)；但 telnetd 二进制
# 从未进过 release 包 —— .gitignore 里一条裸 `telnetd` 规则把它挡在 git 之外，
# 本地树里也没有这个文件，于是每次打包都少它一个。新装机上老版 onboard 会在
# 「缺可执行文件」处直接 exit 1，连 FTP 都不起，而菜单还在显示可点的 Telnet 行。
# 现在：ssh 先起；ssh 成了就跳过 telnet/FTP；只有 ssh 起不来且 telnetd 真的
# 存在时才回落到老路径。缺文件只写日志，不再让安装流程难看。
#
# 行为：幂等，可重复执行（先 killall 再起，不堆进程）
# 日志：/opt/usr/nx-ks/onboard.log —— 装完连不上时可从 SD 卡读到
# ============================================================

DIR=/opt/usr/nx-ks
LOG="$DIR/onboard.log"
BB="$DIR/busybox"
SDCARD=/opt/storage/sdcard

ssh_listening() {
	[ -r /proc/net/tcp ] || return 1
	"$BB" awk '$4 == "0A" && $2 ~ /:0016$/ { found = 1 } END { exit !found }' /proc/net/tcp
}

{
	echo "=== onboard @ $(date 2>/dev/null) ==="
	echo "telnetd : $([ -x "$DIR/telnetd" ] && echo OK || echo 'MISSING (never shipped: .gitignore bare telnetd)')"
	echo "busybox : $([ -x "$BB" ] && echo OK || echo 'MISSING(not exec?)')"
	echo "sdcard  : $([ -d "$SDCARD" ] && echo OK || echo MISSING)"
	# NXUI 是否可用（用户报「拉不起新版 UI、只出老 popup」时先看这一行）
	if [ -x "$DIR/nxui.sh" ]; then
		echo "nxui    : $("$DIR/nxui.sh" diag 2>/dev/null | tr '\n' ' ')"
	else
		echo "nxui    : nxui.sh MISSING"
	fi
} > "$LOG" 2>&1

# ---- 1) 首选：dropbear ssh（逻辑与菜单共用一套，见 ssh_hint.sh）----
SSH_OK=0
if [ -x "$DIR/ssh_hint.sh" ]; then
	sh "$DIR/ssh_hint.sh" --start >>"$LOG" 2>&1 && SSH_OK=1
elif [ -x "$DIR/dropbear/dropbear" ]; then
	chmod +x "$DIR/dropbear/dropbear" "$DIR/dropbear/run.sh" 2>/dev/null
	"$BB" setsid "$DIR/dropbear/run.sh" -F -B -p 22 \
		-r "$DIR/dropbear/dropbear_ed25519_host_key" >>/tmp/db.log 2>&1 </dev/null &
	sleep 2
	ssh_listening && SSH_OK=1
fi

# ---- 2) 兜底：只有 ssh 起不来时才回落到 telnet + ftp ----
TELNET_TRIED=0
if [ "$SSH_OK" = 1 ]; then
	echo "telnet/ftp : SKIP (retired 2026-11-02; ssh:22 is the remote path)" >> "$LOG"
elif [ -x "$DIR/telnetd" ] && [ -x "$BB" ]; then
	TELNET_TRIED=1
	killall -q telnetd 2>/dev/null
	killall -q tcpsvd 2>/dev/null
	killall -q ftpd   2>/dev/null
	sleep 1
	# ---- telnetd (23) ----
	nice -n +10 "$DIR/telnetd" >>"$LOG" 2>&1 &
	# ---- ftpd (21) —— busybox tcpsvd 转发到 ftpd，根目录 = SD 卡 ----
	cd "$SDCARD" 2>/dev/null || cd /
	nice -n +10 "$BB" tcpsvd -u root -vE 0.0.0.0 21 \
		"$BB" ftpd -w -v "$SDCARD" >>"$LOG" 2>&1 &
	sleep 3
else
	echo "!! ssh 未起，telnetd 也不存在 -> 本次没有任何远程通路" >> "$LOG"
	echo "!! 提示: 缺的是 scripts/telnetd（release 包从未包含），应改用 ssh:22" >> "$LOG"
fi

# ---- 结果自检并写日志（★ 用 ps 而非 killall -0，busybox 语义不同）----
{
	echo "--- 结果 ---"
	ssh_listening && echo "ssh(22) : RUNNING" || echo "ssh(22) : DOWN"
	echo "ssh log : $(tail -2 /tmp/db.log 2>/dev/null | tr '\n' ' ')"
	if [ "$TELNET_TRIED" = 1 ]; then
		ps -w 2>/dev/null | grep -E 'telnetd|tcpsvd|ftpd' | grep -v grep
		ps -w 2>/dev/null | grep -q '[t]elnetd' && echo "telnetd : RUNNING" || echo "telnetd : DOWN"
		ps -w 2>/dev/null | grep -qE '[t]cpsvd|[f]tp[d]' && echo "ftp(21) : RUNNING" || echo "ftp(21) : DOWN"
	fi
	# ★ WiFi 接口实测：mlan0 与 lan0 都查（不同固件版本名不同）
	echo "ip(mlan0): $(ip addr ls 2>/dev/null | grep inet | grep mlan0 | cut -d/ -f1 | tr -d ' ')"
	echo "ip(lan0) : $(ip addr ls 2>/dev/null | grep inet | grep  lan0 | cut -d/ -f1 | tr -d ' ')"
} >>"$LOG" 2>&1

exit 0
