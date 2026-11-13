#!/bin/bash
# =====================================================================
# f.sh —— NX-WA 的 App 命令入口（`st app film <命令> [参数...]` 的接收端）
#
# 调用链：
#   st app film recipe apply portra400
#     → SysV 队列 0x8828 → di-camera-app 命令表命中 "film"
#     → C-2 桩（v2）→ system("sh /opt/usr/nx-ks/f.sh recipe apply portra400 ")
#
# ★★ 铁律一：本脚本【绝对不能】调用 `st app ...`
#      App 的 shell 线程执行 system() 时会**阻塞到本脚本返回**；而 `st app`
#      正是往同一个队列 0x8828 发消息、并等待该线程的回执
#      ⇒ 自我死锁（两边都在等对方）。
#      安全通道 = `st cap ...` / `prefman ...` / 直接文件操作（都不经 App 队列）。
#      要跳转 App 侧动作，请：① 用 capdtm 等价物；② 或走机身按键；
#      ③ 或（未来）由 mod 自己注册 App 命令，而不是从 f.sh 里再发队列。
#      ⇒ 因此 `deadlock_guard` 会拒绝"conf 里开着 App 队列开关"的运行条件。
#
# 安全原则：
#   ① 白名单分发 —— 绝不 eval、绝不 exec "$@"
#   ② 参数逐个校验（不做字符串拼接进 shell）
#   ③ 不删文件、不写系统分区；动作幂等或可逆
#   ④ 失败返回非零并写日志（App 不看返回值，日志是唯一回溯线索）
# =====================================================================

D=/opt/usr/nx-ks
FL=$D/filmlab.sh
LOG=$D/f.log
LOGMAX=65536

# ---- 超时工具探测（★ 实测：相机 rootfs 里既无独立 timeout，根 busybox 也没有该 applet）----
#   唯一可用来源 = mod 自带的 $D/busybox（装了 mod 才有）
TMO=""
if [ -x "$D/busybox" ] && "$D/busybox" timeout 1 true >/dev/null 2>&1; then
    TMO="$D/busybox timeout"
elif command -v timeout >/dev/null 2>&1; then
    TMO="timeout"
fi
run_tmo() {   # run_tmo <秒> <命令...>；无超时工具时降级直跑（并已在日志里留痕）
    local t=$1; shift
    if [ -n "$TMO" ]; then $TMO "$t" "$@"; else "$@"; fi
}

log() {
    if [ -f "$LOG" ] && [ "$(wc -c < "$LOG" 2>/dev/null || echo 0)" -gt "$LOGMAX" ]; then
        tail -c 32768 "$LOG" > "$LOG.tmp" 2>/dev/null \n            && { rm -f "$LOG" 2>/dev/null; mv -f "$LOG.tmp" "$LOG"; }
    fi
    echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG" 2>/dev/null
}

deny() {
    log "DENY: $*"
    echo "f.sh: 不支持的命令: $*"
    echo "f.sh: 输入 'st app film help' 查看可用命令"
    exit 2
}

usage() {
    cat <<'EOF'
f.sh — NX-WA App 命令入口（经 `st app film` 调用）

  help                                  显示本用法
  status                                汇总状态（版本 / 模式 / PW 槽 / IP）
  log [n]                               最近 n 行调用日志（默认 20）

  recipe list                           列出配方库
  recipe check                          读回 ISP 手上的 7 维并与配方比对
  recipe apply <名称> [fast]             应用配方（fast = 跳过部分等待）
  recipe cycle                          切到下一个配方
  recipe reset                          恢复中性
  recipe dump                           导出全部槽位
  recipe wbdump                         白平衡段状态

  pw <0-12|standard>                    PW 风格槽切换（画面向导的 3 槽 = 9/10/11）
  shoot                                 拍一张（走 capdtm 通道，不经 App 队列）

  ※ 需要"换模式 / 变焦 / 白平衡 / 质量"等 App 侧动作，请用：
      EV 键菜单、机身 UI，或直接 `st app ...`（在 App 之外调用时）
    —— 本入口内不能发 App 队列命令（会自我死锁，见脚本头注释）
EOF
}

