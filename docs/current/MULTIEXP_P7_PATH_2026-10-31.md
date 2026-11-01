# 多重曝光在 p7 的真实落点（静态定位，2026-10-31）

## 0. 结论摘要

| 问题 | 结论 |
|---|---|
| 原生多曝是否走 p7 的多曝路径 | **是**，p7 里有完整实现，不是靠用户态事后合成 |
| `LVIEW_FRAMEADD_MTOM` 是不是多曝合成器 | **不是**。它是 liveview 的通用帧加节点，与 `LVIEW_FRAMESUB_MTOM` 成对；多曝有独立的 `LVIEW_MULTI_EXPOSURE` 枚举和独立的 material 类 |
| `multiexpotype` 是不是 Add/Average 开关 | **不是**。capdtm 层的枚举只有 `SAVEALL` / `RESULTONLY`（保存策略） |
| Add/Average 由什么分派 | `CMaterial_NX1_Still_Effect_MultiExp::run()` → `FUN_003ff190` → `switch(*(u8*)(ctx+0x24))`，4 路 + default |
| 静功能否确认 Add/Average 各走哪路 | **不能**。静态找不到 `ctx+0x24` 的写入点 ⇒ 疑似恒 0（只走 default 运行平均）。需实测裁决 |

## 1. 排除 `LVIEW_FRAMEADD_MTOM`

### 1.1 LVIEW 处理节点枚举（名表 0x8072cc5c 起）

```
8072d03c  LVIEW_FOCUS_PEAKING
8072d050  LVIEW_MULTI_EXPOSURE      <-- 多曝有独立节点
8072d068  LVIEW_PANORAMA
8072d078  LVIEW_FRAMEADD_MTOM       <-- 帧加，MTOM 是拓扑后缀（Memory-To-Memory）
8072d08c  LVIEW_FRAMESUB_MTOM       <-- 帧减，与上者成对
8072d0a0  LVIEW_SMART_FILTER
```

`MTOM` 不是多曝的缩写，是数据通路拓扑：同族还有 `LVIEW_IPC_MTOM`、`LVIEW_LDC_MTOM`、
`LVIEW_RESIZE_MTOM`、`LVIEW_RESIZE_MTOMMMM` 等 40 余项。**ADD / SUB 成对出现**是帧差结构的特征
（NANR 运动检测、水瀑、光轨一类），不是多曝。

### 1.2 still 侧 dump 位表（0x80724ff4 起）

```
ALL / PP / AE-AWB / LRC / FRAME SUB / IPC / LDC / RESIZE×5 / 3D LUT / JPEG×4 / MAKERNOTE
```

**只有 FRAME SUB，没有 FRAME ADD**。若帧加是多曝合成器，still 路径上不可能不出现。

### 1.3 still 多曝是独立 material

RTTI 名字表（Itaniium ABI，长度前缀）：

```
8058bda4  35CMaterial_NX1_Still_Effect_MultiExp
8059ade0  32CMaterial_MultiExposure_Liveview
80574f84  16CMultiExposureIf
8058aca5  19CDriveMultiExposure
8058ae8c  16CDriveMultiFrame
```

`STILL_MULTIEXP` 在 still effect material 名表里与 `STILL_BEAUTYFACE`、`STILL_WATERFALL`、
`STILL_JUMPSHOT` 同级（0x80725470 邻区）。**多曝 = 一个 Still Effect Material**。

## 2. still 多曝的执行体

```
RTTI:  CMaterial_NX1_Still_Effect_MultiExp
typeinfo  0x8058bdcc
vtable    0x8058bd80
  [0] 0x80191954  deleting dtor
  [1] 0x80191988  complete dtor
  [2] 0x8019193c  return 0
  [3] 0x80191944  return 0
  [4] 0x8019194c  return 0
  [5] 0x8016eeec  return 0
  [6] 0x80191d6c  run()          <-- 主执行体
  [7] 0x8016efc8
```

### run() 流程（0x80191d6c .. 0x801921bb）

1. 取 buffer 描述符 `iVar6 = *(FUN_0016f8ec(this,0) + 0xc4)`
2. `FUN_00524194` 取工作缓冲
3. 帧计数：`[ctx+0x28]` = maxCount，`[ctx+0x2c]` = curCount
4. 建 11 组 YCC plane 指针（`FUN_003f3c70`）
5. `FUN_003ff190(ctx)` ← **算法分派在这里**
6. `FUN_00191b3c` 存每帧缩略图（步长 0x9000 = 192×192）
7. curCount == maxCount 时收尾：`FUN_00191a30()` 释放平面

缓冲区尺寸两档：`0x400×0x2ac`（1024×684）与 `0x2d0×0x1e0`（720×480），
由 `FUN_00071eb4(...)=0x340001` 区分。

## 3. 算法分派：switch(ctx+0x24)

`FUN_003ff190` @ 0x803ff190，跳出点在 0x803ff3e4：

```asm
803ff3e4  ldrb  r3, [r5+0x24]     ; mode
803ff3e8  sub   r3, r3, #1
803ff3ec  cmp   r3, #3
803ff3f0  ldrls pc, [pc+r3]       ; 跳转表（Ghidra 未解析，故 4 个 case 反编译成 halt_baddata）
803ff3f4  b     default
803ff3f8  .word 0x803ff408        ; mode 1
803ff3fc  .word 0x803ff568        ; mode 2
803ff400  .word 0x803ff578        ; mode 3
803ff404  .word 0x803ff590        ; mode 4
```

