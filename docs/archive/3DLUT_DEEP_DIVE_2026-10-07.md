# NX500 3D LUT 深度调查档案（2026-10-07）

> **本文档记录 2026-10-07 上午的调查全过程与结论。**
> 状态：**API 通路已通**；**偏色未解决**（根因已收窄到「表格式」）
> 关系：本文是 [`3DLUT_API_GUIDE.md`](3DLUT_API_GUIDE.md) 的**深入版**，
> 记录了GUIDE 未展开的否证过程、寄存器全图、p7 侧逆向与地址空间模型。

---

## 0. ★ 三十秒速查

| 问题 | 答案 |
|---|---|
| 今天最大的收获是什么？ | ★★★ **官方流程是三步，我只做了两步**（漏了中断等待） |
| LUT 表格式确定了吗？ | ★ **否**。而且**寄存器里根本没有格式字段**（见 §3） |
| 偏色的根因范围？ | ★★ 已收窄到「表数据格式」，排除轴序/参数/表长（§2） |
| p7 能读 Linux CMA 吗？ | ★★★ **能**（identity 映射 4GB，§6） |
| Linux 能读 p7 的表吗？ | ✘ **不能**，所有通道都已排除（§7） |
| 官方数据入口（IPCC）能用吗？ | ✘ `IPCC_INIT` 触发 **p7 (A9) Oops**（§8） |
| ★ 结论 | **这是个工程量问题**：要继续需改 p7 固件 |

---

## 1. ★ 官方流程是三步，我只做了两步

### 1.1 静态分析发现

`sub_3a888`（`libudd5` 里的 LoadLut 实现）**没有等DMA 就返回**：

```c
sub_3a888(p) {
    OnOff(1); Acc_OnOff(0); Acc_OnOff(1);
    switch (p->sel) { case 0/1/2: SetAddress + SetColorFormat... }
    SelLUT(p->sel);
    rw_Start(1);        // ★ 启动 DMA
}                        // ★ push{fp,lr} / pop{fp,pc} —— 无任何等待
```

而 `d5_ep_3dl_load_lut` 的第 4 参数 `timeout` **从未被使用**
（反汇编确认它存进 r3 后未参与任何运算）。

★ 全库交叉引用扫描显示：`load_lut` / `save_lut` / `intr_wait` 家族
**在 libudd5 内部都没有调用者** ⇒ **库不等人，应用程序自己等**。

### 1.2 官方头文件给出的完整答案

```c
D5_EP_INT_ACC_3DLUT_RD_FINISH = 7,  /**< End of Load LUT from DDR on 3DLUT */
D5_EP_INT_ACC_3DLUT_WR_FINISH= 8,  /**< End of Save LUT to DDR on 3DLUT */
int d5_ep_udd_acc_intr_init_wait_queue(struct ep_acc_intr_wait_info *);
int d5_ep_udd_acc_intr_wait        (struct ep_acc_intr_wait_info *);
struct ep_acc_intr_wait_info { int timeout_ms; unsigned jpeg_err; intr; }; // 12B
```

### 1.3 实现与实测

`lutapi.arm` 已实现三步流程（`⓪①②③`）：

```
⓪ d5_ep_top_acc_intr_en(RD_FINISH=7)          => 0    ★ 新增，中断使能
① d5_ep_udd_acc_intr_init_wait_queue(1000ms)  => 0
② d5_ep_3dl_load_lut(virt, sel=0, fmt=1, 0)   => 0
③ d5_ep_udd_acc_intr_wait(RD_FINISH)          => 1000 ★ 仍等不到
```

★ **方案 A 确实生效了**：加 `intr_en` 之后，内核的
`EP_IOCTL_ACC_INTR_WAIT fail`（`d5_ep_ioctl.c:251`）**不再出现在 dmesg**。
但中断仍不来。

★ 返回值精确等于传入的 `timeout_ms`（300→300、1000→1000、2000→2000），
而内核头文件明确写「超时时返回**负值** `-ETIMEDOUT`」⇒ **中断确实没来**。

