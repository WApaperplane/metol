# 离机验证报告（2026-10-08 下午场）

> 承接 `QEMU_S5_OFFLINE_USERSPACE_2026-10-08.md`（"QEMU 能替用户态、替不了硬件"）。
> 本文 = **在用户无法上机的前提下，把"能离机做的"再做掉四项**，并对既有结论做三处修正。
> **全程未触碰相机**（只读 PC 侧素材 + WSL 内 chroot 沙盒）。
>
> 四件：① ★★★ **CJK 真的画出来了** ② 脚本 CI 归零 ③ p7 两个补丁定性 ④ 备份"全零"悬案改写。
> 另：`SLP_CONTAINER_FORMAT_2026-10-08.md`（U12 全解）单列。

---

## 0. 一句话结论

> **① QEMU 把"CJK 能不能用"从"字形在"推到了"字真的画出来了"—— 而且顺手改掉一条既有结论。**
> **② 铁律 99 的 CI 从 3 FAIL 归零，136 个脚本的 git 执行位补齐（拆仓硬前置）。**
> **③ 两个"未记录用途的 p7 补丁"全部定性：一个是复位期 DACR 写入被改成未定义编码（危险），
> 一个是把第 4 个 3D LUT 缓冲指针改到 Linux CMA 区（= U11 的一条暗路）。**
> **④ 逐字节复核推翻了"p3 备份全零"—— p3 与 p2 共享同一记录页指纹，是真·稀疏不是读错。**

---

## 1. ★★★ CJK 离线光栅化：从"字形在"到"字画出来了"

### 1.1 为什么做这件事

S5 只证到"字体文件里随机 300 个 CJK 码点 300/300 有非空 glyf 轮廓"——
**字形存在 ≠ evas 能画出来**。S5 自己把下一步写成："写个 ARM 小程序用 evas 的 buffer 引擎光栅化中文导出 PNG"。

### 1.2 做法（新资产 `test_server/filmlab/src/cjk_render.c` + `build_cjk_render.sh`）

```
cjk_render.arm（zig 交叉编译，arm-linux-gnueabi.2.15 softfp，-O0）
  ecore_evas_init() / evas_init() / ecore_init()
  ecore_evas_buffer_new(800,620)          ← 内存画面：不需要 X，不需要相机
  evas_object_text_add + evas_object_text_font_source_set(<TTF 绝对路径>)
  ecore_evas_manual_render(ee)
  ecore_evas_buffer_pixels_get(ee)        → ARGB32
  自写 PNG（stored deflate，零依赖；CRC/Adler 全自算）→ /tmp/cjk_render.png
```
运行环境：WSL(`NXKS2`) 内 **chroot 到相机 rootfs-1.12 + qemu-arm-static**
（脚本 `raw8/qemu/cjk_render_run.sh`，含"必须看到相机自己的 `st` 与字体"的自证步骤）。

### 1.3 结果

![证据见 raw8/repro/cjk_render_pos.png] —— 六个行全部正确出字：

| 行 | 文本 | 结果 |
|---|---|---|
| A1 | `SDIC_GP_US / CJK 光栅化离线验证` | ✅ 出字 |
| A2 | `中文测试 胶片仿真 影调 颗粒 色彩` | ✅ 出字 |
| A3 | `Portra 400 / Velvia 50 / Tri-X 400` | ✅ 出字 |
| A4 | `麤龘靐齉爩 Yes/No`（三叠/复杂字）| ✅ 出字（可见 麤=三鹿、龘=三龍 的叠字形态）|
| A5 | `日本語 あいう カタカナ` | ✅ 出字（假名正常）|
| A6 | 生僻字放大行 | ✅ 出字 |

**逐行精确取墨（用每个文本对象自己的几何矩形，不与邻行混淆）**：
A1=5178 / A2=9362 / A3=3538 / A4=8497 / A5=3364 像素 一致有墨。

产物：`raw8/repro/cjk_render.png`（800×620）+ `cjk_render.log` + 裁剪图 `cjk_render_top/bot.png`。

### 1.4 ★★ 三处修正（含一条对 S5 的修正）

