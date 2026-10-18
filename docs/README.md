# Metol 文档索引（旧称 NX-KS2 / NX-WA）

> 更新：**2026-10-18**（本次做过一次清理，见 §5）· 分支：`nxwa`
> 本目录按**时效**分区，避免"旧结论淹没新结论"。

## 目录结构

```
docs/
├── README.md        ← 本文件（索引）
├── current/         ← 现行权威：据此做决策
├── archive/         ← 历史归档：结论可能已被推翻
└── evidence/        ← 逆向证据片段（可复现的原始数据/脚本）
```

---

## 1. 先读这四份

| 文档 | 定位 |
|---|---|
| [`HANDOVER_2026-10-16.md`](current/HANDOVER_2026-10-16.md) | ★★★★★ **总入口**：约定、死路、门控、执行序 |
| [`ONDEVICE_SOP_2026-10-16.md`](current/ONDEVICE_SOP_2026-10-16.md) | ★★★★★ **上机日 SOP**：就位 / 判据 / 回退 / 证据落点（§10 LUT 部分已被取代，见文首横幅） |
| [`../README.md`](../README.md) | 对外介绍、安装、功能（★ 用户视角从这里进） |
| [`TASKFLOW_2026-10-16.md`](current/TASKFLOW_2026-10-16.md) | 任务流与执行记录 |

---

## 2. 现行结论（10-15 ~ 10-18）

### 2.1 LUT：运行态换表（★ 当前主线）

| 文档 | 定位 |
|---|---|
| [`LUT_RETARGET_LIVE_2026-10-18.md`](current/LUT_RETARGET_LIVE_2026-10-18.md) | ★★★★★ **运行态换表闭环**：4 字节登记表 + 写槽 + 半按；View/Still 双链路独立；双向回滚 |
| [`LUT_REGTAB_READ_2026-10-18.md`](current/LUT_REGTAB_READ_2026-10-18.md) | ★★★★ **Cfg 位定义钉死** + 三张登记表上机回读 22/22 |
| [`CUBE2LUT_2026-10-18.md`](current/CUBE2LUT_2026-10-18.md) | ★★★★ **机身 `.cube` 转换器**：格式契约 + 逐字节对照 + `e` 记法 bug |
| [`LUT_UI_2026-10-18.md`](current/LUT_UI_2026-10-18.md) | ★★★★ **LUT 面板**：三入口、三个安全设计、两个实测 bug |
| [`NXUI_FOCUS_HANDOFF_2026-10-18.md`](current/NXUI_FOCUS_HANDOFF_2026-10-18.md) | ★★★★ X11 焦点不归还缺陷与回归判据 |
| [`NXUI_NUKLEAR_2026-10-17.md`](current/NXUI_NUKLEAR_2026-10-17.md) | ★★★★ NXUI 安装与验证（10-17 版） |
| [`UI_FRAMEWORK_ALTERNATIVES_2026-10-17.md`](current/UI_FRAMEWORK_ALTERNATIVES_2026-10-17.md) | ★★★★ 换 UI 框架的可行性分层结论 |

### 2.2 上机、交付与设计（10-15 ~ 10-16）

| 文档 | 定位 |
|---|---|
| [`DELIVERY_RESUME_AUDIT_2026-10-16.md`](current/DELIVERY_RESUME_AUDIT_2026-10-16.md) | P5 投递失败的恢复链审计（LUT 后端部分已退役，P5 分析仍有效） |
| [`ONDEVICE_NATIVE_LABEL_RESULT_2026-10-16.md`](current/ONDEVICE_NATIVE_LABEL_RESULT_2026-10-16.md) | 原生标签真机 POC（11 字节） |
| [`T2_PRESET_PROTOCOL_2026-10-16.md`](current/T2_PRESET_PROTOCOL_2026-10-16.md) | `nxwa.preset/1` 协议设计（**未实施**） |
| [`M2_RECIPE_NAME_DESIGN_2026-10-16.md`](current/M2_RECIPE_NAME_DESIGN_2026-10-16.md) | 配方名 `.mo` 文案层设计（**未落地**） |
| [`T2_DELIVERY_REVISION_2026-10-15.md`](current/T2_DELIVERY_REVISION_2026-10-15.md) | 投递链修订（去 restart，只就位） |
| [`MEM_INJECTION_EVAL_2026-10-15.md`](current/MEM_INJECTION_EVAL_2026-10-15.md) | 内存注入路线评估（poker 退出主候选） |
| [`A2_READBACK_VERDICT_2026-10-15.md`](current/A2_READBACK_VERDICT_2026-10-15.md) | A2 刷机状态逐字节裁决 |

---

## 3. 技术基线（不随版本变，可长期引用）

### 3.1 p7 / 3D LUT

