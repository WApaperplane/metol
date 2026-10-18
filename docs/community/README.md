# 对外发布素材（2026-10-18）

针对本次「运行态换表闭环 + 机身 cube2lut + NXUI 焦点修复」的对外传播素材。

| 文件 | 用途 | 平台 |
|---|---|---|
| [`REDDIT_POST_EN.md`](REDDIT_POST_EN.md) | 完整英文技术贴（含 TL;DR、数据表、未验证项、评论区预案） | r/SamsungNX · r/cameras · r/ReverseEngineering |
| [`FORUM_POST_ZH.md`](FORUM_POST_ZH.md) | 中文长文（同内容，中文读者关心的三条前置） | 色影无忌 · 蜂鸟 · 知乎 · V2EX |
| [`VIDEO_SCRIPT_ZH.md`](VIDEO_SCRIPT_ZH.md) | 45s 主版 + 22s 快剪 + 小红书图文版 + 拍摄清单 | 抖音 · 小红书 |
| [`assets/poster_overview.html`](assets/poster_overview.html) | **整体介绍海报**（1080×1780，NXUI 界面设计 + 六项功能 + 数字条，含实机面板截图） | 长图 · 仓库介绍 · 社群置顶 |
| [`assets/poster_4byte.html`](assets/poster_4byte.html) | **单点海报**（1080×1440，只讲「4 字节」） | 小红书首图 · 微博 · 朋友圈 |

## 一句话（所有平台通用）

> 不刷固件，改 1 个 4 字节的登记表项 + 写 19,712 字节进空闲槽 + 半按一次快门 —— 取景器就换成任意 3D LUT。取景和成片还是两条独立链路。

## 下载 / 引用链接

| 用途 | 链接 |
|---|---|
| 本版 Release | https://github.com/WApaperplane/metol/releases/tag/v2.88.0-nxwa.6 |
| 包直链 | `.../releases/download/v2.88.0-nxwa.6/NX-WA-2.88.0-nxwa.6.zip` |
| 校验 | md5 `1f8cb2c85d79127347c1c42d7d6510e3`（7,751,707 B） |
| 仓库 | https://github.com/WApaperplane/metol |

> 论坛贴里优先给 Release 链接而不是 zip 直链 —— 直链会随版本失效，Release 页永远指向当前版。

## 三条硬卖点（按可信度排序）

1. **4 字节换表** —— 可复现，有机器判据（`load_addr` 实测三段跳变）。
2. **取景正常、成片负片** —— 一张照片就能证明的负对照，视觉冲击最强。
3. **`.cube` 丢 SD 卡，机上转换** —— 对普通用户门槛最低，且 ARM 定点输出与 PC 浮点逐字节相同。

## 必须一起说的边界（否则会被打脸）

- 全程内存操作，**断电即回原状**；「开机即生效」仍需改固件镜像。
- 半按一定触发重载；切档/休眠是否触发**未测**。
- 全部在 NX500 1.12 + 特定 p7 版本验证；NX1 同代但**未验**，NX300 是 DRIMe4 不要假设。
- 前提是机器已装 NX-KS2（有 telnet/FTP root），不是原厂一键包。

## 素材位置

| 素材 | 路径 | 状态 |
|---|---|---|
| LUT 面板截图 | `raw8/gates/lut/regtab_2026-10-18/lut_ui2.png` | 已有（*.png 被 gitignore，仅本地） |
| 负片成片 | `raw8/gates/lut/regtab_2026-10-18/photos/SAM_0044.JPG` | 已有（7.7 MB，需导 2048px 版） |
| 取景器前后对比 | — | **需现拍** |
| 三次连切 | — | **需现拍** |
| `.cube` 拖卡 | — | **需现拍** |

## 技术依据（发帖被追问时引用）

| 文档 | 内容 |
|---|---|
| `docs/current/LUT_RETARGET_LIVE_2026-10-18.md` | 实验链、数据表、可逆性核验、未验清单 |
| `docs/current/LUT_REGTAB_READ_2026-10-18.md` | Cfg 位定义、登记表回读 22/22 |
| `docs/current/CUBE2LUT_2026-10-18.md` | 机身转换器、格式契约、三份 cube 逐字节对照 |
| `docs/current/LUT_UI_2026-10-18.md` | 机上 UI 模式、三个安全设计 |
| `docs/current/NXUI_FOCUS_HANDOFF_2026-10-18.md` | X11 焦点不归还缺陷与回归判据 |