| 项 | 原表述 | 实测修正 |
|---|---|---|
| **N04 / P6**（S5 已撤销）| 相机无中文字体 ⇒ 只能 ASCII 降级 | ★ **进一步推进**：不是"字形在"，是**真的能画出来**（离线已证到光栅化那一层）|
| **S5 §2.1**「evas 不硬编码 SDIC_GP_US ⇒ UI **必须**显式指定族名」| 暗示不指定就画不出 | ★ **过头了**。实测：显式给 **Khmer 字体文件**（确定不含 CJK）也照画不误；不给 `font_source`、只给族名 `SDIC_GP_US` 或通用名 `Sans` 也照画 ⇒ **evas 有字形回落**。<br>**真正的硬约束只有一条：`evas_object_text_font_set()` 完全不调用 ⇒ 几何为 0×0、一个像素都不画。** |
| `deploy/filmlab/INSTALL.txt`「已知限制：零中文字体…含中文自动降级成序号+key」| 同上 | ★ **已就地更正**：新增说明（字体在、离线已证能画；只有完全不设字体才画不出）|

**对本项目的实际含义**：原生 UI 的中文标签**零额外成本**（不必再为 CJK 做 ASCII 降级设计），
但**每一处文本都必须设置字体**（推荐显式写 `SDIC_GP_US` 以求确定性，而不是依赖回落）。
残余风险只剩"S5 提到的 10.7MB 字体首次渲染延迟在单核上多大"——**仍需上机一次**。

### 1.5 ★ 本项自身的一个 bug（记录在案）

首版 PNG 的 CRC 全是 `0xffffffff`，PIL 打不开。根因：**写了 `crc_init()` 却从没调用**，
零表使 `crc32` 恒返回 `0xffffffff`。⇒ 教训：**自写格式解析器/写入器必须有"能被第三方工具打开"的验收步骤**，
不能只看"文件大小对"。（文件大小确实"对"——stored deflate 下字节数与内容无关。）

---

## 2. 脚本 CI：3 FAIL → 0 FAIL（拆仓硬前置）

工具：`test_server/tools/check_scripts.py`（读 `git ls-files -s` 判断 git 里的 mode，
因为在 Windows 上 `core.filemode=false`，文件系统位不可信）。
一键修复脚本：`test_server/tools/apply_ci_fixes.py`（新）。

| 项 | 修前 | 修后 | 动作 |
|---|---|---|---|
| **CRLF（铁律 99）** | 2 文件 | **0** | `scripts/fstack.sh`（2 处）、`scripts/gui_br_NX1.tp`（8 处）→ 全部 CRLF→LF |
| **语法错误** | 1 | **0** | `scripts/rem_set.sh:43` `do echo … done` 缺 `;` ⇒ 补上；`bash -n` 通过 |
| **无可执行位** | 136 | **0** | `git update-index --chmod=+x`：全仓 **225 个 .sh** 由 `100644` → `100755` |
| 无 shebang | 2 | 1 | `fstack.sh` 补 `#!/bin/sh`（它由 mod_gui 以 `/opt/usr/nx-ks/fstack.sh` **直接执行**）|

**最终**：`RESULT: PASS (0 fail / 1 warn)` —— 唯一 warn 是 `scripts/EV_MOBILE.sh` 无 shebang（见 §3.3，故意不动）。

★ 关于执行位这条的分量：仓库里所有脚本在 git 里都是 `100644` ⇒ **任何人在 Linux 上 clone 本仓库，
`scripts/*.sh` 全部没有执行位** ⇒ `install.sh` 拷到相机后 `system()` 调用全部失败。
这是"在 Windows 上开发、在 Linux/相机上运行"的仓库**必然踩到**的坑，与铁律 99（CRLF）同族。

---

## 3. 两个"未记录用途的 p7 补丁"——全部定性

前一轮留下的话是"改的是**引导期 MMU/协处理器**与 **LUT 取址** ⇒ 上机/刷机前必须弄清或清理"。
本轮把它们**反汇编 + 三方比对**做完了。

### 3.0 先解决"谁才是原版"（★ 用两份独立官方源）

