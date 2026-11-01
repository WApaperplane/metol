# 拍摄链加固研究：对焦包围 / HDR / 延时

> 日期：2026-10-31 ｜ 状态：**静态研究，未上机、未改脚本**
> 输入：`NX-WA-2.88.0-nxwa.1/scripts/`（实读）、`fw/v1.12` 原厂 `di-camera-app`（实读字符串/反汇编）、`test_server/slp/_pull_prefslot_info0.txt`（pref 键表）、`test_server/sysarch/raw/11_st_usrlist.txt`（capdtm userdata 表）
> 目的：回答「这三条链为什么现在不牢、固件里已经有什么、加固该加在哪一层」

---

## 0. 一句话结论

> ★★ **三条链的失效不是参数没调好，而是同一类架构错位：外部脚本把固件当成"无状态同步函数"来调，而它实际是一个"有状态、异步、会持久化"的状态机。**
>
> ★★★ **固件里本来就有一套成熟的加固设施**——间隔拍摄的三种时间基准 + 三种 BOOT CASE + 镜头位置持久化 + 已拍计数；drive 层的原子包围序列（AE/WB/PW/景深/AF）。我们现在的脚本是**绕开它、在外面自己造一套更弱的**。
>
> **加固 = 三层，缺一不可**：① 序列原子化（借 drive 让固件一次跑完 N 张）；② 状态可恢复（借 pref 落账，进程死了也能判）；③ 终止可判定（看门狗 + `trap` finally + 落盘核账）。

---

## 1. 现状解剖

| | 延时 | 对焦包围 | HDR |
|---|---|---|---|
| 载体 | `timelapse.tp` / `ramplapse.tp` / `wakelapse.sh` | `focus_stack`（ELF v2.30）+ `fstack.sh` | `1HDR.sh` |
| 触发 | `st app nx capture single` 逐张 | 同左，逐张 | `st cap capt single start`，逐张 |
| 时钟 | `$SECONDS`（shell 内建，秒级） | GUI 内 `sleep`/`gettimeofday` | `sleep 1` 固定 |
| 状态 | `/sdcard/presets/lapsing`（取消标志）+ `/sdcard/presets/hib`（焦点位置） | `/root/focus_stack.cfg` | 无 |
| 曝光控制 | 保持机身当前设置 | **每张重新 AE/AWB** | 直接改 `APPPREF_SHUTTER_SPEED_INDEX`(0xa340) |
| 终止 | `lapsedone` 弹窗 + `hybrid-sleep` | GUI 退出 | 无 finally |
| 恢复 | 无（`wakelapse` 靠 `reboot` 重启重跑） | 无 | 无 |

### 1.1 延时：三个实现，三种不同的漏

- `timelapse.tp`：`while [ $SECONDS -lt $end ]` + `sleep gap/2` → 拍 → `sleep gap/2`。
  **周期 = gap + 拍摄耗时**，不是 gap。拍 2000 张、单张 0.8 s、间隔 5 s ⇒ 累积漂移约 5 分钟。`$SECONDS` 是整秒，不补小数。
- 取消机制：`cat /dev/event0 > /sdcard/presets/lapsing &`——**任何按键/触摸事件都写入该文件**，`cancel()` 每秒看它非空就停。后果两条：① 碰一下机身就停；② 文件只会变大，长延时里 `cat` 一直往 SD 卡追加。
- `wakelapse.sh`：`rtcwake -m mem -s N && reboot`，靠开机 `auto/tl.sh` 续跑。项目里已记录过"休眠 = ping 通但 21/23 CLOSED"，这条路本身就有不醒的风险。
- `ramplapse.tp` 额外有 `calctmp` 钳位（快门 index 合法区间 200..65455，越界钳到 200/65456）——**这是三条链里唯一做了边界防护的地方**。

### 1.2 对焦包围：位置是开环的

`focus_stack` 的实拍路径（二进制字符串实证）：

```
st cap iq af mv 255 <abs_pos> 255      ← 移动焦点（绝对语义，与 refocus.sh 的 10 <Δ> <speed> 相对语义不同）
st app nx capture single               ← 立即拍，无回读、无等待确认
```

四个具体缺陷：

