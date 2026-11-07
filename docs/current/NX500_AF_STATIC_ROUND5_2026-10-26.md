**NX500 对焦静态逆向第五轮：镜像盲区修正与枚举定名 · 2026-10-26**

本轮的第一个结果和方法有关：**前四轮的所有脚本只扫了镜像的前 0x570000 字节，而 p7 chunk 实际是 0xB84280（12.06 MB）。有 6.4 MB 从未被任何脚本读过。** 那 6.4 MB 里不是空的——是完整的符号名表和枚举名表。清点之后，`0x30007` 的语义可以定名，`0x30006` 的映射得到二次验证，`IQ+0x1c0` 被排除掉一个可能身份。

仍为纯本地静态分析，没有访问机身、执行相机命令、生成补丁或刷写。沿用官方 v1.12 p7，SHA-256：`f8e417cb5b55768851ba7e2b8017d3a98dc0b0c8444cc0a5061265cc08dbbf7f`。

**1. 盲区：代码段只占 46%，其余是数据**

前四轮的扫描上限 `0x570000` 来自历史 Ghidra 索引的范围假设，从未被验证。按 64 KiB 窗口统计可打印字符串密度即可看出边界：

| 区间 | 每 64 KiB 字符串段数 | 判定 |
|---|---|---|
| `0x000000`–`0x01FFFF` | 236 / 73 | 向量表与启动数据 |
| `0x020000`–`0x51FFFF` | 0（整段为空） | **代码段** |
| `0x560000`–`0x76FFFF` | 360 → 207 → 2348 → 511 | 符号名与枚举名 |
| `0x920000`–`0xAD0000` | 671 → 1627 → 25 | 资源与字体 |

代码确实都在 `0x570000` 以下，所以**历史结论的方向没问题**，但"某 ID 没有写入者"这类负结果原先只有 46% 的覆盖面。本轮全部按 12 MB 重扫（见第 5 节），结论不变。

新增工具 `symbols.py`，把整个镜像的字符串做成可检索索引：107,609 条可打印串，按前缀归类后给出：

| 类别 | 数量 | 地址范围 |
|---|---|---|
| `eIQ_ID_*`（IQ 参数 ID 名） | **184** | `0x700dd0`–`0x701fb8` |
| `eSMARTPRO_MODE_*`（智能模式） | 39 | `0x6ff094`–`0x700c88` |
| `FD_MODE_*`（人脸检测模式） | 10 | `0x585478`–`0x58552c` |
| `MODE_*`（对象追踪状态） | 7 | `0x584f44` 起 |
| `eAF_MOVIE_SENSITIVITY_*` | 6 | `0x6ff158`–`0x6ff1e8` |
| `AFMODE_*` | 5 | `0x6f536c`–`0x6f53b0` |
| `eFOCUS_MODE_*` | 4 | `0x6fed08`–`0x6fed48` |
| `eAF_MOVIE_SPEED_*` | 4 | `0x6ff280`–`0x6ff2c8` |

这把"字段语义不明"从猜测变成了可查。**此前四轮所有"未命名枚举"的缺口，缺的不是推理而是这张表。**

**2. `0x30007` 定名：`eFOCUS_MODE` 的三档派生**

第四轮只知道 `0x30007 = 0x2f399c(...)`，不知道它是什么。现在链路完整：

```text
0x2f399c
  → vtable slot 0x204 = 0x2c10c8
      ldr r3,[r0,#0xc] ; sub r3,#1 ; cmp r3,#3
      ldrls r0, [table + 0x14 + r3*4]
      表 @ 0x805de4ec + 0x14        → [1, 2, 3, 4]   恒等
  若结果 <= 3：r4 = TABLE_0x2f399c[结果]   TABLE = [0, 1, 2, 2]
  否则        ：r4 = 1
```

`IQ+0xc` 的值域是 1..4，而数据段里正好有一组四项枚举：

```text
0x6fed08  eFOCUS_MODE_SINGLE
0x6fed1c  eFOCUS_MODE_CONTINUOUS
0x6fed34  eFOCUS_MODE_MANUAL
0x6fed48  eFOCUS_MODE_AUTO
```

值域、项数、恒等映射三者吻合，`IQ+0xc = eFOCUS_MODE` 可以定。于是 `0x30007` 是：

| `eFOCUS_MODE` | 表下标 | `0x30007` | 语义（推断） |
|---|---|---|---|
| SINGLE (1) | 1 | **1** | 单次驱动 |
| CONTINUOUS (2) | 2 | **2** | 连续驱动 |
| MANUAL (3) | 3 | **2** | 连续驱动（手动拉焦同属持续驱动） |
| AUTO (4) | >3 | **1** | 单次驱动 |
| 无 / 越界 | 0 | **0** | 无 AF |

