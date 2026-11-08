# LUT 秒切：取消半按快门（2026-11-08 实机定案）

> **一句话**：`lut.sh apply` / `off` 现在自己完成 Load —— 面板上点一张，取景器立刻变，不用再半按快门。
> 旧结论「不能从 ARM 侧强制 reload，只能半按」**只对"裸写 `+0x00c` + 脉冲"成立**，因为我们当年漏了两个必要条件。

## 0. 结论

| # | 命题 | 证据 | 强度 |
|---|---|---|---|
| 1 | ARM 侧可以让 ISP 立刻重读 LUT 槽 | `nx_lutload.arm once` 后画面立即换表（黑白↔彩色反复验证） | ★★★ 目视 |
| 2 | 单写 `+0x008` bit8 脉冲**不够** | 槽已换成黑白表、只脉冲 bit8，画面不动 | ★★★ |
| 3 | 完整 7 步写序**够**，但 `+0x008` 的 **bit0 必须复位** | 留着 bit0=1 画面停在异常；清掉立刻恢复 | ★★★ |
| 4 | 用 EP 中断 `ACC_3DLUT_RD_FINISH` 等 DMA，可连续切换且无撕裂 | 5 次连续切换全部 `rc=0`，`elapsed_ms` 0.0–0.4 | ★★★ |
| 5 | 面板/命令行/混合/强度全部自动获得秒切 | 都走同一个 `commit_table` | ★★★ 代码路径唯一 |

## 1. 为什么以前花屏

`3DLUT_API_GUIDE` §5 记的「裸写 `+0x00c` + 脉冲会花屏」是实测现象，但归因错了层次 —— 不是"ARM 侧不能写"，而是**写的东西不完整**。

p7 自己的 Load 入口是 `FUN_004a5c44` → `FUN_004a5e30`，QEMU 逐条实测的写序（`3DLUT_APPLY_PATHS_2026-10-08` §4.1）：

```
+0x000 <- OnOff = 1
+0x008 <- 0            bit0 先清
+0x008 <- 1            bit0 置（Acc）
+0x00c <- table        Load 目标地址
+0x004 <- SelCbCr/SelLUT/ch 使能
+0x008 <- 0x101        bit8 置 → DMA 启动
+0x008 <- 0x001        bit8 清 → 脉冲结束
```

早期的 `lutload.arm` 只做了中间两行（写地址 + 翻 bit8），漏掉 `OnOff`、`Acc` 和 `Cfg` 的通道位 —— 硬件拿不到完整的 Load 条件，于是画面崩。

**2026-11-08 新发现的一条**：QEMU 记录里最后一写是 `0x001`，但真实硬件上 **bit0 必须回到 0**。留 bit0=1 时画面会停在异常（彩色错乱/花屏），清掉立刻恢复正常。固件里另有代码在别处清它（息屏前后读到的 `Pulse` 都是 `0x00000000`），所以 QEMU 那段记录只是序列片段，不是终态。

> 方法论：QEMU 能给"写了哪些寄存器"，给不了"硬件最终要停在什么状态"。**终态必须上机取**。

## 2. 现成工具就是引擎

不需要新写工具 —— `test_server/lutpipe/nx_lutload.c` 里已经有完整正确的写序，而且比手工 `devmem` 强在两点：

| 能力 | 手工 devmem | nx_lutload.arm |
|---|---|---|
| 7 次写的时间窗 | 每次 open/close `/dev/mem`，几十毫秒 = 闪好几帧 | 单次 mmap 连续写，微秒级 |
| 是否等 DMA | 不等，写回就读 | `ioctl(EP_IOCTL_ACC_INTR_WAIT)` 等 `ACC_3DLUT_RD_FINISH` |
| 收尾复位 bit0 | 容易忘 → 画面停在异常 | `out:` 分支无条件 `r[2]&=~1` |
| 型号护栏 | 无 | `/etc/version.info` 必须是 NX500 1.12 |
| 并发 | 无 | `flock /tmp/nxwa_lutload.lock` |

它原本只服务录像 watcher（开录后补载首帧），顺带就是秒切引擎。

**本次唯一的代码改动**：地址白名单从 3 槽（A17/A18/A19）扩到 6 槽（A12/A13/A14/A17/A18/A19），让 `off` 也能 kick p7 刚选中的原厂槽。

## 3. 落点

### 3.1 `scripts/lut.sh`

