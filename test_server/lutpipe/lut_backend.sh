#!/bin/sh
# @gate script=lut_backend.sh opens=rw one_shot=1 gate=cmasafe
# =====================================================================
# lut_backend.sh — LUT 预览后端（T5 产品化 v1 · 2026-10-16）
#
#   定位：把 LUT1 预览链封装为符合 T2 协议的**适配器后端**
#         （probe / apply / rollback / status），供统一控制器调用。
#
#   ★ 关闭语义（依 FILMLAB_LUT_NATIVE_UI_GOALS §3，T1 §4）：
#       rollback = **停守护 + 恢复出厂表指针**（lutload.arm restore）
#       —— 绝不以「加载数学 identity 表」冒充关闭。
#       ⚠ 注意：现有 `lutpick.sh off` 的实现是「加载 _identity 表」
#       （LUT_PIPELINE §3.2），**语义上 ≠ 关闭**；本后端走 factory 路径。
#
#   ⛔ 禁 restart（卡死整机）；apply 前需前置「抢回态」（先对焦一次；U6 §2 规律）
#
#   用法（相机端）：
#     sh lut_backend.sh probe
#     sh lut_backend.sh apply <表名> [--sel 0|1] [--dry]
#     sh lut_backend.sh rollback
#     sh lut_backend.sh status
#   输出：stdout = 单行 JSON（供控制器解析）；人类可读信息走 stderr。
#   v1 · 2026-10-16 · 离线编写（未上机验证）
# =====================================================================

D=${NXWA_MOD_ROOT:-/opt/usr/nx-ks}
BB=$D/busybox
[ -x "$BB" ] || BB=/bin/busybox
[ -x "$BB" ] || BB=$(command -v busybox 2>/dev/null)
[ -x "$BB" ] || BB=""                    # 无 busybox ⇒ RUNNER 退化为系统 sh
if [ -n "$BB" ]; then RUNNER="$BB sh"; else RUNNER="sh"; fi
MOD=${NXWA_LUT_MOD:-/mnt/mmc/filmlab}
[ -d "$MOD" ] || MOD=$D
PICK=$MOD/lutpick.sh
LUTS=$MOD/luts
# ★ 上机实测（10-16）：工具实际部署在 SD $MOD/，不在 $D/（/opt/usr/nx-ks/）
LOAD=$D/lutload.arm
[ -f "$LOAD" ] || LOAD=$MOD/lutload.arm
SENTPID=$LUTS/sentinel.pid

log(){ echo "$*" >&2; }

jstr(){ printf '"%s"' "$(printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g')"; }
has(){ [ -f "$1" ] && printf 1 || printf 0; }

guard_state(){
    # 1 = 守护在跑（以 pid 文件或进程名判断）
    if [ -f "$SENTPID" ] && kill -0 "$(cat "$SENTPID" 2>/dev/null)" 2>/dev/null; then
        echo 1; return
    fi
    if pidof lutsentinel.arm >/dev/null 2>&1; then echo 1; return; fi
    if ps 2>/dev/null | grep -q "[l]utsentinel"; then echo 1; return; fi
    echo 0
}

cmd_probe(){
    n=0
    if [ -d "$LUTS" ]; then
        n=$(ls "$LUTS" 2>/dev/null | grep -c '\.bin$')
    fi
    printf '{"ok":true,"tools":{"cmasafe":%s,"cmapick2":%s,"lutapi":%s,"lutload":%s,"lutsentinel":%s,"lutpick":%s},"luts_count":%s,"guard":%s,"precondition":"apply 前需前置抢回态（先对焦一次）"}\n' \
        "$(has "$MOD/cmasafe.arm")" "$(has "$MOD/cmapick2.arm")" "$(has "$MOD/lutapi.arm")" \
        "$(has "$LOAD")" "$(has "$MOD/lutsentinel.arm")" "$(has "$PICK")" "$n" "$(guard_state)"
}