---

## 2. ★★★ 偏色调查：7 张表与 3 次模型否证

### 2.1 观测汇总（唯一可信的画面层数据）

| # | 表内容 | 画面表现 | 推出的信息 |
|---|---|---|---|
| 1 | 全 `0x0000` | 粉红/洋红 | 0 是色度极值 |
| 2 | 全 `0x8000` | **品红** | ★ 数值中点**不是**中性 |
| 3 | 全 `0xFFFF` | 青绿/品偏 | 与 #1 对称 |
| 4 | 17 段渐变 `0x0000→0xFFFF` | 均匀粉红，**无分带** | 索引未覆盖全表 |
| 5 | 棋盘格（相邻交替 0/FF） | 均匀，**无图案** | ★ 探针频率不匹配 |
| 6 | `uniq_seq`（每节点唯一值） | **淡绿白**，轮廓极淡 | 索引确实在动 |
| 7 | `d1_only`（仅 ch0 渐变） | 品红（与 #2 相同） | ★ **ch0 变化无影响** |

### 2.2 ★ 三次理论推演被自己的数据否证

```
推演 1：全 0 → YCbCr(0,0,0) → 绿色；实际粉红      ✗
推演 2：全 0xFFFF → YCbCr(1,1,1) → 品红；实际青绿 ✗
推演 3：全 0x8000 = 中性 → 应无色偏；实际品红    ✗
```

⇒ 任何「输出直接映射为 RGB 或 YCbCr」的模型都与观测矛盾。

★ 已排除的维度：

| 维度 | 试验 | 结果 |
|---|---|---|
| 表尺寸 | 17³ (29478B) / 33³ (215622B) | 症状相同 ⇒ 不是主因 |
| 轴序 | 6 种排列（`gen_axis.py`） | 全偏色，方向不同 |
| 参数 | 6 组 `fmt × cbcr_ch` | 无一中性 |
| 调用顺序 | 补调 `op_init` | 仍偏色 |
| 通道 | `d1_only` / `d2_only` / `d3_only` | ch0 不影响画面 |

---

## 3. ★★★ 寄存器全图：格式字段根本不存在

`lutapi.arm regdump` 已扩展为完整 4096 字节 dump。实测：

```
3D LUT @ 0x2082b000 size=4096
★ 4096 字节 = 16 组【完全相同】的寄存器副本（每组 0x100）

每组 6 个非零项：
  +0x000 OnOff = 0x00000001
  +0x004 Cfg   = 0x00000100   bit8=1SelLUT=0  CbCr=0
  +0x008 Pulse = 0x00000000
  +0x00c LUT0  = 0x81115200   ★ 指向 p7 内存
  +0x010 LUT1  = 0x00000000
  +0x0fc       = 0x13020619   ★ 全区重复 16 次，此前从未被读过
```

⇒★★★★★ **没有「表深度」「维度数」「是否 2D 模式」等任何格式字段**

⇒ ★★★ **「索引只用部分维度」是硬件硬编码的，不是寄存器可配的**
⇒ ★★ 这直接解释了 §2 的观测 #7：`d1_only` 无反应而 `uniq_seq` 有反应
⇒★ **继续试表无法解决维度问题**

★ `libudd5` 只暴露 5 个寄存器偏移（`0x00/0x04/0x08/0x0c/0x10`），
　反汇编确认 `SetReg` 分别写 `base+0x0c`（LUT0）与 `base+0x10`（LUT1）。

---

## 4. ★ `load_lut` 没有长度参数

