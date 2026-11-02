# LUT / FilmLab 库管理与机内混合（2026-11-01）

> **11-02 机上复查更正**：实体 Left 已明确采到 KP_Left/keycode83；本文“方向键无事件”结论已被推翻，其他键仍需逐个采数。库索引、排序缓存、BusyBox 精确匹配、恢复导出和备份冲突修复见 [11-02 复查](NXWA_ONDEVICE_REVIEW_2026-11-02.md)。

> 承接 [`LUT_STRENGTH_MIX`](LUT_STRENGTH_MIX_2026-10-31.md)（数学等价性）与
> [`LUT_ONDEVICE_PIPELINE`](LUT_ONDEVICE_PIPELINE_2026-11-01.md)（链路现状）。
> 上一轮只回答了「能不能」，这一轮把「强度 / 混合」做成机内可执行的动词，
> 并补上两套库的**机内增删与排序**、以及面板的**编辑态与混合态**。
> 全程离线（WSL 假机身树 + qemu-arm），相机未连接 —— 键位实测是唯一缺口。

---

## 0. 结论

| # | 命题 | 状态 |
|---|---|---|
| 1 | 混合**不需要任何硬件支持**：一个 5,164 B 的 `lutmix.arm` 就够，纯整数 | ✅ qemu 逐字节对齐 |
| 2 | 逐节点混合 = 输出域混合，误差仅来自 8 位取整（≤0.5 级） | ✅ 5 档 + 两端实测 |
| 3 | LUT 库的「顺序 / 收藏」是**一个文本文件**（`state/order`），不是数据库 | ✅ 33 项断言 |
| 4 | 下架 = `mv` 到 `looks/_trash/`，**不是 `rm`**（exFAT 删同名会释放簇链） | ✅ |
| 5 | 配方库**不建第二份顺序**，直接对 `recipes.json` 做块级重排，顺序即文件顺序 | ✅ 21 项断言 |
| 6 | 配方写盘后用 `recipes.txt` 可用行数做校验，不符即回滚 —— 这是唯一可靠的格式判据 | ✅ |
| 7 | 面板三态（浏览 / 编辑 / 混合）**复用同一行布局**，未破 720×208，未移动任何既有坐标 | ✅ 19 项全绿 |
| 8 | 机身键码**已实测**（2026-10-17 上机双探针）：X11 只有 `XF86Reload` / `XF86Favorites` 两个键，方向键与转盘在 X11 和 evdev 里都**没有事件** | ✅ 已写进默认表 |
| 9 | ⇒ 机身导航的主通道**只能是触摸**；混合态另给顶栏按钮（机身无 `F2`） | ✅ 双入口都有回归 |

---

## 1. 机内混合引擎 `lutmix.arm`

### 1.1 契约

| 项 | 规定 |
|---|---|
| 输入 A | 19,712 B 槽镜像 **或** 19,652 B 裸表（两种都接受，尾 60 B 重建） |
| 输入 B | 同上 |
| 强度 | 千分数 `0..1000`；`0` = 纯 A，`1000` = 纯 B |
| 输出 | 19,712 B 槽镜像；尾 = 末项 ×3 + 零填充 |
| 中性表 | `lutmix --identity <out>` 生成全值域恒等表 |
| 拒绝 | 参数不足 / 千分数越界 / 文件读不满或超长 / 打开失败，一律非零退出并打印原因 |
| 依赖 | **无 libc、无 libm、无 libgcc**：`-nostdlib -static -O0 -marm -mfloat-abi=soft`，syscall 走手写 `svc 0` |
| 体积 | 5,164 B，md5 `addae11303c911fe11ef7c48c01aa3c7` |

三种用法其实是同一个操作：

```
交叉淡入      lutmix a.bin b.bin 500 out.bin     0=A 1000=B
look 的强度   lutmix stock.bin look.bin 500 out.bin   0=原厂
中性基准      lutmix --identity out.bin
```

### 1.2 为什么机上算，而不是预生成 11 档

[`LUT_STRENGTH_MIX`](LUT_STRENGTH_MIX_2026-10-31.md) 当时的建议是「预生成 11 档 + 切登记表」：零设备端计算，代价是 11 个槽、217 KB、以及**改强度要回到 PC**。

