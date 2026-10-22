# dropbear ssh on NX500 / NX1

给相机加一条**加密远程登录**通道（替代裸 telnet）。纯 C、无依赖、单二进制，登录后即 root。

- 版本：**dropbear 2024.86**
- 二进制：`/opt/usr/nx-ks/dropbear/dropbear`（330 KB）+ `dropbearkey`（192 KB）
- 端口：**22**（Tizen 原生不带 ssh，无冲突）
- 认证：**ed25519 公钥**（root），并保留 `-B` 允许空密码口径
- 日志：`/tmp/db.log`

---

## 1. 为什么不能直接 `arm-linux-gnueabi-gcc` 一把梭

相机是 **Tizen 2.2 / EGLIBC 2.13 / ARMv7 softfp**，宿主是 glibc 2.39 交叉工具链。直接编会在三处炸：

| 坑 | 现象 | 根因 | 解法 |
|---|---|---|---|
| crt1.o | `version 'GLIBC_2.34' not found` | 宿主 crt1.o 里 `_start` 引用 `__libc_start_main@GLIBC_2.34` | 用 glibc **2.13 的 crt1.o / crti.o / crtn.o** |
| `stat()` | `undefined reference to 'stat'` | glibc 2.14 起 `stat` 才是真符号；2.13 只有 `__xstat`，靠 `libc_nonshared.a` 里的 `stat.oS` 转发 | 头文件用 2.13、链接加 **`libc_nonshared.a`** |
| 内核头 | `linux/errno.h: No such file` | `libc6-dev` 不含 uapi 头 | 从宿主交叉 include 补 `linux/ asm/ asm-generic/ mtd/ sound/ video/` |

配套的还有 `__libc_csu_init/fini` —— 同样在 `libc_nonshared.a`（`elf-init.oS`）里，缺了就报 undefined。

**实测结论**：`__xstat`、`openpty`、`crypt`、`getpwnam`、`fork`、`select`、`socket`、`pthread` 在 2.13 上全部落位，探针 `abi_probe.arm` 在机身跑出 `PROBE OK`。

## 2. 构建

```bash
# 一次性的 sysroot 准备（已落地在 dl/）
curl -O http://old-releases.ubuntu.com/ubuntu/pool/main/e/eglibc/libc6-dev_2.13-20ubuntu5.3_armel.deb
dpkg-deb -x libc6-dev_2.13-20ubuntu5.3_armel.deb dl/sysroot-g213
bash add_kheaders.sh          # 补 linux/ asm/ 等 uapi 头

# 正式编译
wsl -d NXKS2 bash build_dropbear.sh
#   → out/dropbear.arm (330K) / out/dropbearkey.arm (192K)
#   → 断言 NEEDED 只有 libc.so.6 / libutil.so.1 / libcrypt.so.1，版本需求仅 GLIBC_2.4
```

关键 flag（`build_dropbear.sh` 里已固化）：

```
CFLAGS  -O0 -nostdinc -isystem <2.13>/usr/include -isystem <2.13>/usr/include/arm-linux-gnueabi
        -U_TIME_BITS -D_TIME_BITS=32 -U_FILE_OFFSET_BITS -D_FILE_OFFSET_BITS=32
        -mfloat-abi=soft -fno-pic -fno-stack-protector
LDFLAGS -nostartfiles -nodefaultlibs -no-pie -Wl,--dynamic-linker=/lib/ld-linux.so.3
        <2.13 crt1.o> <2.13 crti.o>
LIBS    -Wl,--start-group <机身 libc-2.13.so> <libc_nonshared.a> libutil.so.1 libcrypt.so.1
        -Wl,--end-group -lgcc <2.13 crtn.o>
```

configure 选项（都是相机装机环境所迫）：

```
--host=arm-linux-gnueabi --enable-bundled-libtom --disable-zlib --disable-syslog
--disable-shadow --disable-lastlog --disable-utmp --disable-utmpx
--disable-wtmp --disable-wtmpx --disable-pututline --disable-pututxline
```

- `--disable-syslog` ⇒ **没有 `-E` / `-l` 开关**（这点踩过：传 `-E` 会直接 `Invalid option -E` 退出），日志默认走 stderr。
- 没开 zlib ⇒ 传输不压缩，走本地网络无所谓。

## 3. 部署

```
SD 母本  scripts/dropbear/{dropbear,dropbearkey,sftp-server,authorized_keys,restart.sh}
        → install.sh 的 cp -ar /mnt/mmc/scripts/* /opt/usr/nx-ks/
机端     /opt/usr/nx-ks/dropbear/          (p14，刷机保留)
host key /opt/usr/nx-ks/dropbear/dropbear_ed25519_host_key   (首次开机自动生成)
公钥     /opt/usr/nx-ks/dropbear/authorized_keys → 每次开机复制到 /root/.ssh/
```

> SD 卡是 exFAT，`cp -ar` 后文件都是 0644 ⇒ init.sh 里必须 `chmod +x` 兜底，不能只判 `[ -x ]`。

自启动挂在 `/opt/usr/nx-ks/init.sh` **末尾**（keyscan 之后，注入失败也不影响按键）：

```sh
if [ -z "$($BB pidof dropbear 2>/dev/null)" ]; then
    $BB setsid "$DB/dropbear" -F -B -p 22 \
        -r "$DB/dropbear_ed25519_host_key" >>/tmp/db.log 2>&1 </dev/null &
fi
```

三处 `init.sh` 必须同时更新（仓库 / SD `scripts/init.sh` / 机端），否则下次触发引导器会被旧版打回。

## 4. 使用

```bash
KEY=test_server/dropbear/ssh/nx500_ed25519
ssh -p 22 -i $KEY -o IdentitiesOnly=yes root@192.168.0.106
```

