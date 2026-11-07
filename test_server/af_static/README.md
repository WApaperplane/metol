**NX500 AF 静态调查工具**

这些工具只读取本地文件并输出分析资料，没有机身访问及写入逻辑。

主报告：`E:/NXWA/nx500-modding-work/docs/current/NX500_AF_STATIC_ANALYSIS_2026-10-26.md`。

第二轮：`E:/NXWA/nx500-modding-work/docs/current/NX500_AF_STATIC_ROUND2_2026-10-26.md`，包含实时双眼链、主脸名次评分、追踪参数初值与消费者。

相位/反差优先关系：`E:/NXWA/nx500-modding-work/docs/current/NX500_AF_PHASE_CONTRAST_PRIORITY_2026-10-26.md`，包含初始相位决策、直接驱动、扫描回退与反向切换、跳过完整扫描的结束出口。

第三轮：`E:/NXWA/nx500-modding-work/docs/current/NX500_AF_STATIC_ROUND3_2026-10-26.md`，包含执行器类型到相位许可的链路、两种计数的复位、执行标志映射和独立视频相位驱动路径。

第四轮：`E:/NXWA/nx500-modding-work/docs/current/NX500_AF_STATIC_ROUND4_2026-10-26.md`，相位许可链收口：镜头挂载状态与镜头分类定性、`0x60084` 为启动一次性快照、`GAF+0xc98` 证明是几何派生块计数（非策略参数）、`0x60083` 在 p7 内无写入点、`0x30006` 完整值域 0..6 与 23 项派生表、宿主 RTTI `17CIQ_SysDataIF_NX1`、`0x2ff954` 函数名为 `GetSpecificLensTypeAFActuator`。

第五轮：`E:/NXWA/nx500-modding-work/docs/current/NX500_AF_STATIC_ROUND5_2026-10-26.md`，镜像盲区修正与枚举定名：p7 实为 `0xB84280`（前四轮只扫 `0x570000`，代码段确实全在此下）、数据段含完整枚举名表（184 个 `eIQ_ID_*`）、`IQ+0xc = eFOCUS_MODE` 且 `0x30007` 是其三档驱动类别派生、`IQ+0x274` 表实测（有效 raw 1/5/6/15）、全镜像复核第四轮负结果不变、视频 AF 参数取值为 4 档 × 6 档枚举。

第六轮：`E:/NXWA/nx500-modding-work/docs/current/NX500_AF_STATIC_ROUND6_2026-10-26.md`，数据项 ID 的真实形式：`0x332948(hub,id)` 统一取值、`id = 块号<<16 | 数组下标`、块对象 `{count@+8, array@+0x14}` 且越界返回 0、`0x60084` 在 GAF 状态位下被合成、`IQ+0x2e4` 是死路径覆盖开关（只有构造函数清零与一个无调用者的 setter）、更正第五轮"8 个 `+0x1c0` 消费者全在覆盖分支"（实为 2 个）、28 项分派表与两张字节表、IQ vtable 166 槽全图、184 条 `eIQ_ID_*` 名表 0 引用。

第七轮：`E:/NXWA/nx500-modding-work/docs/current/NX500_AF_STATIC_ROUND7_2026-10-26.md`，**sysdata 参数数组全解**：对象布局 `vptr + u32 slot[184] @+0x04..+0x2e3 + 元数据块 @+0x2e4`（构造函数 `memset(this+4, 0, 0x2e0)` 与 `Get` 的越界判据 `0xb7` 双向锁定）、`id i ↔ 偏移 4+4i` 且 184 条名表就是枚举名（第六轮"名表 0 引用=无效"被推翻）、`GetParameter`/`SetParameter` 两个虚函数是全类唯一的通用读写入口且**位于第六轮扫描窗口下沿之外**（这才是前两轮找不到写入者的结构性原因）、`+0x1c0 = eIQ_ID_APP_MODE`、`+0x1ec = eIQ_ID_3D_MODE`（NX500 无 3D 镜头 ⇒ 四处 3D 门恒假）、`0x3b1858` 是别的类的诱饵写入、第二个类名 `CIQ_ParamInfo_NX1`。

第八轮：`E:/NXWA/nx500-modding-work/docs/current/NX500_AF_STATIC_ROUND8_2026-10-26.md`，**CAFData 块总线**：`0xNNNNN` 形式的 ID 属于与第七轮 184 槽完全无关的第二套命名空间；hub 单例 `0x816d2ce0`（访问器 `0x336e7c`、构造 `0x336c5c`）下挂 6 个 `malloc(0x18)` 的块 `{vptr, count@+8, tag@+0x10, array@+0x14}`，全部具名 `LensSpec`(39) / `Ae`(18) / `UserData`(11) / `State`(37) / `Debug`(61) / `Sequence`(164)，共 330 项；`CAFData::SetData`=`0x3b53c8`、`GetData`=`0x3b546c`（类名出自日志串）；六个块的 `max(used_index)` 全部恰等于 `count-1`；`0x30006` 是 AF 拍摄模式类（`switch23(APP_MODE)`，只有 `APP_MODE==1 且 SMART_PRO_MODE==1` 才得 6），`0x30007` 是 AF 区域类（`{0,1,2,2}[AF_AREA-1]`），两者唯一写入者均为 `0x2f3b6c`；更正第四轮 `0x30006` 语义与第五轮 `0x30007` 标签。