既然混合只是 4,913 次乘加（`(a*(1000-p) + b*p + 500)/1000`），机上一次实测在 qemu 下不到 0.1 s、ARM 上同量级，那么预生成就只剩缺点：占槽、占卡、占 PC。**结论改为机内即时算。**

### 1.3 怎么验的

`test_server/lutpipe/test_lutmix.py`：Python 参考实现与 qemu-arm 真跑产物**逐字节比对**。

| 用例 | 内容 |
|---|---|
| identity | 4,913 个格点全部 `out[i] == i 映射`，尾填充正确 |
| 5 个强度 | 0 / 250 / 500 / 750 / 1000 |
| 端点 | 0 必须逐字节等于 A，1000 必须逐字节等于 B |
| 3 个拒绝 | 千分数 1001、参数缺失、文件不存在 |

全部 PASS。**没有一条断言是「看起来差不多」**，都是字节级。

### 1.4 强度 0 端的两个候选（必须在 UI 上说清）

| 基准 | 白点 | 拉到 0% 的观感 | 何时用 |
|---|---|---|---|
| **原厂 A17**（`0x81115200`） | 206 / 207 / 240 | 就是平时那张画面 | 有 `looks/_stock_A17.bin` 时（`lut.sh stock` 导出） |
| **identity** | 255 / 255 / 255 | **更冷更亮**，是全值域直通而非原厂曲线 | 没 dump 过时的兜底，会额外打印 `WARN` + `HINT` |

这不是 bug，是两条不同的参考轴。面板不隐藏这条差异：`strength` 的 `current` 记录里写明用了哪个基准（`strength:foo@60%(stock)` / `(identity)`）。

---

## 2. LUT 库：增删、排序、收藏

### 2.1 文件布局

```
/mnt/mmc/looks/
    <name>.cube / <name>.bin      库内容（name 是唯一键，同名 .cube 优先）
    _trash/<name>.<ext>           下架区
    _stock_A17.bin                原厂表（下划线开头 = 内部项，list 不显示）
/mnt/mmc/lut/state/
    order                         顺序 + 收藏（一行一条，* 前缀 = 收藏）
    cv/<name>.bin + .sum          .cube → native 转换缓存（按 cksum 失效）
    a18_orig.bin / ready / current / keep   既有会话状态（未变）
```

### 2.2 动词

| 动词 | 行为 | 刷新面板列表 |
|---|---|---|
| `list [--fav]` | 按 order 顺序输出名字，隐藏 `_` 开头 | — |
| `fav <name>` | 无星标 → 加星并**排到最前**；有星标 → 去星、**留在原位** | 是 |
| `move <name> up\|down\|top` | 相邻交换 / 提到最前 | 是 |
| `del <name>` | `mv` 到 `_trash/`，清掉该名字的转换缓存；若正在生效则自动 `off` | 是 |
| `index` | 重建 order：清掉已消失的条目，新文件按名字追加 | 是 |
| `mix <A> <B> <0-100>` | 交叉混合后 `commit_table` | 否（库没变） |
| `strength <name> <0-100>` | 以原厂/identity 为 0 端混合后 `commit_table` | 否 |
| `stock` | dump A17 到 `looks/_stock_A17.bin` | 是 |

### 2.3 order 的三条语义

1. **收藏是「前排」不是「筛选维度」**：加星同时置顶，去掉星标不改变位置 —— 用户手工调过的顺序不会因为取消收藏而被打乱。
2. **order 永远从磁盘派生**：每次进库先 `order_sync`，用 `ls` 的结果去修剪 order；order 里出现而盘上没有的条目直接丢掉。所以 `rm` 掉文件、或从 PC 塞进新文件，都不会让面板显示幽灵项。
3. **不在 order 里的新文件排在后面**，按名字排序。不需要用户手动「导入」。

### 2.4 转换缓存

`table_of()` 是所有动词的表解析入口：

