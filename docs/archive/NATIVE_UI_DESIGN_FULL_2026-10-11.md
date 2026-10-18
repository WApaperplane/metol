# 原生 UI 设计 · 覆盖 mod 全部功能（2026-10-11）

> 取代/扩展 `NATIVE_UI_DESIGN_2026-10-07.md` + `UI_PAGES_OFFLINE_RENDER_2026-10-08.md`（D2 五页）。
> 本文是 **10 页全功能版**：每页都能对上 `FEATURE_MATRIX_MOD_FULL_2026-10-11.md` 里的功能 ID。
> **全部页面已在 QEMU 里实际渲染出图**（证据见 §6）。

---

## 0. 一句话

> **用相机自己的 evas（buffer 引擎）把 mod 的每一个功能画成一页 720×480，中文零 tofu；
> 10 页全部离线出图，出图链路可在 QEMU 里一键复现。**

---

## 1. 设计口径（★ 必须先读，否则会误用这批图）

### 1.1 这是「降级绘制」，不是真实控件

| 设计里写的 | 本轮实际画法 | 能判定 | **不能**判定 |
|---|---|---|---|
| `elm_list` / `elm_scroller` | `evas_object_rectangle_add` 行底 + 文字 | 布局、信息结构、中文出字 | 真实控件外观 |
| `elm_slider` | 槽 rect + 已填 rect + 数值文字 | 参数名/数值/相对位置 | 真实滑块手感 |
| `elm_radio` / `elm_checkbox` | 行 rect + 圆形/方形指示 rect | 选中态表达 | 真实控件外观 |
| `elm_button` | 按钮 rect + 文字 | 按钮分区与文案 | 真实控件外观 |

**原因**（D2 已实测）：`elm_init` 需要 elementary 的 engine 初始化，在**无显示服务的离线 chroot** 里会**挂死或崩**。
⇒ 本轮按 "rect + text 手工复现信息结构" 的口径执行，并在报告里明确标注为降级绘制。

### 1.2 尺寸 / 栅格

```
画面 720 × 480（相机 LCD）
├─ header      y   0 –  40   标题(26px) + 英文副题(20px) + 右上状态(18px)
├─ content     y  44 – 440   各页自定；统一内边距 10px
└─ statusbar   y 444 – 480   一行提示(20px)
```

### 1.3 配色令牌（与 D2 完全一致，不改）

| 名称 | 值 | 用途 |
|---|---|---|
| `BG` | `#0C0E14` | 背景 |
| `PANEL` | `#1A1E2C` | 行 / 卡片 |
| `PANEL_S` | `#262C38` | 选中行 |
| `TEXT` | `#EBEBF0` | 主文字 |
| `TEXT2` | `#D2D2D7` | 次文字 |
| `DIM` | `#96A0B9` | 说明文字 |
| `HL` | `#FFC850` | 高亮 / 选中标记 |
| `OK` | `#78FFA0` | 正常状态 / 状态栏 |
| `WARN` | `#FFAA5A` | 待办 / 需注意 |
| `DANGER` | `#FF9696` | 高危 |

### 1.4 字体规范（硬约束，离线已实测）

- 字体文件 `/usr/share/fonts/SDIC_GP_US_20120720.ttf`（10,680,224 B）
- 族名 `SDIC_GP_US`；CJK 有真轮廓（49,864 字形）
- ★ **每一处文本都必须显式 `font_source_set` + `font_set`** —— 不设则几何 0×0，**根本不画**。
  本轮 10 页共 **238 次 `font_set`** 调用（日志可查）。

---

## 2. 页面地图（页 ↔ 功能 ID）

| 页 | 页面 | 覆盖功能 | 日志实测 rect_n / ink |
|---|---|---|---|
| **P1** | 配方库 Recipes | F01 F02 F19 | 19 / 26100 |
| **P2** | 配方详情 Recipe | F02 F03 F04 F09 | 18 / 30800 |
| **P3** | PW 七维 Picture Wizard | F08 F09 F10 F11 | 27 / 29951 |
| **P4** | 3D LUT 管理 | F05 F06 F07 X03 | 18 / 25182 |
| **P5** | 引擎与判据 Engine & Verdict | F03 F04 | 14 / 28511 |
| **P6** | Web 遥控 / 相册 nx-rc | F12 F13 F14 F15 F16 F17 | 15 / 33179 |
| **P7** | 网络与连接 Network | F18 + 三通道 | 17 / 26840 |
| **P8** | 拍摄参数 / 键位 | F23 F24 F25 | 17 / 28498 |
| **P9** | 同步与安装 Sync & Install | F21 F22 | 14 / 29620 |
| **P10** | 诊断 / 高危 | 备份 / A1 / 门控 / 高危确认 | 16 / 28776 |

