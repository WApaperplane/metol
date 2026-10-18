# NX500 3D LUT 完全指南（官方 API 路线）

> ⚠️ **2026-10-18 文档清理：本文结论已被取代。** 本文描述的是「官方 API 路线」（`lutapi` + CMA + 守护），**已不是当前主线**；作为 LUT API 参考仍有价值。
> 现行结论见 [`LUT_RETARGET_LIVE_2026-10-18.md`](LUT_RETARGET_LIVE_2026-10-18.md)。


> 最后更新：2026-10-07 00:00
> 目标机：NX500 / 固件 1.12 / Linux drime5 3.5.0
> 状态：**花屏已解决**；**偏色问题未解决**（色彩空间假设待验证）

---

## 0. 一页速查

| 问题 | 答案 |
|---|---|
| 3D LUT 能从用户态灌入吗？ | ★★★ **能**。官方 API `d5_ep_3dl_load_lut()` |
| 需要改固件吗？ | ★★★ **不需要**。不动p7、不动内核 |
| 会花屏吗？ | ★★★ **不会**（用 `sel=0` 灌厂商通道） |
| 为什么上午会花屏？ | 我改`+0x00c` 让 ISP 去读一个"数据口袋体系"外的地址 |
| 灌进去后 p7 会覆盖吗？ | ★★ **会**。`View::_load` 每次都重设 `+0x00c` |
| 表格式确定了吗？ | ★ **否**。29478 / 19652 两个数都已被否证 |
| 偏色根因 | 疑似色彩空间（RGB vs YCbCr），**未验证** |

**唯一正确的操作命令**：
```sh
/opt/usr/nx-ks/cmapick2.arm 1024 32          # ★ 每次 load 前必跑（铁律 61）
/opt/usr/nx-ks/lutapi.arm load <file> <落点> 0 1 17 2 300 0
                                       ↑sel=0 ★★ 关键：厂商通道，不花屏
```

---

## 1. ★ 核心发现：三星留了用户态入口

### 1.1 官方 API（NX1 GPL 源码，`usr/include/drime5/udd/ep.h`）

```c
int d5_ep_3dlut_op_init (d5_ep_lut_op_info_st *);   // 配置通道/格式
int d5_ep_3dl_load_lut (unsigned *, sel, fmt, timeout);  // 灌入 LUT
int d5_ep_3dl_save_lut (unsigned *, sel, fmt, timeout);  // ★ 读回（实测无效，见 §6）
```

枚举定义（`ep_type.h`，注释是原文）：
```c
D5_EP_LUT_FORMAT_422 = 0    /**< Color Format of input image  YCC422 */
D5_EP_LUT_FORMAT_420 = 1    /**< YCC420 */
D5_EP_LUT_CBCR_CH0  = 0     D5_EP_LUT_CBCR_CH1 = 1     D5_EP_LUT_CBCR_CH01 = 2
D5_EP_LUT_SEL_LUT0  = 0     D5_EP_LUT_SEL_LUT1 = 1
D5_EP_LUT_SEL_LUT_EXT = 2  /**< ★★ Select Look-up-table Externally */
```

### 1.2 ★★ `SEL_LUT_EXT` 就是"外部 LUT"

这条注释是整个项目的突破口：
> `D5_EP_LUT_SEL_LUT_EXT = 2` — **"Select Look-up-table Externally"**

⇒ 三星本来就设计好了让用户态灌自定义 LUT，不需要改固件。

### 1.3 libudd5.so 导出 23 个 LUT 符号（全部可 dlsym）

```
用户态  d5_ep_3dlut_op_init / d5_ep_3dl_load_lut / d5_ep_3dl_save_lut
库层    _udd_ep_3dl_ctrl_{ConfigAccessMode,ConfigBypassMode,ConfigProcessMode}
寄存器  _udd_ep_3dl_reg_{OnOff,Acc_OnOff,SelCbCr_ch,SelLUT,rw_Start,
                       SetAddress,SetColorFormat_LUT0/LUT1,SetReg,GetReg}
DMA     _udd_ep_{mux,demux}_3dlut_{wdxi,rdxi}
```

---

## 2. ★★★ 三个必须知道的坑

### 坑 1：不调 `d5_ep_open()`，一切 API 静默失效

