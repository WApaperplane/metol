# T5 —— LUT 预览后端产品化（2026-10-16）

> **2026-10-18 离线更新**：后端支持`apply <name> --sel 0|1 [--dry]`（默认1）；picker显式接受`--ch0|--ch1`并拒绝冲突选项。状态从`current.sel`读取请求值，旧记账缺通道时返回null；sel=0拒绝活动守护，不自动启动守护，不宣称成片通过。本轮未部署，详见[LUT0路线复核](LUT_SEL0_ROUTE_REVIEW_2026-10-18.md)。

> **同日后续修正**：真实shell调用漏传 `--ch1` 已修复；旧输出中的 `sel:1` 不能作为硬件证据。`status.sel` 改为 `null`，请求通道另列 `sel_requested`；模拟器不再虚构守护已启动。新增实际shell/驱动回归，详见 [恢复链审计与T5修正](DELIVERY_RESUME_AUDIT_2026-10-16.md) §5–6。机端仍是此前部署版本，本轮没有重新部署。

> **任务来源**：`FILMLAB_LUT_NATIVE_UI_GOALS_2026-10-16.md` §5（T5，P2：LUT预览后端产品化——「已有LUT1能力回归；关闭/恢复、切换、负载和失效状态可靠；可被统一控制器调用」）。
> **输入**：`LUT_PIPELINE_DESIGN_2026-10-09`（链路）、`P7_RECLAIM_COUNTERMEASURE`（守护）、`U6_ONMACHINE_RESULT`（E1/E3 实测）、`T1 §4`（三概念分离）、`T2`（协议）。
> **性质**：后端实现在本日完成（离线 + 契约自测）；上机回归见 §5（U7）。

---

## 0. 结论（先读）

1. **后端已实现**（两件）：
   - **相机侧** `test_server/lutpipe/lut_backend.sh`——把 LUT1 预览链封装为符合 T2 协议的 `probe / apply / rollback / status`，**stdout 单行 JSON**（控制器可直接解析）；
   - **PC 侧** `test_server/lutpipe/lut_backend.py`——离线模拟（`--sim`，与 shell 版**同构契约**）+ 真实驱动（经 `nx-telnet.py` 转发）+ **契约自测**（`--selftest`）。
2. ★ **发现并处理一个真实的语义冲突**：现有 `lutpick.sh off` 的实现是「**加载 `_identity` 表**」（LUT_PIPELINE §3.2）——
   按 GOALS §3 与 T1 §4，**关闭 LUT ≠ 加载 identity**。⇒ 本后端 `rollback` 走 **`factory_restore` 路径**（停守护 + `lutload.arm restore` 恢复出厂表指针），并在 JSON 里**硬标注 `identity_used:false`**（契约自测对这条做了断言）。
3. **契约自测 8/8 PASS**（证据 `logs/t5_backend_selftest_2026-10-16.txt`）。
4. **U7 上机执行改用本后端**（比手敲 lutpick 更规范、判据为 JSON）；`ONDEVICE_SOP §10` 已同步。

## 1. 接口（T2 协议映射）

| T2 适配器方法 | `lut_backend.sh` 子命令 | 输出（JSON 关键字段） |
|---|---|---|
| `probe()` | `probe` | `{ok, tools:{cmasafe,cmapick2,lutapi,lutload,lutsentinel,lutpick}, luts_count, guard, precondition}` |
| `apply()` | `apply <表名> [--dry]` | `{ok, level:"full"/"failed", table, sel:1, dry, note}`；失败带 `error:"table_not_found"/"lutpick_apply_failed"` |
| `rollback()` | `rollback` | `{ok, path:"factory_restore", **identity_used:false**, guard_stopped, restore_rc, note}` |
| `status()` | `status` | `{ok, guard, current, sel, note}`（`current` = 软件记账，**非**硬件读回——如实标注） |