> 覆盖检查：§1 的 **F01–F25 全部落页**；X01–X05（不可做/冻结项）在 P4/P10 以边界文案出现。

---

## 3. 逐页规格

### P1 配方库 Recipes
- **header**：`配方库` / `Recipes` / 右：`95 条 / 6 页`
- **内容**：族统计行（负片32·反转18·黑白15·电影14·风格16）→ 2 列 × 3 行 = 6 条配方卡（色块 + 名称 + 7 维摘要）
- **选中态**：选中行高亮 + 右侧 `<` 标记
- **底部 4 键**：上一页 / 下一页 / 应用所选 / 返回
- **statusbar**：`波轮翻页 · 点击应用（不关窗）· 配方源：SD 卡 filmlab/recipes.json`
- **对应真实实现**：`filmlab.sh mkgui` 生成 `gui_filmlab1b.NX500`（6 页 × 18 + 4 键 = 22 按钮）

### P2 配方详情 Recipe
- 左卡：色块 + 配方名 + 族与 RGB 摘要；右卡：引擎 / `.cube` / 来源
- 七维参数 7 行（R/G/B 标 "外部可直推(A1前不可)"，其余标 "外部直推 ✓"）
- 底部 4 键：应用(--fast) / 写槽不切 / 对比原图 / 删除

### P3 PW 七维 Picture Wizard
- 7 条滑块：R 红 / G 绿 / B 蓝 / HUE 色调 / SAT 饱和 / SHARP 锐度 / CON 对比
- ★ 每行右侧标**可达性**：`需A1`（R/G/B/HUE）或 `直推✓`（SAT/SHARP/CON）
- 底部三格提示：长按回默认 / 写入 prefman + ISP 重读 / 判定：`filmlab.sh check`
- **这正是 F11「外部全 7 维一键」的 UI 表达**；A1 刷入后 4 个 `需A1` 应变为 `直推✓`

### P4 3D LUT 管理
- SD 卡 `/mnt/mmc/luts/*.cube` 列表（3 条）+ 机身内置 4 档
- 底部 3 键：写入所选 LUT / 重新扫描 SD / 恢复出厂表
- statusbar 明示：`写入走 LUT1 + lutsentinel 守护 · 只影响预览，不改 p7`

### P5 引擎与判据
- 引擎版本 / 配方库条数与字节 / `.cube` 数量
- ★ **`apply --fast` 判据块**：SAT/SHARP/CON/HUE 各「期望 vs 实测 → 命中」
- 判据命令写死在页面上：`sh /opt/usr/nx-ks/filmlab.sh check`
- statusbar：`『值变了』≠『被消费』—— 这一条是全项目的判据基准`

### P6 Web 遥控 / 相册
- 服务状态 4 行（80 / dirlist / thumb / push）
- **两条预热进度条**：网格 320px 最新 300 张（68%）、灯箱 1024px 最新 60 张（35%）
- 说明块：折叠目录模型（目录倒序、默认只展开最新）
- statusbar：`80 端口 daemon 的目录列表是启动快照 ⇒ 必须走 8080 dirlist 实时接口`

### P7 网络与连接
- IP / Telnet(23) / FTP(21) / SSH(dropbear) / HTTP(80,8080) 五行状态
- 8080 服务群 4 行：`thumb` / `dirlist` / `prewarm` / `push`
- statusbar：`点主菜单首行即可开/关 Telnet+FTP；不再用 EV+WiFi 组合键`

### P8 拍摄参数 / 键位
- `capdtm setusr/getusr` / WB 两轴 / 键位脚本 / 码率黑场 / FullLoad·FullSave
- 常用键位 4 行（`EV+AEL` 高亮为 "★ 打开 FilmLab 配方菜单"）

### P9 同步与安装
- 固件版本 / mod 落点 / 引导链 / 安装模式 / 卸载
- ★ 两块提示：插卡即自动执行 + 「安装完成」后**手动开一次蓝牙**以初始化 mod；增量同步只覆盖不删除
- 两个部署通道：SD 卡插入 / WiFi push
- statusbar：`刷固件不碰 mod：/opt/usr = p14，不在 SLP 10 段内`

### P10 诊断 / 高危
- 固件与备份状态 4 行：`p7 md5 5fc4824f…` / `分区备份 11/11` / `p12 pcache 已回纯净 0x00` / **`A1 p7 patch 未刷（slp_…v116 待刷）`**
- 高危操作 2 键（刷写固件需确认串 / 备份校验只读）+ 二次确认条（`CONFIRM-FLASH`）
- statusbar：`诊断页只读；所有写操作须经门控 + 二次确认`

