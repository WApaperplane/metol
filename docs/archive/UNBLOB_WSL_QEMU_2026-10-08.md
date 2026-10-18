# unblob × WSL × QEMU：PC 侧相机环境全链路（2026-10-08）

> **一句话**：PC 侧逆向环境建成（WSL2 全数据在 E 盘）——**unblob 26.6.4 把相机 rootfs 全量提取（17,838 文件）**，
> **chroot + qemu-arm 可直接运行相机二进制**（`st` / `bash` / `toybox` 已实测）。
>
> 关联：[`raw8/unblob/SUMMARY.md`](../../raw8/unblob/SUMMARY.md)（扫描汇总）·
> [`raw8/qemu/README.md`](../../raw8/qemu/README.md)（Windows QEMU 分步实验）·
> [`raw8/rootfs/`](../../raw8/rootfs/)（rootfs 导出资产）

---

## 1. 环境总表

| 组件 | 状态 | 位置 / 说明 |
|---|---|---|
| **WSL 3.0.1** | ✅ 全数据在 E 盘 | 发行版 `NXKS2`（Ubuntu 24.04.5）→ `E:\WSL\Ubuntu-24.04`（vhdx 6.2G）；swap → `E:\WSL\swap.vhdx`；C 盘仅 Windows 管理的运行时 App（MSIX，不可迁移） |
| **unblob 26.6.4** | ✅ pipx 安装 | `wsl -d NXKS2 -u root` → `/root/.local/bin/unblob` |
| **qemu-user** | ✅ | `qemu-arm-static` 8.2.2；binfmt 已注册（ARM ELF 直接可执行） |
| qemu-system (Windows) | ✅（补充线） | `E:\qemu` 11.1.0 便携版；ARM Linux 引导 + 挂盘 md5 双端一致（见 qemu/README.md） |
| binwalk v2.3.3 | ✅（Windows 线） | `E:\tools\binwalk-venv`；扫描日志 `raw8/binwalk/` |
| 相机 rootfs | ✅ 已提取（双来源） | WSL `/opt/nxks2/rootfs-112`（slp06 来源）与 `rootfs-v113`（升级包来源）；导出 `raw8/rootfs/rootfs-1.12.tar.gz`（216MB） |
| 分析工作区 | WSL `/opt/nxks2` | `in/`（输入）· `out/`（提取物）· `logs/`（报告）· 全在 E 盘 vhdx 内 |

## 2. 三项核心成果

### 2.1 rootfs 全量提取（★ 双来源交叉验证）

| 来源 | 提取路径 | 文件数 | 体积 | 备注 |
|---|---|---|---|---|
| `slp06`（eMMC 分区 dump 切片） | LZO → ext4(534MB, volume "rootfs") → debugfs 全树 | **17,838** | 489MB | 与实机 1.12 一致 |
| `nx500_v1.13.bin`（官方升级包 SLP 容器） | 同上 | **17,839** | 493MB | 升级包来源 |
| 交叉验证 | `usr/bin/st` md5 | `dec85fa9f9865072439d260d37d73608` | **两边完全一致** | 其余 ±1 文件差异待查 |

- unblob 识别率：slp06 **100.00%**（EXTFS 509MB / LZO 267MB / ELF32 245MB / SQUASHFS 21MB / GZIP / ZIP / ISO / AR）
- ★ 彩蛋：rootfs 内藏 `usr/share/usr_share_locale.squash`（21MB SquashFS 语言包；相机自带 unsquashfs/mksquashfs）

### 2.2 chroot + qemu-arm：相机二进制在 PC 上运行（★ 实测）

```bash
# 配方（WSL 内，root）
R=/opt/nxks2/rootfs-112
cp /usr/bin/qemu-arm-static $R/usr/bin/
chroot $R /usr/bin/qemu-arm-static /bin/bash -c "echo BASH-OK; uname -m"   # → BASH-OK / armv7l
chroot $R /usr/bin/qemu-arm-static /usr/bin/st                              # → 完整 usage 表
chroot $R /usr/bin/qemu-arm-static /usr/bin/st cap                          # → 真实路径报错（无硬件）
```

- `st`（4.6KB 小调度器）实测输出：`Cann't execute capture command over MCB! / IPCC UDD open is failed!!` —— 行为与真机一致（仅缺硬件设备）
- `bash`、`toybox` 同样跑通；`di-camera-app` 定位：`/usr/apps/com.samsung.di-camera-app/bin/di-camera-app`（4.77MB）

### 2.3 unblob × 26 素材扫描矩阵（摘要）

