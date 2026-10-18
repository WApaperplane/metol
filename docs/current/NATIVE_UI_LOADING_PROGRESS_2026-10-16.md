# 原生 UI 主线推进：单入口候选与真实加载边界

> ⚠️ **2026-10-18 文档清理：本文结论已被取代。** 原生 UI（EFL）主线已被 NXUI（Nuklear）取代。
> 现行结论见 [`NXUI_NUKLEAR_2026-10-17.md`](NXUI_NUKLEAR_2026-10-17.md)。


> **后续真机更新**：已在用户单独授权下完成11字节私有字典标签实验，目视改名及恢复通过，见 [ONDEVICE_NATIVE_LABEL_RESULT_2026-10-16.md](ONDEVICE_NATIVE_LABEL_RESULT_2026-10-16.md)。本文为前一轮离线边界；标签现在有运行时数据层候选，不再只等待fresh-exec。持久化、PW槽一致性和完整原生确认仍未完成。

> 2026-10-16；承接 [恢复链审计](DELIVERY_RESUME_AUDIT_2026-10-16.md)。
> 本轮仅本地构建、静态分析和ARM/QEMU探针；未连接相机，未写设备、安装、刷写或控制App生命周期。

## 1. 本轮交付与当前完成度

原生路线保持不变：复用三星图片向导、输入与选择事务，不新增外挂窗口。首探收敛到**一个入口、一个PW预设**，再扩展三槽及LUT组合。

| 项 | 本轮产物 | 仍不能声称 |
|---|---|---|
| 单入口离线候选 | CUSTOM1显示名、同ID七维预设、兼容性和校验清单 | 原生确认事件已接通、机内槽内容已一致 |
| 字典加载边界 | 相机glibc 2.13 + QEMU：冷/热字典、语言往返、新目录绑定及新进程对照 | 真机App已观察到相同状态、菜单已重绘 |
| 快照调用归属 | REA函数证据，纠正最近符号标签导致的误归属 | App每次开机fresh-exec、存在可用前置钩子 |
| 只读现场采集 | 精确exe识别、磁盘/进程文件/映射/字典及unit采集；PC严格判读 | 文件身份等于驻留代码、mount等于UI生效 |

T3仍是“离线候选 + 待实机接通”，不是原生UI完成。T7/T8和U7写表前置保持不变。

## 2. CUSTOM1单入口候选包

位置：[native-entry-portra400](../../fw/v1.12/dicam/native-entry-portra400/README.md)。

- `di-camera-app.mo`：仅`CAP_MENU_CUSTOM_MODE_1 → Portra 400`；CUSTOM2/3和其余词条保持原厂。
- `preset.json`：`nxwa.preset/1`；ID=`portra400`；PW=`106/100/93/11/9/9/8`；需要A2；不含LUT。
- `entry_manifest.json`：源MO/配方库/目标App身份、改变词条和文件SHA-256；投递、槽一致性、原生输入、预览/JPEG及恢复均未验证。
- `SHA256SUMS`与说明；**没有安装器、启动钩子或自动动作**，不得送入旧M2部署链当成可直接安装的包。

生成器为 [native_ui_entry_pack.py](../../tools/native_ui_entry_pack.py)，复用现有`mo_patch`的追加式工艺和全词条验证，而非再写一套MO处理。

只接受已知原版zh_CN MO（MD5 `f2d60cd2f2687de43089729fb06f436c`），拒绝未知来源、非法ID/标签、PW越界、未映射字段和已有输出目录。名称与PW值从同一条配方生成，但**这不写入机内槽，也不证明原生菜单重选会读到相同值**。

候选MO为172,861B（原版172,850B），SHA-256：
`cce910fad71f78f4a20c7179a2f53fc9aeecc3c2409281ab9dc84272d07aae39`。
2194词条逐条对比通过，仅目标词条改变；hash/二分路径离线验证及候选包校验和通过。

```sh
python3 tools/native_ui_entry_pack.py --source-mo /mnt/e/tmp/dicam_zh_CN.mo \
  --recipe portra400 --out /tmp/nxwa-native-entry-new
```

输出必须为尚不存在的目录。首探不同时给槽2/3贴配方名，避免显示承诺超出目前独立存储/应用证据。

## 3. 相机glibc缓存实验：投递不能只看文件

新增 [m2_cache_probe.c](../../test_server/dicam/m2_qemu/m2_cache_probe.c) 与 [test_m2_cache.py](../../test_server/dicam/m2_qemu/test_m2_cache.py)。

探针直接链接保存的相机`libc-2.13.so`，版本输出为2.13；用`qemu-arm-static -L <rootfs>`运行，不使用chroot、mount或设备节点，也不改保存的rootfs。字典替换和编译产物全部位于临时夹具目录。它是gettext探针，**不是运行完整di-camera-app，更不是板级UI虚拟机**。

相机libc SHA-256：`198a7b52e68df955de2573557644720e76580aae489e3785bb9afd80ad6f2e9c`。

| 条件 | 实际查询结果 | 工程含义 |
|---|---|---|
| 已绑定目录，但首次查询前换成新MO | 新名 | 冷字典路径有机会生效，不要求一定是新进程 |
| 先查询旧MO，再用rename替换路径 | 旧名 | 路径已换不等于已加载字典刷新；这是晚bind风险的代表实验，不是实际mount实验 |
| 再调用相同textdomain/绑定同目录 | 旧名 | 不能作为缓存清理方法 |
| LC_MESSAGES切C再切回zh_CN.UTF-8 | 旧名 | 不能把原厂语言菜单往返当作已证重载方案 |
| 绑定另一个含新MO的目录，再查询 | 新名 | 公共API具备可验证的软件边界；App中如何调用、旧控件是否重绘仍未知 |
| 新进程读取替换后的原路径 | 新名 | 有明确fresh-process条件时，文件替换可被新查询读取 |

