# NXUI 启用门禁：为什么用户只看到老 popup（2026-11-10）

> **一句话**：`nxui.sh available` 要求 `/opt/usr/nx-ks/nxui/enabled` 存在，
> 而这个标记只有开发者 SOP 里的 `nxui.sh enable` 会创建 —— release 包从 v2 到
> 15.1 **一次都没带过**。于是新装机上所有 NXUI 入口都走降级分支，出来的是
> `mod_gui` 的原版 NX-KS popup。

## 1. 现象

用户报「拉不起最新版 UI，只出原版 NX-KS 的 popup 窗口」。不是报错、不是黑屏 ——
是**正确地走了降级路径**，所以看起来像"这个版本根本没有新 UI"。

## 2. 调用链

五处入口，全部先问 `available`：

| 文件 | 触发 | 降级后 |
|---|---|---|
| `EV_AEL.sh` | 按住 EV + AEL | `mod_gui gui_filmlab1b`（配方页 popup） |
| `EV_EV.sh` | 单独 EV | `nxui.sh menu` → 失败 → `menu.sh` 路径 |
| `EV_MOBILE.sh` | EV + WiFi | 老的 telnet/IP 槽脚本 |
| `loadgui.sh` | 菜单入口 | `mod_gui gui_ini`（主菜单 popup） |
| `menu.sh` | 菜单入口 | `mod_gui gui_ini` |

判据在 `scripts/nxui.sh`：

```sh
available)
    [ -x "$BIN" ] && [ -f "$D/nxui/enabled" ] && is_nx500
```

`BIN=/opt/usr/nx-ks/nxui/nxui.arm` —— 这个二进制**在包里**（每版都在，479 KB），
`install.sh` 的 chmod 兜底也会给它可执行位。卡住的只有那个标记文件。

## 3. 证据

| 检查 | 结果 |
|---|---|
| `git log --all -- scripts/nxui/enabled` | 空 —— 该文件从未入库 |
| 15.1 及之前每个 `dist/NX-WA-*.zip` 里搜 `nxui/enabled` | **全部没有**（.2 起逐版核过） |
| `grep -rn "nxui.sh enable"` | 只出现在 `test_server/nxui/README.md` 与 `docs/current/NXUI_NUKLEAR_2026-10-17.md` |
| `install.sh` / `init.sh` 是否创建 | 没有 |
| 开发者自己为什么能用 | 10-17 上机验证时手工跑过一次 `enable`，文件留在 p10 上了 |

## 4. 修法：语义反转

旧：「必须 `enable` 才可用」。新：**默认可用，只有显式 `disable` 才关**。

```sh
disable)   : > "$D/nxui/disabled"; rm -f "$D/nxui/enabled"; killall nxui.arm ;;
enable)    rm -f "$D/nxui/disabled" "$D/nxui/enabled" ;;
available) [ -x "$BIN" ] && [ ! -f "$D/nxui/disabled" ] && is_nx500 ;;
diag)      打印 bin/model/disabled/enabled/available 五项 ;;
```

为什么不用「安装时创建 `enabled`」这种更小的改法：

- `disable` 会变成一次性 —— 下次插卡增量同步又把它建回来；
- 语义仍然是「需要一个不存在的文件才能用」，下次谁再漏带一次就复发；
- 反转后**默认态不需要任何文件**，缺文件不再等于关闭。

旧相机上遗留的 `enabled` 被忽略（不是必要条件），`disable` 时顺手删掉。

## 5. 排查入口

以后遇到"UI 出不来"，一条命令定位：

```sh
sh /opt/usr/nx-ks/nxui.sh diag
```

```
bin      : OK
model    : NX500
disabled : no
enabled  : no
available: yes
```

`onboard.sh` 也把这段写进了 `/opt/usr/nx-ks/onboard.log`（装完就能看，不用先连上）。

## 6. 回归

`test_server/nxui/test_enable_gate.py` 6 项：新装可用 / disable 生效 / enable 复原 /
遗留 enabled 被忽略 / 缺二进制不可用 / diag 输出。
连同 `test_launcher.py`、`test_lut_launcher.py` 共 **8 tests OK**（WSL，unittest）。

## 7. 边界

- NX1 仍然不可用（`is_nx500` 闸门）—— LUT / FilmLab 只做过 NX500 实机。
- 反转后，**以前正常用的用户**（有 `enabled`）行为不变。
- 以前手工 `disable` 过的用户（没有 enabled、也没有 disabled）会被重新启用 —— 可接受，
  因为旧 `disable` 本来就不是持久语义。
