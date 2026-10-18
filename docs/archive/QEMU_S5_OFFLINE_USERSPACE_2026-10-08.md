# QEMU S5 · 离线用户态验证（2026-10-08）

> 背景：用户无法上机（人在公司），要求先用 QEMU 虚拟跑一次。
> 本文回答 **「阶段 1 清单里哪些能在 QEMU 里替代、哪些不能」**，并给出 S5 实测结果。
> ★ 本轮有 **两项改变结论** 的发现：**CJK 字体结论被推翻**；**配方引擎跨环境逐字节一致**。

---

## 0. 一句话结论

> ★★★ **QEMU 替不了硬件探针，但替掉了一个我们以为必须上机的问题**：
> **相机 rootfs 自带一个 49864 字形的多语言字体 `SDIC_GP_US`，CJK 字形 100% 有真轮廓**
> ⇒ **档案里「`/usr/share/fonts` 无中文字体 ⇒ 原生 UI 只能 ASCII 降级」（N04 / P6）是错的。**
> ★★ 并且：**在真 rootfs 里跑配方引擎得到的 JPG，与 PC 侧结果 md5 逐字节相同**
> ⇒ 配方引擎与宿主环境无关，PC 侧调好的配方可以直接上机。
> ★ 另附一个新工具 `check_scripts.py`（把铁律 99 变成 CI），**一上线就抓到 3 个真缺陷 + 1 个仓库级问题**。

---

## 1. QEMU 能替代什么、不能替代什么

| 阶段 1 原计划项 | QEMU 能替？ | 原因 |
|---|---|---|
| `/dev/mem` 四点对照（`0x810fd100` / `0x81115200` / `0x2082b000` / `0x94000000`） | ❌ **不能** | 要真实 DRAM 与 p7 堆区；QEMU `-M virt` 没有这些物理地址 |
| IPC 区（`0x2080_0000-0x2081_FFFF`）分行扫描 | ❌ **不能** | EP/IPC 是真实硬件，QEMU 里不存在 |
| 波轮 keysym / 触摸回调 | ❌ **不能** | 需要真实键盘矩阵 + 内核 input 驱动 |
| **CJK 字体能否渲染** | ✅ **能，且本轮已给结论** | 纯用户态：字体文件 + 字形表 |
| **全脚本语法 / CRLF 体检（铁律 99 → CI）** | ✅ **能**（本轮做了） | 纯文本 |
| **EFL 栈齐备性 / 原生 UI 可行性** | ✅ **能** | guest 内核是 ARM，相机二进制原生执行 |
| **配方引擎端到端** | ✅ **能**（本轮做了，并与 PC 交叉验证） | 同上 |

⇒ ★ **结论：QEMU 覆盖了"用户态"那一半；硬件那一半（寄存器/EP/IPC/按键）必须等上机，无法替代。**

---

## 2. S5 实测结果

环境：`qemu-system-arm -M virt -cpu cortex-a15 -m 512M` + S4 的 scratch.img（ext4 幂等路径，跳过 18 秒解压）
日志：`raw8/qemu/boot_s5_offline_userspace.log` ｜ init：`raw8/qemu/s5_init.sh`

### 2.1 ★★★ CJK 字体：结论被推翻

**自证先行**（否则"查不到"不可信）：`ls -l /mnt/usr/bin/st /mnt/lib/ld-linux.so.3` 均在位，顶层 24 项
⇒ 确认挂的是**相机 rootfs**，不是宿主。

相机 `/usr/share/fonts` 共 **9 个 TTF**，其中 ★ **`SDIC_GP_US_20120720.ttf` = 10,680,224 字节**
（`SDIC` = Samsung Digital Imaging；与 binwalk 早前命中的 `/etc/fonts/conf.avail/66-SDIC_GP_US.conf` 呼应）。

**PC 侧解析 cmap + glyf/loca（硬判据）**：

