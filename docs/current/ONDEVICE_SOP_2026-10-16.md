# 上机日 SOP（2026-10-16 版）

> ⚠️ **2026-10-18 文档清理：本文结论已被取代。** §10 的 LUT 上机九步按 `lutpick.sh` + `lutsentinel` 写，**已不适用**；现用 `lut.sh apply` + 半按快门。其余上机纪律仍有效。
> 现行结论见 [`LUT_UI_2026-10-18.md`](LUT_UI_2026-10-18.md)。


> **定位**：把当前全部「待上机项」串成**单份可执行清单**——上机日只读此一份 + 门控脚本，不必翻 7 份文档。
> **输入**：`T2_DELIVERY_REVISION_2026-10-15.md §6`（P5 流程）、`UI_R2R3_DESIGN_2026-10-15.md §4`（R2b 判据）、`M2_RECIPE_NAME_DESIGN_2026-10-16.md §6`（M2 流程）、`A2_READBACK_VERDICT_2026-10-15.md`（回读判据）、`TASKFLOW_2026-10-12.md W-3/W-4`（含 10-15 修订）。
> **相机**：`192.168.0.106` · telnet 23（root/空密）· FTP 21（根 = `/mnt/mmc` = SD）· 工作区 `/opt/usr/nx-ks/`
> **口径**：✅=已证｜🔶=设计｜❓=未决

---

## 0. 开场（每次进门必做）

| # | 动作 | 命令 / 判据 |
|---|---|---|
| 0.1 | **重跑门控**（勿信旧口径） | `cd <克隆> && python test_server/tools/gate_flow.py --json`（跑完更新 `raw8/gates/gate_status.json`；门控须在**小A克隆**跑，Codex 克隆缺 `.uploads/emmcbak` 会假阴性） |
| 0.2 | 探活 | `python tools/nx-telnet.py -c "date"` 通 = 在线。**23 Timeout ≠ 砖**（开机 3 min 内 23 可能未起齐，21 先通；刷后另有 ~4 min Refused 窗口） |
| 0.3 | 负载基线（G1-3） | `python tools/nx-telnet.py -c "uptime; cat /proc/loadavg; free"` → 记录 |
| 0.4 | 证据纪律 | 一经话一条命令 + 结果落盘走 FTP（**不信回显**）：`python tools/nx-probe.py -c "<cmd>"`；抓文件用 `python tools/nx-fetch.py <remote> <local>` |
| 0.5 | 铁律 | ⛔ **禁 `systemctl restart di-camera-app`**（实测卡死整机）；拔卡前安全弹出；`st app` 参数单个 ≤19 字符 |

---

## 1. 批次总览

| 趟 | 批次 | 内容 | 开关机 | 前置 |
|---|---|---|---|---|
| **1** | **U1+U2+U5 合并**（推荐） | P5 部署（C-2 + M2 就位）→ 开关机 → 挂载验证 + `st app film` 首验 + 菜单配方名观察 | 1 次 | §2 就位 |
| 2 | U3（R2b 样本） | 换补丁体为 R2b 样本（或合成体）→ 开关机 → OSD 观察 | 1 次 | U2 完成 |
| 随时 | U4（A2 健康） | 二次回读（只读）+ 多配方体验（日常） | 0 | — |
| 随时 | U6（槽语义） | 只读观察（三自定义槽独立性） | 0 | — |
| 随时 | **U7（LUT 批）** | R-B 终验：identity/Portra 表 → 取景器 + **Still 成片判据** + `lutsentinel` 守护实测 | 0 | SD 部署 `filmlab/`（工具 + 表包）；见 §10 |

> 分步备选：若想最大化变量隔离，趟 1 拆两趟——① P5 + **官件自绑**（把官方件拷为 `di-camera-app.c2`，挂载内容与原件同字节 = 零变化灰度）→ 验证机制；② 换 C-2 → 验证桥。代价 = 多一次开关机（~5 min）。

## 2. 就位清单（PC → 相机，趟 1 前置）

### 2.1 FTP 上传（根 = `/mnt/mmc`）

