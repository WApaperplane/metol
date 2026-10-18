# NX-WA 2.88.0-nxwa.6

发布日期：2026-10-18
上一版：2.88.0-nxwa.5

## 一句话

不刷固件、不改 p7 代码：**改 1 个 4 字节的登记表项 + 写 19,712 字节进空闲槽 + 半按一次快门**，取景器就换成任意 3D LUT。而且取景和成片是两条**独立**可重定向的链路。

## 1. 运行态换表闭环（本版主线）

最小闭环 = 写表进槽 + 改登记表 + 一次重载。不刷机、不改 p7、不用 CMA、不抢时序。

| # | 命题 | 机器判据 |
|---|---|---|
| 1 | 登记表所在页**可写** | `/dev/mem` `O_RDWR` + `PROT_WRITE`，16 KB 窗口内 stray = 0 |
| 2 | p7 **每次 Load 都重读**登记表项 | `cfg`/`sel` 全程不变（`0x100`，SelLUT=0），只有 `load_addr` 变 |
| 3 | 改 `View4[3]` 一个 word ⇒ Load 源真的换 | `0x81115200 → 0x81119F00 → 0x810FD100` |
| 4 | 槽内容被**实际渲染** | 4,913 项全部反相 ⇒ 取景器明显负片（目视确认） |
| 5 | **Still（成片）消费同一套表** | `Still6` 六项全指负片槽 ⇒ `SAM_0044.JPG` 为负片 |

★ 第 5 条是最有价值的负对照：拍照时 `View4[3]` 仍指原厂 A17，**取景器正常、成片负片** ⇒ View / Still 两条链路可分别重定向。

## 2. 判据纪律（这一条比结论重要）

各槽与实机装载源 A17 的差异：

| 槽 | 差异字节 | 占比 | 最大偏差 |
|---|---:|---:|---:|
| A12 标准 | 13,801 | 70.0 % | 97 |
| A14 电影 | 13,810 | 70.1 % | 97 |
| A13 黑白 | 7,792 | 39.5 % | 29 |
| **A18** | **806** | **4.1 %** | **8** |

A18 与 A17 几乎同表 ⇒ 换过去视觉不可辨。**"看不出变化"不是硬件没消费，是判据选错了表。**
所以最终判据换成无歧义的负片表（`255 − R/G/B`）。

同时纠正一条旧结论：实机 Load 源是 `0x81115200`（A17 肤色表），**不是 A12 标准槽**。10-16 把负片写进 A12「画面无变化」是打错靶，不能当作 C1 失败。

## 3. 配置位（曾导致反向结论）

`bits[1:0]` = SelCbCr｜**`bits[5:4]` = SelLUT**｜`bit8` = LUT0 格式位｜`bit12` = LUT1 格式位。

`0x100` 与 `0x1100` **都是** SelLUT=0，只有 `0x1110` 才是 1。把 bit12 当选择位会得出「Still 用 LUT1」——非常有信心，而且完全错。

顺带重解释 E4：E4 把表放进 **LUT1**，而 Still 的 `_load` 用 `sel=0`（LUT0），bank 不匹配 ⇒ 应表述为「**LUT1 直灌对成片无效**」，而不是「成片无法换表」。

## 4. 机身 `.cube` 转换器 cube2lut

相机 rootfs 没有 Python，所以是独立 ARM 二进制（不依赖 libc / libm / libgcc）。

```sh
/opt/usr/nx-ks/lut/cube2lut.arm /mnt/mmc/looks/portra400.cube /mnt/mmc/looks/portra400.bin
```

输出 4,913 × 4 B + 60 B 填充 = **19,712 B**。格式契约：R 变化最快、`DOMAIN` 必须 0..1、拒绝 1D cube 与非 `N³` 节点数。

**一个差点混过去的 bug**：G'MIC 把近黑值写成 `2.2439395252149552e-05`，第一版解析器读到 `e` 返回 0 且**不推进指针** ⇒ 后续值全读 0，而节点计数照旧到 `N³` ⇒ 检查**假通过**，产出 93 % 为零的表仍报成功。18 张真实 film cube 中 12 张中招；三张测试表恰好不含 `e` 记法，所以测试全绿。已修：支持 `e±NN`、解析失败报 `bad number at value index…`、全零表直接拒绝。

> 17³ 测试 cube 与 PC 浮点参考**逐字节相同**；真实 13³/33³ 重采样后 maxdelta = 1（网格插值残差）。

## 5. NXUI：LUT 面板 + 焦点修复