第九轮：`E:/NXWA/nx500-modding-work/docs/current/NX500_AF_STATIC_ROUND9_2026-10-31.md`，**主体保持与眼部 AF 的闭环边界**：`CIQ_SysDataIF_NX1` 槽 `0x240/0x244` → `0x141a80`/`0x14201c` 是 AF 对「主体」的全部认知；`0x141a80` 按 face-info 单例 `+0x20` 切两条数据源，hold 打开时改用 `+0x24` 的整份 `0x444` 载荷副本（`UpdateHoldFaceBox 0x141f20` 做 memcpy）；`SetHoldFaceBox` 真正入口 `0x140de8`（`0x140df0` 只是函数体中段），共 11 个调用点，全属 `C3AStateLock`/`C3AStateLockCAF`/`C3AStateScanAF`/`CmdCancelS1`/`CCmdAutoShutter`/`CResAECompletion` 状态机；FD 准入 `0x2f6c48` 的获得与丢失**共用**一个 `r8 = 0x320`（800 ms，阶段 2 为 0），时间源 `0x2ba9c` 先除 26、`0x4dd064` 再除 1000；AF 区域出口为 `GAF+0x29f0` → `CAFData Sequence[0x13..0x1a]`；眼部结果在 `0xc8/0x190`（正方形，有效位 `0xd8/0x1a0`，结果码 1=双眼 2=只 B），仅笑脸/眨眼/拍后三处调用，**AF 代码区零命中**。

**符号索引工具**（第五轮新增，所有枚举名出自它）：
```powershell
E:/nxks2-re/Scripts/python.exe E:/NXWA/nx500-modding-work/test_server/af_static/symbols.py
E:/nxks2-re/Scripts/python.exe E:/NXWA/nx500-modding-work/test_server/af_static/symbols.py --prefix eIQ_ID_
E:/nxks2-re/Scripts/python.exe E:/NXWA/nx500-modding-work/test_server/af_static/symbols.py --grep MODE
E:/nxks2-re/Scripts/python.exe E:/NXWA/nx500-modding-work/test_server/af_static/symbols.py --near 0x584f44
```

注意：`analyze.py`、`trace_round2/3/4/5.py` 的代码扫描上限是 `0x570000`，覆盖代码段但不覆盖数据段；查符号与字符串一律用 `symbols.py`。`trace_round6/7/8.py` 按全镜像 `0xB84280` 扫描。

ID 复原注意：从 `mov/movw` + `movt` 拼常量时，回扫一遇到 `b/bl/blx` 就必须停，否则会把上一次调用的 `movt` 拼到这次调用上（第一版脚本因此造出假的 `0x70000`）。

运行环境：本机 `E:/nxks2-re/Scripts/python.exe`，已安装 pyelftools、capstone。脚本不安装依赖。

```powershell
E:/nxks2-re/Scripts/python.exe E:/NXWA/nx500-modding-work/test_server/af_static/analyze.py --workspace E:/NXWA
E:/nxks2-re/Scripts/python.exe E:/NXWA/nx500-modding-work/test_server/af_static/inspect_functions.py p7 0xfc7ac 0x13fee4 0x2f6c48 0x2f9700 0x36e7bc 0x36ea08 0x36ecc4 0x36f4f0
E:/nxks2-re/Scripts/python.exe E:/NXWA/nx500-modding-work/test_server/af_static/inspect_functions.py app 0x1e7330 0x1e988c 0x282594
E:/nxks2-re/Scripts/python.exe E:/NXWA/nx500-modding-work/test_server/af_static/trace_round2.py
E:/nxks2-re/Scripts/python.exe E:/NXWA/nx500-modding-work/test_server/af_static/trace_priority.py
E:/nxks2-re/Scripts/python.exe E:/NXWA/nx500-modding-work/test_server/af_static/trace_round3.py
E:/nxks2-re/Scripts/python.exe E:/NXWA/nx500-modding-work/test_server/af_static/trace_round4.py
E:/nxks2-re/Scripts/python.exe E:/NXWA/nx500-modding-work/test_server/af_static/trace_round5.py
E:/nxks2-re/Scripts/python.exe E:/NXWA/nx500-modding-work/test_server/af_static/trace_round6.py
E:/nxks2-re/Scripts/python.exe E:/NXWA/nx500-modding-work/test_server/af_static/trace_round7.py
E:/nxks2-re/Scripts/python.exe E:/NXWA/nx500-modding-work/test_server/af_static/trace_round8.py
E:/nxks2-re/Scripts/python.exe E:/NXWA/nx500-modding-work/test_server/af_static/trace_round9.py
E:/nxks2-re/Scripts/python.exe E:/NXWA/nx500-modding-work/test_server/af_static/inspect_functions.py p7 0x143740 --size 0x198
E:/nxks2-re/Scripts/python.exe E:/NXWA/nx500-modding-work/test_server/af_static/inspect_functions.py p7 0x3dc910 --size 0x390
E:/nxks2-re/Scripts/python.exe E:/NXWA/nx500-modding-work/test_server/af_static/inspect_functions.py p7 0x2c13b8 --size 0x9c
```

