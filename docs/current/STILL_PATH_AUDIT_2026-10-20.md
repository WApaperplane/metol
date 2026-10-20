# Still 成片无 LUT：选表分支漏改 BV12（2026-10-20）

> **现象**（木一，2026-10-20 早上）：v2.88.0-nxwa.8 上机后取景器 LUT 显示正常，拍出来的 JPEG **没有滤镜效果**。
> **结论**：不是「Still 没被消费」，而是 **Still 有两条互斥的选表分支，v8 只改了其中一条**。
> 屏幕色彩（OLED）开启时，Still 走 **BV12（`0x80382B00`，12 项）** 而不是 Still6（`0x80382C5C`，6 项）。
> **状态**：离线修复已完成（写表工具 + `lut.sh`），**尚未上机验证**。

---

## 0. 一句话

`lut.sh apply` 把 `View4[1]`/`View4[3]`/`Still6` 都指向了 A18，
但拍照时 p7 的选表实现 `0x80382B30` 在 **`+0x21 == 1`（屏幕色彩开启）** 时从 **BV12 十二项**取表地址 ——
那 12 项仍是原厂，所以成片永远是原厂表。取景器走 `View4[1]`（已改），故显示正常。

---

## 1. 机制：Still 的两条互斥分支

`CBackend_3dlut_Still::_load`（`FUN_0011e678`）→ `FUN_0009a3c8(ctx, +0x22, +0x21)`：

```c
if (param_3 == 1)                    // param_3 = 后端对象 +0x21
    uVar7 = FUN_003829a4(iVar2, param_2);          // ★ BV12：0x80382B00，12 项
else {
    uVar7 = (param_2 == 1) ? 0x81110500 : 0x8111EC00;
    if (0x4af < 亮度) {                            // 1199
        if (测光 < 0x47) uVar7 = (param_2==1) ? 0x81106B00 : 0x81119F00;
        else             uVar7 = (param_2==1) ? 0x8110B800 : 0x81115200;
    }
}                                                  // ★ Still6：0x80382C5C，6 项
```

| 分支 | 条件 | 登记表 | 项数 | v8 是否重定向 |
|---|---|---|---:|---|
| A | `+0x21 == 1` | `BV12 @0x80382B00` | 12 | ❌ **没有** |
| B | `+0x21 != 1` | `Still6 @0x80382C5C` | 6 | ✅ 有 |

View 侧不受影响：`FUN_0009a3e8(+0x22, +0x21)` 只看 `View4` 四项，v8 已补 `[1]`，所以取景正常。

## 2. 为什么 `+0x21` 在木一的机器上是 1

`+0x21` 由 OrderSheet 展开（`0x800E9FF4` 读 DataManager 108/50/62 → `0x800E8524` → `0x801B3E08` → `+0x21/+0x22`）。
离线执行原厂指令得到的完整矩阵（`raw8/gates/lut/branch_trace_2026-10-19/view_policy.json`）：

| 屏幕色彩 OLED | 色彩空间 | OrderSheet | `+0x21` | `+0x22` | View 项 |
|---|---|---:|---:|---:|---:|
| 关 | sRGB | 0 | **0** | 0 | 3（A17） |
| **开** | **sRGB** | **1** | **1** | **0** | **1（A13）** |
| 关 | AdobeRGB | 2 | 0 | 1 | 2（A14） |
| 开 | AdobeRGB | 3 | 1 | 1 | 0（A12） |

⇒ 屏幕色彩开启 + sRGB 时 `+0x21 == 1`：**View 读 `View4[1]`（v8 已修），Still 读 BV12（v8 漏修）**。
两者用的是同一个设置位 —— 这正是 10-19 发现「当前机器取景读 `View4[1]`」的同一原因。

### 2.1 为什么 10-18 的负片实验能成功

10-18 10:11 那轮把 `Still6` 六项全指向负片槽，成片确实变负片（`SAM_0044.JPG`）。
当时取景走的是 `View4[3]`（= OLED 关闭，`+0x21 == 0`）⇒ Still 走 Still6 ⇒ 改 Still6 有效。
**同一份代码，设置不同，分支不同**。今天 OLED 开着，改 Still6 就落空了。

## 3. 修复

| 件 | 改动 |
|---|---|
| `test_server/lutpipe/nx_regtabwrite.c` | `do_still` 泛化为 `do_table(action, off, n, bak, name, slot)`；新增 `bv-status/bv-set/bv-write/bv-restore`（12 项）；`status` 现在同时打印 BV12 |
| `scripts/lut/ nx_regtabwrite.arm`、`nx_regtabwrite1.arm` | 重新交叉编译，md5 `01e7362dc739eb960ff2b1e2376082c5`，11,968 B，ARM EABI5 soft-float |
| `scripts/lut.sh` | apply 同时写 **Still6 + BV12**（各自独立备份/还原）；`off` 两条都还原；写备份前 `mkdir -p` 备份目录 |
| `scripts/lut/still_probe.sh` | 新增只读诊断：三张表 + EP 寄存器 + OLED/CS/SF 设置 + apply 日志 + 自动判决 |
| `test_server/lutpipe/test_regtabwrite.py` | 12 项守卫全 PASS（新增 BV12 偏移/原厂值断言、两表共用一个写入器断言） |