| mode | 目标 | 算法 |
|---|---|---|
| 1 | 0x803ff408 → `FUN_003fe28c` | 累加：先 `FUN_004e32b8(desc, {128,128}, 7)`（Q7，128 = 1.0，纯累加），再 `{128/maxCount, ...}`（归一化） |
| 2 | 0x803ff568 → `FUN_003fe570` | 宽高 **×2** 的叠加（`FUN_003f3eb4(..., w<<1, h<<1, ...)`），非多曝语义 |
| 3 | 0x803ff578 → `FUN_003fe6f0` | 逐像素比较取**暗**（`>>2` 后比 Y 和） |
| 4 | 0x803ff590 → `FUN_003fe64c` | 逐像素比较取**亮**（条件与 mode3 相反） |
| default | 0x803ff45c → `FUN_003feda4` → `FUN_003fea74` | **运行平均**：`FUN_004e3570(desc, 256/(curCount+1), 8, curCount&1)` |

常量确认：`0x8063f2cc` 与 `0x8063f2d0` 都是 `0x00000080`（Q7 的 1.0）。
`FUN_004e32b8` 内 `1 << 7 == gain[1]` 时走快速拷贝路径 —— 即 `maxCount==1` 时不缩放。

**两个「平均」不是同一个东西**：
- default：每帧重新按 `256/(k+1)` 归一 → 累计平均
- mode 1：累加时不动，末尾乘 `128/N` → 事后平均

## 4. `multiexpotype` 的真实语义

capdtm 名字指针表 @ **0x80572670**，共 557 项，索引即 ID：

```
[ 18] USERDATA_MULTIEXPOSURE        枚举 MULTIEXPOSURE_OFF=0 / ON=1        (NUM=2)
[ 19] USERDATA_MULTIEXPOSURETYPE    枚举 MULTIEXPOSURETYPE_SAVEALL=0
                                          MULTIEXPOSURETYPE_RESULTONLY=1    (NUM=2)
[159] VARIABLE_MULTIEXPOSUREMAXCOUNT
[160] VARIABLE_MULTIEXPOSURECURCOUNT
```

⇒ **`multiexpotype` = 保存策略（全部帧 / 只留结果），不是 Add/Average。**
`NUM_OF_MULTIEXPOSURETYPE = 2`，没有第三个值可以承载「添加 / 平均」。

所以按 `multiexpotype` 去找写入点，找到的只会是「存不存中间帧」的开关，
不会通到 `ctx+0x24` 的算法分派。

capdtm 侧（p7 视角）另有两个相关条目：
`806f2d64 CAPTURE_TOPIC_ID_NOTIFY_ALG_MULTIEXP_DISPLAY`、`806f0ab4 E_CAP_NOTIFY_ALG_MULTIEXP_DISPLAY`
—— 名字里带 **DISPLAY**，是预览显示通知，不是成片合成。

## 5. 待裁决

静态未找到 `ctx+0x24`（全局 `*(0x817dc4c4)` 指向的结构内）的写入点。
若它恒为 0，则 p7 只有 default 一条路（运行平均），Add/Average 的差别必须在别处
（用户态归一化、或者 RAW 域合成、或者两者根本一致）。

**实测矩阵**（固定机位、M 档固定曝光、对准均匀灰卡/白墙、N=2）：

| 场景 | 预期（若 p7 区分） | 预期（若 p7 不区分） |
|---|---|---|
| 多曝关闭，单帧 | B0 | B0 |
| 添加，2 帧 | min(255, 2·B0) | ≈ B0 |
| 平均，2 帧 | ≈ B0 | ≈ B0 |

判定：`add - avg` 的中心亮度差 < 2 级 ⇒ 同一条路径。

工具：`tools/mexp/mexp_probe.py <目录> --n 2`（文件名含 base / add / avg 自动归类）。

## 6. 工具与复现

```
tools/mexp/p7.py            VA<->file 映射（file = VA-0x80000000+0x1000）、xref、字符串 dump
tools/mexp/p7dis.py         capstone 反汇编（ARM 态，含 PC 相对字面量池解析）
tools/mexp/rtti.py          RTTI 名 -> type_info -> vtable -> 虚函数表
tools/mexp/scan_refs.py     字面量引用扫描
tools/mexp/ghidra/Dex.java  headless 反编译指定地址（含 caller 列表）
tools/mexp/mexp_probe.py    JPEG 亮度统计与 Add/Average 判定
```

Ghidra 工程 `E:/ghidra_proj/NXKS2`（p7_full.bin, base 0x0）。地址换算：Ghidra = VA − 0x80000000。

```bash
export JAVA_HOME="E:/Android SDK/jdk21"
"E:/ghidra_12.1.4_PUBLIC_20260921/ghidra_12.1.4_PUBLIC/support/analyzeHeadless.bat" \
  /e/ghidra_proj NXKS2 -process p7_full.bin -noanalysis \
  -scriptPath "E:/NXWA/tools/mexp/ghidra" -postScript Dex.java "out" 0x80191d6c
```

坑：`Dex.java` 里不能用 `getReferenceManager()`（GhidraScript 无此方法），要用 `getReferencesTo()`。