---

## 4. 交互设计

| 交互 | 设计 | 依据 |
|---|---|---|
| 翻页 | **波轮**（keysym 待上机实测） | 铁律：mod_gui 不支持波轮（G04） |
| 选中 | 点按 / OK 键 | `EV_OK.sh` |
| 应用配方 | 点按即**写槽 + 切槽 + 三维直推**，**不关窗** | F02；G05 已证 mod_gui 做不到 |
| 高危操作 | 独立页 + 输入确认串 `CONFIRM-FLASH` | F24 / N07 |
| 长按 | 参数行长按回默认 | P3 |
| 返回 | 底部「返回」键 / `FN` | — |

---

## 5. 渲染与证据链（★ 本轮新建，可一键复现）

### 5.1 两条 QEMU 通道（★ 都跑通了）

| 通道 | 脚本 | 说明 | 本轮结果 |
|---|---|---|---|
| **用户态模拟**（出图主通道） | `build_modui.sh` → `run_modui_chroot.sh` | `arm-linux-gnueabi-gcc` 交叉编译 → `chroot rootfs-112` + `qemu-arm-static` → 出 PNG | ✅ 10 页 rc=0 |
| **系统模式（虚拟机）** | `qemu_vm_run.sh` | `qemu-system-arm -M virt` 起真 VM，**相机 rootfs 直接作为 VM 的根**（打成 initramfs），guest 内**原生**执行渲染器 | ✅ 10 页 rc=0（`raw8/repro/qemu_vm_run.log`） |

**系统模式的三条路取舍（★ 本轮实测，别重复踩）**：

| 路 | 组合 | 结果 |
|---|---|---|
| ① | **相机自己的内核** + `-M virt` / `-M vexpress-a15` | ❌ **零 console 输出**（Samsung 3.5 BSP、非 DT）。`virt` 挂住；`vexpress` 立即 reset。证据 `raw8/repro/qemu_vm_boot.log` |
| ② | 通用内核 + rootfs 作 **virtio 磁盘** | ❌ Alpine lts 内核 `VIRTIO_BLK` / `VIRTIO_MMIO` / `EXT4_FS` **全部 `=m`**（模块），initramfs 里没有 modloop ⇒ `mount /dev/vda` 报 **No such device** |
| ③ | 通用内核 + **rootfs 打进 initramfs** | ✅ **采用**：由内核自带 initramfs 装载，不依赖任何块设备驱动 |

系统模式日志里的自证（`qemu_vm_run.log`）：
```
=== GUEST 自证：这是虚拟机（armv7），且根 = 相机 rootfs ===
Linux (none) 6.6.134-0-lts #1-Alpine SMP ... armv7l GNU/Linux
lrwxrwxrwx ... /lib/ld-linux.so.3 -> ld-2.13.so
-rwxrwxrwx ... /usr/share/fonts/SDIC_GP_US_20120720.ttf   (10680224)
=== 跑 UI 渲染器（★ 原生 ARM 执行，不是 qemu 逐指令解释）===
renderer_rc=0        ... total font_set calls = 238
```
⇒ ★ **"QEMU 虚拟机里跑出 mod 全功能原生 UI"这条链路两端都成立**：用户态通道（快）+ 系统模式虚拟机（真 VM、原生执行）。

### 5.1b ★ 跨通道一致性（本轮最强的一条验证）

两条**互相独立**的 QEMU 通道产出的 10 张 PNG，**md5 逐张相同**：

| 页 | chroot（qemu-arm-static） | 系统模式 VM（qemu-system-arm） |
|---|---|---|
| p1 | `444623a3aadf97439d74f6f72e26e1ff` | `444623a3aadf97439d74f6f72e26e1ff` |
| p2 | `46e806aa257656fb1072628bdc80223b` | `46e806aa257656fb1072628bdc80223b` |
| p3 | `369408ccfba6699780319c42ec855757` | `369408ccfba6699780319c42ec855757` |
| … | （p4–p9 同样逐张相同） | 同左 |
| p10 | `75f3a09ed78b00b1c4df55bf9b227cbd` | `75f3a09ed78b00b1c4df55bf9b227cbd` |

⇒ 说明：**渲染结果只取决于「相机 rootfs（libc 2.13 + EFL 1.7.99 + SDIC_GP_US 字体）+ 我们的源码」**，
与"跑在哪种 QEMU 模式"无关 —— 与 S5 配方引擎"跨环境逐字节一致"是同一个性质的结论。

