# 离机轨 D1–D8 执行总结（2026-10-08）

> 用户指令：**「完成当前设计的离机工作流」** ⇒ 按 `WORKFLOW_PLAN_2026-10-08.md` §2
> 把 **D1–D8 八项全部执行**。**全程离线，未触碰相机**。
> 执行方式：DP2/D3/D4/D5 派并行子任务；**D1/D6/D7/D8 主控直做**。

---

## 0. 一句话结论

> **八项全部落地**（其中 D2/D3 由并行子任务完成，本文件给索引与结论摘要）：
> **一项推翻旧结论**（D1：U11 旧入口被证伪）、**两项证伪旧假设 + 越过目标线**
> （D4 名字"非整串存储"被证伪、D5 覆盖率 44.16%→63.03%）、
> **一项改了产品代码并实测**（D7：nxfilmui v4 中文可用，`VERDICT=PASS`）、
> **一项收口资产风险**（D6：两个危险样本隔离 + MANIFEST 三处更正）、
> **一项准备拆仓**（D8：VERSION/LICENSE/ATTRIBUTION/CI 落地，CI `PASS`）。

---

## 1. 状态总表

| # | 待办 | 状态 | 主要产物 | 验收判据达成 |
|---|---|---|---|---|
| **D1** | U11 3D LUT 表格式静态攻坚 | ✅ | `docs/current/D1_U11_STATIC_ATTACK_2026-10-08.md`、`raw8/p7/u11_static.py` + `.txt`、`raw8/p7/disasm/*.bin` | ✅ 给出**可证伪假设**（槽 `0x4D00` = 60 B 头 + 17³×4；中点偏色三假设）+ 类归属结论 |
| **D2** | 原生 UI 五页离线预渲染 | ✅ | `UI_PAGES_OFFLINE_RENDER_2026-10-08.md`、`raw8/repro/ui_page_p{1..5}.png`、`test_server/filmlab/src/ui_pages_render.c` | ✅ 五页 720×480、**中文零 tofu**、70 次 `font_set`；★ **降级绘制**（真实 `elm_*` 控件待 U2） |
| **D3** | `libfirmware-upgrade.so` 校验链 | ✅ | `FW_UPGRADE_VERIFY_CHAIN_2026-10-08.md`、`raw8/fw/upgrade_chain/` | ✅ 校验点 C1–C8 + 入口 E1–E7；★ **无签名**；★★ **重打包 SLP 在校验层不会被拒** |
| **D4** | U02 MCB 命令全表 | ✅ | `docs/current/MCB_COMMAND_ENUM_TABLE_2026-10-08.md`、`raw8/repro/mcb_command_enum_table.txt` | ✅ **8 域 68 条**全表（旧采样 40 → +28，零冲突） |
| **D5** | U01 覆盖率 → 60%+ | ✅ | `docs/current/P7_CODE_MAP_COVERAGE_2026-10-08.md`、`test_server/isp/p7_extend_map_v2.py`、`raw8/p7/p7_extend_map_v2.tsv` | ✅ 旧口径 **67.08%**、去重口径 **63.03%**（均 > 60%） |
| **D6** | 资产卫生收口 | ✅ | `raw8/p7/quarantine/`、`raw8/fw/quarantine/`（各含 README）、`raw8/emmcbak/MANIFEST.txt`（更正） | ✅ 三项全做（隔离 + 更正 + 截断包决策） |
| **D7** | nxfilmui 反哺 CJK 结论 | ✅ | `nxfilmui.c`(v4) + `nxfilmui_v4.arm`、`nxlabel_probe.c`、`docs/current/D7_NXFILMUI_CJK_REBROADCAST_2026-10-08.md` | ✅ 同款序列实测 **PASS**（正对照出字 / 负对照零墨） |
| **D8** | 拆仓准备 | ✅ | `VERSION`、`LICENSE`、`ATTRIBUTION.md`、`.github/workflows/scripts-ci.yml`、`docs/current/D8_FORK_PREP_2026-10-08.md` | ✅ CI `RESULT: PASS`；8 步中 4 步已落、4 步待授权 |

---

## 2. 逐项要点（只记"会改变决策"的）

### ★★ D1 —— 旧入口推翻，新入口改向
- **撤销**：`0x803837D0`（"四缓冲选择器"）/ `0x80383800`（"消费函数"）。
  主判据（穷举、不依赖模型）：**全镜像 39499 BL + 31 BLX 目标里都没有它们**，且**不作为 32 位指针出现**。
  旁证：Ghidra 判该段为非函数（但 Ghidra 在此区**有漏识别**，故只作旁证）。
- **真引用面**：两张数据区指针表 `0x80382B00`（12 项）/ `0x80382C5C`（6 项）；
  真消费函数 **`FUN_003829a4`** = 算 BV → 按档位从表选指针 → 写 `[obj+0xd8]`（档位 1..12）。
