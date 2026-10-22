# dropbear ssh 上机：加密通道 + SFTP + 取图（2026-10-22）

> **背景**：相机原有远程通道只有 telnet(23) 和 FTP(21)，都是明文；且没有 `scp`/`sftp`，取照片只能走 FTP 或 tar over ssh。
> **结论**：**dropbear 2024.86** 跑在 **22** 端口，root ed25519 公钥（`-B` 同时允许空密码）；补自编 **sftp-server** 后 `scp`/`sftp` 可用。
> **状态**：已上线并实测。唯一未验的是**真机重启后能否自启**（只做了段落等价演练）。

---

## 1. 相机 ABI 三件套（本节是通用结论，不止 dropbear）

Tizen 2.2 = **EGLIBC 2.13 / ARMv7 softfp**，宿主是 glibc 2.39 交叉工具链。直接编必炸：

| 坑 | 现象 | 解法 |
|---|---|---|
| `crt1.o` | `version 'GLIBC_2.34' not found` | 用 glibc **2.13 的** `crt1.o / crti.o / crtn.o` |
| `stat()` | `undefined reference to 'stat'` | glibc **2.14 起** `stat` 才是真符号；2.13 只有 `__xstat@GLIBC_2.4`，转发在 **`libc_nonshared.a`**（`stat.oS`） |
| 内核头 | `linux/errno.h: No such file` | `libc6-dev` 不含 uapi，从宿主交叉 include 补 `linux/ asm/ asm-generic/ mtd/ sound/ video/` |

`__libc_csu_init/fini` 也在 `libc_nonshared.a`（`elf-init.oS`）。

sysroot 来源：`old-releases.ubuntu.com` 的 `libc6-dev_2.13-20ubuntu5.3_armel.deb`
（Debian pool 里 wheezy 的 2.13 已被清，只剩 2.7/2.19+）。

**验证纪律**：先编 13KB 的 `abi_probe.arm` 上机跑一轮（getpwnam/openpty/crypt/stat/fork/socket/select/pthread），再编主体。省掉一整天盲试。

## 2. 部署位置与自启

```
机端   /opt/usr/nx-ks/dropbear/   (p14，刷机保留)
       dropbear(240K) dropbearkey(143K) sftp-server(165K) run.sh restart.sh
       dropbear_ed25519_host_key  authorized_keys
SD 母本 scripts/dropbear/         → install.sh 的 cp -ar /mnt/mmc/scripts/* 下发
                                     发布包 ROOT_DIRS 含整个 scripts/，自动入包
公钥   /opt/usr/nx-ks/dropbear/authorized_keys → 每次开机复制到 /root/.ssh/
       （/root → /opt/home/root 在 p11，刷机被重写，所以必须每次恢复）
```

自启挂在 `init.sh` **末尾**（keyscan 之后，坏了也不影响按键）。**三份 init.sh 必须同步**：仓库 / SD `scripts/` / 机端。

## 3. `-O0` 是 Zig 的规矩，不是 gcc 的

项目历史上"交叉编译一律 -O0"的铁律，三条实证全部指向 **Zig 0.13.0 的 ARM 后端**：

- `HANDOVER_2026-10-07.md:79` — `zig.exe ... ★ 必须 -O0（-O1/-O2 编的 ARM 代码在真机段错误 139）`
- `CONSOLIDATED_REPORT_2026-10-05.md:541` — 根因是自己 `IOC` 宏 `(2)<<30` 有符号溢出（UB），Zig 后端在 UB 上生成非法指令
- `WORK_REPORT_2026-10-06.md:244` — 手写 mmap + memset 踩未映射边界，-O2 用更宽的存储指令放大它

dropbear 是 gcc 13.3 编的普通 C（无 mmap、无内联汇编、浮点只在调试计时），**约束不适用**。
`-O2` 静态指标：指令 −40%、体积 −29%、**0 条 VFP/NEON、0 条 ldrd/strd**、GLIBC 需求仍 2.4。

> 完整论证与三版本对比见 `test_server/dropbear/OPT_ANALYSIS.md`。

