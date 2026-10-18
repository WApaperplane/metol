# NX-KS2 逆向进度总览 / 2026-10-08

> ⚠️ **2026-10-18 文档清理：本文结论已被取代。** 总览停在 10-08，死路清单与能力结论已被后续实测多次改写。
> 现行结论见 [`HANDOVER_2026-10-16.md`](HANDOVER_2026-10-16.md)。


> **定位**：**单文件收口**全部逆向成果 —— 一张总表看清"解了什么 / 卡在哪 / 什么是死路"。
> 每条结论的详细论证在 `docs/current/` 的专题文档里（本文每节都给指针）。
> 状态口径：**✅ 实机验证**｜**◐ 离线解出/推理**｜**⛔ 已证伪（勿再走）**｜**❓ 未解**。
>
> 配套阅读顺序：本文（全局）→ `GATE_FLOW_2026-10-08.md`（现在能不能动手）→ 专题文档（细节）。
> ★ 读任何旧结论前，先看 `ERROR_CORRECTIONS_2026-10-07.md`（C1–C9 纠错）+ 本文 §8 死路清单。

---

## 0. 一页速览

| 领域 | 进度 | 最值钱的一句结论 | 详细文档 |
|---|---|---|---|
| 系统 / 硬件层 | ✅ 主体清晰 | `/dev/mem` 只到得了内核 memory map 内的 RAM；**p7 占用的 DRAM 也读不到** ⇒ 读 p7 一律走驱动 | §1 |
| p7 固件静态 | ◐ 63%+ 覆盖 | 旧入口 `0x803837D0` **已证伪**；真消费函数 `FUN_003829a4`；表槽假设 `0x4D00` | `D1_U11_STATIC_ATTACK_2026-10-08.md` |
| 容器 / 升级链 | ✅ 全解 | **SLP 无签名，重打包不会被校验层拒**；`st firmware up` 连 CRC 都不查 | `SLP_CONTAINER_FORMAT`、`FW_UPGRADE_VERIFY_CHAIN` |
| 通信层 | ✅ 全解 | MCB 68 条命令（8 域）；`st` 表；iqr 184 ID；epmc 10 块 | `MCB_*`、`ST_RE_AND_REPRO` |
| 用户态接口 | ✅ 可写可验 | PW 模型 + **实时切换已通**；ISP 参数块 21 槽 × 2 通道可写 | §5 |
| 3D LUT | ✅ 写入通 / ❓ 表格式 | 用户态写入**实测改变画面**；4 组内置 LUT 在 p7 空间、Linux 永远读不到 | §5.3 |
| 原生 UI（EFL） | ◐ 就差显示 | 进程 / 主循环 / 环境全对，**但窗口不显示**（未解，见 §6） | `U2_UI_DISPLAY_2026-10-08.md` |
| 门控 | 1/5 放行 | 只放行 **L1**（用户态）；改 p7 被 G4 硬挡 | `GATE_FLOW_2026-10-08.md` |

**一句话总纲**：**"用户态 + ISP 参数块 + 3D LUT"这一整层已经打通且可复现；下一层（改 p7）技术上已备好、门控上被挡；原生 UI 只差最后一步"窗口为什么不显示"。**

---

## 1. 系统 / 硬件层

### 1.1 平台骨架

```
SoC：DRIMe5（双核）
├─ Linux 侧（ARM，Tizen，rootfs 只读 96% 满）—— di-camera-app 等全部用户态
└─ p7 侧（RTOS 固件，12,075,648 B，占 DRAM 高段 0x81xxxxxx）
   通信：drime5_ep（中断 149 万次实测量级）/ d5_sma（144 MB CMA @ 0x94000000）
```

| 项 | 结论 | 状态 |
|---|---|---|
| `/dev/drime5_ep` | **纯 mmap 设备**，`open` 零硬件初始化（源码证实）；10 个 EP 块的物理地址经 `ioctl(_IOR('h',100,…))` 权威取得，10/10 与历史实测吻合 | ✅ |
| `/dev/d5_sma` | 144 MB CMA 共享区 @ `0x94000000`，读写均实测 | ✅ |
| `d5_ipcc` | **空壳**：ioctl 返回 0 但不回填；`size=8` 编码直接 SIGILL ⇒ 不是跨核通道 | ⛔ |
| handle 墙 | 只对厂商库成立；直接 mmap 硬件**绕过 handle**（读+写均已实测） | ✅ |