`d5_ep_sma_virt_to_phys()` 反汇编（libudd5 @0x2175c）：
```c
unsigned d5_ep_sma_virt_to_phys(unsigned virt) {
    if (g_d5_dev_ctx < 0) return 0;      // ★★ 我们进程没有设备句柄 ⇒ 直接短路
    if (virt == 0)        return 0;
    if (ioctl(g_d5_dev_ctx, 0xc0047302, &virt) < 0) return 0;
    return virt;
}
```

**现象**：`lutapi.arm probe` 四个 CMA 地址全部返回 0
**对照**：`v2p.arm`（自己 open + 裸 ioctl）同一时刻完全正常（`0x99000000`）
**根因**：**它用的就是同一个 ioctl 号**，唯一差别是进程内有无设备句柄

⇒ ★★ **`malloc` / 匿名 mmap 返回 0 的真因不是"不被支持"，而是函数根本没执行到 ioctl**

**正确做法**：
```c
d5_ep_open();                 // ★ 必须！返回 0 = 成功
// 然后 ep_3dlut_reg_base 从 0x00000000 变成非 0（如 0xb6f84000）
d5_ep_close();
```
前提：相机**不在拍摄态**（无进程持有 `/dev/drime5_ep`）。用 `ls /proc/*/fd` 逐个查。

### 坑 2：缓冲区必须是 `/dev/d5_sma` 的 mmap

```c
malloc / 匿名 mmap  ⇒ virt_to_phys 返回 0（无句柄）
mmap /dev/d5_sma   ⇒ ★★ 精确返回物理地址
```
⇒ 强制用 `open("/dev/d5_sma")` + `mmap(phys)`，并用 `virt_to_phys` 核对。
⇒ ★★ **`munmap` 之后该地址立即失效**，必须在映射存活期内调用。

### 坑 3：`munmap` 后地址作废（23:52 实测）

```
dmesg: d5_uservirt_to_phys:59 invalid userspace address=b6f39000
```
⇒ 驱动认得这个 ioctl，只是拒绝"已失效"的地址。

---

## 3. ★★ `sel` 的选择（花屏的唯一决定因素）

| sel | 含义 | 实测 |
|---|---|---|
| **0** | LUT0（厂商自己的档） | ★★★ **用它，不花屏** |
| 1 | LUT1 | 未测|
| 2 | LUT_EXT（外部） | 能灌入，但 `Cfg` 会被改（`0x100` → `0x1020`） |

**实测对比**：

| | 基线 | `sel=0` | `sel=2` |
|---|---|---|---|
| `Cfg` | `0x00000100` | **`0x00000100`（不变）** | `0x00001020`（被改） |
| `bit8/bit12` | 1 / 0 | **1 / 0 保持** | 0 / 1 翻转 |
| `SelLUT` | 0 | **0 保持** | 2 |
| 花屏 | — | ★ **无** | ★ 高 |

⇒ ★★ **`sel=0` 时官方 API 只写地址，不动 `Cfg`** —— 这是"厂商通道"该有的行为
⇒ ⇒★ **上午花屏的真因**：让 ISP 去读一个"数据口袋体系"外的地址；
而 `sel=0` 是**厂商自己在用的通道**，通过官方 DMA 填它 ⇒ 完全合法

### 官方流程是两步，不能只做一步

```c
d5_ep_3dlut_op_init(&info);    // → ConfigProcessMode → 写 Cfg 寄存器
d5_ep_3dl_load_lut(...);       // → 写地址 + DMA 灌数据
```
`ConfigProcessMode`（@0x3abb4）反汇编：
```c
_udd_ep_3dl_reg_OnOff(1); Acc_OnOff(1); Acc_OnOff(0);
SelCbCr_ch(p->+0x14)          -> Cfg bits[1:0]
SelLUT(p->+0x10)              -> Cfg bits[5:4]
SetColorFormat(sel, p->+0x18) -> Cfg bit8/bit12
```
★ `lutapi.arm load` 已自动先调 `op_init`。

---

## 4. ★★ CMA 落点（铁律 61）

### 4.1 `/dev/d5_sma` 只报告一个 region

