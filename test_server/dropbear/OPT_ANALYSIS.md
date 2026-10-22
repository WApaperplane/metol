# -O0 能不能去掉：静态分析

日期 2026-10-22 · 对象 dropbear 2024.86 · 方法：只看编译产物与源码，未上机

---

## 结论先行

1. **能去掉，改 `-O2`。** 静态指标全绿：指令数 −40%、体积 −29%、GLIBC 版本需求不变、**0 条硬件浮点指令、0 条 ldrd/strd**。
2. **`-O0` 这条"铁律"的来源是 Zig 0.13 的 ARM 后端，跟 gcc 无关。** 它被历史泛化成了"所有交叉编译"，但三条原始实证都指向 Zig + 手写底层代码。
3. **`-march=armv7-a` 不划算。** 只再省 1.2% 指令，却引入 125 条 `ldrd/strd`（8 字节对齐要求）。放弃。
4. **★ 但 `-O2` 只贡献了提速的一半。真正的大头是 `nice`**（见第 9 节）：
   Tizen 把 `telnetd` 及其 shell 设成 **nice=19**，dropbear 继承后与 `di-camera-app`(nice=-10) 差 29 级，在单核饱和的机器上只能抢到 13% CPU。把 nice 拉回 0 后：
   **中位 838 → 1645 KB/s（+96%），单张 10.8MB 从 17.1s 降到 6.4s**。

> 已实施：`-O2` + `nice 0`（经 `scripts/dropbear/run.sh` 强制绝对值）。`-O0` 产物备份在 `out/dropbear.arm.O0`。

---

## 1. `-O0` 的溯源：三条实证全指向 Zig

| 出处 | 原文 | 真实场景 |
|---|---|---|
| `docs/archive/HANDOVER_2026-10-07.md:79` | `zig  D:/download/.../zig.exe`<br>`★ 优化级别  必须 -O0 （-O1/-O2 编的 ARM 代码在真机段错误 139，项目历史实测）` | **Zig 0.13.0** 编 ARM softfp |
| `docs/archive/CONSOLIDATED_REPORT_2026-10-05.md:541` | `必须 -O0。-O1+ 实测段错误` + `IOC 宏在 32 位 int 上有符号溢出：(2)<<30 = 0x80000000 ⇒ zig ARM 后端生成非法指令 SIGILL` | **自己代码的 UB**（signed overflow），Zig 的 LLVM 后端在 UB 上生成非法指令 |
| `docs/archive/WORK_REPORT_2026-10-06.md:244` | `-O0 + 自写 mmap + memset/memcpy 可能踩未映射边界（写 256 字节 SIGSEGV，32 字节正常）` | **手写 mmap** 缓冲区的越界写，-O2 会用更宽的存储指令放大它 |

**三条的共同点：Zig 编译器 / 手写 mmap / 手写宏 UB。**

dropbear 是 **gcc 13.3** 编的普通 C 程序：
- 无手写 `mmap`
- 无内联汇编（`grep` 全源码为 0）
- 浮点只出现在 `dbutil.c` 的调试计时和 `progressmeter.c` 的进度百分比，**不在数据路径**

⇒ 这条约束对 dropbear 不适用。

## 2. 静态安全指标（实测编译产物）

| 构建 | 体积 | ARM 指令数 | VFP/NEON | ldrd/strd | movw/movt | GLIBC 需求 | NEEDED |
|---|---|---|---|---|---|---|---|
| `-O0`（现役） | 336,732 | 58,565 | **0** | **0** | 0 | 2.4 | libc/libutil/libcrypt |
| **`-O2`** | **239,744** | **34,968** | **0** | **0** | 0 | **2.4** | 同 |
| `-O2 -march=armv7-a -mtune=cortex-a9` | 213,472 | 34,539 | **0** | ⚠ **125** | 2,759 | 2.4 | 同 |

- **VFP/NEON = 0** ⇒ 不会碰 VFP 上下文，不受内核 `CONFIG_VFP` 影响，`-mfloat-abi=soft` 的 ABI 假设完好。
- **GLIBC 需求仍是 2.4** ⇒ 相机 glibc 2.13 完全兼容，ABI 没漂移。
- `-O2` 相对 `-O0`：**指令 −40%，体积 −29%**。
- `armv7a` 相对 `-O2`：指令只再 −1.2%，但多出 125 条 `ldrd/strd`（8 字节对齐要求）⇒ **不值得**。

