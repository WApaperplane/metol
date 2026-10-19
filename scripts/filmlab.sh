#!/bin/sh
#=====================================================================
# filmlab-apply.sh  —  FilmLab SD 卡配方引擎 v2（2026-10-10：全 7 维 id + apply --fast 提速）
# 2026-10-17: apply/preview/commit without a slot now follow the current PW
# field, including built-in fields. A2's forced CUSTOM1 selection is restored
# after each send; first-use parameter backups live in filmlab/slot-backups/.
#---------------------------------------------------------------------
# 设计前提（2026-10-04 实机定案）：
#   · 配方库在 SD 卡（/mnt/mmc/filmlab/recipes.json），数量不限
#   · prefman只有 4 个 CUSTOM 槽（CUSTOM_1/2/3/4 = slot 9/10/11/12）
#     → 槽位不是配方，而是"当前选中项"
#   · prefman set 不需 save 即实时生效（已实机验证）
#   · prefman load -a 0 会【覆盖】刚 set 的值，绝对不要用
#   · setusr 20 <enum> 切风格，零延迟
#
# 用法：
#   sh filmlab-apply.sh list                    列出 SD 卡全部配方
#   sh filmlab-apply.sh show   <recipe>         打印配方内容
#   sh filmlab-apply.sh apply  <recipe> [slot]  写槽 + 切风格（实时生效）
#   sh filmlab-apply.sh quick  <recipe>         只切风格（槽已预写时用，零写入）
#   sh filmlab-apply.sh dump   [slot]           读回槽位当前值
#   sh filmlab-apply.sh preset                 把 preset 段写进 3 个可见槽
#   sh filmlab-apply.sh slots                  列出槽位占用
#   sh filmlab-apply.sh mkgui                  ★ 从 SD 卡配方库生成 mod_gui 菜单页
#   sh filmlab-apply.sh neutral                面板「还原」：直推中性值（不写槽、不落盘）
#=====================================================================
# ★ mod_gui 集成（2026-10-04 定案）
#   mod_gui 菜单格式 = 纯文本 `button|标签|命令`，`@` 前缀开子菜单，
#   末两行固定「返回|@<上级>」和「取消|<gui_exit.sh>」，2 列网格上限约 24 个按钮。
#   ★★ 因此"配方数不限"必须靠动态生成菜单才成立 —— 手写菜单就是死的。
#   mkgui 读 SD 卡 recipes.json 的 label，按钮上限 22（给返回/取消留位）。
#   在 EV_EV.sh（mod_gui 入口）里先跑 mkgui 再起 mod_gui → 菜单与 SD 卡永远同步。
#=====================================================================

BB=/opt/usr/nx-ks/busybox
LAB=/mnt/mmc/filmlab
RECIPE=$LAB/recipes.json
LOG=$LAB/last.log

# ---- 外置设置数据（filmlab.conf；2026-10-09）----
#   「校准结果 / 开关 / 通道参数」等【数据】放这里 ⇒ 改数据不改脚本。
#   管理工具（PC 侧）：python test_server/filmlab/flab.py conf --set K=V …  + deploy --conf
#   格式：KEY=VALUE 每行一条（busybox sh 可直接 . source）。
#   优先级：conf（持久配置）> 环境变量 > 脚本默认；下方 ${VAR:-默认} 不覆盖已设值。
#   ★ 逃生门：临时调试想用 env 覆盖时，前缀 FILMLAB_NO_CONF=1 跳过 conf。
if [ -z "${FILMLAB_NO_CONF:-}" ] && [ -f "$LAB/filmlab.conf" ]; then
  . "$LAB/filmlab.conf" 2>/dev/null
fi

# ---- prefman 布局（★ 来自 prefman info 0 的官方命名表，4/4 对齐已验证）----
PW_BASE=41964          # 0xa3ec = APPPREF_EFFECT_STANDARD_R_COLOR
PSTEP=52               # 参数步进（R=0 G=1 B=2 HUE=3 SAT=4 SHARP=5 CON=6）
SSTEP=4                # 风格步进

# ---- WB (★全部来自 prefman info 0 官方命名表，勿凭记忆写) ----
WB_TYPE=41872         # 0x0a390  APPPREF_WB_TYPE
WB_K=41876            # 0x0a394  APPPREF_WB_K_VALUE (Kelvin)
WB_CUSTOM_BA=41916    # 0x0a3bc  APPPREF_WB_CUSTOM_DETAIL_BA_XY (tint 打包)
WB_MANUAL_BA=41920    # 0x0a3c0  APPPREF_WB_K_DETAIL_BA_XY  (K 模式的 tint)
CWB_R=41924           # 0x0a3c4  APPPREF_CWB_RED
CWB_G=41928           # 0x0a3c8  APPPREF_CWB_GREEN
CWB_B=41932           # 0x0a3cc  APPPREF_CWB_BLUE

# ---- WB_TYPE 枚举（setusr 6 实机扫出的真值表，14:58 定案）----
#  0=WB_AUTO          1=WB_AUTO_TUNGSTEN  2=WB_DAYLIGHT  3=WB_CLOUDY
#  4=WB_FLUORESCENTW  8=WB_FLASH          9=WB_CUSTOM
# 10=WB_MANUAL   ← ★ K 值只在这个模式下生效
# 11+ 被拒 (not set -1)
WB_MANUAL=10
TINT_NEUTRAL_A=7
TINT_NEUTRAL_B=7

# ---- slot <-> enum 映射（★ 实机特征色验证 + 命名表双重确认）----
# UI 显示:setusr enum : prefman slot : DATA ID
#   自定义1     9        9        0x140009
#   自定义2     10       10       0x14000a
#   自定义3     12       11       0x14000c   ← enum 与 slot 错位 1！
#   (隐藏)      —        12       —          ← CUSTOM_4 在 prefman 里存在但 UI 不显示
#   enum 11 (0x14000b) 被拒 "not set -1"，是空洞

set_r() { prefman set 0 "$(printf 0x%05x $((PW_BASE + $1 * PSTEP + $2 * SSTEP)))" l "$3" >/dev/null 2>&1; }
get_r() { prefman get 0 "$(printf 0x%05x $((PW_BASE + $1 * PSTEP + $2 * SSTEP)))" l 2>/dev/null \
          | tr -d '\r' | sed -n 's/.*value = \([-0-9]*\).*/\1/p'; }
# ★ 原子写入白平衡：TYPE + K + tint 三项一起，中间不留半成品状态
# 用法: set_wb <K> <tint_a> <tint_b> [manual|auto|keep]
#   manual(默认) → 切WB_MANUAL，K 生效
#   auto         → 切 WB_AUTO，K 被忽略（相机自动）
#   keep         → 不动 WB_TYPE，只写 K 与 tint
# ★ 顺序关键：先切模式（决定 K 是否被采用），再写 K，最后写 tint。
#   顺序反了会出现"模式已是manual 但 K 还是旧值"的窗口。
# ---- ★ [同构 批次2] WB 模式写入：双路可切换（默认原路；FILMLAB_WB_APP=1 走 App 命令）----
#   依据 docs/current/SHELL_TO_APP_ISOMORPHISM_2026-10-12.md §4 批次 2
#   App 侧: `st app nx capture wb <name>` → cmd_set_white_balance → cmd_set_menu_option(0xd3, enum)
#     App 名 → enum: (无参)=0  auto-tungsten=1  tungsten=2  day=3  cloud=4
#                    fluorescent-w=5  fluorescent-n=6  fluorescent-d=7  flash=8  custom=9
#   ★ 与本地 WB_TYPE 真值表（0/1/2/3/4/8/9/10）存在 ±1 错位疑点
#     ⇒ 默认【仍走原路】，上机跑 test_server/dicam/wb_compare.sh 对照读回值后再决定是否切默认。
wb_set_mode() {     # $1 = manual | auto
    if [ "${FILMLAB_WB_APP:-0}" = "1" ]; then
        case "$1" in
            manual) st app nx capture wb custom >/dev/null 2>&1 && return 0 ;;
            auto)   st app nx capture wb        >/dev/null 2>&1 && return 0 ;;
        esac
    fi
    case "$1" in
        manual) st cap capdtm setusr 6 0x06000a >/dev/null 2>&1 ;;
        auto)   st cap capdtm setusr 6 0x060000 >/dev/null 2>&1 ;;
    esac
}

set_wb() {
  K=$1; A=$2; B=$3; MODE=${4:-manual}
  case $MODE in
    manual) prefman set 0 "$(printf 0x%05x $WB_TYPE)" l "$WB_MANUAL" >/dev/null 2>&1
            wb_set_mode manual ;;
    auto)   wb_set_mode auto ;;
    keep)   ;;
  esac
  [ -n "$K" ] && [ "$K" != "0" ] && prefman set 0 "$(printf 0x%05x $WB_K)" l "$K" >/dev/null 2>&1
  BA=$(( (A << 16) | B ))
  prefman set 0 "$(printf 0x%05x $WB_MANUAL_BA)" l "$BA" >/dev/null 2>&1
  prefman set 0 "$(printf 0x%05x $WB_CUSTOM_BA)" l "$BA" >/dev/null 2>&1
}
get_wb()      { prefman get 0 "$(printf 0x%05x $WB_K)" l 2>/dev/null | tr -d '\r' | sed -n 's/.*value = \([-0-9]*\).*/\1/p'; }
get_wb_type() { prefman get 0 "$(printf 0x%05x $WB_TYPE)" l 2>/dev/null | tr -d '\r' | sed -n 's/.*value = \([-0-9]*\).*/\1/p'; }
get_tint()    { V=$(prefman get 0 "$(printf 0x%05x $WB_MANUAL_BA)" l 2>/dev/null | tr -d '\r' | sed -n 's/.*value = \([-0-9]*\).*/\1/p');
                echo "A=$(( (V >> 16) & 0xffff )) B=$(( V & 0xffff ))"; }
get_wb() { prefman get 0 "$(printf 0x%05x $WB_K)" l 2>/dev/null | tr -d '\r' | sed -n 's/.*value = \([-0-9]*\).*/\1/p'; }

