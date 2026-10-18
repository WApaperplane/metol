# U2 · 原生 EFL UI 上机 —— 进展与显示障碍诊断（2026-10-08）

> 工作流总表 **U2**（"nxfilmui 上机"）执行报告。
> 结论：**部署、probe、起 UI、"不拖垮相机"四项全部达成；但窗口不出现在 LCD 上** —— 这是
> 从 **2026-10-07 就存在**、当时记为"剩余待验①"的核心障碍，本轮仍未解开，但**把原因域大幅收窄**。

---

## 0. 一句话结论

> ★★ **UI 进程起来了、相机也不卡（铁律 104 通过），但屏幕上看不到。**
> 已用对照实验排除 5 类原因（env / 显示设备 / 窗口 API / 主循环 / 辅助进程盖屏）；
> ★ **决定性的对照事实：`mod_gui` 在完全同样的环境下能显示** ⇒ 问题一定出在本程序自身，
> 且**一定有解**。剩余候选只剩 3 个（窗口几何 / 窗口 layer / DRM master 独占）。

---

## 1. 已达成（U2 的正面结果）

| 项 | 结果 | 证据 |
|---|---|---|
| 部署 | `nxfilmui.arm` → `/opt/usr/nx-ks/filmlab/`；`flab_ui.sh` → `/opt/usr/nx-ks/` | md5 三方一致 |
| ★ 未碰键槽位 | 全程**不改** `EV_MOBILE.sh` / 任何 `EV_*` 槽位 | 保持安全版 `54a308b8` |
| `probe` 模式 | `load_recipes -> 8`，8 条配方全列出（**中文 label 正常出字**），只读回读 slot9 PW 成功 | `probe_out.txt` |
| 起 UI | `elm_init ok` → `ecore_event_handler_add resolved` → `build_grid: 8 items in 2 columns` → `showing window`，无 FATAL | `filmui.log` |
| ★★ **不拖垮相机** | 用户判定"**流畅**" | 铁律 104（10-07 就是栽在这一条） |

⇒ U2 的验收判据中，"probe 输出配方表 ✅"、"人确认没拖垮 ✅" 已达成；
未达成的是"**开 UI 能看见并交互**"。

---

## 2. ★ 对照实验与排除清单（铁律 118）

| # | 假设 | 实验 | 结论 |
|---|---|---|---|
| 1 | telnet 起的进程环境不足以显示 EFL | 用 **telnet** 跑 `EV_EV.sh` 起 `mod_gui` | ❌ **排除** —— mod_gui 能显示，用户看见菜单 |
| 2 | env 缺图形变量 | 复刻 `di-camera-app` 的 env（含 `LD_LIBRARY_PATH=:/usr/lib:/usr/lib/driver`、`EVAS_GL_NO_BLACKLIST=1`） | ❌ **无效**，屏幕依旧 |
| 3 | 没连上显示设备 | `ls -l /proc/<pid>/fd` | ❌ **排除** —— nxfilmui 已持有 `/dev/dri/card0` + `/dev/ump`，**与 mod_gui 完全相同** |
| 4 | 窗口创建 API 不同 | 解析两者 `.dynsym` | ❌ **排除** —— 都是 `elm_win_add` + `elm_win_resize_object_add` + `evas_object_show` |
| 5 | 主循环不驱动 evas 渲染 | 新增 `NXFUI_ELMRUN=1` 强制走 `elm_run()`（v5） | ❌ **无效** —— 日志确认 `step: entering elm_run` 且未返回，屏幕仍无变化 |
| 6 | 相机 UI 辅助进程盖屏 | 补 `killall focus_stack/focus_buttons/popup_*/onscreen_ov/onscreen_235` | ❌ **无效** |

---

## 3. 剩余候选（按"实验成本"排序）