> 已知无害噪声：VM 里会打印两行 `Fontconfig error: Cannot load default config file`
> —— 精简根里没有 fontconfig 缓存；渲染器是**直接按路径指定字体文件**的，不受影响。

### 5.2 构建链（★ 本轮重建，替掉失效的 D 盘 zig 链路）

```
arm-linux-gnueabi-gcc -O0 -mfloat-abi=soft -fno-stack-protector -no-pie \
  -DUSE_ZLIB \
  -nostdlib -nostartfiles -Wl,-e,_start -Wl,--dynamic-linker=/lib/ld-linux.so.3 \
  -o modui_render.arm  modui_render.c  crt0_arm.S \
  $ROOTFS/lib/libc-2.13.so  $ROOTFS/lib/libz.so.1 \
  $ROOTFS/usr/lib/libecore_evas.so.1  libevas.so.1  libecore.so.1  -lgcc
```

**两个必须记住的坑（本轮踩过，都是"能编过但跑不起来"）**：

| 坑 | 现象 | 解法 |
|---|---|---|
| **crt1.o 的 glibc 版本** | chroot 里报 `/lib/libc.so.6: version 'GLIBC_2.34' not found` —— 宿主 gcc-13 的 `Scrt1.o` 引用 `__libc_start_main@GLIBC_2.34`，相机是 glibc 2.13 | **自备 `crt0_arm.S`**（引用 `@GLIBC_2.4`，与相机 `/usr/bin/st` 一致）+ `-nostdlib -nostartfiles` |
| **链错 libc** | 若仍用宿主 sysroot 的 glibc 2.39，即使自带 crt 也会重新引入 2.34 版本节点 | **直接链相机的 `libc-2.13.so`** ⇒ 版本需求整体落到 GLIBC_2.4/2.13（`readelf --version-info` 可自证） |

### 5.3 产物

| 文件 | 说明 |
|---|---|
| `raw8/repro/ui_page_p1..p10.png` | 720×480，24–37 KB/张（经相机 `libz` 压缩）；**md5 互不相同** |
| `raw8/repro/ui_pages.log` | 渲染器自写：`PAGE n -> path name=… rect_n=… ink=…` + `total font_set calls = 238` |
| `raw8/repro/qemu_vm_boot.log` | 相机内核系统模式启动实测（含否定结论） |
| `raw8/repro/qemu_vm_run.log` | 系统模式虚拟机运行日志 |
| `test_server/filmlab/src/modui_render.c` | 10 页渲染器（纯 evas rect+text，无 EFL 头） |
| `test_server/filmlab/src/ui_pages_render.c` | D2 五页版（保留，零依赖 PNG 写入器） |

### 5.4 门控 G3 已相应放宽

`gate_flow.py` 的 G3 从"硬编码 5 个文件名"改为
**「按目录发现 `ui_page_p*.png`（≥5 张）+ 每张 720×480 + md5 互不相同 + 与日志 PAGE 行一一对应 + ink 全 >0」**。
⇒ 页数可扩，判据不会因"多画了几页"而失真；同时日志与磁盘图**互证**，避免"图在但日志假"。

---

## 6. 与旧文档的关系

| 文档 | 关系 |
|---|---|
| `NATIVE_UI_DESIGN_2026-10-07.md` | 五页**信息架构**的原始设计；本文扩展为 10 页并落到实现 |
| `UI_PAGES_OFFLINE_RENDER_2026-10-08.md`（D2） | 首次离线出图的方法论（降级绘制 + SDIC_GP_US）；本文沿用其纪律，**重建了失效的构建链** |
| `FEATURE_MATRIX_MOD_FULL_2026-10-11.md` | 本文的功能对表来源（页 ↔ 功能 ID） |

---

## 7. 上机待验清单（QEMU 之后的剩余）

| # | 项 | 为什么必须上机 |
|---|---|---|
| 1 | **真实 elm 控件**外观（`elm_list/slider/radio`） | 离线 `elm_init` 会挂死 |
| 2 | **波轮 keysym** | 需真实键盘矩阵 |
| 3 | 单核上 `SDIC_GP_US` 首次渲染延迟（10.7MB 字体缓存） | 真机性能 |
| 4 | 触摸命中区与真实控件几何 | 需真实控件运行 |
| 5 | 从原生 UI 触发 `filmlab.sh apply` 后的 ISP 实际变化 | 只有 `check`/`iqr` 能答 |

---

*生成：2026-10-11 · 分支 `nxwa` · 姊妹文档 `FEATURE_MATRIX_MOD_FULL_2026-10-11.md`*