## 4. ★ 真正的加速点是 nice，不是 -O2

`top` 采样暴露：`dropbear` 是 **NI=19**（最低），`di-camera-app` 是 **NI=-10**，差 29 级。

根因：**Tizen 把 `telnetd` 及其 shell 都设成 nice=19**，dropbear 从 telnet shell 启动就继承了。
（验证：`busybox nice` 不带参数打印 `19`；`awk '{print $19}' /proc/$$/stat` 同为 19。）

**修法**：`scripts/dropbear/run.sh`

```sh
$BB renice 0 -p $$
exec "$D/dropbear" "$@"
```

**不能写成 `nice -n -19`** —— 那是**相对量**：从 telnet(19) 启动恰好 = 0，但从 `init.sh`（nice 0）启动会变成 **-19**，抢爆相机主业务。`renice 0` 是绝对值，安全。

| 配置 | 单张 10.8MB 中位 | 最优 | 批量 16 张 155MB |
|---|---|---|---|
| `-O0` + nice 19（原始） | 838 KB/s | 1027 | 4m43s |
| `-O2` + nice 19 | 909 KB/s | 1301 | — |
| **`-O2` + nice 0** | **1645 KB/s** | **1793** | **1m55s（2.46×）** |

归因：`-O2` 单独 +8%，`nice 19→0` 贡献 +81%。**CPU 抢不到，指令再少也没用。**
完整性：抽样 5 张 md5 与机端逐一比对，全一致。

## 5. sftp-server 必须自编

dropbear 官方**不提供** sftp-server（`default_options.h` 明写），没有它 `scp`/`sftp` 全废。
用 OpenSSH 9.9p1 源码单编（`build_sftpserver.sh`），同一套 ABI 三件套。

**关键约束：根分区是 `ext4 (ro)` 只读** ⇒ `/usr/libexec` 写不进 ⇒
`SFTPSERVER_PATH` 在**编译期**改成 `/opt/usr/nx-ks/dropbear/sftp-server`（`build_dropbear.sh` 里 sed）。
**改这个路径必须重编 dropbear**，不是只换 sftp-server 文件。

> 这条同时修正了旧认知「p10 可写、余量 23MB」——当前挂载是只读的，就地落盘须先 `mount -o remount,rw /`（未验）。

## 6. 另一条踩过的坑：`-march=armv7-a` 与 PIE 冲突

工具链默认 `-march=armv5t`，白白浪费 A9 的 ARMv7 能力。但加 `-march=armv7-a` 后：

```
relocation R_ARM_MOVW_ABS_NC against a local symbol can not be used
when making a shared object; recompile with -fPIC
```

因为 configure 探测到宿主支持 PIE 会塞 `-Wl,-pie`，而 `movw/movt` 的重定位在 PIE 下非法。
修法：configure 之后 `sed -i 's/ -Wl,-pie//g' Makefile`。

**但最终没用 armv7a**：只再省 1.2% 指令，却引入 125 条 `ldrd/strd`（8 字节对齐要求），性价比不成立。

## 7. 使用

```bash
bash tools/nx-ssh.sh                          # 交互 shell
bash tools/nx-ssh.sh cmd 'df -h'
bash tools/nx-photos.sh list | sync | album    # 照片：清单 / 增量取回 / 本地相册
```

图形化（WinSCP/FileZilla）：协议 **SFTP**、主机 `192.168.0.106`、端口 `22`、用户 `root`、**密码留空**（实测空密码可登，不用转 .ppk）。

> 日常手册见 `test_server/dropbear/使用教程.md`。

## 8. 未验证 / 已知限制

- **真机重启后自启**（只做了 `test_autostart.sh` 段落等价演练）。
- 休眠/唤醒后 dropbear 是否存活。
- 无守护进程，崩溃只靠下次 `init.sh` 拉起。
- 无 sftp-server 以外的兼容层，`scp -O`（旧协议）不可用，用默认 SFTP 协议即可。
- 未在 NX1 上验证。
