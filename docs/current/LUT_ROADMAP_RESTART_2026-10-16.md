# LUT 路线重启方案（2026-10-16）

> **2026-10-18 决策更新**：下文“E4证明成片直灌死路”的外推作废，保留所测LUT1序列的负观察。sel=0值得独立验证，但现有守护只改Cfg，不能阻止P7重灌LUT0；500ms预览恢复不证明赶得上Still。最新路线和离线脚本见[LUT0路线复核](LUT_SEL0_ROUTE_REVIEW_2026-10-18.md)。

> **背景**：LUT 线于 10-09 冻结（工具链落地 + U6 波待上机）；A2/PW 线 10-15 达成后重启（用户指令：「LUT 路线还是要再提上日程了」）。
> **输入**：`LUT_PIPELINE_DESIGN_2026-10-09`（链路）、`3DLUT_TABLE_FORMAT_2026-10-08`（表格式）、`3DLUT_VIEW_STILL_ISOLATION_2026-10-08`、`P7_RECLAIM_COUNTERMEASURE_2026-10-09`（守护）、`3DLUT_APPLY_PATHS_2026-10-08`（线路）、`test_server/u6/runbook.txt`。
> **性质**：现状盘点 + 资产修复（本日已执行）+ 路线设计 + 上机批设计。

---

## ★ 2026-10-16 口径修正（依 `U6_ONMACHINE_RESULT_2026-10-09` 与 `FILMLAB_LUT_NATIVE_UI_GOALS_2026-10-16`）

> 本文初稿有两处**硬错误**，以下为修正后的权威口径（GOALS 文档为路线定位的最终依据）：

1. **「LUT1/守护从未实测」= 错误**。10-09 夜二轮上机**已完成**：
   - **E1 ✓**：`lutpick apply _identity --ch1`（sel=1）→ Cfg=0x1110（**SelLUT=1**）⇒ **LUT1 通道接入主渲染链**；
   - **E3 ✓**：`lutsentinel` 运行中用户半按 → **6 次「抢回→恢复」rc=0**，恢复延迟 <500ms；**双单元隔离实锤**；
   - **E4 ✗**：Portra→LUT1 拍摄 → 照片无胶片感（Still 流程主动重配置 Cfg `0x0→0x1100`）⇒ **成片直灌负结果保留**。
   - ⇒ 相关项后续按**回归**处理（不是「首发」）；仍待补的只有：新构建产物回归、连续切换/模式变化行为、负载（E5，低优先）。
2. **「E0=(0,0,0) 即 identity（9 个）」= 语义错误**。按转换器现用格点逐项比对，**严格 identity = 0 个**；
   `0x80897BC0` 实为**低对比灰调表**（白点→(185,185,255)，4092/4913 项非恒等）。
   ⇒ 42 个候选静态表**不等于** 42 个可选滤镜槽；「黑点为 0」不能作为 identity 判据。修正版校验见 `T1_LUT_SEMANTICS_2026-10-16.md`。
3. **路线定位以 GOALS §4 为准**：LUT1+守护 = **预览/诊断后端**（不承诺拍照稳定生效）；C1 = **机制实验手段**（先做来源/消费者映射）；
   **C3 = 长期候选主线**（日常导入无需反复刷机）；C2 = 条件候选（先验写入/长度/权限/同步语义）；软件后处理 = 独立备选。
   本文 §3 的 C1/C2/C3 描述保持为技术备忘，**优先级与承诺以后者为准**。

---

---

## 0. 结论（先读）

1. **资产已修复**（本日）：3 个部署产物从 mod 工作副本恢复入库 + **2 个缺失工具重建**（`cmasafe.arm` / `lutsentinel.arm`，chroot 冒烟 PASS）——`deploy_luts.py` 的推送链**恢复完整**。
2. **三条路线**：
   - **R-A 保底（已通）**：ksfilm 后处理（取景器不动，成片定稿）。
   - **R-B 主线（待上机终验）**：CMA 直灌 LUT1 + `lutsentinel` 守护 → 取景器所见即所得；成片是否跟随 = U6 §[6] 判据。
   - **R-C 进阶（★ 新契机，三个离线候选）**：**表进「p7 档位池」**——从根上消灭「被抢回」：
     - **C1 刷机式**：改 p7 镜像内静态表池（镜像内现成 20+22 槽）→ 「LUT 固件包」（复用 A1/A2 刷机链）。**纯离线可做。**
     - **C2 运行时通道**：`st cap mem`（p7 T-Kernel 调试通道，能力待验证）写运行时池 → 免刷机换表。
     - **C3 补丁式**：p7「表写入器」微补丁（A2 V3 式：从 CMA 拷 19652B 到档位池槽 + 触发）——离线设计 + QEMU 验证。