| 本地 | SD 落点 |
|---|---|
| `scripts/dicam/*.sh`（全部 7 个：P5 三件套 + m2_locale + status + patch_install/rollback 备选） | `/mnt/mmc/stage/dicam/` |
| `fw/v1.12/dicam/di-camera-app.c2.v2`（`48d94bd6…`）| `/mnt/mmc/stage/dicam/di-camera-app.c2` |
| `fw/v1.12/dicam/locale/` 全部（`di-camera-app.zh_CN.m2sample.mo` + `MANIFEST.md5`）| `/mnt/mmc/m2-locale/` |

### 2.2 telnet 落位（p14）

```sh
mkdir -p /opt/usr/nx-ks/dicam /opt/usr/nx-ks/locale/zh_CN
cp -f /mnt/mmc/stage/dicam/*.sh /opt/usr/nx-ks/dicam/
cp -f /mnt/mmc/stage/dicam/di-camera-app.c2 /opt/usr/nx-ks/dicam/
chmod +x /opt/usr/nx-ks/dicam/*.sh
md5sum /opt/usr/nx-ks/dicam/di-camera-app.c2     # 期望 48d94bd63e4479fc931ae1a1fee4e94b
sh /opt/usr/nx-ks/dicam/m2_locale.sh deploy      # 期望：双校验 OK + 输出 e531bd5f…
```

### 2.3 dry-run（不等重启，先验脚本）

```sh
sh /opt/usr/nx-ks/dicam/t2_premount.sh           # 手动跑一次
mount | grep -E "di-camera-app|LC_MESSAGES"      # 应见 2 条 bind（App 目标 + locale）
cat /tmp/dicam_p5_mount.log                      # 应见 [T2]、[M2] 两行
umount /usr/apps/com.samsung.di-camera-app/bin/di-camera-app
umount /usr/share/locale/zh_CN/LC_MESSAGES/di-camera-app.mo
mount | grep -E "di-camera-app|LC_MESSAGES"      # 清净（让"开关机后新挂"成为唯一路径，证据更干净）
```
- 预期：dry-run 挂载**不影响正在运行的 App**（已 exec 进程持旧映射）；umount 亦无影响。
- ⛔ 全程不 restart、不 kill App。

---

## 3. U1 —— P5 部署（开关机 1 次）

> ⛔⛔ **10-16 晚实测：本批判据 5-7 全灭 —— P5 的 `ExecStartPre` 在本机正常开机路径上根本不执行。**
> 根因（决定性证据见 `raw8/gates/dicam/u1_p5_failure_2026-10-16.md`）：本机是「内核冷启 + 用户态恢复」休眠机型
> （`/proc/cmdline` 含 `hibernate=nocompress`/`noresume`、`/etc/snapshot`、`hib_exjob`/`hibernation.sh`、p9 当 swap 装镜像、
> 开机早期时钟 = 2016-03-30），**PID 1 的内存状态（含已解析的 unit 表）随之恢复 ⇒ systemd 不重读 unit 文件**。
> 实测：文件正确（`md5 b227c619…`，ctime/mtime 18:07 未被改）、PID 1 视图与 shell 视图一致、`show` 里连条目都没有，
> 但 `systemctl daemon-reload` 后**立刻出现**该行（`start_time=[n/a]`）。同时 App 仍是 **boot+12.2s 被重新 exec**（pid 247 starttime=12.24s）。
> ⇒ **改 unit / 依赖 systemd 每次开机重读配置的投递方式，在本机不成立。** 交付机制需在下列三者中重裁：
> ① 恢复链钩子（`hib_exjob` / 写 `/tmp/.hib_post` 的那一环）｜② **就地落盘**（App 在 p10 可写、M2 的 `.mo` 需替换 p10 上的 `usr_share_locale.squash`）｜③ 刷机式（改 SLP 内 p10 镜像，L4）。
> ⛔ 在机制重裁前，**不要再靠"开关机"验证 §3 序 5-7**。

