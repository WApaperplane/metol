# st 逆向 + sasquatch 补全 + PC 复现（2026-10-08 下午）

> 承接 [`UNBLOB_WSL_QEMU_2026-10-08.md`](UNBLOB_WSL_QEMU_2026-10-08.md)（环境搭建）。本篇覆盖三项收尾：
> **sasquatch 补全 · Ghidra 静态分析 · chroot/qemu 复现**。
> 资产：`raw8/repro/`（复现产物）· `E:\ghidra_out\st.arm_dump\` 与 `di-camera-app.arm_dump\`（导出）

---

## 1. sasquatch 补全（unblob 依赖闭环 ✅）

- 源码：**onekey-sec/sasquatch**（★ WSL 无法直连 GitHub → Windows 侧下载经 `/mnt/e` 送入）
- 构建：`make -C squashfs-tools` → `/usr/local/bin/sasquatch`（LE 版）
- ★ 验证：`unblob in/usr_share_locale.squash` → **SQUASHFS_V4_LE 100%，提取 583 文件 / 79.18MB**，`ExtractorDependencyNotFound` 错误消除
- v4be 未构建：onekey / devttys0 源码均无 BE 构建目标；我们全部 squashfs 均为 LE ⇒ **无需求**

## 2. Ghidra 静态分析（Windows，headless）

### 2.1 st（4.6KB，★ 未剥离符号）—— 完整解出

**st = 表驱动调度器**（`04_decompiled.c` 全文 <3KB）：

```c
main(argc, argv):
  if (argc < 2) shell_simple_help(&top_cmd_list);        // 打印用法（命令表生成）
  else:
    在 top_cmd_list（{name, handler} 8B 步长表，"end" 终止）中查 argv[1]
    ├─ 未找到          → "%s: test command not found!"
    ├─ handler == NULL → "%s : not implement command !!!"
    └─ 命中 → process_option[i] 分流：
         0 → shell_exec(argc, argv, &top_cmd_list)      // 本地执行
         1 → shell_sndmsg(argc, argv, ...)              // ★ 消息路径（MCB/IPCC）
```

- 依赖 24 个 .so（libshell-command / libudd5 / libdiosal / libmulticore-bridge …）
- ★ **与复现互证**：`st cap` 在 qemu 里报 `Cann't execute capture command over MCB! IPCC UDD open is failed!!`
  = sndmsg 路径确凿（cap 类命令即"发消息给 MCB"，无硬件即失败——行为与真机一致）
- 导出：`E:\ghidra_out\st.arm_dump\`（22 函数 / 81 字符串 / 8 反编译）

### 2.2 di-camera-app（4.77MB）

- 导出：`E:\ghidra_out\di-camera-app.arm_dump\`：**9,258 函数 / 29,264 字符串 / 400 函数反编译**（截断上限）
- 重跑/加深：`-postScript DumpELF.java <outDir> <maxDecomp> <nameFilter>`

### 2.3 新工具

`test_server/isp/ghidra/DumpELF.java`——通用 ELF 导出脚本（函数/字符串/段/反编译；支持上限与名字过滤），已适配 Ghidra 12.x API。

## 3. PC 复现（chroot + qemu-arm）

### 3.1 ★★ 最高成就：ksfilm 胶片引擎全流程（4 配方）

```bash
R=/opt/nxks2/rootfs-112
qemu-arm-static -L $R /opt/nxks2/t1/tools/ksfilm.arm in.jpg out.jpg portra400
```

| 配方 | 输出 | 大小 |
|---|---|---|
| Kodak Portra 400 | out_portra400.jpg | 316,908 B |
| Ilford Tri-X 400（--grain 1）| out_trix400.jpg | 344,598 B |
| Fuji Velvia 50 | out_velvia50.jpg | 572,858 B |
| Ilford HP5 Plus | out_hp5.jpg | 329,827 B |

引擎自报：`[NX-KS2] filmsim: 900x600 -> out.jpg recipe=… (…)`；产物见 `raw8/repro/ksfilm_pc_test/`
⇒ **无相机联调闭环成立**：改引擎 → PC 秒级跑批 → 再上机。

### 3.2 相机工具离线留档（`raw8/repro/`）

- `st_help_offline.txt`（命令全表）· `st_cap_offline.txt`（MCB 报错复现）· `prefman_usage_offline.txt`（11 个 Preference ID + load/save）

### 3.3 ★ 双路线与坑（新增）

| 路线 | 命令 | 适用 |
|---|---|---|
| **-L 路线（推荐）** | `qemu-arm-static -L <rootfs> <any.arm> …` | 任意 ARM 二进制直接跑，无需投放进 rootfs |
| chroot 路线 | 投放文件到 rootfs 内**存在的**目录再 `chroot $R /usr/bin/qemu-arm-static <path>` | 针对 rootfs 内自带工具（st/prefman/busybox）最顺 |

- ★ 坑：**1.12 rootfs 提取树没有 `/root` 目录**——投放 `/root/` 会静默失败，qemu 报 `Error while loading … No such file or directory`（误导性强）。用 `/tmp` 等存在目录即通。
- zig 产物为动态链接（`/lib/ld-linux.so.3` + libc.so.6 softfp）→ 与相机 glibc 2.13 兼容 ✓（-L 指向 rootfs 即可解析）
- 全部操作脚本留档：`E:\tools\tmp\wsl_step{11..15}*.sh`

## 4. 意义与下一步

- **三线全闭环**：静态（Ghidra 素材就绪）↔ 动态（qemu 可运行）↔ 真机（铁律 90 上机）
- 可选深化：di-camera-app 全量反编译（改 `maxDecomp` 重跑）；st 的 `top_cmd_list` 全表提取（读 .data 段）；MCB 消息协议在 libmulticore-bridge.so 内
- 相机上机纪律不变：先探 21 端口（铁律 90）
