# Metol（旧称 NX-WA）

Samsung NX500 / NX1（Tizen / DRIMe5）增强固件 mod，基于社区上游
[`ottokiksmaler/nx500_nx1_modding`](https://github.com/ottokiksmaler/nx500_nx1_modding) 改造与扩展。

**仓库** [WApaperplane/metol](https://github.com/WApaperplane/metol)（fork；默认分支 `nxwa`）·
**许可** AGPL-3.0（血缘见 [ATTRIBUTION.md](ATTRIBUTION.md)）·
**下载** [Releases](https://github.com/WApaperplane/metol/releases)

> English version: [README_EN.md](README_EN.md)

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
| **EV + AEL** | **滤镜条**（NXUI，720×208） | 68 条配方横向滚动 + 滚动条拖动/点击定位，点选**即时预览**（约 1.3 s，画布固定「自定义1」）；`保存并关闭` 落盘并把档位还回打开时那一档；再按一次或**半按快门**关闭。**NX500 专属**，NX1 自动回退社区原版 |
| **EV + WiFi** | **LUT 滤镜面板** | 打开 NXUI 的 LUT 模式（`nxui.sh lut`）；**关闭面板不还原** —— 还原走面板内的「还原原厂」。NXUI 未启用时只弹一句提示 |
| **双击 EV** | 主菜单（NXUI，720×336） | 分页界面，替代旧的 mod_gui 主菜单 |
| **半按快门** | 关闭当前面板 | LUT 面板关闭且**保留当前表**，同时让 p7 重载 —— 让开画面拍照，LUT 继续生效 |

> **EV + WiFi 是组合键**：按住 EV 不放，再按 WiFi。单击 WiFi 仍是相机原生行为（开/关 WiFi），两者不冲突。

相机菜单内还有三项：`IP: x.x.x.x [Telnet关]`（点击开关 23/21）、`远程控制`（开关 Web 相册）、`LUT 滤镜`（等同 EV+WiFi 的 UI 部分）。

## 功能

| 能力 | 一句话 |
| --- | --- |
| 胶片配方 | 68 条（负片 / 反转 / 黑白 / 电影 / 风格），PW 七维一次直进 ISP |
| 3D LUT | `.cube` 机身一条命令转成原生表；**改 4 字节登记表 + 写 19,712 B 空闲槽 + 半按快门**即换表；取景与成片是两条独立链路 |
| NXUI 界面 | Nuklear（MIT）+ 相机自带 X11/Xft 重写，**不链接 EFL**、不抓取/重绘取景帧 |
| Web 相册 | 折叠目录 + `dirlist` 实时目录（新拍照片立即可见）+ 缩略图预热 + WiFi 在线 push |
| 原 NX-KS 模块 | 视频码率、HDR、批量录制、变焦缩放、分辨率修改、拍摄参数 API 等 |

## FilmLab 胶片配方

| 族 | 例子（共 68 条：彩色 60 + 黑白 8） |
| --- | --- |
| 彩色负片 | Portra 400/800、Gold 200、Ektar 100、Superia 400、ProImage 100、Vista 200 … |
| 反转片 | Velvia 50/100、Provia 100F/400X、Ektachrome E100、Kodachrome 25/200 … |
| 黑白 | TriX 400、HP5 Plus、Delta 3200、T-MAX 100/400、Acros 100、XP2 Super … |
| 电影卷 | CineStill 800T/50D、Vision3 250D/500T、Double-X 5222、Eterna 500T |
| 风格 | 青橙 / 暖旧 / 冷峻 / 褪色 / 高调 / 低调 / 棕褐 / 漂白 / 蓝调时刻 / X-Pro 交叉 |

- **改配方不用改代码**：编辑 `/mnt/mmc/filmlab/recipes.json` → 拷回 SD → 重开菜单（自动重建）。仓库权威源是 `scripts/filmlab/recipes.json`，上位机一条龙 `test_server/filmlab/flab.py add|edit|rm|lint|deploy`。
- 配方 = Picture Wizard 七维向量（R/G/B 增益 + HUE/SAT/SHARP/CONTRAST），固定落在「自定义1」槽，位置恒定。
- **全七维直推需要 A2 固件**（`patch-a2/` 随包提供，含刷入教程与 md5）。官方固件下 R/G/B/HUE 需机身「画面向导 → 自定义1」确认一次 —— 这是 p7 归一化器域界（`0x100–0x12e`）的结构性限制，不是脚本 bug。
- 诚实边界：WB 不在配方内（请用机身白平衡）；配方是全局色彩向量，做不出高光滚降 / 分区曝光；NX1 上不启用（prefman 偏移只在 NX500 1.12 实证）。
- 判据只认一条：`sh /opt/usr/nx-ks/filmlab.sh check` 直接读 ISP 手上那七维跟配方比对（只读、零风险）。**"值变了" ≠ "被消费"**。
- 另有 `scripts/nx-rc/MOBILE_MOBILE.sh`（双击 WiFi = 零 UI 轮换下一条配方）——不进安装链，需要时手动放到 `/opt/usr/nx-ks/`。

## 3D LUT

| 项 | 现状 |
| --- | --- |
| 表格式 | `4913×4B {R,G,B,pad}`，索引 `((B*17+G)*17+R)*4`，槽 19,712 B，步长 `0x4D00` |
| 换表 | 写 19,712 B 进工作槽（A18 `0x81119F00`）+ 改**四张**登记表全部指向它 + **半按一次快门** |
| 登记表 | `View4` 四项（色彩空间×屏幕色彩）+ `Still6` 六项 + `BV12` 十二项 —— **一项都不能漏**，漏了就是"取景有、照片没有" |
| 导入 | `.cube → 19,712 B 槽表`：机身 `cube2lut.arm` 一条命令，或 PC 端 `test_server/isp/nx3dlut.py` |
| 取景 / 成片 | 取景只认 `View4`；成片有**两条互斥分支**（屏幕色彩开→`BV12`，关→`Still6`），两条都要指过去 |
| 边界 | 全是内存操作，**断电即回原状**（「开机即生效」仍需改固件镜像）；sRGB 颜色可信，AdobeRGB 只保证生效 |
| 禁区 | ⛔ 自己写 `+0x00C` 再脉冲配置寄存器 ⇒ ISP 读到原厂时序外地址 ⇒ **严重偏色花屏**。唯一安全重载 = **半按快门** |

```sh
sh /opt/usr/nx-ks/lut.sh list | begin | apply <名> | off | status   # 滤镜库 /mnt/mmc/looks/
```

细节：[`docs/current/LUT_RETARGET_LIVE_2026-10-18.md`](docs/current/LUT_RETARGET_LIVE_2026-10-18.md)　面板设计：[`docs/current/LUT_UI_2026-10-18.md`](docs/current/LUT_UI_2026-10-18.md)

## 目录结构

| 路径 | 说明 |
| --- | --- |
| `install.sh` `info.tg` `nx_cs.adj` | SD 卡根触发三件套（装机 / 增量同步） |
| `scripts/` | 全部模块母本 → 同步到相机 `/opt/usr/nx-ks/` |
| `scripts/filmlab.sh` · `scripts/filmlab/recipes.json` | FilmLab 引擎 / 权威配方库（68 条） |
| `scripts/EV_AEL.sh` · `scripts/EV_MOBILE.sh` | 两个组合键入口（`EV+AEL` 滤镜条 / `EV+WiFi` LUT 面板） |
| `scripts/lut.sh` · `scripts/lut/` | 3D LUT 入口 + 四件套（`cube2lut` / `nx_slotwrite` / `nx_regtabwrite` / `nx_regtabdump`） |
| `scripts/nx-rc/` | Web 遥控：`web_root/` `thumb/` `capdtm/` `push/` |
| `test_server/` | PC 端开发验证环境（模拟 API、工具链、门控） |
| `uninstall_pkg/` | 相机菜单卸载入口 |

## 文档

- [`docs/README.md`](docs/README.md) — **文档总索引**（`current` 现行 / `archive` 历史 / `evidence` 证据）
- [`docs/current/HANDOVER_2026-10-16.md`](docs/current/HANDOVER_2026-10-16.md) — 总入口：约定、死路、门控、执行序
- [`docs/current/ONDEVICE_SOP_2026-10-16.md`](docs/current/ONDEVICE_SOP_2026-10-16.md) — 上机日 SOP（就位 / 判据 / 回退）
- [`docs/current/NXUI_NUKLEAR_2026-10-17.md`](docs/current/NXUI_NUKLEAR_2026-10-17.md) — NXUI 安装与验证
- [`docs/current/RE_PROGRESS_2026-10-08.md`](docs/current/RE_PROGRESS_2026-10-08.md) — 逆向进度总览（含死路清单）

> 历史文档里的旧结论（如"View/Still 不可分离""用户态不能写 LUT"）已被推翻，纠错见
> [`ERROR_CORRECTIONS_2026-10-07.md`](docs/current/ERROR_CORRECTIONS_2026-10-07.md)。

## 界限

写清楚比写得好看重要。下表每一条都对应实机或静态验证，没有"应该可以"。

| 维度 | ✅ 能 | ❌ 不能 / 未验 |
|---|---|---|
| 平台 | NX500 固件 **1.12**（全部功能实机验证） | NX1 1.41 可装，但 LUT / FilmLab 未在 NX1 上验证；其它固件版本拒绝安装 |
| 色彩 | **sRGB** 输出下取景与 JPEG 成片颜色可信（45 张随包表的基准） | **AdobeRGB 会生效但颜色未标定**（表按 sRGB 坐标生成）；相机智能滤镜（枚举 14–18）走另一条动态 24 档路径，不覆盖 |
| 载体 | **JPEG 成片 + 取景器** | **RAW（`.SRW`）不承诺被 LUT 烘焙**；视频不在本 mod 范围 |
| 生效 | 写内存即生效（apply 后半按一次装载） | **开机即生效做不到** —— 断电/重启回原厂，要持久化得改固件镜像 |
| 触发 | **半按快门**是唯一可靠的重载点 | 软件触发 p7 重读表的入口尚未找到（`st cap iq af afsta/afsto` 无效） |
| 形态 | 不刷机、不改分区，可双向回滚 | 不改固件分区 ⇒ 重启即回原厂（LUT 写入是内存操作） |

> 它**不是**完整色彩管理（不做输入/输出 profile 转换），**不是**所见即所得承诺（取景与成片处理链不同），
> **不是**破解（不解除区域锁、不改录制时限）。改的是 ISP 里的一个 3D 查找表。

## 硬限制（p7 / 固件层面，不是脚本 bug）

- **全七维 PW 一键需 A2 固件**；官方固件下归一化器域外的值会被拒收。
- **p7 无 UI**（Font/DrawText/Dialog/Widget 全 0 命中）⇒ 界面只能在 Linux 侧改。
- **长按 / 三键以上组合不可得**（内核先消费按键）⇒ 能用的只有「按住 EV + 单键」这一类两键组合。
- 出厂 LUT 表**全是风格表**，不能拿"写 identity 得中性"当判据。

> 胶片仿真引擎与 `.cube` 素材另见 [nx500-filmsim](https://github.com/WApaperplane/nx500-filmsim)（public）。