| # | 候选 | 判据 / 实验 | 成本 |
|---|---|---|---|
| **A** | 窗口几何为 0×0 或位置不在屏内 | 编译 **v6**：显式 `evas_object_resize(g_win, 720, 480)` + `evas_object_move(g_win, 0, 0)`（+ 试 `elm_win_activate`） | 低（改 3 行 + 交叉编译） |
| **B** | 窗口 layer / type 不对 | 试 `elm_win_fullscreen_set` 或改 `elm_win_add` 的 type | 低 |
| **C** | ★ **`di-camera-app` 是 DRM master、独占 primary plane**（z-order） | 临时 `killall di-camera-app` 后看 UI 是否出现（**需授权**；相机屏幕会黑，但 telnet 在、重启即恢复） | 中（有风险，判定力最强） |
| **D** | 保底方案 | 走 **mod_gui 路径**：`mod_gui /opt/usr/nx-ks/gui_filmlab1b` 直达配方列表（**mod_gui 已证能显示**） | 低（已存在资产） |

**建议顺序**：A → B → C；若都不成，用 D 保底（放弃自绘窗口，改用 mod_gui 菜单承载）。

---

## 4. 现场状态与回滚

```
UI 进程      0 个（已清理）
di-camera-app 正常运行（PID 247）
loadavg       1.32 1.53 1.23（相机正常）
```

**回滚（如需完全移除本次部署）**：
```sh
rm -rf /opt/usr/nx-ks/filmlab /opt/usr/nx-ks/flab_ui.sh
```
（不影响既有 mod：未改 `EV_MOBILE.sh`、未改任何键槽位。）

---

## 5. 本轮新增资产

| 文件 | 说明 |
|---|---|
| `test_server/filmlab/nxfilmui_v5.arm` | 65036 B，主循环加 `NXFUI_ELMRUN` 开关（默认行为不变） |
| `test_server/filmlab/src/nxfilmui.c` | 同上改动 + 注释记录本轮排查依据 |
| `test_server/filmlab/build_filmui.sh` | 输出改为 v5 |

---

## 6. ★★ 最终结论（20:50 更新）：尺寸问题已解，但"全屏自绘窗口"这条路在本机走不通

### 6.1 已被证实的两条

**1）"看不见"的真因 = 窗口尺寸只有 1px —— 已修复**

| 版本 | 改动 | `win geom` |
|---|---|---|
| v6 | 加几何自证日志 | `1x53` ← **1 像素宽，肉眼不可见** |
| v7 | box 给 `size_hint_min(720,480)` + 子项补宽度 | `720x53` |
| v8 | 追加 `elm_win_fullscreen_set` + show 后 `evas_object_resize` | **`720x480` ✅** |

机制：`elm_win_resize_object_add` 把窗口尺寸绑到 box 的 size hint，而 box 内所有子项的
`size_hint_min` **宽度都写成 0**（`g_title` 0×28 / `scroll` 无 hint / `g_status` 0×26）
⇒ box 最小宽度被算成 1px。修法已固化进 `nxfilmui.c`。

**2）★★ 但全屏形态会把整机拖死 —— 架构级，不是参数问题**

| 版本 | 主循环 | 窗口 | 结果 |
|---|---|---|---|
| v5 | `elm_run()`（阻塞） | 1×53 | 流畅（因为几乎无渲染） |
| v8 | `ecore_main_loop_iterate`（**忙轮询**，`spin=328000`） | 720×480 | 卡死（可 telnet 止损） |
| v9 | `elm_run()`（阻塞） | 720×480 | **卡死，21/23 端口全不通，需物理重启** |

⇒ 换了主循环照样卡 ⇒ **单核 + 全屏 GL 渲染**是硬墙。
对照事实：**mod_gui 能显示且不卡**（小窗口、控件少）。

### 6.2 ★ 方法论修正（本轮自己犯的错）

- 早先把照片里那条横带当成"我们的窗口"，属**无对照的推断**（违反本项目铁律 118），**用户已纠正**。
- "起 UI 后 4 秒 `loadavg = 0.94`" 被我当成"不拖垮"—— **不足够**：v9 随后仍然卡死。
  ⇒ 纪律升级：图形实验必须**持续观察 ≥30 秒 + 两轮测负载**；"按键无响应"是独立于 loadavg 的判据。

### 6.3 路线修正（三条，均不再走"全屏自绘窗口"）