- 同名 `.cube` 优先（与 `apply` 一致），否则用 `.bin`；
- `.cube` 按 `cksum` 缓存到 `state/cv/<name>.bin`，源文件不变就不重转（0.478 s/次，混合时可能连调十几次）；
- cksum 变了才重转，`del` 时连带清缓存。

### 2.5 为什么下架是「移动」而不是「删除」

exFAT 上**同名文件被重写时旧目录项不回收**，且删除一条同名项会释放整条簇链 —— 其余指向同一簇链的目录项立刻变成脏数据（详见现场纪律里 SD 卡那一节）。所以：

- LUT 是二进制表，可以从 `.cube` 重新生成，但没必要冒这个风险 ⇒ **移到 `_trash/`**，可逆，PC 侧挂载后回收；
- 配方是纯文本、有 `_backup/`，可以物理删（见 §3）。

两者在面板上都要**两段确认**，一次误触完不成。

---

## 3. FilmLab 配方库：`recipelib.sh`

### 3.1 为什么不建一份 order

配方的唯一真相是 `recipes.json`；面板读的 `recipes.txt` 又是 `filmlab.sh export` 从 JSON 生成的。再加一份 order 就是**三份状态**，迟早对不上。所以直接对 JSON 做块级重排，**顺序就是文件里的顺序**。

`filmlab.sh lib <verb>` 只是转发（`exec sh /opt/usr/nx-ks/recipelib.sh "$@"`），不在主链里塞两百行 awk。

### 3.2 块级手术

一个 awk 程序干完所有事：定位 `"recipes": {` 段（到 `"presets": {` 之前）→ 收集每个块的 `[起始行, 结束行]` → 按目标顺序重排 → 统一尾逗号。`list` / `count` / `move` / `del` 走**同一个解析器**，只有 `act` 不同。

> ★ 曾经踩过：用 `grep -c '"key": {'` 数配方，把 `"recipes": {` 和 `"presets": {` 也数进去了，79 变 81，于是「写盘后校验」永远不过、`verify` 永远红。**任何数条目都必须走同一个解析器**，不能用正则近似。

### 3.3 双校验与回滚

```
backup_now   → recipes.json → _backup/recipes-YYYYmmdd-HHMMSS.json
surgery      → .tmp
re_export    → filmlab.sh export → recipes.txt
commit       → 条目数 == 预期 && recipes.txt 可用行数 == 条目数 ? mv : 回滚
```

第二道校验是真正的格式校验：`recipes.txt` 是旧引擎 `nx_load_recipes` 的实际输入，**它解析不出足够行就说明 JSON 已经被改坏**。数括号、数逗号都不可靠，这个可靠。

`@gate` 头保持 `opens=rwdirect one_shot=0`，与其他 mod 脚本一致。

### 3.4 备份保留

`_backup/` 只留最近 **10** 份，超出按时间删最旧的。`restore` **只接受 `_backup/` 下的纯文件名**，防止路径穿越。

---

## 4. 面板：三态与键位

### 4.1 三种模式

| 模式 | 标题 | 怎么进 | 怎么出 |
|---|---|---|---|
| `UI_BROWSE` | `LUT` / `FILMLAB` | 默认 | — |
| `UI_EDIT` | `LUT / 编辑` | **长按列表项 ≥550 ms**（机身唯一入口）/ 桌面 `F1` | 「完成」/ `F1` / `Esc` |
| `UI_MIX` | `LUT / 混合` | **顶栏「混合」按钮**（机身唯一入口）/ 桌面 `F2` | 顶栏「退出混合」/ 「退出」/ `F2` |

三态的列表行、滚条位置、按钮行坐标**完全共用**，切态只换文案与按钮语义 —— 所以不会出现「进了编辑态按钮跑到面板外面」这类位移问题。

`UI_MIX` 的强度滑杆直接复用底部**状态行**显示（`A:sample B:stock 强度 45%`），不新增行 —— 按钮行的 `y=123 / 149` 两个坐标被既有测试钉死，动一下整排落出 208px 面板。

### 4.2 键位：机身实测只有两个键（2026-10-17 上机，双探针）

这不是推测，是当时挂了两个探针（`keysym_probe.c` 抓 X11 KeyPress、`evdev_probe.c` 直读 event0/1/2）实打实量出来的：