```
机上分区 p7.bin[0:12075648]   md5 = 5fc4824f5b6a6a3caca1f9104238b8ac
官方固件 SLP img5             md5 = 5fc4824f5b6a6a3caca1f9104238b8ac   ← 独立来源，完全相同
p7_full.bin[0:12075648]       md5 = 5fc4824f5b6a6a3caca1f9104238b8ac   ← 相同
p7_patched.bin                md5 = 1b29180b0abff2161c89a7b0245097ec   ← 只差 0x200 一个字节
```
⇒ ★★ **`p7_full.bin` 是原版（+尾部补零到 12.25MB），`p7_patched.bin` 是被改过的那一份。**

### 3.1 `p7_patched.bin` —— ★★★ 复位期 DACR 写入被改成未定义编码（**危险样本**）

改动：文件偏移 `0x200`（VA `0x80000200`）`10 0f 03 ee` → `11 0f 03 ee`。反汇编上下文：

```
800001fc  ldr  r0, [pc, #0x54]        @ 0x80000258 = 0x55555555
80000200  mcr  15, 0, r0, cr3, cr0, {0}     ← 原版：写 DACR，16 个域全部 client
          mcr  15, 0, r0, cr3, cr0, {1}     ← 补丁：opcode2 0→1
80000204  dsb  sy
80000208  mcr  15, 0, r0, cr8, cr7, {0}     ← TLBIALL
8000020c  mcr  15, 0, r0, cr7, cr5, {6}     ← 失效分支预测阵列
80000210  dsb  sy
```
- 本镜像确为 **ARMv7**（`f57ff04f` = `DSB SY`）；
- **ARMv7-A 中 CP15 `c3/c0/op2=1` 未定义** ⇒ 该写入要么不生效（DACR 停在复位值，
  域 0 由 client 变 no-access ⇒ 首次被域 0 管辖的访存就 fault），要么触发**未定义指令异常**。

> **处置建议（P0 资产卫生）**：把 `p7_patched.bin` 移到 `raw8/p7/quarantine/`，
> 文件名加 `.DO-NOT-FLASH`，并在 `MANIFEST` 里登记"复位期域权限配置被破坏"。
> **不要**留在 `.uploads/fw/`（那里看起来像"可直接刷的固件"）。

### 3.2 `p7_full.lutmod.bin` —— ★★★ 第 4 个 3D LUT 缓冲被改到 Linux CMA 区（**U11 的一条暗路**）

改动：文件偏移 `0x3837FD..0x3837FF`（3 字节），即字面量池里 1 个 u32：
`0x81115200` → **`0x97600000`**。

反汇编证明这个字面量池**就是一个 4 选 1 的 LUT 缓冲选择器**：

```
803837d0  cmp   r2, #1
803837d4  ldreq r3, [pc, #20]   @ 803837f0 = 0x810FD100   ┐
803837d8  ldreq r0, [pc, #20]   @ 803837f4 = 0x81101E00   │ 四个 LUT 缓冲
803837dc  ldrne r3, [pc, #20]   @ 803837f8 = 0x81106B00   │ 基址（本项目
803837e0  ldrne r0, [pc, #20]   @ 803837fc = 0x81115200 ★改这个  │ 早期已登记）
803837e4  cmp   r1, #1
803837e8  moveq r0, r3
803837ec  bx    lr
80383800  push  {r4-r11, lr}    ← 4 个指针的消费函数（下一步 U11 的入口）
```
★ 顺手拿到两个**新资产**：
1. 这个 4 个 LUT 缓冲基址的**代码位置**（VA `0x803837D0` 选择器 + `0x80383800` 消费函数）——
   以前只知道地址，现在知道**谁在用、怎么选**，U11 有了确定的 Ghidra 入口。
2. `0x97600000` 落在 **Linux 已保留的 CMA 窗口内**（`cma: reserved 288 MiB at 94000000`
   ⇒ `0x94000000–0xA6000000`）⇒ ★ 这个补丁的**意图**是"把 LUT 缓冲挪进 Linux 看得见的 DRAM"。

> **处置建议**：与 §1.4/Tier1 的 `/dev/mem` 四点对照**互为两种方案**：
> - 若 `dd if=/dev/mem @0x81115200` **读得到** ⇒ 根本不需要这个补丁；
> - 若**读不到** ⇒ 这个补丁才是备选，但必须**重新推导目标地址**并在机上确认
>   "p7 写、Linux 读"不会与 CMA 的实际分配撞车（否则是数据损坏事故）。
> **在搞清之前，此文件同属"不能刷"**。