| 位置 | 改动 |
|---|---|
| 工具查找 | 新增 `KICK=$(pick_tool nx_lutload.arm)` |
| 新增 `kick_slot <addr>` | 3 次重试（每次间隔 0.3 s），成功打印 `OK instant switch (no half-press)`；失败打印最后 3 行日志 + `WARN instant switch failed; half-press once`，**不阻断** |
| 新增 `kick_current` | 读 `0x2082b00c` 按硬件当前登记的地址 kick（`off` 用） |
| `commit_table` | 写完 `lutptr` 之后、起 watcher 之前 `kick_slot "$SLOT"`；删掉 `NEXT half-press once` |
| `off` | `oled_restore` 之后 `kick_current`；删掉"半按一次即可" |
| `status` | 只在 `LUT_NOKICK=1` 时提示半按 |

顺序讲究：kick 必须**在 `lut_video.sh on` 之前**，否则 watcher 的录像补载会抢同一把 `nx_lutload` 锁。

### 3.2 后备开关

```sh
LUT_NOKICK=1 sh /opt/usr/nx-ks/lut.sh apply <name>    # 退回"改登记表 + 提示半按"
```

留它是为了排障：如果哪天固件行为变了导致 kick 失败，一条环境变量就能退回旧路径，不用改代码。

## 4. 实机验收（NX500 1.12，192.168.0.106）

### 4.1 判别实验（手工 devmem，逐步排除）

| 步 | 动作 | 画面 |
|---|---|---|
| 1 | 槽写黑白表 + 只脉冲 bit8（`0x100`→`0x000`） | **不变**（彩色）⇒ 单脉冲无效 |
| 2 | 完整 7 步 + 末尾留 `0x001`（bit0=1） | 闪一下 → **停在异常** |
| 3 | 清 `+0x008 <- 0` | **立刻恢复**彩色 ⇒ bit0 是元凶 |
| 4 | 槽写黑白 + 完整 7 步 + 末尾 `0x000` | **变黑白** ⇒ 写序正确且 3DLUT 在工作（不是被旁路） |

> 中间被息屏打断过一次：息屏唤醒本身会触发 p7 的 View::_load（`Pulse` 被清回 0、画面按 `A18` 当前内容重画），所以判据必须在**亮屏且用户注视**的窗口里取。这是本次踩到的唯一操作坑。

### 4.2 工具验收

```
BEFORE on=00000001 cfg=00000100 access=00000000 lut0=81119f00 lut1=00000000
WAIT rc=500 errno=0 elapsed_ms=0.400 jpeg_err=0 irq=7 trigger=1
PROCESS on=00000001 cfg=00000100 access=00000000 lut0=81119f00 lut1=00000000
OK DMA_RD_FINISH and processing mode verified
```

连续切换 5 次（黑白→彩色各两轮 + 末态黑白），全部 `rc=0`。

### 4.3 端到端

```
$ sh /opt/usr/nx-ks/lut.sh apply mono_trix400
OK instant switch (no half-press)
OK applied mono_trix400

$ sh /opt/usr/nx-ks/lut.sh off
OK video LUT off
OK screen-color restored to 0
OK instant switch (no half-press)
OK restored (view=4 factory, still=BV12+Still6 factory, A18=original)
```

用户目视：apply 后**未半按**，画面自动变黑白；off 后自动回原厂。面板走同一条 `lut.sh apply`，因此同样生效。

## 5. 边界

| # | 边界 | 说明 |
|---|---|---|
| 1 | 切换瞬间有约 1 帧的过渡 | DMA 要把 19,712 B 从 DRAM 搬进硬件 SRAM，物理上无法为零。等中断让窗口从"好几帧"降到"几乎不可见"；连续快速切换时仍能看到花屏彩条 |
| 2 | `off` 的 kick 目标是 `0x2082b00c` 的**当前值** | 若 `oled_restore` 已让 p7 切到 A13/A17，就 kick 那一档；若还没切，kick A18（内容已是原厂备份）。两条都能回到原厂观感 |
| 3 | Cfg 必须是 `0x100` 或 `0` | `nx_lutload` 的护栏。AdobeRGB 等其它分支若 Cfg 不同会被拒 → 退回半按，不会写坏 |
| 4 | 照片链路不受影响 | Still 走 `Still6`/`BV12`，拍照时 p7 本来就自己 Load，秒切只是让取景器提前一致 |
| 5 | 全部仍是 RAM-only | 断电回镜像原厂表 |
| 6 | **息屏 / `di-camera-app` 不在时不会生效** | DMA 完成中断只有 ISP 在取景时才产生。`wait-test` 在息屏下一次也拿不到中断（`errno=110`）。因此 `lut.sh` 会在 kick 前用 `ps` 判一次 App 是否在跑，不在就直接提示而不是白等 |
| 7 | **不能靠 `OnOff=0` 遮盖过渡** | 实测（2026-11-08）：把 `+0x000` 清零后调用 `once`，工具报 `OK`、寄存器校验全过，但画面完全没变、必须半按 —— 模块被关掉时根本不执行 DMA。所以"先旁路再加载"这条路是死路，`nx_lutload.c` 里留了注释防回退 |