输入：`E:/NXWA/fw/v1.12/NX500_v1.12.bin` 的官方 p7 chunk，以及 `fw/v1.12/extract` 中的 ELF。历史函数边界/伪代码来自 `E:/ghidra_out`，仅作导航和辅助解释。脚本不会向这些输入位置写文件。

输出均在 `out/`：

- `manifest.json`：样本哈希、来源、ELF 依赖、相关符号。SLP 头原始 CRC 与普通 zlib CRC 均记录；未实现或断言 Samsung CRC 算法。
- `p7_af_strings.json`、各分类 `.tsv`：启发式选中的字符串、数据指针槽、A32 LDR literal 引用。
- `*.asm`：从当前样本生成的 Capstone 反汇编。
- `*_historical.c`：明确标记来源的历史 Ghidra 伪代码，不是本次反编译的新产物。
- `round2/navigation.json`：第二轮的当前机器码引用与 vtable 解析。
- `round2/contracts.json`：带来源及边界的状态、字段、初值、调用链记录，不是公开 ABI 或补丁。
- `priority/verified_checkpoints.json`：从官方样本独立读取并断言的相位/反差决策关键指令、日志引用及指令窗口；无需历史 Ghidra 文件。窗口不代表完整函数或补丁范围。
- `round3/verified_contracts.json`、`round3/navigation.json`：第三轮的当前机器码断言、vtable/RTTI、执行标志与计数生命周期，以及带边界说明的导航候选。
- `round4/verified_contracts.json`、`round4/navigation.json`：第四轮的门控形式、`0x30006` 派生表、值域与消费者，以及 `0x60083`/`0xc98`/`0xc94` 的写入点负结果。
- `round5/verified_contracts.json`：第五轮的镜像布局、三张查找表实测值、`0x30007` 派生、桩函数、全镜像复核与被证伪的假设。
- `round6/verified_contracts.json`：第六轮的 hub ID 编码与 6 块跳表、块对象布局与越界路径、`0x60084` 状态位合成、`IQ+0x2e4` 覆盖对与死路径结论、`+0x1c0` 的 8 个消费者与值域、28 项分派表与两张字节表、IQ vtable 166 槽映射、名表 0 引用。
- `round7/verified_contracts.json`：第七轮的类身份（`CIQ_SysDataIF_NX1` / `CIQ_ParamInfo_NX1`）、`vptr + slot[184] + 元数据` 布局、`GetParameter`/`GetOut`/`SetParameter` 三个虚函数与 `SetParameter` 的 AF 副作用、184 条字段全表、五连槽旁证、第六轮更正项、NX500 的 3D 恒假推论、`0x3b1858` 诱饵分析。
- `round7/sysdata_map.tsv`：`id / id_hex / offset / name` 四列，184 行，可直接拿去和运行时 dump 对照。**仅适用于 0..183 的纯整数 ID，不可套到 `0xNNNNN` 块 ID。**
- `round8/verified_contracts.json`：第八轮的 hub 单例与构造函数、六个块的名称/条目/基址/初始化器/vtable、`CAFData` 布局与越界路径、块号跳表、命名空间不可合并的三条理由、`0x30006/0x30007` 的 23 项与 4 项映射表、四入口调用点普查计数。
- `round8/cafdata_blocks.tsv`：`block / id_base / count / hub_slot / tag / tag_va / init / vtable` 八列，6 行。
- `round8/id_census.tsv`：`id / block / index / block_tag / reads / writes / via_hub / via_direct`，297 个不同 ID，四个入口（`hub_set`/`hub_get`/`SetData`/`GetData`）合并统计。
- `round9/verified_contracts.json`：第九轮的 IQ 槽位对应、`GetMainFaceArea` 双数据源、hold-box 11 个启停点、FD 去抖常量与时间单位、`Sequence[0x13..0x1a]` 总线、眼部结果语义与门控、眼部消费者签名。
- `round9/holdbox_chain.json`：hold 链的六个函数地址与两组调用点。
- `round9/eye_consumers.json`：眼部数据面函数及其访问到的偏移集合（函数起点由启发式给出，数量不作断言）。

限制：字符串名不证明功能启用；数据指针槽不等于代码调用；旧 Ghidra 边界不证明新样本函数长度准确；线性反汇编可能包含函数尾部的常量池。具体结论必须复核有效指令、条件分支和调用链。工具主要覆盖 A32 PC-relative LDR 引用，不是覆盖所有寻址方式的完整反编译器。

第二轮确认旧反编译有尾调用函数体展开的情况：`0x143740` 展开于 `0x1438d8`，`0x3dc910` 展开于 `0x1423dc`。因此这些位置使用明确字节范围重新导出；任何输出都不能直接当作可写补丁范围。
