# NX-WA 2.88.0-nxwa.15.1 — 远程通路修复 + 关机取证（debug）

发布日期：2026-11-10
性质：**debug 版**。修一个装完就存在的洞（没有任何远程通路），并给「挑 LUT 时自动关机」
的报告装上一套可回收的现场记录。功能面与 15 完全一致。

## 一句话

`telnet_toggle.sh` 从第一天起就在包里，**`telnetd` 二进制从来没有**；菜单那一行点了没反应。
这一版把远程改成 ssh 的显式入口（状态 + 连接串），并把关机前的最后 30 秒写到 SD 上。

## 一、zip 为什么缺 telnet

三层叠加，每一层单独看都像"能跑"：

| # | 事实 | 后果 |
|---|---|---|
| 1 | `.gitignore` 里有一条**裸 `telnetd`**（本意是挡三星那个 2 MB 预编译件） | 该模式匹配任意层级的同名文件 ⇒ `scripts/telnetd` 从没进过 git |
| 2 | 本地工作树里也**没有**这个文件（机身 `/opt/usr/nx-ks/telnetd` 是早期装的） | 打包脚本按目录走，自然打不出来；`pack_release.py --list` 也不会报错 |
| 3 | `onboard.sh` 见 `$DIR/telnetd` 缺失就 `exit 1` | 连 FTP 都不起；日志只有一行 `!! 缺可执行文件 -> onboard 放弃` |

所以"缺 telnet 脚本"不是某一次打包手滑，是**从 v1 起每一版都缺**。telnet/FTP 已于
2026-11-02 定为退役，因此本版**不恢复**这个二进制，而是把 ssh 做成菜单上看得见的一行。

## 二、改了什么

### 2.1 菜单行：Telnet 开关 → SSH 状态

`gui_tpl.NX500` / `gui_tpl.NX1`（含 `nx-rc/` 两个变体）：

```
button|IP: %%IP%% [%%TN%%]|ssh_hint.sh --ui
```

`%%TN%%` 的值由 `gen_menu.sh` 现场算，从「Telnet开/关」改成「SSH开/关」。占位符名字保留，
用户自定义模板不会失效；命令从 `telnet_toggle.sh` 换成 `ssh_hint.sh --ui`。
判据用 `/proc/net/tcp` 的 `:0016` 监听项，不用 `pidof` —— 相机 busybox 的 `pidof` 在
2026-11-08 已经坑过一次（进程名与实际不符）。

### 2.2 新脚本 `ssh_hint.sh`

| 动词 | 行为 |
|---|---|
| （默认） | 打印 `state/ip/login` 三行，含公钥路径 |
| `--status` | 只打印「SSH开」/「SSH关」（gen_menu 用） |
| `--ui` | 先尝试拉起 dropbear，再在相机屏弹 `ssh root@<ip> 空密码`（5 s） |
| `--start` | 只在没监听时拉起，不弹窗（onboard / 手动排障用） |

### 2.3 `onboard.sh` 改成 ssh 优先

- 先调 `ssh_hint.sh --start`；起了就记 `telnet/ftp : SKIP (retired)`。
- 只有 ssh 起不来**且** `telnetd` 真存在时才回落到老的 telnet+FTP 路径。
- 缺文件不再 `exit 1`，只写日志 —— 装完不会因为一个可选组件难看。
- 结果自检增加 `ssh(22) : RUNNING/DOWN` 与 `/tmp/db.log` 末尾两行。

### 2.4 关机取证 `pwrlog.sh`（debug 版核心）

每 30 s 往 `/mnt/mmc/nx-ks/pwrlog.txt` 追加一行：

```
14:32:10|up=812|pwr=1|ssh=1|ui=1|lut=mono_trix400
```

| 字段 | 含义 |
|---|---|
| `up` | `/proc/uptime` 秒数（比墙上时间可靠） |
| `pwr` | `APPPREF_POWER_SAVE`（0x230）= 自动关机定时器的设置值 |
| `ssh` | 22 端口是否在监听 |
| `ui` | `nxui.arm` 是否在跑（LUT / FilmLab 面板开着） |
| `lut` | `/mnt/mmc/lut/state/current`，当前落地的表 |

开机时 `pwrlog.sh boot` 先记一条 `BOOT` + 上一次断电前的最后 3 行，并读
`APPPREF_CAP_POWER_OFF_STATUS`（0xc2c4）——这是相机自己记的"上次为什么关机"。
`lut.sh` 的 `apply start` / `apply <名字>` / `off` 都会往同一份日志插 `NOTE` 行，
所以**只有 start 没有收尾**就说明断电发生在写表途中。

读法：`sh /opt/usr/nx-ks/pwrlog.sh dump 60`（或直接把 SD 上那个文件拿下来）。

## 三、拿到报告后先做这两个实验

1. **空转 3 分钟**：开面板什么都不按。若同样关机 ⇒ 自动关机定时器（`pwr` 非 0 基本确认）。
   关掉它：`st app set power_timer off`，再浏览 10 分钟。
2. **关秒切**：`LUT_NOKICK=1 sh /opt/usr/nx-ks/lut.sh apply <名>` 逐张切。不复现 ⇒ 问题在
   `nx_lutload` 的 EP 中断/帧同步，不在槽写入。

两条都不复现时再看 `pwrlog.txt` 里最后一行 `lut=` 与 `NOTE` 的配对关系。

## 四、验证

```sh
sh /opt/usr/nx-ks/ssh_hint.sh              # state/ip/login
sh /opt/usr/nx-ks/ssh_hint.sh --status     # SSH开
sh /opt/usr/nx-ks/pwrlog.sh once           # 采一条并回显
sh /opt/usr/nx-ks/pwrlog.sh dump 20        # 看时间轴
sh /opt/usr/nx-ks/onboard.sh; tail -20 /opt/usr/nx-ks/onboard.log
```

回归：`test_server/lutpipe/test_lut_lib.sh` 57 PASS / 0 FAIL（WSL 下跑，Windows Git Bash
会因路径与桩件差异假红）。

## 五、变更文件

```
scripts/ssh_hint.sh        新增
scripts/pwrlog.sh          新增
scripts/onboard.sh         改写（ssh 优先，缺 telnetd 不再 exit 1）
scripts/gen_menu.sh        %%TN%% 改报 ssh:22
scripts/gui_tpl.NX500      IP 行改 ssh_hint.sh --ui
scripts/gui_tpl.NX1        同上
scripts/nx-rc/gui_tpl.NX500.filmlab / .p7   同上
scripts/lut.sh             apply start / apply / off 写 pwrlog NOTE
scripts/init.sh            开机调 pwrlog boot + start
.gitignore                 telnetd 规则加注（仍不入库，写明恢复方式）
README.md / README_EN.md   新增「远程登录（SSH）」一节
VERSION                    2.88.0-nxwa.15.1
```

## 六、校验

| 项 | 值 |
|---|---|
| 包 | `NX-WA-2.88.0-nxwa.15.1.zip` |
| 大小 | 10,152,974 B |
| md5 | `ecf9b1e74f3e61f9faa50cc2cb41b2c6` |
| 文件数 | 372 条目 = 368 主树 + 3 个 `patch-a2/` 附件 + manifest |
| 已含 | `scripts/ssh_hint.sh`、`scripts/pwrlog.sh`（可用 `unzip -l` 核对） |
