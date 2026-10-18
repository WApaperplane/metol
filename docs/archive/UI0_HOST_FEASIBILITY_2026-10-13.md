# UI-0：进程内宿主可行性审计（2026-10-13）

> **范围**：审计「在 `di-camera-app` 进程内加载 `libnxwa-host.so`、复用其 Canvas/事件循环」的全部前置条件——
> 注入路径、故障恢复、UI 能力面、最小实验设计。
> **性质**：**只读取证**（WSL rootfs-112 逐项实测 + 既有文档提炼），零写机、零固件修改。
> **上游**：`REA_P7_V5_V6_2026-10-13.md`（Codex 提案：进程内宿主 + 模块运行时 + UI-0…UI-5 路线）。
> **口径**：✅ = 本机实测 ｜ 🔶 = 版本/逻辑推断，待上机裁决 ｜ ❓ = 未知（附探查法）
>
> 🔴 **2026-10-13 晚修订**：§7 八项清单**已上机执行完毕**，结果见 **`CAMERA_ONLINE_PROBE_2026-10-13.md`**。
> 其中 **§2 的「restart 兜底 / 单命令回滚」与 §4 的「启用 `Restart=always` 自愈」已被实测证伪**——
> `systemctl restart di-camera-app` **会卡死整机**（须物理重启）。本文对应段落已就地加警告，**冲突处以新文档为准**。

---

## 0. 结论先行

1. **注入链在静态面上成立**（三条关键前提全部满足）：
   - systemd **208**（rootfs 实测）——drop-in 机制自 v207 引入 ⇒ 支持 `/run/systemd/system/*.d/` 🔶
   - `di-camera-app` **非 setuid**（rwxr-xr-x root，unit 裸 exec 无签名闸门）⇒ LD_PRELOAD 无障碍 ✅
   - App **不链 libdl、不调 dlopen**（113 个 DT_NEEDED 无 libdl；`nm -D` 无 dl* 未定义符号）⇒
     **必须由外部注入**，且这个通道就是唯一通道
2. **硬前置：`Restart=always` 当前被注释（崩了不自愈）**——UI-1 之前必须在同一 drop-in 里恢复
   （注入与自愈一步完成，见 §4）。
3. 全部结论止于"静态成立"：**仓内无任何"往 di-camera-app 注入 .so"的先例**（U2/全部实验都是独立 EFL 进程）。
   ⇒ 裁决必须由 **UI-1a 最小实验**（空 .so + 心跳）完成；在此之前**不得**在 App 进程内做任何 EFL 调用。
   > 🔴 **10-13 晚实测补正**：`.so` 注入确无先例，但**「进程内注入」有先例**——
   > `/opt/usr/nx-ks/auto/a_init.sh` 以 `poker $(pgrep di-camera-app) addr:value…`（9 组）对**运行中**的 App 打内存补丁。
   > ⇒ 「必须早于 exec」这一硬约束**只对 LD_PRELOAD 成立**，对内存补丁通道不成立。详见新文档 §3。

---

## 1. 目标进程档案（本机实测）

| 项 | 值 | 来源 |
|---|---|---|
| 路径 | `/usr/apps/com.samsung.di-camera-app/bin/di-camera-app` | rootfs-112 ✅ |
| 尺寸 | 4,773,516 B | rootfs-112 ✅（与 `test_server/appprobe` 样本一致） |
| 类型 | 32 位 ARM **EXEC（非 PIE）**，interp `/lib/ld-linux.so.3` | CAMERA_APP_STRUCTURE ✅ |
| 权限 | rwxr-xr-x root:root，**非 setuid** | rootfs-112 ✅ |
| DT_NEEDED | **113 个**；无 libdl；含 libtbm/libdrm/libX11/ecore_x | rootfs-112 ✅ |
| RPATH | `/usr/apps/com.samsung.di-camera-app/lib`（目录为空） | rootfs-112 ✅ |
| 符号面（U） | **elm_ 230 / evas_ 73 / edje_ 12**；无 dl* | rootfs-112 ✅ |
| 签名 | Tizen DistributorSignature XML 存在（bin+res 均含摘要） | rootfs-112 ✅ |
| 运行校验 | **unit 裸 exec、无签名校验**（既有先例：`systemctl restart` 可用） | DICAM_MOD_DESIGN ✅ |