### 1.2 ★ `/dev/mem` 四点对照（U1，2026-10-08 实机）

| 地址 | 性质 | 结果 |
|---|---|---|
| `0x94000000` | 阳性对照（Linux CMA） | ✅ 可读（3072 B，dd rc=0） |
| `0x2082b000` | 阴性对照（MMIO） | ❌ Bad address |
| `0x810fd100` | 问题本体：p7 LUT 缓冲 A | ❌ Bad address |
| `0x81115200` | 问题本体：p7 LUT 缓冲 B | ❌ Bad address |

- IPC 区 `0x20800000+` P0 子集 8 段（idx 5–12）**全 Bad address** ⇒ **IPC 属 MMIO，必走驱动**。
- ★★ **纠正旧结论**（旧判"'只有 MMIO 读不到'"不完整）：`/dev/mem` 只读得动**内核 memory map 内的 RAM**；
  **p7 占用的 DRAM 子区间同样读不到**（不在 Linux memory map 内）。
- ⇒ 判定 **G2b** ⇒ `lutmod`（把 LUT 缓冲搬到 Linux CMA `0x94000000–0xA6000000`）**从"可选"变"必需"**。
- 证据：`raw8/gates/u1/mem_compare.json`（G2 唯一输入，四点齐全）。

### 1.3 存储与分区

| 分区 | 结论 |
|---|---|
| `/` rootfs | ro，96% 满；**不可写** |
| `/opt/usr`（p14） | **rw，mod 唯一安全落点**（刷固件不覆盖）；★ **~2.1 GB 未备份（真洞）** |
| `/mnt/mmc` | exFAT（SD 卡）；FTP 根目录 = SD 卡根；exFAT **不保证 x 位** |
| p7 | 固件分区，12,075,648 B；三方 md5 一致（SLP img5 = 机上 = `p7_full.bin[:12075648]` = `5fc4824f5b6a6a3caca1f9104238b8ac`） |
| **p8（rtos_data）** | ★ **已定案**：`ro=0` + 写完成 0 次 + 写扇区 0（`/sys/class/block/mmcblk0p8/stat`；start=245761 size=102399≈50 MB）⇒ **从未被写入**（设计如此），不是损坏 |
| p9 / p10 / p11 | 未备份（缺口，见 §9） |
| boot0 / boot1 | ★ **绝不碰** |

- p7 侧 **EFS 模块** `FUN_000765b0`：`nand_write` 写的是 MMIO `0x85601000`，**不写 eMMC**（`P7_EFS_MODULE_2026-10-08.md`）。
- 固件身份：**C8 已证 v1.13 ≡ v1.12**（只差版本字符串 1 字节）⇒ 手头截断的 v1.12 独立价值为 0。

### 1.4 输入设备（U1 实机枚举，`raw8/gates/u1/input_map.json`）

| 设备 | 类型 | 关键码 |
|---|---|---|
| `event0` | GPIO 键盘 | 125/126 Meta、163/165 Next/Prev、177/178 PageDown/Up（全按下-释放成对） |
| `event1` | ADC 键盘 | **四向：72 UP / 75 LEFT / 77 RIGHT / 80 DOWN** |
| `event2` | 触摸 | MT protocol B（TRACKING_ID 27/28 + POSITION_X/Y + PRESSURE） |

★ **全集无 EV_REL** ⇒ 机身**不存在独立相对轴设备**；旋钮/波轮若存在，是被 drime5 驱动映射成 EV_KEY（铁律 111：穷举全 0 才敢说没有）。

---

## 2. p7 固件静态逆向

### 2.1 覆盖与结构

| 指标 | 数值 |
|---|---|
| 代码覆盖率 | 旧口径 **67.08%** / 去重口径 **63.03%** / 含推断 **78.71%**（v1 报的 48.21% 含重复计入，已纠正） |
| 类识别 | 广义 RTTI（typeinfo vptr 签名校验）565 → **1047 类**，覆盖全镜像 |
| 有效代码 | BL 有效段 `0xb8427c` |

