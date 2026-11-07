# 视频 10bit 可行性：NX500 1.12 没有地基

日期：2026-11-07
相机：NX500 1.12（192.168.0.103）
证据：`rea-evidence/20261107-gamma/gamma-d-video.bin`、`gamma-standard-video.bin`、`fw/v1.12/NX500_v1.12.bin`

## 结论

**没有 10bit。** 不是"有通路但没开关"，是整条链路只有 8bit。

现有码流的 `hvcC` 把这件事写死了：

```
profile_idc      = 1        -> HEVC Main（不是 Main10=2）
level_idc        = 153      -> Level 5.1
chromaFormat     = 1        -> 4:2:0
bitDepthLuma     = 8
bitDepthChroma   = 8
```

意味着 `log` 在 NX500 上不可达 —— 8bit 容器里做曲线重映射只能重新分配 256 级码值，不产生动态范围。3DLUT 末端重映射是唯一可行且已通的路。

## 逐项证据

| 检查 | 结果 |
|---|---|
| 码流 hvcC（两段录像一致） | `profile_idc=1` / `8bit` / `4:2:0` / L5.1，无第二组 SPS |
| 全固件 352 MB 搜 `Main10` / `main10` / `MAIN10` | **0 命中** |
| 全固件搜 `profile_idc` / `bit_depth_luma` / `general_profile_idc` | 0 / 0 / 0 |
| 全固件搜 `hvcC` | 仅 2 处，都是 `mp4_parse_hvcC` —— **解析器，不是生成器** |
| 相机 UserData 全表 129 项 | 无视频位深、无编码档位；色彩空间只有 `COLORSPACE_SRGB`，无 BT2020 |
| 相机 Variable 全表 64 项 | 同上，无相关项 |
| di-camera-app 393 条含 MOVIE 的字符串 | 零 `10bit` / `HDR10` / `BT2020` / `HEVC` |
| 外部规格（2015 上市） | 4K24p / UHD30p HEVC，最高约 40 Mbps，无 10bit 记载 |

## 四处容易误判的命中

搜出来的 `10bit` / `10BIT` 全部与视频输出无关：

1. `" nanr_mem_mode = %d, cnr_mem_mode w/h = %d, ycc420 = %d, out10bit = %d\n"` @ `0x807173a1`
   ISP 降噪内存模式的调试打印。只说明 ISP 内部管线有位深/格式参数，**不代表编码器输入或容器是 10bit**。反向推论不成立。
2. `"eCAP_RAW_BIT_10BIT"` @ `0x8072fa0c`
   照片 RAW 位深枚举族（8/10/12/14/16），实际默认 `USERDATA_RAW_BIT = RAW_BIT_14BIT`。与视频无关。
3. `"10bit"` @ `0x8071e0c8`
   邻居是 `sensorwin` / `2r2swin` / `readcom3`，属 sensor 驱动 readout window 表。
4. `USERDATA_HDR` / `HDRLEVEL` / `HDRARTLEVEL`
   三星 HDR 艺术滤镜（照片），不是 HDR10 视频。

## 顺带纠正一条旧记录

`MEMORY.md` 里「4:2:2 是硬件链路固定（`VADD can process only YC422`）」说的是 **JPEG 静态照片**。**HEVC 视频是 4:2:0**，两条不是同一条通路。别把 JPEG 的结论套到视频上 —— 我上一轮就是这么说的，错。

## 外部印证（同时解释了 gamma 那条）

2015 年 NX500 发布时的报道原文：

> "It's also not yet clear whether the other new NX1 firmware features such as picture profiles like **Gamma DR** and the **Master Black Level** setting have made it over to the NX500."

Gamma DR 与 Master Black Level 都是 **NX1** 的功能。NX500 的 IQ[180] `MOVIE_GAMMA_MODE` 与 IQ[181] `MOVIE_MASTER_BLACK_LEVEL` 正好相邻、都无实现 —— 同一批未下放的 NX1 残留，与 `GAMMA_LOG_VERDICT_2026-11-07.md` 的判定互相印证。

## 复现

```python
# hvcC 位深/色度
b = open('gamma-d-video.bin','rb').read()
i = b.find(b'hvcC'); sz = struct.unpack_from('>I', b, i-4)[0]
cfg = b[i+4: i-4+sz]
print(cfg[1]&0x1f, cfg[16]&3, (cfg[17]&7)+8, (cfg[18]&7)+8)   # 1 1 8 8
```

```sh
# 全固件扫描
python -c "d=open('NX500_v1.12.bin','rb').read(); print(d.count(b'Main10'))"
```

## 遗留

- DRIMe5 的 HEVC 硬件 IP 在硅层是否支持 Main10，固件里查不到（无配置入口，即使支持也无从启用）。
- HDMI 输出位深未验证（`USERDATA_HDMIOUT` 只有 1080i/720p 等分辨率枚举，无位深维度）。