**LUT 模式**（第三个 UI 模式）：入口 = `EV+WiFi` / 主菜单「LUT 滤镜」/ `nxui.sh lut`。与 filmlab 数据通路完全独立、可叠加。

三个安全设计：半按只隐藏不还原（否则照片丢掉 LUT）｜退出必 `lut.sh off`｜dry-run 只读。

实测修复两个 bug：`apply` 不触发重载（点按后画面不变）｜半按 = 关闭并走 `off`（"点几下再半按"时最后一次写入被还原）。

**焦点修复**：相机无窗口管理器，X11 `KeyPress` 只投给持有输入焦点的窗口。面板抢焦点后退出只 `XDestroyWindow`、从不归还 ⇒ 原生菜单方向键 "有时候" 失灵。修法 = 保存/精确归还焦点 + 关闭即 `XUnmapWindow`，回归判据 = 焦点停在 `0x1`（PointerRoot）即失败。

## 6. 安装

1. 把 `NX-WA-2.88.0-nxwa.6.zip` 解压到 **SD 卡根目录**
2. 插卡开机，`install.sh` 自动增量同步 `scripts/` → `/opt/usr/nx-ks/`

部署后布局：

```
/opt/usr/nx-ks/lut/*.arm        工具（随包，install.sh 补可执行位）
/mnt/mmc/looks/*.cube|*.bin     滤镜库（自己放）
/mnt/mmc/lut/state/             备份与状态（自动创建）
```

用法：

```sh
/opt/usr/nx-ks/lut.sh list
/opt/usr/nx-ks/lut.sh apply portra400
# 半按一次快门 → 生效
/opt/usr/nx-ks/lut.sh off
```

## 7. 回滚

```sh
/opt/usr/nx-ks/lut.sh off            # 登记表回原厂 + A18 回备份 + 半按一次
# 或整包回退
cp /opt/usr/nx-ks/nxui/backup-lut-20261018/* /opt/usr/nx-ks/
```

所有写入都是**内存操作**，断电即回原状；不写分区、不刷固件。A18 写入前的备份与固件镜像切片逐字节相同（`md5 4c0cc78c…`），双向还原已验证。

## 8. 明确没验的部分

- **持久性**：断电回原状。「开机即生效」仍需改固件镜像（C1）。
- **重载触发**：半按一定触发；切档 / 切模式 / 休眠唤醒是否触发**未测**。
- **多槽并发**：`View4` 4 项 / `Still6` 6 项能否同时指向不同自定义表（= 多档滤镜）**未测**。
- **其它固件**：全部在 1.12 + 特定 p7 版本验证。NX1 同代 DRIMe5 但**未验**；NX300 是 DRIMe4，不要假设。
- **异格式表**：只验 4913×4B；16 bit / 4:2:2 未测。

## 9. ⚠ 禁区

不要自己写 `+0x00C` 再脉冲配置寄存器来强制重载。那样 ISP 会读到原厂时序里从未出现过的地址组合 ⇒ **严重偏色花屏**，只能靠半按让 p7 自己走完选表复位。

`lut.sh apply/off` 刻意**不**自动 reload。唯一生效方式 = **半按快门**。

## 10. 包内容与本版 md5

| 项 | 值 |
|---|---|
| 文件数 | 274 + manifest |
| 新增 | `scripts/lut/{cube2lut,nx_slotwrite,nx_regtabwrite,nx_regtabdump}.arm` |
| `cube2lut.arm` | `582b12f0cc9f04ca765a8989d664b580` |
| `nx_slotwrite.arm` | `ed1708306d8110ef1950bef2843e4747` |
| `nx_regtabwrite.arm` | `6d82f43ca616d5a5a4cdc655f8edba7c` |
| `nx_regtabdump.arm` | `253656833f6555deaf58c5a088f18e8b` |
| `nxui.arm` | `2e94efaea6cebe844b28e95b2b4277f3` |

## 文档

- `docs/current/LUT_RETARGET_LIVE_2026-10-18.md` — 完整实验链与数据
- `docs/current/LUT_REGTAB_READ_2026-10-18.md` — 配置位与登记表回读（22/22）
- `docs/current/CUBE2LUT_2026-10-18.md` — 转换器与格式契约
- `docs/current/LUT_UI_2026-10-18.md` — 机上 UI 模式
- `docs/current/NXUI_FOCUS_HANDOFF_2026-10-18.md` — 焦点缺陷与回归
- `docs/community/` — 对外发布稿（Reddit / 中文长文 / 短视频脚本）