- 工具：`test_server/isp/p7_extend_map_v2.py`、`p7_callgraph.py`、`p7_class_map.py`、`p7_code_map.py`、`Ghidra DumpELF.java`。
- ★ 纠正：旧记"Thumb 序言"**实为 ARM 序言**（p7 基本无 Thumb）。
- 跳转表机制已纠正：**ARM 索引表 ≠ veneer**（`P7_DISPATCH_AND_LSC_2026-10-07.md`）；镜头阴影（LSC）描述符已解。

### 2.2 ★ U11 静态攻坚（3D LUT 选择链，2026-10-08）

| 项 | 结论 |
|---|---|
| 旧入口 `0x803837D0`（"四缓冲选择器"）/ `0x80383800`（"消费函数"） | ⛔ **证伪**：全镜像 39499 BL + 31 BLX 目标里都没有它们，且不作为 32 位指针出现（穷举判据，不依赖模型） |
| 真引用面 | 两张数据区指针表 `0x80382B00`（12 项）/ `0x80382C5C`（6 项） |
| 真消费函数 | **`FUN_003829a4`** = 算 BV → 按档位从表选指针 → 写 `[obj+0xd8]`（档位 1..12） |
| 可证伪假设 H-A | 缓冲槽 = `0x4D00` = **19712 B = 60 B 头 + 17³×4 (19652)** |
| 中点偏色三假设 | H-C 通道序/字节序错配｜H-D `0x8000` 非几何中点（12 位左对齐）｜H-E 第 4 字节非 alpha |
| 新入口方向 | `0x38xxxx` 区**无 vtable 方法** ⇒ 改从 `CBackend_3dlut*` / `CMaterial_NX1_*_3dlut_*` 类方法（`0x11xxxx` / `0x19xxxx`）切入——那才是"把表交给 ISP"的代码 |

### 2.3 3D LUT 三条 C++ 路径（`P7_3DLUT_PATHS_2026-10-07.md`）

- 三条路径全部解出（RTTI + 3 个 vtable）。
- ★ **View 与 Still 独立** ⇒ 改 View 表**不影响照片**（安全的试验田）。

---

## 3. 容器 / 升级链

### 3.1 SLP 容器格式（全解，`SLP_CONTAINER_FORMAT_2026-10-08.md`）

```
[48 B 头] + [16 B tag] + [N × 24 B 记录表] + [N 段连续镜像]
唯一校验 = 每段 JAMCRC（zlib.crc32(b) ^ 0xFFFFFFFF）；★ 无签名
```

- 官方 1.13 用 `verify_slp.py` 复算 **10 段 JAMCRC 全 PASS**。
- ★★ **重打包硬约束（必须保持不动）**：
  - `flags` 是**魔数** `MASK(i) = (0xffffffff >> (4*(i%8))) | (0x87654321 << (4*(i%8)))`
  - `num_image ∈ [1,15]`；`record[0].flags == 0xffffffff`
  - **动 flags 被 `[IMG-MAGIC]` 拒；动 project 被 `[PROJECT]` 拒；CRC 算错被 `[IMG-CRC32]` 拒**——三个拒点即最小实验的定位依据。

### 3.2 升级校验链（`FW_UPGRADE_VERIFY_CHAIN_2026-10-08.md`）

| 项 | 结论 |
|---|---|
| 签名 / 证书 | ★ **无**（该 .so 81 个导入符号里零密码学函数，全串无 sign/cert/hash/rsa/aes/sha） |
| 机型校验 | 16 B `project` 串（`NX500`） |
| 版本校验 | 只在 App / `dfmsd` 层，且**只拦降级**、不拦同版本 |
| 校验点 | C1–C8（`fw_validate` / `fw_upgrade_crc32` / `fw_cmp_bl_version` …）+ 入口 E1–E7 |
| ★★ 入口强度差异 | 相机 UI 走 `flag=1` ⇒ **逐段 JAMCRC 真校验**；而 **`st firmware up` 无 CRC、无版本比较**（内部 `flag=0`）⇒ 更宽松，但**不能用它"通过"来证明官方 UI 路径也会通过** |
| 结构证据 | `fw_validate` 只读"头 64 B + 记录表"，**从不读文件尾** ⇒ 结构上也不可能有尾部签名块 |

