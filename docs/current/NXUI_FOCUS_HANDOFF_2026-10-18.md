# NXUI 关闭不归还 X 输入焦点 —— 相机原生菜单方向键"有时候"失灵

> 触发：用户反馈「换新 mod 后，进相机菜单（非 mod 菜单）有时无法用上下方向键切换菜单项」。
> 结论：`nxui.arm` 打开时抢走 X 输入焦点，退出时只销毁窗口，从未归还。
> 日期：2026-10-18 · 相机 NX500 1.12 · 未刷固件

---

## 1. 机制

相机没有窗口管理器。X11 的键盘事件（`KeyPress`）只投给**持有输入焦点的窗口**，
不是按坐标投递；触摸（`ButtonPress`）才按坐标投递。

相机原生菜单的上下导航是 JOG/方向键，走的是 X KeyPress（不是触摸）：

| 证据 | 位置 |
|---|---|
| `key_down_callback` 只认 4 个 keysym（`Super_L`/`Super_R`/`Menu`/`XF86PowerOff`），方向键与 JOG 全落 else | `docs/current/HANDOVER_2026-10-07.md:110` |
| 探针注释写明「打开 720x192 override-redirect 窗口并**抢焦点**」，靠抢焦点才能读到键 | `test_server/nxui/keysym_probe.c:4` |

因此：**谁持有焦点，谁就拿走菜单的全部方向键。**

## 2. 缺陷

`test_server/nxui/nxui.c` 修复前：

```c
XMapRaised(display, window); XSync(display, False);
XSetInputFocus(display, window, RevertToPointerRoot, CurrentTime);   /* 抢焦点，无记录 */
...
XDestroyWindow(display, window); XCloseDisplay(display);              /* 只销毁，从未归还 */
```

`RevertToPointerRoot` 的含义是：窗口销毁时焦点交给 root，键盘事件改为跟随指针。
di-camera-app 不会自动抢回焦点，于是：

| 阶段 | 焦点 | 原生菜单方向键 |
|---|---|---|
| 面板未运行 | di-camera-app | 正常 |
| 面板运行中 | NXUI（override-redirect，无 WM 干预） | 被 NXUI 吃掉；`menu` 视图下 `!menu` 条件使其**连处理都不处理**（`nxui.c:526-527`） |
| 面板退出后 | PointerRoot（0x1） | 悬空，直到 App 自己重新 set focus |

### 为什么旧 mod 没有

旧 `mod_gui` 的 `key_down_callback` 把方向键落进 else → `quit_app()`。
按一下就自杀、焦点自动回到相机 —— 用户感受是"按一下没反应，再按就好"。
NXUI 收到方向键不退也不转发，所以是持续失灵。

### 为什么"有时候"

1. 面板其实还活着：关闭需要后端 child 结束（`nxui.c:561` `&& !child`），
   `filmlab.sh` 收尾最长 12 s，这期间窗口仍在最上层且持有焦点。
2. 退出后焦点落 PointerRoot，要等 App 自己重新 set focus（切页/切模式/触摸）。
3. `EV_EV.sh` 是双击 EV 唤起面板，误触门槛低。

## 3. 修复

`nxui.c` 三处，均为新增，不改任何渲染/交互逻辑：

```c
static Window prev_focus; static int prev_revert, focus_saved, focus_restored, panel_unmapped;

/* XMapRaised 之前 */
save_focus();                       /* XGetInputFocus + XSetErrorHandler 保护 */

/* 关闭请求出现时（主循环内） */
if (queue.close_requested && !panel_unmapped) {
    restore_focus();                /* XSetInputFocus(prev_focus, prev_revert) */
    XUnmapWindow(display, window);  /* 后端收尾期间不再遮挡取景 */
    XSync(display, False);
    panel_unmapped = 1;
}

/* 进程退出前兜底（--snapshot / lifetime / signal 路径） */
restore_focus();
```

`XSetErrorHandler(ignore_xerror)` 是必要的：原焦点窗口可能已被入口脚本
（`killall mod_gui`）销毁，`XSetInputFocus` 会报 BadWindow，而 Xlib 默认
错误处理器会直接结束进程。原窗口不存在时回落到 PointerRoot。

## 4. 验证

新增 `test_focus.py`：隔离 X server 上建一个假相机窗口 → 设焦点 → 起面板 →
检查焦点被面板持有 → 等面板退出 → 检查焦点**精确回到那个窗口**。

| 对象 | 结果 |
|---|---|
| 修复后二进制 | `PASS`：`focus_while_open=NXWA-Nuklear`，`focus_after_exit=CAMERA-NATIVE`，`restored_exact_window=true` |
| 阴性对照（`restore_focus` 直接 return） | `FAIL`：`focus not restored: 0x1 != 0x200001` —— 精确复现 PointerRoot 悬空 |

`verify_display.py` 已把 `test_focus.py` 纳入流程，host / arm / focus 三组全 PASS。

## 5. 同批修正（与焦点无关，验证时暴露）

1. **点击已选中配方不重应用**：守卫写成
   `nk_selectable_label(...) && picked && idx != selected`，而 Nuklear 点击时会把
   `*value` 取反并返回 1，于是高亮行点击后 `picked==0` 且 `idx==selected`，两个条件
   同时不成立 → `choose()` 永不调用。与 `choose()` 注释和 README「同配方显式重应用」
   矛盾。改为点击即 `choose(idx)`。
2. **`test_interaction.py` 落后于设计**：保存路径在「已应用」时直接 `prefman save`
   （文档化的快速路径），测试仍按旧语义等待 engine 的 `commit`；保存按钮坐标也停在
   旧布局（y=130 落在状态行，按钮行是 147–173，改为 y=160）。

## 6. 交付物

| 文件 | 变化 |
|---|---|
| `test_server/nxui/nxui.c` | 焦点保存/归还 + 关闭即卸窗 + 点击重应用 |
| `test_server/nxui/test_focus.py` | 新增回归 |
| `test_server/nxui/verify_display.py` | 纳入焦点回归 |
| `test_server/nxui/test_interaction.py` | 保存路径/坐标对齐当前设计 |
| `test_server/nxui/README.md` | 行为说明 + 测试命令 |
| `scripts/nxui/nxui.arm` | 重新交叉编译，md5 `1e7c647505c47702edecc4dfa9fea606` |
| `E:/NXWA/release/NXUI-Nuklear-20261018.zip` | 更新包，sha256 `9f71469f1bbd0eae24255db636eb15108a87ff6560169dba7ecdfac2e8a2b650` |

安装：包解压到 SD 独立目录后 `sh install_camera.sh --enable`。
安装前需关闭面板（安装器会拒绝运行中的实例）。

**未验证**：真机上的焦点归还需要用户在相机上复测（打开面板 → 关闭 → 进原生菜单转滚轮）。
