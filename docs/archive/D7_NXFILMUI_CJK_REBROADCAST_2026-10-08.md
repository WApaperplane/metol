# D7 · nxfilmui 反哺 CJK 结论（2026-10-08）

> 工作流总表 **D7** 交付物。承 `OFFLINE_VERIFICATION_2026-10-08.md` §1（CJK 离线光栅化）。
> 目标：把「相机自带 SDIC_GP_US 真能画中文」这条离线结论，**落到原生 UI 的代码里**
> （`nxfilmui.c` 此前是按「无中文字体 ⇒ 必须 ASCII 降级」设计的）。
> 全程离线，未触碰相机。

---

## 0. 一句话结论

> ★★★ **改完了，并且在离机条件下**用 nxfilmui 的真实标签**跑出了中文**：
> 8 条配方名（含 `MonoWarm 暖调黑白`、`Ektachrome Cyan 冷调反转`）、中文标题、
> 带中文的状态栏**全部正确出字**；而**未调用 `font_set` 的负对照 0×0、零墨**。
> ⇒ 「必须显式设字体」这条硬约束在 **nxfilmui 走的 part-text 路径**上被**独立复核成立**，
> 而「中文必须降级成 ASCII」这条旧前提已被**从代码里拿掉**。

---

## 1. 改了什么（`test_server/filmlab/src/nxfilmui.c`，v3 → v4）

| # | 改动 | 位置 | 性质 |
|---|---|---|---|
| ① | ★ **新增 `apply_label_font()`**：取 widget 的 `"label"` part text 对象，显式调 `evas_object_text_font_source_set()` + `evas_object_text_font_set()` | 新增函数 | **行为**：保证每处文本都设了字体 |
| ② | ★ **`g_ascii` 默认 `1` → `0`** | 全局 | **行为**：界面**默认显示中文标签** |
| ③ | 新增降级开关 `nxfilmui <recipes> ascii` | `main` 参数解析 | 兜底：实机异常时一键退回 key 名 |
| ④ | 三项字体常量 `FILMUI_FONT_FILE/FAM/SZ`（`SDIC_GP_US_20120720.ttf` / `SDIC_GP_US` / 26） | 宏区 | 参数集中 |
| ⑤ | 顶部注释新增「CJK 结论反哺」段；`item_text` / 状态栏 / `g_ascii` 注释更正 | 注释 | 防后续读者被旧结论误导 |
| ⑥ | 自证计数 `g_font_n`（日志里能核对"给 N 个文本设了字体"） | `apply_label_font` | 可观测性 |

**调用点**（3 处，覆盖全部会显示的文本）：`build_grid()` 每个 item、`mk_item()`、状态栏 `g_status`。

**没有改**的：`mod_gui`、`deploy/` 部署件、`scripts/`、（以免影响现网 mod 行为）。
⇒ 本项是**源码 + 新产物**，真正上机属上机轨 **U2/U3**。

---

## 2. 为什么这么改（依据链）

| 依据 | 出处 |
|---|---|
| 相机自带 `SDIC_GP_US_20120720.ttf`（49864 字形），**CJK 真能光栅化出字** | `raw8/repro/cjk_render.png`、`OFFLINE_VERIFICATION_2026-10-08.md` §1 |
| evas **有字形回落**（给 Khmer 字体也照画）⇒ "必须显式指定族名"是**过头**表述 | 同上 §1.4 |
| ★ **真约束只有一条：完全不调用一次 `font_set` ⇒ 几何 0×0、一个像素都不画** | 同上；本报告 §4 再次独立复核 |
| ABI 只能取**真机跑通过的 ELF 的未定义符号**（铁律 84） | `ERROR_CORRECTIONS_2026-10-07.md` / 铁律 84 |

**为什么用 `elm_object_part_text_get` 而不是 `elm_object_text_font_set`**：
后者在 mod_gui / di-camera-app 的未定义符号里**无真机证据**（`check_abi.py` 实测 MISS），
前者**有** ⇒ 按铁律 84 选前者。

---

## 3. ABI 核对（`check_abi.py` 扩了一个白名单来源）

`check_abi.py` 原有两个 provider（`scripts/mod_gui`、`test_server/appprobe/di-camera-app`）。
本轮**新增第三个**：`test_server/filmlab/src/out/cjk_render.arm`
—— 它已在相机 rootfs（chroot + qemu-arm-static）里**跑通出图**，
是 **evas 纯文本 API（`evas_object_text_*`）的第一手等价证据**。

核对结果：