⇒ **结论：「改内容 + 重算该段 JAMCRC + 保持 len/offset/flags/project」的 SLP，在 SLP 校验层不会被拒。**
⇒ U4 最小实验（等长、只改 1 字节、重算 JAMCRC）因此可行——但 U4/U5 尚未执行（见 §7 门控）。

### 3.3 刷机路径

- ★⛔ **NX 系无 PC 直连刷机协议**：iLauncher **不直刷相机**（只是把固件拷到 SD 卡，由相机自己发起升级）；FnA.dll 五参数签名 + 完整流水线已还原（`ILAUNCHER_FIRMWARE_FLASH_2026-10-07.md`）。
- ★ 安全网：**改 p7 = 画面异常但 telnet 仍活**（可救）。

---

## 4. 通信层

| 件 | 结论 |
|---|---|
| **MCB** | **68 条命令 / 8 域**全表（旧采样 40 → +28，零冲突）；表本体 = 导出函数 `capture_command_string`（`libcapture-fw-prod.so` VA `0x511e0`，2152 B 二分 if-switch）⇒ 名字**整串存储**（"名字不是整串存的"猜测被证伪）；唯一空洞 `LENS_ 0x506–0x508` |
| **`st` 表** | MCB 协议与 `st` 命令表已还原（`MCB_PROTOCOL_AND_ST_TABLE_2026-10-08.md`、`ST_RE_AND_REPRO_2026-10-08.md`） |
| **iqr** | `st cap iqr` 输出 **184 个 `eIQ_ID_*`**（静态全表 `raw8/p7/tuning_keys.txt`）；★「改了生效没有」的唯一客观判据 |
| **epmc** | `epmc <idx 0..9> <nreg> [nz [from]]`；idx 2=mc / 8=3dlut / 9=nog（与 `p7_ep_windows.py` OFFICIAL 表双源互证） |
| ★ epmc 陷阱 | `nz` 模式里 **`nreg` 是结束下标不是个数**（`epmc.c:107`）⇒ "从 0x1300 扫 512 个"要写 `epmc 0 1728 nz 0x1300`；写成 `512` 会**一次都不扫却打印成功**（假结论形态） |

---

## 5. 用户态接口层（当前可用的那一层）

### 5.1 Picture Wizard（PW）模型 —— FilmLab 的基石

| 项 | 值 |
|---|---|
| 槽位 | 14 槽 × 7 维（R/G/B 增益 + HUE/SAT/SHARP/CONTRAST） |
| prefman 偏移 | `PW_BASE=0xa3ec`、`PSTEP=52`、`SSTEP=4` |
| 中性值 | R/G/B=100，H/S/Sh/C=10 |
| UI 可见槽 | 只有 9/10/11（自定义1/2/3）；**槽 12 存在但隐藏且禁用**（脏数据会搞坏相机） |
| 实时切换 | `setusr 20 0x14000N`；★ 槽 11 → enum 12（**off-by-one**）；enum 11 是空洞 |
| enum 回显 | 有 bug（N=10/11 都显示 CUSTOM2）⇒ **信 prefman 读回，不信 enum 回显** |