**这是 `0x30007` 第一次有可读语义**：它不是 AF 模式直通，而是把四种模式压成三档"驱动类别"（0 无 / 1 单次 / 2 连续）。这个压缩解释了为什么 `0x3356b4` 里 `param_3`（即 `0x30007`）只在"是否等于 0 / 1"处分叉——它只关心驱动类别，不关心具体模式。

需要保留的边界：`eFOCUS_MODE_*` 的字符串是按地址相邻，**数值与名字的绑定是"按定义顺序 1 基"的假设**，没有找到显式的名字数组。所以上表的行标签是推论，`0x30007` 的取值 0/1/2 本身是硬结论。

这同时关闭了第三轮留下的"AF-S/AF-C 菜单值映射"缺口的上半部分：**内部表示不再是未知字段，而是 `IQ+0xc` 的 1..4**。缺的只是"菜单号 → 1..4"这一段，那在 UI 层，不在这条链上。

**3. `IQ+0x274`：第四轮的映射得到二次验证**

第四轮我把次级表的基址取错了（用了 `0x2f3a24` 的 pool 而不是 `0x2c15e8` 的），读出一串无意义的 22..27。正确结果：

```text
0x805de4ec + 0xd0，按 raw 1..15 索引：
raw:   1   2   3   4   5   6   7   8   9  10  11  12  13  14  15
val:   0  -1  -1  -1   1   2  -1  -1  -1  -1  -1  -1  -1  -1   3
```

有效 raw 只有 **1、5、6、15**，映射到 **0、1、2、3**，其余返回 -1。

用这份正确的表回代第四轮的分支逻辑：

```asm
0x2f3af8  sub r3, r0, #2      ; r0 = 次级值
0x2f3afc  cmp r3, #1
0x2f3b00  bls 0x2f3ab8        ; 次级 ∈ {2,3} → 4
0x2f3b04  cmp r0, #0
0x2f3b08  bne 0x2f3b58
0x2f3b58  cmp r0, #1
0x2f3b5c  movne r4, #3
0x2f3b60  moveq r4, #6        ; 次级 == 1 → 6
```

**第四轮的 `0x30006` 派生表成立**：4 来自次级 ∈ {2,3}，6 来自次级 == 1，其余 3。表值 0/1/2/3 恰好覆盖四条分支，说明这张表就是为这个分派设计的，不是巧合。

第四轮漏掉的两项仍然有效：跳表尾部 **idx 21 → 4、idx 22 → 0** 不经过次级调用。

**4. `GetSmartScene` / `GetSubSmartScene` 是恒返回 1 的桩**

`IQ+0x1c0` 一度被认为可能是"智能场景"。查到实现后这个假设被否掉：

```text
0x10f774  GetSmartScene 日志包装  → 尾部 b 0xffccc
0xffccc   mov r0, #1 ; bx lr            ← 恒返回 1
0x10f7cc  GetSubSmartScene 日志包装 → 尾部 b 0xffcd4
0xffcd4   mov r0, #1 ; bx lr            ← 恒返回 1
```

两个函数名保留在 `CLiveviewFactory.cpp` 的断言串和 `[Live] Liveview %s` 日志里，但实体是空壳。**NX500 的 p7 沿用了 NX1 的 Smart Auto 框架而没有实现它**，所以 `IQ+0x1c0` 不是由这两个函数喂养的，它的 23 值枚举另有来源。

顺带一个副产品：`p7` 里保留了 `product/Liveview/common/CLiveviewFactory.cpp` 这样的源文件路径断言串，这类符号对后续定位函数很有用。

**5. 全镜像复核：第四轮的负结果仍然成立**

把扫描范围从 5.6 MB 扩到 12 MB 重跑第四轮的构造点统计：

| 数据项 | 构造点 | 其中 > `0x570000` |
|---|---|---|
| `0x60083` | 2 | **0** |
| `0x60084` | 9 | **0** |
| `0x30006` | 15 | **0** |
| `0x30007` | 1 | **0** |
| `0x30008` | 7 | **0** |
| `0x1001e` | 12 | **0** |
| `0x10004` | 35 | **0** |

`GAF+0xc98` 的写指令全镜像只有两处：`0x334394`（GAF）和 `0x12e5b0`（`strb` 到一个无关对象，基址 `r10` 不来自 GAF 的 literal）。`GAF+0xc94` 同理（`0x3343bc` 与 `0x12e58c`）。

**所以第四轮的三条排除性结论（`0xc98` 是几何派生量、`0x60083` 无写入点、`0x60084` 一次性快照）在 12 MB 全范围内不变。** 区别只在证据强度：现在可以说"全镜像"，而不是"前 46%"。

**6. 视频 AF 两个参数的取值范围已具名**

