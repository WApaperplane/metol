# JPEG 质量常量：17 档量化表阶梯（2026-10-31）

> 任务：静态解读，找 NX500 出片 JPEG 的质量常量。
> 结论：**质量不是一个标量常数，而是一组 17 档预置量化表**，编码器按 `qtable_index` 查表；
> 实测 SFINE 落在 idx 1、FINE 落在 idx 5。表在 **p7 固件**里，不在 `di-camera-app`。

---

## 1. 三层证据

| 层 | 对象 | 结论 |
|---|---|---|
| 出片 | `_photos/*.JPG` | DQT 8bit，4:2:2；只有两种表指纹，对应 idx 1（14 张）与 idx 5（2 张） |
| App | `di-camera-app`（4.77 MB, sha256 55dcc781…） | **无任何 JPEG 量化表 / 质量缩放表**（64B 表、IJG 缩放表、1..100 表全部 0 命中）；只持有质量**枚举**，质量数值不在这一层 |
| 固件 | `p7_wrapped.elf`（12.08 MB, sha256 91c8f8cf…） | 持有 17 档 luma/chroma 量化表数组 + 查表逻辑 + 编码重试机制 |

---

## 2. 表数组位置

| 项 | 文件偏移（p7_wrapped.elf） | p7 原始 bin 偏移 | VA |
|---|---|---|---|
| luma 表数组基址（idx 0） | `0x585450` | `0x584450` | `0x80584450` |
| chroma 表数组基址（idx 0） | `0x585010` | `0x584010` | `0x80584010` |
| **SFINE luma（idx 1）** | `0x585490` | `0x584490` | `0x80584490` |
| **SFINE chroma（idx 1）** | `0x585050` | `0x584050` | `0x80584050` |
| **FINE luma（idx 5）** | `0x585590` | `0x584590` | `0x80584590` |
| **FINE chroma（idx 5）** | `0x585150` | `0x584150` | `0x80584150` |
| 标准 IJG 表（idx 13） | `0x585790` / `0x585350` | `0x584790` / `0x584350` | `0x80584790` / `0x80584350` |

> VA 换算：`p7_wrapped.elf` 单段映射 `file 0x1000 → 0x80000000`，故 `VA = 0x80000000 + (file_off - 0x1000)`；
> 对**裸 p7 bin** 则是 `VA = 0x80000000 + off`（与既有记忆一致）。

---

## 3. 17 档阶梯

| idx | eq_scale | 等效 IJG Q | luma max | 备注 |
|----:|---------:|-----------:|---------:|------|
| 0 | 3.3% | 98.3 | 4 | 最细，机身未用 |
| **1** | **5.1%** | **97.4** | 6 | **SFINE（实测）** |
| 2 | 5.3% | 97.3 | 6 | |
| 3 | 5.8% | 97.1 | 7 | |
| 4 | 7.8% | 96.1 | 10 | |
| **5** | **11.8%** | **94.1** | 15 | **FINE（实测）** |
| 6 | 16.1% | 92.0 | 20 | |
| 7 | 19.4% | 90.3 | 24 | |
| 8 | 24.6% | 87.7 | 30 | |
| 9 | 32.7% | 83.6 | 40 | |
| 10 | 41.4% | 79.3 | 50 | |
| 11 | 50.0% | 75.0 | 60 | |
| 12 | 75.0% | 62.5 | 90 | |
| 13 | 100% | 50.0 | 121 | = IJG 标准表（基准） |
| 14 | 200% | 25.0 | 242 | |
| 15 | 400% | 12.5 | 255 | 钳位 |
| 16 | — | 11.0 | 255 | 全 255，最差 |

**iq 关系**：`idx 13` 就是 IJG 标准表（scale 100% = Q50）；往上每档约 ×0.5~0.75，往下 ×2、×4、×8。

---

## 4. 查表逻辑（p7 `FUN_80128378`）

```c
k   = *(int *)(ctx + 0xd98);            // 当前分量 0..2
idx = *(int *)(ctx + 0xd2c + k*4);      // 每分量的 qtable 索引 0..16
luma_ptr   = DAT_80128638 + idx*0x40;   // 0x80584450 + idx*64
chroma_ptr = DAT_8012863c + idx*0x40;   // 0x80584010 + idx*64
*(int *)(ctx + 0xd5c + k*0xc) = luma_ptr;
*(int *)(ctx + 0xd60 + k*0xc) = chroma_ptr;
```

- `idx > 0x10` → 走 `"(Jpeg_Encode_Retry) Jpeg QTable Max Error!"` 分支；
- 表指针被写进每分量的 JPEG 描述结构（`+0x2c`），随后交给 `d5_ep_jpeg_encoder`。

## 5. 自适应重试（为什么同一档位可能出不同质量）

`FUN_80128378` 里有一段：当 `ctx[0xd90] != 0`（自适应使能）、当前分量结束且计数 < 0x10 时，执行

```c
ctx[0xd30] += 1;
ctx[0xd2c] += 1;        // 质量索引递增 = 量化变粗 = 体积变小
```