- ★★ **PW 生效 = 三条独立通道，缺 ③ 画面不变**（2026-10-08 晚纠错，旧"切模式即可"**已证伪**）：
  | 通道 | 命令 | 作用范围 |
  |---|---|---|
  | ① 存储 | `prefman set 0 0xa3ec…` | 只改槽位数据（偏好存储） |
  | ② 选择 | `setusr 20 0x14000N` | 只改"当前选哪个 PW"（ISP 换风格，但手中 7 维参数是旧的） |
  | ③ **参数** | app「画面向导→确认自定义1」推送（属性总线 `0x10e/0x110/0x111/0x112`） | ★ **只有这条能让画面立刻变**；shell 侧**无入口**（setvar 实测不通且危险） |
  - di-camera-app 自己走 ③ 的等价物：`CAttributeHandler::setPWColor/Saturation/Sharpness/Contrast`
    → `set_attribute(0x10e/0x110/0x111/0x112, &v, 4)`（`test_server/pwfilter/CAPTURE_FW.md` §6），
    该属性总线 **`st` 命令面不暴露** ⇒ 这就是"必须进画面向导点一次自定义1"的根因。
  - ★ 实测链路（用户 2026-10-08 晚复测）：`EV+AEL → 点配方 → 打开画面向导 → 选中自定义1 → 画面生效`。
    "切一次拍摄模式 (`st app mode p;…;a`) 即刷新" **不成立**。
  - ★★ **上机实测（2026-10-08 23:00）**：① ② `save` 全都不搬参数；判据 = `varlist` 的 PW 变量
    （`filmlab.sh check` 一条命令给判词，详见 `PW_PARAM_CHANNEL_2026-10-08.md`）。
  - 引擎已改：`trigger_reload()` 降级为可选（`FILMLAB_MODE=1`，默认关）；apply 补 `prefman save 0`（否则重启回退）；
    新增 `filmlab.sh check`（只读判据）+ `reload`（只重触发）；`pwvar`（setvar 探测）**作废**。
- ★ `SAT=0` = 真黑白；**保留 R/B 增益差 = 暖调/冷调黑白**（相机独有，PC 端矩阵引擎做不到）。

### 5.2 ISP 参数块（路径 B，不刷固件）

| 项 | 值 |
|---|---|
| 块 A / 块 B | `0x20821300` / `0x20821700` |
| 提交位图 | `*(u32*)0x20820044 = 1<<idx` |
| 规模 | **21 槽 × 2 通道** |
| 槽池 | 8 槽 × stride `0xc8`；★ **槽号运行时分配 ⇒ 必须记录写入瞬间的槽号**（U14） |
| 生效判据 | `st cap iqr`（G5-2 已 PASS；G5-3 缺 iqr×epmc 关联表） |
| 关键人物 | 块 A/B 非零 40/512；mc 块 768 ✅（U1 实机） |

### 5.3 3D LUT（用户态写入 ✅）

- ★ 完整 **6 步写入序列**，一步不能少（②⑥ 漏掉完整无效）：
  ```c
  b[0x000] |= 1;  b[0x008] &= ~1UL;  b[0x008] |= 1UL;
  b[0x00c] = lut_phys;  b[0x004] &= 0xffffffcfUL;  b[0x008] &= ~0x100UL;
  ```
- 客观判据：执行后 `+0x008` 保持 1 = 硬件接受了启动；硬约束：LUT 物理地址 **256 B 对齐**。
- ★ **4 组三星内置 LUT**（`0x810fd100` 风格化 / `0x81106b00` 同1 / `0x81115200` 暖色肤色 / `0x81101e00` 纯 identity）——
  **零风险立即可用**：把 `+0x0c` 写成其中之一即可在 4 套方案间切换（无需改固件）。
- ★ **表格式未知**（寄存器无格式字段）：观测 `0x0000→粉红`｜`0x8000→品红`（中点非中性）｜`0xFFFF→青绿`。
  旧否证：表长 19652/29478、save_lut 读回、未等 DMA。
- ★ 缓冲在 p7 地址空间（`0x81xxxxxx`），Linux 永远读不到 ⇒ `lutmod` 搬缓冲是"改 p7 路线"的一部分（见 §1.2）。

---

## 6. 原生 UI（EFL）与显示层

