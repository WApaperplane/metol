# D2 · 原生 UI 五页离线预渲染（2026-10-08）

> 工作流总表 **D2** 交付物。目标：把 `FIRMWARE_FEATURE_SPACE_2026-10-08.md` §3.2 的五页设计
> **在 PC 上先画出来**（不依赖相机、不依赖 X11），供上机前审阅布局与中文可行性。
> 全程离线，未触碰相机。

---

## 0. 一句话结论

> **五页各出一张 720×480 PNG，保存在 `raw8/repro/ui_page_p{1..5}.png`，中文零 tofu。**
> 渲染走**相机自带 evas 的 buffer 引擎**（chroot + `qemu-arm-static`），字体与
> **D7 的 nxfilmui v4 完全同款**（`SDIC_GP_US` / 26 px，每处文本都显式 `font_set`，全流程 70 次调用）。
>
> ★★ **重要限定（诚实标注）**：本轮出图是**降级绘制** —— 用
> `evas_object_rectangle_add`（面板/行背景/色块/滑块槽/按钮）+ `evas_object_text_add`（全部文字）
> **手工复现五页的信息结构与布局**，而**不是**真实 `elm_list/elm_slider/elm_radio/elm_entry` 控件的外观。
> 原因见 §4。⇒ 这五张图**可以**用来判定「布局是否合理 / 中文是否出字 / 信息是否齐全」，
> **不可以**用来判定「真实控件在机身长什么样」。

---

## 1. 五页规格（实现在 `ui_pages_render.c`）

| 页 | 标题（中/英） | 元件（真实设计 → 本轮降级画法） | 内容 |
|---|---|---|---|
| **P1 配方库** | 配方库 / Recipes | `elm_list`+`elm_scroller` → **2 列网格行**（行底 rect + 色块 rect + 文字） | 8 条配方；选中项高亮 + `<` 标记；状态栏 `[3/8] trix400` |
| **P2 参数实时调** | 参数调整 / Picture Wizard·7 axes | `elm_slider`×7 → **槽 rect + 已填 rect + 数值文字** | PW 七维 R/G/B/HUE/SAT/SHARP/CON = `106/100/93/11/9/9/8`（取自 `nx500_recipes.txt` 第 1 条）|
| **P3 3D LUT 管理** | 3D LUT 管理 / 3D LUT | `elm_list`+`elm_button` → 行 rect + 按钮 rect | SD 卡 `/mnt/mmc/luts/*.cube` 列表（2 条）+ 内置 4 档 + 「写入所选 LUT」「恢复出厂」两按钮 |
| **P4 内置色彩 4 档** | 内置色彩 / Built-in Color·4 slots | `elm_radio` → 行 rect + 圆形选择指示 rect | identity / 暖肤色 / 风格化 / 同 1；选中项 `● 已选` |
| **P5 诊断 / 高危** | 诊断 / Diagnostics·High-risk | `elm_entry`+二次确认 → 行 rect + 按钮 rect + 警示条 rect | p7 md5（与官方一致）/ 分区备份 11/11 / **p8 `★0 非零字节·未解释`**；高危操作（刷写固件=需确认串、备份校验=只读）；`CONFIRM-FLASH` 提示；`boot0/boot1 绝不碰` |

**统一布局**：`header`（0–40）、内容区（48–440）、`statusbar`（444–480）。
**配色**：背景 `#0C0E14`、面板 `#1A1E2C`、选中 `#262C38`、正常文字 `#D2D2D2`、高亮 `#FFC850`、状态栏 `#78FFA0`。

---

## 2. 渲染做法与运行时环境

```
test_server/filmlab/src/ui_pages_render.c     ← 源码（一次进程渲染 5 页）
test_server/filmlab/src/build_ui_pages.sh     ← 交叉编译（zig cc, -O0, .so 绝对路径直链）
raw8/qemu/ui_pages_run.sh                     ← WSL chroot + qemu-arm-static 运行
raw8/repro/ui_page_p{1..5}.png + ui_pages.log ← 产物
```

- 引擎：`ecore_evas_buffer_new(720,480)`（**内存画面，不需 X、不需相机**）
- 字体：`evas_object_text_font_source_set("/usr/share/fonts/SDIC_GP_US_20120720.ttf")`
  + `evas_object_text_font_set("SDIC_GP_US", 26)`
- 出图：`ecore_evas_manual_render()` → `ecore_evas_buffer_pixels_get()` → **自写 PNG**（stored deflate，零依赖）
- 运行环境自证：`evas=1 ecore=1 ecore_evas=1`（三项 init 全成功）、`font exist=1`

**实测日志**：

```
PAGE 1 -> /tmp/ui_page_p1.png  rect_n=19 ink=18512
PAGE 2 -> /tmp/ui_page_p2.png  rect_n=24 ink=30139
PAGE 3 -> /tmp/ui_page_p3.png  rect_n=15 ink=20666
PAGE 4 -> /tmp/ui_page_p4.png  rect_n=11 ink=11321
PAGE 5 -> /tmp/ui_page_p5.png  rect_n=12 ink=22617
== done, total font_set calls = 70
```

