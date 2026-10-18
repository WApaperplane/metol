# LUT0 成片路线复核与离线准备（2026-10-18）

附件提出的疑点成立：**E4没有否定所有不刷机的成片方案。** 但“把表改灌LUT0，再用现有守护保住它”存在代码层面的缺口。现有守护只恢复选择配置，不重灌内容；P7可在选择值始终为0时触发新的Load。

本轮仅在PC上读代码、执行原指令仿真、修改脚本并回归。沿用用户“先保留只读结果”的决定，没有连接相机、部署脚本、写RAM/寄存器、启动守护、重启App或刷固件。

## 1. E4的有效范围

[U6结果摘要](U6_ONMACHINE_RESULT_2026-10-09.md) §1.1记载：Portra装入LUT1；半按、松开、等1秒、全按；照片未观察到预期风格，Still期间Cfg出现`0x0→0x1100`。这是该操作序列的负结果，不能排除LUT0装载或源池替换。

不能进一步写成“E4只证明LUT1不影响成片”：它也没有穷举所有LUT1使用方式和时序。原始台账`raw8/gates/u6/u6_result.md`在当前检出中缺失，本轮没有拿原始JPEG重新判片；保留历史摘要及其局限。

E3所记6次恢复`rc=0`、延迟小于500ms，是预览事件下的记录。它没有测量Still实际消费表的时刻，不能证明500ms够用，更不能把返回0当作JPEG已使用导入表。

## 2. 两层可复现证据：选择不变，仍然能重载

### 原P7装载指令

[audit_lut0_reload.py](../../test_server/lutpipe/audit_lut0_reload.py)用已核验A2镜像（MD5 `712c6fd0a49371ec05ce94c367b0d5c7`），复用已有Unicorn环境执行`0x804A5C44(0x81115200, 0, 1, 0)`。两个初态均到达预期返回地址，本次没有命中外部函数桩：

| Cfg初态→末态 | SelLUT | 仍执行的写入 |
|---|---|---|
| `0x100→0x100` | `0→0` | Load源`+0x00c←0x81115200`，Pulse `+0x008` bit8先置后清 |
| `0x1100→0x1100` | `0→0` | 同上 |

[完整写序](../../test_server/lutpipe/logs/lut0_reload_trace_2026-10-18.json)证明软件确实请求装载；没有模拟真实DMA、缓存一致性或Still时序，也不证明DMA完成。

### 真实守护代码的接口回放

[C夹具](../../test_server/lutpipe/fixtures/lutsentinel_host.c)直接包含生产`lutsentinel.c`，替换全部设备、动态库和等待接口；以模型模拟每轮P7重选LUT0并改变表内容。它不模拟硬件SRAM，验证的是守护的实际判断分支。

| 相同的4轮模拟重载 | `op_init`调用次数 | 说明 |
|---|---:|---|
| 守护目标`--sel 0` | 0 | 读到0等于目标0，完全不动作 |
| 守护目标`--sel 1` | 4 | 发现0不等于1，恢复选择 |

生产代码只解析`op_init`，没有调用`load_lut`。因此**改成`--sel 0`不能把选择守护变成内容守护**；即便某次配置被恢复，也不能恢复已经覆盖的表。

## 3. 已完成的脚本改动

- `lut_backend.sh`和PC驱动支持`apply <name> --sel 0|1 [--dry]`，默认仍为1；实际向picker传`--ch0`或`--ch1`，不靠打印字段冒充传参。
- `lutpick.sh`显式识别通道参数，拒绝重复/冲突通道及未知选项；仍依次经过落点命中检查、cmasafe和单次API调用。修复`off --dry`原先没有解析到`--dry`的问题。
- 成功实写后把请求通道记入`luts/current.sel`；dry或API失败不更新。`status.sel`仍为null，`sel_requested`读取记账；旧记录缺通道时返回null，不推定为1。成功rollback清理两份记账。
- sel=0请求遇到活动守护返回`guard_conflict`，不自动停止、重启或切换守护。没有增加重灌守护。
- 保留`hardware_verified:false`，新增`still_verified:false`；`level:full`是原有适配器调用结果，不能据此宣传预览或成片已通过。