```
ioctl(SMA_GET_REGION_START_ADDR) => 0x94000000, size 0x09000000 (144MB)
★★ 但 dmesg 显示：cma: reserved 288MiB at 94000000 / 72MiB at 8f800000
⇒ ★★ 第二个 72MB 区只能从 dmesg 硬编码，ioctl 不会告诉你
⇒ ★★ "没报错"不等于"只有一个区"
```

### 4.2 实测占用情况（2026-10-06 23:10）

```
region#1  0x94000000  144MB  ⇒★ 全非零（ISP 完全占用）
region#2  0x8f800000   72MB  ⇒ 部分非零，连续全零 4096 KB ★
```
⇒ ★★ **v1 工具漏掉的正是这块**。差一个区，结论从"必然卡死"变成"有 4MB 可用"

### 4.3 铁律 61 的实测代价

在 `0x94000000` 写表 ⇒ **整机卡死，拔电池才恢复**
```
dmesg: alloc_contig_range test_pages_isolated(...) failed
```
⇒ 那块是 **ISP 的 WDMA 硬件工作区**，"探测到全 zero" ≠ "可安全独占"

### 4.4 每次 load 前必须重跑

同一地址在不同时刻占用状态不同（实测 `0x8f800000` / `0x8f808000` / `0x8f810000` 轮换）。

**扫描耗时**：216MB @1MB 粒度 = **116ms**（瓶颈是缺页中断，不是算力）

---

## 5. ★ 工具

### 5.1 lutapi.arm — 官方 API 工具

```sh
lutapi.arm probe                ★零风险：符号 + d5_ep_open + mmap 探测
lutapi.arm info                 只读：23 个符号
lutapi.arm regdump              只读：3D LUT 寄存器快照
lutapi.arm opinit <sel><fmt><cbcr><bypass>   只配置
lutapi.arm load <file> <phys> [sel] [fmt] [size] [stride] [settle] [cbcr_ch]
lutapi.arm save <out> <phys> [sel] [fmt] [bytes]    ★ 读回无效（见 §6）
lutapi.arm verify <file> <phys> ...     load+save 比对（★ 基于无效的 save）
lutapi.arm idgen <out> [size] [stride]  生成 identity 表
lutapi.arm probe-size <phys> <n> ...    ★ 自检 save_lut 是否有输出
```

编译：
```sh
zig cc -target arm-linux-gnueabi.2.15 -O0 -o lutapi.arm lutapi.c -ldl
```

**五道安全闸**：
1. `load` 强制要求显式物理地址（不许猜）
2. `SMA_VIRT_TO_PHYS` 核对，不匹配立即中止
3. 写入后 `memcmp` 回读校验
4. `ep_3dlut_reg_base == 0` 时拦截（需先 `d5_ep_open`）
5. DMA settle 期间不清零、不 munmap

**★ 安全闸 6（23:58 事故后加）**：`probe-size` 会拒绝写入当前 `LUT0/LUT1` 覆盖的地址

### 5.2 cmapick2.arm — CMA 落点探测

```sh
cmapick2.arm [step_kb] [need_kb]
```
- 双区扫描（`0x94000000` + `0x8f800000`）
- 三态判定：全零 / 部分非零 / 全非零
- 每 4MB `usleep(2000)` 让出（铁律 3）

### 5.3 eptest_open.arm — 专测 `d5_ep_open` 能否工作

```sh
eptest_open.arm
```
`d5_udd_open` 返回值语义：`0`=首次打开成功`1`=已打开 `2`=引用计数++ 负=错误

### 5.4 PC 端转换器

| 工具 | 用途 |
|---|---|
| `filmsim/cube2nx17.py` | `.cube`(33³) → 17³×3×u16，带 `--selftest` |
| `filmsim/rgb2ycc.py` | RGB 表 → YCbCr 表，**★ 假设未验证** |
| `filmsim/ycc_variants.py` | 生成 identity 候选布局，用于实机反推 |
| `isp/udd5dis.py` | libudd5 PLT 感知反汇编器（可复用） |

---

## 6. ★★★★★★ 【重要否证】`save_lut` 读不出硬件表

### 6.1 实测

```
把【全新的、清零的】262144 字节缓冲交给 save_lut：
  save_lut 返回 0，但读回【全零】
9 种组合全扫（sel × cbcr_ch × fmt）⇒ 全部为 0
```