| 方案 | 内容 | 状态 |
|---|---|---|
| **A（推荐·保底）** | `mod_gui /opt/usr/nx-ks/gui_filmlab1b` 直达配方列表 | mod_gui 已证能显示、不卡；代价 = 失去"滚动不关窗"的对比体验 |
| **B** | 把 nxfilmui 改成**轻量小 HUD**（如 200×120、只显 1–3 条、去滚动） | 需重新设计 + 离线估渲染量后再上机 |
| **C** | 只用 `cycle` 零 UI（`popup_timeout` 弹配方名） | 已证可用；无列表 |

### 6.4 现场

- 相机**需物理重启**（长按电源）。重启后 `/opt/usr/nx-ks/filmlab/` 与 `flab_ui.sh` 仍在，但**不会自启**
  （未挂任何键槽位）。
- 回滚：`rm -rf /opt/usr/nx-ks/filmlab /opt/usr/nx-ks/flab_ui.sh`。

---

## 7. ★★ 方案 A 已走通（20:45–21:00 更新）：U2 核心目标达成

### 7.1 做法

放弃"自绘全屏窗口"，改走 **mod_gui 菜单路径**：

1. 部署缺失的菜单文件 `gui_filmlab1b.NX500` + `gui_filmlab.NX500` → `/opt/usr/nx-ks/`
2. 起菜单：
   ```sh
   killall -q mod_gui; st app bb lcd on; st app disp lcd
   setsid nice -n +15 /opt/usr/nx-ks/mod_gui /opt/usr/nx-ks/gui_filmlab1b
   ```
3. ⇒ **机身上直接显示 8 条配方按钮**（+ 返回/取消），用户确认可见，`loadavg 1.13` 不卡。

### 7.2 ★★ 途中事故：点按钮 → 相机整屏黑

| 项 | 内容 |
|---|---|
| 现象 | 点配方按钮后 LCD 全黑 |
| 直接证据 | `filmlab.sh dump` ⇒ `slot 9 = R=0 G=0 B=0 HUE=0 SAT=0 SHARP=0 CON=0` |
| 真因链 | 引擎读的是 **`/mnt/mmc/filmlab/recipes.json`**（≠ 自绘 UI 用的 `recipes.txt`）；该 json **从未部署**（入库源 `nx500_filmlab_sd.json` 被清成 **0 字节**）⇒ `jval` 返回**空串** ⇒ `set_r` 写入 **0** ⇒ slot9 全 0 ⇒ 整屏黑 |
| 性质 | ★ **静默失败 → 破坏性写入**：读不到就该报错，绝不该写坏值 |
| 恢复 | `filmlab.sh reset` ⇒ slot9 回 `100/100/100/10/10/10/10`，画面恢复 ✅ |

### 7.3 修复（两处）

1. **新增 `test_server/filmsim/mk_recipes_json.py`**：从 `nx500_recipes.txt` 生成引擎格式 recipes.json
   （对象式 + 严格 4 空格缩进，`awk` 解析所要求）⇒ 部署 `/mnt/mmc/filmlab/recipes.json`（1839 B）。
   `filmlab.sh list` 现能列出全部 8 条 ✅
2. **加固引擎 `filmlab-apply.sh`**：apply 前先取 7 维，**任一为空即拒绝写入并报错**（不再写 0）。已部署（机上 md5 `4cd533d8…`）。

### 7.4 端到端验证 ✅

| 命令 | slot 9 结果 | 说明 |
|---|---|---|
| `apply portra400` | `106/100/93/11/9/9/8` | = Portra 400 ✅ |
| `apply trix400` | `100/100/100/10/0/13/12` | = TriX 400（SAT=0 即黑白）✅ |

### 7.5 结论

**U2 核心目标达成**：机身菜单可见 → 点击 → 配方**真正生效** → 不拖垮相机。

代价：mod_gui 固有"点击即退"，拿不到"滚动不关窗"的对比体验。若将来要那个体验，
需按 §6.3 的 **B 方案**重做一个**轻量非全屏** UI（全屏自绘已被证在单核上不可行）。

---

## 8. ★★★ 最终形态（21:15 更新）：EV+AEL → 点配方 → 立即生效（2 步）

> ⛔ **本节结论已于 2026-10-08 晚被用户实机复测证伪，勿再引用。**
> 见 **§9**（真因 + 引擎改动）。此处保留原文仅作排查过程留档。

### 8.1 用户诉求

