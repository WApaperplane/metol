# 外部经典 LUT 导入（G'MIC 公开 CLUT → 原生 Cr,Cb,Y）2026-10-25

## 结论速览

| 项 | 结果 |
|---|---|
| 来源 | G'MIC colour presets（`gmic.eu/color_presets`），CC-BY-SA，327 张 |
| 解码 | 512² Hald PNG = 64³ 立方，**红通道最快** |
| 导出 | `compile_uniform_rgb` → 17³ `{Cr,Cb,Y,0}`，19712B/张 |
| 落盘 | 13 张同名替换 + 30 张新增，`looks/` 82 → 112 |
| 体检 | 新增 30 张中 23 OK / 7 WARN / 0 新增 BAD；替换 13 张里仅 `fuji_velvia50` 触 BAD 阈值 |
| 剔除 | `lomo_redscale100`、`polaroid_timezero`（照片复核过火，留在 `webstage/`） |

原表备份 `E:/NXWA/_looks_before_web_20261025/`；候选全量在 `tools/lutgen/webstage/`（59 张）。

## 一、为什么换掉自建表

自建表走的是物理模型 + 风格目标反推（`film_physics.py` / `style_profiles.json`），能保证不越界、
不失真，但**没有原机受控样本**，片种间的差异被模型压小（前一轮已确认旧 13 表最近多对 ΔE00 1.4–1.7，
用户判为同质化）。外部 CLUT 是别人拿真胶片/官方色彩科学做的成品，片种指纹是现成的。

代价也很清楚：外部表的 S 曲线按「平坦输入」设计，压到已显示参考的 JPEG 上，暗部更容易压死。
`crush_pct` 因此普遍比自建表高——这是交换不是纯增益，见第四节。

## 二、解码：两个坑

### 坑 1：G'MIC 的 Hald PNG 不是教科书布局

教科书 Hald 是 64×64 tile、tile 索引→B、x→R、y→G。按此解，与 G'MIC 自己的 13³ `.cube`
最大差 **250/255**——完全对不上。

实测（沿 x 找 R 的回归点，间距 64；沿 y 无回归点）确定真实映射为
`idx = y*512 + x`，tile 与通道的对应需另定。

### 坑 2：拿 `.cube` 互校会给出「错的正确答案」

用 12 种候选（2 种数组序 × 6 种通道排列）扫，最佳是
`r = idx//4096, g = (idx//64)%64, b = idx%64`，对 13³ `.cube` 均差 **2.2/255**、最大 27.8/255
——残差量级正好是 13³ 重采样应有的，看起来完全成立。

**但它是错的。** G'MIC 的 PNG 与 `.cube` 用同一套（蓝最快的）顺序存储，两者互校时 R/B 同时
被换掉、误差相互抵消。用它导出的表，Portra 400 把 (208,48,48) 送成 (113,80,227)：红变蓝。

暴露路径只有两条，都不在解码环节：

1. `audit.py` 的 `hue_err`：全部彩色表 ~145°，而自建表是 5–12°。单看 jump/dr/black 全正常。
2. 摄影常识：Portra 400 必须把红送成红。

修正后 `r = idx%64`（红最快）、`g = (idx//64)%64`、`b = idx//4096`，Portra 400 给
(208,48,48)→(251,65,23)、(48,64,208)→(107,95,225)，六主色全部落回合理区，`hue_err` 降到 13–32°。

> 教训：**互相一致的两种编码不能互为基准**。R/B 互换是自洽变换，任何用同源数据做的回归都会
> 把它吸收掉。必须有外部锚点（真实照片的方向性，或原厂槽这类独立来源）。

### 用 PNG 还是 `.cube`

`.cube` 是 13³（G'MIC 统一降采样过），PNG 是 64³。目标网格 17³，从 13³ 三线性上采会先丢信息
再补形状，陡的高光肩部尤其吃亏。所以走 PNG。13³ 的 `.cube` 仅用于布局反推的交叉验证。

## 三、导入清单

### 同名替换（13 张，文件名不变 ⇒ NXUI 菜单无需改动）

`kodak_portra400` `kodak_ektar100` `fuji_400h` `fuji_superia400` `agfa_ultra100`
`fuji_velvia50` `fuji_provia100f` `fuji_astia100f` `kodak_kchrome25` `kodak_kchrome64`
`slide_precisa100` `mono_acros` `fuji_classicchrome`

`fuji_classicchrome` 取自 `fujixtransiii`（富士自家的机内色彩科学），比其它来源更接近原厂意图。

### 新增（30 张）

