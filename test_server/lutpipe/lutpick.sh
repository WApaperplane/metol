#!/bin/sh
# @gate script=lutpick.sh opens=rw one_shot=1 gate=cmasafe
# =====================================================================
# lutpick.sh — FilmLab LUT 选择器（相机端）★ LUT 链路的产品化入口
# =====================================================================
# 需求映射（「可选 / 可导入 / 显示 / 照片」四件套的相机端实现）：
#   · 可选    : apply <name> 切换 LUT；off 关闭（identity）；list 列目录
#   · 可导入  : PC 侧 deploy_luts.py（.cube → 原生表 → 推送至 luts/）
#   · 显示    : apply = cmapick → cmasafe 四查 → lutapi load（sel=0）
#               取景器【秒级】变化（View 探针）
#   · 照片    : 表进的是硬件 LUT0（View/Still 共用池）——成片是否跟随由
#               U6 runbook §[6] 拍片实验定论；若被 p7 抢回，保底走 ksfilm 后处理
#
# 目录约定（相机端）：
#   /mnt/mmc/filmlab/luts/         ← 表文件 *.bin（19652 或 19712 字节）
#   /mnt/mmc/filmlab/luts/current  ← 软件记账（上次 apply 的名字；非硬件读回）
#   工具（同 /opt/usr/nx-ks/）：cmasafe.arm / cmapick2.arm / lutapi.arm
#
# 子命令（一次只跑一条）：
#   list                     列可用 LUT + 当前记账
#   apply <name> [--dry] [--ch0|--ch1]   应用一个 LUT（默认 sel=0）
#       --dry : 只做落点探测与安全闸，不 load
#       --ch1 : sel=1 双通道装载（★ 抗 p7 抢回；需先通过 E1 实验）
#   off [--dry]              关闭（加载 _identity 表；等价"不加 LUT"）
#   sentinel start|stop|status     抢回守护（监视 Cfg.SelLUT，被写回 0 时恢复为 1）
#   status                   只读：列目录 + 记账 + 提示
#
# 纪律（继承 U6 安全设计）：
#   * 落点只认 cmapick 的「4KB 粒度命中」行；无该行 = 拒绝（防 0x94000000 事故族）
#   * load 前必过 cmasafe（CMA 范围/黑名单/对齐/全零 四查）
#   * 一次调用只处理一个表；失败不重试
# =====================================================================

D=${NXWA_MOD_ROOT:-/opt/usr/nx-ks}
BB=${NXWA_BUSYBOX:-$D/busybox}
LUTS=${NXWA_LUT_DIR:-${NXWA_LUT_MOD:-/mnt/mmc/filmlab}/luts}
CUR=$LUTS/current
CURSEL=$LUTS/current.sel
# 工具：优先 SD 自包含（与 deploy_luts.py 推送落点一致），fallback /opt 部署版
MOD=${NXWA_LUT_MOD:-/mnt/mmc/filmlab}
[ -x "$MOD/cmasafe.arm" ] || MOD=$D
CMAP=$MOD/cmapick2.arm
SAFE=$MOD/cmasafe.arm
API=$MOD/lutapi.arm
SENT=$MOD/lutsentinel.arm
SLOG=$LUTS/sentinel.log
SPID=$LUTS/sentinel.pid
LOG=$LUTS/last_apply.log

[ -x "$BB" ] || { echo "ERR: 缺 busybox"; exit 1; }
"$BB" mkdir -p "$LUTS"

need_tools() {
  for t in "$CMAP" "$SAFE" "$API"; do
    [ -x "$t" ] || { echo "ERR: 缺工具 $t（用 deploy_luts.py 推送）"; exit 1; }
  done
}

tbl_of() {
  # 接受 <name> 或 <name>.bin；兼容 _slot 变体
  for n in "$LUTS/$1.bin" "$LUTS/$1_slot.bin" "$LUTS/$1"; do
    [ -f "$n" ] && { echo "$n"; return 0; }
  done
  return 1
}

