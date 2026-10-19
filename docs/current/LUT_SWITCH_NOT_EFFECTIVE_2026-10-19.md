# LUT 切换"不生效"静态定位（2026-10-19）

> **一句话**：数据通路没坏，是 **NXUI 的退出路径把刚写进去的表又还原了**。`lut.sh apply` 之后 p7 还没来得及装载，`lut.sh off` 已经跑完；三条退出路径里只有一条会保住结果。

## 0. 结论前置

| # | 判断 | 强度 | 依据 |
|---|---|---|---|
| 1 | **LUT 模式下点"保存并关闭"、按 OK 键 = 应用后立刻 `lut.sh off`** ⇒ 必然无效 | 确定性（代码路径唯一） | `nxui.c:416-418` → `:634` → `:686-701` |
| 2 | **半按只走 event0 code 125 才保住结果；走 `EV_S1.sh` 通道必然还原** | 高（通道二选一，实际走哪条待现场确认） | `EV_S1.sh:4-6` → `nxui.c:559-563` 缺 `lut_keep` |
| 3 | 点"关闭"按钮、Esc、WM 关闭窗 ⇒ 还原（**这是设计如此**，不是 bug） | 确定性 | `nxui.c:366 / :589 / :585` |
| 4 | `apply` 不触发 Load，必须靠半按/切档；**"登记表指针没变、只换槽内容"这条路径从未被实证过** | 待验 | `lut.sh:120-128`；`LUT_RETARGET_LIVE` 三次半按的 `load_addr` 每次都变了 |
| 5 | 文档 `LUT_UI_2026-10-18.md §2.5` 与现行代码不符（写"apply 结尾调 reload"、"半按加 `&& !lut_mode`"，两者都不在代码里） | 确定性 | 对照 `lut.sh:120`、`nxui.c:551` |

## 1. 主因：退出即还原

`nxui.c` 末尾（686-701）：

```c
if (lut_mode && live) {
    if (lut_keep) { /* 写 /mnt/mmc/lut/state/keep */ }
    else { execl("/bin/sh", "sh", engine, "off", (char *)0); }   // ← 还原槽 + 两张登记表
}
```

而 `lut_keep` **只在一条路径上被置 1**（`nxui.c:548-553`，`/dev/input/event0` code 125 press）。其余所有退出路径都不置：

| 触发方式 | 代码位置 | `lut_keep` | 退出时 `lut.sh off` | 用户看到的 |
|---|---|---|---|---|
| 半按，走 **event0 code 125** | `nxui.c:548-552` | 1 | 否 | 生效 |
| 半按，走 **`EV_S1.sh`**（`touch /tmp/nxui-close`） | `EV_S1.sh:5` → `nxui.c:559-561` | **0** | **是** | 闪一下 → 复原 |
| 点"保存并关闭" | `nxui.c:410-419`（commit+close） | **0** | **是** | 永远不变 |
| 按 OK / Enter | `nxui.c:592-595`（commit+close） | **0** | **是** | 永远不变 |
| 点"关闭"、Esc、窗管关闭 | `nxui.c:366 / 589 / 585` | 0 | 是 | 设计如此 |

### 1.1 为什么"保存并关闭"这条最致命

`choose()` 已经先 `apply` 并写好了槽 + 登记表，用户再用最自然的方式点"保存并关闭"确认 → `commit_requested=1, close_requested=1` → 等 apply 子进程结束 → `break` → **无条件 `lut.sh off`**：

```
A18 ← 备份 / View4[3] ← A17 / Still6 ← 原厂
```

p7 此刻才在半按里读登记表，读到的是已经回退的 A17 ⇒ 画面永远是原厂表。**而且这个循环会稳定重复**：下次进面板又 `begin` → 又 apply → 又 off。

### 1.2 半按走的是哪条通道

- `EV_S1.sh` 是 NX-KS 的 **S1 单击槽位脚本**（`/opt/usr/nx-ks/EV_S1.sh`，keyscan 直接调），10-17 加入 `touch /tmp/nxui-close` 就是为了"半按关菜单"。
- `nxui.c` 同时另开一条 `/dev/input/event0` code 125。两条并存说明当时没确认哪条是真通道。
- 若 keyscan 对 `event0` 做了 grab，nxui 的 `ev_fd` 读不到任何事件（`open` 成功但不派发，代码里也没有失败日志），`lut_keep` 永远是 0 ⇒ **半按 100% 还原**。
- 现场判据：`cat /mnt/mmc/s1.log`。有 `nxui=1` 的行 = 走的是 EV_S1 通道。