设计取舍：**不做「判断走哪条分支再改哪条」**，而是两条都指向同一工作槽。
理由：`+0x21` 会随用户改设置而变，按分支改等于把「下次改设置就失效」写进代码；全指则与人设置无关。
代价：Still 的 18 个档位（6+12）在 apply 期间全部同一张表 —— 这正是自定义 LUT 的语义。

## 4. 上机步骤（相机上线后）

### 4.1 先判别（只读，2 分钟）

```sh
sh /mnt/mmc/lut/still_probe.sh
```

看 §4 结论段：

| 输出 | 含义 |
|---|---|
| `STILL6 -> A18 : 6/6` + `BV12 -> A18 : 0/12` | ★ 就是这个 bug（v8 原状），继续 4.2 |
| `6/6` + `12/12` | 登记表已全覆盖，问题在下一层（槽内容/拍照期重走 View），另查 |
| `0/6` | apply 的 still 段没落地，看 `still.log` 的 FAIL/备份目录 |

### 4.2 部署修复

FTP 投递到 `/mnt/mmc/_xfer/`，telnet 安装（相机上 LUT 工具在 **`/mnt/mmc/lut/`**，不是 `/opt/usr/nx-ks/lut/`）：

```sh
cp /mnt/mmc/_xfer/nx_regtabwrite.arm  /mnt/mmc/lut/nx_regtabwrite.arm
cp /mnt/mmc/_xfer/nx_regtabwrite1.arm /mnt/mmc/lut/nx_regtabwrite1.arm
cp /mnt/mmc/_xfer/lut.sh              /mnt/mmc/lut/lut.sh
cp /mnt/mmc/_xfer/lut.sh              /opt/usr/nx-ks/lut.sh
cp /mnt/mmc/_xfer/still_probe.sh      /mnt/mmc/lut/still_probe.sh
chmod +x /mnt/mmc/lut/*.arm /mnt/mmc/lut/*.sh /opt/usr/nx-ks/lut.sh
md5sum /mnt/mmc/lut/nx_regtabwrite.arm   # 期望 01e7362dc739eb960ff2b1e2376082c5
```

### 4.3 验收判据

| # | 动作 | 判据 |
|---|---|---|
| 1 | `sh /opt/usr/nx-ks/lut.sh off` → `apply <黑白表>` → `status` | `STILL6` 六项与 `BV12` 十二项**全部** = `0x81119f00` |
| 2 | 半按一次 | 取景器变黑白（保持 v8 的成果） |
| 3 | 拍一张 JPEG | ★ **成片变黑白**（本次修复的唯一验收点） |
| 4 | `lut.sh off` → 半按 → 再拍 | 成片回原厂；`status` 里 BV12 十二项回原厂值 |
| 5 | 关闭「屏幕色彩」再 `apply` + 拍 | 同样有滤镜（此时走 Still6 分支） |

第 5 步是这次修复的稳健性判据：**改设置换分支后仍生效**。

## 5. 边界与未验

1. 本轮**未连相机**：修复是离线完成，`BV12` 全指后 Still 是否真的跟随，只有第 4.3 步第 3 条能回答。
2. `BV12` 的 `FUN_003829a4` 按 BV 档（`(100·S−8000)/16` + 阈值）选 index；全指后 index 无意义，但**未验**硬件是否对非原厂地址组合有额外约束。
3. 备份目录 `/mnt/mmc/nxwa_regtab_20261018/` 若被清理，`bv-set` 会重新抓一份「当前值」当原厂 —— 与 Still6 原有局限相同，未变坏。
4. 全部写入仍是 RAM-only，重启回镜像原厂。
5. AdobeRGB（`+0x22 == 1`）分支同样读 BV12，本次一并覆盖；但 AdobeRGB 下 View 侧走 `View4[2]`/`[0]`，v8 未改，**AdobeRGB 的取景仍不生效**（未修，属另一项）。
6. **v8 遗留的失效测试**：`test_server/lutpipe/test_lut_sh_rotation.py` 11 项全红，`setUp` 仍在断言 v7 双槽脚本（`CAP=/usr/bin/st`、`active`/`a18`/`a19`、OLED 事件重载）。v8 已退回单槽，被测实现不存在 —— 与本次改动无关，需单独决定删除还是重写为单槽断言。

---

*2026-10-20 · 离线修复 · 证据：`view_policy.json`、`P7_3DLUT_PATHS_2026-10-07.md §3.2`、`LUT_REGTAB_READ_2026-10-18.md §2`、`test_regtabwrite.py 12/12`*