# =====================================================================
# ★★★ PW「画面生效」—— 上机实测定论（2026-10-08 夜，NX500 v1.12）
# ---------------------------------------------------------------------
# 三条独立通道，缺第 ③ 条画面就不会变；而 ③ **`st` 命令面够不到**：
#
#   ① 存储  prefman set 0 0xa3ec…        ⇒ 只改 Linux 侧偏好存储（槽位 RAM 副本）
#   ② 选择  setusr 20 0x14000N          ⇒ 只改 eIQ_ID_EFFECT_MODE（"选哪个风格"）
#   ③ 参数  PW 引擎手里的 7 维副本        ⇒ ★ 只有它能改变画面
#                                        只有 di-camera-app 的"画面向导确认"会推它
#
# ★ 实测证据（2026-10-08，客观判据 = `st cap capdtm varlist` 的 PW 变量）：
#   apply trix400 后：prefman slot9 = 100/100/100 10/0/13/12（读回确认已写）
#                     但 ISP 的 VARIABLE_PWCOLOR_R/G/B 与 PWSATURATION **纹丝不动**
#                     （仍是上一套 88/112/125 / SAT偏移5）
#   加 prefman save 0 + sync 后：仍不动。
#   ⇒ 结论：① ② save 全都不搬参数；③ 只能由 app 的 PW 菜单确认触发。
#   ⇒ setvar 这条路也不通：varlist 显示下标 ≠ setvar/getvar 的 id（id 运行时注册），
#     而历史记录里"盲扫 id"直接写死过 p7 capture 服务 ⇒ 【本项目禁止再试】。
#
# ★ 与 3D LUT 同源：app 推参数走的是【属性总线】
#     CAttributeHandler::setPWColor/Saturation/Sharpness/Contrast
#       → set_attribute(0x10e/0x110/0x111/0x112, &v, 4)
#   该总线不在 `st cap` 里（capdtm 只有 setusr/getusr/setvar/getvar/usrlist/varlist 六个子命令）。
#
# ⇒ 本引擎的立场（诚实版，2026-10-09 更新）：
#   · ① 写槽 + prefman save（持久化；★ 不 save 则重启回退，实测过）
#   · ② 借道切到目标槽（保证"选择"真的发生，虽然它不搬参数）
#   · ③ **已打通（10-10 全 7 维 id 已解）**：属性总线传输层全解
#        （docs/current/ATTR_BUS_MCB_2026-10-09.md + PW_ID_MAP_FULL_2026-10-10.md；
#         A2 通道见 docs/current/A2_PATCH_DESIGN_2026-10-14.md + A2_READBACK_VERDICT_2026-10-15.md）：
#        set_var(id) == SetVariableDataMCB(id,&v,4) → MCB → p7 → ISP。
#        工具 `pwsend.arm`（白名单 [0x100,0x13e]）。
#        ★ 10-15 A2 通道（档位池直写，功能验证 PASS）：全 7 维一键 = seq 0x134..0x13A（原始值）
#          + 0x13B 触发 → p7 写槽 0xdc..0xe2 → 全 8 项下发 ISP。**当前全维通路**。
#        ★ 旧记录（A1/三维时代，保留备查）：可外部直推 = SAT/SHARP/CON（0x110-0x112 经归一化）；
#          R/G/B/HUE（0x130-0x133）曾无外部通路（归一化器域界）——A2 前需改 p7 或走画面向导。
#        ⇒ 置 FILMLAB_PW=1 即得【全 7 维一键】：点配方 → 七维直进 ISP → 画面立即变。
#        ★ 官方画面向导仍是保底链路（重选一遍即恢复）。
#   · check 判据（只读）永远保留：ISP 手上的 7 维 vs prefman 槽位，一眼看出进没进。
# =====================================================================

FILMLAB_MODE=${FILMLAB_MODE:-0}     # 1 = 保留旧的「切模式」触发（默认关）
FILMLAB_SAVE=${FILMLAB_SAVE:-1}     # 1 = apply 后 prefman save（默认开；否则重启回退）
FILMLAB_MID=${FILMLAB_MID:-custom}  # custom(默认)=借道另一个自定义槽 | standard=旧行为

# ---- ③ PW 直推（2026-10-09 新增；校准前默认关）----
PWSEND=${PWSEND:-/opt/usr/nx-ks/pwsend.arm}
FILMLAB_PW=${FILMLAB_PW:-0}         # 1 = apply 后自动直推（★ 10-15 A2 通道后无需 pwcalib 校准）
# ★ 10-15 A2 通道（当前生效路径）：pw_direct 固定发 0x134..0x13B（原始值 + 触发），
#   不再使用下方 PWID_*/编码（保留兼容：旧 conf 里的 PWID_* 将被忽略）。
# ★ 旧 id 表（10-10 上机定案，保留备查，PW_ID_MAP_FULL_2026-10-10.md §6）：
#   S/P/C 三维 = 外部 id 0x110/0x111/0x112（经 p7 归一化 → 内部 SAT/SHARP/CON）【已实测】。
#   R/G/B/HUE = 内部 id 0x130-0x133 曾无外部 MCB 通路（A2 前；归一化器域界）。
PWID_R=${PWID_R:-}        # 旧路遗留（A2 后不参与）
PWID_G=${PWID_G:-}        # 旧路遗留
PWID_B=${PWID_B:-}        # 旧路遗留
PWID_H=${PWID_H:-}        # 旧路遗留
PWID_S=${PWID_S:-0x110}   # 旧路遗留（PWSATURATION）
PWID_P=${PWID_P:-0x111}   # 旧路遗留（PWSHARPNESS）
PWID_C=${PWID_C:-0x112}   # 旧路遗留（PWCONTRAST）
# 旧编码开关（A1 时代；A2 后不参与发送）
FILMLAB_ENC_RGB=${FILMLAB_ENC_RGB:-color}

# ---- userdata(20) 读写（★ getusr/setusr 只认【十进制索引或名字】）----
getusr20() {
  PW_READOUT=$(st cap capdtm getusr 20 2>/dev/null)
  case "$PW_READOUT" in
    *"UserData is "*"(0x"*")"*)
      PW_READOUT=${PW_READOUT#*UserData is }
      PW_READOUT=${PW_READOUT#*(}
      printf '%s\n' "${PW_READOUT%%)*}"
      ;;
  esac
}
setusr20() { st cap capdtm setusr 20 "$1" >/dev/null 2>&1; }

# ---- ② 选择通道：确保 PW 真的切到目标槽（同值 = 空操作 ⇒ 要借道）----
#★ 为什么需要这个函数（★ 一个真实的逻辑 bug）
#   旧 apply 的收尾动作是 `setusr 20 $NEED`「写完再切一次，让 ISP 重读」。
#   但 FilmLab 固定写 slot 9 → enum 恒为 9 → 连按两次同一个 enum。
#   ★ 第二次 setusr 写入的是【与当前完全相同的值】= 空操作 ⇒ 什么都不会发生。
#   修法：制造一次【真实变化】（借道一个不同的值再切回来）。
# ★ 2026-10-08 调整借道值优先级：先另一个【自定义槽】，再 STANDARD。
#   理由：厂商 9 风格的曲线硬编码在 ISP 常量里，切到厂商风格可能走与自定义槽
#   不同的分支；自定义槽之间切换必然走「读槽位数据」的分支。
#   FILMLAB_MID=standard 可退回旧行为（借道 STANDARD=0x140000）。
_NEED_PW=0
# pw_force_reload <目标 enum> [已知当前 enum]
#   第 2 参可省一次 getusr（1.3s）：A2 提交位发送成功后，运行时档位必然是
#   field 10 ⇒ 调用方已知当前值，不必再读一遍。读回自证仍然保留。
pw_force_reload() {
  TGT=$1
  if [ -n "${2:-}" ]; then CUR="$2"; else CUR=$(getusr20); fi
  if [ "$CUR" = "$TGT" ]; then
    # ★ 快路径（2026-10-10）：目标已达成 —— 不借道、不 sleep。
    #   依据：① "切换触发 p7 重读槽"已证伪（切换从不搬参数）；② 直推模式下画面靠
    #   直推即时可见；③ 当前档=9（自定义1）是 apply 的常态 ⇒ apply 常路径 0 次切换。
    #   "借道"只是旧假设的心理安慰，删除无损（重启恢复看的是"当前档=slot"这一事实）。
    RELOAD="already"
    return 0
  fi
  setusr20 "$TGT"
  if [ "${UI_REQUEST:-0}" = 1 ]; then
    # setusr normally completes synchronously. Verify immediately; only wait
    # while the readback is stale, with the same ~1s upper bound as before.
    PW_RETRIES=0
    while :; do
      NOW=$(getusr20)
      [ "$NOW" = "$TGT" ] && { RELOAD="direct"; return 0; }
      [ "$PW_RETRIES" -lt 20 ] || break
      $BB sleep 0.05
      PW_RETRIES=$((PW_RETRIES + 1))
    done
  else
    $BB sleep 1
    NOW=$(getusr20)
  fi
  # ★ 自证：切完回读，确认真的落在目标上（不信 setusr 的退出码）
  [ "$NOW" = "$TGT" ] && RELOAD="direct" || RELOAD="direct-VERIFY-FAIL(now=$NOW want=$TGT)"
}

# ---- ③ PW 直推（2026-10-15 起 = A2 档位池直写通道；下方旧编码器为 A1/历史参考）----
# ★★ A2 通道（功能验证 PASS，varlist 逐值命中）：
#    seq 0x134 R 0x135 G 0x136 B 0x137 HUE 0x138 SAT 0x139 SHARP 0x13A CON 0x13B 1
#    全 7 维【原始值】直发（无编码）；值语义：R/G/B 0-200、其余 0-20；0x13B=1 提交触发。
#    （实测对照：发 106 → 内部 0x0870；发 11 → 0x001F；发 8 → 0xFFEF。）
# ★ 旧编码器（A1 时代 0x130-0x133 / 三维路，保留备查）：
#   SCALAR（H/S/S/C）: (raw16 << 16) | 0xD80A    raw16 = 16×值 - 145（补码 16 位）
#   COLOR （R/G/B）  : (gain16 << 16) | 0x00FF   gain16 = ceil(值×2032/100)
pw_raw_code()  { U=$(( ($1 * 16 - 145) & 0xFFFF )); printf "0x%04x%04x" "$U" 0xD80A; }
pw_gain_code() { G=$(( ($1 * 2032 + 99) / 100 ));   printf "0x%04x%04x" "$G" 0x00FF; }

# pw_direct <R> <G> <B> <HUE> <SAT> <SHARP> <CON> [--yes]
#   默认 dry-run（只打印）；--yes 才真发。七维任一为空 ⇒ 拒绝（防静默坏值）。
pw_direct() {
  [ -x "$PWSEND" ] || { echo "  ③ PW直推: 缺 $PWSEND（先部署）——跳过"; return 1; }
  case "" in
    $1|$2|$3|$4|$5|$6|$7)
      echo "  ③ PW直推: 七维有空值 —— 拒绝发送（防静默坏值）"
      return 1 ;;
  esac
  # A2：固定 id + 原始值 + 提交位（0x13B=1）
  ARGS="0x134 $1 0x135 $2 0x136 $3 0x137 $4 0x138 $5 0x139 $6 0x13A $7 0x13B 1"
  YES="$8"
  # ★ 10-17：条间 150ms 是 A1 时代的保守值，svdm 是同步返回（rc=0 即已入 MCB）。
  #   浏览预览用 FILMLAB_PWSLEEP=40（省 ~0.8s），批量写槽仍用 150。
  [ "$YES" = "--yes" ] && ARGS="$ARGS --sleep ${FILMLAB_PWSLEEP:-150}"
  echo "  ③ PW直推（A2 档位池直写；$([ "$YES" = "--yes" ] && echo 真发 || echo dry-run)）:"
  echo "     $PWSEND seq $ARGS $YES"
  # shellcheck disable=SC2086
  "$PWSEND" seq $ARGS $YES
}

