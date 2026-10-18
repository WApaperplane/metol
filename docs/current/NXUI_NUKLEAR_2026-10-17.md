# NXUI / Nuklear 替代菜单与滤镜预览（2026-10-17）

> 2026-10-18 修复：面板关闭时未归还 X 输入焦点，导致相机原生菜单方向键"有时候"失灵。
> 见 `NXUI_FOCUS_HANDOFF_2026-10-18.md`（根因、判别、回归测试）。

已在用户的 NX500 1.12（192.168.0.106）安装并启用独立的 Nuklear 菜单。
替换范围为 NX-KS / FilmLab 菜单，三星原生拍摄应用继续负责取景。
此前全屏自绘失败不能直接推导为所有框架、面积和事件循环都不可行；
本次以小面积、事件驱动界面和真实机身观察重新检验。

## 已完成与证据

- 用户确认初始取景、按键正常；G0=PASS，G1=MANUAL，脚本体检 0 fail / 0 warn。
- 只读演示：720×192 底部滤镜条，95 条配方，10,039ms 内重绘2次，UI_RC=0。
  用户确认面板可见、取景和按键正常。
- 实际预览：用户点选 Portra 400、Portra 800、UltraMax 400、Fuji 400H；
  日志4次 BACKEND ok=1，A2八条消息逐条 rc=0，均为 `not-saved`。
  用户明确确认“色彩变化，切换和关闭正常”；21,108ms 后正常退出。
- 正式安装：payload 11项 MD5 全部通过；安装器检查当前脚本与原始基线一致后
  备份并切换。试用程序 MD5 `92d56b55bb8dfb51fcbdc0f47073b12d`；
  最终版补充同配方显式重应用/旧菜单操作后状态同步，MD5 `faa861ae262425c400cde0c76749e8a9`。
- 正式入口：`menu.sh → nxui.sh menu → nxui.arm`；日志7项主菜单、
  720×336、95配方；运行后负载约1.09，与基线约1.04同量级。
  用户明确确认“主菜单、子菜单和滤镜切换均正常”。
  这不是长期负载或拍摄压力测试结论。

试用日志与原始脚本备份在相机 SD：`/mnt/mmc/stage/nxui-poc-92d56b55/`。
安装时原版备份：`/opt/usr/nx-ks/nxui/backup-20261017/`。
仓库证据见 `raw8/gates/nxui/`，离线渲染见 `raw8/repro/nxui_nuklear_*.png`。

## 实现

Nuklear（MIT）负责布局，X11/Xft 使用相机现有窗口和字体库，不链接 EFL。
界面不抓取、不重绘实时取景帧；保留相机自身的取景输出。
滤镜条保持打开，切换后调用现有 FilmLab/A2 后端。
250ms 合并选择，最多一个应用进程，后来的请求仅保留最后一个。
新增 `preview` 不保存闪存，`commit` 在后端成功后保存一次。
普通关闭保留当前预览，不承诺恢复原值。

旧 `button` / `checkbox` / 子菜单文件继续使用，控制脚本沿用；专用工具自身
弹窗并未重写。标准方向键已接入，机身滚轮映射尚未验。
目前预览选择器是 PW 配方，不含 LUT 缩略图或 LUT 选择器。
本次没有刷写固件或修改三星原生应用。

## 验证与交付

源码与可复现构建：`test_server/nxui/README.md`。
ARM 通过相机 glibc 2.13运行与中文渲染验证；模型测试和13项引擎测试通过。
隔离 X11 真输入测试覆盖请求合并、串行处理、保存、失败、复选开关和子菜单。
额外修复 XCopyArea NoExpose 回执导致的自触发重绘，以及触屏没有 MotionNotify
时点击坐标未更新的问题。

更新包：`E:/NXWA/release/NXUI-Nuklear-20261017.zip`，只含菜单程序、入口、引擎、
许可、校验与安装/回退脚本。

```sh
sh /opt/usr/nx-ks/nxui.sh disable  # 暂时恢复旧菜单入口
sh /opt/usr/nx-ks/nxui.sh enable
sh /opt/usr/nx-ks/nxui/rollback.sh # 恢复原始六份脚本（含 EV_EV.sh / telnet_toggle.sh）
```

