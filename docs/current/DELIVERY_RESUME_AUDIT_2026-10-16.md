# P5 失败后的恢复链定向审计与 LUT 后端修正

> ⚠️ **2026-10-18 文档清理：本文结论已被取代。** 文中 LUT 后端的 `--ch1` / `lutsentinel` 部分已随 R-B 路线退役；**P5 投递机制的分析仍有效**。
> 现行结论见 [`LUT_RETARGET_LIVE_2026-10-18.md`](LUT_RETARGET_LIVE_2026-10-18.md)。


> 2026-10-16；承接 `HANDOVER_2026-10-16.md`，基线 `eedd885`。
> 本轮执行：读取当日文档、只读分析保存的 rootfs/App/库、修复本地 LUT 后端并做离线回归。未连接相机，未安装、刷写或执行任何休眠程序。

## 1. 本轮结论

1. **保留 P5 的真机失败结论**：该次开机未执行新增 `ExecStartPre`。不继续用正常开关机重复期待同一配置生效。
2. **`.hib_post` 不是已证可用的 App 启动前入口**：标记由 `libhibernation.so::hib_post` 创建，App 的一个已确认直接调用点位于 `UI_Set_Power_Off_Start(bool)`；监控标记的 service 又排在 App 之后。
3. **App 是否重新 exec 仍需直接证据**：仅凭 `/proc/<pid>/stat` 的固定启动拍数、PID和 `ExecStart` 时间记录，不能排除这些记录随快照一起恢复。现有“替换磁盘 App 后每次开机必生效”的推导过强，尚不能据此选择就地落盘。
4. **修复 T5 真代码缺陷**：补传 `--ch1`，把请求通道与硬件观测分开，纠正失败退出码及回退后的旧记账；增加实际 shell/驱动回归，补上原模拟自测的盲区。

## 2. 静态证据身份

| 样本 | SHA-256 |
|---|---|
| rootfs-112 `libhibernation.so` | `fe10b00aea33234bb144c28f14892d4a0583a1b81d27f070a0e7e0f1b5198e03` |
| rootfs-112 `hib_exjob` | `8d57ebdef07a51888faa175c5b5c3a79c832236897596e49f914d573a945ee18` |
| 原版 `di-camera-app` | `55dcc78143724435a2e38b9e0d809960bd728668634bbcf7532ce137f882eb04` |

REA 6.4.0 + Ghidra 12.1.4。库的 objdump 地址为 ELF 符号值；REA/Ghidra 本次将库装载到 `0x10000` 基址，因此符号 `0x19dc` 在分析数据库中为 `0x119dc`。App 地址使用其既有链接 VA，不套用 P7 的 `0x80000000` 换算。

## 3. 恢复标记与快照路径

### 3.1 谁创建 `.hib_post`

REA `hib_post` 伪代码：

```c
device_set_property(5, 5, 0);
FUN_00011970("/tmp/.hib_post");
```

`0x1970` 的 Thumb 反汇编显示该辅助函数 `open` 后 `close`，创建/截断文件；没有执行脚本或提供通用用户回调的代码。

证据 ID：`ev_ac6689461b587d196048f3e286f70d5df41be1344dac763fac96c650955f5b0b`。

App 侧已确认的直接链：

```text
UI_Set_Power_Off_Start(bool)
  call @ 0x12c6b4 -> UI_Hib_Post() @ 0x1c175c
    call @ 0x1c1760 -> hib_post@plt @ 0xad414
      -> libhibernation.so::hib_post
```

这说明标记存在/mtime变化不能单独作为“系统调用了一个 App exec 前的恢复脚本”的证据。本轮没有证明函数只会从关机语境进入，间接/计算调用未解析部分仍未知。

### 3.2 为什么 `hib_post.service` 不满足前置时序

保存的原厂 unit 明确声明：

```ini
After=default.target wm_ready.service deviced.service di-camera-app.service
ExecStart=/bin/sh -c "/sbin/swapoff -a"
```

它负责后处理，没有提供已经验证的 App 前置执行点。新增 service/drop-in 仍受 P5 暴露的 unit 缓存问题约束，不能认为换个 unit 名就解决了问题。

### 3.3 快照发生在 App 服务回调内（后续 REA 已核对函数边界）

App 的 `FUN_001b4f14`（日志标记 `__app_service` / `__ui_camera_power_on`）有以下直接调用：

```text
call @ 0x1b5bb4 -> UI_Hib() @ 0x1c1740
  -> hib@plt @ 0xacf58 -> libhibernation.so::hib
```

**函数归属修正**：早先把此调用归于 `UI_Init_State()`，是误用了 objdump 的最近符号标签。ELF 的 `UI_Init_State` 实际只有20字节（`0x1b4a5c..0x1b4a6f`），并无该调用；REA 将调用点归于 `FUN_001b4f14`。证据见 [原生加载边界推进](NATIVE_UI_LOADING_PROGRESS_2026-10-16.md)；此前的“App内有快照调用”结论保留，但不能继续沿错误函数名推导生命周期。

REA 对 `hib` 的观察：检查 `getenv("HIB")`，随后调用 `hib_part_preproc()`、快照辅助函数，再打印 `snapshot boot start!`、调用 `hib_part_postproc()`，打印 `/opt /opt/usr` 重挂载信息。

快照辅助函数（ELF `0x1a28`）的反汇编包含向 `/sys/power/state` 写入 `disk` 的路径。**本轮仅分析这些指令，没有执行它们。**

证据 ID：`ev_1a75c706cf6a49d38cc4cf20c44274b370586eb49c4c71f02f21fac85e810270`。