## 3. 收益从哪来（热点文件指令数）

| 文件 | -O0 | -O2 | 缩减 |
|---|---|---|---|
| poly1305.c | 1873 | 491 | **−73%** |
| aes.c | 1622 | 945 | −41% |
| sha256.c | 596 | 338 | −43% |
| packet.c | 1194 | 681 | −42% |
| common-channel.c | 2371 | 1590 | −32% |
| bn_mp_mul.c | 96 | 44 | −54% |
| **合计** | **7752** | **4089** | **−47%** |

实际传输走的是 **chacha20-poly1305@openssh.com**（`src/common-algo.c:128` 里排第一，优先级最高），即 ChaCha20 + Poly1305 两个纯整数 ARX 算法 —— Poly1305 那 **−73%** 直接落在数据路径上。

libtomcrypt **没有 ARM 汇编加速路径**（`grep LTC_ARM` 为空），所以收益 100% 来自编译器优化，`-O2` 是唯一杠杆。

## 4. 编译期踩到的坑（已修）

`-march=armv7-a` 首次链接失败：

```
relocation R_ARM_MOVW_ABS_NC against a local symbol can not be used
when making a shared object; recompile with -fPIC
```

根因：configure 探测到宿主支持 PIE，往 `LDFLAGS` 塞了 `-Wl,-pie`；而 `-march=armv7-a` 会用 `movw/movt` 加载地址常量，产生这种重定位，在 PIE 下非法。相机的 glibc 2.13 `crt1.o` 本来就是 non-PIE 的，所以正确做法是**去掉 `-Wl,-pie`**（`build_dropbear.sh` 已加 sed，在 configure 之后）。

> 注：这条修复只对 `-march=armv7-a` 是必需的；纯 `-O2` 在 `-Wl,-pie` 下也能过（ARMv5 用字面量池，重定位是 `R_ARM_ABS32`）。

## 5. 真正让传输慢的：单核已饱和

| 指标 | 数值 | 含义 |
|---|---|---|
| CPU 核数 | **1** | Cortex-A9 单核 |
| load average | **2.57 / 2.64 / 2.27** | 单核上严重过载 |
| CPU idle | **1.2%** | 基本没有空闲 |
| nice 占用 | **51.5%** | 大量低优先级任务 |
| 内存 | 511MB 总 / **15.9MB 空闲** | 也很紧 |
| WiFi 协商速率 | **150 Mb/s**，信号 −53 dBm | 链路很好 |
| 实测吞吐 | 560–660 KB/s ≈ **4.5 Mb/s** | 只用了 WiFi 的 **3%** |

⇒ 瓶颈 **100% 在 CPU 侧**，不是网络、不是 SD 卡。20 倍网络余量摆在那里。

**推论**：`-O2` 让加密指令减半，理论吞吐接近翻倍；但因为整机已经满负荷，实际提升会被抢占打折。**省下来的 CPU 同时也是对相机主业务（`di-camera-app` 已占 32%）的减负**，这一点比单纯提速更有价值。

## 6. 分级方案

| 级别 | 选项 | 静态收益 | 静态风险 | 评价 |
|---|---|---|---|---|
| A | `-O1` | ~−35% | 最低（不开 strict-aliasing） | 保守，收益已接近 -O2 |
| **B（推荐）** | **`-O2`** | **−40%** | **低**（0 VFP / 0 ldrd） | 干净，与现役 ABI 完全一致 |
| C | `-O2 -march=armv7-a -mtune=cortex-a9` | −41% | 中（125 条 ldrd/strd + 需去 PIE） | 性价比低 |
| D | `-O3` 或 `-flto` | 再 −2~5% | 中高（问题难定位） | 不划算 |
| E | 加 `-fno-strict-aliasing` | 0 | 消除唯一的语义风险 | 可与 B 叠加 |

**推荐 B + E**：`-O2 -fno-strict-aliasing`。

## 7. 静态分析**无法**证明的部分

- 长时间运行（数小时传输、反复连接）的稳定性 —— 只能在机身上跑。
- `-O2` 下 strict-aliasing 是否踩到 dropbear 某处类型双关 —— 静态规则无法穷举，加 `-fno-strict-aliasing` 可规避。
- 与相机休眠/唤醒、SD 卡抖动等真实环境交互 —— 上机才能看。

## 8. 落地与回滚（未执行，等确认）