### 3.3 顺带查出的一件事：`scripts/EV_MOBILE.sh` 仍是社区"卡死版"

CI 唯一的 warn（无 shebang）指向它，查文件发现是**社区原版那个每 2 秒 `ip addr ls` 的死循环**：

```sh
netcheck(){ while [[ ! -z $IP ]]; do
    IP=`ip addr ls|grep inet|grep mlan0|cut -d/ -f 1|grep -o '[0-9]\{1,3\}\.…'`; sleep 2
  done; cleanup; }
```
（且第 1 行 `renice -n -15 -p $$`，是**提优先级**的死循环。）

★ 关键路径验证（用 `scripts/keyscan` 的格式串自证，不靠记忆）：
```python
# keyscan 里的格式串（raw8 提取）
0x79f3c  b'%s/%s.sh'      ← <脚本目录>/<名字>.sh
0x79f34  b'EV_%s'         ← EV+某键
0x7a8f4  b'/bin/sh'
# init.sh:39  nice -n +15 /opt/usr/nx-ks/keyscan /dev/event0 /dev/event1 /opt/usr/nx-ks/ &
```
⇒ **EV+WiFi ⇒ `/opt/usr/nx-ks/EV_MOBILE.sh`**；而 `install.sh` 做的是 `cp -ar /mnt/mmc/scripts/* /opt/usr/nx-ks/`
⇒ **`scripts/EV_MOBILE.sh`（37 行死循环版）会被原样装上机**（除非走 `deploy/filmlab/` 那套手工覆盖 4 文件）。

**四种同名文件的 md5（必须区分，别再搞混）**：

| 路径 | md5 | 性质 |
|---|---|---|
| `scripts/EV_MOBILE.sh` | `55c47b8924342c42…` | ★ **37 行、含 2s 死循环** ⇒ 装上机就是"EV+WiFi 卡死" |
| `backup_original/EV_MOBILE.sh` | `6ae2495bfeea69f3…` | 社区原件（留档）|
| `deploy/filmlab/EV_MOBILE.sh` | `2657352ebcadd627…` | FilmLab 覆盖版（安全，直达配方页）|
| `scripts/nx-rc/EV_MOBILE.sh` | `54a308b8c55d8e3a…` | ★ 本项目重写版（修掉死循环），82 行，带 shebang |

> **本报告不擅自改它的行为**（它是"经典 EV+WiFi 通道"，改动属产品决策），
> 但把它列为**上机前 P0 检查项**：目标机上 `/opt/usr/nx-ks/EV_MOBILE.sh` 的 md5 必须是
> `2657352e…`(FilmLab 版) 或 `54a308b8…`(nx-rc 版)，**绝不能是 `55c47b89…`**。

---

## 4. ★ 备份"全零"悬案的改写（p3 **不是**全零）

新脚本 `raw8/emmcbak/audit_sparse_partitions.py` → 报告 `raw8/emmcbak/sparse_partition_report.txt`。

### 4.1 三条独立判据

**J1 非零字节的分布形态**

| 分区 | 大小 | 非零字节 | 首个非零 | 末个非零 | 判定 |
|---|---|---|---|---|---|
| p1/p5 (adj/pref_recovery) | 20,970,496 | 4,359,833 | 0x0 | 0x5352d2 | 有实质内容 |
| p2 (pref) | 10,485,760 | **1,779** | 0x0 | 0x10024d | **稀疏但结构有效** |
| p3 (pref_default) | 31,457,280 | **392** | 0x0 | 0x69a00a | ★ **不是全零** |
| p8 (rtos_data) | 52,427,776 | **0** | — | — | ★ **唯一真·全零** |
| p12 (pcache) | 5,241,856 | 17,306 | 0x400 | 0x6ff7 | 稀疏但结构有效 |

**J2 分区家族指纹（★ 决定性）**：p2 与 p3 在**前 1MB 的非零页指纹完全相同**