# ---- 旧触发：切一次拍摄模式（默认关闭，见上面的纠错）----
trigger_reload() {
  M=$(st cap capdtm getusr DIALMODE 2>/dev/null | tr -d '\r' \
      | sed -n 's/.*UserData is DIALMODE_\([A-Z_]*\).*/\1/p')
  case "$M" in
    SMARTAUTO)    M2=auto ;;
    APERTURE)     M2=a ;;
    SHUTTERSPEED) M2=s ;;
    MANUAL)       M2=m ;;
    SMARTPRO)     M2=smart-pro ;;
    *)            M2=p ;;
  esac
  # 借道：先切到一个【不同】的模式，再切回原模式
  case "$M2" in
    p) TMP=a ;;
    *) TMP=p ;;
  esac
  st app mode $TMP >/dev/null 2>&1
  $BB sleep 1
  st app mode $M2  >/dev/null 2>&1
  $BB sleep 1
  RELOAD2="mode-switch($TMP->$M2)"
}

# ---- ③ 参数通道：状态判据（读 ISP 的 PW 运行时变量）---------------------
# ★★ 2026-10-08 上机实测（决定性，见 docs/current/PW_PARAM_CHANNEL_2026-10-08.md）：
#   · ① prefman set 后，ISP 的 PW 变量**纹丝不动** —— 存储层与运行时是两份数据
#   · ② setusr 20 只改 eIQ_ID_EFFECT_MODE（风格名），**不搬那 7 维参数**
#   · prefman save 0 + sync 也**不搬**
#   · setvar 写不进去：varlist 显示下标 ≠ setvar/getvar 的 id（id 是运行时注册的，
#     且历史上盲扫 id 写死过 p7 capture 服务 ⇒ 【禁止盲试】）
#   ⇒ 所以本引擎**不做参数推送**（做不到），改为提供**客观判据**：
#     直接读 ISP 手上那 7 维的值，和 prefman 里该槽的值比 —— 一眼看出"参数进没进 ISP"。
#
# ISP 变量编码（实测解出）：
#   VARIABLE_PWCOLOR_R/G/B  = (gain20 << 16) | 0x00FF   ⇒ gain ≈ (v>>16)/20.32
#   VARIABLE_PW{HUE,SATURATION,SHARPNESS,CONTRAST} = (b<<16) | 0xD80A
#                            ⇒ 值 = 10 + (b>>4)（低 nibble 恒 0xF，是标记位）
#   [14] VARIABLE_PWCOLOR 恒为 "----------"（聚合项，未定义）
# 用法: st cap capdtm varlist  → 抓 PW 行（只读，零风险）
isp_pw_snapshot() {
  # ★ 用 -F'|' 取第 4 列（varlist 列序: [idx]| NAME | len | ID(Hex) | ID(Dec)|）
  #   别用 gsub(/.*\|/)——贪婪匹配会吃到最后一列的数字，把 hex 读成十进制值。
  st cap capdtm varlist 2>/dev/null | tr -d '
' | sed 's/\[[0-9;]*m//g'   | /opt/usr/nx-ks/busybox awk -F'|' '
    /VARIABLE_PWCOLOR_[RGB]|VARIABLE_PWHUE|VARIABLE_PWSATURATION|VARIABLE_PWSHARPNESS|VARIABLE_PWCONTRAST/ {
      n = $2; gsub(/VARIABLE_/, "", n); gsub(/ /, "", n)
      h = $4; gsub(/ /, "", h)
      if (n != "" && h != "") print n" "h
    }'
}
# 从快照取某变量的 hex（不含 0x 前缀；取不到返回空）
snap_hex() {
  echo "$SNAP" | while read -r n h; do
    [ "$n" = "$1" ] || continue
    echo "${h#0x}"
  done
}
# 标量变量解码：raw16(有符号) = 16*(值-10)+15 ⇒ 值 = 10 + (raw16-15)/16
sgn_scalar() {
  H=$(( 0x$1 >> 16 ))
  [ "$H" -ge 32768 ] && H=$(( H - 65536 ))
  echo $(( 10 + (H - 15) / 16 ))
}
# 把 ISP 的 7 维解出来并打印 + 与 prefman 槽位比对
# 返回 ISP_SYNC=yes|no|unknown
check_isp_pw() {
  SLOT=${2:-9}
  SNAP=$(isp_pw_snapshot)
  if [ -z "$SNAP" ]; then
    echo "  ★ 读不到 ISP PW 变量（varlist 无输出）⇒ 判据不可用"; ISP_SYNC=unknown; return 0
  fi
  VR=$(snap_hex PWCOLOR_R); VG=$(snap_hex PWCOLOR_G); VB=$(snap_hex PWCOLOR_B)
  [ -z "$VR" ] && { echo "  ★ 快照里没有 PWCOLOR_R ⇒ 判据不可用"; ISP_SYNC=unknown; return 0; }
  # 高 16 位 / 20.32 ≈ 增益（÷20.32 用整数近似：×100/2032）
  IR=$(( (0x$VR >> 16) * 100 / 2032 ))
  IG=$(( (0x$VG >> 16) * 100 / 2032 ))
  IB=$(( (0x$VB >> 16) * 100 / 2032 ))
  NH=$(snap_hex PWHUE); NSS=$(snap_hex PWSATURATION)
  NSH=$(snap_hex PWSHARPNESS); NC=$(snap_hex PWCONTRAST)
  # ★ 高 16 位是【有符号】的 16*(值-10)+15 —— 必须按补码还原，否则负偏移会被
  #   当成 0xFF=255 解出 25（2026-10-08 实测踩过：SAT=9 的原始值就是 0xFFFF）。
  IH=$(sgn_scalar "$NH"); IS=$(sgn_scalar "$NSS")
  IP=$(sgn_scalar "$NSH"); IC=$(sgn_scalar "$NC")
  echo "  ISP 现用参数:  R/G/B=$IR/$IG/$IB  HUE=$IH SAT=$IS SHARP=$IP CON=$IC"
  # 槽位值
  P0=$(get_r 0 $SLOT); P1=$(get_r 1 $SLOT); P2=$(get_r 2 $SLOT)
  P3=$(get_r 3 $SLOT); P4=$(get_r 4 $SLOT); P5=$(get_r 5 $SLOT); P6=$(get_r 6 $SLOT)
  echo "  prefman slot$SLOT: R/G/B=$P0/$P1/$P2  HUE=$P3 SAT=$P4 SHARP=$P5 CON=$P6"
  ISP_SYNC=no
  # 颜色只比【比例】（绝对值有量化差）：以 G 为 1
  if [ -n "$IG" ] && [ "$IG" != 0 ] && [ -n "$P1" ] && [ "$P1" != 0 ]; then
    a=$(( IR * 1000 / IG )); b=$(( P0 * 1000 / P1 ))
    d=$(( a - b )); [ $d -lt 0 ] && d=$(( -d ))
    a=$(( IB * 1000 / IG )); b=$(( P2 * 1000 / P1 ))
    e=$(( a - b )); [ $e -lt 0 ] && e=$(( -e ))
    if [ $d -le $(( b / 20 )) ] && [ $e -le $(( b / 20 )) ]; then
      # 比例对上了：再看 4 个标量（必须逐个相等）
      if [ "$IH" = "$P3" ] && [ "$IS" = "$P4" ] && [ "$IP" = "$P5" ] && [ "$IC" = "$P6" ]; then
        ISP_SYNC=yes
      fi
    fi
  fi
  if [ "$ISP_SYNC" = yes ]; then
    echo "  ✓ 判据：ISP 手上的 7 维 = slot$SLOT（参数已进 ISP）"
  else
    echo "  ✗ 判据：ISP 手上的 7 维 ≠ slot$SLOT ⇒ **参数没进 ISP**（画面不会按配方变）"
    echo "     已知可用链路：打开「画面向导」→ 选中「自定义1」→ 再跑 filmlab.sh check 复验"
  fi
}
# slot -> enum（切风格用）
enum_of_slot() {
  case $1 in
    9)  echo 9;;
    10) echo 10;;
    11) echo 12;;   # ★ slot 11 对应 enum 12
    *)  echo $1;;   # 0-8 原生槽，enum = slot
  esac
}
# External PW enum 11 is a hole; CUSTOM3 is enum 12 / prefman slot 11.
slot_of_enum() {
  case "$1" in
    0x140000) echo 0 ;; 0x140001) echo 1 ;; 0x140002) echo 2 ;;
    0x140003) echo 3 ;; 0x140004) echo 4 ;; 0x140005) echo 5 ;;
    0x140006) echo 6 ;; 0x140007) echo 7 ;; 0x140008) echo 8 ;;
    0x140009) echo 9 ;; 0x14000a) echo 10 ;; 0x14000c) echo 11 ;;
    *) return 1 ;;
  esac
}
apply_slot_valid() {
  case "$1" in 0|1|2|3|4|5|6|7|8|9|10|11) return 0 ;; *) return 1 ;; esac
}
# Backup before editing any current field, including a factory preset. Do not
# source backup files as shell code. Their format is slot|R|G|B|H|S|P|C.
backup_apply_slot() {
  BACKDIR=$LAB/slot-backups
  BACKFILE=$BACKDIR/slot-$SLOT.txt
  [ -s "$BACKFILE" ] && return 0
  mkdir -p "$BACKDIR" || return 1
  BACKVALUES=$SLOT
  for BACKPARAM in 0 1 2 3 4 5 6; do
    BACKVALUE=$(get_r "$BACKPARAM" "$SLOT")
    case "$BACKVALUE" in ''|*[!0-9]*) return 1 ;; esac
    BACKMAX=20; [ "$BACKPARAM" -lt 3 ] && BACKMAX=200
    [ "$BACKVALUE" -le "$BACKMAX" ] || return 1
    BACKVALUES="$BACKVALUES|$BACKVALUE"
  done
  printf '%s\n' "$BACKVALUES" > "$BACKFILE.tmp" || return 1
  mv -f "$BACKFILE.tmp" "$BACKFILE"
}
# ★ 合法写入校验（2026-10-04 新增）
#  UI 可见的只有 slot 9/10/11（自定义1/2/3）。slot 12=CUSTOM_4 在 prefman 里
#  存在但 UI 不显示 → 写进去就是"看不见的脏数据"，会污染整机状态
#  （实测：slot 12 残留 240/240/40 时，相机拍完照片后台卡、照片删不掉）。
ok_slot() {
  case $1 in
    9|10|11) return 0;;    # 允许
    *) return 1;;          # 其余一律拒绝
  esac
}
# 自动挑一个可用槽（3 个可见槽轮转）
auto_slot() {
  C=$1
  [ $C -ge 3 ] && C=0
  echo $((9 + C))
}