原链路 4 步：开菜单 → 选配方 → 进图片向导 → 选 Slot9 确认。要求更短。

### 8.2 ★ 核心发现：di-camera-app 用"进程内 PW 副本"

| 尝试 | 结果 |
|---|---|
| `setusr 20 0x140009`（capdtm 改 PW 类型） | ❌ 画面不刷新（回读值确实变了） |
| `prefman set 0 0xa3d4 l 9`（`APPPREF_EFFECT_PW_TYPE`；**diff 实证** 9=自定义1 / 1=标准） | ❌ 画面不刷新（UI 显示自己的内存状态） |
| **`st app mode p; sleep 1; st app mode a`**（切一次拍摄模式） | ✅ **画面立即生效**（两次独立实测：彩→黑白 / 黑白→彩） |

⇒ 真因：外部改的是**存储**，`di-camera-app` 并不知道；只有它**重建 ISP 管线**时才会重读 prefman。
★ 定位方法：`prefman dump 0` 前后 **diff**（即 `pw-snap.sh` 的核心手法），整个 dump 只有 `0xa3d4` 一处变化。

### 8.3 修复

引擎新增 `trigger_reload()`：读当前 `DIALMODE` → 切到一个**不同**模式 → 切回原模式；在 `apply` 末尾调用。

### 8.4 ★ 验收（用户实测）

```
EV + AEL  →  配方菜单  →  点 Portra 400  →  画面立即生效 ✅
```

**链路 4 步 → 2 步**，且完全不需要碰 Fn 菜单。

### 8.5 同时完成

- **换绑 EV_AEL**：原社区"长录像+黑屏"脚本已备份为 `/opt/usr/nx-ks/EV_AEL.sh.orig`；
  新脚本带"再按一次关闭"的开关行为
- 部署菜单 `gui_filmlab1b.NX500` / `gui_filmlab.NX500`
- 修 `recipes.json`（首次部署）+ 引擎加固（读不到值即拒绝写入，防再次全黑）

### 8.6 遗留

用 telnet 跑 `apply` 时，`st app mode` 重建 UI 会**中断 telnet 会话**，脚本后半段输出丢失
（**功能不受影响**：slot 与模式都正确；从菜单点击时无此问题）。

---

## 9. ⛔ 纠错：§8 的"2 步链路"不成立（2026-10-08 晚 · 用户实机复测）

### 9.1 实测结论

```
真实链路：机身 EV+AEL → 点配方 → 打开画面向导 → 选中「自定义1」 → 画面生效
         （§8 声称的「点配方即生效」不成立 —— 最后一步省不掉）
```

### 9.2 断在哪一环：③ 参数通道

| 通道 | 命令 | 写在哪儿 | 画面会变吗 |
|---|---|---|---|
| ① 存储 | `prefman set 0 0xa3ec…` | 偏好存储（槽位数据） | ❌ |
| ② 选择 | `setusr 20 0x14000N` | "当前选哪个 PW" | ❌（ISP 换风格了，但手里那 7 维参数是旧的） |
| ③ **参数** | PW 引擎运行时的 7 维副本 | 只有 app 的"画面向导"会推 | ✅ |

★★ 静态证据（本轮新挖出，决定性地解释"为什么必须是画面向导"）：

```
di-camera-app → CAttributeHandler::setPWColor / setPWSaturation / setPWSharpness / setPWContrast
              → set_attribute(0x10e / 0x110 / 0x111 / 0x112, &v, 4)
   （符号与调用点：test_server/pwfilter/CAPTURE_FW.md §6）
```

- 这一套是**属性总线**，与 capdtm 的 userdata 总线（`0x14xxxx` 那套）**不是同一编号体系**；
- ★ **`st` 命令面（`st cap capdtm` 只有 setusr/getusr/setvar/getvar/usrlist/varlist）不暴露属性总线**
  ⇒ 任何"写 prefman / 改 setusr / 切拍摄模式"都到不了 ③；
- 而在画面向导里点一次自定义1，app 会把该槽的 7 维参数**重新推给 PW 引擎** ⇒ 画面立刻变。

★ 旁证：用户的操作是"（PW 已停在自定义1 的情况下）再选一次自定义1" ——
  ② 通道的值**根本没变化**，画面却变了 ⇒ 变的一定是 ③。

