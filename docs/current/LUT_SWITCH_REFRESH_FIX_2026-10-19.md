# LUT 切换修复：登记项与正常重载（2026-10-19）

> **后续偏色修复**：本页只记录切换闭环。随后已定位并修复 RGB/CrCbY 坐标混用，HP5/Fuji400H 候选正常、36 张导入表重建，见 [色彩修复记录](LUT_CRCBY_FIX_2026-10-19.md)。本页未解决 Acros 的描述是当时阶段的边界。

## 问题与结论

用户要求先解决“选择 LUT 后画面不变化”。本次修复只改切换后端，保留现行面板、滤镜文件、转换器和 FilmLab 参数。Acros 严重偏绿另行记录，不能把切换通过当作色彩正确。

原先只修改 `View4[3]`，而当前相机的“屏幕色彩”开启、输出 sRGB，实际选的是 `View4[1]`。此外，改登记项和写槽本身不能保证 P7 重新加载。此前双槽轮换和单槽就地覆盖都没有解决这两项条件。

## 原厂选表证据

在 MD5 为 `712c6fd0a49371ec05ce94c367b0d5c7` 的原始 A2 镜像中，执行真实 ARM 指令：

`0x800e9ff4` 读取 DataManager `108`（OLEDCOLOR）、`50`（COLORSPACE）和 `62`（SMARTFILTERTYPE），结果存入 OrderSheet `+0x54`；`0x800e8524` 读取该值，`0x801b3e08` 附近把它展开为后端 `+0x21/+0x22`，最终进入 `0x803837d0` 的 View 选择。

| 屏幕色彩 | 输出空间 | OrderSheet | View 项 | 原厂槽 |
|---|---|---:|---:|---|
| 关闭 | sRGB | 0 | 3 | A17 |
| 开启 | sRGB | 1 | 1 | A13 |
| 关闭 | AdobeRGB | 2 | 2 | A14 |
| 开启 | AdobeRGB | 3 | 0 | A12 |

模式字节为 14 时会忽略 OLED；智能滤镜枚举 14–18 另走动态表。本轮没有给这些模式臆造通用映射。

复现脚本：`test_server/lutpipe/audit_lut_view_policy.py`；13 个原厂指令执行案例通过，输出在 `raw8/gates/lut/branch_trace_2026-10-19/view_policy.json`。该脚本只模拟 DataManager 边界，不模拟画面或 DMA。

实机 ABA 进一步确认：保持登记表不变，官方 `setusr 108` 关闭时 `load_addr=A18`（当时 View3 已重定向），重新开启时回到 A13。证据为同目录 `oled_aba.log`。

## 后端行为

`scripts/lut.sh` 现在：

1. 读取当前设置和实际 EP 加载源，用目录锁串行执行 apply/off。
2. sRGB、原厂智能滤镜关闭时，选择当前未加载的 A18/A19；写入后校验槽回读。
3. 同时更新 View1、View3 和原有 Still6；回读两个 View 项。
4. 用官方 OLED 设置事件切到另一值再恢复原值，让 P7 走正常加载；不调用裸寄存器 `reload`。
5. 检查实际 `load_addr` 等于新槽，且 OLED 值已恢复，才更新当前名称并输出成功。
6. `off` 同时恢复 View1=A13、View3=A17、Still6 和两个原厂槽，再正常重载。

AdobeRGB 和原厂智能滤镜开启时，apply 在写槽前返回明确错误；这些分支尚未完成实机验收。临时 OLED 变更失败或进程收到终止信号时，退出处理会尝试恢复读到的原值。

## 验证与安装

实际产品 shell 的 8 项边界模拟测试通过：连续三次切换、OLED 关闭、陈旧状态文件、未发生加载、缺少 patch1、写槽失败、不支持/无法读取设置、关闭恢复。测试中的硬件源只在设置事件时更新，因此“只写成功”不能通过。

实机验收目录 `/mnt/mmc/lbf134647`，本地完整日志：`raw8/gates/lut/branch_trace_2026-10-19/refresh_accept.log`。

| 阶段 | 期望表 | 实际 load_addr | 槽回读 |
|---|---|---|---|
| 1 | slide_astia100f | A18 `0x81119f00` | 与源文件全等 |
| 2 | slide_provia100f | A19 `0x8111ec00` | 与源文件全等 |
| 3 | slide_astia100f | A18 `0x81119f00` | 与源文件全等 |
| off | 原厂 | A13 `0x81101e00` | A18/A19 与原厂备份全等，View4/Still6 回原值 |
| 4 | slide_astia100f | A18 `0x81119f00` | 与源文件全等 |

全程 OLED 恢复为用户原值 ON `0x6c0001`。Astia MD5 `922c10b02ae246527267da4f2675ed0b`，Provia MD5 `bb6b1408e706b36a813c2f94bca5b6e2`。这些结果证明后端切换路径和字节一致性。

安装后请用户在现有面板依次选择 Provia、Astia，用户明确反馈：**“能连续切换，画面跟着变”**。面板切换目视验收通过；此反馈不等于 Acros 偏绿已修复。

已同步安装并回读确认三个入口：`/opt/usr/nx-ks/lut.sh`、`/mnt/mmc/lut/lut.sh`、`/mnt/mmc/scripts/lut.sh`，MD5 均为 `b11a614971cb96abe561b4690be30aab`。三处 `nx_regtabwrite.arm` 均为支持 patch1 的既有二进制，MD5 `c0bd1f38c3cbb222690b82f5f393978d`。安装日志为 `refresh_deploy.log`；更新前脚本和状态保存在上述相机会话目录，脚本副本亦已取回本地。

未重启相机 App、未刷固件。保留 Astia，用户已从原面板确认连续切换正常。