| 文档 | 定位 |
|---|---|
| [`3DLUT_TABLE_FORMAT_2026-10-08.md`](current/3DLUT_TABLE_FORMAT_2026-10-08.md) | ★★★★★ **表格式**：`4913×4B`、索引、槽步长 `0x4D00`、槽池布局 |
| [`3DLUT_APPLY_PATHS_2026-10-08.md`](current/3DLUT_APPLY_PATHS_2026-10-08.md) | ★★★★★ **五条应用线路** + 寄存器写序（`+0x00c`/`+0x010`/`+0x008`） |
| [`3DLUT_CUBE_IMPORT_TOOL.md`](current/3DLUT_CUBE_IMPORT_TOOL.md) | `.cube` 导入工具 `nx3dlut.py` 用法 |
| [`3DLUT_API_GUIDE.md`](current/3DLUT_API_GUIDE.md) · [EN](current/3DLUT_API_GUIDE_EN.md) | LUT API 参考（**官方 API 路线，非当前主线**，文首有横幅） |
| [`P7_3DLUT_PATHS_2026-10-07.md`](current/P7_3DLUT_PATHS_2026-10-07.md) | 三条 C++ 路径全解（RTTI + vtable） |
| [`P7_DISPATCH_AND_LSC_2026-10-07.md`](current/P7_DISPATCH_AND_LSC_2026-10-07.md) | 跳转表机制纠正 + 镜头阴影描述符 |
| [`P7_EFS_MODULE_2026-10-08.md`](current/P7_EFS_MODULE_2026-10-08.md) | EFS 模块逆向（`nand_write` 实为 MMIO） |
| [`P4_HW_WINDOW_CONFIRMED_2026-10-11.md`](current/P4_HW_WINDOW_CONFIRMED_2026-10-11.md) | 3DLUT 硬件窗口两态之谜结案 |

### 3.2 PW / 属性总线

| 文档 | 定位 |
|---|---|
| [`PW_ID_MAP_FULL_2026-10-10.md`](current/PW_ID_MAP_FULL_2026-10-10.md) | ★★★★★ **PW id 全图** + 为什么外部够不到 R/G/B/HUE |
| [`PW_PARAM_CHANNEL_2026-10-08.md`](current/PW_PARAM_CHANNEL_2026-10-08.md) | ★★★★★ 三通道上机定论（只有"参数"通道有效） |
| [`PW_APPLY_TRIGGER_CHAIN_2026-10-10.md`](current/PW_APPLY_TRIGGER_CHAIN_2026-10-10.md) | 「画面向导→自定义1」p7 侧触发链 |
| [`ATTR_BUS_MCB_2026-10-09.md`](current/ATTR_BUS_MCB_2026-10-09.md) | ★★★★★ 属性总线传输层全解 |
| [`MCB_PROTOCOL_AND_ST_TABLE_2026-10-08.md`](current/MCB_PROTOCOL_AND_ST_TABLE_2026-10-08.md) | MCB 协议档案 + `st` 全表 |
| [`MCB_COMMAND_ENUM_TABLE_2026-10-08.md`](current/MCB_COMMAND_ENUM_TABLE_2026-10-08.md) | MCB 命令号枚举全表 |
| [`PW_ONECLICK_DESIGN_2026-10-09.md`](current/PW_ONECLICK_DESIGN_2026-10-09.md) | 一键滤镜设计（PW 直推版） |

### 3.3 系统 / 刷机 / App

| 文档 | 定位 |
|---|---|
| [`NX500_ARCHITECTURE.md`](current/NX500_ARCHITECTURE.md) | ★★★★★ 系统与软件架构（实机抓取） |
| [`SLP_CONTAINER_FORMAT_2026-10-08.md`](current/SLP_CONTAINER_FORMAT_2026-10-08.md) | ★★★★★ SLP 容器格式全解（JAMCRC，无签名） |
| [`FW_UPGRADE_VERIFY_CHAIN_2026-10-08.md`](current/FW_UPGRADE_VERIFY_CHAIN_2026-10-08.md) | 固件升级校验链 |
| [`ILAUNCHER_FIRMWARE_FLASH_2026-10-07.md`](current/ILAUNCHER_FIRMWARE_FLASH_2026-10-07.md) | iLauncher 刷机机制（不直刷相机） |
| [`CAMERA_APP_STRUCTURE_2026-10-07.md`](current/CAMERA_APP_STRUCTURE_2026-10-07.md) | `di-camera-app` 结构盘查 |
| [`CAMERA_MENU_ARCHITECTURE_2026-10-07.md`](current/CAMERA_MENU_ARCHITECTURE_2026-10-07.md) | ★★★★★ 菜单渲染档案 + **证明 p7 无 UI** |
| [`DICAM_PATCH_INSTALL_PATHS_2026-10-12.md`](current/DICAM_PATCH_INSTALL_PATHS_2026-10-12.md) | App 补丁安装路径与 Release 布局 |
| [`SHELL_TO_APP_ISOMORPHISM_2026-10-12.md`](current/SHELL_TO_APP_ISOMORPHISM_2026-10-12.md) | shell → App 官方通道替换 |
| [`UI_R1A_PW_DATAFLOW_2026-10-15.md`](current/UI_R1A_PW_DATAFLOW_2026-10-15.md) · [`R1B`](current/UI_R1B_MENU_ABI_2026-10-15.md) · [`R1C`](current/UI_R1C_APPLY_TRANSACTION_2026-10-15.md) | PW 菜单数据流 / 记录 ABI / 应用事务 |
| [`UI_R0_TARGET_INVENTORY_2026-10-15.md`](current/UI_R0_TARGET_INVENTORY_2026-10-15.md) | 原版 App 样本与哈希台账 |