回退不改变当前配方。试用前slot9为114/102/80、H13/S7/锐8/对比11，
原选中PW_CUSTOM1；完整13槽读取在试用目录 `slot9-before.txt`（旧dump命令实际输出全部槽）。

## 同日后续：取消自定义1固定绑定

按用户要求，范围包括9个内置档位与自定义2/3，切滤镜后保持当前栏位。
`apply`、`preview`、`commit` 未明确给 slot 时，现从 `getusr 20` 解析当前栏位；
`0x14000c` 对应可见自定义3 / prefman slot11，`0x14000b` 空洞拒绝处理。
目标读取失败时拒绝写入，不退回自定义1。

A2 的提交仍会短暂选择自定义1；脚本在发送后恢复所需栏位并核对读回。
本次未更换固件。每个目标栏位首次写入前保存原始参数到 SD `filmlab/slot-backups/`。
预览不执行 `prefman save`；点击保存时才保存当前栏位。

实机自动验证：标准/Portra400、自定义2/TriX400、自定义3/Velvia50，
每组目标栏位保持，七项 ISP 读回逐项匹配 A2 编码（共21项）。
自动验证结束恢复测试过的 prefman 栏位原值与测试前自定义1选择。
离线13项引擎测试通过，含12个栏位映射、备份、失败恢复与保存顺序。
证据见 `raw8/gates/nxui/current-field/`。

## 同日后续：降低界面操作负载

用户已确认滤镜效果通过，但反馈疑似 UI 负载造成机身卡顿。不能仅凭网络超时
断言卡死：恢复连接后无 UI 进程，且上次90s会话只绘制1次，没有后端调用。

优化措施：取消无用途的移动事件/悬停刷新；排版绘制上限10Hz；暴露事件直接
复制现有 pixmap，避免重新排版、绘字和同步查询窗口属性；无待办时阻塞等待，
仅在后端运行时100ms检查一次；进程绝对 nice 19，避免快捷键 nice -15 与启动器
相对 nice +15 抵消。保留250ms选择合并和串行应用。

宿主及相机 ABI 的隔离 X11 回归通过：5ms短点击不丢失；500个移动事件只绘制
初始1帧；500个暴露事件只做缓存复制；500次方向键绘制频率在10Hz以内；
2.4s空闲只有1次 select 唤醒，预览、保存、开关与子菜单仍正常。

真机以相同 nice 19 比较新旧版，10s均只绘制1帧。取中间约6.16s采样，
旧 UI 61次自愿上下文切换，新 UI 0次；RSS 3632KB → 3628KB。
两者 CPU ticks 均未增加，Xorg 同期也未增加，不能据此声称 CPU 下降某个百分比。
相机原生进程同期约69%–72% CPU。证据见 `raw8/gates/nxui/performance/`。

用户随后明确卡顿主要是快捷键后菜单出现慢；复核发现人工唤起仍进入已安装旧版，
临时试用并未接管快捷键。正式升级已把 `EV_EV.sh` 纳入安装/哈希保护/备份/回退：
EV+EV 直接进入新版；取消主菜单启动时运行 `br_menu.sh`，码率/延时子菜单按需
生成并剔除临时菜单文件不需要的全局 `sync`；导出配方表按 JSON 内容校验缓存。
新增真实入口缓存/更新测试、动态子菜单按需生成与不执行全局 sync 的测试，均通过。

正式安装校验12项全部通过；已装 ARM MD5 `329a67fe1ab32b835f19f1a705b552a1`，
引擎 `408cfcfa1937b121f22f2cc78c288a8e`，启动器 `aff030b9c2eeab491e084f2b481e76a8`。
真实入口脚本测量到首帧：首次主菜单603ms；复用配方表后主菜单367/364ms，
滤镜条290/270ms。这不包含机身键识别前的等待时间；首次上屏有一次 XSync
用于确认服务器已处理绘制请求。
完整升级包括取消自定义1固定绑定的引擎，初始备份目录保留并补入原 EV_EV.sh。

最终人工复验：用户明确反馈“重启之前仍然极其卡顿，但在重启之后打开明显加快，
操作正常”。因此本次界面启动与操作验收为重启后通过；重启前严重卡顿的根因尚未
确认，不能把恢复完全归因于某一项界面优化，也不能据此声称长期稳定性已验证。
本次重启由用户操作，安装器没有自动重启相机。

