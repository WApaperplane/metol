# NXUI 面板：还原按钮与"记住上次位置"（2026-10-19）

> **一句话**：PW 面板新增「还原」，LUT 面板的「还原原厂」改为与 apply 同一条 sh 调用链，
> 两个模式都会记住上次停在哪一项（存名字，不存序号）。

## 0. 三个"还原"入口，语义不一样

| 入口 | 命令 | 写槽 | 落盘 | 重启后 | 切档后 |
|---|---|---|---|---|---|
| PW「还原」 | `filmlab.sh neutral` | 否 | 否 | 回原厂 | 回该档位的值 |
| LUT「还原原厂」 | `lut.sh off` | **是**（两槽 + 两张登记表） | 否（RAM-only） | 回镜像原厂 | 仍关（登记表已回 A17） |
| PW「保存并关闭」 | `filmlab.sh commit` | **是** | **是** | 保持配方 | 该档位即配方 |

这不是实现不一致，是两条通道本身的差异：

- **LUT** 的"关闭"能落进登记表，所以切档、半按都还是关着的；只有断电才回镜像。
- **PW** 的参数属于"当前档位"，面板固定用 CUSTOM1（slot 9）当画布（见 `filmlab.sh` 的 UI 快路径注释）。
  写中性进 slot 9 只是把画布刷成灰，并不会改用户正在用的档位；要让"还原"跨切档保持，
  必须写用户当前档位的槽 —— 那会破坏他真实的风格设置，所以不做。

所以 PW 的还原是**临时复位**，提示语写的是"已还原中性 · 切档或重启回原厂"。

## 1. PW「还原」

`scripts/filmlab.sh` 新增 `neutral` 动词：

```sh
sh /opt/usr/nx-ks/filmlab.sh neutral
```

- 中性值 = `R/G/B=100`、`HUE/SAT/SHARP/CON=10`（`set_r` 的换算里 100 → 2032，正是 1.0 增益）
  - ★ **2026-10-19 修正**：初版把这四维写成 0，实机按「还原」直接变黑白。原因是四维值域 0-20、
    **10 才是零点**（`VARIABLE_PW{HUE,SATURATION,SHARPNESS,CONTRAST}` 的 `raw16 = 16*(值-10)+15`）。
    发 0 = 负向拉满 ⇒ SAT 归零 ⇒ 黑白。R/G/B=100 的类比不适用于后四维。
- 走 `pw_direct 100 100 100 10 10 10 10 --yes`，即 A2 的 7 维直推 + 提交位
- 前提与 preview 相同：`FILMLAB_PW=1` 且 `pwsend.arm` 存在；不满足就 `REJECT`
- 不 `prefman save`、不写槽 ⇒ 0 次 eMMC 写入

面板侧：按钮回调把 `queue.applied` / `queue.desired` 置 -1，所以"还原"之后
"保存并关闭"会重新走完整 apply，而不是误判"已生效只保存"。

## 2. LUT「还原原厂」的调用方式修正

原来发的是 `bash -c "<lut.sh 路径> off"`，要求 `lut.sh` 带可执行位；
而 apply/preview 走的是 `sh <引擎> <动词>`，不需要。同一条链两种前提，
部署时很难判断"为什么预览能用、还原不能用"。

现在 `neutral`(kind 7) 与 `off`(kind 8) 都改成：

```c
execl("/bin/sh", "sh", engine, "neutral" /* 或 "off" */, (char *)0);
```

与 apply 完全一致。测试里 engine 桩没 chmod 也能跑，正是靠这个修正暴露出来的。

## 3. 记住上次位置

存的是 **key**（配方 slug / look 名），不是序号 —— 库增删条目后序号会指错项。

| 项 | 值 |
|---|---|
| 目录 | `NXUI_STATE_DIR`，由 `nxui.sh` export 为 `/mnt/mmc/nxui` |
| 文件 | `last-filmlab` / `last-lut`，内容一行 key |
| 写入 | 写 `.tmp` 再 `rename`，断电不会留半截文件 |
| 时机 | 面板退出时（点关闭、半按、Esc、超时都算） |
| 失败 | 目录不存在或不可写 ⇒ 静默跳过，下次从头开始 |
| 名字失效 | 库里没有这个 key ⇒ 回到第一项，不停在空项上 |

**默认关闭**：不设 `NXUI_STATE_DIR` 就不读不写。这样测试、demo、`--snapshot` 天然隔离 ——
之前把默认值写成 `/mnt/mmc/nxui` 时，`verify_display` 的 idle 用例把位置写进了共享目录，
下一次 interaction 就从第 4 项开始，测试红得莫名其妙。