- **可证伪假设 H-A**：缓冲槽 = `0x4D00` = **19712 B = 60 B 头 + 17³×4 (19652)**。
- **中点偏色**三假设：H-C 通道序/字节序错配｜H-D `0x8000` 非几何中点（12 位左对齐）｜H-E 第 4 字节非 alpha。
- ★ **新入口**：`0x38xxxx` 区**无 vtable 方法** ⇒ 应改从 `CBackend_3dlut*` / `CMaterial_NX1_*_3dlut_*`
  类方法（`0x11xxxx` / `0x19xxxx`）切入 —— 那才是"把表交给 ISP"的代码。

### ★ D2 —— 五页出图（**降级绘制**，已诚实标注）
- 5 张 720×480 PNG（`raw8/repro/ui_page_p1..p5.png`），**中文零 tofu**，全流程 **70 次 `font_set`**；逐页 `ink` 11321–30139。
- ★★ **限定**：用 `rect` + `text` 手工复现五页**信息结构**，**不是**真实 `elm_*` 控件外观 ——
  离线 chroot 里 elementary 初始化链不可稳定通过 ⇒ **"控件是否可用"必须留给上机轨 U2**。
- ★ 顺带得到一条**布局数值证据**：P2 的 7 行 × 52 px = 364 px，在 480 高屏（扣掉 header/statusbar）内**刚好放得下**
  ⇒ "机身单屏可容纳全部 7 维"有据。

### ★★ D3 —— 升级校验链：**重打包 SLP 不会被拒**
- ★ **无签名、无证书校验**；机型校验 = 16 B `project` 串（`NX500`）；
  版本校验只发生在 **App / `dfmsd` 层**，且**只拦降级**、不拦同版本。
- ⇒ **「改内容 + 重算该段 JAMCRC + 保持 len/offset/flags/project」的 SLP，在 SLP 校验层不会被拒。**
- ★★ **入口强度不同（关键）**：相机 UI 走 `flag=1` ⇒ **逐段 JAMCRC 真校验**；
  而 **`st firmware up` 无 CRC、无版本比较**（它直接进 `fw_start_upgrade`，内部 `flag=0`）。
  ⇒ 做 U4 最小实验时：`st firmware up` 更宽松，但**不能用它"通过"来证明官方 UI 路径也会通过**。
- 校验点清单 **C1–C8**（`fw_validate` / `fw_upgrade_crc32` / `fw_cmp_bl_version` …）+ 入口 **E1–E7**；
  `verify_slp.py` 对官方 1.13 复算 **10 段 JAMCRC 全 PASS**。
- ★★ **重打包的硬约束（必须保持不动）**：`flags` 是**魔数**
  `MASK(i) = (0xffffffff >> (4*(i%8))) | (0x87654321 << (4*(i%8)))`；`num_image ∈ [1,15]`；
  `record[0].flags == 0xffffffff`。**动 flags 会被 `[IMG-MAGIC]` 拒**，动 project 会被 `[PROJECT]` 拒，
  CRC 算错会被 `[IMG-CRC32]` 拒 —— 三个拒点即"最小实验"的定位依据。
- ★ 补充证据：该 .so 的 **81 个导入符号里零密码学函数**，全串无 sign/cert/hash/rsa/aes/sha；
  `fw_validate` 只读"头 64 B + 记录表"，**从不读文件尾** ⇒ 结构上也不可能有尾部签名块。

### D4 —— 枚举表不是数组，是一个导出函数
- 表 = `capture_command_string`（`libcapture-fw-prod.so` VA `0x511e0`，2152 B，二分 if-switch），
  经 `OperateCapture@0x46b58` → `mcb_debug_set_command_name_function` 注册进 MCB。
- **68 条 / 8 域**；名字**整串存储** ⇒ 此前"名字不是整串存的"猜测**证伪**；唯一空洞 `LENS_ 0x506–0x508`。

### D5 —— 旧口径有重复计入
- **旧 48.21%** 里 667 条是同一地址的重复（`ext` 用十进制键、`cls` 用 `0x` 键 ⇒ 永远不相等）⇒ 去重基线 **44.16%**。
- 主力 **广义 RTTI**（typeinfo vptr 签名校验，565 → **1047 类**，覆盖全镜像）⇒ 旧口径 **67.08%** / 去重 **63.03%** / 含推断 78.71%。
- ★ 纠正：v1 记的"②Thumb 序言"**实为 ARM 序言**（p7 基本无 Thumb）。

### D6 —— 两个危险样本 + 一份更正
- `p7_patched.bin`（复位期 DACR 写入被改成未定义编码）→ `raw8/p7/quarantine/…DO-NOT-FLASH`；
- `NX500_FW_v1.12.zip`（截断 4.4 MB）→ `raw8/fw/quarantine/…TRUNCATED-DO-NOT-USE`；
  ★ **决策 = 不重下**（C8 已证 v1.13 ≡ v1.12，只差版本字符串 1 字节 ⇒ v1.12 独立价值为 0）；
- `MANIFEST.txt` 就地更正 3 处（M1 p6/p13 非主备；M2 p3 非全零；M3 `p7_full` = 官方 p7 + 尾部补零），
  并补精确长度：**BL 有效 0xb8427c / SLP 记录 len 12,075,648**。

