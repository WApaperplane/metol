# NX-WA 2.88.0-nxwa.13 — 视频 LUT 自动联动 / 2.5K 片门全开

发布日期：2026-11-07
性质：功能版本。3D LUT 从「取景 + 照片」扩到录像，且不再需要第二个开关。

## 一句话

`lut.sh apply` 之后直接按录像键就带同一条表，`lut.sh off` 自动停；加载不再靠 `sleep`
猜时间，等的是 ISP 的完成中断，实测 **1.2–6.8 ms** 返回。附带把 2.5K 片门全开验成
可双向、可查询的开关 —— 水平覆盖达照片宽度的 **98.79%**，约 UHD 的 1.66 倍。

## 一、视频 LUT：同一条表，自动跟随

旧做法是开录后盲写工作槽 + 改四张登记表，再 `sleep` 等 p7 自己读。两个说不清的地方：
不知道什么时候写进去的，也不知道到底写进去没有。

新工具 `scripts/lut/nx_lutload.arm` 把这件事变成可确认的：

1. 仅 NX500 / 1.12，单次加载只接受 A17 / A18 / A19，未知 Cfg 直接拒；
2. 使能 EP 的 `EP_K_INT_ACC_3DLUT_RD_FINISH=7`，注册等待队列；
3. 写地址、格式、通道，`+8 bit8` 置位再清零；
4. 等驱动完成中断（500 ms 超时），随后退出访问模式；
5. **超时返回 `errno 110`，绝不记成成功** —— 失败也清访问模式。

`scripts/lut_video.sh` 管生命周期，`scripts/lut.sh` 负责联动：

```sh
sh /opt/usr/nx-ks/lut.sh apply warm_gold   # 同时启动录像监视
# 直接按录像键，不再需要 video on
sh /opt/usr/nx-ks/lut.sh off               # 先停监视，再还原登记表
```

| 设计点 | 为什么 |
|---|---|
| 用相机进程持有的**可写 MP4 描述符**（`l-wx` + DCIM）判断真的在录 | 时间窗猜不准，开机/回放也会开 MP4 句柄 |
| 开录后 400 ms + 连续采样稳定检查 | 初版首次开录撞上一次超时，重试才成功 |
| 只认**本次开机** View4 四项都指向 A18 | 防止沿用重启前卡上的 ACTIVE 标记，把表写进错槽 |
| 控制锁 / 监视锁 / 加载锁分开 | 重复 `apply` 不打架，PID 保持不变 |
| 状态全在 `/tmp/nxwa-lut-video` | 重启即失效，不会带病启动 |
| 连续两次失败就退出 | 不留下一个反复写寄存器的死循环 |

录像 LUT 与普通 LUT **共用一个入口**：面板里应用滤镜成功即启动，`off` 即停。没有新增
视频 LUT 按钮，也没有"一小时过期"。

## 二、说清楚这版做不到的

比写得好看更重要的是写清楚。下面两条不是理论风险，是录到了的：

| 现象 | 证据 | 影响 |
|---|---|---|
| **录像中途换表会出现约 2 秒纯灰帧** | `SAM_0325.MP4`：正常 → 纯灰 → warm_gold；3.0–5.0 s 抽样 9 帧全帧 `YMIN=YMAX=128`、`UAVG=VAVG=128`，随后恢复 | 这段素材不可用，剪掉 |
| **第一帧不保证带 LUT** | 加载在开录之后才触发 | 起手若干帧仍是原厂色 |

未覆盖：长录（>10 s 只测到 8.085 s）、更多帧率、快速状态竞争、面板内直接开关。
「开录即带 LUT」需要 p7 侧在录像初始化之前就拿到表，当前是事件驱动的补写，做不到。

## 三、2.5K 片门全开

UHD 构造器里两条立即数决定输出尺寸，改成 1440 / 2560 就是 2.5K（每轮结束都回读恢复）：

```text
0xe4428: 878ea0e3 -> 5a8ea0e3   # height 2160 -> 1440
0xe442c: 0faca0e3 -> 0aaca0e3   # width  3840 -> 2560
```

照片与两段视频做 SIFT + RANSAC 单应配准（统一 1600 px 宽）：

| 模式 | 照片宽度覆盖 | 照片高度覆盖 | 内点 | 中位重投影误差 |
|---|---:|---:|---:|---:|
| UHD | 59.43% | 50.11% | 304 | 0.292 px |
| 2560×1440 | **98.79%** | 83.34% | 511 | 0.311 px |

结论要说准：这是**接近照片全宽的 16:9 视角**，不是完整 3:2 open-gate（上下仍裁）。传感器
读出方式、跳行合并、混叠、滚动快门、动态范围均未确认，不能拿输出尺寸反推读出。