| 通道 | 实测结果 |
|---|---|
| **X11 KeyPress** | 只有 **`XF86Reload`（keycode 181）** 与 **`XF86Favorites`（keycode 164）** 能到；其余键**一个都没有** |
| **方向键 / 转盘** | X11 **无事件**，evdev 也**无事件** —— 走 `/dev/gpiodev.3` + `/dev/d5_ipcc` 的 GPIO 私有通道，被 `di-camera-app` 独占 |
| **evdev 直读** | 有事件的是半按快门：`/dev/input/event0` **code 125（`KEY_LEFTMETA`）**，已用于「半按关闭面板」，不占键位表 |
| **输入设备** | `event0` Drime5 GPIO Keyboard / `event1` ADC Keyboard / `event2` Melfas 触摸屏（**没有独立滚轮设备**） |

⇒ **方向键与转盘在这台机器上不可能作为交互通道**，不存在「再调一调就能用」的空间。所以机身的主通道是触摸，键盘只是补充。

默认键位表因此分两层：

| 键 | 动作 | 在哪有用 |
|---|---|---|
| `XF86Reload` | `prev` | **机身**（实测唯二之一） |
| `XF86Favorites` | `next` | **机身**（实测唯二之一） |
| `Left` / `Up` / `Right` / `Down` | `prev` / `next` | 仅桌面 / Xvfb 回归 |
| `Return` / `KP_Enter` / `space` | `ok` | 仅桌面 |
| `Escape` | `close` | 仅桌面 |
| `F1` / `F2` | `edit` / `mix` | 仅桌面（机身靠长按 / 顶栏按钮） |

`$NXUI_STATE_DIR/keys.conf` 可以覆盖，一行 `<keysym> <action>`；keysym 写名字或 `0x1008FF73` 这样的**数字**都行（相机那份 libX11 的 XF86 名字表只有 79 条，数字形式是名字解析不出来时的后路）：

```
# keys.conf
XF86Reload    prev
XF86Favorites next
0x1008FF73    prev
```

| 动作 | 含义 |
|---|---|
| `prev` / `next` | 上下移动选中项 |
| `ok` | 应用 / 结束编辑 / 应用混合 |
| `close` | 退出面板 |
| `edit` / `mix` | 切换编辑态 / 混合态 |
| `del` / `movel` / `mover` | 编辑态内的三个操作 |

> **这两个键各自对应哪个物理按键，还没和用户对过**（探针只说「按下去会到 X11」，没记是按的哪个键）。按反了就把 `prev`/`next` 对调，或在 `keys.conf` 里覆盖，不必改二进制。

### 4.2.1 因为机身没有 F2，混合态必须有触摸入口

`F2` 只存在于桌面。若没有别的入口，混合功能在机身上等于没交付 —— 所以**顶栏第三格**加了一个「混合」按钮（LUT 模式显示，非 LUT 模式用空 label 占位，行是手动 push 的，格数必须对满）：

```
[ LUT / 3D 滤镜          356 ] [ 菜单 104 ] [ 混合 104 ] [ 关闭 104 ]
```

顶栏几何（`padding=12/8`，行高 24，格间距 8）：标题 356 + 三格 104×3 + 3×8 = 692 ≤ 面板内宽 696。`test_library_ui.py` 现在**两个入口都验**：先用 F2 进一次，再用顶栏按钮「退出混合」→「混合」进第二次，两次都要真的走到 `lut.sh mix`。

### 4.2.2 采数通道（`nxui.sh` 现在透传多余参数）

```
sh /opt/usr/nx-ks/nxui.sh lut --inputlog /mnt/mmc/nxui/keys.log
```

日志把**每一个** KeyPress 都记下来（`KEY sym=<名字> code=<keycode> state=0x<修饰键>`），**绑定与否都记** —— 这才是采数用的，不是调试用的。按一遍硬件键，看日志里出现哪些 keysym，照抄进 `keys.conf` 即可。

实现上有个顺序问题：`nxui.sh` 全程用 `set --` 重建参数表（`--root/--recipes/--engine/--lut/--live` 分四段拼），所以透传参数**必须最后追加**，提前塞进去会被下一次 `set --` 冲掉。参数不支持含空格。

