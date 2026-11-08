# NX-WA 2.88.0-nxwa.14 — TC 曲线 + LUT 输入域重生成

发布日期：2026-11-08
性质：功能版本。**录像 tone 曲线（TC）可切换**，同时把 34 张 LUT 按实测相机曲线重生成。

## 一句话

`实用功能 → TC 曲线` 里有四条曲线（原厂 / Log / Flat / 高对比），点一下即生效；
LUT 库里有 34 张表按「相机真实响应」重新生成，暗部不再被二次压缩。

## 一、TC 曲线（新增）

p7 内部有一张 19 节点 tone 曲线表，作用在录像链路里、3DLUT 之前。
它不是 `MOVIE_GAMMA_CONTROL`（那个接口在 NX500 1.12 上没有消费者），是数据表本身。

```text
Param0 = read32(0x817dccbc)
Gamma  = read32(Param0 + 0x170)
dirty  = Gamma + 4
Y[i]   = Gamma + 0xe8c + 4i        i = 0..18
源表    = 0x8062f71c + 4i          重启即回原厂
```

写 19 个 Y → 置 dirty `0xffffffff` → ISP 在 <50 ms 内自行消费（**不需要按键**）→ 回读缓存 19 点确认。

入口：

```sh
sh /opt/usr/nx-ks/tc.sh status          # 当前是否原厂、Y[9]、描述符
sh /opt/usr/nx-ks/tc.sh list            # 曲线库
sh /opt/usr/nx-ks/tc.sh set log|flat|hc # 或指向任意 .tcy
sh /opt/usr/nx-ks/tc.sh off             # 恢复原厂
```

菜单：`实用功能 → TC 曲线`（原厂 / Log / Flat / 高对比）。

安全：地址链每次重解析、签名校验、目录锁、录像检测、只允许空闲预览模式；
写入后逐项回读，任何失败自动写回原厂并再次确认。

实机证据：同一段 A/B 录像，全画面 Y mean **63.26 → 98.83**，
像素映射 4→17 / 52→102 / 180→186 / 220→213，是曲线形状不是曝光漂移。

## 二、LUT 按实测输入域重生成

原先所有表都按 **sRGB 输入**生成（`cube_import.py` 的既有假设）。
实测相机响应斜率 `log2(码值)/EV = 0.809`，sRGB 参考 0.45，差 1.8 倍 ——
这个假设不成立，暗部会被二次压缩。

重生成在 64³ RGB 域做输入轴重映射，再转 17³ CrCbY；三通道同时映射，
不是对成品表重采样（后者只改亮度轴，会出现色彩与亮度不匹配）。

| 来源 | 数量 | 状态 |
|---|---:|---|
| G'MIC Hald（`web_regen.py`） | 25 | 已替换 |
| `films.json` 配方（`gen_luts.py --input-regen`） | 9 | 已替换 |
| 无生成器可追溯（brand/gap/warm/samsung/mono/sony 等） | 34 | **未动** |

效果：暗部抬升、中段接近、高光持平，各表自身形状保留。

## 三、边界

**已证**：TC 表可写、可刷新、进入 HEVC、可逆、重启自动回原厂；LUT 重生成方向已上机确认。

**未证**：

- 整体动态范围净增益。局部暗部有改善倾向，严格门槛后区间含零
- TC 的绝对锚点。h 用「中灰锚定」（相机 128 ↔ sRGB 128），换成白点锚定会整体差约 35 码，
  需要一张 18% 灰卡才能定
- TC 与 3DLUT 的叠加关系。TC 会移动 3DLUT 的输入域，两者同时改需重新标定
- 录像中切曲线的稳定性

不要把这些表当成标准 Log 素材：容器仍是 8bit 4:2:0，没有 10bit 地基。

## 四、部署与回退

- 曲线库：`/mnt/mmc/scripts/tc/*.tcy`，与 `/opt/usr/nx-ks/tc/` 同步
- 菜单文件：`gui_tc.NX500` + `gui_func.NX500` 一行入口
- LUT：25 + 9 张替换，`encoding.json` 同步；旧版在 git `84fd972^` / `81ea302^`
- 卸载：`tc.sh off` 即回原厂；重启也会自动回原厂

## 五、工具

`tools/tcgen/`：`tcgen.py`（生成校验）、`tc_verify.py`（只读验链）、
`tc_write.py`（写入恢复）、`tc_record.py`（录制控制）。

`tools/lutgen/`：`web_regen.py`（G'MIC 重生成）、`gen_luts.py --input-regen`（配方重生成）。