3. **近期执行序**：U7 上机批（R-B 终验 + E1 sel=1 首测 + 守护实测）；同时 C1/C3 离线开工。
4. **待决策 3 项**（§5）。

---

## 1. 现状盘点

### 1.1 链路能力矩阵

| 环节 | 状态 | 证据 |
|---|---|---|
| `.cube` → 硬件表（4913×4B，槽 0x4D00） | ✅ 已解+工具 | `3DLUT_TABLE_FORMAT`（逐字节自证）；`test_server/isp/nx3dlut.py` |
| 表推送（FTP + md5 清单） | ✅ 落地 | `test_server/lutpipe/deploy_luts.py build/push` |
| CMA 落点安全闸（四查） | ✅ 落地 | `u6/cmasafe.c`（范围为二 CMA 区、黑名单 `0x94000000+0x5000`、4KB 对齐、全零） |
| 写入通道（sel=0 厂商通道） | ✅ 历史验证 | `lutapi.arm sel=0`；`lutload.arm restore` 常备 |
| **取景器显示（View）** | ◐ **待上机终验** | U6 §[4] R3-A/B（identity 中性 / Portra 风格） |
| **成片（Still）** | ❓ **待上机判据** | U6 §[6]：不半按拍 1-2 张，成片 vs 取景器比对 |
| 抢回对策（双通道 + 守护） | ✅ **已实测（10-09 E1/E3）** | `P7_RECLAIM_COUNTERMEASURE`；E1 ✓（LUT1 接入主渲染链）/ E3 ✓（守护 6 次抢回-恢复 rc=0）；本文按**回归**处理 |
| 一键操作 | ✅ 落地 | `lutpick.sh list/apply/off/status`（+`--ch1/sentinel`） |
| 保底后处理 | ✅ 已通 | ksfilm（4 配方，跨环境逐字节一致） |

### 1.2 关键事实（引用）

- **表格式**：4913 项 × 4B `{R,G,B,pad=0}`，索引 `((B*17+G)*17+R)*4`，**槽步长 `0x4D00`**（19712B）。
- **表池三处**：
  - **镜像内静态池**（`p7_full.bin`，VA `0x808847C0` 起，Block A 20 槽 + Block B 22 槽）——**可直接离线读写**；
  - **运行时池（View/Still）**：标准 `0x810FD100` / 黑白 `0x81101E00` / 电影 `0x81106B00` / 肤色 `0x81115200`（镜像外 BSS）；
  - **MCB 池**：`0x813D8800 / 0x813DD500 / 0x813E2200 / 0x813E6F00`。
- **一致性**：「标准」表在镜像静态池与运行时 `0x810FD100` **逐字节一致** ⇒ 静态池 = 运行时池的内容源（复制路径待精确定位）。
- **p7 只用 LUT0**（View/Still/MCB 的 `_load` 全 `sel=0`）⇒ 我们的表放 LUT1（`sel=1`）不被覆盖；抢回只改 `Cfg.SelLUT`（一个寄存器写）⇒ `lutsentinel` 恢复。
- **CMA 两个合法区**：`0x8f800000..0x94000000` / `0x94000000..0xa6000000`；事故黑名单 `0x94000000+0x5000`。

### 1.3 资产与缺口

| 件 | 路径 | 状态（md5 短） |
|---|---|---|
| `cmapick2.arm` / `lutapi.arm` / `lutload.arm` | `test_server/sysarch/` | ✅ **本日恢复入库**（`2539e765` / `c0f81bee` / `a32dfd7f`） |
| `cmasafe.arm` | `test_server/u6/` | ✅ **本日重建**（`592db890`，6,320B） |
| `lutsentinel.arm` | `test_server/lutpipe/` | ✅ **本日重建**（`bc7c2f72`，10,920B） |
| `lutpick.sh` / `deploy_luts.py` / `nx3dlut.py` | `lutpipe/` / `isp/` | ✅ 在位 |
| 表 `.bin` 包（`build/luts/*.bin`） | — | ❌ **缺**（需 `.cube` 源；见 §5-D2） |
| `.cube` 源（Kodak 6 张等） | — | ❌ 本机无 |
| U6 实验包（runbook/cmasafe.c/u6_lut.sh 等） | `test_server/u6/` | ✅ 在位（runbook 22KB） |

