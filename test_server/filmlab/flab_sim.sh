#!/bin/bash
#=====================================================================
# flab_sim.sh —— filmlab.sh 离线仿真回归（PC 侧 · 无需相机）
#=====================================================================
# 背景（2026-10-10）：filmlab 引擎迭代频繁，而相机经常离线。本工具把
# filmlab.sh 放进"仿真相机环境"（路径替换 + prefman/st/pwsend shim），
# 在 PC 上回归验证核心链路与【进程调用数】（速度指标）。
#
# 原理：
#   1. sed 把 /opt/usr/nx-ks → <sim>/opt、/mnt/mmc/filmlab → <sim>/lab
#   2. shim：busybox（转发）/ prefman（记录调用+假读回）/ st（假 getusr）/
#      pwsend.arm（回显参数）——全部追加进 calls.log 供计数
#   3. 用例断言关键输出 + 进程数阈值
#
# 用法:
#   bash test_server/filmlab/flab_sim.sh            # 全部用例
#   bash test_server/filmlab/flab_sim.sh apply-fast # 单用例（见下方 case）
#
# ★ 只读 PC：不连接相机、不修改仓内源码（仿真产物全在 raw8/tmp/flsim/）
#=====================================================================
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
SIM="$ROOT/raw8/tmp/flsim"
RECIPES="$ROOT/scripts/filmlab/recipes.json"
SRC="$ROOT/scripts/filmlab.sh"

PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); echo "  [PASS] $*"; }
bad()  { FAIL=$((FAIL+1)); echo "  [FAIL] $*"; }
n_calls() { grep -c "${1:-^}" "$SIM/calls.log" 2>/dev/null || echo 0; }

#--------------------------------------------------------------- setup
setup() {
  rm -rf "$SIM"
  mkdir -p "$SIM/opt" "$SIM/lab"

  cat > "$SIM/opt/busybox" <<EOF
#!/bin/sh
cmd=\$1; shift
exec "\$cmd" "\$@"
EOF
  cat > "$SIM/opt/prefman" <<EOF
#!/bin/sh
echo "prefman \$*" >> "$SIM/calls.log"
case "\$1" in
  get)
    # 地址 = PW_BASE(41964) + param*52 + slot*4；param<3 是 R/G/B(0-200)，其余 0-20。
    # 旧 shim 一律返回 100 ⇒ backup_slot 的 0-20 校验必然拒绝，整个回归从根上误报。
    rel=\$((\$3 - 41964))
    p=\$((rel / 52))
    if [ "\$p" -lt 3 ]; then echo "value = 100"; else echo "value = 10"; fi
    ;;
  *) : ;;
esac
exit 0
EOF
  cat > "$SIM/opt/st" <<EOF
#!/bin/sh
echo "st \$*" >> "$SIM/calls.log"
case "\$*" in
  "cap capdtm getusr 20"*)
      cur=\$(cat "$SIM/cur_pw" 2>/dev/null)
      [ -n "\$cur" ] || cur="0x140009"
      echo "UserData is CUSTOM (\$cur)"
      ;;
  "cap capdtm setusr 20 "*)
      echo "\$5" > "$SIM/cur_pw"
      ;;
  *) : ;;
esac
exit 0
EOF
  cat > "$SIM/opt/pwsend.arm" <<EOF
#!/bin/sh
echo "pwsend.arm \$*" >> "$SIM/calls.log"
echo "PWSEND: \$*"
exit 0
EOF
  chmod +x "$SIM/opt/busybox" "$SIM/opt/prefman" "$SIM/opt/st" "$SIM/opt/pwsend.arm"

  cp "$RECIPES" "$SIM/lab/recipes.json"
  sed -e "s#/opt/usr/nx-ks#$SIM/opt#g" -e "s#/mnt/mmc/filmlab#$SIM/lab#g" \
      "$SRC" > "$SIM/opt/filmlab_sim.sh"
  chmod +x "$SIM/opt/filmlab_sim.sh"

  export PATH="$SIM/opt:$PATH"
}