```c
int d5_ep_3dl_load_lut(unsigned *virt, int sel, int fmt, unsigned timeout);
//                     ^^^^ 地址          ^^^ 格式        ★ 无size

// _udd_ep_3dl_reg_SetAddress @0x1fea4
ldr r3,[r3] ; add r2, r3, #0xc ; ldr r3,[fp,#-8]  → SetReg(base+0x0c, addr)
                                              ★ 全表无任何长度寄存器

// _udd_ep_3dl_reg_SetColorFormat_LUT0 @0x1fc04
uxtb r3,r3,#0 ; and r3,r3,#1 ; bfi r3,r2,#8,#1
                  ↑ 只取 bit0 ★ 塞进 Cfg 的 bit8
```

⇒ `fmt` 只影响 `Cfg` 的 bit8（420/422 采样格式），**与表长无关**
⇒ ★★ **DMA 搬运长度完全由硬件决定，用户态无法指定**

### 4.1 ★ `ipcc_write_pkt` 的结构（权威）

```c
struct ipcc_buf_info {
    int            core_id;    // +0
    unsigned int   len;        // +4
    int            ret;        // +8
    unsigned char *buf;        // +12
};  // 12 字节（ARM EABI 32位）
```

---

## 5. ★★★ p7 侧 `load_lut` 完整实现（与 libudd5 交叉验证）

p7 固件里有一份**同源实现**，两边交叉验证通过：

| 证据 | p7 侧 | libudd5 |
|---|---|---|
| 参数边界 | `sel < 3 && fmt < 2` | `sel > 2 → -1`、`fmt > 1 → -1` |
| `sel==2` 行为 | 写两条通道 | `sub_3a888` case 2 写 LUT0+LUT1 |
| 前导序列 | `OnOff(1); Acc(0); Acc(1)` | 同|
| 错误码 | `-300` | `D5_EP_ERR_3DLUT = -300` |

### 5.1 完整调用链

```c
View::_load  (FUN_0011e20c)
  ├─ FUN_000f6474()                 // GetDataPocket()：取数据口袋
  ├─ FUN_000f1b58()                 // 读param_1[0x3a]
  ├─ 若 == 0 → FUN_0009a3e8()       // ★ 静态 4 档（纯查 4 个指针）
  └─ 若 != 0 → FUN_0009a408()       // 动态 24 档
        ↓
  FUN_00179314(表, 0, bypass, 0)
     └─ FUN_004a5c44(ptr, sel, fmt)      // 校验层
          └─ FUN_004a5e30(&packed)      // ★★★ 真正的 load_lut
```

### 5.2 `FUN_004a5e30` 揭示的结构体布局（★ 权威）

```c
FUN_004a5e30(int param_1, ...) {
    if (param_1[+1] == 1) {          // ★ [1] = 操作模式：1=Load 2=Save
        FUN_004cf3d4(1);             // OnOff(1)
        FUN_004cf45c(0);             // Acc(0)
        FUN_004cf45c(1);             // Acc(1)
        cVar1 = param_1[+0xc];      // ★ [0xc] = sel (0/1/2)
        if (sel == 1) { FUN_004cf4b4(*(ptr*)[+8], ...);    // +8 = LUT1 描述符
                        FUN_004a5de4(sel, *(u8*)(*(int*)[+8] + 8)); }
        if (sel == 0) { FUN_004cf4b4(*(ptr*)[+4], ...);    // +4 = LUT0 描述符
                        FUN_004a5de4(sel, *(u8*)(*(int*)[+4] + 8)); }
        if (sel == 2) { ★★ 两条都做 }
    }
    else if (param_1[+1] == 2) { ... }// Save 路径
}
```

⇒ ★★★ **描述符的 `+8` 字节就是 `fmt`**
　　（`FUN_004a5de4(sel, *(u8*)(descriptor + 8))`）

### 5.3 p7 的 4 个静态档（★ 关键）

```c
undefined4 FUN_0009a3e8(ctx, fmt, cbcr) {     // ★ 纯查表，无任何转换
    uVar2 = DAT_003837f4; uVar1 = DAT_003837f0;
    if (param_3 != 1) { uVar2 = DAT_003837fc; uVar1 = DAT_003837f8; }
    if (param_2 == 1) { uVar2 = uVar1; }
    return uVar2;
}
```