1. **开环**：`af mv` 是异步投递，脚本不读 `af pos` 确认到位就按快门。镜头越慢、步进越大，越容易拍到"上一格"。
2. **曝光漂移**：逐张 `capture` 之间固件会重新 AE/AWB。堆栈合成要求同曝光同白平衡，这是**合成失败的头号原因**，不是焦点不准。
3. **线性插值 ≠ 等景深**：near/far 之间按帧数均分位置，景深在近端变化快、远端慢，结果近端过疏远端过密。
4. **位置精度未知**：项目已有记录 `LENS 0x509 = SET_MF_POSITION`（`PATCH_SURFACE_REVIEW_2026-10-12.md` 标 ❓待验证），这可能是比 `af mv` 更干净的绝对定位入口。

### 1.3 HDR：一个没有 finally 的裸序列

`1HDR.sh` 的五档快门 index：**65 → 92 → 119 → 146 → 200**（前四档等差 27，末档跨 54）。每档 `prefman set 0 0xa340 l <v>` → `sleep 1` → 拍。

问题按严重度排：

1. **无 trap/finally**：中途任何失败（存储满、镜头错、用户退出），pref 停在 146 或 200，**下一次开机拍摄就是错的曝光**。这是三条链里唯一会**污染持久状态**的操作。
2. `st cap capt single start` 后固定 `sleep 1`，不判断是否真的写盘完成。
3. 五档之间没锁 ISO/WB，序列只能当"素材"用，不能直接合成。
4. 末尾一句 `st key click s1` 语义不明，可能是退出某种半按状态，但**它会在已经拍完后额外按一次快门键**——如果相机还在处理上一张，这一下可能被吞或触发意外行为。
5. 五档的 EV 跨度未标定：`0xa340` 是 `APPPREF_SHUTTER_SPEED_INDEX`，index→秒 的映射表项目里没有，所以"这五档到底是 ±几 EV"目前无法回答（见 §6 待测项）。

---

## 2. 失效模式：按机制归类，不按功能

把三条链的 bug 按**机制**合并，只剩五类——这是加固设计的靶子。

| 类 | 机制 | 三条链各自的表现 | 加固手段 |
|---|---|---|---|
| **A 时序** | 用"固定 sleep"代替"完成事件" | 延时漂移；包围拍到上一格；HDR 拍到未落盘 | 单调时钟对齐 + 目标时刻 sleep + 完成判据轮询（带退避） |
| **B 残留** | 改了持久状态但不还原 | HDR 停在最后一档快门；`timelapse.tp` 把 `APPPREF_TOUCH_OPERATION`(0xa690) 设 0 后靠 `tscon` 还原，若进程被杀则不还原 | `trap ... EXIT` + 启动时"幽灵状态清零" |
| **C 中断** | 进程死了就全丢 | 延时无续拍；包围无断点；HDR 无记录 | 落账文件（每帧 append）+ 启动时对账 + 幂等重入 |
| **D 资源** | 单核 + SD 写 + 电池 | 长延时把 exfat 目录项撑爆（本项目已踩过）；拍摄中 `cat /dev/event*` 常驻 | 单实例锁；取消改用 `read -t`；定期 `sync`；张数上限 |
| **E 判据** | 没有"成功"的定义 | 三条链都只弹窗，不核张数 | 每帧后核文件数；结束输出 `expect/actual/missing` |

★ **B 类最危险，因为它跨会话**：A/C/D 只毁这一次拍摄，B 会让下一次拍摄也错。

---

## 3. 固件已有的加固设施（本次新发现，是加固的真正着力点）

### 3.1 drive 层：包围是固件内的原子序列

`st app` 的原厂帮助里直接写着（`di-camera-app`，文件偏移 `0x36398d`，非运行时地址）：

```
st app drive [single|conti_n|conti_h|timer|bracket]
```

对应的参数键全在 pref（`_pull_prefslot_info0.txt`）：