do_load() {
  TBL=$1
  # 1) 落点探测（只读）
  echo ">>> [1/3] cmapick2 探测落点（只读）"
  "$CMAP" --need19652 > "$LOG.cmapick" 2>&1
  RC=$?
  if [ $RC -ne 0 ]; then
    echo "★★ cmapick 无落点（rc=$RC）—— 此刻 load 必然卡死整机，中止。"
    echo "   退出拍摄态让 ISP 释放后重试。"
    exit 2
  fi
  HIT=$("$BB" grep "4KB 粒度命中" "$LOG.cmapick" | "$BB" head -n 1)
  [ -z "$HIT" ] && {
    echo "★★ 无『4KB 粒度命中』行（拒绝用区起点——0x94000000 事故族）"; exit 3; }
  ADDR=$("$BB" echo "$HIT" | "$BB" sed -n 's/.*\(0x[0-9a-f]*\) 起.*/\1/p')
  [ -z "$ADDR" ] && { echo "★★ 地址解析失败: $HIT"; exit 3; }
  echo "    落点 = $ADDR"

  "$BB" sleep 5    # 段间缓冲（单核让出）

  # 2) 安全闸（只读四查）
  echo ">>> [2/3] cmasafe 安全闸"
  "$SAFE" "$ADDR" || { echo "★★ 安全闸拒绝 —— 未做任何写入。"; exit 4; }

  if [ "$DRY" = "1" ]; then
    echo ">>> [3/3] --dry：跳过 load（闸已通过，落点可用）"
    return 0
  fi

  # 3) load（官方 API；--ch0/--ch1 选择通道；均不证明 Still 成片生效）
  echo ">>> [3/3] lutapi load（sel=$SEL fmt=1 cbcr=0 settle=300）"
  "$API" load "$TBL" "$ADDR" "$SEL" 1 17 2 300 0 > "$LOG" 2>&1
  RC=$?
  "$BB" cat "$LOG" | "$BB" tail -n 20
  echo "lutapi rc=$RC"
  return $RC
}

usage() {
  echo "用法: lutpick.sh list | status"
  echo "      lutpick.sh apply <name> [--dry] [--ch0|--ch1]   # 默认 sel=0；--ch1 请求 sel=1"
  echo "      lutpick.sh off [--dry]                    # 加载 identity（画面回中性）"
  echo "      lutpick.sh sentinel start|stop|status     # 抢回守护（配合 --ch1）"
  echo "  表目录: $LUTS"
}

CMD=$1
NAME=$2
SEL=0
DRY=0
SEEN_CHANNEL=0
case "$CMD" in
apply|off)
  if [ "$CMD" = apply ]; then
    [ "$#" -ge 2 ] || { usage; exit 1; }
    shift 2
  else
    shift
  fi
  for opt in "$@"; do
    case "$opt" in
      --dry) DRY=1 ;;
      --ch0|--ch1)
        [ "$SEEN_CHANNEL" = 0 ] || { echo "ERR: 重复或冲突的通道选项"; exit 1; }
        SEEN_CHANNEL=1
        [ "$opt" = --ch1 ] && SEL=1
        ;;
      *) echo "ERR: 未知选项 $opt"; exit 1 ;;
    esac
  done
  ;;
esac

case "$CMD" in