## 2. 次因：指针不变时 p7 是否重载，没有实证

`lut.sh apply` 只做三件事：写 A18、`View4[3]→A18`、`Still6→A18`，**不触发 Load**（`:120-128`，注释里"reload 是禁区"）。

问题在于：
- 第一次 apply：`View4[3]` 由 A17 变 A18 —— 指针**变了**。
- 第二次 apply：`View4[3]` 已经是 A18 —— `nx_regtabwrite patch` 直接打印 `NOTE: already at target, nothing to write`，**4 字节都不写**。此时只有槽内容变。

`LUT_RETARGET_LIVE_2026-10-18.md` 的三次半按（步 3/5/8）**每次 `load_addr` 都发生了变化**，也就是说"指针变"这个条件一直成立。**"指针不变、只换内容"这条路径没有任何一次实证。**

如果 p7 的 View 装载路径对 `load_addr` 做了"不变则跳过"，那么第二次以后的切换就永远不会重新 DMA 表 ⇒ 与"只有第一次生效"完全吻合。

> 注：`do_reload` 的写序是从 `0x804A5C44` 反出来的 7 次无条件写，看起来不像有条件分支；但"函数被调用"与"函数被跳过"是两件事，静态无法定论。

## 3. 相机上线后的 5 分钟判别（按顺序做）

| 步 | 命令 | 期望 | 判什么 |
|---|---|---|---|
| 1 | `cat /mnt/mmc/s1.log \| tail` | 有 `nxui=1` 行 | 半按走 EV_S1（→ 主因 2 成立） |
| 2 | `sh /opt/usr/nx-ks/lut.sh status` | `VIEW4` 第 4 项、`load_addr` | 当前登记表与硬件装载源 |
| 3 | `lut.sh off; lut.sh apply portra400` **不用面板** | — | 绕开 NXUI |
| 4 | 半按一次，再 `lut.sh status` | `load_addr=0x81119f00` | 指针已改 |
| 5 | `lut.sh apply trix400`（**不清 off**）→ 半按 → `status` | 若画面不变且 `load_addr` 不变 ⇒ **指针不变不重载** | 次因定论 |
| 6 | 若步 5 无变化：`lut.sh off` → `apply trix400` → 半按 | 画面变 ⇒ 确认必须"指针发生跳变" | — |

判别 5 的关键：两次 `apply` 都指向 A18，`load_addr` 读数相同是必然的，**只能靠画面**。所以判据用两张悬殊极大的表（如 `trix400` 黑白 vs `velvia50`），不要用 A18/A19 那种 4% 差异的相邻表（旧教训）。

## 4. 修复选项

### A. 最小修（1 行级）：给所有"想保留"的退出路径置 `lut_keep`
- `nxui.c:559-561`（`/tmp/nxui-close`）→ 加 `if (lut_mode) lut_keep = 1;`
- `nxui.c:416-418` / `592-595`（commit+close）→ 同上
- 保持"关闭/Esc/WM"仍然还原

代价：`/dev/input/event0` 若真的读不到事件也无所谓，因为 EV_S1 那条已经兜住。

### B. 语义修（推荐）：把"还原"与"退出"解耦
- 面板退出**一律不还原**，只在显式点"还原原厂"时 `off`。
- 理由：LUT 是拍摄参数，不是 UI 状态；关面板就把照片风格改了，本来就反直觉。
- 代价：需要一个"还原"按钮，否则用户只能靠重启或命令行 `lut.sh off`。

### C. 双槽交替（解决次因）
- 每次 apply 在 A18 / A19 之间轮换，登记表跟着跳，**每次切换都产生指针变化**，不需要赌 p7 的重载条件。
- 附带好处：不再"逐字节改写正被登记表引用的槽"（`LUT_WORKBUDDY_REVIEW §4` 提过的竞态）。
- 代价：A19 是原厂 `Still6[2]` 的目标槽，会话结束后没有备份，`off` 只能靠重启还原 A19。需要单独为 A19 建备份。

**建议组合：B + C**。A 是过渡（改一行就能验证主因）。

## 5. 顺带记录的两个健壮性缺口