## 同日后续：配方与服务操作响应、状态即时刷新

用户要求优化发送配方和开启 Telnet/FTP 的响应，并指出开启服务后需重开菜单
才能确认状态。新 UI 不再把菜单文件里的旧标签当服务状态：读取 IPv4/IPv6 TCP
监听表，独立显示 Telnet 与 FTP；操作完成后立即刷新当前页，外部变化在约1s内
反映，仅可见服务页启用这个只读检查，状态不变不重绘。无法读状态显示问号。

服务 UI 路径使用 `telnet_toggle.sh --ui enable|disable`，不等待旧弹窗倒计时，
后台服务的标准输入/输出重定向以免持有 UI 管道。先操作、再核对真实监听状态；
失败或部分成功照实显示。实机还发现旧 `killall tcpsvd` 漏掉进程名为 busybox 的
FTP 实例，现精确匹配 BusyBox 路径 + tcpsvd + 0.0.0.0:21，未对其它 tcpsvd 操作。

配方合并等待250ms → 150ms；选择、排队、发送、确认和完成显示对应配方。
管道/SIGCHLD 唤醒主循环，减少等待轮询的响应延迟。恢复当前栏位先立即读回，
只有尚未达到目标才每50ms重查，最多20次；保留失败拒绝、12个栏位映射、备份
及成功后才保存的保护。A2发送仍为150ms间隔和300ms收尾，本次未刷固件。

离线：15项引擎、4项服务开关、5项安装器与启动缓存测试通过；宿主及相机 ABI
真实 X11 输入覆盖同页开关、外部状态变化、部分失败重试和保留页码，旧交互与
10Hz绘制上限回归通过。真机：标准栏位 Portra400 5.39s → 4.35s；TriX400
5.33s → 4.36s，四组七项 ISP 读回均精确匹配，原始参数恢复。
同一服务页面完成关闭266ms、开启200ms，两服务状态1/1 → 0/0 → 1/1，
未重新打开菜单；服务测试另设独立恢复步骤。证据见 `raw8/gates/nxui/responsiveness/`。

响应优化已正式安装，13项 payload 校验通过，六份原始脚本备份保留。安装后用户
用原快捷键完成服务关/开及配方发送，并明确确认“状态即时刷新，响应和取景正常”。
最终 ARM MD5 `874553e0d6dc588267f85b2e603bf3c4`，引擎
`dc745c306f74bf4603b0ba275ad7f5d5`，服务脚本 `4d245109e8a6c5ab47240a23c2f4458d`。

## 同日 18:00–18:30：预览慢的根因（实测）与 3× 提速

用户实测反馈"因为要等待预览，速度反而变慢了"。相机在线（192.168.0.106）分段计时后
定性：**瓶颈不是渲染，是 `st cap capdtm` 每次 ~1.3s**。

### 实测（loadavg 2.44，`raw8/gates/nxui/responsiveness/timing_probe*.sh`）

| 项 | 耗时 |
|---|---|
| `st cap capdtm getusr 20` | 1.31 s |
| `st cap capdtm setusr 20 0x140000` | 1.23 s |
| 再次 `getusr 20`（读回自证） | 1.30 s |
| `prefman get` ×7 | 0.17 s（24 ms/次） |
| `pwsend.arm seq` 启动 | 0.45 s |
| `/bin/true` ×20 | 0.27 s（13.5 ms/fork） |

`prefman` 与 fork 都很便宜，唯 `st` 通道是秒级（命令走 App 队列 key 0x8828，取景占
36% CPU 时轮询一轮 1.3s）。

### 根因

`preview` → `apply UI_REQUEST=1`：无 slot 时按 `FILMLAB_ENUM_CACHE` 解析当前栏位 →
目标 ≠ `0x140009` ⇒ `pw_force_reload` 三连 st（读档位 1.3 + 切档 1.2 + 读回 1.3）→
`pwsend` 固定 7×150 ms + 300 ms = 1.35 s → 7×`prefman set` 写槽 + 7×`get` 备份（≈0.4 s，
预览完全用不到）。合计 4.3–5.9 s，与既有 `results.json` 的 4.35 s 吻合。

**回归点**：同日早先的"preview 跟随当前 PW 栏位、发送后恢复原档位"改动。改之前 apply
固定写 slot 9，preview 走 `TARGET==0x140009` 快路径 = 0 次 st；改之后只要相机停在
STANDARD（默认拍摄档）每次滚动都付三次 st。