旧三词条样机和新CUSTOM1候选各跑6项测试，均通过；候选轮同时确认CUSTOM2/3仍为原名。

```sh
python3 test_server/dicam/m2_qemu/test_m2_cache.py \
  --sample fw/v1.12/dicam/native-entry-portra400/di-camera-app.mo \
  --report /tmp/nxwa-entry-cache-report.json
```

这收紧了M2投递完成标准：必须证明“首次加载之前投递”或“已有进程确实走了新绑定/重载并重绘”，不能以文件哈希、挂载和正常开关机替代。

## 4. REA交叉核对：纠正函数边界

目标仍为原版App：SHA-256 `55dcc78143724435a2e38b9e0d809960bd728668634bbcf7532ce137f882eb04`。

1. `UI_Init_State()` 的ELF符号值为`0x1b4a5c`，大小**20字节**，结束`0x1b4a6f`。REA伪代码仅三个Init调用后返回；没有`UI_Hib`。证据：`ev_4c7b61324b8463ef0d5764e62581709abc42e121a0a96b4ef1896dc8684c3e8d`。
2. 查询实际调用指令`0x1b5bb4`，REA归于`FUN_001b4f14`，函数范围`0x1b4f14..0x1b5dff`。其日志标记`__app_service`，首次服务分支中有`__ui_camera_power_on`，依次调用Before_SnapShot、sysmap初始化、`UI_Hib`，返回后处理升级标记和开机状态。证据：`ev_04925caf702937d73da364c1a3115603da53569ecab6b148b5be4bb3be53d8f1`。
3. `0x1b5ff4 → ui_shell_init()`属于`FUN_001b5f28`（`0x1b5f28..0x1b6003`），日志标记`__app_create`；它在`main`的`0x1b60e0`有数据引用，符合回调注册形式，而非已解析的直接调用边。证据：`ev_02f04418685f7f93401862a18c62c04630e8e383c05b2b7e05d5c1154b957bf3`。**不能仅因地址较大就认定它在本次`UI_Hib`返回后才运行**；创建与服务是不同回调，真实调度和每次恢复是否重新执行仍待证。

此前恢复审计中“`UI_Init_State`内调用快照”的归属已在原文纠正。objdump为无符号内部代码显示最近的导出符号加偏移；它不是函数边界证明。后续函数命名必须同时核对符号大小、反汇编与REA函数体，不用最近符号直接命名匿名函数。

`CAPPGUIEtc::SetLanguage(int)`的保存反汇编显示`setlocale(5, ...)`，未在该函数中看到公共字典重绑定调用。此为限定函数范围的观察，不是“整个语言切换路径不存在其它回调”的证明。

## 5. 下一次只读现场采集件

[probe_native_loading.sh](../../test_server/dicam/probe_native_loading.sh)只向stdout输出，默认不写日志；不调用`st`、systemctl、mount、kill或设备节点。通过`/proc/*/exe`的准确文件名找App，避免cmdline里出现`di-camera-app`的诊断shell被误选。多进程候选、采集中进程变化、缺字段均保留未知。

[native_ui_loading.py](../../tools/native_ui_loading.py)在PC端解析保存输出，明确区分：

- 当前路径指向哪个文件；
- 进程`exe`引用哪个后备文件；
- 实际驻留代码/字典是否更新——**此采集器不作证明**；
- 原生标签及交互是否可见——**必须另行观察**。

即使exe/目标哈希相同、unit有P5行、字典路径等于部署件，报告仍保持`fresh_exec=unknown`、`running_code_verified=false`、`native_ui_verified=false`。固定PID/starttime或变化的boot_id均不自动解锁投递。

现场只读运行需先按既有门控核对现场；若须把脚本放到相机，那个文件投递须单独记录，不能混称零写入。推荐从PC会话向`sh`送脚本文本，返回数据保存在PC；不自动运行本步骤，也不要求用户现在重启相机。

```sh
# 相机端脚本的输出取回PC后，再在PC执行：
python3 tools/native_ui_loading.py saved_probe_stdout.txt
```

旧`dicam_patch_status.sh`已纠正“挂载/目标哈希/P5行在位=已生效”的提示，并修正进程识别；未部署本轮版本。

## 6. 验证记录与下一顺序

- 单入口生成器：8项，自包含合成字典、身份拒绝、值域、仅改单项、可复现、校验和及禁止覆盖。
- 加载采集/判读：9项，临时伪`/proc`夹具；包括不写夹具、伪进程、多候选、竞争、缺信息和禁止过度宣称。
- 相机glibc/QEMU：6项×2轮；真实目标MO及相机libc，不模拟翻译函数。
- 全部新shell语法通过；仓库既有脚本检查`0 fail / 0 warn`。
- 原始函数证据、反汇编、测试输出和缓存报告：[native_ui_loading_2026-10-16](../../raw8/gates/dicam/native_ui_loading_2026-10-16/)。

下一顺序：只读现场材料核对 → 裁决真正可用的加载/重载边界与撤销方式 → 仅CUSTOM1名称首探 → CUSTOM1槽内容/重选/返回验证 → 再扩三槽和PW/LUT统一确认。

若只读材料仍不足以证明边界，应明确提出所需的最小受控实验及风险，不能自动升级为App就地替换、重建快照、共享库修改或刷写SLP。当前没有给这些操作放行。