| 件 | 结论 |
|---|---|
| **mod_gui** | 不能迭代、只能取代：4 控件 / 2 列 / 点击即退 / 只认 **4 个 keysym**（旧档"13 键"是误植）；`mkgui` 上限 `MAXBTN=22` |
| ★ 标签订截断 | 2 列网格**静默截断**长标签 ⇒ 显示名 ≤ ~6 全角字符（~12 半角）（2026-10-04 实测） |
| 菜单格式 | 纯文本 `button\|label\|command`；`@` 前缀 = 子菜单；末两行固定 `返回\|@…` / `取消\|gui_exit.sh` |
| **p7 无菜单** | 判据 = 搜 `Font/DrawText/Dialog/Widget` 四件套全 0 ⇒ 无界面；系统菜单在 Linux 侧 `di-camera-app` |
| evas 真约束 | **必须调用一次 `evas_object_text_font_set()`**（不设 ⇒ 几何 0×0 不画）；"必须指定族名"是过头表述 |
| EFL 环境 | `DISPLAY=:0`、`ELM_PROFILE=mobile`、`EVAS_FONT_DPI=72`、★ `LD_LIBRARY_PATH=:/usr/lib:/usr/lib/driver`（`/usr/lib/driver` = Mali GPU）；抄自 `/proc/<di-camera-app>/environ` |
| **nxfilmui** | 自写 EFL UI；v4 **中文可用**（`apply_label_font()` + `g_ascii` 默认 0）；同款调用序列离线实测 PASS（正对照出字 / 负对照零墨） |
| ★ **已决（10-08 夜）** | **U2 走 mod_gui 菜单路径达成**：自绘全屏 UI 的"窗口不显示"障碍（5 类排除 + 3 候选）**不再追**——理由：即使显示成功，全屏自绘在单核上有拖死风险（已实测过）；改由 **mod_gui 4 控件菜单**承载功能入口（实测能显示、不卡）。自绘窗口问题留作"阶段 2 增强"的可选项，见 `U2_UI_DISPLAY_2026-10-08.md` §3 |

- 架构级天花板（记下防忘）：长按/连击/组合键不可得｜WB 仅 K 值+色调｜fb0 64×64｜X11 自绘吃满单核｜**单次连续段 ≤768 regs**。

---

## 7. 门控与能力放行（★ 已同步至 2026-10-09 口径）

> 变更摘要（对照 10-08 版）：**G5 全绿**（G5-3 已补，见 `G5P3_IQR_EPMC_MAP`）；
> **U2 已解**（改走 mod_gui 菜单路径，见 `U2_UI_DISPLAY` §3-D + `TASKFLOW` §0）；
> **p8 已结案**（`P8_ZERO_INVESTIGATION` §9）；**U4 离机阶段完成**（重打包自证，上机未执行）。
> 当前 G0/G1 随相机在线状态浮动（10-09 上午：**整机离线**）。
> ★ 进门纪律不变：动手前必跑 `python test_server/tools/gate_flow.py`。

| 门 | 状态 | 说明 |
|---|---|---|
| **G0** 上机可达 | ◐ 随相机浮动 | 判诀：`REFUSED`=服务未起 / `TIMEOUT`=整机离线 |
| **G1** 上机安全 | ◐ 机器项全 OK | ★ EV_MOBILE 死循环版已修复（安全版 `54a308b8`）；3 项须机上人工签字；U6 包 lint 已入 G1-7c |
| **G2** U11 路线判定 | ✅ **PASS（G2b）** | 四点齐全；**两个 LUT 缓冲均不可读** —— 事后由「表格式离线解开」整体超越（见 §5.3） |
| **G3** 原生 UI 上机 | ✅ **PASS** | 五页 720×480 PNG + `font_set` 70 次 |
| **G4** 允许改 p7 | ⛔ **BLOCKED** | 缺 U4（`raw8/gates/u4/acceptance.json`）+ U5（`raw8/gates/u5/rollback_drill.json`）；★ **唯一主线：U4 上机 → U5 → G4 转绿** |
| **G5** 生效判据 | ✅ **全绿** | G5-3 已补：`iqr_epmc_map.tsv` 40 行关联表 + 架构判定（槽池 = 流描述符层，与 iqr 正交） |

**能力放行：1/5。** 只有 **L1（用户态脚本 / 胶片引擎 / 3D LUT 写入）** 放行；
L2 / 路径 B / U4 / L4 全部被挡。聚合优先级 `FAIL > BLOCKED > MANUAL > PASS`。
★ 10-09 新增在 L1 内的能力：**3D LUT 自定义表全链路**（R3 造表包已备，`raw8/gates/u6/`）
与 **PW 属性用户态推送路径**（传输层已解，POC `pwsend.arm` 在案，见 `ATTR_BUS_MCB_2026-10-09.md`）。

