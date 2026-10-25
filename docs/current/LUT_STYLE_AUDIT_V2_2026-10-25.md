# NX500 LUT 独立复核、12主方案与曲线实测

2026-10-25。按用户“先审核修正，再测曲线”的要求，冻结旧13物理表，保留先前48表和未提交工作，修复边界编码及检测方法，另建12个方向明确的创意方案。[物理批次更正](LUT_PHYSICAL_FILM_2026-10-25.md)撤回旧版未经证实的因果解释。

## 编码和同质化

格式为17³、Cr/Cb/Y/0、Cr最快、灰色度128、槽19712字节。在33³=35937个合法RGB输入上测试完整插值链：

| 恒等表编译方法 | 最大通道误差（8bit） |
|---|---:|
| 直接原生恒等 | 0.886 |
| RGB逐通道裁切 | 7.597 |
| WorkBuddy灰轴投影 | 41.018 |
| 新边界单元线性外推 | 0.886 |

0.886的基线来自极端色度255.5被工作转换器裁成255；新编译器4913节点恒等字节完全保留。越界比例不能代替合法输入验证；仿射保持也不保证任意非线性外推完美。

本轮扩大验证时发现：固定Lab明度压色度在高亮黄色附近造成急剧漂白，原生插值可把暖黄推成偏品红。最终设计改为输出线性RGB共同平移负最小值、共同缩放超界最大值，保留通道排序及通道差比例，允许L*变化；这与原生输入网格投影不同。12表×35937个合法RGB点，最大ΔE00从初稿最高19.40降到4.386，P99各表均≤2.113，P95各表均≤1.434。原初稿保存在`styles_selected/`和`dense_native_validation_before.json`，最终可交付为`styles_final/`；不得把初稿对照误标成最终版本。

旧13表逐亮度去偏色、统一端点、弱曲线压小纸白/片基冷暖/反差。72探针定义=12色相×2饱和×3亮度，中位ΔE00：

| 组合 | 旧物理批次 | 新主方案 |
|---|---:|---:|
| Portra400 / Kodak Gold200 | 1.662 | 3.629 |
| Superia400 / Agfa Vista100 | 1.428 | 相似候选不进入主包 |
| Pentax Gold / Kodak Gold | — | 4.542 |
| Classic Chrome / Eterna | — | 7.137 |

18本地候选仅选12主方案，最终最近一对中位ΔE00=3.112（Velvia/Canon Landscape，固定L*后色度差仅0.988，仍同属浓艳蓝绿家族）。这是项目去重门槛，不是普适可见阈值或胶片还原度证明；不能保证同一小场景下每对都明显不同。`style_separation.json`另存固定L*后的色相/色度差，避免把明度变化当作全部色彩差异。

## 12主方案

| 文件（均加v2_前缀） | 目标 |
|---|---|
| pentax_gold | 蓝影金光，中灰收敛，与柯达暖黄分开 |
| pentax_satobi | 褪红、暗黄、青蓝，柔和旧色 |
| fuji_classicchrome | 低彩、冷影、橄榄绿、压品红 |
| fuji_velvia50 | 强反差、浓绿深蓝，控制暖色 |
| fuji_eterna | 柔和高光、开阔暗部、低彩电影方向 |
| kodak_portra400 | 柔人像影调、温暖肤色、缓和绿 |
| kodak_gold200 | 暖黄日常，明亮黄色 |
| kodak_kchrome64 | 砖红、赭黄、深蓝、较深黑位 |
| ricoh_bleach | 低彩硬调，区别于黑白 |
| canon_landscape | 蓝绿通透、白色干净 |
| polaroid600 | 奶油纸白、抬黑、柔色；暖纸白属设计 |
| ilford_hp5 | 中性黑白、中间调层次；不模拟颗粒 |

