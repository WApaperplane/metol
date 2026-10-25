# LUT 色彩：文档索引与结论演化

2026-10-25 一天内做了四轮，其中**两个结论被后来的工作推翻**。按时间读容易读到错的东西，
所以这里给出阅读顺序和结论的演化关系。**冲突时以最后一份为准。**

## 阅读顺序

| 顺序 | 文档 | 作用 | 状态 |
|---|---|---|---|
| 1 | [LUT_CRCBY_ONDEVICE_FIX](LUT_CRCBY_ONDEVICE_FIX_2026-10-25.md) | 第一轮：发现 RGB 表被按 Cr,Cb,Y 消费，机端实拍确认并修 | ✅ 成立 |
| 2 | [LUT_COLORSPACE_REGRESSION_REVIEW](LUT_COLORSPACE_REGRESSION_REVIEW_2026-10-25.md) | 第一轮：编码回归的取证与 20 个设计方向 | ⚠️ 部分结论后被修正 |
| 3 | [LUT_PHYSICAL_FILM](LUT_PHYSICAL_FILM_2026-10-25.md) | 第二轮：三层根因 + 色域塌陷 + 物理链 | ⚠️ 边界处理后被 Codex 修正 |
| 4 | [LUT_STYLE_AUDIT_V2](LUT_STYLE_AUDIT_V2_2026-10-25.md) | Codex：独立复核 + 12 主方案 + 曲线实测 | ✅ 成立 |
| 5 | [LUT_DEDUP_AND_GAPFILL](LUT_DEDUP_AND_GAPFILL_2026-10-25.md) | 第三轮：同质化审计、清理、12 张补空白 | ❌ **六轴数据作废** |
| 6 | [LUT_BRAND_LOOKS](LUT_BRAND_LOOKS_2026-10-25.md) | 第四轮：修底层 bug、7 张品牌色系 | ✅ **以本文为准** |
| 7 | [COLOR_DEF](COLOR_DEF_2026-10-25.md) | 配色定义参考 | ✅ |

## 结论演化

**三重根因（成立）**：偏色不是参数问题，是编码 / 色域 / 模型三层独立缺陷叠加。
- 编码：RGB 表按 Cr,Cb,Y 读 —— 已修
- 色域：17³ 网格 80.5% 在 sRGB 外，Y=0 与 Y=255 平面合法率各仅 0.3% —— 已修
- 模型：加性感知调色必然跑品红（品红 = R、B 同抬，而真实染料是乘性密度只降单通道）—— 已换

**色域处理（被修正）**：第二轮我用"沿灰轴投影"处理越界格点。Codex 在 33³ 合法 RGB 上
实测其最大通道误差 **41.018 LSB**，改用"边界单元线性外推"后为 **0.886**（与直接恒等
同水平）。**边界处理以 Codex 的方法为准**；物理链本身（光谱 H&D + 染料密度）仍成立。

**库的形状（作废）**：第三轮报"warmth 只有 0.4~11.8、没有偏冷的表、绿偏 −66.7~−33.6"。
这些都算在错误的色彩空间里 —— `rgb_to_lab` 的 sRGB→XYZ 矩阵乘反了，中性灰算出 a\*=−54.5、
纯白 L\*=107。正确值是 warmth −2.3~11.0、绿-品红轴只有 ±2。**以 LUT_BRAND_LOOKS 第二节为准。**

**分离色调（作废）**：第三轮报"分离幅度都很小"，其实是 `shadow_tint` 与 `high_tint`
在 L\*=0/100 处读 b\*，而 `grade()` 的两端保护把染色淡出为零，两个指标同时退化成同一个数。
已改为在输入 45/128/210 三点读。

**清理（方向成立、数值待复核）**：错空间是连续单调变换，距离排序大体保留，所以
"90 张只有 32 种可区分外观、清掉 27 张"的结论方向可用；但绝对阈值要在正确空间里复核。
正确空间下重算 75 张，最近合法对为 `mono_hard`/`style_noir` **1.361**，仍低于 1.5 门槛。

## 数据在哪

| 内容 | 位置 |
|---|---|
| LUT 本体 | `looks/*.bin`（`v2_` = Codex 12 主方案，`gap_` = 补空白 12，`brand_` = 品牌 7） |
| 编码声明 | `looks/encoding.json`（每表色彩空间 + SHA256） |
| 配方 | `tools/lutgen/style_profiles.json`、`gap_profiles.py`、`brand_profiles.py` 内的 PROFILES |
| 度量数据 | `tools/lutgen/audit_out/`（运行产物，不入库） |

## 怎么复现

```bash
# 全部在 tools/lutgen 下执行
python colour_metrics.py --help        # 九轴度量
python coverage_audit.py               # 覆盖与空白
python similarity_audit.py             # ΔE00 距离矩阵
python cluster_audit.py                # 完整链接聚类
python dedup_plan.py                   # 去重清单（加 --move 才会归档）
python brand_profiles.py               # 7 张品牌方案 + 特征验收
python gap_profiles.py                 # 12 张补空白 + 双重门槛判定
```

依赖 `E:/NXWA/.venv`（numpy / scipy / colour-science / spectral_film_lut）。

## 一条纪律

**任何色彩结论在做完以下两件事之前都不算数**：
1. 用已知色块验证色彩空间（白 → L\*100/a\*0，中性灰 → a\*0）
2. 用至少两个独立指标交叉验证（色相与彩度分开量，不能用一个数代替）

这一天的两次返工都是因为漏了这两条。