# ---- JSON 极简解析（只取 recipes 段下的 key 和数值，够用即可）----
# 用法: jval <recipe_name> <field>   例: jval portra400 R_COLOR
jval() {
  /opt/usr/nx-ks/busybox awk -v r="\"$1\": " -v f="\"$2\":" '
    index($0, r) { inr=1; next }
    inr && index($0, f) {
      s = substr($0, index($0, f) + length(f))
      gsub(/[^0-9-]/, "", s)
      if (s != "") { print s; exit }
    }
    inr && $0 ~ /^    \}/ { exit }
  ' $RECIPE 2>/dev/null
}
# ★ jtable —— 一次性导出全部配方表（单 awk 进程）
#   供 export/mkgui 使用：35 配方从"280 次 awk 进程风暴（~90s）"降到 <1s（2026-10-09 优化）
#   输出：key|label|R|G|B|HUE|SAT|SHARP|CON（每行一个配方；与 recipes.txt 同格式）
jtable() {
  /opt/usr/nx-ks/busybox awk '
    BEGIN { inr=0; key=""; label="" }
    /"recipes"/ { inr=1; next }
    /"presets"/ { inr=0; next }
    !inr { next }
    /^    "/ {
      key=$0; sub(/^    "/,"",key); sub(/": *\{.*$/,"",key); sub(/",? *$/,"",key)
      label=""; delete F; next
    }
    /^        "label":/ { s=$0; sub(/.*"label": *"/,"",s); sub(/".*$/,"",s); label=s; next }
    /^        "/ {
      name=$0; sub(/^ *"/,"",name); sub(/":.*$/,"",name)
      val=$0; gsub(/[^0-9-]/,"",val)
      F[name]=val; next
    }
    /^    \}/ {
      if (key != "") printf "%s|%s|%s|%s|%s|%s|%s|%s|%s\n", key,label,F["R_COLOR"],F["G_COLOR"],F["B_COLOR"],F["HUE"],F["SATURATION"],F["SHARPNESS"],F["CONTRAST"]
      key=""; next
    }
  ' $RECIPE 2>/dev/null
}
# ★ jline —— 单配方一次提取（单 awk 进程，2026-10-10 apply 提速）
#   输出: R|G|B|HUE|SAT|SHARP|CON（7 值一行）；替代 7 次 jval（7 进程 → 1 进程）
jline() {
  /opt/usr/nx-ks/busybox awk -v want="$1" '
    BEGIN { inr=0; key="" }
    /"recipes"/ { inr=1; next }
    /"presets"/ { inr=0; next }
    !inr { next }
    /^    "/ {
      key=$0; sub(/^    "/,"",key); sub(/": *\{.*$/,"",key); sub(/",? *$/,"",key)
      delete F; next
    }
    /^        "/ && key == want {
      name=$0; sub(/^ *"/,"",name); sub(/":.*$/,"",name)
      val=$0; gsub(/[^0-9-]/,"",val)
      F[name]=val; next
    }
    /^    \}/ {
      if (key == want) {
        printf "%s|%s|%s|%s|%s|%s|%s\n", F["R_COLOR"],F["G_COLOR"],F["B_COLOR"],F["HUE"],F["SATURATION"],F["SHARPNESS"],F["CONTRAST"]
        exit
      }
    }
  ' $RECIPE 2>/dev/null
}
# 列出所有配方名
jlist() {
  /opt/usr/nx-ks/busybox awk '
    /"recipes"/ { inr=1; next }
    /"presets"/ { inr=0; next }
    index($0, "\"") && inr && /^    "/ {
      k = $0
      gsub(/^ +"/,"", k); gsub(/".*/,"", k)
      if (k != "" && substr(k,1,1) != "_") print k
    }
  ' $RECIPE 2>/dev/null
}
# 取字符串值（用于 wb_mode 这类枚举字段）
jstr() {
  /opt/usr/nx-ks/busybox awk -v r="\"$1\": " -v f="\"$2\":" '
    index($0, r) { inr=1; next }
    inr && index($0, f) {
      s = substr($0, index($0, f) + length(f))
      gsub(/^[ \t]*"/, "", s)
      gsub(/".*$/, "", s)
      gsub(/[ \t]*$/, "", s)
      gsub(/,.*$/, "", s)
      if (s != "") { print s; exit }
    }
    inr && $0 ~ /^    \}/ { exit }
  ' $RECIPE 2>/dev/null
}
# 取 label
jlabel() {
  /opt/usr/nx-ks/busybox awk -v r="\"$1\":" '
    $0 ~ r { inr=1; next }
    inr && /"label":/ { gsub(/.*"label": *"/,""); gsub(/".*/,""); print; exit }
  ' $RECIPE 2>/dev/null
}

log() { echo "$*" >> $LOG; }

#===============================================================
CMD=$1
REC=$2
SLOT=$3
FAST=0
UI_REQUEST=0
# ★ --fast（10-10 提速）：菜单路径专用 —— 跳过 ISP 判据读与逐项回读（省 ~14 个进程）；
#   详细判据仍可用 `filmlab.sh check`（只读）单独跑。
case "$SLOT" in --fast) FAST=1; SLOT="" ;; esac
[ -z "$CMD" ] && CMD=help
# Persistent UI: browsing must not save every intermediate selection to flash.
# Resolve these after filmlab.conf, so its FILMLAB_SAVE cannot override intent.
case "$CMD" in
  # ★ 2026-10-17 提速（实测 4.35s → 目标 ~1.0s）：预览/提交一律以 CUSTOM1（slot 9）
  #   为画布。理由见 apply 分支内 "UI 快路径" 注释。
  #   FILMLAB_PWSLEEP 控制 A2 条间间隔：浏览时不值得等 7×150ms。
  preview) CMD=apply; FILMLAB_SAVE=0; FAST=1; UI_REQUEST=1; FILMLAB_PWSLEEP=40 ;;
  commit)  CMD=apply; FILMLAB_SAVE=1; FAST=1; UI_REQUEST=1 ;;
esac
mkdir -p $LAB 2>/dev/null

case $CMD in

#---------------------------------------------------------------
list)
  echo "=== FilmLab SD 卡配方库 ==="
  echo "文件: $RECIPE"
  echo
  printf "%-14s %-22s %s\n" "KEY" "LABEL" "7 维 (R/G/B/HUE/SAT/SHARP/CON)"
  echo "------------------------------------------------------------------------"
  jlist | while read k; do
    [ -z "$k" ] && continue
    R=$(jval $k R_COLOR); G=$(jval $k G_COLOR); B=$(jval $k B_COLOR)
    H=$(jval $k HUE);     S=$(jval $k SATURATION)
    P=$(jval $k SHARPNESS); C=$(jval $k CONTRAST)
    printf "%-14s %-22s %s/%s/%s %s/%s/%s/%s\n" "$k" "$(jlabel $k)" \
      "$R" "$G" "$B" "$H" "$S" "$P" "$C"
  done
  echo
  echo "预设槽（UI 零延迟）:"
  grep -o '"slot1[01]": *"[a-z0-9_]*"' $RECIPE 2>/dev/null | sed 's/^/  /'
  ;;

#---------------------------------------------------------------
show)
  [ -z "$REC" ] && { echo "用法: show <recipe>"; exit 1; }
  echo "=== $REC ==="
  L=$(jlabel $REC);[ -n "$L" ] && echo "显示名: $L"
  echo "  R=$(jval $REC R_COLOR)  G=$(jval $REC G_COLOR)  B=$(jval $REC B_COLOR)"
  echo "  HUE=$(jval $REC HUE)  SAT=$(jval $REC SATURATION)  SHARP=$(jval $REC SHARPNESS)  CONTRAST=$(jval $REC CONTRAST)"
  echo "  K=$(jval $REC K)  tintA=$(jval $REC tint_a)  tintB=$(jval $REC tint_b)"
  ;;