镜像偏移处的实际内容（与实机`regdump` 双向一致）：

| 变量 | 值 | 档位 |
|---|---|---|
| `DAT_003837f0` | `0x810fd100` | 标准 |
| `DAT_003837f4` | `0x81101e00` | 黑白 |
| `DAT_003837f8` | `0x81106b00` | 电影 |
| `DAT_003837fc` | `0x81115200` | 肤色 ★ 当前生效 |

---

## 6. ★★★ p7 地址空间模型：identity 映射 4GB

p7 的 MMU 初始化代码（`FUN_00000140`，capstone 已核对）：

```c
coproc_moveto_Control(uVar2 | 0x30000400);       // 开 MMU
uVar2 = DAT_00000240;                // = 0x402
puVar3 = (uint *)&DAT_81000000;      // 页表基址0x81000000
uVar4 = 0;
do {
    *puVar3 = uVar4 | uVar2;         // PTE[i] = (i*1MB) | 0x402
    uVar4 += 0x100000;
} while (uVar4 != 0);                // ★ 4096 项，覆盖 0x0-0xF0000000

puVar5 = 0x80000000; puVar3 = 0x81002000;
do {
    *puVar3 = (uint)puVar5 | 0x1c0e;  // 第二轮：0x80000000-0x80FFFFFF
    puVar5 += 0x100000;
} while (puVar5 != 0x81000000);      // ★ 只 16 项
```

### 6.1 逐地址解算

| 地址 | 用途 | PTE | 归属 | 结论 |
|---|---|---|---|---|
| `0x8f800000` | **Linux CMA 第二区** | `0x8f800402` | 第2296 号槽 | ★★★ **p7 可见** |
| `0x94411000` | CMA 第一区 | `0x94400402` | 第 2372 号槽 | ★ p7 可见 |
| `0x810fd100` | p7 静态档（标准） | `0x81000402` | 第 2064 号槽 | ✔ |
| `0x81115200` | p7 静态档（肤色） | `0x81100402` | 第 2065 号槽 | ✔ |

⇒ ★★★ **第一轮是 identity 映射（VA == PA），覆盖 0–3840MB**
⇒ ★★ 第二轮只改 `0x80xxxxxx` 段属性（`0x1c0e` = coarse page），不影响 `0x8f` 段

### 6.2 双核结构实证

内核崩溃打印里出现 `CA9 user fault`，结合 `d5_lib.h`：

```c
enum d5_intr_type {
    INT_IPCC_CA7_1, INT_IPCC_CA7_2,      // ★ CA7 = Linux (Cortex-A7)
    INT_IPCC_CA9_1, INT_IPCC_CA9_2,      // ★ CA9 = p7   (Cortex-A9)
    INT_IPCC_CM4_1, INT_IPCC_CM4_2, INT_IPCC_CM4_3,   // CM4 = 协处理器
    INT_IPCC_SRP, INT_IPCC_MAX, ... };
```

⇒ **相机 = CA7（Linux）+ CA9（p7）+ CM4（协处理器）三核**

---

## 7. ★ Linux 读 p7 内存：所有通道都已排除

| 通道 | 实测结果 |
|---|---|
| `/dev/mem` | ✘ **整体不可用**（连已知可读的 `0x2082b000` 也 Bad address） |
| `/proc/iomem` | ✘ 空 |
| `/proc/maps` | ✘ 只有普通用户段 |
| EP `GET_PHYS_REG_INFO` | ✘ 只给 `0x2082b000`（硬件寄存器） |
| SMA `/dev/d5_sma` mmap | ✘ 受 region 限制 |
| IPCC | ✘ 见 §8 |

⇒ ★★★ **`/dev/mem` 在这台机器上整体不可用**（内核未开 `CONFIG_STRICT_DEVMEM`）
⇒ ★★ 这修正了早期「p7 内存不在 Linux iomem」的判断 —— 真因是**根本没有读取通道**