**service unit 全文**（rootfs-112 实测）：

```ini
[Unit]
Description=Start di-camera-app
After=hib_ready.service xorg.service default.target wm_ready.service deviced.service

[Service]
ExecStart=/usr/apps/com.samsung.di-camera-app/bin/di-camera-app
StandardOutput=tty
EnvironmentFile=/run/tizen-mobile-env
#Restart=always
#RestartSec=3

[Install]
WantedBy=default.target
```

**环境面**（`/etc/profile.d/*.sh` 实录，经 `tizen-generate-env.service` 汇入 `/run/tizen-mobile-env`）：

| 变量 | 值 | 意义 |
|---|---|---|
| `ELM_PROFILE` | `mobile` | Elementary 主题档 |
| `EVAS_FONT_DPI` | `72` | 字体渲染参数 |
| `EVAS_GL_NO_BLACKLIST=1` | — | 与 U2 复刻一致 ✅ |
| `DISPLAY` / `HOME` | `:0` / `/root` | **Xorg 栈**（非裸 fbdev/wayland） |
| `LD_LIBRARY_PATH` | `…:/usr/lib:/usr/lib/driver` | 与 U2 复刻一致 ✅ |
| `EINA_LOG_DLOG_ENABLE` | `1` | Eina 日志→dlog（**宿主日志可走 dlog**） |

---

## 2. 注入路径分析（5 条候选）
    
| # | 路径 | 生效范围 | 写在哪 | 刷机后 | 评价 |
|---|---|---|---|---|---|
| **P1** | `/run/systemd/system/di-camera-app.service.d/*.conf` drop-in + `daemon-reload` | **仅 di-camera-app** | `/run`（tmpfs） | 免（重启即清、init.sh 重建） | ★ **首选** |
| P2 | drop-in 内加 `EnvironmentFile=-/opt/usr/nx-ks/dicam/nxwa.env` | 仅 di-camera-app | `/run` + p14 | 免 | P1 的变体（环境值与代码分离，便于切换） |
| P3 | `/etc/profile.d/` 加脚本（经 `tizen-generate-env` 进 `/run/tizen-mobile-env`） | **全系统共享者**（xscim/resourced/launchpad…） | rootfs | 重置 | ⚠ 不推荐（污染无关服务） |
| P4 | `/etc/ld.so.preload` | **全系统所有进程** | rootfs（需 remount rw） | 重置 | 仅测试/最后手段 |
| P5 | 改 unit 本体 | 仅 di-camera-app | rootfs | 重置 | drop-in 的劣化版，不采用 |

**P1 落地形态**（由 `init.sh` 幂等维护——它已由 bluetoothd wrapper 每次开机调用）：

```sh
# /opt/usr/nx-ks/init.sh 追加段（示意）
mkdir -p /run/systemd/system/di-camera-app.service.d
cat > /run/systemd/system/di-camera-app.service.d/nxwa.conf <<'EOF'
[Service]
Environment=LD_PRELOAD=/opt/usr/nx-ks/dicam/libnxwa-host.so
Restart=always
RestartSec=3
EOF
systemctl daemon-reload
```

- **时序风险** ✅ **已坐实**（10-13 晚实测）：init.sh 在 **boot+37.8 s**、di-camera-app 在 **boot+12.2 s**
  ⇒ **init.sh 永远晚 25 s**。
  ~~首次注入靠 `systemctl restart di-camera-app` 兜底~~ —— 🔴 **该兜底手段已作废**（restart 会卡死整机）
  ⇒ 注入必须在 App 首次 exec 之前就绪；「boot+12.2 s 之前的执行点」= 新文档 §5 的 **U1**（当前头号阻塞）。