- **结果分级**沿用 T2：`full` / `failed`（`skipped` 在 LUT 侧不适用——表缺失即 `failed`）。
- **异步约定**（T2 §4）：`apply` 内部调 lutpick（cmapick 扫描可能 30–60s）⇒ 控制器须在工作线程调用，完成后再回填 UI。
- **前置语义进 probe 输出**：`precondition:"apply 前需前置抢回态（先对焦一次）"`——这是 U6 §2 的实测规律，写进契约避免误用。

## 2. 关闭语义（★ 本任务的关键修正）

| 动作 | 旧实现（`lutpick.sh off`） | 本后端（`rollback`） |
|---|---|---|
| 停止守护 | ✗（未涉及） | ✅（kill lutsentinel + 清 pid 文件） |
| 恢复出厂表 | ✗（**写 identity 表**——画面变中性但不等于原厂） | ✅（`lutload.arm restore` 恢复出厂表指针 `0x81115200` 族） |
| JSON 标注 | — | ✅ `identity_used:false`（契约断言） |
| 语义 | 「画面回中性」（**≠关闭**） | 「已恢复原厂配置」 |

- 保留 `lutpick.sh off` 原样（它是既有工具，且 identity 加载在**诊断**场景仍有用）——但**产品路径必须走 factory_restore**（GOALS 要求）。
- identity 的正确用途（T1 §4）：**诊断**（验证写入链 / 观察「移除风格处理」）——在 JSON/文档里保持 `purpose:"diagnostic"` 语义。

## 3. 状态与判据（关闭/恢复/切换/负载/失效）

| 维度 | 判据（上机取数） | 工具 |
|---|---|---|
| **关闭/恢复** | `rollback` 后：守护不在（`guard:0`）、画面回原厂（与「未灌表」基准一致）、`restore_rc:0` | `lut_backend.sh rollback` + 目视 |
| **切换** | 连续 `apply A→B→A`：每次 `level:"full"`；画面 A/B 可辨且可复现；**记录是否每次都需要重新「抢回态」** | `apply` ×N + 目视 |
| **负载** | `lutsentinel` 运行中（500ms 轮询）：两轮 `loadavg` 采样 vs 基线；恢复延迟（<500ms 历史值） | `probe` + `top/uptime` |
| **失效状态** | ① 表缺失 → `failed/table_not_found`（不误报成功）；② 落点被拒 → `failed/lutpick_apply_failed`；③ 守护被误杀 → `guard:0` 如实反映；④ `lutload` 缺失 → `rollback` 的 `restore_rc` 非 0 且 `ok:false` | 契约已覆盖（自测） |

## 4. 契约自测（8/8 PASS）

```
[OK] probe JSON 契约            [OK] apply 成功 → level=full / sel=1
[OK] apply 后 status：guard=1   [OK] 表不存在 → failed/table_not_found
[OK] dry-run 不改变状态          [OK] ★ rollback 的 identity_used == false
[OK] rollback 走 factory_restore [OK] rollback 后状态清空
```
- 证据：`test_server/lutpipe/logs/t5_backend_selftest_2026-10-16.txt`
- 复现：`python test_server/lutpipe/lut_backend.py --selftest`
- 注：模拟模式（`--sim`）每次调用为独立进程、状态不持久（真实后端状态由相机侧持久：守护进程 + `luts/current`）；序列语义由 `--selftest` 覆盖。

## 5. U7 上机执行（更新版，替换 SOP §10 的手敲命令）

