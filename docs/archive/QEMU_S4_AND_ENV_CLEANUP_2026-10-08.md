# QEMU S4 全系统链路 + PC 侧资源归位（2026-10-08）

> 上一篇：`UNBLOB_WSL_QEMU_2026-10-08.md`（WSL/unblob/rootfs 提取）
> 本文件回答两件事：**① S4 做完了没有（做完了）；② 这次的东西有没有落在 C 盘（没有，除一项系统级组件）。**

---

## 一、S4 结论：纯 Windows（零 WSL）跑通「固件 → 解压 → 挂载 → chroot → 跑相机二进制」

### 1.1 链路

```
宿主机  raw8/fw/slp06_280505658.bin  (280.5MB, 整文件是一个 lzop 流)
        └─ 只读挂入 guest ──────────────►  /dev/vdX
宿主机  E:\qemu-vm\scratch.img        (1.2GB 稀疏)
        └─ 读写挂入 guest ──────────────►  /dev/vdY
guest   unlzop -c < /dev/vdX > /dev/vdY        # 280MB → 534MB ext4 镜像
guest   mount -t ext4 /dev/vdY /mnt            # 485M / 已用 458M / 97%
guest   chroot /mnt <相机二进制>                 # 原生执行，不用 qemu-user
```

### 1.2 实测（`raw8/qemu/boot_s4c_chroot_SUCCESS.log`）

| 检查项 | 结果 |
|---|---|
| guest 内 `unlzop` | rc=0，**18.1 秒**（`up 2.01 → 20.15`，≈30 MB/s） |
| 解压后 superblock magic | 写前 `0000` → 写后 **`53ef`** ✓ |
| `mount -t ext4` | rw 成功，uuid `dae4e423-9f91-4ce7-a7f6-05856079f99d` |
| 文件总数 | **16021**（`usr/bin` 531 项 / `usr/lib` 1162 项） |
| `chroot /mnt /bin/bash` | `CHROOT-BASH-OK` / `uid=0(root)` / `arith=42` |
| `chroot /mnt /usr/bin/st` | 打印完整内置命令表（24 条）— **相机二进制原生跑通** |
| `chroot /mnt /tmp/ksfilm.arm` | 我们交叉编译的 ARM EABI5 softfp 产物打印 usage ✓ |
| `chroot /mnt /tmp/mcbtest.arm` | rc=143（`timeout 40` 杀掉）— **预期**：无真实 MCB 硬件，阻塞等 ipcc 应答 |
| `chroot /mnt /tmp/toybox.arm uname` | `toybox: Unknown command uname`（toybox 可跑，只是未编入 uname） |

### 1.3 ★ 新证据：`st` 运行时内置命令表（原生环境，独立于 Ghidra）

```
help  readl  writel  dump   gpio   hdmi   log    lcd    cap    pmu    clk
thread key   firmware util  app    leak   devman stlcd  bat    rtc    tbm
micom  misc  oic    dvfs   adc
```
共 **24 个 built-in**。此前 `MCB_PROTOCOL_AND_ST_TABLE_2026-10-08.md` 里靠 gdb 经 GOT 直取
拿到的是 `top_cmd_list` 的 **28 条**（含 `shell_exec` / 别名等非 built-in 入口）；
两条路径互为交叉验证，且证明 **`st` 在干净 rootfs 里零依赖可跑**。

### 1.4 ★★ S4 两个新坑（务必记住）

| # | 坑 | 现象 | 解法 |
|---|---|---|---|
| 1 | **virtio-blk 设备号顺序不可依赖** | 声明 `hd0=slp06, hd1=scratch`，guest 里 **vda 拿到 scratch(1.2GB)、vdb 拿到 slp06(280MB)** —— 顺序被反 | 一律**用魔数自识别**：读 4 字节找 `89 4c 5a 4f`（lzop magic）定位源盘，另一个就是目标盘 |
| 2 | **ext4 需要 `crc32c` crypto 驱动** | 只装 `ext4/jbd2/mbcache/crc16` 时，dmesg 报 `EXT4-fs (vda): Cannot load crc32c driver.`，mount 报 `No such file or directory`（极具误导性） | 补 `kernel/crypto/crc32c_generic.ko` + `crc32_generic.ko`，并把 `modules.alias` / `modules.builtin` 一起拷进 initramfs（否则 `modprobe crc32c` 无 alias 可解析） |

**幂等设计**：init 先读目标盘 offset 1080 的 2 字节 superblock magic，若已 `53ef` 就**跳过 18 秒解压**直接挂载
⇒ 第二次起约 2 秒进入 chroot。

### 1.5 复现

```bash
# ① 模块准备（一次性）：ext4 jbd2 mbcache crc16 crc32c_generic crc32_generic
#    + modules.dep / modules.alias / modules.builtin
#    落点 E:\qemu-vm\initrd-src\lib\modules\6.12.110-0-lts\   （见 raw8/qemu/step23b|23c*.sh）

# ② 打包
python E:/tools/tmp/pack_initramfs.py

# ③ 启动
E:/qemu/qemu-system-arm.exe -M virt -cpu cortex-a15 -m 512M \
  -kernel E:/qemu-vm/vmlinuz-lts -initrd E:/qemu-vm/initrd.cpio.gz \
  -append "console=ttyAMA0 earlycon=pl011,0x9000000 rdinit=/init panic=-1 loglevel=7" \
  -drive "id=hd0,file=D:/download/NX-KS2-88/raw8/fw/slp06_280505658.bin,format=raw,if=none,readonly=on" \
  -device virtio-blk-device,drive=hd0 \
  -drive "id=hd1,file=E:/qemu-vm/scratch.img,format=raw,if=none" \
  -device virtio-blk-device,drive=hd1 \
  -nographic -no-reboot > E:/qemu-vm/boot_s4.log 2>&1
```