reset_calls() { : > "$SIM/calls.log"; }
filmlab()     { sh "$SIM/opt/filmlab_sim.sh" "$@"; }

#--------------------------------------------------------------- 用例
case_apply_fast() {
  echo "== 用例 1：apply --fast（提速路径）=="
  reset_calls
  OUT=$(filmlab apply portra400 --fast)
  echo "$OUT" | grep -q "✓ portra400 -> slot9" && ok "单行结果输出" || bad "输出缺 ✓ 行：$OUT"
  N=$(grep -c "prefman set" "$SIM/calls.log" 2>/dev/null || echo 0)
  [ "$N" = "7" ] && ok "prefman set = 7 次" || bad "prefman set = $N（应 7）"
  T=$(grep -c "prefman\|^st " "$SIM/calls.log" 2>/dev/null || echo 0)
  # 组成：7 set + 7 backup 回读（仅首次）+ 1 save + 2 getusr（CLI 跟随当前档位）
  [ "$T" -le 18 ] && ok "总进程调用 = $T（≤18）" || bad "总进程调用 = $T（应 ≤18）"
}

case_apply_pw() {
  echo "== 用例 2：FILMLAB_PW=1 A2 全 7 维直推（0x134..0x13B + 提交位）=="
  reset_calls
  OUT=$(FILMLAB_PW=1 filmlab apply portra400 --fast)
  echo "$OUT" | grep -q "seq 0x134 108 0x135 100 0x136 93 0x137 11 0x138 6 0x139 9 0x13A 8 0x13B 1" \
    && ok "七维原始值 + 提交位" || bad "A2 seq 错：$(echo "$OUT" | grep -i 'seq ' | head -2)"
  echo "$OUT" | grep -q "0x110" \
    && bad "仍发 A1 三维（0x110-0x112）" || ok "未混入 A1 三维"
  echo "$OUT" | grep -q "pw=direct" && ok "fast 行含 pw=direct" || bad "fast 行缺 pw 状态"
}

case_apply_detail() {
  echo "== 用例 3：apply（详细路径）=="
  reset_calls
  OUT=$(filmlab apply trix400)
  echo "$OUT" | grep -q "通道: ①存储=已写" && ok "通道状态行" || bad "缺通道状态行"
  echo "$OUT" | grep -q "已写入(saved)" && ok "回读写入确认" || bad "缺回读确认"
}

case_jline() {
  echo "== 用例 4：jline 单配方提取（对照实测值）=="
  # 以仿真脚本同款 awk 提取（配方 portra400 实测 = 106/100/93/11/9/9/8）
  LINE=$(awk -v want="portra400" '
    BEGIN { inr=0; key="" }
    /"recipes"/ { inr=1; next }
    /"presets"/ { inr=0; next }
    !inr { next }
    /^    "/ { key=$0; sub(/^    "/,"",key); sub(/": *\{.*$/,"",key); sub(/",? *$/,"",key); delete F; next }
    /^        "/ && key == want { name=$0; sub(/^ *"/,"",name); sub(/":.*$/,"",name); val=$0; gsub(/[^0-9-]/,"",val); F[name]=val; next }
    /^    \}/ { if (key == want) { printf "%s|%s|%s|%s|%s|%s|%s\n", F["R_COLOR"],F["G_COLOR"],F["B_COLOR"],F["HUE"],F["SATURATION"],F["SHARPNESS"],F["CONTRAST"]; exit } }
  ' "$RECIPES")
  [ "$LINE" = "108|100|93|11|6|9|8" ] && ok "portra400 = $LINE" || bad "portra400 提取 = $LINE（配方调色后需同步本基线）"
}