`scripts/res_25k.sh` 提供 `on|off|status`（`off` 即时回写原值，不用重启），但**不作为菜单
入口** —— 原菜单 checkbox 已自带 `off_res_UHD2K.sh`，保留它作诊断工具。

## 四、顺带改的菜单文案

`scripts/gui_res.NX500` 原来写「UHD映射为2K」「DC映射为UHD」，主语宾语不明，用户分不清是
改录制档还是改屏幕。现在统一成「**<档位>档 → <目标>（尺寸）**」，两组各三行按档位排。

## 五、两条否证（这版为什么不做 log / 10bit）

| 检查 | 结果 |
|---|---|
| 码流 `hvcC` | `profile_idc=1`（Main）/ `bitDepthLuma=8` / `4:2:0` / L5.1，无第二组 SPS |
| 全固件 352 MB 搜 `Main10` / `profile_idc` / `bit_depth_luma` | **0 命中** |
| `hvcC` 出现位置 | 仅 `mp4_parse_hvcC` —— 解析器，不是生成器 |
| `MOVIE_GAMMA_CONTROL`（0x760000） | 可写可逆，但 `IQ[180]` 恒为 `NORMAL/0`，画面无差异；app 侧 393 条 MOVIE 字符串**零 gamma** |

⇒ 8 bit 容器里做曲线重映射只能重分配 256 级码值，不产生动态范围。**log 在 NX500 上不可达**，
末端 3DLUT 重映射是唯一真实可用的色彩通道。

## 六、验证

| 项 | 结果 |
|---|---|
| 原 LUT 库回归（隔离挂载命名空间） | **46 PASS / 0 FAIL** |
| 未应用本次开机 LUT | 拒，rc 5 |
| 重复监视 | 拒，rc 4 |
| 非法槽 | 拒，rc 2 |
| 重复 `video on` | 幂等 |
| 跨 SSH 存活 / 显式 off / 总 off 停止 / 原厂登记表还原 | 通过 |
| 实解码 | `SAM_0322` 3840×2160/25 HEVC；`SAM_0323` 2560×1440/25，5.44 s；`SAM_0325` 2560×1440/25，8.085 s |
| 自动联动 | `SAM_0326`：不执行 `video on` 直接录，开停与完成中断正常，sample entry 为 2560×1440 |
| 编译 / 语法 / whitespace | 严格编译、`sh -n`、`git diff --check` 全过 |

## 七、安装与回退

与之前相同：解压到 SD 卡根 → 开机自动同步（`install.sh` 只覆盖不删）。本轮改动文件：

| 文件 | md5 |
|---|---|
| `scripts/lut.sh` | `f142046839c13ffbed0edf379e94f7d4` |
| `scripts/lut_video.sh` | `e6e93fce095e1d26037832a1757ff341` |
| `scripts/lut/nx_lutload.arm` | `d975e86da2dc2f543c1f51663b70dcea` |
| `scripts/res_25k.sh` | `f13deb28f5ac0f19496e2928b9f7b051` |
| `scripts/gui_res.NX500` | `ebb7ce80a9f8cf9d7d9f88246042e325` |

> `.arm` 是 zip 里的普通数据，解压到 SD 会丢可执行位；`install.sh` 对 `/opt/usr/nx-ks` 下
> 所有普通文件 `chmod +x` 兜底，漏了这一步的表现是 `lut.sh apply` 报
> `ERR nx_lutload.arm is missing`。
>
> 构建不可复现：`nx_lutload.arm` 每次重建 md5 都会变（`.strtab` 里的临时目标名），
> 判部署漂移要在 push 完立刻比，别拿昨天的哈希比今天重建的产物。

回退：`sh /opt/usr/nx-ks/lut.sh video off` 只停监视；`lut.sh off` 连表一起还原；
整包回退覆盖旧版 `scripts/` 即可，无固件改动、无分区写入。

## 八、证据

- [`docs/current/VIDEO_LUT_AND_2K_2026-11-07.md`](../current/VIDEO_LUT_AND_2K_2026-11-07.md) — 完整协议、实录与 FOV 配准
- [`docs/current/RES25K_TOGGLE_2026-11-07.md`](../current/RES25K_TOGGLE_2026-11-07.md) — 2.5K 开关与菜单纠错
- [`docs/current/VIDEO_10BIT_FEASIBILITY_2026-11-07.md`](../current/VIDEO_10BIT_FEASIBILITY_2026-11-07.md) — 10 bit 逐项证据
- [`docs/current/GAMMA_LOG_VERDICT_2026-11-07.md`](../current/GAMMA_LOG_VERDICT_2026-11-07.md) — 内置 gamma / log 判死
- [`docs/current/LUT_INPUT_CALIBRATION_2026-11-07.md`](../current/LUT_INPUT_CALIBRATION_2026-11-07.md) — 输入曲线标定协议