### 6.2 ⇒ 连带作废的结论

|曾断言 | 状态 |
|---|---|
| "硬件表长 = 29478 = 17³×3×u16" | ★★ **不成立** |
| "读回内容与 identity 14739 通道全对" | ★ **作废** |
| "19652 作废，29478 才对" | ★★ **两个都不确定** |

### 6.3 为什么是自证循环

```
我用 load_lut 把表写进 CMA 缓冲 A
再用 save_lut 从缓冲 A 读回
⇒ 读到的是我自己写进去的数据
⇒ 只证明 DMA 读写通路对称，完全不能证明硬件 SRAM 的内容
```

### 6.4 可能原因（待查）

1. ★★★ 读方向需要 `rw_Start(2)`（bit4），官方 `save_lut` 可能没触发
   → 白天手写的 dump 序列用 `rw_Start(2)` 确实读出过数据
2. 读方向要求不同的 `fmt`
3. 硬件表在另一个 SRAM 区，`+0x00c` 只是写入口

---

## 7. ★★ 未解决问题：偏色

### 7.1 现象

| 灌入的表 | 用户观察 |
|---|---|
| Portra 400（RGB 版） | 红偏色明显 |
| Kodachrome 64（RGB 版） | 蓝紫偏色明显 |
| Portra 400（YCbCr 版） | 洋红/绿分离 + 严重色阶断裂 |
| identity 表 | **仍然偏色**（★ 连identity 都不中性） |

**★ 照片确认**：`UI 图标/文字颜色全部正常`，只有画面偏色
⇒ LUT 只作用于图像通路，不碰 OSD 叠加

### 7.2 单通道判别实验（部分完成）

只把某一轴压到 50%：

| 压暗的轴 | 观察 | 推断 |
|---|---|---|
| 第 1 轴 | 画面变暗 + 色彩变浓 | ★ **Y**（亮度） |
| 第 2 轴 | 白墙变鲑鱼色（丢蓝） | ★ **Cb** |
| 第 3 轴 | 待确认 | 预期 **Cr** |

⇒ ★★ 疑似三轴 = **(Y, Cb, Cr)**，与 `YCC420` 命名一致

### 7.3 ★ 失败的假设

| 假设 | 结果 |
|---|---|
| interleaved (Y,Cb,Cr) full-range | ★ 偏色 |
| planar（三个平面分开） | ★ "极其糟糕" |
| 漏调 `op_init` | ★ 已修，但**仍偏色** |

⇒ ⇒★ **连 identity 表都不中性 ⇒ 我的 identity 表本身就不是 identity
⇒ ⇒★★ 说明"索引 ↔ 数值"的对应关系错了，而不只是布局问题**

### 7.4 关键逻辑漏洞

★★ **我用 `save_lut` 读回 29478 字节非零，就断定"表长=29478"**
⇒ 那读到的是**我自己写的数据**，长度当然等于我写的长度
⇒ ★★ **如果真实表是 33³（215622 字节），我写的 29478 只覆盖 1/8 输入域，
　　其余是未初始化垃圾 ⇒ 这就能解释"所有表都偏色"**

### 7.5 下一步（不能再猜）

★ **既然读不出来，就用画面做唯一判据**：
1. ★ 单轴表：只让一个轴偏离identity，观察变化出现在哪个维度
2. ★ 饱和度阶梯：沿Cb 方向线性拉伸，看色度是否线性
3. ★★★ **先排除"表尺寸不足"**：把identity 表做到 215622 字节（33³）看效果
   ⇒ 若表变大后 identity 变中性 ⇒ ★★★ 尺寸就是根因

---

## 8. ★★ p7 会抢回指针

实测（20 次连续采样，1 秒间隔）：
```
[1-6]  LUT0 = 0x8f808000   ← 我灌的地址
[7-20] LUT0 = 0x81115200   ← 半按快门对焦后，p7 抢回出厂表
```

⇒ ★★ p7 的 `View::_load` 每次都重设 `+0x00c`
⇒ ★⇒ **只要不触发 View 重载（不半按快门），我的表就持续生效**
⇒ ⇒★★ **"半按对焦后恢复正常"不是回滚失败，是 p7 正常工作**