```bash
# 现役 -O0 产物保持不动，作为回滚备份
cp test_server/dropbear/out/dropbear.arm{,.O0.bak}

# 编 -O2
wsl -d NXKS2 bash test_server/dropbear/build_dropbear.sh -O2
cp test_server/dropbear/out-O2/dropbear.arm scripts/dropbear/dropbear

# 切过去（不刷机、不重启相机）
bash tools/nx-ssh.sh cmd 'sh /opt/usr/nx-ks/dropbear/restart.sh'

# 测速
time bash tools/nx-photos.sh get SAM_0001.JPG /tmp

# 回滚：把 .O0.bak 拷回 scripts/dropbear/dropbear 再 restart
```

> 三个产物目录：`out/`（-O0）、`out-O2/`（-O2）、`out-test/`（armv7a）。都列出 `GLIBC_2.4`、NEEDED 一致，可随时互换。

---

## 9. 实测（已实施，2026-10-23 凌晨）

### 9.1 意外发现：dropbear 出生就带着 nice=19

传输时 `top` 采样：

```
Cpu(s): 16.4%us, 27.4%sy, 52.7%ni, 3.2%id
 247 root  10 -10  ...  44.3%  di-camera-app      ← 高优先级
1479 root  39  19  ...  12.9%  dropbear           ← 最低优先级！
 322 root  -2   0  ...   7.4%  ksdioirqd/mmc1     ← SD 卡中断也在抢
1480 root  39  19  ...   5.5%  sftp-server
```

排查：

```sh
$ busybox nice          # 不带参数，打印当前 shell 的 nice
19
$ awk '{print $19}' /proc/$$/stat
19                      # telnet shell = 19
```

**根因**：Tizen 把 `telnetd` 及其 shell 都设成 `nice=19`（给相机主业务让路），dropbear 从 telnet shell 启动就继承了它。而 `di-camera-app` 是 `nice=-10` —— 优先级差 29 级，单核饱和时 dropbear 根本抢不到时间片。

### 9.2 修法：用 renice 设绝对值，不用 `nice -n`

`scripts/dropbear/run.sh`：

```sh
$BB renice 0 -p $$
exec "$D/dropbear" "$@"
```

**为什么不能用 `nice -n -19`**：`nice -n` 是**相对**调整量。
- 从 telnet shell（19）启动时，`19 + (-19) = 0` ✓ 恰好对
- 但从 `init.sh`（nice 0）启动时会变成 **-19**（最高优先级）✗ 会抢爆相机主业务

`renice 0` 无论继承什么都是 0，安全。

### 9.3 实测数据（同一张 10.8MB JPG，各 5 次）

| 配置 | 各次 KB/s | 中位 | 最优 |
|---|---|---|---|
| `-O0` + nice 19（原始） | 793 / 777 / 1027 / 838 / 1007 | 838 | 1027 |
| `-O2` + nice 19 | 1301 / 909 / 344 / 472 / 1056 | 909 | 1301 |
| **`-O2` + nice 0** | **1645 / 1793 / 1041 / 1340 / 1708** | **1645** | **1793** |

- **中位 838 → 1645，+96%**
- 5 次总耗时：68 秒 → **44 秒**
- 单张最优：17.1 秒（最早的 -O0 测量）→ **6.4 秒**
- **批量 16 张 / 155MB：4 分 43 秒 → 1 分 55 秒（2.46×，≈1.35 MB/s）**
- 完整性：抽样 5 张 md5 与机端逐一比对，全一致

**归因**：`-O2` 单独只带来 +8%（中位），`nice 19→0` 带来 +81%。两者叠加 +96%。

这也解释了为什么静态的 −40% 指令数没有兑现成 −40% 时间 ——**CPU 抢不到，指令再少也没用**。

### 9.4 还能更快吗

| 手段 | 预期 | 代价 |
|---|---|---|
| dropbear nice 设 -5 | 再快一些 | 传输时相机可能卡顿（与 di-camera-app 的 -10 只差 5 级） |
| 只传缩略图 | 数据量降一个数量级 | 需要相机侧生成缩略图（当前没做） |
| 换成 `aes128-ctr` | 未见得比 chacha20 快，A9 无 AES 硬件 | 需实测 |

**不建议**继续压榨：`nice 0` 已经在"快"和"不干扰相机"之间取得平衡，再往上调会开始影响拍照/录像。