### 1.6 价值定位

- 这是**「没有相机也能跑相机用户态」的通用调试底座**，替代此前依赖 WSL 的
  `qemu-arm-static -L rootfs-112 <bin>` 手工流程。
- 补充事实：相机 rootfs 的动态加载器是 **`/lib/ld-linux.so.3`（软浮点 glibc 2.13）**，
  **不是** `ld-linux-armhf.so.3`。软浮点 EABI5 用户态可直接跑在 hardfloat 内核上，无需兼容层。
- 与 mod 的关系：mod 部署/联调阶段可先在 guest 里跑通，再上机（降低铁律 90「先探 21 端口」的试错成本）。

---

## 二、PC 侧资源归位与 C 盘审计（2026-10-08）

### 2.1 处置动作（**移动**，不是删除）

| 源（C 盘） | 去向（E 盘） | 大小 | 说明 |
|---|---|---|---|
| `C:\Users\31623\AppData\Local\Temp\wsl-crashes\*.dmp` × 4 | `E:\tools\tmp\wsl-crashes\` | **690 MB** | 我们跑 `qemu-arm-static` 时的崩溃转储（`st log` 段错误那批） |
| `…\Temp\nxks2_docs.log` / `nxks2_folders.txt` / `slp.py` | `E:\tools\tmp\xtemp\` | ~3 KB | 本次调查的临时输出 |
| `C:\Users\31623\.config\binwalk\` | `E:\tools\binwalk-venv\home\.config\binwalk\` | ~0 | binwalk 配置目录 |

binwalk 之所以会写 C 盘，是因为它用 `os.path.expanduser('~')` 定位配置（Windows 上即 `USERPROFILE`）。
**已把包装器改成给子进程私有 HOME**（`E:\tools\binwalk-venv\Scripts\binwalk.cmd`）：

```bat
set "USERPROFILE=E:\tools\binwalk-venv\home"
set "HOME=E:\tools\binwalk-venv\home"
set "XDG_CONFIG_HOME=E:\tools\binwalk-venv\home\.config"
```
**已验证**：重跑 `binwalk --help` 后 `C:\Users\31623\.config\binwalk` **未再出现**。

### 2.2 C 盘剩余项（全部已确认，仅一项无法消除）

| 路径 | 大小 | 可迁移性 | 结论 |
|---|---|---|---|
| `C:\Program Files\WSL` | **1.2 GB** | ⛔ **不可迁移** | 卸载表显示 `Windows Subsystem for Linux 3.0.1.0`，`InstallDate=20261008`，目录创建时间 `2026-10-08 08:13:41`（即本次会话装的）；MSI 机器级安装 + `WslService` 服务，微软只支持 `%ProgramFiles%\WSL`。**唯一替代是卸载 WSL**（代价：unblob 失去 Linux 环境，需改走 QEMU x86 VM） |
| `C:\Users\31623\.wslconfig` | 76 B | ⛔ 不可迁移 | WSL 只从该固定路径读；内容是 `swapFile=E:\WSL\swap.vhdx`（**把 swap 已指向 E**） |
| `C:\Users\31623\.config\` | ~0 | ✅ 已清空相关项 | 仅剩 `clash/`、`fish/`、`wecom/`（非本次产物） |
| `C:\Users\31623\AppData\Local\Temp\` | 117 MB | ✅ 本次产物已清 | 余量为其它程序所有 |

### 2.3 E 盘落点（本次全部产出）

```
E:\WSL\Ubuntu-24.04\            6.2 GB   WSL NXKS2 发行版 vhdx（注册表 BasePath 已核 = E:\WSL\Ubuntu-24.04）
E:\WSL\swap.vhdx                 36 MB   WSL swap
E:\qemu\                         QEMU 11.1.0 便携版
E:\qemu-vm\                      实验室：kernel / initramfs 源与产物 / scratch.img / 全部 boot 日志
E:\tools\binwalk-venv\           binwalk v2.3.3 独立 venv + home/（配置）
E:\tools\unblob-venv\            unblob venv（Windows 侧入口，实际解包在 WSL 内）
E:\tools\tmp\                    全部中间脚本（wsl_step*.sh / pack_initramfs.py / 迁移件）
E:\ghidra_out\                   Ghidra 导出（di-camera-app 7,073 函数等）
```

**WSL 数据面 100% 在 E**（发行版 vhdx 6.2G + swap 36M），符合「WSL 不得铺设在 C 盘」的硬要求；
仅**程序本体**（系统级 MSI）留在 `C:\Program Files\WSL`。

---

## 三、遗留 / 待决

| 项 | 状态 |
|---|---|
| `E:\tools\tmp\wsl-crashes\`（690 MB 崩溃转储） | 已从 C 盘移出；**内容已无价值**，可随时删（需你确认） |
| `C:\Program Files\WSL`（1.2 GB） | **待你决策**：接受（推荐，WSL 要用来跑 unblob）或卸载（则 unblob 改走 QEMU x86_64 VM 路线） |
| S4 未覆盖 | `st cap iqr` 等**需要真实 ISP/MCB** 的命令在 guest 里必然失败 —— 这是设计边界，不是缺陷 |
| 下一步候选 | 用 S4 底座反查 `pref` 分区（p2）与 `/opt/usr`（p14）——它们在 rootfs 镜像里**不存在**（是独立分区），可按同样方式挂入 |

---

*生成：2026-10-08 · 分支 `nx-ks2` · 证据：`raw8/qemu/boot_s4*.log`*