第一轮发现"视频 AF 有独立的换焦速度与响应灵敏度参数"，当时只有数据项号和初值。数据段里它们的枚举名是完整的：

```text
0x6ff280  eAF_MOVIE_SPEED_INVALID
0x6ff298  eAF_MOVIE_SPEED_FAST
0x6ff2b0  eAF_MOVIE_SPEED_NORMAL
0x6ff2c8  eAF_MOVIE_SPEED_SLOW

0x6ff158  eAF_MOVIE_SENSITIVITY_INVALID
0x6ff178  eAF_MOVIE_SENSITIVITY_LEV1
0x6ff194  eAF_MOVIE_SENSITIVITY_LEV2
0x6ff1b0  eAF_MOVIE_SENSITIVITY_LEV3
0x6ff1cc  eAF_MOVIE_SENSITIVITY_LEV4
0x6ff1e8  eAF_MOVIE_SENSITIVITY_LEV5
```

对应 IQ 参数 `eIQ_ID_AF_MOVIE_SPEED`（`0x701114`）和 `eIQ_ID_AF_MOVIE_SENSITIVITY`（`0x70112c`）。这是第一轮"最适合先做场景配置"那条建议的落地依据：**档位是 4 档 × 6 档，不是连续值。**

**7. 一个被证伪的假设**

`IQ_SysDataIF_NX1` 缓存了 184 个 IQ 参数（`eIQ_ID_*` 有 184 项）。如果字段按 ID 顺序每项 4 字节推进，`+0xc` 对应第 0 项 `eIQ_ID_AF_MODE`，那么：

```text
+0x010 → eIQ_ID_AF_MOVIE_MODE
+0x014 → eIQ_ID_AF_AREA           ← 与 0x2c10f4 判 "AF_AREA != 1" 吻合
+0x1c0 → eIQ_ID_CWB_G_GAIN        ← 白平衡增益
+0x274 → eIQ_ID_SMARTART_EXPOSURE_LEVEL
```

`+0x1c0` 落在白平衡增益上，而它是一个 23 值枚举、被 AF 策略分派消费，两者不相容。**线性映射假设否定**，`IQ+0x1c0` 仍然无名。`+0x14` 与 `AF_AREA` 的巧合不足以支撑这个假设。

**优化判断的更新**

| 候选 | 本轮变化 |
|---|---|
| "AF-S/AF-C 无法映射" | **部分关闭**。内部表示 = `IQ+0xc`（1..4），`0x30007` = 三档驱动类别。缺的是 UI 菜单号到 1..4 的那一段 |
| 视频 AF 参数调节 | **可落地**。4 档 × 6 档枚举已具名，可取值为 `FAST/NORMAL/SLOW` 与 `LEV1..LEV5` |
| `IQ+0x1c0` 定名 | 未解，但排除了 Smart Scene 与 IQ-ID 线性槽两个身份 |
| 前四轮的负结果 | **加固**。从 46% 覆盖升级为全镜像 |

下一轮值得做的两件事，都有明确抓手：

1. **给 `IQ+0x1c0` 找到写入者**。已知它构造函数里被 `memset` 清零、vtable 里没有 setter、8 个消费者都在 `+0x2e4 == 0` 的默认分支。下一步应该查 `+0x2e4` 这个"覆盖开关"是谁置的——一旦找到写入路径，23 值枚举的来源会同时暴露。
2. **用符号表反查 `0x1001e`**。数据段有 184 个 IQ 参数名，`0x1001e` 是门控里唯一完全未定位的项。做法是在 `eIQ_ID_*` 附近找参数‑数值的绑定表，而不是继续猜字段偏移。

**复核产物**

- `test_server/af_static/symbols.py`：全镜像字符串索引，支持 `--grep` / `--prefix` / `--near` / `--dump-json`。本轮所有枚举名都出自它。
- `test_server/af_static/trace_round5.py`：断言 **20 条指令、16 个枚举名、3 张查找表、7 个数据项 ID 的全镜像构造点**，另含 `0xc98`/`0xc94` 写指令的全镜像计数。
- `out/round5/verified_contracts.json`：表值、派生关系、桩函数、全镜像复核结果与被证伪的假设。

复现命令：

```powershell
E:/nxks2-re/Scripts/python.exe E:/NXWA/nx500-modding-work/test_server/af_static/trace_round5.py
E:/nxks2-re/Scripts/python.exe E:/NXWA/nx500-modding-work/test_server/af_static/symbols.py
E:/nxks2-re/Scripts/python.exe E:/NXWA/nx500-modding-work/test_server/af_static/symbols.py --prefix eIQ_ID_
```

`Survey` 会校验官方样本哈希；本轮的字符串统计与枚举名全部来自当前官方固件字节，不依赖历史 Ghidra 产物。