### ★ D7 —— 产品代码真的改了，且离机验过
- `nxfilmui.c` v3→v4：新增 **`apply_label_font()`**、**`g_ascii` 默认 1→0（中文可用）**、新增 `ascii` 降级开关；
  产物 `nxfilmui_v4.arm`（64,988 B，NEEDED 自检通过、未静态绑定 `ecore_event_handler_add`）。
- **`nxlabel_probe`**：把 v4 的**同款调用序列**（`SDIC_GP_US` + `26 px`）搬到 evas buffer 引擎 ⇒ **PASS**
  （11 项出字，含 `MonoWarm 暖调黑白`；**负对照未设字体 = 0×0、零墨**）。
- `check_abi.py` 新增**第三个白名单来源** `cjk_render.arm`（相机 rootfs 里跑通过的 ELF）⇒ 29/33 OK。

### D8 —— 拆仓 8 步：4 步已落
- 已落：**VERSION**（2.88.0-metol.1，含"相机端路径保持 `/opt/usr/nx-ks/`"硬约束）、
  **LICENSE**（AGPL-3.0 全文）、**ATTRIBUTION.md**（血缘 + 发布前必做）、**CI 门控**（`PASS: 0 fail / 1 warn`）。
- 待授权：建 org/仓、拆目录、打 tag、旧 272 MB `.git` 取舍（迁移命令见 `D8_FORK_PREP_2026-10-08.md` §3）。

---

## 3. 本轮新增资产索引

| 类别 | 文件 |
|---|---|
| **报告**（`docs/current/`） | `D1_U11_STATIC_ATTACK`、`UI_PAGES_OFFLINE_RENDER`、`FW_UPGRADE_VERIFY_CHAIN`、`MCB_COMMAND_ENUM_TABLE`、`P7_CODE_MAP_COVERAGE`、`D7_NXFILMUI_CJK_REBROADCAST`、`D8_FORK_PREP`、`OFFLINE_TRACK_SUMMARY`（本篇） |
| **发布前文件**（仓库根） | `VERSION`、`LICENSE`、`ATTRIBUTION.md`、`.github/workflows/scripts-ci.yml` |
| **脚本** | `raw8/p7/u11_static.py`、`raw8/p7/lut_ref_scan.py`、`test_server/isp/p7_extend_map_v2.py`、`test_server/filmlab/src/{nxlabel_probe.c,build_nxlabel_probe.sh,ui_probe.c}`、`raw8/qemu/nxlabel_probe_run.sh`、`raw8/fw/upgrade_chain/*.py` |
| **证据** | `raw8/p7/u11_static_report.txt`、`raw8/p7/disasm/*.bin`、`raw8/p7/p7_extend_map_v2.tsv`、`raw8/repro/mcb_command_enum_table.txt`、`raw8/repro/nxlabel_probe.png`、`raw8/repro/ui_page_p*.png`、`raw8/fw/upgrade_chain/` |
| **隔离区** | `raw8/p7/quarantine/`、`raw8/fw/quarantine/`（各含 README） |

---

## 4. 与门控 / 上机轨的衔接（本轮改动会影响这些）

| 门控 | 本轮影响 |
|---|---|
| **G2 / G2a** | D1 给出了**四条可只读验证的判据**（槽头/网格/档位差/中点语义）⇒ 一次上机可同时回答 H-A~H-E；若 `0x810FD100` 读得到 ⇒ `lutmod` 补丁**永久弃用** |
| **G3**（原生 UI 上机） | D2 的五页 PNG + **D7 的字体设定**共同构成"每处文本都设了字体"的进场条件 |
| **G4**（允许改 p7） | D3 的校验链结论是 U4 的前置（详见 `FW_UPGRADE_VERIFY_CHAIN_2026-10-08.md`）|
| **U1**（合并只读上机） | D1/D4/D5 都产出了"上机可一次验完"的候选判据，可与 U1 的 5 问合并 |

---

## 5. 未完成 / 风险（如实记录）

| # | 项 | 状态 |
|---|---|---|
| 1 | **相机上机验证**（U1–U5 全部） | ⛔ 本轮**只做离机**，一项未上机（符合指令） |
| 2 | **D8 的建仓/push** | 🔶 需授权（未执行，避免在未授权下创建公开仓） |
| 3 | **`nxfilmui` 首次渲染延迟**（10.7 MB 字体在单核上的首帧代价） | 🔶 离线不可判，属 U3 |
| 4 | **D6 的 `EV_MOBILE.sh` 死循环版** | 🔶 **故意不动**（属产品决策）⇒ 仍列 preflight §5-2 的 P0 检查项 |
| 5 | **p8 全零之谜** | 🔶 仍开放（分区真空 / 读错 / 读保护 未区分） |
| 6 | **未 commit** | 🔶 本轮改动未提交 git（用户未要求）；`raw8/`、`.uploads/` 已被 `.gitignore` 覆盖 |

---

*生成：2026-10-08 · 全程离线 · 未触碰相机 · 分支 `nx-ks2`*