#---------------------------------------------------------------
# 面板「还原」：中性值（R/G/B=100，HUE/SAT/SHARP/CON=10）直推给 ISP。
#
# ★★ 2026-10-19 修正（用户报「按还原变黑白」）：HUE/SAT/SHARP/CON 的中性值是 **10**，
#   不是 0。四维值域是 0-20、10 才是零点（`VARIABLE_PWHUE/SATURATION/SHARPNESS/CONTRAST`
#   = (raw16<<16)|0xD80A，raw16 = 16*(值-10)+15 ⇒ 值 10 ⇔ raw16=0x000F ⇔ 零偏移）。
#   原先发 0 = 负向拉满 10 档：SAT 归零 ⇒ 直接变黑白（这是用户看到的症状），
#   HUE/SHARP/CON 同时被压到底。R/G/B=100 的 1.0 增益没问题（100→2032），
#   出错的是后四维 —— 不要拿 set_r 的「100 中性」类推过来。
#
# 与 preview 同语义 —— 只改运行时，不写槽、不落盘。所以：
#   · 立刻生效，画面回中性；
#   · 相机切档或重启就回原厂/配方值，"还原"不是持久设置；
#   · 面板随后的"保存并关闭"仍会 apply 当前选中的配方（这是有意的：
#     还原是临时态，不是把配方改成中性）。
# 要做到"切档也保持中性"必须写用户正在用的档位槽，那会破坏真实风格，
# 与 apply 的 UI 快路径（固定 slot 9）同一个理由，所以不做。
# ★ 不叫 reset：`reset` 已是「14 个槽全部恢复出厂并逐槽核对」的重量级维护
#   命令（见下方 reset 分支），两者语义差得远，不能共用一个词。
neutral)
  if [ "$FILMLAB_PW" != 1 ] || [ ! -x "$PWSEND" ]; then
    echo "REJECT: neutral requires FILMLAB_PW=1, pwsend.arm and verified A2 firmware"
    exit 1
  fi
  if pw_direct 100 100 100 10 10 10 10 --yes; then
    log "$(date '+%H:%M:%S') neutral -> 100/100/100 10/10/10/10"
    echo "✓ neutral (100/100/100 10/10/10/10)"
    exit 0
  fi
  echo "REJECT: PW backend failed"
  exit 1
  ;;

#---------------------------------------------------------------
apply)
  [ -z "$REC" ] && { echo "用法: apply <recipe> [slot]"; exit 1; }
  if [ "$UI_REQUEST" = 1 ] && { [ "$FILMLAB_PW" != 1 ] || [ ! -x "$PWSEND" ]; }; then
    echo "REJECT: preview/commit requires FILMLAB_PW=1, pwsend.arm and verified A2 firmware"
    exit 1
  fi
  # Follow the field selected at the moment this request is executed. Never
  # silently fall back to CUSTOM1 when a read fails or an enum is unsupported.
  # ★ 10-17：允许调用方（nxui）用 FILMLAB_ENUM_CACHE 提供最近一次读到的档位
  #   （格式 0x1400XX），省掉每次 1.4s 的 getusr。缓存无效时会落到 REJECT。
  if [ "$UI_REQUEST" = 1 ]; then
    # ★★ UI 快路径（2026-10-17 实测定根因）：预览/提交固定以 CUSTOM1（slot 9）为画布。
    #   原因一（性能）：A2 提交位 0x13B 本身就把运行时档位切到 field 10。若"跟随当前
    #     栏位"（STANDARD 等），收尾必须 getusr(1.3s)+setusr(1.2s)+getusr(1.3s) 把档位
    #     搬回去 —— 单次预览 4.35s 里 2.5~3.9s 全耗在这三次 st 调用（相机实测 1.3s/次）。
    #   原因二（正确性）：跟随当前栏位会把配方 7 维写进 slot 0（标准风格）且 preview
    #     不恢复，用户切回"标准"看到的是最后一次预览 —— 预览是临时态，不该污染真实风格。
    #   代价：预览期运行时档位停在 CUSTOM1（画面本来就是配方效果，语义自洽）；
    #     commit 才把档位还回打开面板时那一档（FILMLAB_ENUM_CACHE 由 nxui 传入）。
    SLOT=9
    case "${FILMLAB_ENUM_CACHE:-}" in
      0x1400*) TARGET_PW="$FILMLAB_ENUM_CACHE" ;;
      *)       TARGET_PW="0x140009" ;;
    esac
    ENUM=9
  else
    if [ -z "$SLOT" ]; then
      CURRENT_PW="$(getusr20)"
      SLOT=$(slot_of_enum "$CURRENT_PW") || { echo "REJECT: cannot resolve current PW field ($CURRENT_PW)"; exit 1; }
    fi
    ENUM=$(enum_of_slot $SLOT)
    TARGET_PW=$(printf "0x%06x" $((0x140000 + ENUM)))
  fi
  apply_slot_valid "$SLOT" || { echo "REJECT: unsupported PW slot $SLOT"; exit 1; }
  echo ">>> 应用 '$REC' -> slot $SLOT (enum $ENUM)"
  # ★★★ 2026-10-08 加固：先取全部 7 维，★ 任一为空就【拒绝写入】。
  #   起因（U2 上机实测，用户报告）：/mnt/mmc/filmlab/recipes.json 缺失时 jval 返回空串，
  #   set_r 把槽位写成 0 ⇒ slot9（UI 自定义1）全 0 ⇒ 相机【整屏黑】，只能靠 reset 救回。
  #   ★ 读不到就该报错退出，绝不该写入坏值 —— 这是"静默失败导致破坏性写入"的典型。
  # ★ 10-10 提速：单次 awk（jline）提取全部 7 值 —— 替代 7×jval（7 进程 → 1 进程）
  LINE=$(jline "$REC")
  OIFS="$IFS"; IFS='|'
  # shellcheck disable=SC2086
  set -- $LINE
  IFS="$OIFS"
  V0=$1; V1=$2; V2=$3; V3=$4; V4=$5; V5=$6; V6=$7
  case "" in
    $V0|$V1|$V2|$V3|$V4|$V5|$V6)
      echo "★ 拒绝写入：配方 '$REC' 的字段读不到值。"
      echo "  原因通常是 /mnt/mmc/filmlab/recipes.json 缺失或格式不符（先用 filmlab.sh list 自查）。"
      echo "  ★ 强行写入会把槽位清成 0 ⇒ 画面全黑，故中止。"
      exit 1 ;;
  esac
  # The JSON and exported UI table may be edited independently. Validate the
  # actual values consumed by A2 before touching any slot (its scalar LUT is 0..20).
  VALUE_PARAM=0
  for VALUE in "$V0" "$V1" "$V2" "$V3" "$V4" "$V5" "$V6"; do
    case "$VALUE" in ''|*[!0-9]*) echo "REJECT: nonnumeric recipe value"; exit 1 ;; esac
    VALUE_MAX=20; [ "$VALUE_PARAM" -lt 3 ] && VALUE_MAX=200
    [ "$VALUE" -le "$VALUE_MAX" ] || { echo "REJECT: recipe value out of range"; exit 1; }
    VALUE_PARAM=$((VALUE_PARAM + 1))
  done
  # ★ 10-17：预览不写槽、不备份 —— 画面完全由 A2 直推决定，槽只在 commit 落盘时写。
  #   省掉 7×prefman set + 7×prefman get（≈0.4s），浏览过程也不改 eMMC 侧数据。
  if [ "$UI_REQUEST" = 1 ] && [ "$FILMLAB_SAVE" != 1 ]; then
    :
  else
  backup_apply_slot || { echo "REJECT: cannot back up slot $SLOT"; exit 1; }
  if [ "$UI_REQUEST" = 1 ]; then
    set_r 0 $SLOT "$V0" && set_r 1 $SLOT "$V1" && set_r 2 $SLOT "$V2" &&
      set_r 3 $SLOT "$V3" && set_r 4 $SLOT "$V4" && set_r 5 $SLOT "$V5" &&
      set_r 6 $SLOT "$V6" || { echo "REJECT: slot write failed"; exit 1; }
  else
    set_r 0 $SLOT "$V0"
    set_r 1 $SLOT "$V1"
    set_r 2 $SLOT "$V2"
    set_r 3 $SLOT "$V3"
    set_r 4 $SLOT "$V4"
    set_r 5 $SLOT "$V5"
    set_r 6 $SLOT "$V6"
  fi
  fi
  # v2: 白平衡不由配方控制，相机保持自动 WB（见 recipes.json 的 _note）
  # ★ 落盘（2026-10-08 实测必需）：只 set 不 save ⇒ 相机重启后槽位回退到旧值。
  #   FILMLAB_SAVE=0 可关掉（跑批量试验时省 eMMC 写入）。
  if [ "$FILMLAB_SAVE" = "1" ] && [ "$UI_REQUEST" != 1 ]; then
    prefman save 0 >/dev/null 2>&1
    sync
    SAVED="saved"
  else
    SAVED="not-saved"
  fi
  # ③ PW 直推（2026-10-09 新链路；FILMLAB_PW=1 时启用——pwcalib.sh 校准后开）
  PWSTAT="off"
  if [ "$FILMLAB_PW" = "1" ]; then
    [ "$UI_REQUEST" != 1 ] || echo 'NXUI_STAGE send'
    if pw_direct "$V0" "$V1" "$V2" "$V3" "$V4" "$V5" "$V6" --yes; then
      PWSTAT="direct"
    else
      PWSTAT="failed"
    fi
  fi
  # A2 commit writes runtime field 10 (= CUSTOM1), regardless of the selected
  # field. Restore the intended enum *after* sending, including on send failure.
  # ★ 10-17 快路径：A2 提交位已经把运行时档位切到 CUSTOM1。
  #   preview（不落盘）的语义就是"停在 CUSTOM1 看效果" ⇒ 完全跳过档位通道（0 次 st，
  #   省 2.5~3.9s）。commit 才把档位还回打开面板时那一档（TARGET_PW，来自 nxui 缓存）；
  #   目标本来就是 CUSTOM1 时同样跳过。发送失败仍走原路径自证。
  if [ "$UI_REQUEST" = 1 ] && [ "$FILMLAB_SAVE" != 1 ]; then
    RELOAD="already"
  elif [ "$TARGET_PW" = "0x140009" ] && [ "$PWSTAT" = "direct" ]; then
    [ "$UI_REQUEST" != 1 ] || echo 'NXUI_STAGE restore'
    RELOAD="already"
  else
    [ "$UI_REQUEST" != 1 ] || echo 'NXUI_STAGE restore'
    # commit 的 A2 发送成功后运行时档位必为 CUSTOM1 ⇒ 传进去省一次 getusr
    if [ "$PWSTAT" = "direct" ]; then
      pw_force_reload "$TARGET_PW" "0x140009"
    else
      pw_force_reload "$TARGET_PW"
    fi
  fi
  if [ "$UI_REQUEST" = 1 ] && [ "$PWSTAT" = failed ]; then
    echo "REJECT: PW backend failed (target=$TARGET_PW reload=$RELOAD)"
    exit 1
  fi
  # 旧触发（切拍摄模式）—— 2026-10-08 证伪，默认关闭；FILMLAB_MODE=1 才跑
  RELOAD2="off"
  [ "$FILMLAB_MODE" = "1" ] && trigger_reload
  if [ "$UI_REQUEST" = 1 ]; then
    case "$RELOAD" in *VERIFY-FAIL*) echo "REJECT: VERIFY-FAIL"; exit 1 ;; esac
    if [ "$FILMLAB_SAVE" = 1 ]; then
      prefman save 0 >/dev/null 2>&1 || { echo "REJECT: save failed"; exit 1; }
      sync
      SAVED="saved"
    fi
  fi
  log "$(date '+%H:%M:%S') apply $REC -> slot$SLOT enum$ENUM reload=$RELOAD mode=$RELOAD2 pw=$PWSTAT $SAVED"
  # ★ --fast 出口（10-10）：菜单路径 —— 只回一行结果，不做回读/判据（那 ~15 个进程省掉）
  if [ "$FAST" = "1" ]; then
    echo "✓ $REC -> slot$SLOT  (reload=$RELOAD pw=$PWSTAT $SAVED)"
    case "$RELOAD" in *VERIFY-FAIL*) echo "  ★★ ② 通道自证失败：enum 未落到目标槽";; esac
    exit 0
  fi
  echo "  已写入($SAVED):"
  echo "  R=$(get_r 0 $SLOT) G=$(get_r 1 $SLOT) B=$(get_r 2 $SLOT) HUE=$(get_r 3 $SLOT) SAT=$(get_r 4 $SLOT) SHARP=$(get_r 5 $SLOT) CON=$(get_r 6 $SLOT)"
  echo "  PW_TYPE  = $(st cap capdtm getusr 20 2>/dev/null | tr -d '