| 家族 | 表 |
|---|---|
| 电影印片 | `kodak_2383` `kodak_2393` `fuji_3510` `fuji_3513` |
| 彩色负片 | `kodak_portra160` `kodak_portra800` `fuji_160c` `fuji_800z` `fuji_superia100` `agfa_vista200` `kodak_elitecolor200` |
| 反转片 | `fuji_velvia100` `kodak_kchrome200` `kodak_ektachrome100` `lomo_xpro_slide200` |
| 黑白 | `mono_trix400` `mono_tmax100` `mono_hp5` `mono_delta100` `mono_delta3200` `mono_fp4` `mono_panf50` `mono_hie_infra` |
| 一次成像 | `polaroid_669` `polaroid_690` `fuji_fp100c` `fuji_fp3000b` |
| 富士机内模拟 | `fuji_pro_neg_hi` `fuji_pro_neg_std` `fuji_xtrans_provia` |

印片四张是这批里最「经典」的：2383/2393 是柯达院线标准正片，3510/3513 是富士对应型号，
现代所有 film-look 调色都从它们起手。注意它们本来是 log→print 的变换，G'MIC 版本已改成
可直接吃显示参考图像，但反差仍然很重（`kodak_2383` jump 4.25、`kodak_2393` 4.31）。

## 四、体检与照片复核

`audit.py --dir webstage`（59 张）→ 41 OK / 10 WARN / 8 BAD。

8 张 BAD 逐张用样片（`SAM_0143` 红墙、`SAM_0026` 人像）复核：

| 表 | 触发 | 复核结论 |
|---|---|---|
| `agfa_ultra100` | crush 16.7 | 正常，浓片本色，无断裂 |
| `agfa_vista200` | crush 12.1 | 正常 |
| `fuji_velvia50` | crush 8.4 | 正常，Velvia 就该压暗部 |
| `kodak_elitechrome200` | crush 8.2 | 正常，偏粉属风格 |
| `kodak_elitecolor400` | crush 8.2 | 正常 |
| `fuji_xtrans_sepia` | gray_gap 55 | 设计意图（棕调） |
| `lomo_redscale100` | crush 8.6 + 灰轴 31 | **剔除**：色相整体乱转 |
| `polaroid_timezero` | 抬黑 102、dr 124 | **剔除**：是滤镜不像 look |

结论：`crush_pct` / `gray_gap` 的阈值（3%/8%、30/46）是对自建表校准的，对「浓片」和「过期片」
系统性偏高。这类判废**必须配照片复核**，不能只按格点数值下架——否则会把 Velvia 50 一起删掉。

## 五、复现

```
cd tools/lutgen
python web_import.py --selftest      # identity 64³ -> 17³，表体必须 0 差
python web_import.py --stage         # 下载 + 转换，落 webstage/
python audit.py --dir webstage       # 结构体检
python preview_photos.py <照片> out.png --dir webstage <表名...>
python web_import.py --apply         # 备份原表并写入 looks/
```

`--apply` 只写 `MANIFEST` 里 `action='replace'` 的项与 `DEPLOY_ADD` 白名单；
其余候选留在 `webstage/`，随时可单独 `--only` 或加进白名单。

## 六、收敛：112 → 90，并已上机

外部表并入后库到 112 张，菜单过长。用 `tools/lutgen/trim_plan.py` 归档 22 张（不删除，
移到 `E:/NXWA/_looks_trim_20261025/`），依据两类：

- **同一片种两份文件**：`ektar100`、`film_portra`、`film_superia`、`film_expired`，以及 11 张
  同片种已有公开来源版本而留下会造成两个近同名项的 `v2_*`。
- **人眼分辨不出的成对**（median dE00 < 1.5）：`fuji_3513`→3510、`kodak_2393`→2383、
  `mono_delta3200`→HP5、`mono_fp4`→Delta100、`style_noir`→mono_hard、`style_bleach`→pentax_bleach。

**没有用自动聚类定案**。试过按项目门槛 3.112 做完整链接聚类 + "名字短优先"，结果是
`mono_fp4` 顶掉 Tri-X、`fuji_160c` 顶掉 Portra 160、`cool_arctic` 顶掉 Eterna——距离矩阵只能
回答"像不像"，回答不了"哪张该活"。所以清单逐条写死并附理由，聚类只用于查漏。

推送结果：机端 61 → 90 张，删除 13 张已归档表，**90 张全量 MD5 与本地一致**。
`encoding.json` 清理了 22 条悬挂登记。

## 七、未做

- 未 commit。改动涉及 `looks/`（60 个二进制）、`scripts/lut/cube2lut.arm`、`test_server/lutpipe/cube2lut.c`、
  三份 docs 与两个新工具。
- 输入曝光曲线仍未做（上一轮遗留），所以这批表和自建表一样是「显示参考输入」假设下的结果。
- 相机 IP 已变为 192.168.0.102（原先记录的是 .106）。
