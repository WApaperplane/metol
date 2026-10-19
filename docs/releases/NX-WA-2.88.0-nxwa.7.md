# NX-WA 2.88.0-nxwa.7

发布日期：2026-10-19
上一版：2.88.0-nxwa.6

## 一句话

上一版能让取景器换上任意 3D LUT，但**关掉面板它就掉**、连切第二张不生效、滑到最后一张立刻半按会写成上一张。
本版把这条链补齐：双槽交替、退出不还原、半按前把队列排空；面板加横向滚动条、一键还原、记住上次位置。

## 1. LUT 切换"没反应"的三个真因

| # | 缺陷 | 表现 | 修法 |
|---|---|---|---|
| 1 | 退出时无条件 `lut.sh off` | 应用后闪一下即回原厂 | 删除退出还原；"还原"只由按钮触发 |
| 2 | 每次都写 A18，且 `View4[3]` 已经指着 A18 | 第二次以后不生效（指针不变 ⇒ p7 可能跳过重载） | **A18/A19 交替**，每次都是"新地址 + 新内容" |
| 3 | 半按丢弃 debounce 窗口里的最后一次选择 | 滑到最后一张立刻半按，写进槽的是**上一张**，面板却高亮最后一张 | 关闭时把队列排空（`drain_on_close`），最多补跑一张 |

配套的**写入自证**：`lut.sh apply` 不再信任返回值，写完回读 `View4[3]` / `Still6`，
必须等于目标槽地址，否则 `die`。这条防的是旧版 `nx_regtabwrite` 静默写回 A18 ——
部署时最怕的就是"日志全绿、画面没变"。

## 2. 面板：还原、记住位置、滚动条

| 入口 | 命令 | 写槽 | 落盘 | 切档后 |
|---|---|---|---|---|
| PW「还原」 | `filmlab.sh neutral` | 否 | 否 | 回该档位原值 |
| LUT「还原原厂」 | `lut.sh off` | 是 | 否 | 仍关（登记表已回 A17） |
| PW「保存并关闭」 | `filmlab.sh commit` | 是 | 是 | 该档位即配方 |

三个入口语义不同是**设计**，不是实现不一致：PW 的参数属于"当前档位"，面板固定拿
CUSTOM1 当画布，写中性进去只是刷画布；要跨切档保持就得写用户正在用的档位槽，会破坏
他真实的风格设置，所以不做。

**记住上次位置**：存 key（配方 slug / look 名）不存序号，库增删不会错位；
`tmp` + `rename` 原子写；名字失效回落到第一项。默认关闭（不设 `NXUI_STATE_DIR` 就不读不写），
测试与 demo 天然隔离。

**横向滚动条**（本版新增）：两模式共用一条 696px 的条，按下任意位置即跳过去，拖动实时跟手。

- 面板高度 192 → **208**（16px 条 + 5px 行距；192 会把按钮行挤出面板，Nuklear 直接不渲染）
- **不能用 `nk_slider_float`**：它的拖动判定要求"当前鼠标仍落在滑块矩形内"，
  696px 轨道分 7 步 = 每步 99px、滑块只有 26px ⇒ 手指一移出滑块拖动就断
- 自绘实现，并且**抬手那一帧按松手位置补算一次** —— 面板 10Hz 会把 20ms 一次的
  motion 合并，不补的话拖到 480px 只落到第 3 项
- 拖完直接生效，连续拖动由 150ms 防抖收敛成一次 apply

## 3. 面板打不开：`busybox` 多套了一层

`nxui.sh` 里写成了 `busybox setsid "$BB" "$BIN"`。busybox 的 `setsid` 只 exec 一个程序，
多出来的 `"$BB"` 让它把 `nxui.arm` 当成 **applet 名**：

```
/tmp/nxui.log: nxui.arm: applet not found
```

机身表现是"按键完全没反应"，文件 md5 却全是新的 —— 排查时最容易误判成"版本被回退"。
旧版能跑是因为中间有 `nice` 这个合法 applet，字体链收敛时删 `nice` 却没删那一层。

## 4. 首帧：真机在 500ms 量级

| 场景 | font_ms | FIRST_FRAME |
|---|---:|---:|
| PW（68 配方） | 314–324 | **526 ms** |
| LUT（43 look） | 293–351 | **449 ms** |

字体链两级：**GB2312 子集 1.9 MB（按 family，~50ms）→ 原厂 10.7 MB（按文件，~370ms）**。
38 KB 的面板子集**没有收益**（`FcFreeTypeQuery` 的固定开销与码点数几乎无关），默认关闭。
68 个配方名里有 21 个含中文，所以只发 ASCII 子集必然降级，反而更慢。