- **回滚**：`rm -rf /run/systemd/system/di-camera-app.service.d && systemctl daemon-reload`，
  **然后走自然重启**（正常关机 / 开机）。
  ~~`… && systemctl restart di-camera-app`~~ —— 🔴 **实测证伪：restart 该 unit 会卡死整机（须物理重启）**，见 §7 执行结果。
- ✅ **原待裁决已结**（10-13 晚）：systemd **208 认** `/run/systemd/system/*.d/*.conf`——
  `systemctl show -p DropInPaths` 成功登记该文件、`Environment=` 被采纳。**drop-in 通道的静态面成立。**

---

## 3. UI 能力与复用面盘点

### 3.1 库与资源（rootfs-112 ✅）

| 资产 | 状态 |
|---|---|
| EFL 1.7.99 全系 | evas / edje / elementary / eina / ecore*（含 ecore_x）/ eet / efreet 均在 `/usr/lib` |
| `libelementary.so.1` | 导出 `elm_init/elm_run/elm_shutdown/elm_win_add/elm_win_fullscreen_set` ✅（宿主可同源调用） |
| 官方 .edj（rootfs 实有） | **4 个**：nx_style.edj (1,087,293 B) / nx_style_hdmi.edj / nx_style_hdmi_720.edj / tizen-hd.edj (1,990,094 B) |
| ★ slp_edc_*.edj（21 个） | **二进制引用存在、文件不在 rootfs**（v1.12 与 v1.13 双版对照，均无）⇒ 真机另有来源（`/opt` 或 `/opt/usr`）❓ **待上机 `ls`** |
| edje_cc / edje_decc | **不在机内**（rootfs /usr/bin 无）⇒ .edj 编译须 PC 侧（EFL 1.7.99 匹配工具链）或走纯代码构图 |
| 素材 | `res/edje/images` 4,106 个文件（lcd/hdmi 两套） ✅ |
| 三星私有 UI 库 | `libdi-elementary.so` (31,668 B / **127 符号**)；`libgui.so` (85,092 B)；`libapex.so` (40,440 B) |

### 3.2 与 U2 硬墙的关系（关键约束）

- U2 已证：**第二套全屏 GL 窗口在单核上拖死整机**（v8/v9，需物理重启）；`mod_gui` 小窗口可用。
- 宿主方案的立论正在于此：**复用现有 Canvas 不新建窗口/不另起事件循环** ⇒ 架构上绕开该硬墙。
  但该立论**未经任何上机检验**（无先例）——UI-1 系列实验设计（§5）即为逐级检验。
- 附带纪律（U2 教训）：图形实验 **≥30 秒持续观察 + 两轮负载 + "按键无响应"独立判据**。

### 3.3 权能盘点（宿主进进程后能拿到什么）

- **UI 面**：elm_ 230 / evas_ 73 / edje_ 12 个 API 可同源调用（编译时链接相机 rootfs 的 EFL .so，走既有归零链）。
- **参数面**：`CAttributeHandler::set_attribute(0x10e/0x110/0x111/0x112, &v, 4)` 在**同一进程内**
  ⇒ 这是 shell 侧（`st cap` 全家）到不了的 ③ 通道，宿主天然可呼（**但传输层语义仍待逆向**，见 U2 §10 候选 B）。
- **菜单面**：`CAPPGUIMenuView` / `tag_MENU_INFO` / 17 个 `UI_*_Menu_Info_By_GUI` 同地址空间；
  ★ 首选验证点 = `UI_Manage_Development_Menu_Info_By_GUI`（全项目唯一的"现成未验证入口"）。

---

## 4. 故障恢复设计（硬前置）

