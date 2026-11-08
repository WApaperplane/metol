# NX-WA 2.88.0-nxwa.15 — LUT 秒切（取消半按快门）

发布日期：2026-11-08
性质：体验版本。**换 LUT 不用再半按快门** —— 面板上点一张，取景器立刻变。

## 一句话

`lut.sh apply` / `off` 现在自己完成 Load，等你看到的就是新表；
以前那套「点完还要半按一次快门才生效」的流程到此结束。

## 一、以前为什么要半按

p7 侧的 `CBackend_3dlut_View::_load` 只在它自己的事件里跑（半按、切档、模式切换、
息屏唤醒）。`lut.sh` 只改登记表 + 写槽，不动硬件，所以必须靠用户半按去"踢"它一脚。

历史文档把这写成铁律：「不能从 ARM 侧强制 reload，裸写 `+0x00c` + 脉冲会花屏」。
**这条归因错了层次**：花屏不是因为"ARM 不能写"，而是因为当年写的**写序不完整**。

## 二、正确的写序

p7 自己的 Load 入口是 `FUN_004a5c44` → `FUN_004a5e30`，QEMU 逐条实测：

```text
+0x000 <- OnOff = 1
+0x008 <- 0              清 bit0
+0x008 <- 1              置 bit0（Acc）
+0x00c <- table          Load 目标地址
+0x004 <- SelCbCr/SelLUT/ch 使能
+0x008 <- 0x101          bit8 置 → DMA 启动
+0x008 <- 0x001          bit8 清 → 脉冲结束
+0x008 <- 0x000          ★ bit0 复位（本次新增，QEMU 记录里没有）
```

漏掉前两行与 `Cfg` 的通道位 → 硬件拿不到完整 Load 条件 → 花屏。
**最后那一步 `bit0 复位` 是上机才发现的新事实**：留着 bit0=1，画面会停在异常；
清掉立刻恢复。QEMU 能给"写了哪些寄存器"，给不了"硬件最终要停在什么状态"。

## 三、实现

不用新工具 —— `nx_lutload.arm` 里已经是这套写序（它原本服务录像首帧补载），
而且比手工 `devmem` 强在两点：单次 mmap 连续写（微秒级，不是几十毫秒），
以及 `ioctl(EP_IOCTL_ACC_INTR_WAIT)` **等 `ACC_3DLUT_RD_FINISH` 中断**才返回。

`scripts/lut.sh` 的改动：

| 位置 | 改动 |
|---|---|
| 新增 `kick_slot` | 先判 `di-camera-app` 在跑（息屏/退出时中断必不来）；再 3 次重试；成功 `OK instant switch (no half-press)`；失败只 WARN，**不阻断** apply |
| 新增 `kick_current` | 读 `0x2082b00c` 按硬件当前登记的槽 kick（`off` 用） |
| `commit_table` | 写完登记表 + `lutptr` 后 kick，且在起录像 watcher **之前**（避免抢锁） |
| `off` | `oled_restore` 之后 kick 当前槽 |
| `status` | 只在 `LUT_NOKICK=1` 时提示半按 |

`nx_lutload.arm` 唯一改动：地址白名单 3 槽 → 6 槽（A12/A13/A14/A17/A18/A19），
让 `off` 能 kick p7 刚选中的原厂槽。仍是硬编码白名单，不接受任意地址。

## 四、后备开关

```sh
LUT_NOKICK=1 sh /opt/usr/nx-ks/lut.sh apply <name>
```

退回旧路径（改登记表 + 提示半按），不改代码。留它是排障用：
万一哪天固件行为变了、kick 被拒，一条环境变量就能绕过。

## 五、实机验收（NX500 1.12）

```text
$ sh /opt/usr/nx-ks/lut.sh apply mono_trix400
OK instant switch (no half-press)
OK applied mono_trix400
```

未半按快门，取景器直接变黑白（用户目视确认）。`off` 同样自动回原厂。

工具层：

```text
BEFORE on=00000001 cfg=00000100 access=00000000 lut0=81119f00 lut1=00000000
WAIT rc=500 errno=0 elapsed_ms=0.400 jpeg_err=0 irq=7 trigger=1
PROCESS on=00000001 cfg=00000100 access=00000000 lut0=81119f00 lut1=00000000
OK DMA_RD_FINISH and processing mode verified
```

连续切换 5 次（黑白↔彩色）全部 `rc=0`。

## 六、边界

- **切换瞬间有约 1 帧花屏**：19,712 B 要从 DRAM 搬进硬件 SRAM，DMA 期间 ISP 读到半写好的表。这是硬件固有行为 —— p7 自己 `View::_load`（半按、切档）走同一段硬件，同样会花，只是半按伴随对焦、平时注意不到。`+0x008` 只有 Load/Save 两个脉冲位，EP 没有 VSYNC 中断，ARM 侧无法把加载对齐到消隐期。**1 帧是这个方案的物理下限。**
- **息屏时不生效**：DMA 完成中断只有 ISP 在取景时才产生。`lut.sh` 会先判 `di-camera-app` 是否在跑，不在就提示而不是白等；屏幕亮着时正常。
- **`OnOff=0` 遮盖过渡是死路**：实测清零后调用，工具报 OK、寄存器全对，但画面完全没变、必须半按 —— 模块关闭时根本不执行 DMA。`nx_lutload.c` 里留了注释防回退。
- `off` 的 kick 目标是硬件当前登记的槽，所以 `oled_restore` 若已让 p7 切到 A13/A17，就 kick 那一档，观感仍是原厂。
- Cfg 必须是 `0x100` 或 `0`（`nx_lutload` 的护栏）。其它分支会被拒 → 退回半按，不会写坏。
- 照片链路不受影响：Still 走 `Still6`/`BV12`，拍照时 p7 本来就自己 Load。
- 全部仍是 RAM-only，断电回镜像原厂表。

## 七、文件

| 文件 | md5 |
|---|---|
| `scripts/lut.sh` | `cd722928b0c9bb23f96eb31875ff6cb3` |
| `scripts/lut/nx_lutload.arm` | `ec8d58e1da930f70b39bc871d7b0a802` |

三处安装点必须同步（漏 SD 母本会被 `install.sh` 打回旧版）：

```text
/opt/usr/nx-ks/lut.sh
/mnt/mmc/lut/lut.sh
/mnt/mmc/scripts/lut.sh
以及三处的 lut/nx_lutload.arm
```

## 八、测试

`test_server/lutpipe/test_lut_lib.sh` 新增 16 项秒切断言，总 **57 PASS / 0 FAIL**：

- apply 调用一次 `nx_lutload once 0x81119F00`
- 输出必须含 `OK instant switch`
- `LUT_NOKICK=1` 时不调用工具且提示半按
- kick 失败时 apply 仍成功、给 `WARN instant switch failed`、不谎报秒切

`test_lut_backend_shell.py` 21 项全 PASS（未受影响）。

完整技术记录：`docs/current/LUT_INSTANT_SWITCH_2026-11-08.md`