```sh
# 0) 部署：SD /mnt/mmc/filmlab/ 放工具 5 件 + lutpick.sh + lut_backend.sh + 表包
# 1) 探测
/opt/usr/nx-ks/busybox sh /mnt/mmc/filmlab/lut_backend.sh probe
# 2) 演练（不写）
/opt/usr/nx-ks/busybox sh /mnt/mmc/filmlab/lut_backend.sh apply _identity --dry
# 3) 首测（E1 回归；★ 前置：先对焦一次以进入「抢回态」）
/opt/usr/nx-ks/busybox sh /mnt/mmc/filmlab/lut_backend.sh apply _identity
# 4) 风格表（可辨效果）
/opt/usr/nx-ks/busybox sh /mnt/mmc/filmlab/lut_backend.sh apply portra400
# 5) 状态/记账
/opt/usr/nx-ks/busybox sh /mnt/mmc/filmlab/lut_backend.sh status
# 6) 守护实测（半按触发抢回→恢复）
/opt/usr/nx-ks/lutsentinel.arm --sel 1 --count 120
# 7) 关闭（★ factory_restore；判 identity_used:false + 画面回原厂）
/opt/usr/nx-ks/busybox sh /mnt/mmc/filmlab/lut_backend.sh rollback
# 8) 切换测试（A→B→A）+ 负载采样（两轮）
```
- 判据落点：`raw8/gates/lut/`（JSON 原文 + 目视照片）。

## 6. 与 T2 的关系

- 本后端 = T2 协议中 **`lut` 适配器的真实实现**（T2 文档 §3.1 的 mock 已被此实现替换；`preset_sim.py` 的 `LutMock` 保持为**契约参考**）。
- T2 状态机的 `partial` 场景（PW 成功 + LUT 失败）需要**两者同时在场**才能演示 —— 上机时可用「A2 直推 + LUT apply 失败（表缺失）」组合复现（低成本）。

## 7. 未决

| # | 项 |
|---|---|
| 1 | 「切换是否每次都需要重新抢回态」——上机记录（T5 §3 切换判据） |
| 2 | `lutsentinel` 的**负载上限**（轮询间隔 vs 单核占用）——上机取数后定默认值 |
| 3 | Cfg 读回能力（`status` 目前为软件记账）——若 `st cap` 可读 Cfg，升级 `status` 为硬件判据 |
| 4 | 与 U7 合并执行时的**变量隔离**（LUT 实验不要与 C1 刷机同趟混测——见 T6 §5） |

## 8. 上机首验（2026-10-16 晚 · 相机在线）

> 完整记录与原始输出：`raw8/gates/lut/t5_backend_onmachine_2026-10-16.md`（+ `u7_2_dry_*.log` / `t5_backend_onmachine_2026-10-16.txt`）

| 项 | 结果 |
|---|---|
| `probe`（修复前） | `lutload:0` —— 工具在 SD，脚本只找 `/opt/usr/nx-ks/`，**`rollback`（factory_restore）会失效**（离线模拟覆盖不到的致命路径） |
| 修复 | `LOAD` 加 SD 回退；`BB/RUNNER` 解释器探测（无 busybox ⇒ 退化为 `sh`）；`pkill` 走 busybox |
| `probe`（修复后） | `lutload:1`；6 工具全在；`luts_count:10`；双端 md5 `c2c04f2db529a69dce63eb1ba3f82a35` |
| `status` | `{"ok":true,"guard":0,"current":"Kodak_Portra_400","sel":1,…}` |
| `apply _identity --dry` | **通过**：落点 `0x8f800000` + cmasafe 四查全过（范围/对齐/黑名单/全零 20480B）+ `RC=0`，**零写入** |
| `lut_backend.py --selftest` | 8/8 PASS（修复后复跑） |

★ **调用口径修正（实测）**：相机**没有** PATH 上的 `busybox`（只在 `/opt/usr/nx-ks/busybox`）；`/bin/sh` 是 bash。
本文所有示例已改为 `/opt/usr/nx-ks/busybox sh …`；直接 `sh …` 亦可。

★ **写表前置仍成立**：cmapick2 末行告警「有 2 个候选落点 —— 不要尝试，先退出拍摄态让 ISP 释放」，且本次报的落点是**区起点 `0x8f800000`**（10-09 成功那次为 `0x8f81e000`）⇒ 序 3-4 写表须：相机进**菜单界面** + **先对焦一次**（抢回态）+ 落点口径裁决后再执行。

---
*生成：2026-10-16 · 后端实现 + 契约自测（离线）；上机首验 probe/status/--dry 已通过；写表回归（U7 序 3-8）待放行。*