### 4.3 触屏手势

| 手势 | 结果 |
|---|---|
| 短按列表项 | 选中 / 应用（与触摸屏和鼠标同一条路） |
| **长按 ≥550 ms 不动** | 进编辑态 |
| 按下后位移 >12 px | 判定为滑动，取消长按 |
| 编辑态连点两次删除 | 第二次才执行，3 s 无操作自动取消确认 |

按下瞬间同时记 `press_at` 和坐标；`select` 的等待时间按 `press_at + 550` 与 `confirm_del_at + 3000` 里更早的那个收敛，所以长按不会多等一轮事件。

### 4.4 一个必须记住的坑：`nk_spacing` 会撑行

> **空位必须用 `nk_label(ctx, "", NK_TEXT_LEFT)` 占，不能用 `nk_spacing(ctx, 1)`。**

`nk_spacing` 在**最后一列**上会把 `row.index` 绕回 0 并 `nk_panel_alloc_row()` —— 等于多开一整行 65 px。库内条目少于 5 时，按钮行被顶到 `y=188`，整行掉出 208 px 面板，**静默不渲染**，现象是「点不到删除按钮」。这个 bug 花了两轮才定位，因为渲染没报错、测试也只看到「`move` 从未到达引擎」。

### 4.5 引擎调用统一走 `run_engine()`

```
sh <engine> <verb> [arg1 [arg2 [arg3]]]
```

不要求脚本带可执行位（机身 `/opt/usr/nx-ks/` 下的挂载不带 x 的情况见过一次）。`refresh` 参数区分这次操作要不要重读列表：`0`=不改库（混合）、`1`=重跑 `lut.sh list`、`2`=重读 `recipes.txt`。子进程退出后按此刷新，避免「操作成功但列表没变」。

---

## 5. 验收（全部离线、可复跑）

| 套件 | 内容 | 结果 |
|---|---|---|
| `test_server/lutpipe/test_lutmix.py` | qemu 真跑 + Python 参考逐字节比对 | **PASS**（identity + 5 blends + 端点 + 3 拒绝） |
| `test_server/lutpipe/test_lut_lib.sh` | `lut.sh` 库管理 / 排序 / 收藏 / 缓存 / 混合 / 非法名 / 下架当前 look | **33 PASS / 0 FAIL** |
| `test_server/lutpipe/test_recipelib.sh` | `recipelib.sh` 增删排序 / 双校验 / 回滚 / 备份保留 / 路径穿越 | **21 PASS / 0 FAIL** |
| `test_server/nxui/verify_display.py` | 面板全量：host + ARM qemu 双目标 × 9 模式 + focus-handoff | **19/19 PASS** |

`verify_display.py` 新增 `library-ui` 模式，完整走一遍：长按 → 编辑态 → 两段删除 → 自动刷新 → 左移 → 完成 → F2 混合 → 设 A / 设 B → 拖滑杆 → 应用 → **顶栏「退出混合」→ 顶栏「混合」→ 再混一次**。引擎用桩脚本，断言的是**实际收到的命令行**（写进 `calls` 文件轮询），不是面板日志 —— 面板日志里根本没有引擎输出。

同一个脚本现在还有一条键位断言：每个渲染模式都必须打出 `KEYMAP entries=12` 且**没有** `unknown keysym`。这条断言只在 ARM 目标（qemu + 相机 libX11）上才有意义 —— 相机那份 `libX11.so.6` 的 XF86 名字表实测只有 79 条（`strings` 数的），名字解析不出来就静默丢键。现在 host 与 arm 两种目标都过了，日志落在 `out/<target>-<mode>.log`。

另：`test_lut_sh_rotation.py` 已加 `skipUnless(LEGACY)`。它锚定早已退役的 `CAP=/usr/bin/st`，HEAD 版也失败；现行覆盖由 `test_lut_lib.sh` 承担。