| 序 | 动作 | 判据/记录 |
|---|---|---|
| 1 | `sh /opt/usr/nx-ks/dicam/dicam_patch_status.sh` | **基线**：无 bind-mount、P5 行 ✗、M2 未挂载（存证） |
| 2 | `sh /opt/usr/nx-ks/dicam/dicam_p5_install.sh` | 注入输出「已注入」/自检 1 命中/`daemon-reload OK`；**无 restart** |
| 3 | `sh /opt/usr/nx-ks/dicam/m2_locale.sh status` | 部署件在位（`e531bd5f…`）、未挂载（基线） |
| 4 | **正常关机 → 开机**（等 21 先通、23 复通；别急判砖） | — |
| 5 | `sh /opt/usr/nx-ks/dicam/dicam_patch_status.sh` | ✓ mount 在位（T2 目标 md5 = `48d94bd6…`）✓ P5 行在位 ✓ M2「已挂载」 |
| 6 | `cat /tmp/dicam_p5_mount.log` | `[T2] mount ok…` + `[M2] mount ok…` 两行（**含 uptime 时间戳 = 挂载早于/先于 App exec 的证据，记录数值**） |
| 7 | 画面检查 | 取景正常出图（App 起得来） |
| 8 | （可选）`cat /proc/<pid>/maps \| grep di-camera-app` 与 `mount` 交叉 | 进程实际加载件 = 挂载件 🔶（未实测项） |

- **失败模式与回退**：App 黑屏 ⇒ telnet 仍在 ⇒ `dicam_p5_rollback.sh` + `m2_locale.sh remove` + 开关机 ⇒ 回官方。unit 注入失败会自恢复（脚本内置备份+自检）。

## 4. U2 —— W-4：`st app film` 命令桥首验（承接 U1，无额外开关机）

链路：`st app film <args>` → 队列 → 桩 v2（净化：`a-z A-Z 0-9 . _ + - /`，其余→`_`）→ `sh /opt/usr/nx-ks/f.sh <args>`（f.sh = mod 分发器）。

| 序 | 动作 | 判据 |
|---|---|---|
| 1 | `st app help` | 回显用法表（App 消息链活） |
| 2 | `st app film help` | **f.sh 用法表回显** + rc=0（= 桥通） |
| 3 | `st app film recipe list` | 配方列表回显（分发链活） |
| 4 | （可选，用户在场）`st app film recipe apply portra400` | 画面变化 + `f.log` 一行（**会实际改画面**，谨慎） |
| 5 | ★ 反证：`st app uscom` | **不再**输出 UserSpec dump（= 改名生效，命令表已换） |
| 6 | 回归：`st app mode m` / `st app mode p` / `st app disp lcd` | 与原行为一致（补丁未伤其它命令） |
| 7 | ⛔ 禁忌复验（可选）：`st app film probe`（f.sh 内调 st app）→ 预期阻塞超时 | **不用做**；纪律记住即可：f.sh 内禁调 st app（死锁实证） |

- 判据落点：`raw8/gates/dicam/c2_film.log`（每步 rc + 输出）。
- **回退**（单批）：换回官方件 ⇒ 删/换 `/opt/usr/nx-ks/dicam/di-camera-app.c2` + 开关机；或 P5 整体回退（§3 失败模式）。

## 5. U5 —— M2 配方名（趟 1 已生效，观察为主）

| 序 | 动作 | 判据 |
|---|---|---|
| 1 | `sh /opt/usr/nx-ks/dicam/m2_locale.sh status` | 「目标 = 部署件（M2 生效中）」 |
| 2 | **菜单观察**：MENU → 相机页 →「图片向导」→ 选项列表 | 原「自定义 1/2/3」→ **Portra 400 / Gold 200 / TriX 400** |
| 3 | 观察记录（4 项）：① 截断/溢出（13 字符 vs 原 3 字）② 字体/拉丁渲染 ③ OSD/SmartPanel 面是否同步 ④ 进/出该菜单正常 | 记入 `raw8/gates/m2/menu_observe.txt`（附照片） |
| 4 | （可选强证据）`st app film` 时代已证 gettext 读新件：切换相机语言再切回（zh_CN）后重现观察 | — |

- **回退**：`sh /opt/usr/nx-ks/dicam/m2_locale.sh remove` + 开关机 ⇒ 恢复「自定义 1/2/3」。

## 6. U3 —— R2b 样本 A/B（开关机 1 次；可与 U2 合成体内合并）

样本依据：`UI_R2R3_DESIGN §2.2`（样本 A 等长 1B / 样本 B 指针 4B；净差 3B；与 C-2 无重叠）。