' | sed -n 's/.*UserData is \(.*\)//p')"
  echo "  通道: ①存储=已写  ②选择=$RELOAD  模式触发=$RELOAD2"
  case "$RELOAD" in *VERIFY-FAIL*) echo "  ★★ 自证失败：切完回读不等于目标（② 通道没落到目标槽）";; esac
  # ★★ 客观判据：ISP 手上的 7 维到底是不是这个槽的值
  check_isp_pw "" $SLOT
  case "$ISP_SYNC" in
    yes) echo "  ★ ISP 已按本配方渲染 ⇒ 画面应当就是配方效果。" ;;
    no)
      echo "  ★★ 画面**不会**变（① ② 两条通道不搬参数）。"
      if [ "$FILMLAB_PW" != "1" ]; then
        echo "     ⇒ 两个选择："
        echo "       a) 人工（保底，已验证）：画面向导 → 选中「自定义1」（全 7 维）"
        echo "       b) 自动：置 FILMLAB_PW=1 ⇒ A2 全 7 维直推（0x134..0x13B 原始值）"
      else
        echo "     ⇒ ③ 直推已开（A2 全 7 维）但 ISP 未跟上："
        echo "        · 重跑一次 pwpush <recipe> --yes；或看 pwsend 输出 rc"
        echo "        · 或人工恢复：画面向导 → 选中「自定义1」"
      fi ;;
    *) echo "  ★ 判据不可用，无法自动确认。" ;;
  esac
  echo "  相机画面向导栏位: enum $ENUM / slot $SLOT"
  ;;

#---------------------------------------------------------------
quick)
  # 只切风格，零prefman 写入（槽已预写好时用）
  [ -z "$REC" ] && { echo "用法: quick <recipe>  （槽已在preset 里）"; exit 1; }
  P=$(/opt/usr/nx-ks/busybox awk -v r="\"$REC\":" '/"presets"/{p=1} p && $0 ~ r {print; exit}' $RECIPE 2>/dev/null)
  SLOT=$(echo "$P" | sed -n 's/.*"slot1\?\([0-9]\+\)".*/\1/p')
  [ -z "$SLOT" ] && SLOT=$(echo "$P" | sed -n 's/.*"slot\([0-9]\+\)".*/\1/p')
  if [ -z "$SLOT" ]; then echo "配方 '$REC' 不在 preset 段，请用 apply"; exit 1; fi
  ENUM=$(enum_of_slot $SLOT)
  pw_force_reload $(printf "0x%06x" $((0x140000 + ENUM)))
  echo "quick: $REC -> slot $SLOT enum $ENUM (reload=$RELOAD)  PW_TYPE=$(st cap capdtm getusr 20 2>/dev/null | tr -d '\r' | sed -n 's/.*UserData is \(.*\)/\1/p')"
  ;;

#---------------------------------------------------------------

#---------------------------------------------------------------
dump)
  if [ -n "$SLOT" ]; then
    echo "slot $SLOT: R=$(get_r 0 $SLOT) G=$(get_r 1 $SLOT) B=$(get_r 2 $SLOT) HUE=$(get_r 3 $SLOT) SAT=$(get_r 4 $SLOT) SHARP=$(get_r 5 $SLOT) CON=$(get_r 6 $SLOT)"
  else
    for S in 0 1 2 3 4 5 6 7 8 9 10 11 12; do
      printf "slot %-3s R=%-5s G=%-5s B=%-5s HUE=%-4s SAT=%-4s SHARP=%-4s CON=%-4s\n" $S \
        "$(get_r 0 $S)" "$(get_r 1 $S)" "$(get_r 2 $S)" "$(get_r 3 $S)" \
        "$(get_r 4 $S)" "$(get_r 5 $S)" "$(get_r 6 $S)"
    done
  fi
  ;;

#---------------------------------------------------------------
#---------------------------------------------------------------
wb)
  # 单独设置白平衡（不动 PW）
  K=$2; A=$3; B=$4; MODE=${5:-manual}
  [ -z "$K" ] && { echo "用法: wb <K> <tint_a> <tint_b> [manual|auto|keep]"; exit 1; }
  [ -z "$A" ] && A=$TINT_NEUTRAL_A
  [ -z "$B" ] && B=$TINT_NEUTRAL_B
  set_wb "$K" "$A" "$B" "$MODE"
  echo "WB 已设置:"
  echo "  PW_TYPE  = $(st cap capdtm getusr 20 2>/dev/null | tr -d '\r' | sed -n 's/.*UserData is \(.*\)/\1/p')"
  ;;

#---------------------------------------------------------------
wbdump)
  echo "=== WB 段完整状态 ==="
  printf "  %-34s %s\n" "WB_TYPE (0xa390)" "$(get_wb_type)"
  printf "  %-34s %s\n" "WB_K_VALUE (0xa394)" "$(get_wb)"
  printf "  %-34s %s\n" "WB_K_BA (0xa3c0)" "$(get_tint)"
  printf "  %-34s %s\n" "WB_CUSTOM_BA (0xa3bc)" "$(get_tint)"
  printf "  %-34s %s\n" "CWB_RED (0xa3c4)" "$(prefman get 0 0x0a3c4 l 2>/dev/null | tr -d '\r' | sed -n 's/.*value = \([-0-9]*\).*/\1/p')"
  printf "  %-34s %s\n" "CWB_GREEN (0xa3c8)" "$(prefman get 0 0x0a3c8 l 2>/dev/null | tr -d '\r' | sed -n 's/.*value = \([-0-9]*\).*/\1/p')"
  printf "  %-34s %s\n" "CWB_BLUE (0xa3cc)" "$(prefman get 0 0x0a3cc l 2>/dev/null | tr -d '\r' | sed -n 's/.*value = \([-0-9]*\).*/\1/p')"
  printf "  %-34s %s\n" "setusr 6 (WB 模式)" "$(st cap capdtm getusr 6 2>/dev/null | tr -d '\r' | sed -n 's/.*UserData is \(.*\)/\1/p')"
  ;;

#---------------------------------------------------------------
preset)
  # 把配方写进指定槽（默认 9），用于预置 3 个可见槽
  R=$2; T=$3
  [ -z "$R" ] && { echo "用法: preset <recipe> [slot]"; exit 1; }
  [ -z "$T" ] && T=9
  ok_slot $T || { echo "拒绝：slot $T 不是 UI 可见槽（只允许 9/10/11）。"; exit 1; }
  set_r 0 $T "$(jval $R R_COLOR)"; set_r 1 $T "$(jval $R G_COLOR)"
  set_r 2 $T "$(jval $R B_COLOR)"; set_r 3 $T "$(jval $R HUE)"
  set_r 4 $T "$(jval $R SATURATION)"; set_r 5 $T "$(jval $R SHARPNESS)"
  set_r 6 $T "$(jval $R CONTRAST)"
  echo "预设 $R -> slot $T:
    R=$(get_r 0 $T) G=$(get_r 1 $T) B=$(get_r 2 $T) HUE=$(get_r 3 $T) SAT=$(get_r 4 $T) SHARP=$(get_r 5 $T) CON=$(get_r 6 $T)"
  echo "  提示：现在可在机身 UI 上选对应的『自定义』槽查看"
  ;;