| pref 地址 | 键 | 语义 |
|---|---|---|
| `0xa5d8` | `APPPREF_DRIVE_SET_CONTINOUS` | 连拍设置 |
| `0xa5dc` / `0xa5e0` | `..._CONTI_H_FRAME` / `..._CONTI_N_FRAME` | 高速/普通连拍张数 |
| `0xa5e4` / `0xa5e8` | `..._SET_TIMER` / `..._SET_TIMER_SELF` | drive 定时器 |
| `0xa5ec` | **`APPPREF_DRIVE_SET_BKT`** | **包围模式选择** |
| `0xa5f4` | **`APPPREF_BRK_AF_STEP`** | **AF 包围步进** |
| `0xa5f8` | **`APPPREF_BRK_AE_STEP`** | **AE 包围步进** |
| `0xa5fc` | `APPPREF_BRK_WB_SET` | WB 包围设置 |
| `0xa600` | `APPPREF_BRK_PW_TYPE` | Picture Wizard 包围 |
| `0xa604` | **`APPPREF_BRK_DEPTH_TYPE`** | **景深包围类型** |
| `0xa628` | `APPPREF_HDR_LEVEL` | HDR 强度 |
| `0xa624` | `APPPREF_DYNAMIC_RANGE` | 动态范围（Smart Range） |

capdtm 侧的对应 userdata（`11_st_usrlist.txt`）：

| ID | 名字 | 当前值样例 |
|---|---|---|
| 10 | `USERDATA_DRIVE` | `DRIVE_SINGLE` = `0x000A0001` |
| 32 | `USERDATA_AEBRKORDER` | `AEBRKORDER_PZM` |
| 33 | `USERDATA_AEBRKAREA` | `AEBRKAREA_1OVER3` |
| 34 | `USERDATA_WBBRKSET` | `WBBRKSET_AB3` |
| 35–47 | `USERDATA_PWBRK*` | 13 种 Picture Wizard |
| 67 / 76 | `USERDATA_HDR` / `USERDATA_HDRLEVEL` | `HDR_OFF` / `HDRLEVEL_LV2` |
| **92** | **`USERDATA_DEPTHBRKAREA`** | `DEPTHBRKAREA_1` |
| 93 / 94 | `USERDATA_INTERVAL` / `USERDATA_TIMELAPSE` | `INTERVAL_OFF` / `TIMELAPSE_OFF` |

★★ **这几行改变了问题的性质**：原厂**本来就有对焦包围**（`BRK_AF_STEP` + `BRK_DEPTH_TYPE` + `DEPTHBRKAREA`），也有 AE 包围（`BRK_AE_STEP` + `AEBRKAREA` + 顺序 `PZM`）。`focus_stack` 和 `1HDR.sh` 是在重复实现固件已具备的能力，而且实现得更弱（开环、无锁曝光、无原子性）。

**推断（高置信，待上机）**：`USERDATA_DRIVE` 的编码是 `(data_id << 16) | enum`（`DRIVE_SINGLE` = `0x000A0001`，AFMODE 的既有用法 `0x00070003` 同构）。所以 `st cap capdtm setusr DRIVE <0x000A00xx>` 可以**精确**切 drive 档，不依赖 `st key drive` 的"下一个"语义。

### 3.2 interval 层：原厂把"断电续拍"做完了

pref 里有 **0xa76c–0xa804 共 25 个键**，构成一个完整的可恢复状态机：

| 组 | 键 | 用途 |
|---|---|---|
| 参数 | `INTERVAL_CAPTURE_SET` / `TIME_HOUR|MIN|SEC` / `TIME_NUM` | 开、间隔、张数 |
| 计数 | `INTERVAL_TIMER_COUNT` / `INTERVAL_CAPTURE_CURR_COUNT` | 目标 / 已拍 |
| **三种时间基准** | `SAVE_*_START`、`SAVE_*_PASSED`、`SAVE_*_POWEROFF`、`SAVE_*_PAUSE_START`、`SAVE_*_PAUSE_HOLD` | 起点 / 已过 / 关机时刻 / 暂停起点 / 暂停保持 |
| 断电语义 | **`INTERVAL_CAPTURE_POWEROFF_TYPE`** | 区分"正常关机 / 低电 / 拔电" |
| 引导语义 | **`INTERVAL_CAPTURE_BOOT_FOR_RTC`** | 本次启动是不是 RTC 唤醒 |
| 镜头 | `INTERVAL_LENS_INFO_FOCUS`(`_D`)、`ZOOM`(`_D`)、`INTERVAL_SET_LENS_INFO` | **保存上次焦点/变焦位置**（防跑焦、防变焦漂移） |
| 启动 | `INTERVAL_CAP_START_MODE`、`TIME_BEGIN_*`、`TIME_BEGIN_REMAIN_TIME` | 起始模式与剩余时间 |

对应日志（`di-camera-app`，文件偏移 0x37bc24 起）：

