# 内置 Gamma / Log 判定：1.12 上是预留位，未实现

日期：2026-11-07
相机：NX500 1.12（192.168.0.103），boot_id `dbb7e6ce-8b5e-4d2a-ba3e-bf5ea16d54bc`
证据根：`E:/NXWA/rea-evidence/20261107-gamma/`

## 结论

`USERDATA_MOVIE_GAMMA_CONTROL`（0x760000，三档 STANDARD / GAMMA_V / GAMMA_D）在 NX500 1.12 上是**可读写的预留参数位，没有任何消费者**。写它不改变 IQ[180]，不改变画面。这不是"没触发"，是固件里没有实现。

不要再在这个接口上投入实验。1.12 的录像画质重映射只能走 3DLUT（`lut.sh` / `lutmix.arm` 那条已通的路）。

## 四层证据

| 层 | 动作 | 结果 |
|---|---|---|
| UserData | `capdtm setusr MOVIE_GAMMA_CONTROL 7733248/7733249/7733250` 后 `getusr` | 三档均正确回读 `0x760000 / 0x760001 / 0x760002`，可逆 |
| IQ | 每次 `setusr` 后立即 `st cap iqr \| grep MOVIE_GAMMA` | `[180] eIQ_ID_MOVIE_GAMMA_MODE = eIQIF_MOVIE_GAMMA_NORMAL / 0`，**三次取值完全相同** |
| 画面 | SAM_0330(D) vs SAM_0331(STANDARD)，同机位同参数 | 均 4.84s / 121 帧 / 2560×1440 / 88.3Mbps；D 抽帧为正常对比度，无 flat/log 特征 |
| 动态范围 | 未测 | 不宣称任何 DR 收益 |

用户态对照（决定性）：`di-camera-app.c2.v2` 中含 `MOVIE` 的字符串 393 条，覆盖短片尺寸全套、画质（HQ/PRO/NORMAL）、AF 模式与响应速度、淡入淡出、风噪、麦克风、DIS、3D、Trim，甚至 `eUI_Y2R_MOVIE_HD_0_255 / 16_235 / 16_255`（对应 IQ[182] `eIQIF_MOVIE_LUMINANCE_LEVEL` 的三档）。**没有一条含 GAMMA / LOG / 曲线**。

同区间对照：IQ[182] 亮度范围有完整的 app 实现 + UI；IQ[180] gamma 模式没有。两者相邻、同在 `capture` 的 userdata 区，一个有落地一个没有。

## 静态排查与三条被推翻的判据

排查脚本留在 `rea-evidence/20261107-gamma/static/`（s1–s7b）。p7 换算：`VA = 0x80000000 + file_off - 0x1000`（锚点 file 0x585450 → VA 0x80584450）。

以下三条都**曾被当作证据，后经对照推翻**，不要重复：

1. **「`eIQIF_MOVIE_GAMMA_D` 出现在代码段 ⇒ 有功能分支」——错。**
   file 0x09ef88 那段（VA 0x8009df88）不是字面池，是 p7 内联在代码之后的**枚举名只读池**。同批还有 `eFOCUS_ZONE*`、`eMOVIE_AE_*`、`eSMARTRANGE_*` 等数百个枚举名。s6 局部全反汇编确认无任何 ldr 引用这些 slot。

2. **「USERDATA 名字表自身零引用 ⇒ 孤岛」——无效。**
   统计 91 条 `USERDATA_*` 名字，被引用次数全部 1~3，**没有一条是 0**。表通过 base+offset 访问，不存单项指针。所有项同构，判据无法区分 gamma 和正常功能。

3. **「p7 里 `0x760002` 零出现 ⇒ 无实现」——不能单独成立。**
   `0x760000` 严格 4 字节对齐也只有 2 处（0x807fbe68 是配置头区、0x809ef428 是图像数据里的字节巧合），`0x760001/2/3` 均为 0，且全镜像无 `movw/movt` 构造 0x76xxxx。但整族 USERDATA ID 都不以常量形式出现（运行期 base+index 计算），所以这条对任何 UserData 都成立，不具区分力。

真正有区分力的只有两条：**实测 IQ 恒 0** 与 **app 侧 MOVIE 家族零 gamma**。

## 复现

```sh
NXHOST=192.168.0.103 bash tools/nx-ssh.sh cmd '
  st cap capdtm getusr MOVIE_GAMMA_CONTROL
  st cap capdtm setusr MOVIE_GAMMA_CONTROL 7733250; sleep 1
  st cap capdtm getusr MOVIE_GAMMA_CONTROL
  st cap iqr 2>/dev/null | grep -a MOVIE_GAMMA
  st cap capdtm setusr MOVIE_GAMMA_CONTROL 7733248'
```

`st cap iqr` 只读：`set` / `get 180` 被当作无参调用忽略，183 项全表 dump。写 IQ 没有可用入口。

## 遗留

- 相机 RTC 比实际早一年（`date` 返回 2025-11-07），录制的 `creation_time` 同错。
- 卡上 11-07 的 MP4 已不在（用户侧删除）；本地两份副本 box 结构完整，可复核。
- GAMMA_V / GAMMA_D 可能是 NX1 同基线代码的残留（NX500 与 NX1 共用 p7），未验证。