> 注：五个 PNG 文件大小相同（1,037,423 B）是**正常现象** —— stored deflate 下 PNG 体积只由**尺寸**决定，
> 与内容无关。内容确有差异，证据是逐页 `ink` 计数不同（11321–30139）。

---

## 3. 逐页验收

| 页 | 出字 | 中文 tofu | 尺寸 | ink | 判定 |
|---|---|---|---|---|---|
| P1 配方库 | ✅ | **无**（`配方库`、`MonoWarm 暖调黑白`、`Ektachrome Cyan 冷调反转` 全部正确） | 720×480 | 18512 | ✅ |
| P2 参数调整 | ✅ | **无**（`红/绿/蓝/色调/饱和/锐度/对比`） | 720×480 | 30139 | ✅ |
| P3 3D LUT | ✅ | **无** | 720×480 | 20666 | ✅ |
| P4 内置色彩 | ✅ | **无**（`暖肤色`、`风格化`） | 720×480 | 11321 | ✅ |
| P5 诊断 | ✅ | **无**（`刷写固件（需确认串）`、`二次确认`…） | 720×480 | 22617 | ✅ |

**人工目视复核**（主控逐张看过 P1/P2/P3/P5）：中文标题、中文标签、选中高亮、色块预览、
滑块填充与数值、按钮、警示条、状态栏**全部正确渲染**，无方框/空白。

★ 与 `NATIVE_UI_DESIGN_2026-10-07.md` 里"中文降级为 `(cjk)`"的旧决策**冲突** —— 那条已被
`OFFLINE_VERIFICATION_2026-10-08.md` §1（CJK 真能画）+ **D7**（nxfilmui v4 实改）取代。

---

## 4. ★ 哪些是真实控件、哪些是降级绘制

| 页 | 真实设计（上机用） | 本轮画法 | 差异 |
|---|---|---|---|
| P1 | `elm_list` + `elm_scroller` | 2 列 `rect` 行 + `text` | 无滚动条外观、无 list 行样式 |
| P2 | `elm_slider` ×7 | 轨道 `rect` + 填充 `rect` + 数值 `text` | 无滑块手柄、无主题外观 |
| P3 | `elm_list` + `elm_button` | 行 `rect` + 按钮 `rect` + `text` | 按钮无按下态/焦点态 |
| P4 | `elm_radio` | 行 `rect` + 圆点 `rect` | 无 radio 勾选动画 |
| P5 | `elm_entry` + 二次确认 | `rect` + `text`（含 `CONFIRM-FLASH` 文案） | **无真实输入框**（`elm_entry` 的文本编辑不可离线复现） |

**为什么必须降级**：真实 `elm_*` 控件需要 `elm_init()` 成功并绑定一个可用 engine。
本轮并行子任务尝试过 `ELM_ENGINE=buffer` 路线并定位到 `elm_init`/engine 选择处的失败
（详细崩溃点见子任务记录）。在**离线 chroot（无显示服务）**下，elementary 这条初始化链
不可稳定通过；而 evas 纯文本路径（`ecore_evas_buffer_new`）**已在 D7 与本项两次独立跑通**。
⇒ 结论：**离线预览用 evas，控件真实性留给上机轨 U2**。

---

## 5. 对上机实现的反哺

1. ★ **中文零成本已被两张图独立证实**（`nxlabel_probe.png` + 本项五页）⇒ UI 文案可以**直接用中文**，
   不需要 ASCII 降级设计。
2. ★ **每处文本都必须 `font_set`** —— 本项 5 页共 70 次调用，**无一例外**。
   漏一处＝那一处 0×0（D7 的负对照已证）。
3. ★ **布局给上机实现一个参照**：P2 的 7 行 × 52 px = 364 px 在 480 高屏内**刚好放得下**（含状态栏），
   这是"机身单屏可容纳全部 7 维"的**数值证据**。
4. ★ **P5 的门控文案**（`CONFIRM-FLASH` + `boot0/boot1 绝不碰`）可直接作为 `elm_entry` 的二次确认串设计。
5. ⚠️ **上机时必须换回真实控件** —— 本预览**不能**作为"控件能否用"的证据（尤其 `elm_entry`）。

---

## 6. 复现步骤

```bash
bash test_server/filmlab/src/build_ui_pages.sh
MSYS_NO_PATHCONV=1 wsl -d NXKS2 -u root -- sh /mnt/d/download/NX-KS2-88/raw8/qemu/ui_pages_run.sh
# → raw8/repro/ui_page_p1..p5.png + ui_pages.log
```

---

*生成：2026-10-08 · 全程离线 · 未触碰相机 · 分支 `nx-ks2`*