依据：[宾得Custom Image](https://www.ricoh-imaging.co.jp/english/products/custom_image/)、[富士Classic Chrome](https://www.fujifilm-x.com/global/products/film-simulation/classic-chrome/)、[富士Film Simulation](https://www.fujifilm-x.com/en-us/products/film-simulation/)、[佳能Picture Style](https://global.canon/en/imaging/picturestyle/editor/understanding.html)、[理光GR支持](https://www.ricoh-imaging.co.jp/english/support/qa/gr-3/)、[HP5 PLUS](https://www.ilfordphoto.com/hp5-plus-35mm/)。逐表来源与配方在`tools/lutgen/style_profiles.json`。光谱参考库：[上游项目](https://github.com/JanLohse/spectral_film_lut)。

这些是可复现的参考风格设计，非原厂映射或真实胶片逐款实测复制。Portra等肤色目标尚缺真人受控样本；柜子/玩偶/白墙不能验收天空、植物、不同肤色、日光和混光。

## 实拍与验证

初稿12主表及恒等/灰度2控制逐一实拍，SAM_0189—0202。最终版本部署后另行重拍，SAM_0244—0255，文件名`final_v2_*.JPG`，EXIF/哈希在`style_captures.jsonl`，`styles_actual_12.png`只使用最终版本；旧图另存`styles_initial_12.png`。6480×4320 JPEG，M档、1/80s、F4、ISO1600、固定5500K、手动WB（EXIF=1）、PW中性。对照图无后期套表。特征配准确认轻微构图位移，960像素宽下最大4.47像素（约0.47%）；接触表用于视觉比较，不做逐像素色差统计。原图在`E:/NXWA/_color_styles_20261025/device/`。

22项测试覆盖仿射恒等/黑白保持、编码哈希防误读、风格方向、灰阶单调、有效RGB近似、主包去重、光谱构建回归，新增35937点密集边界与极亮黄色防品红回归。最终72彩色探针P95 ΔE00最大约1.715；灰轴L*最小相邻增量为正。检查不保证所有颜色/曝光/光源均无瑕疵。

## 证据和复现

根目录`E:/NXWA/_color_styles_20261025/`：`before/`冻结旧13表和源码；`audit_physical.json`、`style_separation.json`、`dense_native_validation.json`记录数值；`styles_final/`为最终12主表；`styles/`与`styles_selected/`仅保留早期候选；`curve/`为单独曲线测试。原工作区未提交改动没有重置。

```powershell
E:/NXWA/.venv/Scripts/python.exe tools/lutgen/style_collection.py --out E:/NXWA/_color_styles_20261025/rebuild
# 在tools/lutgen目录执行：
E:/NXWA/.venv/Scripts/python.exe -m unittest test_native_codec test_style_collection test_film_physics
```

机端进入本轮时61表、工作槽、参数和脚本备份为`/mnt/mmc/lut/review_20261025_styles_v2/`；本地镜像`device/device_before.tar`。exFAT部署须完整目录切换，核对目录项和哈希，避免单文件临时重命名覆盖造成重复项。曲线与最终部署实测追加如下。

## 输出端测量与输入曲线延期

常量LUT的21档灰阶输出均与JPEG解码RGB逐码一致，最大差0、采样区空间标准差0；8个Y128/色度±24探针与BT.601全范围预测RMSE0.329，优于709全范围3.946和601限幅4.454。该配置未测出LUT后额外灰阶曲线；这不证明LUT输入等于sRGB或场景线性光。

输入端曝光包围未形成有效数据。用户明确要求“先完成LUT修正，曝光曲线稍后测”，因此暂缓；无完整gamma/传感器反演结论。详细方法、失败样本排除与设置恢复见`E:/NXWA/_color_styles_20261025/CURVE_OUTPUT_REPORT.md`。

## 最终部署

相机日常列表为原48表+最终12个`v2_`主方案，共60张。原48张MD5逐一相同，无新增已删除的旧表。旧13个`phys_`、初稿12表和所有控制表完整保存在机端备份根`looks_full_tested104/`，没有单文件覆盖重命名。备份根中的`looks_before/`另保留进入本轮时61表。

完整60表目录切换前后均核验MD5，无重复名；新表SHA256、配方和编码标识在`styles_final/manifest.json`及`encoding.json`，部署清单`device/deployment.json`。最终恢复AF_AUTO、自动WB（保存值与运行值都恢复）、M1/80/F4/ISO1600，PW中性，预览展示`v2_pentax_gold`。没有重启相机App或刷新固件。