```
[INTERVAL] BOOT CASE 1 : RTC BOOT
[INTERVAL] BOOT CASE 2 : LOW BATTERY OR PAUSE
[INTERVAL] BOOT CASE 3 : eCAP_INFO_INTERVAL_PAUSE_HOLD
[INTERVAL] BOOT CASE 3 : ETC
[INTERVAL] over wait => stop :%d
[INTERVAL] begine + pause => must exit pause!!! :%d
```

★★★ **这就是"延时加固机制"的标准答案**，而且是原厂写了十年的：开机时按 `POWEROFF_TYPE` + `BOOT_FOR_RTC` + `PAUSE_HOLD` 分成三种 BOOT CASE 决定"续拍 / 保持暂停 / 放弃"，用 `CURR_COUNT` 对账，用 `LENS_INFO` 复位镜头。

我们自己的 `timelapse.tp` 一个都没有。

### 3.3 HDR 层

- `USERDATA_HDR`（`HDR_OFF`/`HDR_ON`）+ `USERDATA_HDRLEVEL`（`HDRLEVEL_LV2`）+ `USERDATA_SMARTRANGE`（`SMARTRANGE_OFF`）：这是**机身单次拍摄内的合成**，出一张。
- 菜单 id：`depth2_HDR`、`depth2_one_shot_hdr`、`menu_dep1_one_shot_hdr`、`get_hdr_value_string`、`UI_Restore_Hdr_Value_One_Touch_Hdr`。
- `1HDR.sh` 走的完全是另一条路（5 张独立帧，后期合成）。两者不冲突，但**目的不同**：机身 HDR 是"直接出片"，`1HDR.sh` 是"给后期留素材"。加固要分开谈。

### 3.4 调用面盘点

| 通道 | 形式 | 语义 | 适用 |
|---|---|---|---|
| `st app drive <mode>` | 高层 | 切 drive 档（等价拨盘） | 包围/连拍/定时 |
| `st key drive <mode>` | 事件注入 | 同上，走按键事件 | 备用 |
| `st cap capdtm setusr <name|id> <val>` | 参数 | 写 userdata（每次 ≈1.2–1.3 s，见 nxwa.5 计时） | 精确设参 |
| `st cap capt single start` | 动作 | 触发单张 | 逐张链 |
| `st app nx capture single` | 动作 | 同上（app 层） | 逐张链 |
| `st cap iq af mv <a> <b> <c>` | 动作 | 移动焦点（`10,Δ,speed` 相对 / `255,pos,255` 绝对） | 对焦链 |
| `st cap iq af pos` | 读 | 焦点位置回读 | 闭环判据 |

★ 成本约束（**实测数字，来自 nxwa.5**）：`st cap capdtm getusr` 单次 **1.31 s**，`setusr` **1.23 s**。这决定了"每张都回读确认"在设计上不可行——10 张堆栈光回读就 +13 s。加固必须做**分级确认**：整段前后各一次全量核账，段内只在超阈值时回读。

---

## 4. 加固设计

### 4.1 通用骨架（三条链共用）

```
acquire_lock          # 单实例：/tmp/nxks_cap.lock（flock），三条链互斥
snapshot_state        # 拍前：快门 index / ISO / WB / AFMODE / DRIVE / 焦点位置 → 落盘
trap restore EXIT     # 任何退出路径都还原 snapshot + 释放锁
for each step:
    wait_until(t0 + n*interval)     # 单调时钟，不用 $SECONDS
    act()                            # 一次动作，不重试超过 N 次
    verify_frame()                   # 落盘核账（文件数 / 文件名连续性）
    append_ledger()                  # 每帧一行，fsync
finalize              # expect vs actual vs missing，写 summary
```

三条铁律：

1. **不进 `trap` 的状态，等于没还原。** 所有 `prefman set` / `setusr` 必须先 `get` 存原值。
2. **不落盘的进度，等于没进度。** 进度写 `/mnt/mmc/nxks/lapse/<job>.log`，一行一帧，`sync` 后再拍下一张。
3. **没有 `expect/actual` 的结束，等于没结束。** 弹窗不算完成判据。

### 4.2 延时