### 3.4 方法与纪律

| 文档 | 定位 |
|---|---|
| [`GATE_FLOW_2026-10-08.md`](current/GATE_FLOW_2026-10-08.md) | 门控任务流（三态 PASS/FAIL/BLOCKED + 证据契约） |
| [`ERROR_CORRECTIONS_2026-10-07.md`](current/ERROR_CORRECTIONS_2026-10-07.md) | 历史纠错 C1–C9 |
| [`PATCH_SURFACE_REVIEW_2026-10-12.md`](current/PATCH_SURFACE_REVIEW_2026-10-12.md) | 补丁化空间评估（L0–L5 分层 + 判据 J1–J5） |
| [`MOD_DECISION_P7_APP_2026-10-12.md`](current/MOD_DECISION_P7_APP_2026-10-12.md) | p7 与 App 修改决策记录（ADR） |
| [`FIRMWARE_FEATURE_SPACE_2026-10-08.md`](current/FIRMWARE_FEATURE_SPACE_2026-10-08.md) | 固件改写功能空间 + 架构天花板 |

> 其余 10-07 ~ 10-14 的逆向记录仍在 `current/`（未归档），多为过程记录，**不作判据来源**；
> 需要时按文件名在目录里找，或到 `archive/` 查更早的。

---

## 4. 已作废结论速查（看到这些就当没看见）

| 旧结论 | 现状 | 依据 |
|---|---|---|
| View 与 Still 共用池 ⇒ **软件层无法隔离** | ❌ 可隔离：池共用，但**三张登记表是分开的** | `LUT_RETARGET_LIVE_2026-10-18` |
| **成片直灌 LUT 是死路** | ❌ 只有 **LUT1 直灌**无效；改 `Still6` 成片照样换表 | 同上 |
| **LUT1 + `lutsentinel` 守护**是预览主线 | ⛔ 已退役（抢时序 / 只覆盖预览 / 不抗抢回） | 同上 |
| 实机装载源是 **A12 标准槽** | ❌ 是 **A17 `0x81115200`**（肤色表） | 同上 |
| `bit12` 是 SelLUT 选择位 | ❌ **`bits[5:4]`** 才是；`0x100` 与 `0x1100` 都是 SelLUT=0 | `LUT_REGTAB_READ_2026-10-18` |
| 出厂有 **identity / 中性**表可作基准 | ❌ 全是风格表 | `U6_ONMACHINE_RESULT_2026-10-09` |
| `lutpick.sh off` = 关闭 LUT | ❌ 是加载 identity ≠ 关闭；关闭走 `factory_restore` / `lut.sh off` | `LUT_UI_2026-10-18` |
| **`mod_gui`** 是 mod 主界面 | ❌ 已被 **NXUI（Nuklear）** 取代 | `NXUI_NUKLEAR_2026-10-17` |
| 配方 **95 条** | ❌ 现 **68 条**，权威源 `scripts/filmlab/recipes.json` | 仓库 |
| **原生 UI（EFL）** 是方向 | ⛔ 全屏自绘实测是墙；小面板（NXUI）可行 | `UI_FRAMEWORK_ALTERNATIVES_2026-10-17` |
| 改 unit / 依赖可开机重读 | ⛔ 本机是用户态恢复机型，systemd 不重读 unit（P5 死路） | `HANDOVER_2026-10-16` |
| `setvar` 可写 PW 变量 | ⛔ 禁区：id 运行时注册，盲扫曾写死 capture 服务 | `ERROR_CORRECTIONS_2026-10-07` |

---

## 5. 本次清理做了什么（2026-10-18）

- **归档 28 份**：旧交接（10-07 / 10-11 / 10-12）、旧任务流（10-09 / 10-10 / 10-12）、
  一次性离机与 QEMU 执行记录、被 NXUI 取代的原生 UI 设计（10-07 / 10-11 / 10-13 / 10-15）、
  被 68 条取代的配方批次记录、10-07 深度调查（中英）。
  → `docs/archive/`，正文未改，保持历史原样。
- **加横幅 24 份**：结论已被取代但仍需可查的技术文档（T1/T3/T4/T5/T6、`3DLUT_API_GUIDE`、
  `P7_RECLAIM`、`U6`、`LUT_*_2026-10-17/18`、`MODGUI_*`、`FEATURE_MATRIX_*` 等），
  文首统一为「⚠️ 2026-10-18 文档清理：本文结论已被取代」+ 指向现行文档。
- **重写本索引**：从 122 条平铺改为「入口 → 现行 → 基线 → 作废速查」四段。
- **同步根 README**：3D LUT 一节按 10-18 结论重写（中英双语）。

> 归档文件里的相对链接（指向 `current/` 的）会失效 —— 需要时用文件名在本目录 `current/` 里找。
