# mod_gui 弹出提速 + 配方库扩充（2026-10-10）

> ⚠️ **2026-10-18 文档清理：本文结论已被取代。** `mod_gui` 已被 NXUI 取代；配方数现为 **68**（本文的 95 条口径已废弃，以 `scripts/filmlab/recipes.json` 为准）。
> 现行结论见 [`NXUI_NUKLEAR_2026-10-17.md`](NXUI_NUKLEAR_2026-10-17.md)。


> 用户三项诉求中的 1、2：**「modgui 弹出要两秒多」** 与 **「进一步增加滤镜配方」**。
> 结论：**弹出路径 2.4 s → ~0.6 s（约 4×）**；翻页 3.2 s → ~0.4 s（约 8×）；
> 配方 **35 → 68 条**（菜单自动分 4 页）。全部改动已上机验证。

---

## 1. 慢在哪（先量化，别猜）

弹出链（`EV+AEL` → 菜单）：

| 段 | 旧版耗时 | 原因 |
|---|---|---|
| `st app bb lcd on; st app disp lcd` | ~0.2 s | 同步等 |
| **`sleep 1`** | **1.0 s** | 社区惯例的"屏幕切换余量"，纯白等 |
| **`filmlab.sh mkgui`** | **~1.0 s** | ★ 头号来源：**每次全量重建菜单** |
| `mod_gui` 启动 | ~0.2 s | 14 KB ELF |

### 1.1 mkgui 为什么慢 —— **fork 风暴**（实测）

每行配方都要 `LBL=$(echo "$LBL" | tr -d '"\r,' | sed 's/[|]//g')` ⇒ **每行 fork 3 次**，
18 行 = **54 次 fork**。单核 ARM 上一次 fork 十几~几十毫秒 ⇒ 这就是那"第二秒"。

| 版本 | 冷跑（重建菜单） | 热跑（未变，直接复用） |
|---|---|---|
| **旧版** | **46 fork** | 47 fork（没有缓存，每次都重建） |
| **新版** | **8 fork** | **3 fork** |

> 量法：`/tmp/mkbench.sh` —— 给 `awk/grep/sed/tr/cmp/...` 装计数 shim，统计一次 `mkgui` 的
> 全部外部命令调用。机上实测交叉印证：**热跑 0.162 s/次（含 bash 启动）、冷跑 0.26 s/次**。

### 1.2 ★ 一个真踩到的坑：跨文件系统的 `mtime` 不能用来做缓存

初版缓存用 `[ "$PG" -ot "$OUT" ]`（页号文件比成品旧 ⇒ 复用）。
**在机上时灵时不灵**：`/opt/usr` 是 **ext4**、SD 卡是 **exFAT**，两侧 mtime 粒度不同 ⇒
`page.idx` 与成品会判成"同秒" ⇒ `-ot` 为假 ⇒ 每次都全量重建。

```
实际观测：连跑 3 次 mkgui —— 3 次全部 "已生成"（缓存没生效）
修复后：  1 次 "已生成" + 3 次 "缓存命中"
```
⇒ **改用【内容指纹】**：`md5sum recipes.json` + 页号 + 当前项，存 `gui_filmlab1b.NX500.sig`。
**与文件系统无关、确定性**。（配方表同样改为 md5 比对，落 `recipes.txt.md5`。）

---

## 2. 改了什么（四处）

| 文件 | 改动 | 效果 |
|---|---|---|
| `scripts/filmlab.sh`（mkgui） | ① 删冗余 `jlist` 预扫；② 按钮生成改**单个 awk**；③ 配方表 + 菜单**内容指纹缓存**；④ 原子替换 `$OUT.tmp → mv` | 46→8 fork（冷）/ 3 fork（热） |
| `scripts/EV_AEL.sh` | 切屏**后台发**；去掉 `sleep 1`，留 `EV_AEL_DELAY`（默认 0.4 s，可调 0）；补 NX1 机型闸门 | −1.0 s 硬等 |
| `scripts/filmlab_page.sh` | 去掉**两个** `sleep 1`；页数改读 `recipes.txt`（与 mkgui 同源）；旧窗口改"退了就走"有界等待 | 翻页 −2.0 s |
| `scripts/gen_menu.sh` | IP 提取 4 进程 → **1 个 awk**；Telnet 状态 `ps -w` → **`pidof`**；内容不变不写盘 | 主菜单（EV 键）路径提速 |
| `scripts/loadgui.sh` | 型号/版本判断 2~4 个 `grep` → **读一次文件 + bash 内部分行** | 少 3 次 fork |
| `scripts/filmlab/recipes.json` | **35 → 68 条配方** | 菜单自动分 **4 页** |