由此可提出更保守的解释：App 可能在初始化内部从快照继续运行，而不是每次重新加载磁盘文件。它与 P5 的“PID1持有旧unit定义”观察相容，但本轮静态分析不能代替真机启动路径观测。

`hib_exjob` 的符号/帮助文本主要描述 pagecache 额外数据的准备、提取和打印。不能因为名称含 `job` 或存在 `-r` 就把它当作任意脚本恢复钩子；也不应执行它来“试一下”。

## 4. 对投递候选的重新约束

| 候选 | 本轮结论 | 进入实施前还缺什么 |
|---|---|---|
| 恢复链钩子 | `.hib_post`/`hib_post.service` 尚不能满足前置要求；未找到可直接复用的通用脚本点 | 准确时序、脚本是否每轮从磁盘重读、资源缓存是否已初始化 |
| App 就地落盘 | 离线可准备补丁体，开机必执行新文件尚未证明 | 确认真实 fresh-exec 或已知能重建快照的受控流程；不能依赖 fixed starttime 推断 |
| locale squash 替换 | 可离线重建，当前部署效果不能提前承诺 | 文件系统重新挂载与 gettext 缓存的生命周期；已打开/映射的旧件是否保留 |
| rootfs/SLP 修改 | 属另一个需要完整评估的交付候选 | 资源与快照生成的一致性、校验和恢复流程；不因其它候选失败而自动执行 |

正常关机开机、内核重启和用户态 fresh-exec 必须分开记录。“磁盘文件哈希正确”不等于“进程已装载该文件”；“进程实际映射与磁盘一致”也不能单独证明本轮发生了 fresh-exec。

本轮不撤销 `restart di-camera-app` 的禁用约束，也没有把改共享库或修改快照文件作为可立即上线的方案。

## 5. T5 真实后端缺陷与修正

| 问题 | 原行为 | 本轮修正 |
|---|---|---|
| 通道参数漏传 | shell JSON 固定写 `sel:1`，实际调用 `lutpick apply` 没有 `--ch1`，底层默认 `SEL=0` | 真加载和 dry-run 都传 `--ch1`；新增 `sel_requested:1` |
| 硬件状态被软件推断 | `status` 根据 `current` 文件推导 `sel=1` | `sel:null`、`hardware_verified:false`；软件记账另列 `sel_requested` |
| 模拟器虚构守护 | 模拟 `apply` 自动置 `guard=1`，真实 shell 并未启动守护 | 模拟器与实际保持一致；apply 回报观测到的 guard，不自动增加一次硬件操作 |
| dry-run 文案 | 探测通过也输出“预览生效” | 明确命令返回/探测成功不等于画面已验收 |
| 失败退出码 | apply 分支输出失败JSON后，最后一个 printf 仍使进程退出0 | 返回底层 rc；恢复失败同样非零退出 |
| 回退记账 | restore 后旧 `current` 仍在 | 仅当restore返回成功且守护已停时清空；失败保留现场 |
| PID路径 | 后端用 `/tmp/lutsentinel.pid`，选择器用 `luts/sentinel.pid` | 与选择器的PID文件路径统一 |
| 外部表名 | 可包含路径/意外选项；PC驱动拼成未转义shell字符串 | shell端限定稳定ID字符；PC驱动逐参数shell引用 |

`level:full` 仅表示该后端命令返回成功。新增的 `hardware_verified:false` 必须被上层尊重，不能据此触发“拍摄已验证”状态。`rollback` 走原厂恢复命令且不加载identity；原厂画面是否恢复仍需目视与真实状态判据。

新增 `NXWA_MOD_ROOT`、`NXWA_LUT_MOD` 两个路径覆盖项用于离线记录桩测试；缺省仍使用原相机路径。未将本轮脚本部署到相机，不能沿用旧md5台账认定机端已更新。

## 6. 验证与复现

- 实际执行 `lut_backend.sh` 的8项记录桩回归，加1项PC驱动参数边界测试，共9项；不只测试Python模拟器。
- Python模拟契约8项；shell/Python语法检查。
- 覆盖真实 `--ch1` 转发、dry-run不改状态、硬件未知、命令失败、原厂恢复、恢复失败保留记账、非法输入及远端shell参数引用。
- 记录桩不会调用相机、设备节点、挂载或真实 LUT 工具；不构成硬件回归通过。

```sh
python3 test_server/lutpipe/test_lut_backend_shell.py
python3 test_server/lutpipe/lut_backend.py --selftest
bash test_server/dicam/analyze_resume_chain.sh /opt/nxks2/rootfs-112 <证据输出目录>
# 如复用同目录已有REA证据（脚本仍核验库SHA-256和函数参数）：
NXWA_RESUME_REUSE=1 bash test_server/dicam/analyze_resume_chain.sh /opt/nxks2/rootfs-112 <同一证据目录>
```

证据：[恢复链文件](../../raw8/gates/dicam/resume_chain_2026-10-16/)、[shell回归输出](../../test_server/lutpipe/logs/t5_shell_regression_2026-10-16.txt)。原始REA JSON保留完整函数证据、样本身份和工具限制。

## 7. 下一步

1. UI投递：优先补“恢复后哪个执行/加载边界真的重新发生”的直接证据，再选择挂钩或落盘方式；只读材料不足以裁决时，明确所需最小实机观测，不重复P5安装。
2. LUT：本轮修复脚本先过离线记录桩回归；后续上机先核对机端脚本哈希，再做 `probe`、dry-run和状态检查，不能复用旧`sel=1`输出作为硬件证据。
3. U7写表仍需满足现场和落点条件，本轮没有解除其前置；T7运行时换表和T8成片/原生端到端仍未完成。