### 9.3 已落到引擎的改动（本次）

| 改动 | 内容 |
|---|---|
| ⬇ 降级 | `trigger_reload()`（切拍摄模式）默认**关闭**，仅 `FILMLAB_MODE=1` 启用（它会重建 UI、打断 telnet，收益已证伪） |
| ⬆ 新增 | `pw_push_vars()` —— 用 ③ 通道等价物 `st cap capdtm setvar VARIABLE_PW*` 推 7 维参数 |
| ⬆ 新增 | `filmlab.sh pwvar` —— **安全探测** ③ 通道可用写法（只写 ±1 并立即还原；先 `getvar` 回读语义校验，读不到就不写），结果缓存 `/mnt/mmc/filmlab/pwvar.fmt` |
| ⬆ 新增 | `filmlab.sh reload` —— 只重触发、不写配方（配方没变但画面没跟上时用） |
| 🔧 调整 | `pw_force_reload()` 借道值优先级：**另一个自定义槽**（默认）> STANDARD（`FILMLAB_MID=standard` 可退回） |
| 📣 提示 | `apply` 结尾按 ③ 通道状态打印**下一步该做什么**（未探明时明确要求"进画面向导选自定义1"） |

★ 判定顺序（上机一次性做完）：
```
1) sh filmlab.sh pwvar          # 探明 ③；期间盯取景器（±1 变化肉眼看不出，只看是否报 [OK]）
2) sh filmlab.sh apply portra400   # 3 通道全推，看画面是否【立刻】变
3) 若仍不变 → sh filmlab.sh reload 再试；仍不变 ⇒ ③ 不可达，保持"进画面向导"这一步
```
★ 纪律：③ 是**运行时通道**，`pwvar` 单次只碰 1 个变量、4 个候选，输出很小（铁律 88）。

*生成：2026-10-08 · 上机轨 U2 · 相机地址已脱敏*

---

## 10. ★★★ 上机定论（2026-10-08 23:00 · 相机在线复测）

§9 的"三通道"模型**成立并被实测证实**（细节见
[`PW_PARAM_CHANNEL_2026-10-08.md`](PW_PARAM_CHANNEL_2026-10-08.md)）：

| 通道 | 动作 | ISP 的 7 维变量 |
|---|---|---|
| ① 存储 | `prefman set ×7`（+`save 0`+`sync`） | ❌ 纹丝不动（仍 88/111/125 / SAT15） |
| ② 选择 | `setusr 20 0x140009`（含借道） | ❌ 只改 `eIQ_ID_EFFECT_MODE` |
| ③ 参数 | app「画面向导→确认」 | ✅ 唯一有效 |

- ★ **客观判据已找到并落地为命令**：`st cap capdtm varlist` 的 PW 变量 = ISP 手上的 7 维，
  编码已解（`PWCOLOR_x = gain<<16|0x00FF`；`PW{HUE,SAT,SHARP,CON} = (10+offset)<<16|0xD80A`
  形态用 `(b>>4)` 取偏移）。`filmlab.sh check` 一条命令直接给判词。
- ★ `st cap iqr` 不适合做判据：PW 变化只动 `eIQ_ID_EFFECT_MODE` 一个节点。
- ★ 不再有任何"shell 侧一键"的幻想：③ 走属性总线（`0x10e/0x110/0x111/0x112`），
  `st cap` 全家（capt/fenx/live/dp/seq/capmm/face/back/capdtm）都没有入口。
- 新候选（未通）：**A** `st app nx key` 键注入（命令在、键名表未解）；
  **B** 自写用户态助手直调属性总线（需先解 `set_attribute` 传输层）。
- 现实链路仍是 3 步，且**只有第 3 步有效** —— 已同步进 README / RE_PROGRESS。
- ★★ **闭环已验（23:13）**：apply 后 ✗（ISP=88/111/125）；木一在机身点一次「画面向导→自定义1」后
  **✓（ISP=108/100/93 11/9/8/7 = slot9）**。⇒ ③ 唯一性实证，判据双向验证通过。
- 键注入（`st app nx key`）实测**未生效**（S1 不锁 AF、S2 不出片）⇒ 归入独立里程碑。
