#!/bin/sh
#=====================================================================
# filmlab_page.sh —— FilmLab 菜单翻页器（配合 mkgui 分页版）
#=====================================================================
# 用法：filmlab_page.sh next | prev
# 由 mod_gui 菜单里的「▶ 下页 / ◀ 上页」按钮调用：
#   点击即退（mod_gui 固有行为）→ 本脚本改页 → 重生成菜单 → 自动重开菜单。
# 页状态：/mnt/mmc/filmlab/page.idx（0 基；mkgui 读取并做越界归一）
# 翻页为环形（末页 next 回第 1 页）；页码在导航按钮 label 上可见（如「▶ 下页2/4」）。
#
# ★ 2026-10-10 提速版：原来这里是【两个 sleep 1】= 2 秒纯白等（点"下页"要等两秒多）。
#   现在：① 切屏后台发，不阻塞；② 页数改读 recipes.txt（与 mkgui 同源，不再 re-parse JSON）；
#         ③ 旧窗口改"退了就走"的有界等待（点击即退 ⇒ 通常 0 轮）。
#=====================================================================
BB=/opt/usr/nx-ks/busybox
D=/opt/usr/nx-ks
# ★ 2026-11-13 统一存储层：page.idx 是纯易失游标（重启回第 1 页无副作用），
#   挪到 tmpfs；recipes.txt 是 export/mkgui/recipelib 三方共享文件，仍留 SD。
if [ -r /opt/usr/nx-ks/nxstore.sh ]; then . /opt/usr/nx-ks/nxstore.sh; fi
command -v nx_ram >/dev/null 2>&1 || nx_ram() { _d=/tmp/nx/${1:-state}; mkdir -p "$_d" 2>/dev/null; echo "$_d"; }
command -v nx_log >/dev/null 2>&1 || nx_log() { mkdir -p /tmp/nx/log 2>/dev/null; echo "$*" >> /tmp/nx/log/main.log 2>/dev/null; }
LAB=/mnt/mmc/filmlab
PG=$(nx_ram filmlab)/page.idx
TBL=$LAB/recipes.txt
PERPAGE=18          # 同步：mkgui 与 flab.py 的 PERPAGE

DIR=$1
case "$DIR" in next|prev) ;; *) echo "用法: filmlab_page.sh next|prev"; exit 1 ;; esac

# 页数：与 mkgui 同源（recipes.txt 行数）；表缺失时现场导一次
[ -s "$TBL" ] || "$D/filmlab.sh" export >/dev/null 2>&1
N=$($BB grep -c . $TBL 2>/dev/null)
case "$N" in ""|*[!0-9]*) N=0 ;; esac
PAGES=$(( (N + PERPAGE - 1) / PERPAGE ))
[ "$PAGES" -lt 1 ] && PAGES=1

PAGE=$(cat $PG 2>/dev/null)
case "$PAGE" in ""|*[!0-9]*) PAGE=0 ;; esac

if [ "$DIR" = "next" ]; then
  PAGE=$(( (PAGE + 1) % PAGES ))
else
  PAGE=$(( (PAGE - 1 + PAGES) % PAGES ))
fi
echo "$PAGE" > $PG

# 切 LCD（与 EV_AEL 同款：不切的话窗口可能起在 EVF 上）—— 后台发，不等
{ st app bb lcd on; st app disp lcd; } > /dev/null 2>&1 &

# 重生成菜单：页号刚变过 ⇒ 必重建（mkgui 缓存只对"没变化"生效）
"$D/filmlab.sh" mkgui >/dev/null 2>&1

# 旧窗口退干净：点击即退，通常已退出；有界等待最多 0.6s，退了立刻走
i=0
while [ $i -lt 3 ]; do
  $BB pidof mod_gui > /dev/null 2>&1 || break
  $BB killall -q mod_gui 2>/dev/null
  $BB sleep 0.2
  i=$((i+1))
done

nice -n +15 $D/mod_gui $D/gui_filmlab1b &
nx_log filmlab "page -> $((PAGE+1))/$PAGES ($DIR)"
exit 0