| 层 | 措施 | 具体做法 |
|---|---|---|
| 时序 | 目标时刻制 | `t0=$(date +%s.%N)`；第 n 帧 `target = t0 + n*gap`；`now < target` 才 sleep，落后则**跳帧并记账**（`skipped=n`），绝不追赶式连拍 |
| 中断 | 落账 + 续拍 | 每帧写 `seq,timestamp,filename`；启动时读账本算 `next_seq`，从断点继续（幂等） |
| 取消 | 换掉 `cat /dev/event*` | 用 `read -t 1 -n 1 </dev/input/event0` 或独立小进程只识别特定键；不再往 SD 卡追加 |
| 资源 | 张数上限 + 空间预检 | 开拍前 `st app isfull` + `df`；按"单张大小 × 张数 × 1.2"预检；每 100 帧 `sync` |
| 状态 | 借原厂语义 | 若改用原生 interval（`USERDATA_INTERVAL`），直接获得 §3.2 的三 BOOT CASE 续拍；自建链则至少复刻 `CURR_COUNT` 与 `LENS_INFO` 两个字段的语义 |

★ 最省力的路线不是加固 `timelapse.tp`，而是**先验证原生 interval 能否被外部驱动**（`setusr INTERVAL` + 开始/停止入口）。能驱动就整条换掉，加固成本归零。

### 4.3 对焦包围

| 层 | 措施 | 具体做法 |
|---|---|---|
| 序列 | 优先借 drive | 若 `BRK_AF_STEP`/`BRK_DEPTH_TYPE` 可用：`setusr DRIVE 0x000A00xx` 切到 AF/景深包围，一次触发由固件跑完 N 张——**曝光锁定、镜头移动、张数全部由固件保证** |
| 曝光 | 锁三角 | 拍前 `st app mode m` + 固定 ISO + 手动 WB；或先 AEL 锁再开始。**这一步比焦点精度更决定合成成败** |
| 位置 | 分级闭环 | 段首/段尾各回读一次 `af pos`（2×1.3 s 可接受）；段内仅在 `|Δ| > 阈值` 时回读重试一次。不要每张回读 |
| 规划 | 等景深步进 | 用超焦距公式算步进：`Δ = 2·N·c·(1+m)/m²`（N 光圈、c 容许弥散圆、m 放大率），近端密远端疏；不要线性均分 |
| 精度 | 试 `LENS 0x509` | 若 `SET_MF_POSITION` 验证可用，替换 `af mv`：绝对定位 + 可回读，去掉"异步投递"这一层不确定性 |
| 判据 | 张数 + 焦点 | 每张核文件；结束输出每个位置的实际 `af pos`，与目标比对 |

### 4.4 HDR

分两条，不要混：

**A. 要"直接出片"** → 用机身 HDR（`setusr HDR` + `HDRLEVEL`）。加固点只有两个：拍前存原值、`trap` 还原。

**B. 要"后期素材"** → 把 `1HDR.sh` 从"裸序列"改成"事务序列"：

1. `snapshot`：`prefman get 0 0xa340 b` 存原快门 index。
2. `trap 'prefman set 0 0xa340 l $ORIG; st app mode $ORIG_MODE' EXIT INT TERM`。
3. 用**原生 AEB** 而不是手改快门：`setusr DRIVE 0x000A00xx`（bracket）+ `AEBRKAREA`（步进）+ `AEBRKORDER`（顺序）。固件保证等间隔、连续写盘、不中途 AE。
4. 若必须手改快门：删掉末尾的 `st key click s1`，改成显式 `verify 5 files → restore`。
5. 标定五档的真实 EV：读 `getusr SHUTTER_SPEED` 的名字（如 `1/500`）而不是记 index。

---

## 5. 判据（怎么算"加固成功"）

| # | 判据 | 测法 | 通过线 |
|---|---|---|---|
| H1 | 延时无累积漂移 | 拍 300 帧 @5 s，比对第 1 与第 300 帧的时间戳 | 总漂移 < 2 s |
| H2 | 延时可续拍 | 拍到第 100 帧强杀进程 → 重启 → 观察是否从 101 继续 | 不重拍、不跳号 |
| H3 | 取消不误触 | 拍摄中轻触屏幕 | 不中断 |
| H4 | 状态不残留 | HDR 中途 `kill -9` → 重启读 `0xa340` | 等于原值 |
| H5 | 包围曝光一致 | 同一包围序列 5 张的 EXIF 曝光/ISO/WB | 除快门外全同 |
| H6 | 包围张数完整 | `expect N` vs 目录新增数 | 相等 |
| H7 | 互斥 | 延时运行中启动包围 | 第二个拒绝启动并提示 |
| H8 | 单核不被打满 | 三条链各自运行 5 分钟，`top` 采样 | 无持续 100% 单核 |

