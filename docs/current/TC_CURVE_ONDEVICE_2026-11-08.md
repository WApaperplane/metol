# TC 曲线：p7 内部 19 节点表可写、可恢复、进入 HEVC

日期：2026-11-08
> 后续本地工具修复与技术还原候选见 [TC 还原工作流](TC_RESTORATION_WORKFLOW_2026-11-08.md)。新实现尚未部署；下文部署哈希和耗时记录对应此前机端版本。
相机：NX500 1.12（本轮 IP `.106`，DHCP 已从 `.103` 漂移）
证据根：`E:/NXWA/rea-evidence/20261108-tc/`
前序：`rea-evidence/20261107-gamma/TC_ENCODED_ABA_2026-11-08.md`（Codex 的 A/B/A 首证）

## 结论

1. **录像链路里的 tone 曲线（TC）在运行态可改写，且改动进入最终 HEVC 码流。**
2. **`MOVIE_GAMMA_CONTROL` / `IQ[180]` 那条对外接口仍然没有消费者**，这两件事不矛盾：前者是参数入口，这是 p7 内部数据表。
3. **8bit 4:2:0 容器不变。** 「曲线可编程」已证；「整体动态范围净增益」未证。

本文件不再重复「Log 数据基础不存在」这类推论。8bit 限制的是量化精度，不排除 Log 形式；Codex 第五轮的实测结论是「整体 DR 增益未确认」，不是「Log 不成立」。

## 地址链（当前固件已验证）

```
Param0 = read32(0x817dccbc)
Gamma  = read32(Param0 + 0x170)
dirty  = Gamma + 4
Y[i]   = Gamma + 0xe8c + 4i      i = 0..18
源表    = 0x8062f71c + 4i         i = 0..18（p7 运行态，重启即回原厂）
```

签名校验：

```
read32(Param + 0x00) == 0x8062f5f8
read32(Gamma + 0x00) == 0x8062f6b0
```

本次 boot 实例：`Param0=0x8215c000 → Gamma=0x8215c800`，`Param1=0x82170800 → Gamma=0x82171000`。
堆地址可能随 boot 变化，**必须从 `0x817dccbc` 链式解析并校验，不能硬编码**；跨重启复用尚未实测。

两个易错点：

- `0x8215c800` 是 Gamma 对象，不是参数对象；参数对象是 `0x8215c000`
- `0x8215d6b0` 是 Y[9]，Y[0] 在 `0x8215d68c`

## 表和写入协议

| 项 | 值 |
|---|---|
| 节点数 | 19 |
| X 定义域 | 0–16383（固件固定，不改） |
| Y 值域 | 0–1023 |
| 原厂 Y | `0,16,36,64,105,156,223,305,397,500,606,704,786,860,918,960,991,1019,1023` |

写入六步：

1. 读 19 个源节点，确认等于原厂（入场检查；恢复操作可跳过）
2. 写 19 个 Y 到 `0x8062f71c + 4i`
3. 写 `0xffffffff` 到 `Gamma + 4`
4. 等 ISP 消费 dirty（**实测 <50ms，不需要按键**；轮询 Y[9] 变化即可）
5. 回读 19 个缓存节点 `Gamma + 0xe8c + 4i`
6. 逐项等于目标才算成功；不等则再等一轮，仍不等按失败处理并恢复

### s1 不是必需的（2026-11-08 补充实测）

Codex 的实验脚本用 `st key push s1` 触发刷新。本轮空闲态实测：

```
写表 + dirty 0xffffffff
T0    cache Y9 = 0x25F（旧值，未刷新）
T50ms cache Y9 = 0x1F4（新值），dirty 回到 0x0A00807F
```

ISP 在下一帧就消费了 dirty。<50ms 自动完成，无需按键。`tc.sh` 已改为轮询 Y[9]（每 50ms 一次，最多 20 次），只在超时才调一次 `s1` 兜底。

**未测**：录像中是否同样自动消费。Codex 的 A/B/A 是在录制中切曲线成功的，但那轮用了 s1，不能直接推断「录像中不按键也能刷新」。

## 描述符语义（本轮修正）

`Gamma+4` 是包含曲线选择等信息的描述符，`0xffffffff` 同时作为失效哨兵：

- 写 `0xffffffff` → 刷新 → 回到 `0x0A00807F`
- **只改一个节点，描述符同样回到 `0x0A00807F`**，不会变成 `0xAA00807F`

原函数离线分析显示 `0xAA00807F` 的最高三位为 5，选择对象中的自定义曲线；`0x0A00807F` 的选择号为 0，走固定表。修改固定表的节点不会改变选择号，因此不能用描述符辨认这张固定表的实际节点内容。成功必须结合完整回读：

```
19 个缓存节点 == 目标 且 描述符 != 0xffffffff
```

固定表改写路径需要核对完整源表和实际缓存；自定义选择分支还需要核对其自身数据来源。

`Param1` 的 dirty 常态是 `0xffffffff`，与 `Param0` 的写入无关，不要拿它判断状态。

## 工具

`tools/tcgen/`：

| 文件 | 职责 | 是否碰设备 |
|---|---|---|
| `tcgen.py` | 五条预设（stock / linear / log / flat / hc）+ 六条合法性校验 + 曲线对比图 | 否 |
| `tc_verify.py` | 地址链解析、双实例签名、19 源 + 19×2 缓存全量比对 | 只读 |
| `tc_write.py` | 入场检查、写入、dirty、s1、回读、默认恢复原厂 | 写入 |
| `tc_record.py` | 录制控制，`/proc/<pid>/fd` 判录制态，`--iso-ud` 开录后锁 ISO | 控制 |