| 项 | 现状 | UI-1 前要求 |
|---|---|---|
| 进程自愈 | **`#Restart=always` 被注释** ⇒ 崩溃永久黑屏（U2 v9 教训：需物理重启） | 🔴 **~~drop-in 内启用 `Restart=always` + `RestartSec=3`~~ 已否决（10-13 晚实测）**：`restart` 该 unit 即卡死整机 ⇒ 启用后 = 「App 一异常就自动卡死」，**比不自愈更糟**。自愈须另寻机制（外部 watchdog 拉活 / 接受物理重启兜底） |
| 宿主自身纪律 | — | constructor **最小化**：只写心跳（open/write/close），零 EFL 调用、零全局构造副作用 |
| 心跳 | — | `/mnt/mmc/nxwa-hb.txt`（pid + 时间戳 + 版本串），供人查/供看门狗巡逻（后续可选） |
| 兜底 | 物理重启可行（长按电源，U2 已验证） | 实验前确认回滚命令就绪（§2） |

---

## 5. UI-1 最小实验设计（分级·含判据）

> 原则：一次一步（铁律 90）；每级**全绿才进下一级**；两级之间保留 ≥1 次"纯原厂状态"回归（拔 SD/删 drop-in 重启）。

### UI-1a —— 空宿主注入存活（第一裁决点）

- **实验体**：`libnxwa-host.so`，constructor 仅：读取自身版本串 → 打开 `/mnt/mmc/nxwa-hb.txt` 写 `pid|ts|ver` → 返回。
- **注入**：P1 drop-in（含 Restart 恢复）。
- **判据（4 条全过）**：
  1. ✅ 心跳文件出现，且 pid 对得上（`cat /proc/<pid>/comm == di-camera-app`）
  2. ✅ 屏幕正常出画面；telnet 21/23 可达；MENU 键进出菜单正常
  3. ✅ 30 秒 + 两轮 loadavg 观测，无可感劣化
  4. ✅ 可逆：删 drop-in + reload ⇒ **自然重启一次** ⇒ 心跳不再出现、一切如旧
     （🔴 原写法 `… + restart` = 卡死整机，已按 §7 实测修正）
- **裁决含义**：注入链（P1）+ 环境传递 + 无害性 + 可逆性，四项一次裁定。

### UI-1b —— 只读探测（不创建/不修改任何对象）

- **实验体**：在 1a 基础上追加**安全只读**动作：打印 `evas_version()`、`elementary_version()`；验证一组 elm_ 符号在进程内可解析（dlsym 主符号面或直接链接调用 version 类纯函数）。
- **判据**：心跳含版本串 + 1a 的全部 4 条判据复检。
- **禁止项**：创建 UI 对象、触碰任何窗口/canvas 指针、调用任何"会进入事件循环"的函数。

### UI-1c（预留，不在本轮设计范围）

任何"进程内首次创建 UI 元素/挂接菜单"的实验，必须等 1a+1b 双绿后**另行设计**（对接 C4 入口或 Canvas 复用两条线）。

**执行前置**：相机上线 + 门控 G0/G1（相机相关）恢复为 PASS；与 A1 Step1 正交互不阻塞。
**观测纪律**：≥30 秒；两轮负载；按键响应独立判据；失败即回滚（§2 命令）——失败不判"方向错误"，只记事实。

---

## 6. 风险清单

| # | 风险 | 缓解 |
|---|---|---|
| R1 | 宿主导致 App 崩溃 = 整机无屏 | Restart 恢复 + 物理重启兜底 + 1a 零 EFL 纪律 |
| R2 | systemd 208 传递 LD_PRELOAD 异常 | UI-1a 直接裁决；备选 P4（ld.so.preload，测试期） |
| R3 | 宿主与 App 的 EFL/glibc ABI 不匹配 | 归零链编译（自备 crt0 + 直接链相机 libc-2.13/EFL .so，见 NATIVE_UI_DESIGN_FULL） |
| R4 | 单核资源（常驻内存/字体缓存 10.7 MB 首渲延迟） | 铁律 88 + §5 观测纪律 |
| R5 | init.sh 晚于 App 启动（首注入不生效） | restart 兜底；上机先测时序（§7-2） |
| R6 | 固件版本漂移（偏移/ABI 变化） | 宿主文件名带版本 + bootstrap 存在性/版本检查 |
| R7 | 与 A1/C-2 波次互操作 | 三层正交（P7/App/交付），波次独立验收；失败互不牵连 |