**附带缺陷（已修）**：预览在 STANDARD 档会把配方 7 维写进 slot 0（标准风格）且不恢复，
切回"标准"看到的是最后一次预览 —— 预览是临时态，不该污染真实风格。

### 改动（`scripts/filmlab.sh`）

1. `preview`/`commit` 固定以 CUSTOM1（slot 9）为画布：A2 提交位 0x13B 本来就把运行时
   档位切到 field 10，固定槽后全程 0 次 st cap。
2. `preview` 不写槽、不做 slot 备份（画面完全由 A2 直推决定）；`commit` 才写槽 + save。
3. `preview` 跳过档位通道（不发 `NXUI_STAGE restore`，`RELOAD=already`）。
4. `commit` 才把档位还回打开面板时那一档（`TARGET_PW` 取 `FILMLAB_ENUM_CACHE`）。
5. `pw_force_reload <目标> [已知当前值]`：A2 发送成功后调用方传 `0x140009`，省一次
   getusr（commit 的 3 次 st → 2 次）。
6. `pw_direct` 支持 `FILMLAB_PWSLEEP`：浏览预览用 40 ms（原 150 ms），批量写槽仍 150。

### 验证

- **离线桩测试**（`E:/tmp/filmlab_stub_test.sh`，非入库）：preview = 0 set / 0 get /
  0 save / 0 st / 1 pwsend；commit = 7 set / 7 get / 1 save / pwsend /（目标为 CUSTOM1
  时 0 st，带 STANDARD 缓存时 2 st）。
- **真机**：preview 4.35 s → **1.43 s / 1.44 s**（两次连续，均 `reload=already
  pw=direct not-saved`）；从 STANDARD 档起步同样 1.4 s。预览后运行时档位停在
  `PW_CUSTOM1`（新语义），手动 `setusr 20 0x140000` 可回标准。
- 部署：`/opt/usr/nx-ks/filmlab.sh` md5 **`021a7aff98d724f1eaf6309c04ffcd62`**；
  原文件备份 `filmlab.sh.bak-1017b`（`4ecddd03`）；相机端 `sh -n` 通过。

### 遗留

- 预览后关闭面板（不 commit）运行时档位停在"自定义1"，槽数据未变 ⇒ 切走再切回即回旧值。
  若要"退出面板自动还档"，需在 nxui 退出路径加一次 setusr（约 1.2 s，退出时付一次）。
- `pwsend` 收尾固定 300 ms 未动（需重编 ABI 二进制）；再压可到 ~1.2 s。

### 同日 18:30–18:40：pwsend 收尾 usleep 300ms → 100ms

`pwsend.arm` 两处 `usleep(300000)`（单发 / seq 末尾）压到 100 ms。因本机无 zig 0.13.0，
以**二进制常量补丁**落地（两处 `.word 0x493e0` → `0x186a0`，vaddr 0x26264 / 0x26808
→ 文件偏移 0x6264 / 0x6808，PT_LOAD#2 `vaddr = offset + 0x20000`；diff 仅 6 字节）；
源码 `test_server/pwsend/pwsend.c` 同步改为 100000。

真机验收（连续三次不同配方）：

| 配方 | 耗时 | 七维读回 |
|---|---|---|
| portra400 | 1.32 s | R 0x0890 / G 0x07F0 / B 0x0760、HUE 0x001F、SAT 0xFFCF、SHARP 0xFFFF、CON 0xFFEF |
| trix400 | 1.29 s | R 0x0880 / G 0x07F0 / B 0x0790、HUE 0x000F、SAT 0xFF6F、SHARP 0x002F、CON 0x002F |
| portra800 | 1.27 s | 全部命中 |

⇒ 收尾缩短**不影响送达**；累计预览 4.35 s → 1.27~1.32 s（3.4×）。
部署 md5：`filmlab.sh 021a7aff` / `pwsend.arm 935fead9`；备份 `*.bak-1017b` / `*.bak-1017c`。
`pwsend.arm` 首次纳入 `scripts/`（install.sh 的 `cp -ar scripts/*` + 全局 chmod 兜底）⇒
全新安装也能直接预览，不必再手工 deploy。