`READY` 行新增 `sel=N`，可以直接看恢复到第几项。

## 4. 按钮布局（测试与维护的依据）

面板 720×**208**（10-19 晚加横向滚动条后由 192 加高，见 `NXUI_SCROLLBAR_2026-10-19.md`）。

| 模式 | 行 | y | 列宽 / 列 |
|---|---|---:|---|
| PW | 滚动条 | 123..139 | 整宽 696 |
| PW | 按钮 | 144..170 | 4×168：15..176 / 191..352 / 367..528 / 543..704 |
| LUT | 滚动条 | 102..118 | 整宽 696 |
| LUT | 按钮 | 123..149 | 4×168：同上四列 |

PW 按钮行内容：‹ 上一个 / **保存并关闭** / **还原** / 下一个 ›
LUT 按钮行内容：‹ 上一个 / **保存并关闭** / **还原原厂** / 下一个 ›

LUT 面板没有 PW 分量行（省 16px），但没有省滚动条 —— 两模式都有一行 16px 的条，
所以 LUT 的按钮行仍比 PW 高 21px。
两处坐标都有测试钉住，改布局时先看 `test_interaction.py` 里的注释。

## 5. 验证（2026-10-19 18:15）

| 项 | 结果 |
|---|---|
| `verify_display.py` | **17 项 PASS**（host+arm × filmlab/lut/menu/idle/interaction/lut-interaction/service-interaction/performance + focus-handoff） |
| `test_interaction`（PW） | 新增：点第三列「还原」→ 引擎收到 `neutral` |
| `run_lut_interaction`（新） | 点第二列「还原原厂」→ 引擎收到 `off` |
| `test_last_choice.py`（新） | 写盘 / 恢复 / 未知 key 回落到 0，三项全 PASS |
| `test_lut_sh_rotation` / `test_cube2lut` | 8 / 14 PASS |
| `build.sh` host 单测 | PASS |

产物：

| 文件 | md5 | 大小 |
|---|---|---:|
| `scripts/nxui/nxui.arm` | `8a7001d4e76335dce28545f31e6276f9` | 460,516 B |
| `scripts/filmlab.sh` | `48fe58a91bc2d919e48347d6991f81c7` | 59,542 B |
| `scripts/nxui.sh` | `b0acc066a18c0e9da7f48d81a86e74ba` | 4,516 B |

## 6. 上机验收

| 步 | 动作 | 判据 |
|---|---|---|
| 1 | 开 PW 面板，选一张配方 → 半按 | 画面变（既有行为） |
| 2 | 再开面板 → 点「还原」 | 画面回中性；`/tmp/nxui.log` 有 `BACKEND kind=7 ok=1` |
| 3 | 点「还原」后切一次拍摄模式 | 画面回配方效果（这是设计，不是 bug） |
| 4 | 开 LUT 面板 → 点「还原原厂」 | 取景器回原厂表；`lut.sh status` 显示 IDLE |
| 5 | 关面板 → 重开（同模式） | 停在刚才那一项，不是第一项 |
| 6 | 删掉一张 look 的 `.cube` 后重开 | 若上次选的正是它，回到第一项，不报错 |

步 3 与步 5 是这次的两个关键判据：前者验证 PW 还原的语义边界，后者验证位置记忆。

## 7. 上机结果（2026-10-19 18:05–18:12，真机 192.168.0.106）

### 7.1 部署

| 目标 | 文件 | md5 核对 |
|---|---|---|
| `/opt/usr/nx-ks/nxui/nxui.arm` | nxui.arm | `8a7001d4…` ✓ |
| `/opt/usr/nx-ks/lut.sh` | lut.sh | `813b6d22…` ✓ |
| `/opt/usr/nx-ks/nxui.sh` | nxui.sh | `b0acc066…` ✓ |
| `/opt/usr/nx-ks/filmlab.sh` | filmlab.sh | `48fe58a9…` ✓ |
| `/mnt/mmc/lut/nx_regtabwrite.arm` | nx_regtabwrite.arm | `896de680…` ✓ |
| `/mnt/mmc/lut/cube2lut.arm` | cube2lut.arm | `582b12f0…` ✓（机上本来就是这版） |
| `/mnt/mmc/lut/nx_slotwrite.arm` | nx_slotwrite.arm | `ed170830…` ✓（同上） |
| `/mnt/mmc/lut/nx_regtabdump.arm` | nx_regtabdump.arm | `25365683…` ✓（**首轮漏传，后补**） |
| `/opt/usr/nx-ks/nxui/fonts/NXUI_CJK.ttf` | 字体子集 | `9736b5e5…` ✓ |
| `/opt/usr/nx-ks/nxui/fonts.conf` | fontconfig | `fca41133…` ✓ |