```
G0 ─┬─> U1 只读上机 ──> G2 ──> D1 走哪条路
G1 ─┘                └─> G5 ──> 路径 B（ISP 参数块）
    ├─> U2/U3 原生 UI 上机（另需 G3）
    └─> U4 SLP 重打包 ──> U5 回滚演练 ──> G4 ──> 才允许改 p7
```

★ 顺序铁律：**U1（只读、零风险）→ U2/U3 → U4 → U5 → 才讨论真改 p7**。那之前**永远停在"用户态 + ISP 参数块"层**。

### 7.1 上机轨执行状态（★ 已同步至 2026-10-09）

| 轨 | 状态 |
|---|---|
| **U1 只读上机** | ✅ **全部完成**（①/②/③/④/⑤）——四点对照、IPC 8 段、input_map、iqr 184、epmc 自证；产物在 `raw8/gates/u1/` |
| **U2 原生 UI** | ✅ **达成**（10-08 夜）——自写全屏 UI 已证不可行（窗口不显示 + 拖死风险）；**改走 mod_gui 菜单路径**（实测不卡、能显示），见 `U2_UI_DISPLAY` |
| **U3** 首次渲染延迟 | ❓ 未测（测量脚本并入 U6 顺带项） |
| **U4** SLP 重打包验收 | ◐ **离机完成、上机未执行**：重打包自证 IDENTICAL + 段↔分区映射 + 风险"1.13≈1.12"（`U4_SLP_REPACK`）；上机步骤见 `TASKFLOW` §3-U4 |
| **U5** 回滚演练 | ❓ 未执行（U4 通过后） |
| **U6 3D LUT 上机包** | ★ **新编号，10-09 离机备妥**：造表包 + runbook + 安全闸（cmasafe）就绪；执行序 **U6 → U4 → U5（不可跳）** |

★ 纪律（会流血的）：上机批次必须留散热间隔（**连续 ~40 分钟只读后相机过热自动重启**，实测）；`/mnt/mmc` 与 `out/` 持久（SD 卡），但 exFAT 不保证 x 位 ⇒ 重跑前 `chmod 755`。

---

## 8. 死路清单（★ 最值钱的一节，勿再走）

| # | 死路 | 判据 |
|---|---|---|
| 1 | 指望 `mod_gui` 迭代 | 4 控件 / 2 列 / 点击即退 / 4 keysym —— 只能取代 |
| 2 | 在 p7 找菜单 | 四件套全 0 ⇒ p7 无界面 |
| 3 | 长按/连击/组合键 | 架构级不可得 |
| 4 | 纯寄存器写进固件 | 铁律 92：DMA/共享内存才能写 ⇒ NOG 仅 256B ⇒ 必走 DMA |
| 5 | PC 直连刷机 | iLauncher 只是"拷文件到 SD，由相机自己发起" |
| 6 | `/dev/mem` 读 p7 / MMIO | 实测全 Bad address（§1.2）——改走驱动 |
| 7 | 用户态读 LUT 缓冲 | 缓冲在 p7 地址空间，Linux 永远读不到 |
| 8 | 直接猜 3D LUT 表格式 | 寄存器无格式字段；旧三条否证（表长 / 读回 / 未等 DMA）——只能按 H-A~H-E 逐条验 |
| 9 | 用 `st firmware up` 的宽松"证明"官方 UI 会过 | 两个入口强度不同（§3.2） |
| 10 | 按 `epmc ... nz` 的"个数"直觉调用 | `nreg` 是结束下标（§4）——假输出陷阱 |

---

## 9. 未解清单 / 缺口（★ 已同步至 2026-10-09）

**本轮消除**：~~U2 窗口不显示~~（改走 mod_gui，§6）｜~~3D LUT 表格式~~（已解，`3DLUT_TABLE_FORMAT`）｜
~~G5-3~~（已补，§7）｜~~p8 全零~~（已结案，`P8_ZERO_INVESTIGATION` §9）。