★ 两份 `EV_AEL.sh`（`scripts/` 与 `scripts/nx-rc/`）之前**内容不一致**、且全量安装会互相覆盖
—— 本次**统一为同一份**（md5 `974d4fb4`）。

---

## 3. 机上验证（真机 192.168.0.105）

| 项 | 结果 |
|---|---|
| 5 个脚本部署 | 机上 md5 == 本地；`sh -n` 全 **SYNTAX-OK** |
| `recipes.json` | 机上 md5 `8ab47634…` == 本地 |
| 解析 | `recipes.txt` = **68 行**，每行 9 字段（引擎同款 awk 复算，0 空字段） |
| 菜单 | `gui_filmlab1b.NX500` = **22 个 button**（18 配方 + 上/下页 + 返回 + 取消）；标题"第 1/4 页（配方库共 68 个）" |
| 缓存 | 连跑 4 次：1 次重建 + **3 次"缓存命中"** ✓ |
| 耗时 | 热跑 **0.162 s/次**、冷跑 **0.26 s/次**（`/proc/uptime` 两位小数实测） |
| CI / 门控 | `check_scripts.py` **0 fail / 0 warn**（168 文件）；`flab_sim.sh` **12/12 PASS**；G0–G5 无回归 |

**预期端到端**：

| 动作 | 旧 | 新 |
|---|---|---|
| EV+AEL 开菜单 | ~2.4 s | **~0.6 s** |
| 翻页 | ~3.2 s | **~0.4 s**（点即退，无 sleep） |
| 改配方后首次开菜单 | ~2.4 s | ~0.7 s（这一次确实要重建） |

★ `EV_AEL_DELAY`：默认 `0.4`（秒）。调快用 `EV_AEL_DELAY=0.2`；
若发现窗口起在 EVF 上（后屏看不见），调大到 `0.8`。

---

## 4. 新增的 33 条配方

| 类别 | 新增 |
|---|---|
| 彩色负片（9） | Lomo 100 / Lomo 800 / Gold 100 / Gold 400 / Fujicolor 100 / Solaris 100 / Vista 400 / Reala 100 / Fuji 9000 |
| 反转片 E-6（5） | Velvia 50 风光 / Provia 1600 / Sensia 100 / EliteChrome 100 / Velvia 100F |
| 黑白（7） | TriX 400 推档 / HP5 推1600 / Delta 100 / T-MAX 100 / Pan F Plus 50 / Neopan 100 / Kentmere 400 |
| 电影卷（3） | Vision3 500T / CineStill 50D / Double-X 5222 |
| 风格（9） | 青橙 / 暖旧 / 冷峻 / 褪色 / 高调 / 低调 / 棕褐 / 漂白 / 蓝调时刻 |

取值域沿用既有配方：`R/G/B 88–125`（100 中性）、`HUE 9–15`（10 中性）、
`SAT 0–16`（0 = 纯黑白）、`SHARP 7–13`、`CON 3–16`。

★ 提醒：本机 PW 只有 **SAT/SHARP/CON 三维**能外部直推（`PW_ID_MAP_FULL_2026-10-10.md` §6），
R/G/B/HUE 需走官方「画面向导 → 自定义1」；所以**配方的色彩倾向靠槽位 + 官方路径体现**。

---

## 5. 复现与回归

```bash
# 离线
bash test_server/filmlab/flab_sim.sh          # 12 断言
python test_server/filmlab/flab.py lint       # 配方格式 lint
bash /tmp/mkbench.sh scripts/filmlab.sh NEW   # fork 计数（冷/热）
python test_server/tools/check_scripts.py     # CI

# 上机（每脚本自带 cp+chmod+sh -n+md5 自证）
python test_server/tools/cam.py deploy scripts/filmlab.sh /opt/usr/nx-ks/filmlab.sh
# … EV_AEL.sh / filmlab_page.sh / gen_menu.sh / loadgui.sh 同理
# 配方库单独 FTP 到 /filmlab/recipes.json
```

---

*生成：2026-10-10 · 分支 `nxwa` · 真机 192.168.0.105 · 全部改动已上机验证*