cmd_apply(){
    name=$1; dry=""; sel=1; sel_seen=0
    [ -n "$name" ] || { printf '{"ok":false,"level":"failed","error":"no_name"}\n'; return 1; }
    shift
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --dry) dry=--dry; shift ;;
            --sel)
                [ "$sel_seen" = 0 ] && [ "$#" -ge 2 ] || { printf '{"ok":false,"level":"failed","error":"invalid_option"}\n'; return 1; }
                case "$2" in 0|1) sel=$2 ;; *) printf '{"ok":false,"level":"failed","error":"invalid_sel"}\n'; return 1 ;; esac
                sel_seen=1; shift 2 ;;
            *) printf '{"ok":false,"level":"failed","error":"invalid_option"}\n'; return 1 ;;
        esac
    done
    case "$name" in
        *[!a-zA-Z0-9_.-]*|.|..) printf '{"ok":false,"level":"failed","error":"invalid_name"}\n'; return 1 ;;
    esac
    [ -f "$PICK" ] || { printf '{"ok":false,"level":"failed","error":"lutpick_missing"}\n'; return 1; }
    [ -f "$LUTS/$name.bin" ] || { printf '{"ok":false,"level":"failed","error":"table_not_found","table":%s}\n' "$(jstr "$name")"; return 1; }
    # Existing sentinel changes Cfg only; it cannot protect LUT0 contents from a P7 reload.
    # A running LUT1 guard would also undo a deliberate sel=0 request.
    if [ "$sel" = 0 ] && [ "$(guard_state)" = 1 ]; then
        printf '{"ok":false,"level":"failed","error":"guard_conflict","sel_requested":0}\n'
        return 1
    fi
    [ -f "$LUTS/_identity.bin" ] || log "(提示：无 _identity.bin；诊断表缺省)"

    log "-- apply $name ${dry:+($dry)}（sel=$sel 通道；成片待验）--"
    channel=--ch1
    [ "$sel" = 0 ] && channel=--ch0
    if [ "$dry" = "--dry" ]; then
        out=$($RUNNER "$PICK" apply "$name" "$channel" --dry 2>&1); rc=$?
    else
        out=$($RUNNER "$PICK" apply "$name" "$channel" 2>&1); rc=$?
    fi
    echo "$out" | sed 's/^/  /' >&2
    if [ "$rc" = "0" ]; then
        printf '{"ok":true,"level":"full","table":%s,"sel":%s,"sel_requested":%s,"hardware_verified":false,"still_verified":false,"guard":%s,"dry":%s,"note":"sel 为请求通道；dry=true 仅探测，其余为加载命令返回成功；守护未自动启动，画面与成片另验"}\n' \
            "$(jstr "$name")" "$sel" "$sel" "$(guard_state)" "$([ "$dry" = "--dry" ] && echo true || echo false)"
    else
        printf '{"ok":false,"level":"failed","table":%s,"rc":%s,"error":"lutpick_apply_failed"}\n' "$(jstr "$name")" "$rc"
    fi
    return "$rc"
}

cmd_rollback(){
    # ★ 关闭 = 停守护 + 恢复出厂表；不写 identity
    g=$(guard_state)
    if [ "$g" = "1" ]; then
        log "-- 停止守护 lutsentinel --"
        if [ -f "$SENTPID" ]; then
            kill "$(cat "$SENTPID" 2>/dev/null)" 2>/dev/null
            rm -f "$SENTPID"
        fi
        if [ -n "$BB" ]; then "$BB" pkill -f lutsentinel.arm 2>/dev/null; else pkill -f lutsentinel.arm 2>/dev/null; fi
    fi
    rc_r=255
    if [ -f "$LOAD" ]; then
        log "-- 恢复出厂表（lutload.arm restore）--"
        "$LOAD" restore >/dev/null 2>&1; rc_r=$?
    else
        log "!! 缺 lutload.arm —— 无法恢复出厂表（请用 SD 重刷/重启兜底）"
    fi
    g_after=$(guard_state)
    ok=false
    if [ "$rc_r" = "0" ] && [ "$g_after" = "0" ]; then
        ok=true
        rm -f "$LUTS/current"
        rm -f "$LUTS/current.sel"
    fi
    printf '{"ok":%s,"path":"factory_restore","identity_used":false,"hardware_verified":false,"guard_stopped":%s,"restore_rc":%s,"note":"恢复命令返回结果，原厂画面另验（非 identity）"}\n' \
        "$ok" "$([ "$g_after" = "0" ] && echo true || echo false)" "$rc_r"
    [ "$ok" = true ]
}

cmd_status(){
    cur=""; requested=null
    [ -f "$LUTS/current" ] && cur=$(cat "$LUTS/current" 2>/dev/null)
    if [ -n "$cur" ] && [ -f "$LUTS/current.sel" ]; then
        stored=$(cat "$LUTS/current.sel" 2>/dev/null)
        case "$stored" in 0|1) requested=$stored ;; esac
    fi
    printf '{"ok":true,"guard":%s,"current":%s,"sel":null,"sel_requested":%s,"hardware_verified":false,"note":"current 与 sel_requested 为软件记账；sel 未读取硬件"}\n' \
        "$(guard_state)" "$(jstr "$cur")" "$requested"
}

case "$1" in
    probe)    cmd_probe ;;
    apply)    shift; cmd_apply "$@" ;;
    rollback) cmd_rollback ;;
    status)   cmd_status ;;
    *)        printf '{"ok":false,"error":"usage: lut_backend.sh probe|apply <name> [--sel 0|1] [--dry]|rollback|status"}\n'; exit 2 ;;
esac