或直接用封装好的 `nxssh.sh` / `nxpush.sh`。

**传文件**：`scp` / `sftp` 已可用（见第 6 节）。另有 tar over ssh 作为批量通道（比 scp 快，一次打包）：

```bash
tar cf - -C localdir . | ssh ... "mkdir -p /dest && /opt/usr/nx-ks/busybox tar xf - -C /dest"
```

日常看图/取照片用 `tools/nx-photos.sh list|sync|album`，详见 `使用教程.md`。

## 5. 排障

| 症状 | 查什么 |
|---|---|
| 连不上 22 | `netstat -ltn \| grep :22`；`cat /tmp/db.log` |
| `Invalid option -E` | 本构建无 syslog，去掉 `-E` |
| `Permission denied (publickey)` | `/root/.ssh` 700、`authorized_keys` 600、`/opt/home/root` 不能 group/world 可写 |
| `GLIBC_2.34 not found` | crt1.o 用错了，换 2.13 的 |
| `undefined reference to stat` | 漏了 `libc_nonshared.a` |
| 端口被占 / 起不来 | 换 `-p 2222` 验证；`pidof dropbear` 看残留 |

## 6. sftp-server（scp / sftp 支持）

dropbear 官方**不提供** sftp-server（`src/default_options.h` 里明写 "The sftp-server program is not provided by Dropbear itself"），没有它 `scp` / `sftp` 全部报 `subsystem sftp not found`。

解法：从 OpenSSH 源码单独编 `sftp-server`（`build_sftpserver.sh`），用同一套 ABI 三件套链接，产物 **216 KB，只 NEEDED `libc.so.6`**，版本需求 `GLIBC_2.4/2.6`（都 ≤ 2.13）。

**关键约束：根分区是 `ext4 (ro)` 只读**，`/usr/libexec` 写不进去 ⇒ 不能按默认路径安装。所以路径在**编译期**改掉：

```c
/* src/default_options.h，build_dropbear.sh 里 sed 替换 */
#define SFTPSERVER_PATH "/opt/usr/nx-ks/dropbear/sftp-server"
```

`/opt/usr`（p14）可写、刷机保留，正好。改完要**重编 dropbear**，不是只换 sftp-server。

```bash
wsl -d NXKS2 bash build_sftpserver.sh   # → out/sftp-server.arm
```

实测：`sftp` 能列 `/opt/storage/sdcard/DCIM/100PHOTO`，`scp` 拉 11MB 单张 17 秒（≈660 KB/s）。

## 7. 已知限制

- **传输速度约 1.4–1.6 MB/s**（`-O2` + `nice 0`）。历史配置（`-O0` + 继承 telnet 的 nice 19）只有 0.5–0.8 MB/s。
  **瓶颈不是网络**（WiFi 协商 150 Mb/s，只用了不到 10%），而是**单核 A9 的 CPU 抢占** —— 详见 `OPT_ANALYSIS.md` 第 9 节。
- **必须经 `run.sh` 启动**：Tizen 的 telnetd/shell 是 `nice=19`，直接启动 dropbear 会继承它，速度腰斩。`run.sh` 用 `renice 0` 强制拉回（不能用 `nice -n`，那是相对值）。
- **~2 MB/s 是物理天花板**（详见 `OPT_ANALYSIS.md` 第 10 节）：换 cipher 无收益（散布 > 差异）、绕开加密走 FTP 在真实 JPG 上同样重叠（瓶颈是 SD 读 + CPU 抢占），单命令延迟 ~350 ms 也用不上连接复用。
- **自启已做字节级等价演练**（第 11 节）：直接 source 机身 `init.sh` 的 dropbear 段（1263 字节原样），杀干净后能拉起、`nice=0`、22 在听。真机冷启一次即可闭环。
- **相机休眠断网**：休眠时 21/22/23 全部 CLOSED，属机型行为。
- 无守护进程：dropbear 崩了不会自动重启（只在 `init.sh` 触发时拉起）。
- 客户端会提示 post-quantum KEX 警告（dropbear 2024.86 尚无 PQ KEX），可忽略。
- 未在 NX1 上验证（理论上同一套 Tizen/glibc 2.13 可用）。

## 8. 文件清单

| 文件 | 作用 |
|---|---|
| `build_dropbear.sh` | 交叉编译（sysroot + flags 全固化，含 SFTPSERVER_PATH 改写） |
| `build_sftpserver.sh` | 单编 OpenSSH 的 sftp-server（补 scp/sftp） |
| `build_probe.sh` / `abi_probe.c` | ABI 探针，上机前先验证 |
| `add_kheaders.sh` | 给 2.13 sysroot 补 uapi 头 |
| `使用教程.md` | **日常使用：ssh/sftp/WinSCP/看图** |
| `dl/sysroot-g213/` | glibc 2.13 sysroot（头 + crt + libc_nonshared.a） |
| `dl/openssh.tar.gz` | OpenSSH 源码（sftp-server 源） |
| `ssh/nx500_ed25519` | 客户端私钥（勿外传） |
| `install_key.sh` | 装机端公钥安装（权限修正） |
| `deploy_dropbear.sh` | 二进制落位 + host key 生成 |
| `start_dropbear.sh` / `test_autostart.sh` | 手动起停 / 自启段落演练（旧版） |
| `drill_autostart.sh` | **自启等价演练**：源机身 init.sh 的 dropbear 段（字节级），杀净后重拉 |
| `bench_cipher.sh` | cipher 吞吐横评（换算法是否有收益） |
| `scan_bins.sh` / `analyze_opt.sh` / `test_link.sh` | 三版本横评 / 热点指令对比 / 链接验证 |

机端 `scripts/dropbear/` 母本含：`dropbear` `dropbearkey` `sftp-server` `authorized_keys` `restart.sh`。
