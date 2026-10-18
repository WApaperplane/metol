# NX-WA 2.88.0-nxwa.1

首个 **NX-WA** 版本 —— 基于 NX-KS 2.88（KinoSeed）血脉 + 社区上游 `ottokiksmaler/nx500_nx1_modding` 的改造与扩展。

## 这个包是什么

**SD 卡安装包**：解压到 SD 卡根目录 → 插入相机 → 自动安装（首次）/ 增量同步（已装过）。

- 支持固件：**NX500 1.12** / **NX1 1.41**（其它版本会被拒绝）
- 已装过再插卡 = **增量同步**：只覆盖不删除，**永不误卸载**；SD 上的 `scripts/` 母本保留
- 卸载请用相机菜单里的 `uninstall.sh`
- 安装完成后，在设置里**开一次蓝牙**即开始初始化

## 亮点

| 能力 | 说明 |
| --- | --- |
| **FilmLab 胶片配方 68 条** | 负片 / 反转 / 黑白 / 电影 / 风格五族，菜单自动分 4 页 |
| **PW 三维直推** | `EV+AEL` → 点配方：SAT / SHARP / CONTRAST **秒级直接进 ISP** |
| **3D LUT 链路** | 任意 `.cube` → 原生表；预览直灌（LUT1 + `lutsentinel` 守护） |
| **Web 遥控相册** | 实时目录源（新拍立即可见）+ 缩略图预热 + 折叠目录模型 |
| **主菜单直显 IP** | 一键开关 Telnet(23) / FTP(21)，替代 EV+WiFi 组合键 |
| 同步链路 | SD 智能引导器增量同步 + WiFi 在线 push（免拔卡） |

## ★ 诚实边界（务必先读）

- **全 7 维 PW 不能一键**：`R/G/B/HUE` 无外部通路（p7 的 id 归一化器只认 `0x100–0x12e`，界外一律拒收 —— 上机负结论 + 静态机制铁证）。要全维生效，需在机身「**画面向导 → 自定义1**」确认一次，或改 p7（本版不含固件改动）。
- **3D LUT**：预览可直灌；**成片需后处理**（ksfilm）。"成片直灌"已实测为死路（拍片流程会主动重配置 LUT 档位池）。
- **菜单是 mod_gui 覆盖层**：点击即退，不能滚动对比；只取代不迭代。
- **长按 / 连击 / 组合键架构性不可得**（内核先消费按键）⇒「一键」上限 = 一次按键一个动作。
- 配方为 **NX500 专属**；NX1 上 `EV+AEL` 自动回退社区原版长录像脚本。

## 安装三步

```
1. 解压本 zip 到 SD 卡根目录（得到 install.sh / info.tg / nx_cs.adj / scripts/ ...）
2. 插入相机 → 自动执行安装/同步 → 弹窗提示 → 自动重启
3. 拔卡；在相机设置里开一次蓝牙 → 初始化完成
```

## 校验

```
md5: 80ac83fee8c0f7bdda49cbf15c731f2c   NX-WA-2.88.0-nxwa.1.zip
```

包内 `NX-WA-MANIFEST.txt` 含**逐文件 md5**、版本号与构建提交（本包构建自 commit `7164dc7`，分支 `nxwa`）。

## 本次文档审查与更正（README §勘误）

发布前用 `gh` 实测核对，更正了 7 处**错误或已被实测推翻**的表述：

1. 仓库地址 `WApaperplane/nxwa` → **`WApaperplane/NXWA-nx500_modding`**（`/nxwa` 当时不存在；旧名 URL 仍重定向 —— 本次 `git push` 时远端自己回了 "This repository moved…"，属独立印证）。
   ★ **2026-10-18 补记**：该仓库已改名为 **`WApaperplane/metol`**，`NXWA-nx500_modding` 与 `nx500_nx1_modding` 两个旧地址均仍重定向。
2. 上游 `SamsungNX500/nx500_nx1_modding` → **`ottokiksmaler/nx500_nx1_modding`**（前者不存在）
3. 内置配方 18 → **68**；权威源 `nx500_recipes.txt` → **`scripts/filmlab/recipes.json`**
4. 「点配方即生效 / 两步出片」→ **三维可直推即时；全 7 维需机身确认一次**
5. 「View 与 Still 独立」❌ **已证伪**（View 4 档 ⊆ Still 18 档，共用同一缓冲池）
6. 「用户态写 LUT 数据不可行」→ **已修**（`lutapi load` 可行；不可读写的是 p7 内置 4 个缓冲）
7. 「内置表含纯 identity」❌ **判据作废**（出厂表全是风格表）

## 门控状态（未完成项，如实列出）

- **G0/G1 FAIL**：发布时相机离线，未做新一轮上机验证（已知结论来自 10-08/10-09 的实机记录）。
- **U4（SLP 重打包）/ U5（回滚演练）未做 ⇒ G4 未开**。
- ⇒ **本版不含任何固件改动**，全部能力位于用户态（L1 层）。

## 许可证与血缘

**AGPL-3.0** —— 派生自社区上游 `ottokiksmaler/nx500_nx1_modding`（已复核为 AGPL-3.0）。
上游血缘表与发布前核对清单见仓库 [`ATTRIBUTION.md`](https://github.com/WApaperplane/metol/blob/nxwa/ATTRIBUTION.md)。
本包**不含**任何三星原厂固件 / eMMC 备份 / rootfs dump。

## 文档

- 当前执行序：[`docs/current/TASKFLOW_2026-10-10.md`](https://github.com/WApaperplane/metol/blob/nxwa/docs/current/TASKFLOW_2026-10-10.md)
- 逆向进度总览：[`docs/current/RE_PROGRESS_2026-10-08.md`](https://github.com/WApaperplane/metol/blob/nxwa/docs/current/RE_PROGRESS_2026-10-08.md)
- 全部文档索引：[`docs/README.md`](https://github.com/WApaperplane/metol/blob/nxwa/docs/README.md)
- 安装 / 同步 / 回滚（双语）：[`SYNC.md`](https://github.com/WApaperplane/metol/blob/nxwa/SYNC.md)
