# AdobeRGB 下取景不生效：View4 只写了两个项（2026-10-20）

> **背景**：[Still 通路审计](STILL_PATH_AUDIT_2026-10-20.md) 修完 BV12 后，还留一个缺口 ——
> v8 的 apply 只写 `View4[1]`/`[3]`，而 AdobeRGB 走的是 `[0]`/`[2]`。
> **结论**：View4 是**一张四项表**，出口由 OrderSheet（色彩空间 × 屏幕色彩）选；写全四项才与用户设置无关。
> **状态**：离线修复完成（`view-set` / `view-restore`），**未上机验证**。

---

## 1. 映射：四项各对应哪种组合

`FUN_0009a3e8(fmt, cbcr)`，其中 `fmt = 后端+0x22`（= AdobeRGB 位）、`cbcr = +0x21`（= 屏幕色彩位）。
QEMU 实跑四组参数（`3DLUT_APPLY_PATHS_2026-10-08.md §3.1`），与 `view_policy.json` 的 `view_index` 逐条对齐：

| `+0x22` | `+0x21` | 设置组合 | 返回表 | View4 项 |
|---:|---:|---|---|---:|
| 0 | 0 | sRGB + 屏幕色彩关 | `0x81115200` A17 | **3** |
| 0 | 1 | sRGB + 屏幕色彩开 | `0x81101E00` A13 | **1** |
| 1 | 0 | AdobeRGB + 屏幕色彩关 | `0x81106B00` A14 | **2** |
| 1 | 1 | AdobeRGB + 屏幕色彩开 | `0x810FD100` A12 | **0** |

v8 写了 `[1]`、`[3]`（sRGB 两档）⇒ **AdobeRGB 两种组合都还指原厂表**，取景不变。

## 2. Still 侧不用再动

`FUN_0009a3c8(ctx, param_2=+0x22, param_3=+0x21)` 只在 `param_3 == 1` 时才分叉到 BV12；
`param_2`（AdobeRGB 位）只影响**同一分支内选第几项**，不换表：

| 分支 | 分支内按 `param_2` 选 |
|---|---|
| `+0x21 == 1` → BV12（12 项） | index 由 BV 档算，与 `+0x22` 无关 |
| 否则 → Still6（6 项） | `+0x22 == 1` 取 `0x81110500`/`0x8110B800`/`0x81106B00`，否则取 `0x8111EC00`/`0x81115200`/`0x81119F00` |

上一轮已把 **Still6 6 项 + BV12 12 项全指工作槽**，所以 **AdobeRGB 下成片自动跟随**，无需额外改动。

## 3. 修复

| 件 | 改动 |
|---|---|
| `nx_regtabwrite.c` | 新增 `do_view_all(action, slot)`：一次映射、一次快照，写或还原**四项**；`view-set <slot>` / `view-restore` / `view-status`。新增 `VIEW0_OFF`/`VIEW2_OFF`/`VAL_A14`。 |
| `scripts/lut.sh` | apply 改调 `view-set "$SLOT"`（替代 `patch` + `patch1` 两段）；off 改调 `view-restore`（替代 `restore` + `patch1`）。`nx_regtabwrite1.arm` 不再被引用（文件保留）。 |
| `test_regtabwrite.py` | 14/14 PASS，新增「四项偏移」「四项由同一循环写入」断言 |

产物：`nx_regtabwrite.arm` md5 **`a1db60c1aa2673951e8e4e52f4d5076b`**，13,100 B。

`view-restore` 是无条件写回四个原厂字（`A12/A13/A14/A17`），幂等，不需要额外备份文件 —— View4 的原厂值是镜像常量，不会像槽内容那样被我们改。

## 4. 需要注意：生效 ≠ 颜色正确

AdobeRGB 下 LUT **会生效**，但成片的颜色**不一定和 sRGB 下一致**：

- JPEG 会带 AdobeRGB profile，看图软件按 AdobeRGB 解释；而我们的表按 sRGB 坐标生成（`cube2lut` 轴序已由 10-19 的探针确认为 R/G/B，中性点 128）。
- 也就是说：`sRGB 下好看` ≠ `AdobeRGB 下好看`。这不是登记表的问题，是表本身的坐标前提。
- 未做色卡验收前，**不建议把 AdobeRGB 当成「另一个可用的输出空间」** —— 只把它当成「取景也不会掉回原厂」的兜底。

要真在 AdobeRGB 下出片，需要单独一批按 AdobeRGB 坐标标定的表，或让用户在相机里固定 sRGB。

## 5. 上机验收

```sh
sh /opt/usr/nx-ks/lut.sh off
sh /opt/usr/nx-ks/lut.sh apply mono_acros     # 悬殊的黑白表
/opt/usr/nx-ks/lut/nx_regtabwrite.arm view-status
# 期望：四项全部 0x81119f00
```

| # | 动作 | 判据 |
|---|---|---|
| 1 | `view-status` | 四项全 `0x81119f00` |
| 2 | 相机设为 AdobeRGB（屏幕色彩任选）→ 半按 | ★ 取景变黑白（v8 在这是不变的） |
| 3 | 拍一张 | 成片也变黑白（Still 侧上一轮已覆盖） |
| 4 | `lut.sh off` → 半按 | 取景回原厂；`view-status` 四项回 `A12/A13/A14/A17` |
| 5 | 切回 sRGB → 半按 | 仍是黑白（`[1]`/`[3]` 未被 off 误伤） |

第 5 步防回归：写四项/还原四项不能把 sRGB 两档弄丢。

## 6. 边界

1. 未上机。`view-set` 一次改 4 个 word，`stray` 检查覆盖整个 16 KiB 窗口，理论上只会动这 16 字节，但**实机未验**。
2. `mode_byte == 14` 时 OLED 位被忽略（`view_policy.json`：mode 14 下 OLED 开关不影响 OrderSheet），此时仍映射到 `[3]`/`[2]`，已覆盖。
3. 智能滤镜枚举 14–18 另走动态路径（OrderSheet 4–8），v8/v9 **都不覆盖** —— 那是 `FUN_0009a408` 的 24 档池，需要另一套改法。
4. 相机内 JPEG 是否在 AdobeRGB 下仍经过 3D LUT（而不是在 LUT 之后再做空间转换）**未验**；若顺序相反，颜色差异会更大。

---

*2026-10-20 · 离线 · 姊妹文档 `STILL_PATH_AUDIT_2026-10-20.md` · 证据 `view_policy.json`、`3DLUT_APPLY_PATHS_2026-10-08.md §3.1`、`P7_3DLUT_PATHS_2026-10-07.md §2.1`*