| 序 | 动作 | 判据 |
|---|---|---|
| 0 | PC 生成样本体（复现命令见 `UI_R2R3` §2.2；默认 A+B 合成；**建议**同时合成 C-2 ⇒ `di-camera-app.c2r2b`） | 字节复验 OK |
| 1 | 上传替换 `/opt/usr/nx-ks/dicam/di-camera-app.c2`（或合成体名）+ 开关机 | 按 §3 序 5 复查 mount |
| 2 | **观察**：切到「画面向导 → 自定义1」值 | OSD/SmartPanel 的 CUSTOM1 图标变化（A：图标名 custom02；B：图标变 smart_filter 图标） |
| 3 | 交互回归：MENU/滚轮/触摸/返回 | 全部正常（本样本不涉 UI 事件） |
| 4 | ≥30s + 两轮负载（`loadavg` 两轮采样） | 无劣化 |
| 5 | **撤销演练**：换回（C-2 或官方）+ 开关机 | 恢复原样 |

- 证据落点：`raw8/gates/dicam/u3_r2b.txt`。

## 7. U4 —— A2 健康（只读/日常，随时）

### 7.1 二次回读（运行期存活证据）

```sh
# 12 MiB 读回 = 镜像 12,075,648 B + 分区尾部 507,264 B 零区
dd if=/dev/mmcblk0p7 bs=1M count=12 2>/dev/null | md5sum
# 期望：69050a17ea9fdbcdab4cf32e7b5ffdb2
```
- 与 10-15 首读结果（`raw8/gates/a2/readback_2026-10-15.json`）比对：**一致 ⇒ 运行期未覆盖**（「两次一致」= 更强证据）。
- 不符或需强证据时：拉回本地精查（`nx-fetch.py`）→ `python tools/a2_readback_check.py <拉回件> --json raw8/gates/a2/readback2_2026-10-16.json`
  （双判据：head 12,075,648B 逐字节 + 尾部零区；**已用 10-15 真机件回归 PASS**）。
- 落点：`raw8/gates/a2/readback2_2026-10-16.json`。

### 7.2 多配方体验（用户日常）

```
sh /opt/usr/nx-ks/filmlab.sh apply portra400   （或 pwpush gold200 …）
```
- 记录：观感（各配方区分度、是否需要微调）；问题清单。

## 8. U6 —— 槽语义只读实验（决定 M2 三槽口径）

**问题**：三个自定义档位是否有**独立存储**？（决定「三槽=三配方」能否成立）
**方法**（纯 UI 观察，零写入风险——只是正常调参）：

| 序 | 动作 | 判据 |
|---|---|---|
| 1 | 「画面向导」→ 选**自定义 2** → 把 R 滑块调到某明显值（如最大）→ 返回取景 | — |
| 2 | 再进「画面向导」→ 选**自定义 1** → 看 R 滑块值 | = **原自定义1值** ⇒ 独立存储 ✅；= 自定义2的值 ⇒ 共享槽 |
| 3 | 反向再验一次（调自定义 1 → 看自定义 2） | 交叉确认 |

- 记录：`raw8/gates/dicam/u6_slots.txt`（含两次读取的滑块值）+ 照片。
- 结论用途：独立存储 ⇒ M2 三槽一致性走「写自定义 2/3 存储」方向（A2 V2：`0x10e/0xdb` 槽探索）；共享 ⇒ 收敛为「槽 1=主推配方」单槽口径。

## 9. 回退汇总

| 影响面 | 回退动作 | 生效时机 |
|---|---|---|
| M2 locale | `m2_locale.sh remove` | 正常开关机 |
| T2 补丁体 | 删除/替换 `dicam/di-camera-app.c2`；或 `dicam_p5_rollback.sh`（全撤） | 正常开关机（当前会话可加 `umount` 立即回路径） |
| P5 unit | `dicam_p5_rollback.sh` | 正常开关机 |
| 固件（A2） | `README-A2.md` 回退段（备份写回 / 官方重刷） | 开关机 |

⛔ 任何回退**禁用 restart**。所有回退在机内完成、不依赖网络。

## 10. U7 —— LUT 批（R-B 终验；设计全文见 `LUT_ROADMAP_RESTART_2026-10-16.md` §4）

> 注：本章引用的「§[n]」= `test_server/u6/runbook.txt`（旧 LUT 波次）的节号，**非本 SOP 的 U6 批**。
> 前置：SD 部署 `filmlab/`（5 工具 + `lutpick.sh` + 表包）；**相机停在菜单界面**（写表需官方 API 安全闸放行）。