### 7.1 完整地址空间模型

```
┌─ p7 (Cortex-A9) ─────────────────────────┐
│ identity 映射 0x0-0xF0000000（4GB）      │
│ 有效：0x80xxxxxx（镜像）+ 0x81xxxxxx（堆）│
│ 静态档表：0x810fd100 ... 0x81115200       │
└──────────────────────────────────────────┘
┌─ Linux (Cortex-A7) ─────────────────────┐
│ CMA 可用：0x94000000(144MB) / 0x8f800000  │
│ 读不到 p7 内存（无通道）                 │
└──────────────────────────────────────────┘
            ↓ 同一片 DRAM ↓
```

⇒ **两套软件地址空间，物理内存共享**
⇒★ p7 能看到 Linux CMA；**Linux 看不到 p7 的表**

---

## 8. ★★★ IPCC 官方接口：API 齐全但 p7 Oops

### 8.1 完整的官方 API（`ipcc.h:28-37`）

```c
intipcc_open(void);
void      ipcc_close(void);
void      ipcc_int_set_callback(enum d5_intr_type, void (*)(void));
unsigned int ipcc_get_write_available(int core_id);
unsigned int ipcc_get_read_available(int core_id);
unsigned int ipcc_get_read_pkt_lenth(int core_id);
unsigned int ipcc_read_pkt (unsigned char *buf, int core_id, unsigned len);
unsigned int ipcc_write_pkt(unsigned char *buf, int core_id, unsigned len);
unsigned int ipcc_raw_send_interrupt(enum d5_intr_type);
```

`libudd5` 导出 **14 个 `ipcc_*` 符号，全部 `STB_GLOBAL`**，实测 12 个可 `dlsym`。

### 8.2 绕过库锁：裸 ioctl 可行

`ipccraw.c` 成功用 `open("/dev/d5_ipcc")` + 裸 `ioctl` 绕过 `libudd5` 的
`pthread_mutex` + `d5_udd_open(2,1)` 锁。

★ **但 ioctl 号必须以库实测为准**（见 §8.4）。

### 8.3 ★★ `IPCC_INIT` 触发 p7 (A9) Oops

```
ipccraw.arm scan ⇒ 进程被内核杀，零输出
dmesg:
  [<c00c91dc>] (sys_ioctl+0x74/0x7c) from [<c000eb00>] (ret_fast_syscall)
  ret = 0                              ← open 成功
  A9 kernel fault(Oops - BUG)          ← ★★ p7 侧崩溃
  ---[ end trace 8dd9f487dc7dedaa ]---
相机存活（loadavg 正常，SSH 通，音频通路继续）
```

⇒ ★★★★ **`IPCC_INIT` (0xc0087401) 会让 p7 崩溃**
⇒ ★★ 这解释了 `ipccprobe` 走 `ipcc_open()` 时的段错误 ——
　不是库加锁失败，**是 IPCC 初始化本身会让 p7 崩**

### 8.4 ioctl 号（★ 权威 = libudd5 实测，勿用头文件宏）

| 名称 | 值 | 与 NX1 GPL 头文件对比 |
|---|---|---|
| `IPCC_INIT` | `0xc0087401` | — |
| `IPCC_GET_WRITE_AVAIL` | `0xc0087403` | ✔ 一致 |
| `IPCC_GET_READ_AVAIL` | `0xc0087404` | ✔ 一致 |
| `IPCC_GET_READ_PKT_LENTH` | `0xc0087405` | ✔ 一致 |
| `IPCC_READ_PKT` | `0xc0107406` | ✘ 头文件算 `0xc00c7406`（size 12 vs 16） |
| `IPCC_WRITE_PKT` | `0xc0107407` | ✘ 同上 |
| `IPCC_RAW_INT_WAIT` | `0xc008740b` | ✘ 头文件 nr=10，库实测 nr=11 |