list|status)
  echo "=== LUT 目录：$LUTS ==="
  N=0
  for f in "$LUTS"/*.bin; do
    [ -f "$f" ] || continue
    B=$("$BB" basename "$f")
    SZ=$("$BB" wc -c < "$f" 2>/dev/null | tr -d ' ')
    echo "  $B  ($SZ B)"
    N=$((N + 1))
  done
  [ $N -eq 0 ] && echo "  （空 —— 用 PC 侧 deploy_luts.py 推送 .cube 转换的表）"
  echo "  共 $N 个表"
  if [ -f "$CUR" ]; then
    echo "  当前记账: $("$BB" cat "$CUR")  （软件记账，非硬件读回）"
  else
    echo "  当前记账: （无）"
  fi
  if [ "$CMD" = "status" ]; then
    echo
    echo "★ 取景器判据：load 后 1-2 秒内画面应变化；半按快门可能让 p7 重载原厂表"
    echo "  （正常现象）；『照片是否跟随』见 U6 runbook 拍片实验。"
  fi
  ;;

apply)
  [ -z "$NAME" ] && { usage; exit 1; }
  need_tools
  TBL=$(tbl_of "$NAME") || { echo "★ 表不存在：$NAME（先 lutpick.sh list）"; exit 1; }
  echo "=== lutpick apply：$TBL ==="
  do_load "$TBL"
  RC=$?
  if [ $RC -eq 0 ] && [ "$DRY" != "1" ]; then
    "$BB" echo "$NAME" > "$CUR"
    "$BB" echo "$SEL" > "$CURSEL"
    echo "★ 已应用 '$NAME'（记账已更新）。看取景器确认；"
    echo "  ★ 不半按快门则保持；拍片实验见 U6 runbook。"
  fi
  exit $RC
  ;;

off)
  need_tools
  TBL=$(tbl_of "_identity")
  if [ -z "$TBL" ]; then
    echo "★ 缺 _identity.bin（部署时由 deploy_luts.py 自动生成）；"
    echo "  备选：lutload.arm restore + 半按快门（恢复出厂表指针）"
    exit 1
  fi
  echo "=== lutpick off：加载 identity（画面回中性）==="
  do_load "$TBL"
  RC=$?
  [ $RC -eq 0 ] && [ "$DRY" != "1" ] && "$BB" echo "(off)" > "$CUR"
  [ $RC -eq 0 ] && [ "$DRY" != "1" ] && "$BB" echo "$SEL" > "$CURSEL"
  exit $RC
  ;;

sentinel)
  # ★ 抢回守护（双通道方案）：监视 Cfg.SelLUT，被 p7 写回 0 时恢复为 1。
  #   前置：表须以 --ch1（sel=1）装载（守护只改 Cfg，不重灌表）。
  case "$NAME" in
    start)
      [ -x "$SENT" ] || { echo "★ 缺 $SENT（deploy_luts.py 推送）"; exit 1; }
      OLD=$("$BB" ps 2>/dev/null | "$BB" grep lutsentinel | "$BB" grep -v grep | "$BB" awk '{print $1}' | "$BB" head -1)
      [ -n "$OLD" ] && { echo "已在运行 pid=$OLD"; exit 0; }
      /usr/bin/setsid "$SENT" --sel 1 --interval 500 > "$SLOG" 2>&1 < /dev/null &
      "$BB" sleep 1
      PID=$("$BB" ps 2>/dev/null | "$BB" grep lutsentinel | "$BB" grep -v grep | "$BB" awk '{print $1}' | "$BB" head -1)
      if [ -n "$PID" ]; then
        "$BB" echo "$PID" > "$SPID"
        echo "lutsentinel 已起 pid=$PID（日志 $SLOG）"
        echo "★ 提醒：停止用 lutpick.sh sentinel stop；状态用 sentinel status"
      else
        echo "★ 未检测到进程——读日志："; "$BB" cat "$SLOG" 2>/dev/null | "$BB" head -5
        exit 1
      fi
      ;;
    stop)
      PID=$("$BB" ps 2>/dev/null | "$BB" grep lutsentinel | "$BB" grep -v grep | "$BB" awk '{print $1}')
      if [ -n "$PID" ]; then
        for p in $PID; do "$BB" kill "$p" 2>/dev/null; done
        echo "lutsentinel 已停（pid: $PID）"
      else
        echo "未在运行"
      fi
      "$BB" rm -f "$SPID"
      ;;
    status|"")
      PID=$("$BB" ps 2>/dev/null | "$BB" grep lutsentinel | "$BB" grep -v grep | "$BB" awk '{print $1}')
      if [ -n "$PID" ]; then echo "运行中 pid=$PID"; else echo "未运行"; fi
      echo "---- 最近日志 ----"
      "$BB" tail -n 8 "$SLOG" 2>/dev/null || echo "（无日志）"
      ;;
    *)
      echo "用法: lutpick.sh sentinel start|stop|status"; exit 1 ;;
  esac
  ;;

*)
  usage
  exit 1
  ;;
esac