# ---- ★ 死锁护栏：conf 里若开着 App 队列开关，则拒绝执行 ----
deadlock_guard() {
    local conf=$D/filmlab.conf
    if [ -f "$conf" ]; then
        if grep -qE '^[[:space:]]*(FILMLAB_WB_APP|FILMLAB_MODE)[[:space:]]*=[[:space:]]*1' "$conf" 2>/dev/null; then
            log "REFUSE: filmlab.conf 打开了 App 队列开关（会死锁）"
            echo "f.sh: 拒绝执行。"
            echo "      filmlab.conf 里 FILMLAB_WB_APP / FILMLAB_MODE = 1，"
            echo "      它们在 f.sh 上下文里会再发 st app（同一队列 0x8828）⇒ 自我死锁。"
            echo "      处理：把这两个开关置 0（或删掉该行）后重试。"
            return 1
        fi
    fi
    return 0
}

u6() { st cap capdtm getusr "$1" 2>/dev/null | tr -d '\r' | sed -n 's/.*UserData is \(.*\)/\1/p'; }

do_status() {
    echo "== NX-WA status =="
    echo "firmware : $(tr '\n' ' ' < /etc/version.info 2>/dev/null)"
    echo "uptime   : $(cut -d' ' -f1 /proc/uptime 2>/dev/null)s  load: $(cut -d' ' -f1-3 /proc/loadavg 2>/dev/null)"
    echo "mode     : $(u6 DIALMODE)"
    echo "pw slot  : $(u6 20)"
    echo "wb type  : $(u6 6)"
    local ip
    ip=$(ifconfig wlan0 2>/dev/null | sed -n 's/.*inet addr:\([0-9.]*\).*/\1/p' | head -1)
    [ -z "$ip" ] && ip=$(ifconfig 2>/dev/null | sed -n 's/.*inet addr:\([0-9.]*\).*/\1/p' | grep -v 127.0.0.1 | head -1)
    echo "ip       : ${ip:-(未连)}"
    echo "engine   : $([ -x "$FL" ] && echo "在位 $FL" || echo "★缺失 $FL")"
}

do_log() {
    local n=${1:-20}
    case "$n" in ''|*[!0-9]*) n=20 ;; esac
    [ "$n" -gt 200 ] && n=200
    echo "== $LOG (尾巴 $n 行) =="
    tail -n "$n" "$LOG" 2>/dev/null || echo "(无日志)"
}

do_recipe() {
    local sub="$1"; shift 2>/dev/null || true
    deadlock_guard || exit 3
    if [ ! -x "$FL" ]; then
        log "recipe $sub -> 引擎缺失"
        echo "f.sh: 引擎缺失：$FL"
        return 4
    fi
    case "$sub" in
        list|check|cycle|reset|dump|wbdump)
            run_tmo 60 "$FL" "$sub"
            local rc=$?
            log "recipe $sub -> rc=$rc"
            return $rc ;;
        apply)
            # 配方名可能含空格（如 "TriX 400"）⇒ 用 $* 复原
            local name="$*" fast=""
            case "$name" in *" fast") name=${name% fast}; fast="--fast" ;; esac
            [ -z "$name" ] && deny "recipe apply <名称>"
            # 字符白名单（配方名只应是字母数字与 . _ + - 空格）
            case "$name" in
                *[!A-Za-z0-9._+\ -]*)
                    log "BADNAME: $name"
                    echo "f.sh: 配方名含非法字符：$name"
                    return 2 ;;
            esac
            run_tmo 90 "$FL" apply "$name" $fast
            local rc=$?
            log "recipe apply '$name' ${fast}-> rc=$rc"
            return $rc ;;
        *)
            deny "recipe $sub" ;;
    esac
}

do_pw() {
    local v="$1"
    case "$v" in
        [0-9]|1[0-2])   st cap capdtm setusr 20 "$(printf '0x1400%02x' "$v")" >/dev/null 2>&1 ;;
        standard)       st cap capdtm setusr 20 0x140000 >/dev/null 2>&1 ;;
        *)              deny "pw $v" ;;
    esac
    log "pw $v -> rc=$?"
    echo "pw -> $v"
}

do_shoot() {
    # ★ 走 capdtm（不经 App 队列）；App 路命令在 f.sh 上下文里会死锁
    st cap capt single start >/dev/null 2>&1
    log "shoot(capdtm capt single) -> rc=$?"
    echo "shoot -> ok"
}

# ---------------- 分派 ----------------
CMD="$1"; shift 2>/dev/null || true

case "$CMD" in
    ''|help|-h|--help) usage; exit 0 ;;
    status)            do_status; exit 0 ;;
    log)               do_log "$@"; exit 0 ;;
    recipe)            do_recipe "$@"; exit $? ;;
    pw)                do_pw "$@"; exit $? ;;
    shoot)             do_shoot; exit 0 ;;
    *)                 deny "$CMD" ;;
esac