```
page     0x0     p2= 9  p3= 9        page   0xa700  p2=19  p3=19
page   0x200     p2=37  p3=30        page   0xa800  p2=23  p3=23
page  0xa300     p2=62  p3=58        page   0xaa00  p2= 1  p3= 2
page  0xa400     p2=64  p3=64        page   0xc100  p2= 5  p3= 5
page  0xa500     p2=48  p3=46        page   0xc200  p2= 1  p3= 1
page  0xa600     p2=38  p3=36        page   0xc300  p2= 6  p3= 6
⇒ 两边都有非零的页 = 14 / 14（**100% of 较小者**）
```
两者头部同形：`33 00 33 00 | <4B> | 0c 07 01 00` ⇒ **同一「pref 家族」的稀疏记录存储**。

**J3 判据合起来**：读错区域**不可能**读出一个"和另一个分区对得上"的记录页指纹 ⇒
「读出全零 = 备份读错」这一假设在 **p2/p3** 上被削弱；**p8 是唯一的真异常**。

### 4.2 因此要改的结论

| 原表述 | 修正 |
|---|---|
| 「`p3`/`p8` 备份**实际全零**」 | **p8 成立（0 非零字节）；p3 不成立（392 非零字节 + 与 p2 同族的页指纹）** |
| 「全零的 p3 **不可能**做回滚源」 | ★ **该推论的前提不成立**。p3 能不能回滚取决于"出厂 pref 应有哪些记录"⇒ **必须机上验证**，不能用备份字节数否证 |
| 「`p2` 是 prefman 一直在写却几乎全零 ⇒ 「pref 写在 p2」或「备份读对了」必有一错」 | ★ **可解释**：pref 是**稀疏记录存储**，未写过的 eMMC 页读作 `0x00` ⇒ 1779 字节非零是正常的。两个假设都不必错 |
| 「p8 全零」 | **仍开放**（分区真空 / 读保护 / 从未写入 未区分）。它现在是**唯一**需要解释的那个 |

---

## 5. 本轮新增资产索引

| 文件 | 说明 |
|---|---|
| `test_server/filmlab/src/cjk_render.c` | ★★★ 离线 CJK 光栅化探针（evas buffer 引擎 + 自写 PNG）|
| `test_server/filmlab/src/build_cjk_render.sh` | 其交叉编译脚本（含 DT_NEEDED 自证）|
| `raw8/qemu/cjk_render_run.sh` | WSL chroot + qemu-arm-static 运行脚本（含自证步骤）|
| `raw8/repro/cjk_render.{png,log}` + `cjk_render_{top,bot,pos,ctl}.png` | ★★★ 证据图与日志 |
| `test_server/tools/apply_ci_fixes.py` | 铁律 99 CI 的一键修复（CRLF / 语法 / git 执行位）|
| `raw8/emmcbak/audit_sparse_partitions.py` | ★ 稀疏分区判据（页指纹法）|
| `raw8/emmcbak/sparse_partition_report.txt` | 其输出 |
| `raw8/fw/slp_parse.py` + `raw8/fw/slp_parse_report.txt` | ★★★ SLP 容器解析与校验（见 `SLP_CONTAINER_FORMAT_2026-10-08.md`）|
| `raw8/p7/disasm/reset_0x140.bin`、`lutpool_0x3837c0.bin` | 两个补丁点的反汇编输入切片 |

---

## 6. 仍然只能上机做的事（本轮之后没有减少）

1. ★★★★ `dd if=/dev/mem` 四点对照（`0x810fd100` / `0x81115200` / `0x2082b000` / `0x94000000`）
2. ★★★ IPC 区（`0x2080_0000–0x2081_FFFF`）分行只读扫描（≤768 regs/段）
3. ★★ 波轮 keysym + 触摸回调（`nxfilmui` 挂 `FN_FN`）
4. ★ CJK **在相机上的实际渲染延迟**（离线已证能画；单核 10.7MB 字体的首帧代价未测）
5. ★ `iqr`(184 ID) × `epmc`(两个参数块) 关联 —— **必须记录写入瞬间的运行时槽号**（U14 已证槽号动态分配）
6. ★ 官方升级路径是否接受**重打包后的 SLP**（SLP 格式已解，但接受性未验）

---

*生成：2026-10-08 · 全程离线，未触碰相机*