> 之前按 qemu 定的"首帧 ~105ms 是下限"**只适用于模拟环境**；Cortex-A9 建 7,547 码点的
> `FcCharSet` 要 300ms 以上。

## 5. 验证

| 项 | 结果 |
|---|---|
| `verify_display.py` | **17/17 PASS**（host + arm × filmlab/lut/menu/idle/interaction/lut-interaction/service-interaction/performance + focus-handoff） |
| `lut_accept_20261019.sh`（机端） | **ALL PASS**：5 次换槽交替 a18↔a19、view/still 回读、状态保留、off 三还原 |
| `test_lut_sh_rotation` / `test_cube2lut` / `test_regtabwrite` / `test_regtabdump` | 8 / 14 / 10 / 7 PASS |
| `test_launcher` / `test_lut_launcher` / `test_last_choice` | PASS |
| 真机 `selftest.sh` | PW/LUT 两模式 `rc=0`，`panel=720x208`，滚动条行落在 12,123 / 12,102 |

## 6. 安装

1. 把 `NX-WA-2.88.0-nxwa.7.zip` 解压到 **SD 卡根目录**
2. 插卡开机，`install.sh` 自动增量同步 `scripts/` → `/opt/usr/nx-ks/`
3. **首次需要重启一次**面板进程（`pidof nxui.arm` 有残留时先杀掉）

本版新增文件：

```
scripts/nxui/fonts/NXUI_CJK.ttf     GB2312 子集字体 1.9 MB
scripts/nxui/fonts.conf             只含 mod 字体目录的 fontconfig
scripts/nxui/install_nxui_fonts.sh  字体安装
scripts/lut/nx_regtabdump.arm       登记表只读 dump（诊断用，不在调用链）
```

部署后布局与用法同上一版；`/mnt/mmc/looks/*.cube` 仍是自己的滤镜库。

## 7. 回滚

```sh
/opt/usr/nx-ks/lut.sh off              # 登记表回原厂 + 两槽回备份 + 半按一次
cp /opt/usr/nx-ks/nxui/backup-lut-20261019/nxui.arm.prev /opt/usr/nx-ks/nxui/nxui.arm
```

所有写入都是**内存操作**，断电即回原状；不写分区、不刷固件。

## 8. 明确没验的部分

- **触摸拖动跟手**：数据面证明写入与登记正确，手感需目视。若"点击能跳、拖动不跟"，
  说明相机触摸板不发按住态的 motion —— 这是降级（抬手补算保证终点正确），不是故障。
- **持久性**：断电回原状；「开机即生效」仍需改固件镜像。
- **重载触发**：半按一定触发；切档 / 休眠唤醒是否触发**未测**。
- **多档并发**：`View4` / `Still6` 能否同时指向不同自定义表**未测**。
- **其它固件**：全部在 1.12 验证。

## 9. ⚠ 禁区

不要自己写 `+0x00C` 再脉冲配置寄存器强制重载 —— ISP 会读到原厂时序里从未出现过的地址组合，
**严重偏色花屏**，只能靠半按让 p7 自己走完选表复位。`lut.sh apply/off` 刻意不自动 reload。

## 10. 包内容与本版 md5

| 项 | 值 |
|---|---|
| 文件数 | 见包内 `NX-WA-MANIFEST.txt` |
| `nxui.arm` | `cedc8305dd5fa506ab3c978dd802d9b7`（460,628 B） |
| `nxui.sh` | `bb5b608b0934dacb59b57691385b2e8e` |
| `lut.sh` | `813b6d22e33de436bfbb33716d3adeb2` |
| `filmlab.sh` | `48fe58a91bc2d919e48347d6991f81c7` |
| `nx_regtabwrite.arm` | `896de680e99ae11c57082dfc6bf66913` |
| `NXUI_CJK.ttf` | `9736b5e57e8afd4cb315ae3db0510795` |

## 文档

- `docs/current/NXUI_SCROLLBAR_2026-10-19.md` — 滚动条：为什么不能用 `nk_slider_float`
- `docs/current/NXUI_PANEL_UX_2026-10-19.md` — 三个还原入口语义 + 布局坐标表
- `docs/current/NXUI_FIRST_FRAME_2026-10-19.md` — 字体链与真机首帧
- `docs/current/LUT_SWITCH_NOT_EFFECTIVE_2026-10-19.md` — 六步现场判别 + 交付 SOP
- `docs/current/NXUI_LAUNCH_APPLET_2026-10-19.md` — `busybox setsid` 多套一层