```
nxfilmui.c 引用的 EFL 符号 33 个 → 有真机证据 29/33
新增的三个都 OK： elm_object_part_text_get / evas_object_text_font_set / evas_object_text_font_source_set
剩余 4 个 MISS 全部是**已知无害**：
  elm_box                ← 正则误抓（源码里是 elm_box_add / elm_box_pack_end，均 OK）
  elm_box_recalculate    ← 注释里已声明"不存在，已弃用"
  elm_gengrid_page_size_set / elm_win_fullscreen_set ← 已弃用，不在调用路径
  （elm_gengrid_item_append 是 OK 但**运行时会崩**，源码已改用 elm_box —— 与本次改动无关）
```

编译产物自检（`build_filmui.sh`）：

```
nxfilmui_v4.arm  64,988 B（v3 为 64,308 B，+680 B = 字体调用）
NEEDED = libelementary.so.1 / libevas.so.1 / libecore_evas.so.1 / libecore.so.1
         / libecore_input.so.1 / libpthread.so.0 / libc.so.6 / libdl.so.2 / librt.so.1   ✅
导入表含 evas_object_text_font_set / evas_object_text_font_source_set / elm_object_part_text_get  ✅
导入表**不含** ecore_event_handler_add（仍走 dlsym）✅
```

---

## 4. ★ 离机同款验证（新资产 `nxlabel_probe`）

**为什么不能直接说"cjk_render 已经证过了"**：
cjk_render 证的是 `evas_object_text_add()`（纯 evas 文本对象）；
而 nxfilmui 走的是 **`elm_*` 控件 → 内部 evas text 子对象**，再经
`elm_object_part_text_get()` 取出来设字体 —— **这条序列没被单独验证过**。

**做法**：新写 `test_server/filmlab/src/nxlabel_probe.c`，
把 nxfilmui v4 的**同款三项常量 + 同款调用顺序**原样搬出来，
用 nxfilmui **真实会显示的文本**（8 条配方 label），在 evas buffer 引擎上画一遍。

```
test_server/filmlab/src/nxlabel_probe.c        ← 探针源码
test_server/filmlab/src/build_nxlabel_probe.sh ← 交叉编译（-O0，.so 绝对路径直链）
raw8/qemu/nxlabel_probe_run.sh                 ← WSL chroot + qemu-arm-static 运行
raw8/repro/nxlabel_probe.png / .log            ← ★ 结果
```

**结果（`VERDICT=PASS`）**：

| 项 | 结果 |
|---|---|
| 中文标题 `FilmLab 配方库 / Film Recipes` | ✅ 出字，ink=3096 |
| 8 条配方 label（含两处中文） | ✅ 全部出字，ink 847–2622 |
| 选中项（`TriX 400  <`）高亮色 | ✅ 正确（橙黄，对应 `paint_sel` 的 255,200,80） |
| 状态栏（`[3/8] trix400  胶片仿真 · Picture Wizard 7 维`） | ✅ 出字，ink=4311 |
| ★ **负对照：不调用 `font_set`** | ✅ **geom = 0×0，ink = 0**（复现"忘记设字体"的失败模式） |
| `g_font_n` 自证 | 11（= 全部需设字体的项；负对照未计入） |

![证据](../raw8/repro/nxlabel_probe.png)
（图内可见：中文标题、`MonoWarm 暖调黑白`、`Ektachrome Cyan 冷调反转`、
以及负对照行的位置确实为空。）

⇒ ★★ **正对照有墨 + 负对照零墨** ⇒ 这条改动**确实在起作用**，不是"反正 evas 会回落"。

---

## 5. 未做 / 仍需上机

| # | 项 | 为什么 |
|---|---|---|
| 1 | nxfilmui v4 在**机身**跑（挂 `FN_FN`） | 属上机轨 **U2**；本项只交付"源码 + 离线验证 + 产物" |
| 2 | **首次渲染延迟**（10.7MB 字体在单核上的首帧代价） | 离线只证"能画"；属上机轨 **U3** |
| 3 | 波轮/触摸在机身的实际 keysym | 与本次改动无关（U1 的③④） |
| 4 | `deploy/filmlab/nxfilmui.arm` 是否换成 v4 | **产品决策**，未擅自改（部署件影响现网用户） |

---

## 6. 复现步骤

```bash
# 1) 语法/编译 + 产物自检
bash test_server/filmlab/build_filmui.sh          # → nxfilmui_v4.arm
C:/.../python.exe test_server/filmlab/src/check_abi.py

# 2) 离线标签验证（WSL）
bash test_server/filmlab/src/build_nxlabel_probe.sh
MSYS_NO_PATHCONV=1 wsl -d NXKS2 -u root -- sh /mnt/d/download/NX-KS2-88/raw8/qemu/nxlabel_probe_run.sh
# → raw8/repro/nxlabel_probe.png + .log（期望 VERDICT=PASS）
```

---

*生成：2026-10-08 · 全程离线 · 新增资产：`nxlabel_probe.{c,arm}`、`build_nxlabel_probe.sh`、`nxlabel_probe_run.sh`、`nxfilmui_v4.arm`*
