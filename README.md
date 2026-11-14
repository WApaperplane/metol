# Metol（旧称 NX-WA）

Samsung NX500 / NX1（Tizen / DRIMe5）增强固件 mod，基于社区上游
[`ottokiksmaler/nx500_nx1_modding`](https://github.com/ottokiksmaler/nx500_nx1_modding) 改造与扩展。

**仓库** [WApaperplane/metol](https://github.com/WApaperplane/metol)（fork；默认分支 `nxwa`）·
**许可** AGPL-3.0（血缘见 [ATTRIBUTION.md](ATTRIBUTION.md)）·
**下载** [Releases](https://github.com/WApaperplane/metol/releases)

> English version: [README_EN.md](README_EN.md)

**最新 v2.88.0-nxwa.15.3**（2026-11-10）— 双语发行：每次发版两个包，
`NX-WA-<ver>.zip`（中文）与 `NX-WA-<ver>-EN.zip`（英文菜单 / 英文 NXUI 面板 / 英文 README），
Release 说明中英并列。

---

## 30 秒上手

1. 把 `NX-WA-<ver>.zip` 解压到 **SD 卡根目录** → 插卡 → 屏上「安装完成」→ 自动重启。
2. **手动开一次蓝牙**（机身菜单 → 系统设置 → 启用蓝牙）—— mod 的开机钩子靠它初始化。
3. 记住四个按键：

| 按键 | 打开 | 备注 |
|---|---|---|
| **EV + AEL** | FilmLab 滤镜条（79 条配方） | 点选即时预览，`保存并关闭` 落盘 |
| **EV + WiFi** | 3D LUT 面板（86 张表） | 点选即换表，**不用半按** |
| **双击 EV** | 主菜单（NXUI 分页界面） | 菜单内容见「[相机菜单一览](#相机菜单一览)」 |
| **半按快门** | 关闭当前面板 | LUT/FilmLab 面板关闭后**保留当前效果** |

> 组合键都是「按住 EV 不放，再按另一个键」；单击 WiFi 仍是相机原生的开/关 WiFi。

装完想看菜单里每一项干什么、出问题该看哪个日志，直接跳
[相机菜单一览](#相机菜单一览) 和 [排障](#排障先看日志再动手)。

## 排障：先看日志，再动手

### 三条恢复命令（先保命）

```sh
sh /opt/usr/nx-ks/nxui.sh disable    # UI 出问题 → 回老的 mod_gui 菜单
sh /opt/usr/nx-ks/lut.sh off         # 颜色不对 → 回原厂 LUT
sh /opt/usr/nx-ks/tc.sh off          # 录像曲线 → 回原厂
sh /opt/usr/nx-ks/nxui.sh diag       # 面板能不能用，一次看全
```

`nxui.sh diag` 会打印 `bin / model / disabled / enabled / available` 五项；
`available: no` 只有三种原因：二进制没装好、机型是 NX1、或者被 `disable` 过。

### 日志在哪

| 路径 | 谁写 | 断电后还在？ |
|---|---|---|
| `/mnt/mmc/nx-ks/pwrlog.txt` | `pwrlog.sh`（15.1+，每 30 s 一条 + 开机记 `BOOT`） | ✅ SD |
| `/mnt/mmc/lut/state/*.log` | `lut.sh` 每一步（write / view / still / bv / lutptr / kick） | ✅ SD |
| `/mnt/mmc/filmlab/last.log` | 配方 apply 的最后一次上下文 | ✅ SD |
| `/opt/usr/nx-ks/onboard.log` | 装机自检（telnet / ssh / nxui diag / IP） | ✅ 机身 p10 |
| `/tmp/nxui.log` | 面板全部 `READY / ACTION / BACKEND ok=…` | ❌ 关机即失 |
| `/tmp/db.log` | dropbear（ssh 起没起、为什么没起） | ❌ |
| `/tmp/nxwa-lut-video/watch.log` | 录像 LUT 监视器 | ❌ |

**相机自己关机/重启**是唯一必须提前取证的问题：`pwrlog.txt` 里最后一条
（`up=… pwr=… ssh=… ui=… lut=…`）加上 `pwrlog.sh dump 60` 的时间轴就是全部线索，
`/tmp` 里的东西事后一律拿不到。

### 常见症状对照

| 症状 | 先看 |
|---|---|
| 按 EV+AEL 出来的是原版 NX-KS 弹窗 | `nxui.sh diag`；`available: no` 见上 |
| 面板点了没反应 / 一直"正在发送" | `/tmp/nxui.log` 尾部 `BACKEND ok=0` + 对应 `lut.sh` 的 state 日志 |
| 换了 LUT 画面不变 | `lut.sh status`；再半按一次快门（p7 自己的 Load 事件） |
| 颜色偏 / 想确认是不是 LUT 的锅 | `lut.sh off` 前后对比；`lut.sh stock` 导出原厂表 |
| 相机自己关机 | `/mnt/mmc/nx-ks/pwrlog.txt` → `sh /opt/usr/nx-ks/pwrlog.sh dump 60` |
| ssh 连不上 | 菜单 `IP: … [SSH on]`；`sh /opt/usr/nx-ks/ssh_hint.sh --start`；`/tmp/db.log` |

## 安装

1. 把 `info.tg`、`nx_cs.adj`、`install.sh`、`scripts/` 放到 **SD 卡根目录**（或把 `NX-WA-<version>.zip` 解压到根目录）。
2. 插卡 → 自动安装，屏上显示「安装完成」。
3. **手动开一次蓝牙** —— mod 的开机钩子靠它初始化。

- 固件：NX500 **1.12** / NX1 **1.41**，其它版本拒绝安装。
- 两个包：`NX-WA-<ver>.zip`（中文）与 `NX-WA-<ver>-EN.zip`（英文菜单 + 英文 NXUI 面板 + 英文 README）。功能完全相同，只有文案语言不同。装错语言再装回另一个包即可，`nxui/lang` 随包覆盖。
- 再插一次卡 = **增量同步**（只覆盖、不删除；永不自动卸载）；卸载走相机菜单里的 `卸载模块`。
- 安装 / 同步 / WiFi push / 回滚：[SYNC.md](SYNC.md)（中英双语）。

## 远程登录（SSH）

远程只有一条路：**dropbear ssh，端口 22**（随包，`init.sh` 开机自启）。telnet 与 FTP
自 2026-11-02 起退役；`telnetd` 二进制**不在发布包里**（2016 年的三星原件，故意不入库）。

| 方式 | 命令 | 前提 |
| --- | --- | --- |
| 空密码 | `ssh root@<相机IP>` | 直接回车（dropbear `-B`）；部分客户端拒绝空密码 |
| 公钥（推荐） | 把自己的 `id_ed25519.pub` 追加到相机 `/opt/usr/nx-ks/dropbear/authorized_keys`，再 `sh /opt/usr/nx-ks/ssh_hint.sh --start` | 需要先用空密码进去一次 |
| 菜单 | 相机菜单 → `IP: 192.168.x.x [SSH开]` | 显示状态；按下弹窗给出连接串，没起会顺手拉起 |

主机私钥 `dropbear_ed25519_host_key` 首次开机自动生成（p14 保留，刷机不丢）。
排障看 `/opt/usr/nx-ks/onboard.log` 与 `/tmp/db.log`。

---

## 相机菜单一览

主页六个入口 + 一行状态；下面把每一页的项写全，标了来源（★ = 本项目新增，
上游 = 继承 NX-KS 2.88，未改动行为）。

### 主页

| 项 | 作用 |
|---|---|
| 延时摄影 → | 见「延时摄影」 |
| 实用功能 → | 见「实用功能」 |
| 对焦 & 配置文件 → | 见「对焦」 |
| 系统设置 → | 见「系统设置」 |
| 休眠 | 立即休眠（`hibernate.sh`，上游） |
| 远程控制 ☑ | 开关 Web 相册 / 遥控（`nx-rc.sh`，上游） |
| `IP: x.x.x.x [SSH开]` | ★ 显示 SSH 状态；按下弹连接串，没起会拉起 dropbear |

### 延时摄影

| 项 | 作用 |
|---|---|
| 唤醒延时 | 定时唤醒后开拍的延时流程（`wakelapse.sh`，上游） |
| 渐变曝光 → | 延时里的曝光渐变：总时长 / 间隔 / 曝光起点终点 / 渐变开始与时长 / 延时启动，`开始` 走 `ramping.sh`（上游） |
| 模块延时 | `mod_lapse`（上游二进制） |
| 即将推出 | 占位 |

### 实用功能

| 项 | 作用 |
|---|---|
| 远程保存 ☑ | 远程保存开关（`rem.sh`，配置 `remote.cfg`，上游） |
| 视频码率 → | 五档码率（Pro4K / ProHD / Hq4K / HqHD / HqVGA）与当前值，模板 `gui_br.tp`（上游） |
| 变焦缩放 | 设延迟 → 拍一张 → 镜头回广角，做变焦爆发（`zoomzoom.sh`，上游） |
| 分辨率修改 → | 见「分辨率映射」 |
| 批量录制 | 按分钟分批连续录像，可选隐藏录制界面（`brec.sh`，上游） |
| HDR | M 档五档快门（65 / 92 / 119 / 146 / 200）连拍 5 张，**机身不合成**，后期自己叠（`1HDR.sh`，上游） |
| LUT 滤镜 | ★ 直接进 NXUI 的 LUT 面板（等同 EV+WiFi） |
| TC 曲线 → | ★ 录像曲线：原厂 / Log / Flat / 高对比 |
| `版本 v2.88` | 版本弹窗（`ver.sh`） |
| 摄像模式 ☑ | 快门键变录像键（`camcorder_mode.sh` → `shutter_to_rec`，上游） |

### 对焦 & 配置文件

| 项 | 作用 |
|---|---|
| 对焦堆栈 | 按张数 / 间隔自动移焦（`fstack.sh`，配置在 SD：`/mnt/mmc/scripts/focus_stack.cfg`，上游） |
| 对焦按钮 | 长按存位置、点击回位置（位置表 `/mnt/mmc/scripts/af_positions.txt`，上游） |
| 配置文件 → | 保存 / 加载 `EV+UP`、`EV+DN`、完整备份（`save_UP.sh` / `EV_UP.sh` / `FullSave.sh` …，上游） |
| 对焦速度 | 设拉焦速度 1–255（写 `fps` 环境变量，`fpspeed.sh`，上游） |
| 自定义选项 / 自定义按钮 | 模板占位，可改成自己的脚本（`cCheckbox.sh` / `cButton.sh`，上游） |

### 系统设置

| 项 | 作用 |
|---|---|
| 静音快门 ☑ | 电子快门 `ADJUSTSHUTTERTYPE 0x750001`（`rolling_shutter.sh`，上游） |
| 禁用菜单键 ☑ | 关掉 MENU 键的默认 OSD 行为（`z_button.sh`，上游） |
| 无录制限制 ☑ | 解除录像时长限制（`prefman 0xc2d9=1`，上游） |
| 开机重新对焦 ☑ | 开机按休眠前记录的位置重新对焦（`refocus.sh`，上游） |
| 无镜头释放 ☑ | 无镜头也能释放快门（`prefman 0xc2dd=1`，上游） |
| 启用蓝牙 ☑ | 重启蓝牙服务（`bt.sh`，上游） |
| 叠加显示 ☑ | 打开 `onscreen_ov` 叠加层（上游） |
| 卸载模块 v2.88 | 卸载 mod（`uninstall.sh`） |

### 分辨率映射

把某个拍摄档位（UHD / DC / VGA）映射成另一种分辨率，八项互斥，**同一档位一次只开一个**：

| 档位 | 可映射到 |
|---|---|
| UHD | 2.5K 全宽（2560×1440）/ DC 4K（4096×2160）/ FHD（1920×1080） |
| DC | 2.5K / UHD / FHD |
| VGA | UHD / DC 4K |

开关落在机内偏好，改完回取景器确认实际输出。属于上游 NX-KS 能力。

---

## FilmLab 胶片配方

| 族 | 例子（共 79 条：彩色 71 + 黑白 8） |
| --- | --- |
| 彩色负片 | Portra 400/800、Gold 200、Ektar 100、Superia 400、ProImage 100、Vista 200 … |
| 反转片 | Velvia 50/100、Provia 100F/400X、Ektachrome E100、Kodachrome 25/200 … |
| 黑白 | TriX 400、HP5 Plus、Delta 3200、T-MAX 100/400、Acros 100、XP2 Super … |
| 电影卷 | CineStill 800T/50D、Vision3 250D/500T、Double-X 5222、Eterna 500T |
| 风格 | 青橙 / 暖旧 / 冷峻 / 褪色 / 高调 / 低调 / 棕褐 / 漂白 / 蓝调时刻 / X-Pro 交叉 |
| 相机内置风格 | 理光 GR（正片 / 负片 / 怀旧 / 漂白 / 交叉冲洗）、宾得 Custom Image（鮮やか / 反转片 / 銀残し / ほのか / 里び / Gold） |

- **改配方不用改代码**：编辑 `/mnt/mmc/filmlab/recipes.json` → 拷回 SD → 重开菜单（自动重建）。仓库权威源是 `scripts/filmlab/recipes.json`，上位机一条龙 `test_server/filmlab/flab.py add|edit|rm|lint|deploy`。
- 配方 = Picture Wizard 七维向量（R/G/B 增益 + HUE/SAT/SHARP/CONTRAST），固定落在「自定义1」槽，位置恒定。
- **全七维直推需要 A2 固件**（`patch-a2/` 随包，刷法见「[A2 p7 补丁](#a2-p7-补丁可选)」）。官方固件下 R/G/B/HUE 需机身「画面向导 → 自定义1」确认一次 —— 这是 p7 归一化器域界（`0x100–0x12e`）的结构性限制，不是脚本 bug。
- 诚实边界：WB 不在配方内（请用机身白平衡）；配方是全局色彩向量，做不出高光滚降 / 分区曝光；NX1 上不启用（prefman 偏移只在 NX500 1.12 实证）。
- 判据只认一条：`sh /opt/usr/nx-ks/filmlab.sh check` 直接读 ISP 手上那七维跟配方比对（只读、零风险）。**"值变了" ≠ "被消费"**。
- 另有 `scripts/nx-rc/MOBILE_MOBILE.sh`（双击 WiFi = 零 UI 轮换下一条配方）——不进安装链，需要时手动放到 `/opt/usr/nx-ks/`。

## 3D LUT

| 项 | 现状 |
| --- | --- |
| 表格式 | `4913×4B {Cr,Cb,Y,pad}`，索引 `((Y*17+Cb)*17+Cr)*4`，槽 19,712 B，步长 `0x4D00`（10-19 实机闭合，旧的 RGB 命名已作废） |
| 换表 | 写 19,712 B 进工作槽（A18 `0x81119F00`）+ 改**四张**登记表全部指向它 + **自动等帧结束后装载**（`nx_lutload.arm`，不用半按） |
| 登记表 | `View4` 四项（色彩空间×屏幕色彩）+ `Still6` 六项 + `BV12` 十二项 —— **一项都不能漏**，漏了就是"取景有、照片没有" |
| 导入 | `.cube → 19,712 B 槽表`：机身 `cube2lut.arm` 一条命令，或 PC 端 `test_server/isp/nx3dlut.py` |
| 生成依据 | 按**实测相机输入域**：响应斜率 `log2(码值)/EV = 0.809`，不是 sRGB 的 0.45（差 1.8 倍）。按 sRGB 假设做的表会在暗部被二次压缩。86 张定档集里，47 张沿用上一版（其中 34 张已按真实响应重生成：25 张 G'MIC + 9 张配方），39 张来自 11-08 社区批次 |
| 取景 / 成片 | 取景只认 `View4`；成片有**两条互斥分支**（屏幕色彩开→`BV12`，关→`Still6`），两条都要指过去 |
| 视频 | `apply` 之后直接按录像键，**首帧就带表**（p7 的 23 项档位指针表被整体指到 A18），`off` 自动停监视。**连续录制 4 分钟实测正常**；更多帧率组合未覆盖 |
| 面板关闭 | **不还原**：`保存并关闭` / 半按只是关面板，表继续生效；要回原厂按面板里的「还原原厂」或 `lut.sh off` |
| 边界 | 全是内存操作，**断电即回原状**（「开机即生效」仍需改固件镜像）；sRGB 颜色可信，AdobeRGB 只保证生效 |
| 装载写序 | ⛔ 自己写 `+0x00C` 必须走完整 8 步：`OnOff` → 清/置 Acc → 地址 → Cfg 通道位 → bit8 脉冲 → **末尾复位 Acc**，并等取景帧结束。只写地址 + 脉冲就会花屏 —— 这才是 10-08 那条「禁区」的真实原因 |

### 滤镜库与混合

| 能力 | 用法 |
| --- | --- |
| 库管理 | `lut.sh list [--fav]` / `fav` / `move up\|down\|top` / `del` / `index` / `stock` |
| 交叉混合 | `lut.sh mix <A> <B> <0-100>` |
| 单表强度 | `lut.sh strength <名> <0-100>`（0 端 = 原厂 A17，先跑一次 `lut.sh stock` 导出来） |
| 双表各自强度 | `lut.sh blend <A> <r 0-100> <B> <s 0-100>` —— `r` 是 A/B 比例，`s` 是总强度 |
| 录像 LUT | 不用单独开：`apply` 成功自动启动、`off` 自动停。诊断用 `lut.sh video on\|off\|status`（`on` 带秒数可限时） |

顺序与收藏落在 SD 卡 `looks/../lut/state/order`，一行一条、`*` 前缀表示收藏。
下架是**移到 `looks/_trash/`**，不是删除（exFAT 上删同名文件会释放簇链，见现场纪律）。

#### 库定档与旧表清理

随包的 86 张是**定档集**（2026-11-11 按机上实选定档），清单在 `looks/MANIFEST.txt`（md5 + 字节数）。旧批次的 80 个名字列在
`looks/obsolete.txt` —— 因为解压是"覆盖不删除"，不清的话它们会一直赖在卡上，面板里新旧混在一起。

```sh
sh /opt/usr/nx-ks/lut.sh verify          # 对照清单：MISSING / CHANGED / EXTRA
sh /opt/usr/nx-ks/lut.sh prune --dry-run # 先看会动哪些
sh /opt/usr/nx-ks/lut.sh prune           # 把旧批次移到 looks/_trash/（移动，不删）
```

`verify` 的 `EXTRA` 不一定是错：你自己加的 look 也会算 extra。`prune` 只动 `obsolete.txt`
里列出的名字，其它文件一概不碰；误清的东西在 `looks/_trash/` 里可以拿回来。
改库（增删改任何一张表）之后必须重跑 `python tools/lutgen/make_manifest.py` 并提交，
否则下一台机器上 `verify` 会报 `CHANGED` —— 这是有意的：库的变更必须是显式动作。

面板里就是「两个强度各自一根」：左右键切 A/B 焦点，滑杆和右上拨盘调当前那个，
底部状态行同时显示两个强度与换算后的比例/总强度。

双表强度的语义是**归一加权**：`r = B/(A+B)` 定比例，`s = min(A+B, 100)` 定总强度，
最终 `T = 原厂 + s·(mix(A,B,r) − 原厂)`。所以两个都推满时得到两张表的折中，不会溢出成死黑死白。
实测对比见 [`docs/current/DUAL_STRENGTH_2026-11-02.md`](docs/current/DUAL_STRENGTH_2026-11-02.md)。

### LUT 面板按键（NX500 实体键，全部实测）

| 键 | 浏览态 | 编辑态 | 混合态 |
| --- | --- | --- | --- |
| 上 / 下 · EV 拨盘 | 翻页 | — | 翻页（换条目） |
| 左 / 右 | 翻页 | — | 选 A / B 焦点 |
| 中央 OK | 应用并关闭 | 完成 | 应用混合 |
| 播放 ▶ | 进编辑态 | — | — |
| 长按列表项 | 进编辑态 | — | — |
| Fn | 进混合态 | — | 退出混合 |
| 右上拨盘 | 翻页 | — | 调当前焦点强度（5%/格） |
| BACK · MENU | 关闭 | 关闭 | 关闭 |

> 三态里**唯一会改库内容**的是编辑态（删除 / 排序）。混合态的 A/B 用按钮行设
> （`设为A` / `设为B` / `应用混合` / `退出`），退出**不会**自动应用。
> 键位可以覆盖：`$NXUI_STATE_DIR/keys.conf` 一行 `<keysym> <action>`，`none` 表示解绑。

```sh
sh /opt/usr/nx-ks/lut.sh list | begin | apply <名> | off | status   # 滤镜库 /mnt/mmc/looks/
sh /opt/usr/nx-ks/lut.sh video on|off|status                       # 录像监视，通常不用手动调
```

细节：[`docs/current/LUT_RETARGET_LIVE_2026-10-18.md`](docs/current/LUT_RETARGET_LIVE_2026-10-18.md)　面板设计：[`docs/current/LUT_UI_2026-10-18.md`](docs/current/LUT_UI_2026-10-18.md)

## TC 曲线（录像 tone 曲线）

p7 录像链路里有一张 **19 节点 tone 曲线表**，作用在 3DLUT 之前。它不是 `MOVIE_GAMMA_CONTROL`
（那个接口在 NX500 1.12 上没有消费者），是数据表本身：写 19 个 Y → 置 dirty → ISP **<50 ms 内自行消费**，
不需要按键。

| 项 | 现状 |
| --- | --- |
| 表 | 19 节点，X 固定 `0–16383`，Y `0–1023`，首 0 尾 1023、严格递增 |
| 地址链 | `Param0 = read32(0x817dccbc)` → `Gamma = read32(Param0+0x170)` → `Y[i] = Gamma+0xe8c+4i`；**每次重新解析 + 签名校验**，堆地址随 boot 变，不能硬编码 |
| 入口 | 菜单 `实用功能 → TC 曲线`（原厂 / Log / Flat / 高对比），或 `tc.sh set log\|flat\|hc` |
| 生效 | 进入 HEVC 码流：同段 A/B 录像全画面 Y mean **63.26 → 98.83**，像素映射 4→17 / 52→102 / 180→186 |
| 回退 | `tc.sh off` 回原厂；重启也自动回原厂（改的是运行态内存，不写固件） |

```sh
sh /opt/usr/nx-ks/tc.sh status             # 是否原厂、Y[9]、描述符
sh /opt/usr/nx-ks/tc.sh list               # /mnt/mmc/tc/*.tcy
sh /opt/usr/nx-ks/tc.sh set log|flat|hc    # 或指向任意 .tcy
sh /opt/usr/nx-ks/tc.sh off
```

诚实边界：

- **曲线可编程 ≠ 动态范围增加**。容器仍是 8bit 4:2:0，没有 10bit 地基；Y mean 抬升是曲线形状，不是曝光漂移，也不是 DR 净增益（严格门槛后区间含零）。
- 锚点是「中灰锚定」（相机 128 ↔ sRGB 128）；换白点锚定整体差约 35 码，要 18% 灰卡才能定。
- **TC 会移动 3DLUT 的输入域**，两者同时改需重新标定。
- 只在空闲预览模式下写入（目录锁 + 录像检测 + 逐项回读，失败自动写回原厂）；**录像中切换的稳定性、照片路径是否受影响，都未验证**。

细节：[`docs/current/TC_CURVE_ONDEVICE_2026-11-08.md`](docs/current/TC_CURVE_ONDEVICE_2026-11-08.md)　还原工作流：[`docs/current/TC_RESTORATION_WORKFLOW_2026-11-08.md`](docs/current/TC_RESTORATION_WORKFLOW_2026-11-08.md)

## A2 p7 补丁（可选）

「全七维 PW 一键直推」的固件前提。没刷也不会坏，只是 R/G/B/HUE 要靠机身「画面向导」确认一次。

| 项 | 值 |
|---|---|
| 镜像 | `patch-a2/p7_a2.bin`（随发布包，12,075,648 B，md5 `712c6fd0a49371ec05ce94c367b0d5c7`） |
| 目标分区 | `/dev/mmcblk0p7`（约 30 MB，**写错分区不可逆**） |
| 通道 A | 解压包 → 相机 `dd` 写入 p7（约 1 s） |
| 通道 B | Release 附件 `slp_a2_p7_v117.bin`（352 MB）改名 `nx500.bin` 走官方刷机链 |
| 生效 | **正常关机 → 开机**；⛔ 不要 `systemctl restart di-camera-app` |
| 回退 | 写入前的 `p7_backup_*.bin` 写回，或重刷官方 1.12 |

完整步骤（ssh 口径、备份、回读判据、分段比对、回退）见
[`fw/v1.12/a2/README-A2.md`](fw/v1.12/a2/README-A2.md)（[EN](fw/v1.12/a2/README-A2_EN.md)）。
官方固件升级会重写 p7 ⇒ **升级后要重刷 A2**。

## 目录结构

| 路径 | 说明 |
| --- | --- |
| `install.sh` `info.tg` `nx_cs.adj` | SD 卡根触发三件套（装机 / 增量同步） |
| `scripts/` | 全部模块母本 → 同步到相机 `/opt/usr/nx-ks/` |
| `scripts/filmlab.sh` · `scripts/filmlab/recipes.json` | FilmLab 引擎 / 权威配方库（79 条） |
| `scripts/EV_AEL.sh` · `scripts/EV_MOBILE.sh` · `scripts/EV_EV.sh` | 三个组合键入口（滤镜条 / LUT 面板 / 主菜单） |
| `scripts/nxui.sh` · `scripts/nxui/` | NXUI 启动器 + 面板二进制（`nxui.arm` 中文 / `nxui_en.arm` 英文）+ 字体 + `lang` |
| `scripts/lut.sh` · `scripts/lut/` | 3D LUT 入口 + 工具集（`cube2lut` / `nx_slotwrite` / `nx_regtabwrite` / `nx_regtabdump` / `nx_lutload` / `nx_lutptr` / `lutmix`） |
| `scripts/lut_video.sh` | 录像 LUT 监视器（随 `apply`/`off` 联动，锁与状态都在 `/tmp`） |
| `scripts/tc.sh` · `scripts/tc/*.tcy` | TC 曲线写入与曲线库（原厂 / Log / Flat / 高对比） |
| `scripts/ssh_hint.sh` · `scripts/dropbear/` | SSH 状态提示与 dropbear 本体 |
| `scripts/pwrlog.sh` | 关机取证采样（30 s 一条到 SD） |
| `scripts/gui_*.NX500` | 原生菜单页（`i18n/en/scripts/` 是英文覆盖层） |
| `tools/tcgen/` · `tools/lutgen/` | PC 端工具：曲线生成 / 只读验链 / LUT 生成与体检 |
| `test_server/` | PC 端开发验证环境（模拟 API、工具链、面板源码与 `make_en.py`） |
| `uninstall_pkg/` | 相机菜单卸载入口 |

## 文档

- [`docs/README.md`](docs/README.md) — **文档总索引**（`current` 现行 / `archive` 历史 / `evidence` 证据）
- [`docs/current/HANDOVER_2026-10-16.md`](docs/current/HANDOVER_2026-10-16.md) — 总入口：约定、死路、门控、执行序
- [`docs/current/NXUI_ENABLE_GATE_2026-11-10.md`](docs/current/NXUI_ENABLE_GATE_2026-11-10.md) — 「UI 出不来」的门禁根因与 diag
- [`docs/current/TC_CURVE_ONDEVICE_2026-11-08.md`](docs/current/TC_CURVE_ONDEVICE_2026-11-08.md) — TC 曲线：地址链、写入协议、实机 A/B
- [`docs/current/VIDEO_LUT_FIRSTFRAME_2026-11-07.md`](docs/current/VIDEO_LUT_FIRSTFRAME_2026-11-07.md) — 录像首帧带表：p7 档位指针表
- [`fw/v1.12/a2/README-A2.md`](fw/v1.12/a2/README-A2.md) — A2 p7 补丁刷入教程
- [`docs/current/RE_PROGRESS_2026-10-08.md`](docs/current/RE_PROGRESS_2026-10-08.md) — 逆向进度总览（含死路清单）

> 历史文档里的旧结论（如"View/Still 不可分离""用户态不能写 LUT"）已被推翻，纠错见
> [`ERROR_CORRECTIONS_2026-10-07.md`](docs/current/ERROR_CORRECTIONS_2026-10-07.md)。

## 界限

写清楚比写得好看重要。下表每一条都对应实机或静态验证，没有"应该可以"。

| 维度 | ✅ 能 | ❌ 不能 / 未验 |
|---|---|---|
| 平台 | NX500 固件 **1.12**（全部功能实机验证） | NX1 1.41 可装，但 LUT / FilmLab / NXUI 未在 NX1 上启用；其它固件版本拒绝安装 |
| 色彩 | **sRGB** 输出下取景与 JPEG 成片颜色可信（86 张随包表的基准，其中 34 张按实测输入域生成） | **AdobeRGB 会生效但颜色未标定**；相机智能滤镜（枚举 14–18）走另一条动态 24 档路径，不覆盖 |
| 载体 | **JPEG 成片 + 取景器 + 录像（首帧即带表）** | **RAW（`.SRW`）不承诺被 LUT 烘焙**；地基只有 8bit 4:2:0（10bit 不可达，内置 gamma 接口无消费者）；录像已实测 4 分钟长录，多帧率组合未覆盖 |
| 录像曲线 | **TC 曲线四条预设，写表后 <50 ms 生效并进入 HEVC** | 只重分配 256 级码值，不产生动态范围；绝对锚点待灰卡定；录像中切换、与 3DLUT 叠加、照片路径影响均未验证 |
| 生效 | LUT 写内存后**自动装载**（等取景帧结束，无需按键）；TC 曲线写表后 **<50 ms 自行生效** | **开机即生效做不到** —— 断电/重启回原厂，要持久化得改固件镜像 |
| 触发 | `nx_lutload.arm once` 复刻 p7 的 Load 写序，用 `CORE RSZ_OUT1_EOF` 帧事件对齐 | 息屏或 `di-camera-app` 不在时 ISP 不取景，DMA 完成中断不会来 —— 此时退回「半按一次」 |
| 形态 | 不刷机、不改分区，可双向回滚（A2 是唯一可选的 p7 写入） | 不改固件分区 ⇒ 重启即回原厂（LUT 写入是内存操作） |

> 它**不是**完整色彩管理（不做输入/输出 profile 转换），**不是**所见即所得承诺（取景与成片处理链不同），
> **不是**破解（不解除区域锁、不改录制时限）。改的只是 ISP 里的两张表：末端 3D 查找表 + 录像 tone 曲线。

## 硬限制（p7 / 固件层面，不是脚本 bug）

- **全七维 PW 一键需 A2 固件**；官方固件下归一化器域外的值会被拒收。
- **p7 无 UI**（Font/DrawText/Dialog/Widget 全 0 命中）⇒ 界面只能在 Linux 侧改。
- **三键以上组合不可得**（内核先消费按键）⇒ 能用的只有「按住 EV + 单键」这一类两键组合；长按由 NXUI 按 press/release 时长自己判定，不是硬件事件。
- **TC 曲线只改形状，不改位深**：8bit 4:2:0 里重映射 256 级码值不产生新的动态范围；`MOVIE_GAMMA_CONTROL` / `IQ[180]` 那条接口没有消费者，10bit 编码在固件里不存在。
- 出厂 LUT 表**全是风格表**，不能拿"写 identity 得中性"当判据。

> 胶片仿真引擎与 `.cube` 素材另见 [nx500-filmsim](https://github.com/WApaperplane/nx500-filmsim)（public）。
