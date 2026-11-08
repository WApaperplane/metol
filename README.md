# Metol（旧称 NX-WA）

Samsung NX500 / NX1（Tizen / DRIMe5）增强固件 mod，基于社区上游
[`ottokiksmaler/nx500_nx1_modding`](https://github.com/ottokiksmaler/nx500_nx1_modding) 改造与扩展。

**仓库** [WApaperplane/metol](https://github.com/WApaperplane/metol)（fork；默认分支 `nxwa`）·
**许可** AGPL-3.0（血缘见 [ATTRIBUTION.md](ATTRIBUTION.md)）·
**下载** [Releases](https://github.com/WApaperplane/metol/releases)

> English version: [README_EN.md](README_EN.md)

**最新 v2.88.0-nxwa.15**（2026-11-08）— LUT 秒切：换滤镜不再需要半按快门，
面板上点一张取景器立刻变；`lut.sh apply/off` 自己完成 Load 并等 DMA 完成中断。

## 安装

1. 把 `info.tg`、`nx_cs.adj`、`install.sh`、`scripts/` 放到 **SD 卡根目录**（或把 `NX-WA-<version>.zip` 解压到根目录）。
2. 插卡 → 自动安装，屏上显示「安装完成」。
3. **手动开一次蓝牙** —— mod 的开机钩子靠它初始化。

- 固件：NX500 **1.12** / NX1 **1.41**，其它版本拒绝安装。
- 再插一次卡 = **增量同步**（只覆盖、不删除；永不自动卸载）；卸载走相机菜单里的 `uninstall.sh`。
- 安装 / 同步 / WiFi push / 回滚：[SYNC.md](SYNC.md)（中英双语）。

## 快捷键

| 按键 | 打开 | 说明 |
| --- | --- | --- |
| **EV + AEL** | **滤镜条**（NXUI，720×208） | 79 条配方横向滚动 + 滚动条拖动/点击定位，点选**即时预览**（约 1.3 s，画布固定「自定义1」）；`保存并关闭` 落盘并把档位还回打开时那一档；再按一次或**半按快门**关闭。**NX500 专属**，NX1 自动回退社区原版 |
| **EV + WiFi** | **LUT 滤镜面板** | 打开 NXUI 的 LUT 模式（`nxui.sh lut`）；**关闭面板不还原** —— 还原走面板内的「还原原厂」。NXUI 未启用时只弹一句提示 |
| **双击 EV** | 主菜单（NXUI，720×336） | 分页界面，替代旧的 mod_gui 主菜单 |
| **半按快门** | 关闭当前面板 | LUT 面板关闭且**保留当前表**，同时让 p7 重载 —— 让开画面拍照，LUT 继续生效 |

> **EV + WiFi 是组合键**：按住 EV 不放，再按 WiFi。单击 WiFi 仍是相机原生行为（开/关 WiFi），两者不冲突。

相机菜单内还有四项：`IP: x.x.x.x [Telnet关]`（点击开关 23/21）、`远程控制`（开关 Web 相册）、`LUT 滤镜`（等同 EV+WiFi 的 UI 部分）、`TC 曲线`（实用功能 → 原厂 / Log / Flat / 高对比）。

## 功能

| 能力 | 一句话 |
| --- | --- |
| 胶片配方 | 79 条（负片 / 反转 / 黑白 / 电影 / 风格 / 相机内置风格），PW 七维一次直进 ISP |
| 3D LUT | `.cube` 机身一条命令转成原生表；**改四张登记表 + 写 19,712 B 空闲槽 + 半按快门**即换表；**两张表可以各带一个强度混着用**；滤镜库可在机身内增删、排序、收藏；**录像随 apply 联动，直接按录像键就带同一条表** |
| TC 曲线 | 录像 tone 曲线四条预设（原厂 / Log / Flat / 高对比）：写 19 节点 + 置 dirty，**<50 ms 自行生效、不用按键**，重启回原厂 |
| NXUI 界面 | Nuklear（MIT）+ 相机自带 X11/Xft 重写，**不链接 EFL**、不抓取/重绘取景帧 |
| Web 相册 | 折叠目录 + `dirlist` 实时目录（新拍照片立即可见）+ 缩略图预热 + WiFi 在线 push |
| 原 NX-KS 模块 | 视频码率、HDR、批量录制、变焦缩放、分辨率修改、拍摄参数 API 等 |

## FilmLab 胶片配方

| 族 | 例子（共 79 条：彩色 71 + 黑白 8） |
| --- | --- |
| 彩色负片 | Portra 400/800、Gold 200、Ektar 100、Superia 400、ProImage 100、Vista 200 … |
| 反转片 | Velvia 50/100、Provia 100F/400X、Ektachrome E100、Kodachrome 25/200 … |
| 黑白 | TriX 400、HP5 Plus、Delta 3200、T-MAX 100/400、Acros 100、XP2 Super … |
| 电影卷 | CineStill 800T/50D、Vision3 250D/500T、Double-X 5222、Eterna 500T |
| 风格 | 青橙 / 暖旧 / 冷峻 / 褪色 / 高调 / 低调 / 棕褐 / 漂白 / 蓝调时刻 / X-Pro 交叉 |
| 相机内置风格 | 理光 GR（正片 / 负片 / 怀旧 / 漂白 / 交叉冲洗）、宾得 Custom Image（鮮やか / 反转片 / 銀残し / ほのか / 里び / Gold） |

- **改配方不用改代码**：编辑 `/mnt/mmc/filmlab/recipes.json` → 拷回 SD → 重开菜单（自动重建）。仓库权威源是 `scripts/filmlab/recipes.json`，上位机一条龙 `test_server/filmlab/flab.py add|edit|rm|lint|deploy`。
- 配方 = Picture Wizard 七维向量（R/G/B 增益 + HUE/SAT/SHARP/CONTRAST），固定落在「自定义1」槽，位置恒定。
- **全七维直推需要 A2 固件**（`patch-a2/` 随包提供，含刷入教程与 md5）。官方固件下 R/G/B/HUE 需机身「画面向导 → 自定义1」确认一次 —— 这是 p7 归一化器域界（`0x100–0x12e`）的结构性限制，不是脚本 bug。
- 诚实边界：WB 不在配方内（请用机身白平衡）；配方是全局色彩向量，做不出高光滚降 / 分区曝光；NX1 上不启用（prefman 偏移只在 NX500 1.12 实证）。
- 判据只认一条：`sh /opt/usr/nx-ks/filmlab.sh check` 直接读 ISP 手上那七维跟配方比对（只读、零风险）。**"值变了" ≠ "被消费"**。
- 另有 `scripts/nx-rc/MOBILE_MOBILE.sh`（双击 WiFi = 零 UI 轮换下一条配方）——不进安装链，需要时手动放到 `/opt/usr/nx-ks/`。

## 3D LUT

| 项 | 现状 |
| --- | --- |
| 表格式 | `4913×4B {Cr,Cb,Y,pad}`，索引 `((Y*17+Cb)*17+Cr)*4`，槽 19,712 B，步长 `0x4D00`（10-19 实机闭合，旧的 RGB 命名已作废） |
| 换表 | 写 19,712 B 进工作槽（A18 `0x81119F00`）+ 改**四张**登记表全部指向它 + **半按一次快门** |
| 登记表 | `View4` 四项（色彩空间×屏幕色彩）+ `Still6` 六项 + `BV12` 十二项 —— **一项都不能漏**，漏了就是"取景有、照片没有" |
| 导入 | `.cube → 19,712 B 槽表`：机身 `cube2lut.arm` 一条命令，或 PC 端 `test_server/isp/nx3dlut.py` |
| 生成依据 | 按**实测相机输入域**：响应斜率 `log2(码值)/EV = 0.809`，不是 sRGB 的 0.45（差 1.8 倍）。按 sRGB 假设做的表会在暗部被二次压缩；68 张随包表里 34 张已按真实响应重生成（25 张 G'MIC + 9 张配方），其余 34 张无生成器可追溯、保持原样 |
| 取景 / 成片 | 取景只认 `View4`；成片有**两条互斥分支**（屏幕色彩开→`BV12`，关→`Still6`），两条都要指过去 |
| 视频 | `apply` 之后直接按录像键，**首帧就带表**（p7 的 23 项档位指针表被整体指到 A18），`off` 自动停监视。长录与更多帧率尚未覆盖 |
| 边界 | 全是内存操作，**断电即回原状**（「开机即生效」仍需改固件镜像）；sRGB 颜色可信，AdobeRGB 只保证生效 |
| 禁区 | ⛔ 自己写 `+0x00C` 再脉冲配置寄存器 ⇒ ISP 读到原厂时序外地址 ⇒ **严重偏色花屏**。唯一安全重载 = **半按快门** |

### 滤镜库与混合

| 能力 | 用法 |
| --- | --- |
| 库管理 | `lut.sh list [--fav]` / `fav` / `move up\|down\|top` / `del` / `index` / `stock` |
| 交叉混合 | `lut.sh mix <A> <B> <0-100>` |
| 单表强度 | `lut.sh strength <名> <0-100>`（0 端 = 原厂 A17，先跑一次 `lut.sh stock` 导出来） |
| 双表各自强度 | `lut.sh blend <A> <r 0-100> <B> <s 0-100>` —— `r` 是 A/B 比例，`s` 是总强度 |
| 录像 LUT | 不用单独开：`apply` 成功自动启动、`off` 自动停。诊断用 `lut.sh video on\|off\|status`（`on` 带秒数可限时） |

顺序与收藏落在 SD 卡 `looks/../lut/state/order`，一行一条、`*` 前缀表示收藏。
下架是**移到 `looks/_trash/`**，不是删除（exFAT 上删同名文件会释放簇链，见现场纪律）。

面板里就是「两个强度各自一根」：左右键切 A/B 焦点，滑杆和右上拨盘调当前那个，
底部状态行同时显示两个强度与换算后的比例/总强度。

双表强度的语义是**归一加权**：`r = B/(A+B)` 定比例，`s = min(A+B, 100)` 定总强度，
最终 `T = 原厂 + s·(mix(A,B,r) − 原厂)`。所以两个都推满时得到两张表的折中，不会溢出成死黑死白。
实测对比（偏移叠加会溢出 14%、图层覆盖会随 A/B 顺序变 7–30 级）见
[`docs/current/DUAL_STRENGTH_2026-11-02.md`](docs/current/DUAL_STRENGTH_2026-11-02.md)。

### LUT 面板按键（NX500 实体键，全部实测）

| 键 | 浏览态 | 编辑态 | 混合态 |
| --- | --- | --- | --- |
| 上 / 下 · EV 拨盘 | 翻页 | — | 翻页（换条目） |
| 左 / 右 | 翻页 | — | 选 A / B 焦点 |
| 中央 OK | 应用并关闭 | 完成 | 应用混合 |
| 播放 ▶ | 进编辑态 | — | — |
| 长按列表项 | 进编辑态 | — | — |
| Fn | 进混合态 | — | 退出混合 |
| 右上拨盘 | 翻页 | — | 调当前焦点强度（5%/格） |
| BACK · MENU | 关闭 | 关闭 | 关闭 |

> 三态里**唯一会改库内容**的是编辑态（删除 / 排序）。混合态的 A/B 用按钮行设
> （`设为A` / `设为B` / `应用混合` / `退出`），退出**不会**自动应用。
> 键位可以覆盖：`$NXUI_STATE_DIR/keys.conf` 一行 `<keysym> <action>`，`none` 表示解绑。

> 面板的列表是「选中项居中」的 5 项窗口，所以**不做横滑切项**：滑动与整排平移叠加
> 会把目标甩掉，长按也按不准。翻页只走滚条、上下键、两只拨盘 —— 滚条一次可跨全库，
> 轨道上还画着 A（绿）/ B（橙）两个刻度。

```sh
sh /opt/usr/nx-ks/lut.sh list | begin | apply <名> | off | status   # 滤镜库 /mnt/mmc/looks/
sh /opt/usr/nx-ks/lut.sh video on|off|status                       # 录像监视，通常不用手动调
```

细节：[`docs/current/LUT_RETARGET_LIVE_2026-10-18.md`](docs/current/LUT_RETARGET_LIVE_2026-10-18.md)　面板设计：[`docs/current/LUT_UI_2026-10-18.md`](docs/current/LUT_UI_2026-10-18.md)

## TC 曲线（录像 tone 曲线）

p7 录像链路里有一张 **19 节点 tone 曲线表**，作用在 3DLUT 之前。它不是 `MOVIE_GAMMA_CONTROL`
（那个接口在 NX500 1.12 上没有消费者），是数据表本身：写 19 个 Y → 置 dirty → ISP **<50 ms 内自行消费**，
不需要按键。

| 项 | 现状 |
| --- | --- |
| 表 | 19 节点，X 固定 `0–16383`，Y `0–1023`，首 0 尾 1023、严格递增 |
| 地址链 | `Param0 = read32(0x817dccbc)` → `Gamma = read32(Param0+0x170)` → `Y[i] = Gamma+0xe8c+4i`；**每次重新解析 + 签名校验**，堆地址随 boot 变，不能硬编码 |
| 入口 | 菜单 `实用功能 → TC 曲线`（原厂 / Log / Flat / 高对比），或 `tc.sh set log\|flat\|hc` |
| 生效 | 进入 HEVC 码流：同段 A/B 录像全画面 Y mean **63.26 → 98.83**，像素映射 4→17 / 52→102 / 180→186 |
| 回退 | `tc.sh off` 回原厂；重启也自动回原厂（改的是运行态内存，不写固件） |

```sh
sh /opt/usr/nx-ks/tc.sh status             # 是否原厂、Y[9]、描述符
sh /opt/usr/nx-ks/tc.sh list               # /mnt/mmc/tc/*.tcy
sh /opt/usr/nx-ks/tc.sh set log|flat|hc    # 或指向任意 .tcy
sh /opt/usr/nx-ks/tc.sh off
```

诚实边界：

- **曲线可编程 ≠ 动态范围增加**。容器仍是 8bit 4:2:0，没有 10bit 地基；Y mean 抬升是曲线形状，不是曝光漂移，也不是 DR 净增益（严格门槛后区间含零）。
- 锚点是「中灰锚定」（相机 128 ↔ sRGB 128）；换白点锚定整体差约 35 码，要 18% 灰卡才能定。
- **TC 会移动 3DLUT 的输入域**，两者同时改需重新标定。
- 只在空闲预览模式下写入（目录锁 + 录像检测 + 逐项回读，失败自动写回原厂）；**录像中切换的稳定性、照片路径是否受影响，都未验证**。

细节：[`docs/current/TC_CURVE_ONDEVICE_2026-11-08.md`](docs/current/TC_CURVE_ONDEVICE_2026-11-08.md)　还原工作流：[`docs/current/TC_RESTORATION_WORKFLOW_2026-11-08.md`](docs/current/TC_RESTORATION_WORKFLOW_2026-11-08.md)

## 目录结构

| 路径 | 说明 |
| --- | --- |
| `install.sh` `info.tg` `nx_cs.adj` | SD 卡根触发三件套（装机 / 增量同步） |
| `scripts/` | 全部模块母本 → 同步到相机 `/opt/usr/nx-ks/` |
| `scripts/filmlab.sh` · `scripts/filmlab/recipes.json` | FilmLab 引擎 / 权威配方库（79 条） |
| `scripts/EV_AEL.sh` · `scripts/EV_MOBILE.sh` | 两个组合键入口（`EV+AEL` 滤镜条 / `EV+WiFi` LUT 面板） |
| `scripts/lut.sh` · `scripts/lut/` | 3D LUT 入口 + 工具集（`cube2lut` / `nx_slotwrite` / `nx_regtabwrite` / `nx_regtabdump` / `nx_lutload` / `nx_lutptr` / `lutmix`） |
| `scripts/lut_video.sh` | 录像 LUT 监视器（随 `apply`/`off` 联动，锁与状态都在 `/tmp`） |
| `scripts/tc.sh` · `scripts/tc/*.tcy` | TC 曲线写入与曲线库（原厂 / Log / Flat / 高对比） |
| `scripts/gui_tc.NX500` | 原生菜单入口：实用功能 → TC 曲线 |
| `tools/tcgen/` · `tools/lutgen/` | PC 端工具：曲线生成 / 只读验链 / LUT 生成与体检 |
| `scripts/nx-rc/` | Web 遥控：`web_root/` `thumb/` `capdtm/` `push/` |
| `test_server/` | PC 端开发验证环境（模拟 API、工具链、门控） |
| `uninstall_pkg/` | 相机菜单卸载入口 |

## 文档

- [`docs/README.md`](docs/README.md) — **文档总索引**（`current` 现行 / `archive` 历史 / `evidence` 证据）
- [`docs/current/HANDOVER_2026-10-16.md`](docs/current/HANDOVER_2026-10-16.md) — 总入口：约定、死路、门控、执行序
- [`docs/current/ONDEVICE_SOP_2026-10-16.md`](docs/current/ONDEVICE_SOP_2026-10-16.md) — 上机日 SOP（就位 / 判据 / 回退）
- [`docs/current/NXUI_NUKLEAR_2026-10-17.md`](docs/current/NXUI_NUKLEAR_2026-10-17.md) — NXUI 安装与验证
- [`docs/current/TC_CURVE_ONDEVICE_2026-11-08.md`](docs/current/TC_CURVE_ONDEVICE_2026-11-08.md) — TC 曲线：地址链、写入协议、实机 A/B
- [`docs/current/VIDEO_LUT_FIRSTFRAME_2026-11-07.md`](docs/current/VIDEO_LUT_FIRSTFRAME_2026-11-07.md) — 录像首帧带表：p7 档位指针表
- [`docs/current/LUT_INPUT_CALIBRATION_2026-11-07.md`](docs/current/LUT_INPUT_CALIBRATION_2026-11-07.md) — 输入曲线实测协议与结果
- [`docs/current/RE_PROGRESS_2026-10-08.md`](docs/current/RE_PROGRESS_2026-10-08.md) — 逆向进度总览（含死路清单）

> 历史文档里的旧结论（如"View/Still 不可分离""用户态不能写 LUT"）已被推翻，纠错见
> [`ERROR_CORRECTIONS_2026-10-07.md`](docs/current/ERROR_CORRECTIONS_2026-10-07.md)。

## 界限

写清楚比写得好看重要。下表每一条都对应实机或静态验证，没有"应该可以"。

| 维度 | ✅ 能 | ❌ 不能 / 未验 |
|---|---|---|
| 平台 | NX500 固件 **1.12**（全部功能实机验证） | NX1 1.41 可装，但 LUT / FilmLab 未在 NX1 上验证；其它固件版本拒绝安装 |
| 色彩 | **sRGB** 输出下取景与 JPEG 成片颜色可信（68 张随包表的基准，其中 34 张按实测输入域生成） | **AdobeRGB 会生效但颜色未标定**；相机智能滤镜（枚举 14–18）走另一条动态 24 档路径，不覆盖 |
| 载体 | **JPEG 成片 + 取景器 + 录像（首帧即带表）** | **RAW（`.SRW`）不承诺被 LUT 烘焙**；地基只有 8bit 4:2:0（10bit 不可达，内置 gamma 接口无消费者）；录像长录与多帧率未覆盖 |
| 录像曲线 | **TC 曲线四条预设，写表后 <50 ms 生效并进入 HEVC** | 只重分配 256 级码值，不产生动态范围；绝对锚点待灰卡定；录像中切换、与 3DLUT 叠加、照片路径影响均未验证 |
| 生效 | LUT 写内存后**半按一次**装载；TC 曲线写表后 **<50 ms 自行生效**（不用按键） | **开机即生效做不到** —— 断电/重启回原厂，要持久化得改固件镜像 |
| 触发 | **半按快门**是唯一可靠的重载点 | 软件触发 p7 重读表的入口尚未找到（`st cap iq af afsta/afsto` 无效） |
| 形态 | 不刷机、不改分区，可双向回滚 | 不改固件分区 ⇒ 重启即回原厂（LUT 写入是内存操作） |

> 它**不是**完整色彩管理（不做输入/输出 profile 转换），**不是**所见即所得承诺（取景与成片处理链不同），
> **不是**破解（不解除区域锁、不改录制时限）。改的只是 ISP 里的两张表：末端 3D 查找表 + 录像 tone 曲线。

## 硬限制（p7 / 固件层面，不是脚本 bug）

- **全七维 PW 一键需 A2 固件**；官方固件下归一化器域外的值会被拒收。
- **p7 无 UI**（Font/DrawText/Dialog/Widget 全 0 命中）⇒ 界面只能在 Linux 侧改。
- **三键以上组合不可得**（内核先消费按键）⇒ 能用的只有「按住 EV + 单键」这一类两键组合；长按由 NXUI 按 press/release 时长自己判定，不是硬件事件。
- **TC 曲线只改形状，不改位深**：8bit 4:2:0 里重映射 256 级码值不产生新的动态范围；`MOVIE_GAMMA_CONTROL` / `IQ[180]` 那条接口没有消费者，10bit 编码在固件里不存在。
- 出厂 LUT 表**全是风格表**，不能拿"写 identity 得中性"当判据。

> 胶片仿真引擎与 `.cube` 素材另见 [nx500-filmsim](https://github.com/WApaperplane/nx500-filmsim)（public）。