`View::_load` 关键代码（capstone 逐层验证）：
```c
FUN_000f6474();                    // ★ socket 收"数据口袋"（688 字节缓冲）
if (FUN_000f1b58() == 0)
     iVar5 = FUN_0009a3e8(ctx, uVar4, uVar3);  // 静态 4 档
else
     iVar5 = FUN_0009a408(ctx, uVar2, uVar3);  // 动态 24 档
FUN_00179314(iVar5, 0, cVar1 != 1, 0);         // 提交
```

---

## 9. ★ 方法论铁律（今晚新增）

| # | 铁律 | 代价 |
|---|---|---|
| 65 | 推翻结论后必须全文回扫所有文档 | — |
| 66 | ★★★★★ **有静态数据源在手时先扒代码，不要钻实验** | 今天白天 11 次实机实验本可避免 |
| 67 | ★★★★★读指令级结论必须用 capstone | — |
| 68 | ★★★★ 判断"是否存在独立数据通路"要找【数据源日志】 | — |
| 69 | ★★★ **PC 端复刻 C 逻辑逐字节比对**才能验证数据生成代码 | 抓到 make_identity 索引方向反了 |
| 70 | ★★★ **自检函数必须和被检函数用同一套映射** | 抓到"自检自己错了" |
| 71 | ★★★★★ **多入口 API 必须先扒清调用顺序**，不能只盯主功能 | 漏调 `op_init` |
| 72 | ★★★★★★ **"写进去能读回来"≠"读回来的是硬件里的东西"** | ★★ **自证循环浪费 3 小时** |
| 73 | ★★★★★ **探测工具必须拒绝写入硬件正在使用的区域** | ★ 清空了生效的表 |

---

## 10. 完整操作手册

### 灌入一张 LUT

```sh
# 1. 相机停在菜单界面（不在拍摄态）
# 2. 选落点（★ 每次必跑）
telnet/ssh: /opt/usr/nx-ks/cmapick2.arm 1024 32
#    记下"4KB 粒度命中：0x........ 起连续 XX KB"

# 3. 灌入（★ sel=0）
/opt/usr/nx-ks/lutapi.arm load /mnt/mmc/luts/<表>.bin 0x........ 0 1 17 2 300 0

# 4. 看取景器 —— 画面应该变化
# ★ 不要半按快门（会触发 p7 抢回指针）
```

### 回滚

```sh
/opt/usr/nx-ks/lutload.arm restore    # 只改指针回 0x81115200，不触发 DMA
然后半按快门对焦                     # 让 p7 重新灌表
```

### 排错

| 现象 | 原因 | 处理 |
|---|---|---|
| 安全闸拦住，`reg_base==0` | 未 `d5_ep_open` | 等相机回菜单界面 |
| `virt_to_phys` 返回 0 | 没用 `/dev/d5_sma` mmap | 检查工具 |
| 花屏 | `sel=2` | ★ 改用 `sel=0` |
| 半按后恢复 | p7 抢回指针 | ★ 正常现象，不用管 |
| 偏色 | 色彩空间未匹配 | 见 §7，**未解决** |

---

## 11. 参考

### 官方文档
- `usr/include/drime5/udd/ep.h` — 3D LUT API 原型
- `usr/include/drime5/udd/ep_type.h` — 枚举定义（注释即权威）

### 本项目文档
- `docs/current/3DLUT_API_GUIDE.md`（本文件）
- `docs/evidence/p7/` — p7 反汇编证据片段
- `docs/evidence/discovery/01..06` — 静态清点报告

### 硬件事实
- EP 3D LUT 寄存器基址 `0x2082b000`，size 4096
- `+0x000` OnOff / `+0x004` Cfg / `+0x008` Pulse / `+0x00c` LUT0 / `+0x010` LUT1
- 出厂 LUT0 = `0x81115200`（肤色档），LUT1 = `0`
- `Cfg` bit8/bit12 = 色彩格式，bits[1:0] = CbCr 通道，bits[5:4] = SelLUT

---

*文档结束。**§6 与 §7 是最重要的两节** —— 前者记录了我的自证循环，后者是唯一未解决的问题。*