| # | 项 | 阻塞点 |
|---|---|---|
| 1 | **3D LUT 上机验证（U6）** | 造表包/runbook/安全闸已备妥（10-09 离机）；**等相机在线 + G0/G1** |
| 2 | **PW 属性推送上机校准** | 传输层已解、POC 已编译（`pwsend.arm`）；id↔维度/值编码需一次上机实验（`ATTR_BUS_MCB` §3） |
| 3 | **U4 / U5** | 上机未执行 ⇒ G4 保持 BLOCKED ⇒ p7 禁改；★ 唯一主线 U4→U5 |
| 4 | **备份缺口** | p9 / p10 / p11 / **p14（~2.1 GB）** 未备份；传输策略待定（U6 后单列波次） |
| 5 | 原生 UI 首帧延迟 | 10.7 MB 字体在单核上的代价（属 U3，标注为 U6 顺带项） |
| 6 | PW 的 R/G/B 通道细分 + PWHUE id | 实验一次可校准（`ATTR_BUS_MCB` §4 遗留 #1/#2） |

---

## 10. 资产与证据索引

```
不可再生：raw8/p7/p7_full.bin（12,075,648 B, md5 5fc4824f…）
          raw8/emmcbak/ 194 MB｜.uploads/fw/nx500_v1.13.bin 352 MB（= v1.12 等价）
已隔离：  raw8/p7/quarantine/p7_patched.bin.DO-NOT-FLASH（改 0x200 破坏复位期 DACR）
          raw8/fw/quarantine/NX500_FW_v1.12.zip.TRUNCATED-DO-NOT-USE
暗路：    raw8/p7/p7_full.lutmod.bin（LUT 缓冲 0x81115200→0x97600000，落 Linux CMA）——G2b 后待重推目标地址
门控证据：raw8/gates/u1/{mem_compare.json, input_map.json, iqr_dump.txt}｜raw8/gates/gate_status.json
逆向证据：docs/evidence/p7/（Ghidra 片段）｜docs/evidence/discovery/（3D LUT 发现期）
上游材料：NX1 官方 GPL 包（NX1_kernel.tar.gz + NX1_packages.tar）——内核/系统层参考
```

- 跑相机用户态：`qemu-arm-static -L <rootfs>`；**跑 evas/EFL 必须 chroot**。
- WSL(NXKS2) rootfs `/opt/nxks2/rootfs-112`；Ghidra `E:\ghidra_12.1.4…` + JDK21，项目 `NXKS2/p7_full.bin`；QEMU `E:\qemu`（S0–S5 通）。
- 工具链：zig `arm-linux-gnueabi.2.15` **必须 -O0**。

---

## 11. 下一步（★ 已同步至 2026-10-09；日常调度以 `TASKFLOW_2026-10-09.md` 为准）

| # | 动作 | 属门 | 现在能做吗 |
|---|---|---|---|
| 0 | 进门：相机开机联网 → `python test_server/tools/gate_flow.py` | G0/G1 | 等硬件 |
| 1 | ★ **U6 3D LUT 上机包**（R3 验证 + 增量只读）→ `test_server/u6/runbook.txt` | L1（不用 G4） | 等硬件（资产已备妥） |
| 2 | **U4 SLP 最小实验**（pcache 首字节，会重启） | G4 | 依赖 1（U4 排在 U6 后） |
| 3 | **U5 单分区回滚演练** | G4 | 依赖 2 |
| 4 | PW 推送校准实验（`pwsend.arm` + capdtm 读回） | L1 | 依赖 0；与 U6 可同波次 |
| 5 | p14/p9-p11 备份（分块传输策略待定） | — | 单列波次（不混跑） |
| 6 | 拆仓发布收尾（4/8 步已落，4 步待授权） | — | 等授权 |

★ 离机轨 D1–D8 / O1–O5 已清空（10-09 上午）；**离机期新增能力**：3D LUT 造表包、
U6 runbook、cmasafe 安全闸、PW 传输层全解 + POC —— 上机机会零浪费。

---

*生成：2026-10-08 · 分支 `nx-ks2` · 口径：本文汇总各专题文档 + 2026-10-08 21:50 门控实测；冲突时以专题文档为准。*