⇒★★★★★ **NX1 GPL 头文件与实机 `libudd5` 的 ioctl size/nr 定义不一致**
　⇒ ★ **必须以库实测值为准**

---

## 9. ★ 官方数据入口：p7 侧的实现

`FUN_000f6474` 是「取数据口袋」。它的 DAT 常量二级解引用后：

```
DAT_000f655c -> 0x806ede0c  "Assertion Failed! %s --- File %s Line %d\n"
DAT_000f6560 -> 0x8070eed4  "product/Liveview/common/CLiveviewFactory.cpp"
DAT_000f6564 -> 0x8070dcc0  "m_pcLiveviewDataPocket != __null"
DAT_000f6568 -> 0x806ede04  "ASSERT"
DAT_000f656c -> 0x8057e458  "GetDataPocket"          ★ 方法名
```

⇒ ★★★ **「数据口袋」是三星官方命名**（`GetDataPocket`）
⇒ ★ 源文件：`product/Liveview/common/CLiveviewFactory.cpp`

★ **解引用技巧**：DAT 变量（Ghidra 地址 `0x000f6xxx`）里存的是运行时装载
地址 `0x8xxxxxx` ⇒ `file offset = va - 0x80000000`
⇒ ★★ 这是绕开「字符串 xref 恒为 0」的办法

### 9.1 它不是 socket

PAL 层全是系统调用 stub：

```c
FUN_004d9ee8(){ software_interrupt(6); }   // recv
FUN_004d9a8c(){ software_interrupt(6); }   // send
// 全库 SVC 统计：#0x08 × 105、#0x06 × 86、#0x09 × 7
```

⇒ SVC 处理器**不在 `p7_full.bin` 里**（那是用户态镜像）
⇒ 相机侧验证：`/proc/net/tcp` 监听 `21/22/23/53/80/8080`，**无 p7 IPC 端口**；
`/proc/net/unix` 全是 X11/dbus/pulse/alsa
⇒ ★★★ **数据口袋不经过 socket**（共享内存 / 邮箱 / IPC）

---

## 10. ★★ 「复用 p7 官方通路」方案的判定

| 方案 | 做法 | 判定 |
|---|---|---|
| **A** | 改 p7 的 `DAT_003837f0` 指向我的表 | ✘ **Linux 无写入 p7 内存的通道** |
| B | 改 p7 固件二进制里的指针初值 | ✘ 需重刷 p7，风险高 |
| C | 灌 identity 表让画面中性再叠加 | ✘ 至今没做出中性表 |

★ 方案 A 的物理前提①②③：
① 改 p7 指针 → **✘ 所有通道已排除（§7）**
② p7 访问 Linux CMA → **✔ 可以（§6）**
③ p7 是否会覆盖回来 → 未测

---

## 11. ★★★ 工具清单（今日新增）

| 工具 | 用途 | 状态 |
|---|---|---|
| `test_server/sysarch/ipccprobe.c/.arm` | IPCC 符号解析 + `ipcc_open` 探测 | ★ `scan` 会段错误（p7 Oops） |
| `test_server/sysarch/ipccraw.c/.arm` | **裸 ioctl IPCC**（绕过库锁） | ★ `scan` 触发 A9 Oops |
| `test_server/filmsim/coverprobe.py` | 覆盖探针（全零/全FF/half） | ✔ 自检通过 |
| `test_server/filmsim/ramp.py` | 阶梯渐变探针（17 段 u16） | ✔ 自检通过 |
| `test_server/sysarch/lutapi.c` | `regdump` 扩展为**完整 4096B dump** | ✔ 已上机 |

探针表（`test_server/sysarch/verify/`，已被 `.gitignore` 忽略）：

```
pz_14739/19652/29478/39304.bin   全零，不同长度
pf_29478.bin                    全 FF
ph_29478.bin                    前半 FF 后半 00
ramp16.bin / ramp8.bin          阶梯渐变
chk_alt.bin / chk_axes.bin      棋盘格
uniq_seq.bin                    每节点唯一值
d1_only / d2_only / d3_only.bin 单维渐变
pfx_000006 .. pfx_029478.bin    前 K 字节 FF
```