---

## 2. 本日修复动作（盘点→补齐，全部离线）

1. **产物恢复**：从 mod 工作副本 `NX-WA-2.88.0-nxwa.1/scripts/sysarch/` 恢复 3 个 arm 到仓库 `test_server/sysarch/`（md5 台账见 §1.3）。
2. **缺失重建**：新脚本 `test_server/lutpipe/build_lut_tools.sh`（相机 ABI 配方：crt0 + 直链 libc-2.13）。
   - 教训入脚本：**`-D_TIME_BITS=32 -D_FILE_OFFSET_BITS=32`**（防 time64 符号）+ **glibc 2.13 的 `clock_gettime` 在 librt**（相机自家 `st` 亦 NEEDED `librt.so.1`）。
3. **chroot 冒烟**（rootfs-112 + qemu-arm-static）：
   - `cmasafe.arm` 无参数 → usage/rc=1 ✅；带非法地址 → 完整四查逻辑输出（打印两 CMA 区）+ rc=2 ✅
   - `lutsentinel.arm --sel 0 --count 1` → 正常启动至硬件调用点（`d5_ep_open rc=-2`，无硬件符合预期）✅
4. `.gitattributes` 增 `*.arm binary`。

---

## 3. 三条路线

### R-A —— 保底（已通，零阻塞）

拍原始 → ksfilm 后处理。取景器不显示 LUT。**价值**：立刻可用的成片 LUT 工作流；`FILMLAB_WHEEL_PREVIEW` 定式的一半。

### R-B —— 主线（机制齐备，待上机终验）

```
.cube → nx3dlut → 槽表(19752B) → deploy_luts.py push → /mnt/mmc/filmlab/luts/
  → lutpick.sh apply <名>（cmapick2 落点 → cmasafe 四查 → lutapi load sel=1）
  → LUT1 生效（取景器）
  → lutsentinel 守护（p7 抢回 Cfg 后写回 sel=1）
  → 成片：U6 §[6] 判据（不半按拍 1-2 张比对）
```

- **待证（修正口径）**：① **LUT1+守护 = 回归项**（E1/E3 已于 10-09 实测；待补新工具产物回归、连续切换/模式变化、负载 E5）；② Still 成片已被 **E4 判负**（直灌不跟随）⇒ 成片路径另寻（R-A 保底 / R-C）；③ 「平时画面基准表」（0x81115200）文件版候选 = ID#1/#2/#3，附录 C 闭环实验**未做**。
- **回退**：`lutpick.sh off`（identity）→ `lutload.arm restore` + 半按 → 重启。

### R-C —— 进阶：表进档位池（★ 新契机，三候选）

**动机**：R-B 的「抢回」是 p7 事件驱动的表重载——**从根上消灭它的唯一方式 = 让 p7 自己拿的就是我们的表**。

| 候选 | 机制 | 离线可做 | 优点 | 未知/风险 |
|---|---|---|---|---|
| **C1 刷机式** ★首推 | 改 **p7 镜像内静态表池**（现成 20+22 槽）→ 重新打 SLP 包 → 刷机（复用 A1/A2 链） | ✅ **全离线**（表生成器 + 镜像补丁 + SLP 打包） | 真·全程所见即所得（含拍片）；**多槽 = 多 LUT**（切档换表）；抗抢回天然成立 | 静态池 → 运行时池的复制路径需定位（离线 RE）；刷机换表（低频、可接受） |
| **C2 运行时通道** | `st cap mem`（p7 T-Kernel 调试通道）写运行时池 | ◐ **能力待验**（离线查 st 二进制 + 上机试） | 免刷机、即时换表 | `st cap mem` 是否支持**写**、写 p7 内存的限制/风险 |
| **C3 补丁式** | p7「表写入器」微补丁（A2 V3 式：外部给「CMA 源地址 + 槽号」→ p7 拷 19652B 进档位池 → 触发 load） | ✅ 离线设计 + **QEMU 可验证**（a2_qemu 模式） | 即时换表 + 抗抢回；与 A2 通道同构 | 拷贝循环代码量（~60B，A2 块 80B 同级）；DMA/cache 一致性 |

