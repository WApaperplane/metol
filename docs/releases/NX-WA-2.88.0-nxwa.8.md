# NX-WA 2.88.0-nxwa.8

发布日期：2026-10-20
上一版：2.88.0-nxwa.7

## 一句话

**把 LUT 后端退回 10-18 那套能用的单槽 + 半按，并补上"OLED 开启时取景器读 View4[1]"这个漏洞；同时随包分发 45 张按原厂格式重做的滤镜表。**

v7 的"双槽交替 + 官方设置事件重载"被证明不可靠：它能改指针、能让 `load_addr` 回读正确，
但 **ISP 不会因此重读槽内容**。于是出现"日志全绿、画面没变"。本版撤回这条路线。

## 1. 回退：为什么退回单槽

| | v6（本版） | v7（撤回） |
|---|---|---|
| 写槽 | 固定 A18 | A18 / A19 交替 |
| 登记表 | `View4[3]` + `Still6` | 额外改 `View4[1]` |
| 触发重载 | **用户半按快门**（P7 正常事件） | OLED 双切换 + 设置事件 |

实测结论：OLED 双切换只能让寄存器与回读值变化，**不能证明 ISP 重读了表**。同一张彩色表在
"复位到原厂后第一次"正常、第二次起变黑白单色，就是这条造成的。半按快门是历史上唯一
每次都能生效的触发点。

## 2. 补漏：`View4[1]` 也必须写

sRGB 下 **OLED 色彩开启时取景器读 `View4[1]`（原厂 A13），关闭时读 `View4[3]`（原厂 A17）**。
v6 只写 `[3]`，所以在 OLED 开启的机器上表现为"表写了、画面不动"。

本版新增 `nx_regtabwrite1.arm`（支持 `patch1`），`apply` 写 `[1]` 与 `[3]` 都指向 A18，
`off` 分别恢复 A13 / A17。登记表在 RAM，**重启后必然回原厂**，所以必须每次 apply 都补写。

## 3. 45 张滤镜表随包分发

新增 `looks/`（解压到 SD 根，即 `/mnt/mmc/looks/`），全部为 19,712 B 标准槽表
`{R,G,B,0} × 4913 + 60B`，索引 `((B·17+G)·17+R)·4`，中性点 128。

| 组 | 数量 | 内容 |
|---|---:|---|
| 冷色 | 7 | `cool_arctic` `cool_blue` `cool_cyan` `cool_mint` `cool_night` `cool_slate` `cool_steel` |
| 暖色 | 7 | `warm_amber` `warm_candle` `warm_gold` `warm_honey` `warm_rust` `warm_sepia` `warm_sunset` |
| 胶片 | 11 | `film_astia` `film_cinestill` `film_ektar` `film_expired` `film_faded` `film_kodachrome` `film_negative` `film_portra` `film_provia` `film_superia` `film_velvia` |
| 黑白 | 4 | `mono_acros` `mono_hard` `mono_infra` `mono_soft` |
| 风格 | 6 | `style_bleach` `style_dream` `style_matte` `style_noir` `style_teal_orange` `style_vivid` |
| 基准 | 10 | `samsung_a00/01/02`（原厂槽 dump）`identity17` `ektar100` `velvia50` `kodak_k64_legacy` `portra160` `portra400uc` `slide_precisa100` |

生成方式为数学合成（通道增益 → 对比/gamma → 饱和度 → 分离色调 → 抬黑/压白），
**中性点全部落在 128±3**；`film_*` 灰轴偏差 ≤5，黑白严格为 0。冷/暖两组的偏色是设计意图。

## 4. 表格式定案：RGB，不是 CrCbY

用原厂 A18/A13 备份做轴向探针（其余轴固定 8）：

| 摆动 | 原厂输出 | 含义 |
|---|---|---|
| `[k,8,8]` | `(3,127,128)` → `(255,132,121)` | 只有 byte0 走全幅 |
| `[8,k,8]` | `(128,0,128)` → `(128,255,128)` | 只有 byte1 走全幅 |
| `[8,8,k]` | `(128,128,0)` → `(128,128,255)` | 只有 byte2 走全幅 |

**判据**：若第一轴是 Cr，`Cr=0` 时绿色分量须按 BT.601 反向补偿成 `128+0.714×128=219`；
实测 **127**，纹丝不动 ⇒ 第一轴是 R 不是 Cr。**表格式 = `{R,G,B,0}`，第 i 轴直接驱动第 i 字节。**

因此本版 `cube2lut.arm` 回到 RGB 输出（`582b12f0…`，8,880 B），撤回中途引入的 CrCbY 转换
（`2d94e76f…`）——后者会把彩色 LUT 压成偏色单色图。

## 5. 保留

v7 的面板改动全部保留：横向滚动条、一键「还原原厂」、位置记忆（存 key 不存序号）。
本次只动 LUT 后端与滤镜库。

## 6. 已知限制

- **每次 apply 后需半按一次快门**才会装载。面板会提示 `NEXT half-press once`。
- 重启后登记表回原厂，需要重新选一次（`apply` 会重新写 `[1]`/`[3]`）。
- 软件触发 P7 重读表的入口尚未找到：`st cap iq af afsta/afsto` 无效。这是下一版的主攻方向。

## 校验

解压到 SD 卡根即可，`install.sh` 会把 `scripts/` 同步到 `/opt/usr/nx-ks/`，`looks/` 保持原位。