机端仍是原来版本；本地两份shell和PC驱动需一起核验部署，不能把本轮离线测试当作机端回归。

当前可以运行的纯离线演练：

```sh
python test_server/lutpipe/lut_backend.py --sim apply portra400 --sel 0 --dry
python test_server/lutpipe/lut_backend.py --selftest
# 以下两个测试模块在WSL运行；ARM工具/设备边界均被夹具替代。
cd test_server/lutpipe
python3 -m unittest -v test_lut_backend_shell test_lutsentinel_replay
```

原指令复现（PC需Unicorn）：

```sh
python test_server/lutpipe/audit_lut0_reload.py --image E:/NXWA/fw/v1.12/a2/p7_a2.bin --json test_server/lutpipe/logs/lut0_reload_trace_2026-10-18.json
```

## 4. 对附件其余提案的判断

| 提案 | 可保留的价值 | 尚不能推出的结论 |
|---|---|---|
| sel=0单次装表拍摄 | 成本较低的独立实验，E4未覆盖 | 不能承诺守护保住内容；负结果仍可能是重载/时序，不能直接否定所有成片路线 |
| A17运行池替换 | 更贴近当前观测的View源，可检验正常重载是否消费改表 | 共享RAM、缓存及重载时机未经闭环，不能称零风险；成功也不能保证C1在全部View/Still状态成功 |
| 改镜像副本再`ref reboot` | 仅保留研究假设 | 重定位公式不证明镜像原件仍驻留、跨核可写且会被复用；重启也可能从存储重新加载，无现成“软刷机”结论 |
| 指针改向SMA并加守护 | 待解决缓冲所有权与生命周期的运行时方案 | 不是天然持久化；全零扫描不等于已分配专有缓冲，不能直接当成长期可用内存 |

10-17两轮共1800个样本中是**1799个A17、1个全零过渡态**，不是1800次全部A17。这是当前View/半按观测，不能替代历史A12实验当时的选表证据，也不能证明全按时Still必选A17。

## 5. 后续推进依据

先把LUT0当作**一次受控机制实验**，不要与“LUT0守护已解决”绑定。后续若用户决定开展写入，应单独准备原厂基线、明显诊断表和恢复结果；固定场景/曝光/白平衡，分别记录取景、半按、全按和原始JPEG。先确认导入表在预览上有可辨效果，再判断成片；负结果只能限定到该次条件。现有恢复命令对LUT0内容是否足够也要独立验，不能用identity替代恢复原厂。

较长期仍推进C3：明确目标缓冲所有权，让P7正常的View/Still重载流程取到导入表，减少抢时序。A17可作来源机制试验的候选，Still还要确认具体分支与目标槽。C1包保持本地候选，刷入及机身升级菜单确认仍是独立决定；本轮没有越过只读边界。

## 6. 验证记录

- [23项实际shell/守护回放测试](../../test_server/lutpipe/logs/sel0_offline_regression_2026-10-18.txt)：通过。覆盖默认LUT1、显式LUT0、完整两层shell到API参数、dry无load、落点/安全闸拒绝、API失败、冲突参数、旧记账和恢复路径。
- [10项模拟契约自测](../../test_server/lutpipe/logs/sel0_backend_selftest_2026-10-18.txt)：通过；属于模拟证据。
- [原指令两场景](../../test_server/lutpipe/logs/lut0_reload_trace_2026-10-18.json)：通过；DMA和机身效果未验证。
- [脚本检查](../../test_server/lutpipe/logs/scripts_ci_2026-10-18.txt)：在仓库根作为检查目标执行；相机端脚本语法和LF行尾检查一并通过。
