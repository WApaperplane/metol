# 历史归档 / Archive

> ⚠ **这些文档的结论可能已被后续调查推翻。**
> 取结论前，请先对照 [`../current/ERROR_CORRECTIONS_2026-10-07.md`](../current/ERROR_CORRECTIONS_2026-10-07.md)
> 与 [`../current/HANDOVER_2026-10-16.md`](../current/HANDOVER_2026-10-16.md)。

归档共 **60 份**，分两批：2026-10-07 一次（10-05/10-06 的阶段性成果）、**2026-10-18 一次**（见文末 §2）。

## 为什么保留

这些是 2026-10-05 / 10-06 的阶段性成果与调查报告，**记录了当时的推理过程**，
对理解"为什么走过某些弯路"仍有价值。但**其中若干结论是错的**，例如：

| 文档里的旧结论 | 实际情况 | 修正出处 |
|---|---|---|
| mod_gui `key_down_callback` 只认 **13 键** | 实为 **4 keysym**（Super_L/Super_R/Menu/XF86PowerOff）| ERROR_CORRECTIONS C1/C2 |
| `p6`/`p13` 是**主/备份同一内核** | 实为**两个不同构建**（#7 vs #1183），运行 p6 | ERROR_CORRECTIONS C6 |
| p7 里**没有任何 EP 物理基址字面量** | 实有 **342 个 EP 寄存器访问** | ERROR_CORRECTIONS C3 |
| p13（`rImage`）= 内核备份 | — | ERROR_CORRECTIONS C6 |
| "1.13 固件"是新版本 | v1.13 == v1.12，仅版本字符串差 1 字节 | ERROR_CORRECTIONS C8 |

## 内容清单

- `2026-10-05` 系列：固件层框架、p7 分析、SLP、SMA、BC 路径挖掘、魔灯可行性、综合报告
- `2026-10-06` 系列：3D LUT 写入通路打通、EP 驱动状态、libudd5 API 图、功能设计与矩阵、各类工作/评估报告
- `_2026-10-06_purged/`：2026-10-06 当晚即已作废的 3D LUT 探索文档（更早一轮的已否证结论）

## 完整历史

如需当时的完整上下文，见 git 历史（归档前的路径均为 `docs/<文件名>`）。

---

## 2. 2026-10-18 批次（28 份）

清理原则：**只在 `current/` 留「还能据以决策」的文档**。以下四类归档 ——
正文一字未改，保留当时的推理原貌。

| 类别 | 文件 | 为什么归档 |
|---|---|---|
| 旧交接 | `HANDOVER_2026-10-07 / 10-11 / 10-12` | 已被 `current/HANDOVER_2026-10-16` 取代 |
| 旧任务流 | `TASKFLOW_2026-10-09 / 10-10 / 10-12` | 已被 `current/TASKFLOW_2026-10-16` 取代 |
| 一次性执行记录 | `OFFLINE_TRACK_SUMMARY` `OFFLINE_VERIFICATION` `TIER1_AND_TIER3_OFFLINE` `QEMU_S4_AND_ENV_CLEANUP` `QEMU_S5_OFFLINE_USERSPACE` `UNBLOB_WSL_QEMU` `ST_RE_AND_REPRO` `WORKFLOW_PLAN` `AUDIT_2026-10-07` `D1_U11_STATIC_ATTACK` `D7_NXFILMUI_CJK_REBROADCAST` `D8_FORK_PREP` `STRATEGY_2026-10-07` `U2_UI_DISPLAY` `UI_PAGES_OFFLINE_RENDER` | 当日执行日志，结论已被总结吸收 |
| 被取代的路线设计 | `NATIVE_UI_DESIGN_2026-10-07` `NATIVE_UI_DESIGN_FULL_2026-10-11` `NATIVE_UI_ROADMAP_2026-10-15` `UI0_HOST_FEASIBILITY_2026-10-13` | 原生 UI（EFL）主线已被 **NXUI（Nuklear）** 取代 |
| 被取代的数据口径 | `RECIPES_BATCH2_2026-10-11` | 95 条 → 现 **68 条**，权威源是 `scripts/filmlab/recipes.json` |
| 被取代的调查 | `3DLUT_DEEP_DIVE_2026-10-07`（中英） | 表格式终解在 `current/3DLUT_TABLE_FORMAT_2026-10-08` |

> 另有 **24 份仍留在 `current/`** 的技术文档只加了「本文结论已被取代」横幅（不归档，
> 因为它们承载的**证据与过程**仍需可查）。清单见 `../README.md` §5。