| 缺口 | 位置 | 后果 |
|---|---|---|
| `apply` 三段写入不具事务性：槽 → View 登记 → Still 登记 | `lut.sh:107-118` | 若 Still 段失败（如 `/mnt/mmc/nxwa_regtab_20261018/` 被清理，`still-set` 备份写不出），前面的槽和 View 已改，脚本报 ERR 但相机停在半应用态 |
| `begin` 无条件覆盖 `a18_orig.bin` | `lut.sh:69` | 若上一次 `off` 失败（A18 仍是一张 look），下次 `begin` 会把 look 当"原厂"备份，此后 `off` 永久回不到原厂。**v3 已修**：只在备份文件缺失时才写 |

## 6. 排查阶段未做的事（后续已补齐，见 §7）

- 排查时未连相机、未改任何机上文件；修复在同一日的第二轮完成，仍未连相机。
- 文档 `LUT_UI_2026-10-18.md` 与代码不一致的问题**已在第二轮订正**。

## 7. 修复落地（2026-10-19 第二轮，采纳 B + C）

### 7.1 改了什么

| 文件 | 改动 | 目的 |
|---|---|---|
| `scripts/lut.sh` | 重写为**双槽状态机**：apply 在 `A18 0x81119F00` / `A19 0x8111EC00` 间交替；两槽各有 `a18_orig.bin` / `a19_orig.bin` 备份；`off` 两槽都还原；`begin` 只补备份、不再 off；清理旧 `ready`/`keep` | C：每次切换都让登记表那 4 字节变化；写入的槽永远不是当前被引用的槽 |
| `nx_regtabwrite.c` | `patch` / `still-set` / `still-write` 接受可选槽地址参数（默认 A18）；`known_slot` 加 A19；`REFUSE` 非法槽 | 支撑双槽 |
| `nxui.c` | 删除退出时无条件 `lut.sh off` 与 `lut_keep`；LUT 模式按钮改为「‹ 上一个 / **还原原厂** / 关闭」；滤镜条 84 → **60px**；LUT 模式隐藏 PW 分量状态行 | B：退出不还原；顺带修布局溢出 |
| `nxui_model.c` | `nx_key_valid` 补拒 `/ \ ; $ `` | 修既有债：`../x` 原本能穿过校验（test_model 一直红） |

### 7.2 一个顺带发现的显示 bug

改完跑离线快照才发现：**滤镜条高度 10-18 从 55 改成 84 后，192px 高的面板放不下后续行，状态行和按钮行整行不再渲染**。也就是说在面板里根本点不到「保存并关闭」——这解释了为什么"切换不生效"会稳定复现，而不是偶发。

60px 后两个模式都完整：FILMLAB 显示 `标题 / 5 卡片 / 状态 / 3 按钮 / 底栏`，LUT 显示 `标题 / 3 卡片 / 3 按钮`。

### 7.3 产物

| 文件 | md5 | 大小 |
|---|---|---:|
| `scripts/nxui/nxui.arm` | `fcd8b1d4844104a39249627949561ec2` → **`8a7001d4e76335dce28545f31e6276f9`**（还原按钮 + 记住位置，见 `NXUI_PANEL_UX_2026-10-19.md`） | 456,132 → 460,516 B |
| `scripts/lut/nx_regtabwrite.arm` | `896de680e99ae11c57082dfc6bf66913` | — |
| `scripts/lut.sh` | `813b6d22e33de436bfbb33716d3adeb2` | 8,671 B |

GLIBC 依赖上限仍是 2.7（机上是 2.13），NEEDED 与旧版一致：`libX11.so.6` / `libXft.so.2` / `libc.so.6` / `librt.so.1`。

### 7.4 离线验证

| 项 | 结果 |
|---|---|
| `test_regtabwrite.py`（10 项守卫） | PASS，新增 A19 槽位校验与"两条登记表都走调用方槽位" |
| `test_lut_sh_rotation.py`（**新增**，8 项） | PASS：交替序列 `A18→A19→A18`、登记表跟随、每槽只备份一次、off 还原两槽、legacy 状态不原地覆盖、**旧版 writer 必须被拒**、**脚本里不得留单槽硬还原** |
| `test_regtabdump.py`（7 项） | PASS |
| `test_cube2lut.py`（14 项） | PASS |
| `build.sh host`（test_model + test_services） | PASS（修 key 校验前是红的） |
| LUT 面板快照 | 720×192，标题 + 3 卡片 + `‹ 上一个 / 还原原厂 / 关闭` |
| FILMLAB 面板快照 | 720×192，五要素齐全，无溢出 |

### 7.5 上机验收（相机上线后按顺序）

| 步 | 动作 | 判据 |
|---|---|---|
| 1 | 部署 `lut.sh`、`nxui/nxui.arm`、`lut/nx_regtabwrite.arm` | `md5sum` 与 §7.3 一致 |
| 2 | `sh /opt/usr/nx-ks/lut.sh begin` | `BACKUP a18=present a19=present` |
| 3 | `lut.sh apply <黑白色的表>` → 半按 | 取景器变黑白 |
| 4 | 再开面板 → 点另一张**悬殊**的表 → 半按 | 画面跟着变（这是旧版做不到的一步） |
| 5 | 连做 5 次，`lut.sh status` | `ACTIVE` 的 slot 在 a18/a19 间跳；`load_addr` = 当前槽地址 |
| 6 | 点「还原原厂」→ 半按 | 回原厂；`lut.sh status` 显示 `IDLE` |
| 7 | 不点还原，直接「关闭」→ 重新半按拍照 | LUT **仍然生效**（旧版这里会掉） |
| 8 | 拍一张 JPEG | 成片同样带 LUT（`Still6` 指向当前槽） |

步 4/5/6 是这次修复的真正判据；步 7 验 B，步 5 验 C。

### 7.6 已知边界

- **A19 不是空闲槽**：原厂 `Still6[2]` 就指向它（`0x8111EC00`），T1 阶段其指纹还异常（E0/diag8 对、尾部不符，未细查）。双槽意味着会话中 A19 也会被覆盖；`off` 靠 `a19_orig.bin` 还原，**若该备份缺失只能靠重启**（RAM-only，重启即回镜像）。首次 `begin` 必定生成两个备份。
- 两个槽的备份是"首次见到时抓取"。若有人绕过 `lut.sh` 直接写槽后再跑 `begin`，那份"原厂"就是脏的——与旧版对 A18 的限制相同，没有变坏。
- 面板仍会在半按后关闭（只是不再还原）。连续换 look 需要重新按 EV+WiFi，属于既有 UX，本次未动。
- 全部写入仍是 RAM-only，断电/重启回到镜像原厂表，不存在持久化损坏。

## 8. 交付物与上机 SOP（2026-10-19 15:45 补）

相机未上线，本轮止步于离线交付。上机时只需要下面三件。

### 8.1 部署包

| 项 | 值 |
|---|---|
| 路径 | `release/NXUI-LUT-FIX-20261019.zip` |
| 大小 | 1,330,658 B |
| sha256 | `95d2bfd42b53f0d43ec8e7e665818693e48bbb0396345b3c767fe82fc6cd6c47` |

内容（`manifest.md5` 随包）：

```
3a7601b40c21208033d4b53c2d7ad4e3  lut_accept_20261019.sh
48fe58a91bc2d919e48347d6991f81c7  scripts/filmlab.sh
813b6d22e33de436bfbb33716d3adeb2  scripts/lut.sh
582b12f0cc9f04ca765a8989d664b580  scripts/lut/cube2lut.arm
253656833f6555deaf58c5a088f18e8b  scripts/lut/nx_regtabdump.arm
896de680e99ae11c57082dfc6bf66913  scripts/lut/nx_regtabwrite.arm
ed1708306d8110ef1950bef2843e4747  scripts/lut/nx_slotwrite.arm
b0acc066a18c0e9da7f48d81a86e74ba  scripts/nxui.sh
fca41133f2c48c4fb8fb5612860afda6  scripts/nxui/fonts.conf
9736b5e57e8afd4cb315ae3db0510795  scripts/nxui/fonts/NXUI_CJK.ttf
a761a1ba5dbf39749a44eea204da7b93  scripts/nxui/install_nxui_fonts.sh
8a7001d4e76335dce28545f31e6276f9  scripts/nxui/nxui.arm
```

> 2026-10-19 18:34 重新打包：`lut_accept_20261019.sh` 修掉了三处硬编码路径（见 `NXUI_PANEL_UX_2026-10-19.md §7.2`），md5 由 `85abbc4a…` 变为 `3a7601b4…`。

### 8.2 部署（FTP 投递 → telnet 安装）

FTP 根被 chroot 到 `/mnt/mmc`，`/opt/usr` 只在 telnet 视野内。所以必须两段式。

**① FTP 侧**（相对 `/mnt/mmc`，先清空投递目录——它会累积历史测试文件）

```ftp
mkdir _xfer/20261019
cd _xfer/20261019
put nxui.arm
put lut.sh
put nx_regtabwrite.arm
put lut_accept_20261019.sh
put nxui.sh
put filmlab.sh
put NXUI_CJK.ttf
put fonts.conf
put install_nxui_fonts.sh
```

**② telnet 侧**（绝对路径，CWD 不在 /mnt/mmc）

> ⚠ **LUT 工具装在哪**：这台机器上根本没有 `/opt/usr/nx-ks/lut/`，`lut.sh` 的
> `pick_tool` 会落到 **`/mnt/mmc/lut/`**（SD 卡，FTP 可见）。`nx_regtabwrite.arm`
> 必须覆盖那一份，往 `/opt/usr/nx-ks/lut/` 拷只会得到 "No such file or directory"。
> 2026-10-19 上机时就踩了这一下。

```sh
B=/opt/usr/nx-ks
BK=$B/nxui/backup-lut-20261019
mkdir -p $BK
cp $B/nxui/nxui.arm            $BK/nxui.arm.prev
cp $B/lut.sh                   $BK/lut.sh.prev
cp $B/lut/nx_regtabwrite.arm   $BK/nx_regtabwrite.arm.prev
cp $B/nxui.sh                  $BK/nxui.sh.prev
cp $B/filmlab.sh               $BK/filmlab.sh.prev