> ★ 写 WSL 测试时的两个环境坑（不是脚本的错，但会把人绕进去）：
> 1. **`$?` 的展开在这套 WSL 会话里不可靠**（`false; echo $?` 会打印 0），但 `if cmd; then`、`cmd && …`、`cmd || …` 反映的是**真实退出状态**。断言一律写 `if`/`&&`，不要写 `[ "$?" = 0 ]`。
> 2. 用 `bash -lc "…heredoc…"` 生成辅助脚本时，`$@`/`$#`/`$1` 会在**外层**就被展开，生成出 `exec ""` 这种空壳。带 `$` 的辅助脚本一律先用文件工具写盘再 `cp` 进去。

---

## 6. 随包部署清单

| 文件 | 字节 | md5 | 落点 |
|---|---|---|---|
| `scripts/lut/lutmix.arm` | 5,164 | `addae113…` | `/opt/usr/nx-ks/lut/lutmix.arm` |
| `scripts/nxui/nxui.arm` | 474,740 | `8d8936d9…` | `/opt/usr/nx-ks/nxui/nxui.arm` |
| `scripts/lut.sh` | 19,548 | `686c41e7…` | `/opt/usr/nx-ks/lut.sh` |
| `scripts/recipelib.sh` | 9,527 | `1d5d4977…` | `/opt/usr/nx-ks/recipelib.sh` |
| `scripts/filmlab.sh` | 63,157 | `9972291c…` | `/opt/usr/nx-ks/filmlab.sh` |

> `nxui/build.sh` 末尾会自动 `cp out/nxui.arm ../../scripts/nxui/nxui.arm`，容易误以为「没重新部署」—— 判断依据只能是 md5，不是 `git status`。
>
> `install.sh` 是 `cp -ar /mnt/mmc/scripts/* /opt/usr/nx-ks/`，**只覆盖不删**。改了这几个文件之后必须同步 SD 卡母本 `/mnt/mmc/scripts/`，否则下一次 `install.sh` 会把机身打回旧版（这条纪律在 `cube2lut.arm` 上已经付过一次代价）。

---

## 7. 尚未闭环

| # | 事项 | 状态 / 怎么收 |
|---|---|---|
| 1 | **`XF86Reload` / `XF86Favorites` 各对应哪个物理按键** | 键码本身 10-17 已实测，**只差物理归属**。上机时 `nxui.sh lut --inputlog /mnt/mmc/nxui/keys.log`，各按一次即知；按反了在 `keys.conf` 里对调两行 |
| 2 | 混合结果的照片复核 | 需要实拍。混合表写进 A18 后**必须半按一次快门**；花屏 / 不生效都先怀疑 reload，**不要**去碰强制 reload |
| 3 | 顶栏「混合」按钮在真屏上的可点性 | 顶栏行高 24 px 偏小（手指目标一般要 ≥40 px）。若实测手感差，把顶栏行高提到 32 并相应压掉列表条的 8 px —— 现在没法验，因为面板只能在离线 X 里跑 |
| 4 | SD 母本同步 | 相机不在线，未同步 `/mnt/mmc/scripts/`。**下次上机装之前必须先同步**，否则 `install.sh` 会把机身打回旧版 |
| 5 | 「半按=关闭面板」与「半按=让 p7 重新 Load 表」是不是**同一次**半按 | 未验证。若同一次，流程最顺：改完强度 → 半按一次，面板关、表也生效；若不同，必须关面板后再半按一次。测量方法：面板内改强度 → 半按 → 退出后立刻看 `lut.sh status` 的 `ENGINE` 与实拍画面 |

已经被证据关掉的两条（留着是因为它们在别的文档里还写着「待验」）：

| 旧问题 | 实测结论 |
|---|---|
| 转盘 / 方向键会不会发 `KeyPress` | **不会**。X11 无事件、evdev 也无事件，走 GPIO 私有通道被 App 独占 ⇒ 不再是「待验」，是「此路不通」 |
| 是否要给 `--inputlog` 加默认开关 | **不加**。只在采数时手动带参数，常驻写 SD 会加剧 exFAT 碎片 |

半按快门这条是硬约束：`commit_table` 只写槽 + 改三张登记表，**从不自动触发硬件 Load**。裸写 `+0x00c` 加脉冲会花屏，这一点在 10-18 就定过，本轮没有改动。
