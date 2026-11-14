# 两个用户报告的修复：PW 槽污染 + 默认码率

> 2026-11-14。来源：GitHub Discussion 2026-11-12，用户 **ssam87** 两条报告：
> ①「metol mod 导致 SD 卡卡顿、无法录像」（两台 NX500 + 同一张卡复现，换不带 mod 的卡正常）；
> ②「改了 custom 2 后换 filmlab 配方，custom 1 和 custom 2 都被影响」。
> 结论：**两个独立 bug，不是同一根因**。

## ① PW 槽污染（filmlab）

### 机制

`preview`/`commit` 的 UI 快路径把画布固定成 CUSTOM1（`SLOT=9`），A2 直推
（`0x134..0x13B`）也只写「自定义1」的运行时位置。但**发送那一刻**，相机仍把这次
改动归属到用户当前选中的那一档。

⇒ 用户停在自定义2 时浏览/提交配方：

| 槽 | 结果 |
|---|---|
| slot 9（自定义1） | 被 `prefman set` 写成配方值（设计如此） |
| slot 10（自定义2） | runtime 归属把它写成配方值（**意外**） |
| 备份 | 只有 `slot-9.txt`；slot 10 无还原点 ⇒ 不可恢复 |

`docs/current/ONDEVICE_SOP_2026-10-16.md` 里的 U6 实验（三自定义槽是否独立存储）
一直标「待」，从未上机 —— 这就是没人发现的原因。

### 修复

1. `pw_preenter_custom1()`：直推**之前**先把运行时档位落到 CUSTOM1，把归属窗口
   关进本来就该被写的那一档。`neutral`（面板「还原」）同样前置切换 ——
   「只改运行时」这个说法在 A2 直推面前不成立。
2. `backup_slot <n>` 参数化；打开面板时所在档位的槽也做首次写入前备份。
3. 常态（`FILMLAB_ENUM_CACHE` 已是 `0x140009`）零额外 `st` 调用，预览速度不变。

### 上机验证（2026-11-14，192.168.0.108）

```
初始: slot9=102/101/98 11/7/8/9   slot10=100/100/100 10/10/10/10
操作: setusr 20 0x14000a  (切到自定义2)
      FILMLAB_ENUM_CACHE=0x14000a filmlab.sh commit portra400
结果: slot9=108/100/93 11/6/9/8   slot10=100/100/100 10/10/10/10  ← 未污染
      档位回到 PW_CUSTOM2，reload=direct，七维 rc=0
恢复: slot9 写回原值 + 切回 CUSTOM1 + 直推原值
```

## ② 默认码率过高（auto/a_init.sh）

### 机制

`scripts/auto/a_init.sh` 每次开机把码率顶到：

```
Pro4K=160  ProHD=180  Hq4K=90  HqHD=90  HqVGA=180   (Mbps)
```

160 Mbps ≈ 20 MB/s 持续写入。普通 UHS-I（Class 10 / U1）标称下限只有 10 MB/s
⇒ 写缓冲一满，先表现为 UI 卡顿（用户说的 "SD card lag"），然后录像 abort。
原厂 4K Pro 约 60 Mbps。

这是 NX-KS 基线自带的值（画质优先取向），metol 直接继承，不是本项目新加的功能。

### 修复

- 默认改为 `80 / 100 / 50 / 60 / 40`，菜单「视频码率」仍可逐档改高（`br_set.sh`
  会重写 `a_init.sh`，所以改动是持久的）。
- `br_set.sh` 的输入框改为预填**当前值**（原来写死 180，会让人误以为当前就是 180）。

### 上机验证

```
应用后 systemctl 环境: Pro4K=80 ProHD=100 Hq4K=50 HqHD=60 HqVGA=40
渲染后 poker 参数:     0xb4095a08:c0f2c440 (pro1=80) ... 0xb40959b2:c0f26223 (hq6=40)
实测录像 4s: SAM_0461.MP4 = 40,468,497 B ≈ 80 Mbps  ← 码率生效且卡吃得住
（测试文件已删）
```

## 回归

`bash test_server/filmlab/flab_sim.sh` → **17/17 PASS**

顺带修好仿真器本身：`prefman` shim 原来对所有参数一律返回 100，而 HUE/SAT/SHARP/CON
的值域是 0-20 ⇒ `backup_slot` 校验必然拒绝，基线是 **7 FAIL**（长期误报）。
新增用例 6 钉住「非 CUSTOM1 档位不被污染」，含"停在 CUSTOM1 时零 setusr"的性能断言。

## 仍未做

- **U6 槽语义实验**：CUSTOM1/2/3 是否真的独立存储，仍需只读上机验证
  （`docs/current/ONDEVICE_SOP_2026-10-16.md:165`）。本次只是**阻止**了污染，
  没有回答"三槽能不能各存一套配方"。
- 卡侧 128MB swap（`swap.sh`）默认关闭，但开 swap 会加重 eMMC 写入 —— 与录像
  稳定性可能相关，未测。
