# NX-WA 2.88.0-nxwa.15.2 — NXUI 默认可用（热修）

发布日期：2026-11-10
性质：**热修**。修一个从 v2 一直带到现在的问题：装完之后新 UI **根本调不出来**，
按 EV+AEL / MENU 出来的是原版 NX-KS 的 popup。功能面与 15.1 相同（含远程通路修复
与 `pwrlog` 关机取证）。

## 一句话

`nxui.sh available` 要求一个**从来没有随包发过**的标记文件才肯放行；现在改成
**默认可用**，只有显式 `nxui.sh disable` 才回到老 popup。

## 一、根因

| # | 事实 | 后果 |
|---|---|---|
| 1 | `available` 判据是 `[ -x nxui.arm ] && [ -f nxui/enabled ] && is_nx500` | 缺 `enabled` 就直接判不可用 |
| 2 | `enabled` 只有 `nxui.sh enable` 会创建，而这条命令只写在开发者 SOP（`test_server/nxui/README.md`、10-17 文档） | 普通用户永远不知道要跑它 |
| 3 | `git log --all -- scripts/nxui/enabled` 为空；把 v2 → 15.1 每个 zip 都翻了一遍，**没有一版含这个文件** | 每台新装机都中招 |
| 4 | 五处入口全部先问 `available`：`EV_AEL.sh` / `EV_EV.sh` / `EV_MOBILE.sh` / `loadgui.sh` / `menu.sh` | 全部走降级分支 → `mod_gui` 老 popup |

所以现象不是崩溃、不是黑屏，而是**正确地走了降级路径** —— 用户看起来就像"这版没做新 UI"。
开发者自己的相机之所以正常，是因为 2026-10-17 验证时手工跑过一次 `enable`，标记留在了 p10 上。

## 二、改法：语义反转

```sh
# 旧
available) [ -x "$BIN" ] && [ -f "$D/nxui/enabled" ] && is_nx500 ;;
# 新
available) [ -x "$BIN" ] && [ ! -f "$D/nxui/disabled" ] && is_nx500 ;;
disable)   : > "$D/nxui/disabled"; rm -f "$D/nxui/enabled" ;;
enable)    rm -f "$D/nxui/disabled" "$D/nxui/enabled" ;;
```

为什么不用"安装时创建 enabled"这种更小的改法：

- `disable` 会变成一次性的 —— 下次插卡增量同步又把它建回来；
- 语义仍然是"必须有一个不存在的文件才能用"，下次谁漏带一次就复发；
- 反转后**默认态不需要任何文件**，"缺文件"不再等于"关闭"。

旧相机上遗留的 `enabled` 被忽略（不再必需），`disable` 时顺手删掉。
NX1 仍然不可用（`is_nx500` 闸门不变，LUT / FilmLab 只在 NX500 上验过）。

## 三、新增排查入口

```sh
sh /opt/usr/nx-ks/nxui.sh diag
# bin      : OK
# model    : NX500
# disabled : no
# enabled  : no
# available: yes
```

`onboard.sh` 把这段写进了 `/opt/usr/nx-ks/onboard.log`，装完不连网也能看。
以后再有"UI 出不来"，先要这一行，不用猜。

## 四、升级与验收

1. 解压到 SD 卡根 → 插卡（增量同步）→ 自动重启。
2. 重启后按 **EV + AEL**：应出现 720×208 的 NXUI 滤镜条（深色、可横向滚动），
   而不是老的浅色 EFL 弹窗。
3. 按 **MENU**：应出现 NXUI 菜单页（标题 `NX-KS / 菜单`）。
4. 想回老 popup：`sh /opt/usr/nx-ks/nxui.sh disable`；恢复：`… enable`。

## 五、验证

- `test_server/nxui/test_enable_gate.py` 6 项：新装可用 / disable 生效 / enable 复原 /
  遗留 enabled 被忽略 / 缺二进制不可用 / diag 输出。
- 连同既有 `test_launcher.py`、`test_lut_launcher.py` 共 **8 tests OK**（WSL，unittest）。
- `test_lut_lib.sh` 57 PASS 不受影响（未改 lut.sh）。

## 六、校验

（打包后回填）