#---------------------------------------------------------------
reset)
  # 把全部 14 个槽恢复出厂中性
  # ★★★ 必须包含 slot 12（CUSTOM_4）★★★
  #   2026-10-04：slot 12 残留 R=240 G=240 B=40（黄绿）导致相机"拍完照片后台卡、
  #   照片删不掉"，只有 reset 能救 —— 而当时的循环只到 11，漏了它。
  #   写 slot 12 很容易发生（preset <recipe> 12），UI 又看不见，查不出来。
  for s in 0 1 2 3 4 5 6 7 8 9 10 11 12; do
    set_r 0 $s 100; set_r 1 $s 100; set_r 2 $s 100
    set_r 3 $s 10;  set_r 4 $s 10;  set_r 5 $s 10;  set_r 6 $s 10
  done
  # ★ 先离开再回来，制造一次真实跳变。
  #   ★ 不能连续两次都写 0x140000 —— 第二次是同值空操作，借道也借不动。
  #   先切到 CUSTOM_1(0x140009)，再让 pw_force_reload 切回 STANDARD。
  st cap capdtm setusr 20 0x140009 >/dev/null 2>&1
  $BB sleep 1
  pw_force_reload 0x140000
  # 读回验证：任何一槽不中性就报出来（不要静默成功）
  BAD=0
  i=0
  while [ $i -le 6 ]; do
    s=0
    while [ $s -le 12 ]; do
      case $i in 0|1|2) OK=100;; *) OK=10;; esac
      V=$(get_r $i $s)
      case "$V" in
        $OK|"$OK (*)"|"") ;;
        *) echo "  ★ 未恢复 dim$i slot$s =$V (期望 $OK)"; BAD=$((BAD+1));;
      esac
      s=$((s+1))
    done
    i=$((i+1))
  done
  [ $BAD -eq 0 ] && echo "  ✓14 槽全部已核对为中性" || echo "  ★仍有 $BAD 处异常"
  echo "当前 PW_TYPE = $(st cap capdtm getusr 20 2>/dev/null | tr -d '\r' | sed -n 's/.*UserData is \(.*\)/\1/p')"
  ;;

#---------------------------------------------------------------
# ★ gui / quit 已于 2026-10-05 移除（X11 全屏 720x480 在单核机上吃满 CPU，
#   点一下整机卡死；flab_ui.sh 已删除）。
#   交互入口只剩 mod_gui（菜单页由 mkgui 生成）+ 机身键 cycle。
#   配方选择一律走 mod_gui，不要试图恢复 X11 方案。
#  ;;

#---------------------------------------------------------------
cycle)
  # ★ 轮换到下一个配方（为机身按键设计，零界面、零 X11）
  # ★★ 与 apply 一样：永远写 slot 9（UI「自定义1」），位置恒定 → 真正的一键
  # 状态文件记录当前索引，SD 卡上，相机重启后保持
  ST=/mnt/mmc/filmlab/cur.idx
  N=$(jlist | grep -c .)
  [ -z "$N" ] || [ "$N" -lt 1 ] && { echo "配方库为空"; exit 1; }
  CUR=0
  [ -f "$ST" ] && CUR=$(cat $ST 2>/dev/null)
  case "$CUR" in ""|*[!0-9]*) CUR=0 ;; esac
  NEXT=$(( (CUR + 1) % N ))
  # 取第 NEXT 个配方名
  KEY=$(jlist | sed -n "$((NEXT+1))p")
  [ -z "$KEY" ] && { echo "取配方名失败"; exit 1; }
  # 固定写 slot 9（UI 上的自定义1），保证"当前选中项"固定
  SLOT=9
  ENUM=$(enum_of_slot $SLOT)
  set_r 0 $SLOT "$(jval $KEY R_COLOR)"; set_r 1 $SLOT "$(jval $KEY G_COLOR)"
  set_r 2 $SLOT "$(jval $KEY B_COLOR)"; set_r 3 $SLOT "$(jval $KEY HUE)"
  set_r 4 $SLOT "$(jval $KEY SATURATION)"; set_r 5 $SLOT "$(jval $KEY SHARPNESS)"
  set_r 6 $SLOT "$(jval $KEY CONTRAST)"
  # ★ 同样必须强制重读：cycle 恒定写 slot 9，enum 永远是 9，
  #   旧代码的 setusr 20 <9> 在第二次按 S1 时是同值空操作 → 按了没反应。
  pw_force_reload $(printf "0x%06x" $((0x140000 + ENUM)))
  echo $NEXT > $ST
  NTH=$((NEXT+1))
  echo "[$NTH/$N] $(jlabel $KEY)  (key=$KEY, reload=$RELOAD)"
  log "$(date '+%H:%M:%S') cycle -> [$NTH/$N] $KEY reload=$RELOAD"
  ;;

slots)
  echo "=== 槽位映射 ==="
  echo "slot 9 = 0x140009  UI 自定义1  可见  ← FilmLab 主用"
  echo "slot 10= 0x14000a  UI 自定义2  可见"
  echo "slot 11= 0x14000c  UI 自定义3  可见   ★ enum 与 slot 错位 1"
  echo "slot 12= —               隐藏  ★ CUSTOM_4 在 prefman 存在但 UI 不显示"
  echo "                          ★ 已禁止写入：脏数据会污染整机状态"
  echo "                          ★ 修复请跑 filmlab.sh reset（它会清到 slot 12）"
  echo
  echo "当前 PW_TYPE = $(st cap capdtm getusr 20 2>/dev/null | tr -d '\r' | sed -n 's/.*UserData is \(.*\)/\1/p')"
  ;;

#---------------------------------------------------------------
check)
  # ★★ 客观判据（只读）：ISP 手上那 7 维 vs prefman 槽位值
  #   这是"参数到底有没有进 ISP"的唯一可信判据（不是回读 prefman，也不是看 enum 回显）
  echo "=== FilmLab 参数通道判据 ==="
  check_isp_pw "" ${2:-9}
  ;;

#---------------------------------------------------------------
pwvar)
  # ⛔ 已作废：capdtm setvar 写 PW 运行时变量（varlist 下标 ≠ setvar id，且盲试会写死
  #    p7 capture 服务）。2026-10-08 上机实测证伪，2026-10-09 移除探测代码。
  echo "⛔ pwvar 已作废（setvar 通道实测不通，且盲试有写死 ISP 的风险）。"
  echo "   请改用: filmlab.sh check   —— 只读判据，直接告诉你参数有没有进 ISP。"
  ;;

#---------------------------------------------------------------
reload)
  # ★ 只重触发、不写配方：把「当前 slot$SLOT 的值」重新推一遍
  #   用途：配方的存储值没变，但画面没跟上时，不必再点一次配方（省一次 prefman 写）
  SLOT=9
  ENUM=$(enum_of_slot $SLOT)
  V0=$(get_r 0 $SLOT); V1=$(get_r 1 $SLOT); V2=$(get_r 2 $SLOT)
  V3=$(get_r 3 $SLOT); V4=$(get_r 4 $SLOT); V5=$(get_r 5 $SLOT); V6=$(get_r 6 $SLOT)
  case "" in
    $V0|$V1|$V2|$V3|$V4|$V5|$V6)
      echo "★ 拒绝：slot $SLOT 有字段读不到（PW 段可能被写坏）⇒ 先跑 filmlab.sh dump $SLOT 自查"
      exit 1 ;;
  esac
  pw_force_reload $(printf "0x%06x" $((0x140000 + ENUM)))
  RELOAD2="off"
  [ "$FILMLAB_MODE" = "1" ] && trigger_reload
  echo "reload: slot$SLOT = $V0/$V1/$V2/$V3/$V4/$V5/$V6"
  echo "  ② 选择=$RELOAD  模式触发=$RELOAD2"
  check_isp_pw "" $SLOT
  log "$(date '+%H:%M:%S') reload slot$SLOT reload=$RELOAD isp=$ISP_SYNC"
  ;;

#---------------------------------------------------------------
pwpush)
  # ★ ③ PW 直推（2026-10-09，ATTR_BUS_MCB 通道）：把配方的 7 维送进 ISP PW 引擎
  #   用法: pwpush <recipe> [--yes]      —— 默认 dry-run；--yes 真发
  #   前置: pwsend.arm 已部署；pwcalib.sh 校准完成后 PWID_* 为实测值
  #   ★ 这是「一键滤镜」的直推步骤本体；apply 在 FILMLAB_PW=1 时会自动调用它。
  [ -z "$REC" ] && { echo "用法: pwpush <recipe> [--yes]（默认 dry-run）"; exit 1; }
  V0=$(jval $REC R_COLOR);   V1=$(jval $REC G_COLOR);    V2=$(jval $REC B_COLOR)
  V3=$(jval $REC HUE);       V4=$(jval $REC SATURATION)
  V5=$(jval $REC SHARPNESS); V6=$(jval $REC CONTRAST)
  case "" in
    $V0|$V1|$V2|$V3|$V4|$V5|$V6)
      echo "★ 拒绝：配方 '$REC' 字段读不到（先 filmlab.sh list 自查）"; exit 1 ;;
  esac
  echo "pwpush '$REC' => R/G/B=$V0/$V1/$V2 HUE=$V3 SAT=$V4 SHARP=$V5 CON=$V6"
  if [ "$SLOT" = "--yes" ]; then
    pw_direct "$V0" "$V1" "$V2" "$V3" "$V4" "$V5" "$V6" --yes
  else
    echo "（dry-run；加 --yes 真发）"
    pw_direct "$V0" "$V1" "$V2" "$V3" "$V4" "$V5" "$V6"
  fi
  echo "  （校验请跑 filmlab.sh check）"
  ;;

