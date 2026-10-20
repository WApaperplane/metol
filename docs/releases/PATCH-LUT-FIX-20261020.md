# 补丁：LUT 通路修复（2026-10-20）

> **只给已装 2.88.0-nxwa.8 的人用。** 新装机请直接下载完整包 `NX-WA-2.88.0-nxwa.9.zip`，
> 它等于 v8 + 本补丁，不用先装 v8 再打补丁。

## 修两个 bug

| # | 症状 | 根因 |
|---|---|---|
| A | **取景器有滤镜，拍出来的照片没有** | Still 有两条互斥选表分支（p7 `0x80382B30`）：屏幕色彩**开启 → BV12 十二项**、关闭 → Still6 六项。v8 只改了 Still6 |
| B | **切到 AdobeRGB 后取景不生效** | View4 是四项表（`[0]` AdobeRGB+开 / `[1]` sRGB+开 / `[2]` AdobeRGB+关 / `[3]` sRGB+关），v8 只写了 `[1]/[3]` |

修法：apply 时 Still6（6 项）+ BV12（12 项）一起写，View4 四项一起写。**没有任何阈值、算法改动**，纯粹是覆盖不全。

顺带修掉一个静默半应用：`still-set` 首次要备份原厂六字到 `/mnt/mmc/nxwa_regtab_20261018/`，
目录不存在时备份失败 —— 此时槽和取景已经改好，只有成片那条没写。现在写前 `mkdir -p`，失败会明确报错。

## 只替换 4 个文件

| 文件 | 投到 | MD5 |
|---|---|---|
| `nx_regtabwrite.arm` | `/mnt/mmc/lut/`（若 `/opt/usr/nx-ks/lut/` 存在也放一份） | `a1db60c1aa2673951e8e4e52f4d5076b` |
| `nx_regtabwrite1.arm` | 同上（新版 `lut.sh` 不再调用它，保留兼容） | `a1db60c1aa2673951e8e4e52f4d5076b` |
| `lut.sh` | `/mnt/mmc/lut/lut.sh` **和** `/opt/usr/nx-ks/lut.sh` | `822da54c34d0001e91333085176bd70c` |
| `still_probe.sh` | `/mnt/mmc/lut/`（新增，只读诊断） | `529d4449e9619070be0a17ca2092d322` |

> ⚠️ 这台机器上 LUT 工具实际在 **`/mnt/mmc/lut/`**，不是 `/opt/usr/nx-ks/lut/`。
> 只往后者拷会得到 "No such file or directory"，而旧工具会继续被调用 —— 表现为"补丁装了但没用"。

```sh
cp /mnt/mmc/_xfer/nx_regtabwrite.arm  /mnt/mmc/lut/
cp /mnt/mmc/_xfer/nx_regtabwrite1.arm /mnt/mmc/lut/
cp /mnt/mmc/_xfer/lut.sh              /mnt/mmc/lut/lut.sh
cp /mnt/mmc/_xfer/lut.sh              /opt/usr/nx-ks/lut.sh
cp /mnt/mmc/_xfer/still_probe.sh      /mnt/mmc/lut/
chmod +x /mnt/mmc/lut/* /opt/usr/nx-ks/lut.sh
md5sum /mnt/mmc/lut/nx_regtabwrite.arm   # 期望 a1db60c1aa2673951e8e4e52f4d5076b
```

滤镜表（`looks/`）与面板（`nxui.arm`）**都没变**，不用动。

## 装完先诊断（只读）

```sh
sh /mnt/mmc/lut/still_probe.sh
```

输出三张登记表、当前「屏幕色彩 / 色彩空间 / 智能滤镜」设置、上次 apply 的日志，最后自动给结论：

| 结论行 | 含义 |
|---|---|
| `VIEW4 -> A18 : 4/4` + `STILL6 6/6` + `BV12 12/12` | 补齐了，可以拍照验收 |
| `BV12 -> A18 : 0/12` | 还是 v8 状态，补丁没生效（大概率工具拷错位置） |
| `STILL6 -> A18 : 0/6` | apply 的 still 段失败，看 `still.log` |

## 验收（三步，肉眼判）

```sh
/opt/usr/nx-ks/lut.sh off
/opt/usr/nx-ks/lut.sh apply mono_acros     # 悬殊的黑白表
# 半按一次快门 → 取景变黑白
# 拍一张       → 成片也应变黑白   ★ 唯一验收点
```

再补两项稳健性：

| 动作 | 期望 |
|---|---|
| 相机切 **AdobeRGB**（屏幕色彩任选）→ 半按 | 取景仍是黑白（v8 在这里会变回原厂） |
| 切回 **sRGB** → 半按 | 仍是黑白（确认写四项/还原四项没把 sRGB 两档弄丢） |
| `lut.sh off` → 半按 → 拍 | 回原厂 |

## 回退

```sh
/opt/usr/nx-ks/lut.sh off            # 先把登记表与槽还原到原厂
# 再覆盖回 v8 的两个文件（如果 10-19 装过，备份在 $B/nxui/backup-lut-20261019/）
```

不想手动回退就直接装完整包 `NX-WA-2.88.0-nxwa.9.zip` 覆盖，它已含本补丁。

## 界限

与完整包相同，见 [`NX-WA-2.88.0-nxwa.9.md`](NX-WA-2.88.0-nxwa.9.md) §4。最要紧的三条：

1. **sRGB 下颜色可信；AdobeRGB 只保证"生效"，颜色未标定**（表按 sRGB 坐标生成）。
2. **RAW（`.SRW`）不承诺被 LUT 烘焙**，本版只验证 JPEG。
3. **全部是内存写入，重启回原厂**；apply 之后必须半按一次快门才会装载。