X=/mnt/mmc/_xfer/20261019
cp $X/nxui.arm            $B/nxui/nxui.arm
cp $X/lut.sh              $B/lut.sh
cp $X/nxui.sh             $B/nxui.sh
cp $X/filmlab.sh          $B/filmlab.sh
cp $X/lut_accept_20261019.sh /mnt/mmc/lut_accept_20261019.sh
chmod +x $B/lut.sh $B/nxui/nxui.arm $B/nxui.sh $B/filmlab.sh
sync
```

LUT 工具（SD 卡侧，FTP 直接覆盖）：

```
put nx_regtabwrite.arm  /lut/nx_regtabwrite.arm
put nx_regtabdump.arm   /lut/nx_regtabdump.arm
put cube2lut.arm        /lut/cube2lut.arm
put nx_slotwrite.arm    /lut/nx_slotwrite.arm
put lut.sh              /lut/lut.sh
```

> ⚠ **四个工具一个都不能少**：`nx_regtabdump.arm` 不在 `lut.sh` 的调用链上，漏了它 apply/off 照样跑，
> 只有排查寄存器时才报 "No such file"。2026-10-19 就漏过一次。

回滚：`cp $BK/*.prev` 回对应位置。

**③ 字体（可选，但首帧差 320 ms）**

不装字体面板照样能用：`nxui.sh` 只在 `$D/nxui/fonts.conf` 存在时才 export `FONTCONFIG_FILE`，所以缺文件时 fontconfig 走系统配置，打开 10.7 MB 原厂字体（370 ms）。装了之后首帧从 ~430 ms 降到 ~105 ms。

```sh
sh /mnt/mmc/_xfer/20261019/install_nxui_fonts.sh /mnt/mmc/_xfer/20261019
```

装完会打印两个 md5，与 §8.1 的 manifest 对一下（`fonts.conf` = `fca41133…`，`NXUI_CJK.ttf` = `9736b5e5…`）。回滚就是删掉 `$B/nxui/fonts.conf`（下一帧起回到原厂字体）。

### 8.3 一键验收（数据面）

```sh
setsid sh /mnt/mmc/lut_accept_20261019.sh > /mnt/mmc/lut_accept.log 2>&1 &
```

轮询日志直到出现 `=== RESULT ===`。脚本验四条断言：

| 断言 | 含义 | 对应修复 |
|---|---|---|
| A1 | 连切 5 次，`active` 槽在 a18/a19 交替 | C（双槽） |
| A2 | 每次 apply，view/still 回读值 == 目标槽 | C 的防呆（旧 writer 会硬写 A18） |
| A3 | `off` 后 IDLE、登记表回 A17、两槽内容 == 原厂备份 | 还原链完整 |
| A4 | apply 后不 off，状态保留 | B（退出不还原） |

数据面 PASS 只代表写入与登记正确。**画面是否真的变，必须目视**：apply 后回取景器半按一次，看颜色是否跟着换。这一步机器替代不了。

> **2026-10-19 18:08 真机实测：ALL PASS**。5 次 apply 的 active 槽 `a18→a19→a18→a19→a18`，每次 view/still 回读都等于目标槽；A4 状态保留、A3 off 后 IDLE + view 回 A17 + 两槽内容与原厂备份逐字节一致。
> 第一轮曾误报 12 项 FAIL，全部是脚本自身硬编码路径与"名字/地址混比"，不是产品问题（详见 `NXUI_PANEL_UX_2026-10-19.md §7.2`）。

### 8.4 目视验收（三次操作）

| 步 | 动作 | 期望 |
|---|---|---|
| V1 | 开面板选一张**黑白** look → 半按 | 取景器变黑白 |
| V2 | 再开面板选一张**与上一张悬殊**的 look → 半按 | 画面明确改变（旧版卡死在这一步） |
| V3 | 不点还原直接「关闭」→ 随便拍一张 | LUT 仍在（旧版这里会掉回原厂） |
| V4 | 滑到最后一张后**立刻**半按（不等状态行） | 落地的是最后那张，不是上一张（§9 的排水修复） |

## 9. 半按"排水"：关面板时补跑最后一个未落地的选中

### 9.1 触发点

上一轮回答「半按能不能直接保存并退出」时，逐行核到主循环里的一道闸：

```c
/* 旧 */
if (!child && (!queue.close_requested || queue.commit_requested) && (index = nx_queue_take(...)) >= 0)
```

`close_requested=1` 而 `commit_requested=0` 时，队列里**还没 dispatch** 的 apply 请求被直接丢弃。而 LUT 模式的 apply 在 `choose()` 之后要过 150 ms 防抖（`NXUI_DEBOUNCE_MS`，`nxui_model.h:7`）才 `start_child`。

于是最常见的手势——滑到最后一张、手指还没离开就半按——写进槽的是**上一张**，而面板上高亮的是最后一张。屏幕和槽不一致，且没有任何提示。

### 9.2 改法

| 位置 | 改动 |
|---|---|
| `nxui.c` 全局 | 新增 `drain_on_close` |
| 主循环 | 关闭条件加 `(!lut_mode \|\| queue.desired < 0 \|\| queue.desired == queue.applied)`：LUT 模式下还有没落地的选中就先不 break |
| 主循环 | `nx_queue_take` 的那道 `(!close_requested \|\| commit_requested)` 闸去掉；启动时若已 `close_requested` 则置 `drain_on_close` |
| `poll_child` | `drain_on_close` 的那一跑无论成败都退出——面板此时已 `XUnmapWindow`，没有地方显示错误；失败等价于"没切换"，日志里有 `BACKEND ok=0` |

**FILMLAB 不受影响**：`drain_on_close` 只在 `lut_mode` 下置位，FILMLAB 的关闭仍然是"丢弃未落地的预览"（它的 preview 本来就不是承诺）。

最多只补跑一张：`nx_queue_select` 是覆盖式的（`nxui_model.c:132` 只留最后一个 `desired`），不会连锁。

### 9.3 构建与回归

| 项 | 结果 |
|---|---|
| `build.sh`（host `test_model` + `test_services`，ARM 交叉） | PASS |
| 新 `nxui.arm` | md5 `fcd8b1d4844104a39249627949561ec2`，456,132 B（字体链修复后重建，见 `NXUI_FIRST_FRAME_2026-10-19.md`） |
| NEEDED | `libX11.so.6` / `libXft.so.2` / `libc.so.6` / `librt.so.1`（未变） |
| GLIBC 上限 | 2.7（未变） |
| `test_lut_sh_rotation` 8 / `test_regtabwrite` 10 / `test_cube2lut` 14 / `test_regtabdump` 7 | 全 PASS |
| `verify_display.py`（Xvfb，host + qemu-arm 两套 × filmlab/menu/idle/interaction/service-interaction/performance + focus-handoff） | 13 项全 PASS |
| `test_lut_backend_shell` 21 | WSL 下全 PASS；**Windows 下 2 项红**，是 `pathlib` 路径分隔符与临时目录隔离导致的误报，与本次改动无关 |

**顺带修掉一条测试债**：`test_interaction.py:54` 的「保存并关闭」点击坐标写死 `y=160`，对应 10-18 之前 84px 的滤镜条。条高降到 60px 后按钮行上移到 123..149，那一下点进了状态标签——测试一直红，但上一轮没跑到这个文件。已改为 `y=136` 并注明换算。