备份在 `/opt/usr/nx-ks/nxui/backup-lut-20261019/`（5 个 `.prev`）。
**机上没有 `/opt/usr/nx-ks/lut/`** —— LUT 工具在 `/mnt/mmc/lut/`，`lut.sh` 的 `pick_tool` 就落在那儿。

四个工具都要在 `/mnt/mmc/lut/` 齐全：`nx_regtabwrite.arm`（写登记表）、`nx_slotwrite.arm`（读写槽）、
`cube2lut.arm`（.cube → 19712 B 槽表）、`nx_regtabdump.arm`（只读 dump，诊断用）。
**首轮漏了 dump 工具** —— 它不在 `lut.sh` 的调用链上，所以 apply/off 全都能跑，只有排查时才发现缺。

`nx_regtabdump.arm` 实测输出（2026-10-19 18:38，off 之后的原厂状态）：

```
CTRL 0x80011620: 0xe59f1138 0xe59f2138 0xe59f3138 0xf5d1f0c0 [4/4]
VIEW4 @0x803837F0: 0x810fd100 0x81101e00 0x81106b00 0x81115200 [4/4]
STILL6 @0x80382C5C: 0x81119f00 0x81115200 0x8111ec00 0x8110b800 0x81106b00 0x81110500 [6/6]
BV12 @0x80382B00: 12/12
DUMP 16384 bytes ok
```

`VIEW4[3]` 回到 `0x81115200`（A17）、`STILL6` 全部原厂 —— 与 off 的预期一致。

### 7.2 数据面（`lut_accept_20261019.sh`）—— ALL PASS

```
PASS 第 2 次换槽 a18 -> a19
PASS 第 3 次换槽 a19 -> a18
PASS 第 4 次换槽 a18 -> a19
PASS 第 5 次换槽 a19 -> a18
PASS view 回读 a18/a19（每次）
PASS still 回读 a18/a19（每次）
PASS 状态保留 active=a18     ← A4
PASS off 后状态 IDLE         ← A3
PASS view 已回 A17
PASS a18 已还原 / a19 已还原
ALL PASS
```

脚本自身有三个 bug 导致第一轮误报 12 项，已修（`lut_accept_20261019.sh`）：

| # | bug | 现象 |
|---|---|---|
| 1 | `grep "READBACK.*$cur"` —— `$cur` 是 `a18`，日志里是 `0x81119f00` | 明明回读正确却报 "view 回读不是 a18" |
| 2 | `nx_slotwrite.arm` 硬编码 `/opt/usr/nx-ks/lut/` | §5 槽比对读不到文件，两槽都报"不一致" |
| 3 | `regtabwrite md5` 同样硬编码 | 环境段显示 `md5=?` |

现在两处都用 `find_tool`（先 `/opt/usr/nx-ks/lut`，再 `/mnt/mmc/lut`），A2 断言在地址层面比。

### 7.3 真机首帧（`selftest.sh`，1.5 s 自退，不写状态）

| 模式 | tier | font_ms | backend | map | FIRST_FRAME |
|---|---|---:|---:|---:|---:|
| FILMLAB（68 条） | 1 | 324 | 7 | 22 | **592 ms** |
| LUT（43 个 look） | 1 | 351 | 10 | 19 | **540 ms** |

**真机比 qemu 慢 5–6 倍**（qemu 冷缓存 51 ms / 首帧 105 ms）。差距几乎全在字体：Cortex-A9 建 7,547 码点的 `FcCharSet` 要 300+ ms，x86 上的 qemu 只要 50 ms。
⇒ 之前按 qemu 数据定的"首帧 ~105 ms 是下限"只适用于模拟环境；真机下限在 500 ms 量级，且字体仍占六成。

> 这条也意味着：字体子集在真机上的收益**可能比 qemu 显示的更大**（原厂 44,426 码点在真机估计 1.5–2 s），但本轮没有做"原厂字体真机基线"，所以不写具体数字。

### 7.4 待目视

数据面只证明写入与登记正确。下面四条必须人眼确认（见 §6）：

1. PW 面板选一张配方 → 半按 → 画面变
2. 面板点「还原」→ 画面回中性
3. 点「还原」后切一次拍摄档位 → 画面回配方（设计如此）
4. LUT 面板点「还原原厂」→ 取景器回原厂
5. 关面板再开 → 停在刚才那一项