---

## 6. 上机验证清单（一次上机、只读优先、按序）

> 全程不改脚本、不重启 `di-camera-app`。预计 10 分钟。

| 步 | 动作 | 期望 | 风险 |
|---|---|---|---|
| 1 | `st app drive` (无参) | 打印 `[single|conti_n|conti_h|timer|bracket]` 帮助 | 零 |
| 2 | `st cap capdtm getusr DRIVE` | 打印当前 drive 名（如 `DRIVE_SINGLE`） | 零 |
| 3 | 循环 `setusr DRIVE 0x000A000N`（N=0..12），每次 `getusr DRIVE` 读回 | 得到 **drive enum 全表**；记录哪些是 bracket 档 | 低（切档，不拍） |
| 4 | 对每个 bracket 档读 `getusr AEBRKAREA / BRK_AF_STEP` 同源项 | 确认步进档位名与取值 | 零 |
| 5 | `st cap capdtm getusr DEPTHBRKAREA`，试 `setusr` 三档 | 景深包围步进可写 | 低 |
| 6 | `getusr INTERVAL` / `TIMELAPSE`，读 `prefman get` 的 `0xa76c`–`0xa804` 全部 | 拿到原厂 interval 状态快照 | 零 |
| 7 | `prefman get 0 0xa340 b` 后记下当前快门 index；再 `getusr SHUTTER_SPEED` | 建立 **index ↔ 快门时间** 对照（标定 `1HDR.sh` 的 65/92/119/146/200 真实 EV） | 零 |
| 8 | `st cap iq af pos` 计时 ×5 | 确认回读成本（是否也 1.3 s） | 零 |
| 9 | `st cap capt single start` 计时 + 立即 `ls DCIM` | 判断该命令是同步还是异步（决定要不要轮询落盘） | 低（拍 1 张） |

★ 第 3 步是本次最关键的未知：**拿到 drive enum 表，包围链就能整条改成固件驱动**。建议单独做、单独记录，不要和其他实验混。

---

## 7. 不做的事 / 已知风险

- **不重写 `focus_stack`**：它是二进制、无源码、GUI 完整。加固应做"外层包装 + 参数预置"，不是逆向重写。
- **不碰 `systemctl hybrid-sleep` 这条路**：`wakelapse.sh` 的 `rtcwake + reboot` 在 NX500 上有不醒记录，加固不应建立在"能可靠休眠"的假设上。
- **不在延时运行时改 drive**：`cmd_change_to_next_drive` / `UI_Callback_Stop_Drive_Dial_Lock3a` 表明切档会中断 3A 锁，长曝光链上切档风险未知。
- **`af mv` 的 255 语义未证实**：`focus_stack` 用 `255,pos,255`（绝对），`refocus.sh` 用 `10,Δ,speed`（相对）。两者是否同一参数位的不同解释，需上机差分验证，**不要凭字面推断**。

---

## 附：证据索引

| 结论 | 证据位置 |
|---|---|
| `st app drive [...]` 存在 | `di-camera-app` 文件偏移 0x36398d |
| interval 三种 BOOT CASE | 同上 0x37bc24 / 0x37bc48 / 0x37bc78 |
| `Ui_Check_Restart_Interval` 等 24 个 interval 函数 | 同上 0x372f5c–0x3734xx（`__func__` 串，文件偏移） |
| pref 键全表（drive/bracket/interval/HDR） | `test_server/slp/_pull_prefslot_info0.txt` L273–L405 |
| capdtm userdata 97 项 | `test_server/sysarch/raw/11_st_usrlist.txt` |
| `st cap` 子树与 PLT 符号 | `libshell-command.so`（`shell_capture.cpp`） |
| capdtm 单次 1.2–1.3 s | `docs/releases/NX-WA-2.88.0-nxwa.5.md` §为什么慢 |
| `focus_stack` 的调用序列 | 二进制字符串：`/usr/bin/st cap iq af mv 255 %d 255`、`/usr/bin/st app nx capture single` |
| `1HDR.sh` 五档值 | `scripts/1HDR.sh`（65/92/119/146/200） |
| 本地分析脚本 | `_tmp/dicam_probe.py`（exidx 边界 + literal-pool 交叉引用 + PLT 名解析） |