配合 `Jpeg_Encode_Retry` 字符串，说明编码器有"超限就升一档重编"的速率控制。
实测 16 张里全部稳定落在 idx 1 / idx 5，说明该路径在正常拍摄下未触发。

---

## 6. app 侧：质量只以枚举下传

| 项 | 内容 |
|---|---|
| 枚举字符串表 | `0x3afdb0` 起：`eUS_IQ_SFINE=0, eUS_IQ_FINE=1, eUS_IQ_NORMAL=2, eUS_IQ_RAW_ONLAY=3, eUS_IQ_SFINE_RAW=4, eUS_IQ_FINE_RAW=5, eUS_IQ_NORMAL_RAW=6` |
| 命令映射 | `cmd_set_photo_quality @ 0x272da4`：`"fine"→1, "norm"→2, "raw"→3, "raw+sfine"→4, "raw+fine"→5, "raw+norm"→6`，其余（含 `sfine`）→ 0 |
| 写入点 | `UI_Set_Value(0xd0, enum)`；RVF 事件 `0x2d` 同样写 `0xd0`（`FUN_0017af80(0xd0, val, 1)`） |
| 编码调用 | `UI_Mm_Photo_Encode_Ycc → mm_photo_encode_ycc(ycc, buf)`（第 2 参数是目标缓冲区，**不是质量**）；`UI_Mm_Photo_Encode_To_File → mm_photo_encode_to_file(ycc, info)` |

> 所以「quality 数值」不在 app 内，链路是：`app 枚举 → vconf/DB → capture-fw → p7 qtable_idx`。
> 枚举→idx 的映射在 Linux 侧（`libcapture-fw-prod.so` / `libmm-photo.so`，本机固件包内没有，需从机身拉取才能继续）。

---

## 7. 对画质的意义

1. **压缩已接近无损**：SFINE = idx 1（等效 Q97.4），比它更细的只剩 idx 0（Q98.3）。
2. **4:2:2 是 ISP 链路固定，不是可配置项**。证据：p7 内无 SOF0/SOS 段模板（`FF C0 00 11`、`FF DA 00 0C` 均 0 命中，头是逐字节生成）；采样相关字符串全部指向硬件链路 ——
   `Error: VADD can process only YC422 data.`、`DMA 420 param should be set as 422 for Bayer format`、`DMA_FMT_420 should be set as 422 for Bayer format`。
   JPEG 编码器吃的就是 YUV422，**改 4:4:4 不可行**。
3. **可下手的是量化表本身**：它是固件里的静态数据，编码器只按下标取指针，不做任何校验。

## 8. 档位与索引的关系

- 实测：`SFINE → idx 1`、`FINE → idx 5`，**间隔 4**。
- 推测：`idx = quality_enum * 4 + 1`（`NORMAL → 9`，Q83.6），每档留 4 步给重试递增；idx 0 为保留（比 SFINE 更细，机身不用）。
- **未在代码中直接找到映射表**（`[1,5,9]`、`[1,5,9,13]` 在固件内均无有意义的命中），该推断属高置信猜测。
- 验证方法：拍一张 **NORMAL（普通）** 质量样片，跑 `python tools/jpegq/ladder.py` 看命中 idx，是 9 则公式成立。

## 9. Patch 面

工具：`python tools/jpegq/patch_qtable.py`

```bash
# 列出 17 档在裸 bin 里的位置
python tools/jpegq/patch_qtable.py --list --src p7.bin
# 把 SFINE(slot 1) 换成 idx0 的表
python tools/jpegq/patch_qtable.py --src p7.bin --dst p7_new.bin --slot 1 --mode copy --from-slot 0
# 把 SFINE 换成全 1 表（近无损，体积会明显变大）
python tools/jpegq/patch_qtable.py --src p7.bin --dst p7_new.bin --slot 1 --mode ones
# 整体缩放 50%
python tools/jpegq/patch_qtable.py --src p7.bin --dst p7_new.bin --slot 1 --mode scale --pct 50
```

裸 bin 偏移：luma `0x584450 + slot*0x40`、chroma `0x584010 + slot*0x40`。

**前置提醒**：`fw/v1.12/p7_patched_test.bin` 与 `p7_wrapped.elf` 的 0x1000 之后并非全等（已被既有 mod 改动），
量化表区虽一致，但做基线 patch 应另取原厂 p7 段，勿直接在该文件上叠改。

---

## 10. 复现

```bash
python tools/jpegq/ladder.py                 # 17 档阶梯 + 样片命中
python tools/jpegq/solve_q.py "_photos/*.JPG" # IJG 公式逐项反解
python tools/jpegq/find_table.py <jpg>       # 全固件目录搜表
python tools/jpegq/armdis.py 0x1293a0 0x220  # capstone 定点反汇编
python tools/jpegq/patch_qtable.py --list --src <p7.bin>   # 17 档在裸 bin 的位置
```

脚本目录：`E:/NXWA/tools/jpegq/`（capstone 5.0.7 装在 `E:/NXWA/tools/pylibs`，未污染 C 盘）。