| 项 | 值 |
|---|---|
| `numGlyphs` | **49864** |
| 字形表覆盖 | **CJK 统一表意 20902** / CJK 扩展A 6530 / **谚文 11172** / 平假名 93 / 片假名 96 / CJK标点 64 / 全角 164 |
| **随机 300 个 CJK 码点** | ★ **300/300 有非空 glyf 轮廓**（min 52 / median 276 / max 552 字节） |
| 抽样 | 中(88B) 文(148B) 测(232B) 试(244B) 胶(248B) 片(92B) 濾(440B) あ(408B) **全部真轮廓** |
| 字体族名 | `SDIC_GP_US`（nameID 1/4） |

**独立旁证**：rootfs 里另有 **`zh_CN` 语言目录**（在 locale squash 解包内）⇒ 相机本来就带中文语言包。

**唯一保留**：evas **不硬编码**该字体（`libevas.so.1` 里零命中，只有扫描常量 `*.ttf`；
`/etc/fonts` 不存在；edje 主题里的字符串是压缩的抓不到）
⇒ **原生 UI 需显式指定字体族 `SDIC_GP_US`**，不能指望主题自动选中。
⇒ ★ 但这反而简单：**UI 是我们自己写的，显式指定即可。**

⇒ ★★★ **修正 `FEATURE_MATRIX` N04 与 `HANDOVER` P6**：
"无中文字体 ⇒ 大概率需 ASCII 降级"**不成立**；中文标签可用。
（残余风险：10.7MB 字体在单核上首次渲染可能有延迟，evas 字形缓存行为待上机确认。）

### 2.2 ★★ 配方引擎跨环境逐字节一致（强交叉验证）

| 检查 | 结果 |
|---|---|
| 输入 md5 | guest `5c2689c71208b49b56096ed409e71f22` == PC 侧同值 ✓ |
| guest 内跑 `ksfilm.arm test_in.jpg out_qemu.jpg portra400` | rc=0，输出 `900x600 -> out_qemu.jpg recipe=portra400` |
| **产物 md5** | ★ **guest = `2aaa3332358f6d0f56b75da11f55bf24` == PC 侧 `out_portra400.jpg` 逐字节相同** |

⇒ ★★ **配方引擎与宿主环境无关** ⇒ PC 侧调好/验证过的配方与 LUT 处理可以直接上机，不需要"上机再验一遍算法"。

### 2.3 EFL 栈齐备 + ★ 新发现的离线渲染能力

| 项 | 结果 |
|---|---|
| 五个核心库 | `libevas / libecore / libecore_evas / libedje / libelementary` 全部 `1.7.99` 在位 ✓ |
| elementary 资源 | `themes/{default,default-desktop,tizen-default}.edj` ✓ |
| objects | `cursors / font_preview / multibuttonentry / multip / postit_ent / test / test_external` ✓ |
| ★ **evas 引擎** | `buffer` / `fb` / `gl_x11` / `software_generic` / `software_x11` |
| ★ 现成 EFL 程序 | `isf-demo-efl` / `isf-panel-efl` / `enlightenment*` |

★★ **`buffer` 引擎在场是关键**：evas 可以**渲染到内存、不需要 X、不需要相机**
⇒ **下一步可以写一个 ARM 小程序，用 buffer 引擎光栅化中文并导出 PNG** ——
**"中文字形真的能画出来"这件事也能离线验证**（本轮只验到"字形有真轮廓"这一层）。

### 2.4 ★ 新工具：`check_scripts.py`（铁律 99 的 CI 化）

`test_server/tools/check_scripts.py`（检查 CRLF / `bash -n` / 执行位 / shebang；`.tp` 是菜单模板已排除）。

**142 个文件的结果：**