---

## 7. 待上机核查清单（相机上线后）

> ★ **10-13 晚已全部执行完毕**，逐项结果见 **`CAMERA_ONLINE_PROBE_2026-10-13.md` §1**。摘要：
> 1 ✅ 208 ｜ 2 ✅ App boot+12.2 s vs init.sh boot+37.8 s（**慢 25 s，时序死锁**）｜ 3 ✅ 真机仅 4 个 .edj ｜
> 4 ✅ slp_edc 非本 App 资源 ｜ **5 🔴 静态面成立，但 `restart` 卡死整机** ｜ 6 ✅ environ 与 §1 表逐条一致、**零注入** ｜
> 7 ✅ rootfs ro（96 % 满）、`/opt/usr` rw（2.3 G 用 6 %）｜ 8 ✅ `/opt/usr/nx-ks/dicam/` 不存在

1. `systemctl --version`（真机版本，对照 rootfs 208）
2. `systemctl show -p ExecMainStartTimestamp bluetooth-frwk.service di-camera-app.service`（**时序裁决**）
3. `ls -la /usr/apps/com.samsung.di-camera-app/res/edje/`（**slp_edc 之谜：真机实有几张**）
4. `find / -name "slp_edc*.edj"`（`/opt` `/opt/usr` 排查）
5. `/run/systemd/` 结构 + 无害 drop-in 实测（`Environment=NXWA_TEST=1` + reload + ~~restart~~ → 查 `/proc/<pid>/environ`）
   🔴 **`restart` 这步会卡死整机——勿照做**；改「reload + 自然重启」后查 environ。详见新文档 §2。
6. `cat /proc/<pid>/environ | tr '\0' '\n'`（App 真实环境，对照 profile.d 清单）
7. `mount | grep -E "root|opt|usr"`（rootfs ro/rw、/etc 写保护现状）
8. `ls /opt/usr/nx-ks/dicam/`（T2 投递目录现状——C-2 波次共用）

---

## 8. 与 Codex 提案的对齐与修正

| 对齐 | 说明 |
|---|---|
| 大方向 | 进程内宿主 + 模块运行时 + 三层（交互/能力/数据）—— 采纳 |
| UI-0 定位 | 本审计在其"ABI 表"要求之上扩展了**注入路径决策 + 恢复前置 + 最小实验设计**（这是"动之前必须知道的"） |

| 修正 | 内容 |
|---|---|
| M1 | UI-2 第一版**静态内链接**（单体 .so），2–3 功能跑稳后再抽模块 ABI（防过早抽象） |
| M2 | 菜单注入**先验 C4**（`UI_Manage_Development_Menu_Info_By_GUI`），不先碰 `setMenuList` 改码 |
| M3 | **看门狗/Restart 前置**：任何进程内代码上线前，先恢复自愈（§4）——U2 物理重启的教训不可重演 |

**下一动作**（10-13 晚更新）：~~相机上线 ⇒ 先跑 §7 清单（8 项）⇒ 再启动 UI-1a~~ —— **§7 已跑完**。
⇒ 启动 UI-1a 之前，须先解 **`CAMERA_ONLINE_PROBE_2026-10-13.md` §5 的 U1**（boot+12.2 s 之前的执行点）
与 **U2**（restart 卡死机理）；且 UI-1a 实验设计须按该文档 **§2.4** 修订（**禁用 restart / 否决 `Restart=always`**）。

---
*生成：2026-10-13 · 分支 `nxwa` · 证据源：WSL `rootfs-112`/`rootfs-v113` 实测 + 5 份既有文档提炼（CAMERA_MENU_ARCHITECTURE / CAMERA_APP_STRUCTURE / U2_UI_DISPLAY / NATIVE_UI_DESIGN_FULL / FW_NATIVE_UI_ONEKEY_FEASIBILITY）*
*本文是审计（只读结论），不含任何写机动作；写机须过门控 + 波次验收。*