---

## 12. ★★★ 方法论教训（今日新增，全部来自实际翻车）

### 78★★ 判读前必须先排除显示链路特征

我在**用手机拍 LCD** 的条件下判读画面，屏幕的像素栅格、摩尔纹、亮度不均
全部混进信号。**连续三次把显示特征当成了数据伪影**：

| 我说的 | 实际 |
|---|---|
| 「撕裂纹理」 | 用户桌面的木纹 |
| 「彩色点阵」 | AMOLED 子像素结构 |

⇒ ★ 偏色/色偏类实验中，**「图像结构是否完整」最容易被误判**，
　因为色度 LUT 出错时亮度直通，结构天然完整

### 79 ★★ 厂商 GPL 头文件 ≠ 实机库实现

`ipcc_read_pkt` 头文件算 `0xc00c7406`，实机库用 `0xc0107406`（size 字段 16 vs 12）。
★ 我在 ioctl 编码上**连错 3 次**（type/nr 顺序、size 字段、`RAW_WAIT` 的 nr）
⇒ ★★ **同一类错误连续犯 3 次 = 该换方法**
　　正确做法：直接从 `movw/movt` 立即数读，不要手写位域提取

### 80 ★★ 提「时序/竞争」类假设前，先算量级

我曾假设「没等 DMA 中断 → 表是半成品 → 色阶断裂」：

```
29478 字节÷ DDR2 2GB/s = 14.74 µs
我等的 settle      = 200000 µs    ← 十万倍
```

⇒ ★★★ **表内容在 200ms 前就完整了**，该假设物理上不成立
⇒ ★ 绕道「等中断」这条线，即使做通也不会解决偏色

### 81 ★★ 探针的空间频率必须匹配被测信号

棋盘格探针（周期 2）在索引跳变步长更大时，图案互相抵消，
看起来像「表没被读」—— 而 `pfx_000006`（只改 6 字节）却产生强图案。
⇒ ★ **「精心设计的探针无反应」时，先怀疑探针的假设**

### 82 ★★ 跨进程/跨核的内存映射要自己算

p7 页表在 `0x81000000`，而 Linux 侧 `/dev/mem` 不可用。
⇒ ★ 判据：**地址空间是各自的，物理内存才是共享的**

---

## 13. ★ 结论与下一步

### 13.1 已彻底走通（可复用）

```
★ 官方用户态 API（op_init + load_lut，sel=0 不花屏）
★ CMA 落点探测（双区 + 可调粒度，216MB @ 116ms）
★ 3D LUT 寄存器全图（16 组副本，格式字段硬编码）
★ p7 完整调用链 + 与 libudd5 交叉验证（同源实现）
★ p7 地址空间模型（identity 映射 4GB，双核 CA7+CA9+CM4）
★ IPC 官方 API（12 符号全解析，裸 ioctl 可绕过库锁）
```

### 13.2 卡住的两点

```
✖ 偏色：LUT 表格式（维度硬编码 + readback 不可用）
✖ 数据口袋写入（IPCC_INIT → p7 A9 Oops）
```

⇒ ★★ **两者都需要改 p7 固件** —— 属另一量级工程

### 13.3 ★★ 顺序反思

> 我花了 7 张表、3 次模型否证去猜 LUT 格式 ——
> 而**格式其实由 p7 决定**。正确顺序应该是**先打通数据口袋，再谈格式**。

⇒ ★ 若重来，第一件事应该是查 IPCC 而不是灌第一张表

---

*文档结束。配套：[`3DLUT_API_GUIDE.md`](3DLUT_API_GUIDE.md)（操作手册）、
[`LIBUDD5_EP_API_MAP_2026-10-06.md`](LIBUDD5_EP_API_MAP_2026-10-06.md)（API 地图）。*