#---------------------------------------------------------------
mkgui)
  # ★ 从 SD 卡配方库生成 mod_gui 菜单页（2026-10-10 提速版）
  #   提速三招（把 ~60 次 fork 压到 ~4 次 —— 这是"菜单弹出 2 秒多"的头号来源）：
  #     ① 干掉冗余的 jlist 预扫：TOTAL 直接用配方表行数，不再数两遍
  #     ② 按钮生成改【单个 awk】：原来每行 fork 3 次（echo|tr|sed）× 18 行 = 54 次
  #     ③ 菜单/配方表【带缓存】：源没变就直接退出（重复开菜单 / 翻页回看 ≈ 0 成本）
  #   分页版：每页 18 个 + 上/下页 + 返回/取消 = 22（mod_gui 上限）
  #   页状态 /mnt/mmc/filmlab/page.idx；翻页用 filmlab_page.sh
  OUT=/opt/usr/nx-ks/gui_filmlab1b.NX500
  PERPAGE=18                   # 每页配方数（同步：flab.py / filmlab_page.sh）
  ST=$LAB/cur.idx              # 当前配方索引（打 ★）
  PG=$LAB/page.idx             # ★ 页状态（0 基）
  TBL=$LAB/recipes.txt         # 扁平配方表（mkgui / nxfilmui 共用）
  SIGF=$OUT.sig                # ★ 输入指纹（上次生成时的快照）
  TMD5F=$TBL.md5               # ★ 配方表指纹

  # ---- 输入指纹：用【内容哈希】，不用 mtime ----
  #   ★ 踩坑记录：初版用 `[ "$PG" -ot "$OUT" ]` 判缓存 —— 在机上时灵时不灵。
  #     真因：/opt/usr 是 ext4、SD 卡是 exFAT，两侧 mtime 粒度不同 ⇒ page.idx 与成品
  #     会判成"同秒"（-ot 为假）⇒ 每次都全量重建。内容哈希是确定的，与文件系统无关。
  RMD5=$($BB md5sum "$RECIPE" 2>/dev/null); RMD5=${RMD5%% *}
  CUR=0;  [ -f "$ST" ] && read -r CUR  < "$ST"  2>/dev/null
  PAGE=0; [ -f "$PG" ] && read -r PAGE < "$PG" 2>/dev/null
  case "$CUR"  in ""|*[!0-9]*) CUR=0  ;; esac
  case "$PAGE" in ""|*[!0-9]*) PAGE=0 ;; esac

  # ---- 配方表：RECIPE 内容变了才重建（原子替换，绝不留半成品）----
  TMD5=""
  [ -f "$TMD5F" ] && read -r TMD5 < "$TMD5F" 2>/dev/null
  if [ ! -s "$TBL" ] || [ "$RMD5" != "$TMD5" ]; then
    jtable > "$TBL.tmp" 2>/dev/null
    if [ -s "$TBL.tmp" ]; then
      mv -f "$TBL.tmp" "$TBL"
      printf '%s\n' "$RMD5" > "$TMD5F"
    else
      rm -f "$TBL.tmp"
    fi
  fi
  [ -s "$TBL" ] || { echo "mkgui: 配方库为空（表为空），保持原菜单不动"; exit 1; }

  TOTAL=$($BB grep -c . "$TBL" 2>/dev/null)
  case "$TOTAL" in ""|*[!0-9]*) TOTAL=0 ;; esac
  [ "$TOTAL" -lt 1 ] && { echo "mkgui: 配方库为空，保持原菜单不动"; exit 1; }
  PAGES=$(( (TOTAL + PERPAGE - 1) / PERPAGE ))
  [ "$PAGES" -lt 1 ] && PAGES=1
  [ "$PAGE" -ge "$PAGES" ] && PAGE=$((PAGES - 1))   # 越界归一（删配方后页数变少）
  printf '%s\n' "$PAGE" > $PG
  START=$((PAGE * PERPAGE))
  # 本页按钮数（纯算术，不额外 fork）
  N=$((TOTAL - START)); [ "$N" -gt "$PERPAGE" ] && N=$PERPAGE; [ "$N" -lt 0 ] && N=0

  # ---- 菜单缓存（★ 关键提速）：输入指纹一致 ⇒ 直接复用，不重建不写盘 ----
  SIG="$RMD5 $PAGE $CUR"
  OLD=""
  [ -f "$SIGF" ] && read -r OLD < "$SIGF" 2>/dev/null
  if [ -s "$OUT" ] && [ -n "$OLD" ] && [ "$OLD" = "$SIG" ]; then
    echo "mkgui: 菜单已是最新（缓存命中），跳过重建"
    exit 0
  fi

  #先写头部（务必 LF 行尾 —— CRLF 会让 mod_gui 解析失败）
  {
    echo "#====================================================================="
    echo "# gui_filmlab1b.NX500 —— FilmLab 一键配方（由filmlab.sh mkgui 自动生成）"
    echo "#   第 $((PAGE+1))/$PAGES 页（每页 $PERPAGE 个；配方库共 $TOTAL 个）"
    echo "#====================================================================="
    echo "# ★ 本文件是生成物，不要手改。改配方请编辑 SD卡 filmlab/recipes.json"
    echo "#   然后重新打开 mod_gui（或 telnet 执行 filmlab.sh mkgui）"
    echo "#格式：button|标签|命令"
    echo ""
  } > "$OUT.tmp"

  # ★ 单个 awk 生成本页按钮（原来每行 fork 3 次，18 行 = 54 次；这里 1 次）
  #   标签剥离 引号/逗号/CR/竖线（竖线会破坏 mod_gui 解析）；当前配方打 ★
  "$BB" awk -F'|' -v start="$START" -v per="$PERPAGE" -v cur="$CUR" '
    NR <= start { next }
    NR >  start + per { exit }
    {
      k = $1; if (k == "") next
      l = $2; if (l == "") l = k
      gsub(/["\r,|]/, "", l)
      if (start + n == cur) l = "★ " l
      n++
      printf "button|%s|/opt/usr/nx-ks/filmlab.sh apply %s --fast\n", l, k
    }
  ' "$TBL" >> "$OUT.tmp"

  {
    echo ""
    if [ "$PAGES" -gt 1 ]; then
      echo "button|◀ 上页$((PAGE+1))/$PAGES|/opt/usr/nx-ks/filmlab_page.sh prev"
      echo "button|▶ 下页$((PAGE+1))/$PAGES|/opt/usr/nx-ks/filmlab_page.sh next"
    fi
    echo "button|返回|@/opt/usr/nx-ks/gui_filmlab.NX500"
    echo "button|取消|/opt/usr/nx-ks/gui_exit.sh"
  } >> "$OUT.tmp"

  # ★ 原子替换：mod_gui 只会看到完整菜单文件，绝不读到半成品
  mv -f "$OUT.tmp" "$OUT"
  # ★ 记录本次生成所用的输入指纹（下次比对；内容哈希，跨文件系统可靠）
  printf '%s\n' "$SIG" > "$SIGF"

  echo "mkgui: 已生成 $OUT — 第 $((PAGE+1))/$PAGES 页，$N 个配方按钮（配方库共 $TOTAL 个）"
  log "$(date '+%H:%M:%S') mkgui -> page $((PAGE+1))/$PAGES, $N buttons (of $TOTAL)"
  ;;

#---------------------------------------------------------------
export)
  # ★ 从 SD 卡 JSON 导出扁平配方表，给机内 UI 程序（nxfilmui.arm）读。
  #   nxfilmui 不解析 JSON（相机上也没有 jq），只读纯文本：
  #     key|label|R|G|B|HUE|SAT|SHARP|CON
  #   ★ 2026-10-09 优化：改用 jtable（单 awk 进程）——35 配方从 ~90s 降到 <1s。
  OUT=$LAB/recipes.txt
  TMP=$OUT.tmp
  jtable > $TMP
  N=$(grep -c . $TMP 2>/dev/null)
  case "$N" in ""|*[!0-9]*) N=0 ;; esac
  if [ "$N" -gt 0 ]; then
    mv -f $TMP $OUT
    echo "export: 已生成 $OUT — $N 个配方"
  else
    rm -f $TMP
    echo "export: 生成失败（配方库空或格式异常），保持原$OUT 不变"
    exit 1
  fi
  ;;

#---------------------------------------------------------------
*)
  echo "filmlab-apply.sh — FilmLab SD 卡配方引擎"
  echo
  echo "  list              列出 SD 卡全部配方"
  echo "  show <recipe>     查看配方内容"
  echo "  apply <recipe> [slot] [--fast]   默认跟随当前画面向导栏位，应用配方"
  echo "  preview <recipe> [slot]         保持当前栏位即时预览，不保存到闪存"
  echo "  commit <recipe> [slot]          应用并保存当前栏位"
  echo "  quick <recipe>    只切风格（零写入，槽需已预写）"
  echo "  preset            预写 3 个可见槽并 save"
  echo "  dump [slot]       读回槽位值"
  echo "  slots             槽位映射表"
  echo "  wb <K> <a> <b> [manual|auto|keep]   单独设白平衡"
  echo "  wbdump            WB 段完整状态"
  echo "  preset <recipe> [slot]     预写一个槽（供 UI 零延迟选）"
  echo "  reset             全部槽位恢复出厂中性"
  echo "  mkgui             ★ 从 SD 卡配方库生成 mod_gui 菜单页（打开 mod_gui 时自动跑）"
  echo "  export            ★ 导出 recipes.txt（给机内 UI 程序读）"
  echo "  cycle              轮换到下一个配方（绑机身键用，零界面）"
  echo "  check [slot]      ★ 客观判据（只读）：ISP 手上的 7 维 vs prefman 槽位值"
  echo "  reload            ★ 只重触发（不写配方）+ 打印判据 —— 配方没变但画面没跟上时用"
  echo "  pwpush <recipe> [--yes]  ★ ③ PW 直推（10-15 = A2 全 7 维）：七维原始值直进 ISP（默认 dry-run）"
  echo "  quit               关闭 X11 选择器（已弃用，X11 在单核机上会吃满 CPU）"
  echo
  echo "★ 生效通道：①prefman 存储 ②setusr 选择 ③【PW 直推（A2 全 7 维）】"
  echo "  ① ② 到不了 ISP；③ = A2 档位池直写 0x134..0x13B（R/G/B/HUE/SAT/SHARP/CON 全 7 维）【10-15 实测 PASS】"
  echo "  · 全 7 维进 ISP 的自动路 = A2（已刷、已验证）；官方画面向导（自定义1）仍为保底"
  echo "  · 置 FILMLAB_PW=1 ⇒ apply 即一键生效（自动直推全 7 维）"
  ;;

esac
