# NXUI 面板打不开：busybox setsid 多套一层（2026-10-19）

## 现象

机身上按 EV+WiFi（或主菜单「实用功能 → LUT 滤镜」）**完全没有反应**：屏幕不弹面板，
`/tmp/nxui.log` 只有一行，且不产生任何窗口。

## 根因

`scripts/nxui.sh` 末行：

```sh
$BB setsid "$BB" "$BIN" "$@" >> /tmp/nxui.log 2>&1 &
```

`busybox setsid` 的语义是 `setsid PROG ARGS`，只 exec **一个**程序。
多套一层 `$BB` 后，实际执行的是：

```
/opt/usr/nx-ks/busybox /opt/usr/nx-ks/nxui/nxui.arm ...
```

busybox 把 `nxui.arm` 当成 **applet 名**，直接报 `nxui.arm: applet not found` 退出。

正确写法：

```sh
$BB setsid "$BIN" "$@" >> /tmp/nxui.log 2>&1 &
```

## 引入点

旧版是 `$BB setsid "$BB" nice -n 15 "$BIN"` —— 中间那层 `nice` 是合法 applet，
它会 exec 后面的 `nxui.arm`，所以**一直是能跑的**。

10-19「字体链收敛」把 `nice -n 15` 删掉（nxui 自己设了绝对优先级 19），
但忘了同时去掉 `"$BB"` ⇒ 多出来的那层从"无害"变成"把二进制当 applet"。

该改动一直**未提交**，所以 `git diff` 里 HEAD 仍是带 `nice` 的正确版本。

## 为什么测试没抓到

`test_launcher.py` 的 busybox 桩把未知 applet 当作"直接执行"：

```sh
*) exec "$cmd" "$@" ;;
```

于是 `busybox nxui.arm` 在桩里照样执行了 nxui.arm，测试全绿。
真实 busybox 是报错退出，两者行为相反。

另外启动器是 `setsid ... &` 后立即 `exit 0`，原测试只断言 `returncode == 0`，
即使二进制没起来也永远为 0。

## 修复

1. `scripts/nxui.sh`：去掉多余的 `"$BB"`，并加注释说明为什么不能再套。
2. `test_server/nxui/test_launcher.py`：
   - busybox 桩的未知 applet 改成真实语义 —— 打印 `applet not found` 并 `exit 127`；
   - 补 `cksum` 分支（脚本里用到）；
   - 新增断言：日志里必须出现 `UI`（证明 nxui.arm 真被执行）。
   - 阴性对照已验：把该行改回 bug 版 → 测试报
     `AssertionError: 0 not greater than or equal to 1 : launcher must actually exec nxui.arm`。

## 上机验证（2026-10-19 19:0x）

```
pidof nxui.arm = 437
READY backend=nuklear-xft live=1 recipes=43 panel=720x192 nice=19 tier=1 sel=0
INIT recipes_ms=1 display_ms=25 font_ms=317 backend_ms=13 map_ms=18
FIRST_FRAME process_ms=517 launch_ms=955
BACKEND kind=6 ok=1 elapsed_ms=1392 output=
```

`nxui.sh available` → OK；面板正常渲染 43 个 look。

## 部署位置

| 路径 | md5 |
|---|---|
| `/opt/usr/nx-ks/nxui.sh` | `bb5b608b0934dacb59b57691385b2e8e` |
| `/mnt/mmc/scripts/nxui.sh`（SD 母本） | 同上 |

## 附带校准

10-19 部署只覆盖了 5 个核心文件，另有 12 个仍停留在 10-06 母本版本，
本轮一并推送到 `/opt/usr/nx-ks/` 与 `/mnt/mmc/scripts/`：
`EV_AEL.sh` `EV_EV.sh` `1HDR.sh` `gui_focus.NX500` `gui_ini.NX500` `loadgui.sh`
`menu.sh` `telnet_toggle.sh` `fstack.sh` `brb.sh` `nrec.sh` `zoomzoom.sh`。
机端备份在 `/opt/usr/nx-ks/nxui/backup-20261019c/`。
