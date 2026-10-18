# LUT 应用链路设计（2026-10-09）

> ⚠️ **2026-10-18 文档清理：本文结论已被取代。** 文末「定式 = 预览直灌 / 成片后处理」**已不成立**：成片走 `Still6` 同样可换表。
> 现行结论见 [`LUT_RETARGET_LIVE_2026-10-18.md`](LUT_RETARGET_LIVE_2026-10-18.md)。


> 任务：设计一条链路推进 LUT 应用 —— **可选 / 可导入 .cube / LUT 显示 / LUT 照片真实可用**。
> 形态：**链路设计 + 已落地资产**（`lutpick.sh` + `deploy_luts.py` + 复用 U6 安全闸）。
> 前置事实：表格式已解（`3DLUT_TABLE_FORMAT`）、写入路径已验证（`lutapi.arm` sel=0）、
> 安全闸已备（`cmasafe`）、R3 上机验证已排入 U6 波次。全程 L1（零 G4 依赖）。

---

## 0. 一句话

> **`.cube`（PC 任意来源）→ `deploy_luts.py` 一键转换+推送 → 相机 `lutpick.sh apply <名>`
> → 取景器秒级显示 → 成片（Still）按 U6 判据实证**。
> 四个需求全部有明确落点；唯一待上机实证的是"拍片时表是否被 p7 抢回"（§5，U6 §[6] 判据）。

---

## 1. 链路全景

```
[PC 侧]                                    [相机侧]
 任意 .cube ─┐
            ├─► nx3dlut.py import（按硬件非均匀格点 {0,16,…,240,255} 采样）
 Kodak 6 张 ─┘        │
                      ▼
            19712B 整槽表（*_slot.bin）
                      │  deploy_luts.py push（FTP，带 md5 清单）
                      ▼
             /mnt/mmc/filmlab/luts/*.bin ──► lutpick.sh apply <名>
                                                  │
                                        ┌─────────┼──────────────┐
                                        ▼         ▼              ▼
                                   cmapick2    cmasafe        lutapi load
                                   （找落点）  （四查闸）      （sel=0）
                                        └─────────┬──────────────┘
                                                  ▼
                                     硬件 LUT0 ← 表（DMA）
                                                  │
                              ┌───────────────────┴───────────────────┐
                              ▼                                       ▼
                      View 取景器（秒级）                     Still 成片（待实证 §5）
```

---

## 2. 四需求 → 实现映射

| 需求 | 实现 | 地位 |
|---|---|---|
| **可选** | `lutpick.sh list / apply <名> / off / status`；目录 `/mnt/mmc/filmlab/luts/`；`current` 记账文件 | ✅ 落地 |
| **可导入 .cube** | `deploy_luts.py build`（扫描任意目录 → 转换 → 清单）→ `push`（FTP） | ✅ 落地（本日 build 实测 7 表，与 U6 包**字节级交叉一致**） |
| **LUT 显示** | `apply` = 落点探测→安全闸→`lutapi load`（历史验证路径）→ 取景器秒级变化 | ✅ 机制落地；U6 §[4] 终验 |
| **照片真实可用** | 硬件 LUT0 为 View/Still 共用池（`VIEW_STILL_ISOLATION` §1）；**Still 覆盖风险**见 §5 | ◐ U6 §[6] 拍片实证；保底见 §5.3 |

---

## 3. 组件与用法

### 3.1 PC 侧

```bash
PY=C:/Users/31623/.workbuddy/binaries/python/versions/3.13.12/python.exe

# ① 转换 + 清单（默认扫 test_server/filmsim/luts/；--cubes 追加密目录）
$PY test_server/lutpipe/deploy_luts.py build [--cubes "D:/my_cubes"]

# ② 推送（表 + 工具；FTP 根 == SD 卡）
$PY test_server/lutpipe/deploy_luts.py push --host 192.168.0.105
# 二合一：build-push
```
产物：`test_server/lutpipe/build/luts/*.bin`（19712B 整槽）+ `manifest.json`。
**单表转换**亦可直接 `nx3dlut.py import <cube> <out.bin> --slot`。

### 3.2 相机侧（一次性 chmod 后）

```sh
BB=/opt/usr/nx-ks/busybox
# 列目录
$BB sh /mnt/mmc/filmlab/lutpick.sh list
# 应用（自动：探测→闸→load→记账；约 30-60s，含 cmapick 扫描）
$BB sh /mnt/mmc/filmlab/lutpick.sh apply Kodak_Portra_400
# 关闭（加载 _identity 表 = 画面回中性）
$BB sh /mnt/mmc/filmlab/lutpick.sh off
# 只探测不写（演练）
$BB sh /mnt/mmc/filmlab/lutpick.sh apply Kodak_Portra_400 --dry
```

### 3.3 相机端落点

```
/mnt/mmc/filmlab/luts/<名>.bin     ← 表（deploy_luts.py 推送）
/mnt/mmc/filmlab/luts/current      ← 记账（上次应用的名；非硬件读回）
/mnt/mmc/filmlab/{cmasafe,cmapick2,lutapi,lutload}.arm + lutpick.sh
```

---

## 4. 与 PW「一键滤镜」通道的关系（两条独立引擎）