case_mkgui() {
  echo "== 用例 5：mkgui 菜单（分页 + --fast 按钮）=="
  OUT=$(filmlab mkgui)
  echo "$OUT" | grep -q "18 个配方按钮" && ok "分页按钮数 = 18" || bad "按钮数异常：$OUT"
  MENU="$SIM/opt/gui_filmlab1b.NX500"
  grep -q "filmlab.sh apply portra400 --fast" "$MENU" && ok "按钮命令带 --fast" || bad "按钮缺 --fast"
  grep -q "▶ 下页" "$MENU" && ok "分页导航在" || bad "缺分页导航"
}

#--------------------------------------------------------------- 用例 6
# ★ 2026-11-14 新增：ssam87 在 GitHub Discussion 报「换配方后 custom 1 和 custom 2
#   都被改」。根因是 A2 直推在"用户仍停在自定义2"时发送，相机把改动归属到当前档，
#   而引擎只 set/backup 了 slot 9。这个用例钉住两条修复：直推前先切 CUSTOM1、
#   打开面板时所在档位也要备份。
case_pollute() {
  echo "== 用例 6：非 CUSTOM1 档位不被污染（ssam87 2026-11-12 报告回归）=="
  rm -rf "$SIM/lab/slot-backups" "$SIM/ram"
  mkdir -p "$SIM/ram"
  echo "0x14000a" > "$SIM/cur_pw"          # 用户停在 自定义2
  reset_calls
  NX_RAM="$SIM/ram" FILMLAB_PW=1 FILMLAB_ENUM_CACHE=0x14000a filmlab commit portra400 >/dev/null 2>&1
  grep -q "cap capdtm setusr 20 0x140009" "$SIM/calls.log" \
    && ok "直推前切到 CUSTOM1" || bad "没有前置切档（污染窗口仍开着）"
  [ -s "$SIM/lab/slot-backups/slot-10.txt" ] \
    && ok "当前档位 slot10 已备份" || bad "slot 10 无备份（污染后不可恢复）"
  grep -q '^10|' "$SIM/lab/slot-backups/slot-10.txt" 2>/dev/null \
    && ok "备份格式 slot|七维" || bad "备份内容异常"
  A=$(grep -n "setusr 20 0x140009" "$SIM/calls.log" | head -1 | cut -d: -f1)
  B=$(grep -n "pwsend.arm seq" "$SIM/calls.log" | head -1 | cut -d: -f1)
  if [ -n "$A" ] && [ -n "$B" ] && [ "$A" -lt "$B" ]; then
    ok "切档早于直推（行 $A < $B）"
  else
    bad "顺序错：setusr@${A:-无} pwsend@${B:-无}"
  fi
  # 常态（停在 CUSTOM1）必须零 st 开销：cache 已说明在 9 就不该再问一次
  echo "0x140009" > "$SIM/cur_pw"; reset_calls
  NX_RAM="$SIM/ram" FILMLAB_PW=1 FILMLAB_ENUM_CACHE=0x140009 filmlab commit portra400 >/dev/null 2>&1
  N=$(grep -c "cap capdtm setusr" "$SIM/calls.log" 2>/dev/null || :)
  N=${N:-0}
  [ "$N" = "0" ] && ok "停在 CUSTOM1 时零 setusr" || bad "多做 $N 次 setusr"
}

#--------------------------------------------------------------- main
ALL=(apply-fast apply-pw apply-detail jline mkgui pollute)
WANT="${1:-all}"

setup
echo "仿真环境: $SIM"
echo ""

for c in "${ALL[@]}"; do
  [ "$WANT" != "all" ] && [ "$WANT" != "$c" ] && continue
  case "$c" in
    apply-fast)   case_apply_fast ;;
    apply-pw)     case_apply_pw ;;
    apply-detail) case_apply_detail ;;
    jline)        case_jline ;;
    mkgui)        case_mkgui ;;
    pollute)      case_pollute ;;
  esac
  echo ""
done

echo "=========================================="
echo "RESULT: $([ $FAIL -eq 0 ] && echo PASS || echo FAIL)  ($FAIL fail / $PASS pass)"
exit $([ $FAIL -eq 0 ] && echo 0 || echo 1)