合法性规则：19 点、整数、0–1023、严格递增、`Y[0]=0`、`Y[18]=1023`、X 必须等于固件固定表。

`tcgen.py gen log` 与 Codex 第五轮候选曲线**逐点相等**（Y[9]=492），作为生成器的交叉校验。

## 实机证据（2026-11-08 07:55）

M 档，开录后设 ISO500 并回读，settle 1s，各录 3 秒。

| 段 | 曲线 | Y mean | 帧间 sd | 空间 std | p5 | p50 | p95 |
|---|---|---:|---:|---:|---:|---:|---:|
| SAM_0384 | 原厂 | **63.26** | 0.08 | 47.99 | 4 | 67 | 176 |
| SAM_0385 | flat (k=255) | **98.83** | 0.07 | 47.96 | 16 | 114 | 184 |

像素级映射（A→B，按 8 码分组取中位）：`4→17`、`52→102`、`180→186`、`220→213`，相关系数 0.9529。

这些变化与候选的曲线形状一致，但非线性 ISP 后的编码 Y 不要求随曝光等比变化，不能仅凭该形状排除曝光漂移。本轮证据包未提供这对片段完整的实际 Tv/Sv/Av 回读。

另有两步前置验证：

- 写原值：`AFTER_CACHE_OK=1`、`AFTER_DIRTY=0x0A00807F`
- 单节点 500→499→500：源表与缓存同步变化并恢复

## 现场坑

| 坑 | 表现 | 处理 |
|---|---|---|
| `st key push mode` | XTEST BadValue | 正确语法 `st key mode m`（两参），只有 `rec`/`s1` 用 push/release |
| 开录回写 ISO | 录前 500，录后 `getusr` 回 `0x50000`，sv 102→129 | 开录后再设 ISO 并回读，跳过 settle 窗口 |
| 恢复被入场检查拦住 | 源表是 flat 时 `ENTRY_MISMATCH` | 目标 == stock 时跳过入场检查 |
| DHCP 漂移 | `.103` → `.106` | 用 `--host` 或 `NXHOST` |
| RTC 慢一年 | MP4 文件时间显示 2025 | 已知，不影响分析 |

## 边界

已证：曲线可写、可刷新、进入 HEVC、可逆。修改位于 RAM，重启预期重载固件原表，但本轮没有跨重启实测。

未证：

- 整体动态范围净增益（Codex 第五轮：局部暗部有 0.25–1.0 EV 倾向，严格门槛后区间含零）
- 跨重启的地址复用（每次 boot 需重新解析并校验）
- 录像中切曲线的稳定性（同一片段内可能出现亮度跳变）
- 与 3DLUT 的叠加关系（TC 在链路前段，改 TC 会移动 3DLUT 的输入域；现有 LUT **尚未**按实测曲线标定，标定文档写的是「凭感觉调（现状）」）

## 复现

```sh
cd tools/tcgen
python tc_verify.py --host <ip>                    # 只读，退出码分级诊断
python tc_record.py --host <ip> --seconds 3 --iso-ud 0x50008 --settle 1.0
python tc_write.py  --host <ip> --curve curves/flat.json --keep
python tc_record.py --host <ip> --seconds 3 --iso-ud 0x50008 --settle 1.0
python tc_write.py  --host <ip> --curve curves/stock.json   # 恢复
```

## 机端入口 `tc.sh`

已部署：机身 `/opt/usr/nx-ks/tc.sh`，SD 母本 `/mnt/mmc/scripts/tc.sh`，两侧 MD5 `191ecef6…`。
曲线库 `/opt/usr/nx-ks/tc/*.tcy` 与 `/mnt/mmc/scripts/tc/*.tcy`（19 行十进制，`#` 注释）。

```sh
sh /opt/usr/nx-ks/tc.sh status          # CURVE=stock|custom / Y9 / DIRTY / 完整 Y
sh /opt/usr/nx-ks/tc.sh list            # 名称 Y9 所在目录
sh /opt/usr/nx-ks/tc.sh set log         # 内置名或 .tcy 路径
sh /opt/usr/nx-ks/tc.sh off             # 恢复原厂
```

机端实测：`set log` → `OK=1 Y9=492` → `status` 报 `custom`；`off` → `OK=1 Y9=500` → `status` 报 `stock`。
无按键版本耗时约 **0.5s**（19 写 + 轮询 + 19 读）。
内置：`stock`(500) / `log`(492，k=63) / `flat`(607，k=255) / `hc`(264，k=7)。

失败路径：写入失败或刷新后缓存不符，脚本自动写回原厂并回读确认，退出码 2/3/4 区分阶段。

## 菜单入口（原生 mod_gui，非 NXUI）

不单独做 NXUI 面板。原生菜单是文本定义，零代码，与「分辨率修改」「LUT 滤镜」同级：

`gui_func.NX500` 新增一行：

```
button|TC 曲线|@/opt/usr/nx-ks/gui_tc.NX500
```

`gui_tc.NX500` 四个按钮：原厂 / Log / Flat / 高对比，各自调用 `tc.sh`。

已部署两侧（MD5 一致）：

| 文件 | MD5 |
|---|---|
| `tc.sh` | `073b9b52…` |
| `gui_tc.NX500` | `e098a20f…` |
| `gui_func.NX500` | `3c050044…` |

**未实测**：菜单内点击的实际体验（需要人工按 MENU 键；`st key push menu` 会触发 XTEST 段错误，无法远程注入）。菜单按钮执行 `tc.sh` 约 0.5s，期间菜单可能卡顿一下，属预期。

**未做**：开机自动加载、录像中切换的稳定性、与 LUT 的联动。