> **关键支撑事实**：镜像内静态池可直接离线读写（`3DLUT_TABLE_FORMAT` 逐字节自证）——**C1 的技术风险很低**，主要工作在「表→槽映射」与「打包链」。
> **与 A2 的关系**：A2 已证明「外部写 p7 槽」的通道模式（0x134..0x13B → 槽 + 触发）；C3 是其向「大块表数据」的自然延伸。

---

## 4. U7 上机批设计（R-B 终验，建议并入 ONDEVICE_SOP）

**前置**：门控重跑；SD 部署 `filmlab/`（工具 5 件 + `lutpick.sh` + 表包）；**相机停在菜单界面**（写表需要官方 API 安全闸放行）。

| 步 | 动作 | 判据 | 风险/回退 |
|---|---|---|---|
| 1 | `lutpick.sh list` | 列出表目录（空则先 push 表包） | — |
| 2 | `lutpick.sh apply <identity> --dry` | 落点探测 + 四查全过（不写） | 失败 ⇒ 等更安全时机（**不换地址硬上**） |
| 3 | `lutpick.sh apply <identity>`（**sel=1**） | **回归**（E1 已于 10-09 通过）：Cfg 终态 `SelLUT=1`；画面变化。★ **写表需前置「抢回态」**——先对焦/半按一次再写（10-09 §2 规律） | 异常 ⇒ `off`/`lutload restore` |
| 4 | `lutpick.sh apply <Portra 400>` | 取景器出**可分辨、与表语义一致**的风格（新判据；「写 identity→中性」已作废） | 同上 |
| 5 | Still：直拍 1-2 张 → 比对成片 vs 取景器 | **E4 已判负**（直灌不跟随）⇒ 本步为复核记录（记 Still 流程 Cfg `0x0→0x1100` 重配置序列） | — |
| 6 | `lutsentinel --sel 1 --count 120`（1 分钟） | 半按/切档后画面**自动恢复**（日志有恢复行） | 频繁恢复告警 ⇒ 记录间隔 |
| 7 | 叠加观察：PW 一键 + LUT 同时开 | 记录观感（是否过强） | — |
| 8 | 回退演练：`off` + `restore` + 重启 | 画面回中性 | — |

- **纪律继承**：单会话单命令、结果 FTP 拉、`setsid` 脱离；（u6/runbook.txt 全文为准）。
- ⛔ 禁 `systemctl restart di-camera-app`。

---

## 5. 待决策

| # | 项 | 选项 | 建议 |
|---|---|---|---|
| **D-LUT1** | U7 上机批安排 | ① 独立一趟（LUT 专属，变量干净）② 并入下一批（省开关机） | 若与 P5/C-2 批同趟：**先做 P5/C-2 验证再做 LUT**（避免互相干扰） |
| **D-LUT2** | `.cube` 源 | ① 用户自备（他自有 LUT 库）② Kodak 官方免费 LUT（Portra 400 等）③ `make_cube.py` 从配方烘焙（自产） | ①+③ 并行：用户提供偏好 LUT，另用 ③ 生成测试件跑通链路 |
| **D-LUT3** | R-C 是否启动 | ① 先 C1（刷机式，纯离线，风险低）② 先验 C2（`st cap mem` 能力，快）③ 等 R-B 上机判据后再定 | **建议：C1 离线开工 + C2 顺手上机验**（两者都不阻塞 R-B） |

---

## 6. 证据与资产索引

- 设计：`LUT_PIPELINE_DESIGN_2026-10-09`（链路）、`3DLUT_TABLE_FORMAT_2026-10-08`（表格式）、`P7_RECLAIM_COUNTERMEASURE_2026-10-09`（守护）、`3DLUT_VIEW_STILL_ISOLATION_2026-10-08`（池⊆关系）
- 实验包：`test_server/u6/`（runbook.txt 22KB 全文判据）
- 工具：`test_server/lutpipe/{deploy_luts.py, lutpick.sh, lutsentinel.c, build_lut_tools.sh}`、`test_server/isp/nx3dlut.py`
- 产物：`test_server/sysarch/{cmapick2,lutapi,lutload}.arm`、`test_server/u6/cmasafe.arm`、`test_server/lutpipe/lutsentinel.arm`
- 冒烟：本日 chroot 输出（见 §2）

---
*生成：2026-10-16 · 离线完成（资产修复 + 冒烟 + 路线设计）；R-B 上机动作待放行。*