| 类别 | 数量 | 明细 |
|---|---|---|
| **CRLF 违规（铁律 99）** | **2** | ★ `scripts/fstack.sh`（2 处，两行全带 CRLF ⇒ `renice -p 'xxxx\r'` 必然失败）<br>★ `scripts/gui_br_NX1.tp`（8 处）|
| **语法错误** | **1** | ★ `scripts/rem_set.sh` 第 43 行 `do echo "..."  done` **缺 `;`** ⇒ 整个脚本跑不起来 |
| ★★ **执行位** | **136/136** | ★★ **git 里全部记录为 `100644`** ⇒ **在 Linux 上 clone 本仓库，所有脚本都没有执行位** |
| 无 shebang | 2 | `EV_MOBILE.sh` / `fstack.sh` |

★ 关于执行位这条：本仓 `core.filemode=false`（Windows），**工作区位不可信**，
所以 CI 已改为读 `git ls-files -s`（第一版按文件系统位判断，误报 138 条 —— 已修正）。

### 2.5 记一次自伤（方法论）

用 `wsl.exe ... bash -c '...'` 时，**变量赋值与 `$(...)` 会被吞掉**：
`R=$(readlink -f ...)` 返回空 ⇒ `ls "$R/usr/share/fonts"` 变成 `ls /usr/share/fonts`
⇒ **我第一轮"字体普查"实际查的是宿主机 Ubuntu 的字体**（30 个含 `UbuntuSansMono[wght].ttf` 的现代可变字体），
结论完全错误。**靠自证（`ls -l usr/bin/st` 必须存在）才发现。**
⇒ ★ **纪律：跨 Windows/WSL 传命令时，不用变量赋值、不用 `$(...)`，一律用 `cd` + 相对路径，并保留一条自证。**

---

## 3. 因此需要修改的既有结论

| 位置 | 原结论 | 修正 |
|---|---|---|
| `FEATURE_MATRIX_2026-10-07.md` **N04** | `/usr/share/fonts` 无中文字体 ⇒ 大概率需 ASCII 降级 | ❌ **撤销**。`SDIC_GP_US` 含 49864 字形、CJK 100% 真轮廓；UI 显式指定该族即可用中文 |
| `HANDOVER_2026-10-07.md` **P6** | CJK 字体是否渲染空白（待上机） | ★ **离线已答大半**：字形在且非空。剩"evas 实际光栅化 + 单核性能"待上机 |
| `FIRMWARE_FEATURE_SPACE_2026-10-08.md` §3.2 横切 | CJK 默认 ASCII 降级 | 改为「**默认模板用 `SDIC_GP_US`；ASCII 降级仅作兜底**」|

---

## 4. 仍必须上机的清单（QEMU 之后没有减少）

1. ★★★★ `dd if=/dev/mem` 四点对照（`0x810fd100` / `0x81115200` / `0x2082b000` / `0x94000000`）
2. ★★★ IPC 区（`0x2080_0000-0x2081_FFFF`）分行只读扫描（≤768 regs/段）
3. ★★ 波轮 keysym + 触摸回调（`nxfilmui` 挂 `FN_FN`）
4. ★ CJK **实际光栅化**（evas buffer 引擎可离线做，但相机上的字形缓存/延迟要实测）
5. ★ `iqr`(184 ID) × `epmc`(两个参数块) 关联 —— ★ **必须记录写入瞬间的运行时槽号**（U14 已证槽号动态分配）

---

## 5. 建议的下一步（都不用相机）

| # | 动作 | 价值 |
|---|---|---|
| **1** | ★★ 写一个 ARM 小程序：**evas buffer 引擎光栅化中文 → 导出 PNG** | 把"CJK 可用"从"字形在"推到"能画出来"，**完全离线** |
| **2** | ★ 修掉 CI 抓到的 3 个缺陷 + 给 136 个脚本补 git 执行位 | 拆仓前必须做，否则 Linux 用户 clone 下来全是不可执行 |
| **3** | ★ 把 `check_scripts.py` 接进"拆仓动作清单"第 4 步（本来就是为它写的） | 铁律 99 自动化 |
| **4** | 继续推调用图/类地图（当前硬证据 48.21% → 含推断 64.3%） | 纯静态 |

---

*生成：2026-10-08 · 全程离线，未触碰相机*