### 5.1 过渡期花屏为什么消不掉

取景器在 3DLUT 之后合成，DMA 期间 ISP 读到半写好的表，输出就是彩条/撕裂。p7 自己
`View::_load`（半按、切档）走的是同一段硬件，同样会花 —— 只是因为半按伴随对焦动作、
画面本来就在变，所以平时注意不到。

`+0x008` 只有 `bit8 = Load 启动`、`bit4 = Save 启动` 两个脉冲，EP 也没有 VSYNC 中断，
所以 ARM 侧无法把加载对齐到消隐期。**1 帧过渡是这个方案的物理下限**。

要彻底消除只有两条路，都不在这次范围内：

1. 让 p7 自己走 `View::_load`——需要找到非半按的触发事件（10-19 试过 OLED 设置事件，不能让 ISP 重读槽内容）
2. 在 ISP 侧做双缓冲——需要改 p7 代码

### 5.2 面板侧的缓解：LUT 模式去抖 450 ms

LUT 的一次 apply 要写 19,712 B 槽再触发一次 DMA，逐格落地在快速滑动时就是
「一帧花屏 × 格数」。所以把去抖做成队列属性而不是全局常量：

| 模式 | 去抖 | 理由 |
|---|---:|---|
| FILMLAB | 150 ms | PW 七维只是标量直推，不写槽、不 Load，越快越跟手 |
| **LUT** | **450 ms** | 每次落地要写槽 + DMA，等用户停手再落一次 |

`nx_queue.debounce_ms` 默认 `NXUI_DEBOUNCE_MS`，LUT 模式在 `nx_queue_init` 之后
改成 `NXUI_LUT_DEBOUNCE_MS`。另外两条路径不再依赖常量：

- `nx_queue_select_now()`：OK / 保存并关闭是明确确认，直接 `due = now` 跳过去抖。
  原先写的是 `now_ms() - NXUI_DEBOUNCE_MS`，常量一改就会失准。
- **关闭面板时 `due = 0`**：用户已经用关闭动作确认了这一张，不必再空等 450 ms。

实机：快速连滑 3–5 格只切一次（用户验收「只切一次，可接受」），单点一格
慢半拍但不难受。

## 6. 三处安装点（改动后必核）


| 路径 | 说明 |
|---|---|
| `/opt/usr/nx-ks/lut.sh` | 机身主副本 |
| `/mnt/mmc/lut/lut.sh` | SD 卡（`pick_tool` 的第二候选） |
| `/mnt/mmc/scripts/lut.sh` | SD 母本（`install.sh` 的来源，漏了会把机身打回旧版） |
| 同上三处的 `lut/nx_lutload.arm` | 工具本体 |

本次部署 md5：

```
cd722928b0c9bb23f96eb31875ff6cb3  lut.sh
ec8d58e1da930f70b39bc871d7b0a802  nx_lutload.arm
53cea9925529b08a391c25d75c92f6b5  nxui/nxui.arm   (LUT 去抖 450 ms)
```

回滚：`/mnt/mmc/lut/_bak_20261108/` 里有 `lut.sh.prev`、`lut.sh.sdcard_prev`、`nx_lutload.arm.prev`。

## 7. 测试

`test_server/lutpipe/test_lut_lib.sh` 新增 16 项，总 57 PASS / 0 FAIL：

- apply 调用一次 `nx_lutload`，动词 `once`，目标是 `0x81119F00`
- 输出必须含 `OK instant switch`
- `LUT_NOKICK=1` 时**不得**调用工具，且要提示半按
- kick 失败时 apply 仍成功、给出 `WARN instant switch failed`、且**不谎报**秒切

`test_lut_backend_shell.py` 21 项不变，全 PASS。

> 顺带发现 `test_lut_sh_rotation.py` 第 80 行语法错（`@unittest.skipUnless` 装饰器与 `LEGACY = ...` 赋值顺序颠倒），该文件已是历史归档、不参与现行判定，本次未动。