| | PW 7 维（一键滤镜） | 3D LUT（本链路） |
|---|---|---|
| 作用面 | ISP 的 PW 引擎参数（增益/色彩/hue/锐度/对比） | ISP 的 3D LUT 硬件表（全格点映射） |
| 粒度 | 7 维标量 | 4913 点 × 三通道 |
| 适用 | 轻调色/风格微调（胶片味参数） | 强风格/精确色彩映射（film 模拟 LUT） |
| 工具 | `pwsend.arm` + `filmlab.sh` | `lutpick.sh` + `deploy_luts.py` |
| 叠加 | **两者可叠加**（不同硬件单元，先后串联生效）——叠加时的观感需上机记录 | 同左 |

★ 两条都在 L1；互不依赖。推荐工作流：LUT 定"大调"、PW 微调画面；或只用其一。

---

## 5. ★ 关键待实证点：Still 拍片与"表被抢回"

> ★ **2026-10-09 更新：本节问题已有系统处理方案** —— 见
> [`P7_RECLAIM_COUNTERMEASURE_2026-10-09.md`](P7_RECLAIM_COUNTERMEASURE_2026-10-09.md)：
> **双通道隔离（表进 LUT1，p7 不碰）+ 寄存器级守护恢复（lutsentinel）**；
> 本节升级为"实验 E1–E5"（并入 U6 附录 A）。

### 5.1 风险（诚实陈述）

历史实测：**半按快门**会让 p7 的 `View::_load` 重设表指针（"抢回出厂表"）。
推论：**快门（Still 流程）大概率也会触发一次从档位池的 load** ⇒ 直灌硬件 LUT0 的表
可能在拍照瞬间被覆盖为"档位表"——成片不带我们的 LUT。

### 5.2 U6 §[6] 判据（已排入上机包，直接回答）

> 保持 Portra 表生效 → **不半按**、直接拍 1-2 张 → 与取景器比对。
> - **成片有色（跟随）** ⇒ 直灌即所见即所得 ⇒ 本链路"照片"一栏 ✅ 直接闭环。
> - **成片无色（被抢回）** ⇒ 转 §5.3 保底/或等 §5.4。

### 5.3 保底路线（今天即可用，零门控）

**ksfilm 后处理**：拍原始 → 相机/PC 侧对成片做 LUT 处理（引擎已跑通 4 配方，跨环境
逐字节一致）。缺点：非实时、取景器不显示 LUT——按"拍原始 + 后处理"工作流使用。
（若选此路，建议取景器用 PW 通道做"预告"、成片用 ksfilm 定稿——两条通道配合。）

### 5.4 进阶路线（G4 后）

把自定表**写进 p7 的档位池**（替换"自定义"档内容）→ p7 自己 load → 真·全程所见即所得
（含半按/拍片）。属改 p7 领域，**须 G4 转绿**（U4→U5 之后），不在本链路当前范围内。

---

## 6. 安全与回退

| 层 | 机制 |
|---|---|
| 落点 | 只认 cmapick「4KB 粒度命中」行；无该行 ⇒ 拒绝（防 0x94000000 事故族） |
| 写入 | `cmasafe` 四查（CMA 范围/黑名单/4KB 对齐/全零）不过 ⇒ 不写 |
| 通道 | `sel=0`（厂商通道，历史验证不花屏）；`lutload.arm restore` 常备 |
| 回退 | ① `lutpick.sh off`（identity 表）② `lutload.arm restore` + 半按 ③ 重启 |
| 部署 | 工具走 SD 自包含（`/mnt/mmc/filmlab/`），与 u6 实验包同源（单一来源：`u6/cmasafe.arm`、`sysarch/*.arm`） |

---

## 7. 上机验证映射（与 U6 runbook 对应）

| 本链路环节 | U6 runbook 节 | 判据 |
|---|---|---|
| 转换正确性 | 已完成（离线交叉验证：Portra400/identity md5 == U6 包） | 字节级一致 |
| 落点/安全闸 | §[2][3] | cmasafe 真机行为校准 |
| **显示**（View） | §[4] R3-A/B（identity 中性 / Portra 风格） | 取景器目视判据 |
| **照片**（Still） | §[6] 拍片 | 成片 vs 取景器一致性 |
| 读回交叉验证 | §[7] save 通道 | 字节级或负结论 |
| 产品化复跑 | 本链路 `lutpick apply`（复用同一套闸与参数） | `--dry` 先演练 |

---

## 8. 未决与进阶

| # | 项 | 说明 |
|---|---|---|
| 1 | Still 覆盖问题 | §5；U6 实证后二选一（直灌闭环 / ksfilm 保底） |
| 2 | 表切换的"零延迟" | 每次 apply 都跑 cmapick（约 30-60s）。可优化：缓存落点+复检（v2） |
| 3 | LUT × PW 叠加观感 | 上机记录一张叠加样例（判断是否双通道共振过强） |
| 4 | 档位池直写（真·所见即所得） | G4 后；含"自定义档 ↔ 表文件"映射设计 |
| 5 | 1D .cube 曲线 | nx3dlut 已支持（展开为逐通道曲线）；本链路一并可用 |

---

*生成：2026-10-09 · 分支 `nxwa` · 离线完成 · 上机验证按 `test_server/u6/runbook.txt` 执行*