| 序 | 动作 | 判据 | 回退 |
|---|---|---|---|
| 1 | `/opt/usr/nx-ks/busybox sh /mnt/mmc/filmlab/lutpick.sh list` | 表目录列出（10 张，10-16 已验证；空 ⇒ 先 `deploy_luts.py push`） | — |
| 2 | `/opt/usr/nx-ks/busybox sh /mnt/mmc/filmlab/lut_backend.sh apply <identity> --dry` | 落点探测 + cmasafe 四查全过（**不写**）；10-16 已通过（落点 `0x8f800000`） | 失败 ⇒ 换时机，**不换地址硬上** |
| 3 | `lutpick.sh apply <identity>`（**sel=1**） | **回归**（E1 已于 10-09 通过）：Cfg 终态 `SelLUT=1`；画面变化。★ **写表需前置「抢回态」**——先对焦/半按一次再写（10-09 §2 规律；非抢回态写入不生效） | `lutpick.sh off` / `lutload.arm restore` |
| 4 | `lutpick.sh apply <Portra 400>` | 取景器出**可分辨、与表语义一致**的风格（新判据；「写 identity→中性」已作废） | 同上 |
| 5 | Still：直拍 1-2 张 → 比对成片 vs 取景器 | **E4 已判负**（直灌不跟随）⇒ 本步为**复核记录**（记 Still 流程 Cfg `0x0→0x1100` 重配置序列），不作为闭环期望 | — |
| 6 | `lutsentinel.arm --sel 1 --count 120`（约 1 分钟，500ms 间隔） | 半按/切档后**画面自动恢复**（日志有恢复行）；无不稳定告警 | `--count 1` 体检模式先试 |
| 7 | 叠加观察：PW 一键（A2）与 LUT 同开 | 记录观感（是否过强/共振） | 二者独立可分别关 |
| 8 | 回退演练：`off` + `restore` + 重启 | 画面回中性、参数回官方 | — |
| 9 | （可选，C2 顺验）`st cap help` / `st cap ref mem` | 记录 `st cap mem` 是否支持**写**（决定 R-C-C2 通道） | 只读探，无风险 |

⛔ 纪律：单会话单命令 + FTP 拉结果 + `setsid`；禁 `systemctl restart di-camera-app`。
⛔ LUT 专属：写表时**不在拍摄态**；看取景器**决不半按**（半按 = p7 抢回，正常现象，不是回滚失败）。
★ **推荐执行方式**（T5 后端，JSON 判据）：`/opt/usr/nx-ks/busybox sh /mnt/mmc/filmlab/lut_backend.sh probe|apply <名>|rollback|status`
—— `rollback` 走 factory_restore（**identity_used:false**，关闭≠identity）；`apply` 前需**先对焦一次**（抢回态）。

★★ **上机实测修正（10-16 晚）**：
1. 相机**无 PATH 上的 `busybox`**（只有 `/opt/usr/nx-ks/busybox`；`/bin/sh` 是 bash）⇒ 一律用绝对路径或直接 `sh`。
2. LUT 工具全在 **SD `/mnt/mmc/filmlab/`**（`/opt/usr/nx-ks/` 无）；后端已按此修正 `lutload` 落点（双端 md5 `c2c04f2d…`）。
3. **长命令（≥10s）勿经 telnet 直跑**：会话超时会把输出截断（只剩首行）⇒ 用 `setsid … > /mnt/mmc/xxx.log 2>&1 &` 后轮询取回。
4. 序 2 干跑已通过，落点 = **`0x8f800000`（区起点）**，而 10-09 成功那次为 `0x8f81e000` ⇒ **写表前先裁决「区起点是否可用」**（见 `raw8/gates/lut/t5_backend_onmachine_2026-10-16.md` §5）。

## 11. 证据落点约定

| 目录 | 内容 |
|---|---|
| `raw8/gates/dicam/` | p5_status_before/after、c2_film.log、u3_r2b.txt、u6_slots.txt |
| `raw8/gates/m2/` | m2_status_before/after、menu_observe.txt、照片 |
| `raw8/gates/a2/` | readback2_2026-10-16.json |
| `raw8/gates/lut/` | U7：identity/Portra 取景器照片、成片 vs 取景器对比、`lutsentinel` 日志、Cfg 读回 |
| 通用 | 命令一律经 `nx-probe.py`/`nx-fetch.py` 落盘取回（G1-4：不信回显） |

---
*生成：2026-10-16 · 全离线编写 · 上机动作全部「待放行」；执行时逐批更新判据结果并回写本表。*
