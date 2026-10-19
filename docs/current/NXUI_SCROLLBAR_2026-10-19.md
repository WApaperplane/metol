# NXUI 横向滚动条（2026-10-19）

> **一句话**：两个模式都加了一条整宽的横向滚动条 —— 按住任意位置即跳过去，
> 拖动实时跟手；为此面板高度从 192 加到 208，并且**不能用 Nuklear 的 `nk_slider_float`**。

## 1. 为什么不用 `nk_slider_float`

Nuklear 的滑块只在「**当前**鼠标位置仍落在滑块矩形内」时才继续更新：

```c
/* nuklear.h, nk_slider_behavior → nk_input_has_mouse_click_down_in_rect */
left_mouse_click_in_cursor = nk_input_has_mouse_click_down_in_rect(in, NK_BUTTON_LEFT, *visual_cursor, nk_true);
/* 里面最后一步是 nk_input_is_mouse_hovering_rect(i, r) —— 用鼠标当前位置，不是按下位置 */
```

本次轨道 696px、68 个配方时每步 10px 尚可，但界面只露出 5 项、`max=count-1`：
8 项的 LUT 列表每步 99px，而滑块只有 26px。手指一移出滑块，hover 判定立刻失败，
拖动在第二帧就断 —— 表现为**按住能高亮、一拖就停**，触摸屏上等于不可用。

实测（修复前）：`test_input drag 20 110 480 110 10` 发完后 `/tmp/nxui.log` 里
一条 `BAR` 都没有，引擎一次 `apply` 都没收到；`verify_display` 在
`run_lut_interaction` 红。

## 2. 实现

`scrollbar_row(ctx, sel, n)`：自己取矩形、自己算比例、自己画，返回目标序号或 -1。

| 项 | 值 |
|---|---|
| 行高 | 16px（触摸判定按整行，轨道视觉只有 8px 居中） |
| 轨道 | `x=12, w=696`，圆角 4，色 `45/53/59` |
| 已选段 | 从轨道左端到滑块中心，色 `88/111/79` |
| 滑块 | `30×12`，色 `203/233/153`（比滑块默认值大 4 倍，手指才按得住） |
| 映射 | `ratio = (mouse.x − track.x − 15) / (696 − 30)`，`want = round(ratio × (n−1))` |
| 按下 | 行内任意位置 ⇒ 立即跳到该比例（tap-to-jump），不需要先拖 |
| 抬手 | **单独补一帧计算**（见 §3） |

两个模式共用同一行控件，只是 y 不同。

## 3. ★ 抬手那一帧必须补算

面板渲染是 10 Hz（`next_frame` 节流），触摸板 20ms 一次的 motion 会被合并：
松手时鼠标早就在终点，但最后一帧处理到的可能是半路的位置。

修复前实测：拖到 x=480，最后只落到第 3 项（log 里最后一条 `BAR sel=0 want=3 x=296`）。
判据是「松手位置才是终点」，所以：

```c
was = bar_drag;
if (press && hover) bar_drag = 1;
if (bar_drag || (was && !down)) { …按 mouse.pos 重算… }
if (!down) bar_drag = 0;
```

`ButtonRelease` 到达前事件循环已经先喂过 `nk_input_motion(x2,y2)`，所以这一帧
`mouse.pos` 就是终点。修复后同一拖拽落到 `look05`（`(480−27)/666×7 = 4.76 → 5`），
与几何预期一致。

## 4. 布局代价：192 → 208

新增 16px 行 + 5px 行距。192 高时按钮行会被 Nuklear 静默丢弃
（10-19 早先已经在 84px 滤镜条上踩过同一个坑），所以面板加高到 208：

| 层 | y（PW） | y（LUT） |
|---|---|---|
| 标题行 24 | 8..32 | 8..32 |
| 滤镜条 60 | 37..97 | 37..97 |
| PW 分量行 16 | 102..118 | — |
| **滚动条 16** | **123..139** | **102..118** |
| 按钮行 26 | 144..170 | 123..149 |
| 底部状态 23 | 175..198 | 154..177 |

`resize_panel()`、`height = 208`、`Display must be at least 720x208` 三处同步；
`verify_display` 的快照断言也改成 `720 208`。

**按钮行整体下移 21px**，`test_interaction` 里 PW 的「保存并关闭」和「还原」
坐标、LUT 的「还原原厂」坐标都已按新行重钉（x 不变，y +21）。

## 5. 测试

| 用例 | 断言 |
|---|---|
| `test_input drag`（新） | `drag x1 y1 x2 y2 [steps]`：press → 10 次带 `Button1Mask` 的 MotionNotify → release。**只有 press/release 的 click 测不出 motion 链** |
| `run_lut_interaction` | 拖到 480px ⇒ 最后一条调用**必须正好是** `apply look05`（不是"变了就行"） |
| `run_lut_interaction` | 点轨道 680px ⇒ 必须 `apply look07`（tap-to-jump） |
| `verify_display` | 17 项：host/arm × filmlab/lut/menu/idle/interaction/lut-interaction/service-interaction/performance + focus-handoff，**全 PASS** |

阴性对照：把 `scrollbar_row()` 换回 `nk_slider_float`，`run_lut_interaction` 立刻红
（引擎收不到 apply，日志里没有 `BAR`）—— 这条测试确实钉住了拖动链路。

`/tmp/nxui.log` 新增诊断行（首帧一次 + 每次换项一次）：

```
BAR rect=12,102 696x16 st=2
BAR sel=0 want=3 x=342
BAR sel=3 want=5 x=480
```

## 6. 上机（2026-10-19 19:45，真机 192.168.0.106）

| 项 | 值 |
|---|---|
| `/opt/usr/nx-ks/nxui/nxui.arm` | `cedc8305dd5fa506ab3c978dd802d9b7` 460,628 B |
| `/mnt/mmc/scripts/nxui/nxui.arm`（SD 母本） | 同上 —— **必须同步**，否则引导器下次触发会打回旧版 |
| 备份 | `/opt/usr/nx-ks/nxui/backup-scrollbar-20261019/nxui.arm.prev` = `8a7001d4…` |
| 安装脚本 | `test_server/nxui/install_scrollbar.sh`（setsid 后台 + md5 三方互证） |

`selftest.sh` 机端输出：

```
READY backend=nuklear-xft live=1 recipes=68 panel=720x208 tier=1 sel=0
BAR rect=12,123 696x16 st=2          ← FILMLAB
FIRST_FRAME process_ms=526  (font_ms=314)
EXIT renders=2 elapsed_ms=1513

READY backend=nuklear-xft live=1 recipes=43 panel=720x208 tier=1 sel=0
BAR rect=12,102 696x16 st=2          ← LUT
FIRST_FRAME process_ms=449  (font_ms=293)
EXIT renders=2 elapsed_ms=1507
```

两模式 `rc=0`，行位置与宿主布局表逐像素一致。首帧与加滚动条前同量级
（526/449ms，字体仍占六成）—— 新增的一行绘制成本在噪声内。

## 7. 待现场目视

数据面证明不了手感，下面三条要手指确认：

1. LUT 面板按住条子从最左拖到最右 → 卡片跟着滚、松手停在第 43 个 look
2. 点条子中段 → 直接跳过去（不用先拖）
3. PW 面板同样两条；拖完半按 → 落的是松手时高亮的那张

若 **拖动不跟手但点击能跳**，说明相机触摸板不发按住状态的 motion —— 这是
降级而不是故障（§3 的抬手补算保证终点正确）。此时要补的是 `Button1MotionMask`
之外的触摸事件源（XInput2 或 `evdev` 直读）。
