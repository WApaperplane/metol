# NXWA 三条主线机上复查（2026-11-02）

## 结论与部署
相机 192.168.0.104：SSH 22 可用；telnet/FTP 未开启，不能把端口关闭当相机离线。
复查前相机无 recipelib.sh，lut.sh MD5 a07ec0cc，nxui.arm MD5 96f5309e，未部署 11-01 成果。
已备份并同步 lut.sh、recipelib.sh、filmlab.sh、nxui.sh、lut/lutmix.arm、nxui/nxui.arm 到 SD 母本与 /opt/usr/nx-ks。
备份：工作区 rea-evidence/20261102-review/before.tar，64,449,536 字节、920 条目；包含旧 mod、母本、LUT 状态与配方库。
逐文件双副本哈希：同目录 deployed-md5.json。未覆盖用户 recipes.json 和 looks 内容。

## 本轮修复
1. lut.sh/order_sync：空的首输入使 FNR==NR 误判第二输入，整库替换漏掉新条目。改用 FILENAME==ARGV[1]；追加列表单独写候选文件，避免读写同一文件。
2. lut.sh/move、fav：机上 BusyBox 1.20.2 的 grep -x 对 warm_sepia 完整行返回不匹配，普通 grep -q 匹配且字节检查为正常 LF。改用 awk 字符串精确比较，避免名字被当正则。
3. nxui.sh：缓存只关注 looks 目录时间，排序只改 state/order，重开仍旧序。加入 order 的时间失效条件；机上以惰性假二进制和隔离状态验证真实启动器。
4. recipelib.sh/restore：原先直接 cp JSON，没有 export，恢复删除前快照后 TXT 仍少一条。改走 commit 校验与重新导出，并在备份轮转前暂存所选快照。
5. recipelib.sh/backup_now：机上同秒连续操作覆盖备份。使用同秒递增、补零序号；轮转到上限后仍保留最新回滚点。

## 验证证据
- LUT 原 33 项通过；新增整库替换复现 35 PASS / 1 FAIL；修后 36 PASS / 0 FAIL。
- FilmLab 原 21 项通过；恢复快照补验复现 21 PASS / 1 FAIL；最终 24 PASS / 0 FAIL，含同秒备份和轮转后回滚点。
- test_lutmix.py：ARM qemu identity、5 个比例、端点与 3 类拒绝全部通过。
- verify_display.py：host/ARM 两目标完整交互与焦点恢复共 19/19 PASS；原始报告 test_server/nxui/out/display-results.json。
- 真实相机临时库：LUT list/move/trash；FilmLab 79→78→79 且 JSON/TXT 同步；启动器排序缓存刷新通过。日志 rea-evidence/20261102-review/device-verification.log。
- 真实相机 lutmix.arm 生成 50% 混合，19,712 字节全部与 Python 参考一致（19,652 字节表体，末条重复三次加 48 字节零尾）。只生成临时表，未把试验混合强写到槽。
- 已读 A17 导出 /mnt/mmc/looks/_stock_A17.bin（19,712 字节），供 strength 0% 基准使用；未强制硬件 reload。
- 最终面板机上 READY：recipes=68，panel=720x208，KEYMAP entries=13（含 KP_Left）。用户确认长按编辑成功、顶栏混合及拖动比例成功。新增 KP_Left 回归后重新构建并复跑 19/19，通过后再次同步面板双副本。
- 实际面板日志出现 OK applied style_matte 等操作成功；不能用此代替混合后的成像验收。

## 剩余工作与约束
三条主线均为局部已验证；不能把本轮部署验收算成全部功能完成。
1. 机内新增：目前无 LUT 导入/混合另存和 FilmLab 新建配方触屏入口。已有文件加入 looks 后可收编，不等于机内创建完成。
2. 混合：已验真实 ARM 数学与触屏入口；混合应用→半按→实拍照片、强度端点和同一次半按能否完成关闭与 reload 尚未闭环。
3. 键位：重新开启 inputlog 后用户按实体 Left，明确采到 KP_Left / keycode83，已加入默认 prev 绑定。旧“方向键均无事件”结论被推翻；其余实体键与转盘需分别采数。日志 left-key.log。新增真实 X 事件回归：Right→velvia50，再 KP_Left→portra400。
4. 本轮库写操作均使用 /tmp 副本，真实用户库的下架/删除没有用于试验；触屏手感结论来自用户实际操作。
5. 优先逐键采 X11 事件，不尝试私有 GPIO/IPCC；不调用强制 LUT reload，不重启 di-camera-app。

## 恢复方式
before.tar 是部署前快照；按需提取六个被更新文件到其原目录，恢复后核 MD5。旧版没有 recipelib.sh/lutmix.arm，若要完全回旧版，需单独下架这两个新增工具；不整包覆盖用户当前配方与 LUT 状态。
本轮未提交 Git；原工作区 zz_invert.bin 删除和 AF 未跟踪文件保持原状。
构建通过；编译器仍报告既有长标签 snprintf 截断警告，未扩展为本轮修复项。

## 补充（11-02 夜间）：构建不可复现，md5 只对同一份产物有效

同一份源码连续跑两次 `build.sh`，md5 会变，差异恒为 **6 字节**，位置在 `.strtab`，内容是 gcc 给临时汇编产物起的随机名 `ccXXXXXX.o`（STT_FILE 符号，由 `.file` 指令带入）。

| 产物 | md5 | 说明 |
|---|---|---|
| 机上 `/opt/usr/nx-ks/nxui/nxui.arm` | `f841b1a6…` | 用户本轮实测的那一版 |
| 仓库 `scripts/nxui/nxui.arm`（同源码重建） | `cad18230…` | 与机上**只差这 6 字节**（`cmp -l` 数出 6 处，偏移 459709–459714） |
| 同源码再建一次 | `68219c70…` | 又是另一组 6 字节 |

⇒ 两条结论：

1. 机上那版与仓库源码构建**功能等价**，不必为了 md5 对不上重新部署。
2. 「本地 md5 == 机上 md5」只在**同一份产物**上成立。重建即换指纹，判部署漂移必须 push 完立刻比，不能拿昨天的哈希去比今天重建的产物 —— 否则每次都会看到「六个文件全不一致」的假警报。

要根治就得不让 gcc 把临时 .o 名写进符号表：分步 `-c -o 固定名.o` 再链接，或链接后 strip 掉 `.symtab`/`.strtab`（这两节合计 67 KB，占面板二进制的 14%）。本轮不动：符号表留着对现场 core/backtrace 有用，而这条噪声有明确解释。