| 类别 | 结果 |
|---|---|
| uImage 内核（p6/p13/slp00/02/03） | zImage → gzip → 内核载荷全链解出；6MB 系（p13/slp00/slp03）含**嵌套 gzip**（450+ 子块） |
| SLP 容器（v1.13.bin） | 切成 3×GZIP(内核) + 3×LZO（rootfs 534MB / opt 4.8MB / backup 37MB），20,380 子任务 |
| rootfs（slp06） | 18,068 子任务；全树提取（见 2.1） |
| p7 / p1 / p2 / p3 / p5 / p8 / p12 / pref / boot0 / boot1 / slp01/04/05/08 | 无可提取容器（纯数据/代码区，与 binwalk 结论一致） |
| 异常 | `NX500_FW_v1.12.zip` 实为**截断包**（7z："Unexpected end of archive"）；`slp06`/`v1.13` exit=1 = 2×符号链接净化 + sasquatch 缺失（内容已完整，无需担心） |

## 3. 命令备忘

```bash
# 进入 WSL（root，默认用户已设为 root）
wsl -d NXKS2

# 脚本模式（★ 必须 MSYS_NO_PATHCONV=1，否则 /mnt/... 参数被 Git Bash 改写）
MSYS_NO_PATHCONV=1 wsl.exe -d NXKS2 -u root -- bash /mnt/e/tools/tmp/xxx.sh

# unblob 复跑单文件
/root/.local/bin/unblob -f -e /opt/nxks2/out/<name> --report /opt/nxks2/logs/<name>.json /opt/nxks2/in/<file>

# chroot 运行相机二进制（见 2.2 配方）；binfmt 生效时可直接：
chroot $R /bin/bash          # （binfmt auto-qemu 模式，需 loader 在 chroot 内可解析）
```

## 4. 坑清单（2026-10-08 新增）

1. **MSYS 路径转换**：Git Bash 直传 `/mnt/...` 给 wsl.exe → 参数被改写（"No such file or directory"）。**必须 `MSYS_NO_PATHCONV=1`**。
2. `wsl --install --no-distribution` **非管理员即可成功**（本机实测；WSL 3.0.1 + 内核 6.18.40.1，无需重启）；发行版安装用 `--location <E盘路径>` 一步到位（官方支持的"不落 C"姿势）。
3. wsl.exe 输出为 **UTF-16LE（自身消息）与 UTF-8（子进程）混合**——解码需先试 UTF-8 再回退 UTF-16（本流程脚本已封装）。
4. unblob 的 JSON 报告是**按子任务的数组**（`[{task, reports[]}]`），不是扁平 chunk 表——统计时按 `FileMagicReport` 聚合。
5. Windows 侧无法原生跑 unblob（25.4.14+ 无 Windows 轮子；旧版依赖 pyperscan/unblob-native 也无）——**结论落空，改走 WSL 是正确的最终解**。
6. `raw8/` 已被 `.gitignore` 整目录排除——所有大导出（rootfs tar、unblob 日志）安全入档，不污染仓库。
7. 解码 Unicode 输出/写 WSL 脚本时的老纪律继续有效：**脚本必须 LF**（本流程全部先 assert 再执行）。

## 5. 资产清单（新增）

```
E:\WSL\Ubuntu-24.04\ext4.vhdx      NXKS2 全系统（6.2G，含全部分析产物）
E:\WSL\swap.vhdx                   36M（.wslconfig 已重定向）
raw8\rootfs\rootfs-1.12.tar.gz     216MB 相机 rootfs 全树（1.12）
raw8\rootfs\MANIFEST-1.12.txt      19,673 条路径清单
raw8\rootfs\tools\                 st.arm / toybox.arm / bash.arm / unsquashfs.arm / di-camera-app.arm
raw8\rootfs\usr_share_locale.squash  21MB 语言包 SquashFS
raw8\unblob\SUMMARY.md             扫描矩阵汇总
raw8\unblob\logs\                  25×json（结构化报告）+ 25×log（终端输出）
WSL /opt/nxks2\{in,out,logs,rootfs-112,rootfs-v113}
```

## 6. 下一步

- [ ] **静态 RE 直通**：对 rootfs 内 `st`/`toybox`/di-camera-app 直接上 Ghidra（文件已可导出到 Windows）
- [ ] 复现既有相机侧结论在模拟环境（如 `st help`、pref 数据流）——为 mod 开发提供无相机联调环境
- [ ] 可选：编译 sasquatch（唯一缺的 unblob 依赖）；手动解 `usr_share_locale.squash` 对照
- [ ] 相机上机纪律不变：先探 21 端口（铁律 90）

> ★ 2026-10-08 下午：前三项已完成（sasquatch 补全 / Ghidra 分析 / PC 复现），详见 [`ST_RE_AND_REPRO_2026-10-08.md`](ST_RE_AND_REPRO_2026-10-08.md)。
