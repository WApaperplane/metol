# A2 补丁镜像（p7 段）—— 刷入教程

> 本目录的 **`p7_a2.bin`** 是 `NXWA-A2` 补丁的 **p7 分区镜像**（12,075,648 B）。
> 它是「**全 7 维 PW 一键**」的固件前提：写入相机的 p7 分区后，`filmlab.sh` 的直推可**一次写入全部 7 个维度**（R/G/B/HUE/SAT/SHARP/CON）。
> 未刷 A2 时一切照旧（直推段静默无效，不会崩），全维效果仍可用「画面向导 → 自定义1」保底。

> ★ **2026-11-11 口径更新**：远程登录只剩 **ssh（22 端口）**，telnet / FTP 自 2026-11-02 起退役。
> 老教程里"点 IP 行开 Telnet"、"FTP 传文件"都作废；本文所有命令都在 **ssh 会话**里执行。

---

## 0. 先分清两份东西

| 物件 | 大小 | 用途 | 从哪拿 |
|---|---|---|---|
| `p7_a2.bin`（本文主角） | 12,075,648 B | **通道 A**：只写 p7 分区，1 秒完成 | 每个发布 zip 内的 `patch-a2/p7_a2.bin` |
| `slp_a2_p7_v117.bin` | 352,121,435 B | **通道 B**：整包走官方刷机链 | Release 附件（目前挂在 `v2.88.0-nxwa.2` 页 Assets，含 `.md5`） |

两者**刷进 p7 的内容等价**。选一个即可，不要都做。

## 1. 前置条件

- **仅 NX500**（NX1 无此构建），基于官方固件 **1.12** 验证。
- 相机已装 mod，且能 **ssh 登录**：`ssh root@<相机IP>`，回车用空密码。
  - 不知道 IP / 连不上：相机菜单 → `IP: x.x.x.x [SSH on]` 点一下会弹连接串；
  - 或先跑 `sh /opt/usr/nx-ks/ssh_hint.sh --start` 把 dropbear 拉起来。
  - 想用密钥而不是空密码：见 README 的「远程登录（SSH）」。
- 电量充足（写入只有约 1 秒，但要保证中途不断电）。

### 1.1 把镜像放到相机的 SD 卡上（二选一）

```sh
# 方式①：解压发布包到 SD 卡根 —— 相机里就是 /mnt/mmc/patch-a2/p7_a2.bin
#         （NX-WA-<ver>.zip 已自带 patch-a2/ 目录，不用单独下）

# 方式②：直接 scp（PC 上执行）
scp patch-a2/p7_a2.bin root@192.168.0.106:/mnt/mmc/
```

> SD 卡根 = 相机里的 `/mnt/mmc`。两条路等价，方式①对没有 ssh 客户端的机器更省事。

## 2. 三个数字先对上

| 项 | 期望值 |
|---|---|
| 文件大小 | `12075648` 字节 |
| md5 | `712c6fd0a49371ec05ce94c367b0d5c7` |
| 目标分区 | `/dev/mmcblk0p7`（约 30 MB，p7 = ISP 固件分区） |

```sh
md5sum /mnt/mmc/patch-a2/p7_a2.bin      # 必须等于 712c6fd0…
cat /proc/partitions | grep mmcblk0p7   # 确认分区存在，block 数约 30720（=30 MB）
```

md5 对不上就别往下走：重新拷贝（exFAT 上大文件偶尔拷坏），或回 PC 重新解压。

## 3. 刷入（ssh 会话里逐条执行）

```sh
# 3.1 备份当前 p7 —— 回退唯一依赖，务必执行
dd if=/dev/mmcblk0p7 of=/mnt/mmc/p7_backup_$(date +%s).bin bs=1M
sync
ls -l /mnt/mmc/p7_backup_*.bin          # 记下文件名，回退要用

# 3.2 写入 A2（约 1 秒）
dd if=/mnt/mmc/patch-a2/p7_a2.bin of=/dev/mmcblk0p7 bs=1M
sync; sync; sync

# 3.3 回读校验（12 MiB = 镜像 12,075,648 B + 分区尾部 507,264 B 零区）
dd if=/dev/mmcblk0p7 bs=1M count=12 2>/dev/null | md5sum
#     期望：69050a17ea9fdbcdab4cf32e7b5ffdb2
```

⚠️ **执行前把设备名读两遍**：写的是 `/dev/mmcblk0p7`。写成 `mmcblk0p1` 之类的后果不可逆。

### 3.4 回读不是 `69050a17…` 怎么办

先别慌，分两种情况：

| 现象 | 含义 | 处理 |
|---|---|---|
| 与期望完全不同 | 写入没完成 / 写错文件 | 重跑 3.2 一次，再回读 |
| 只差一点点、且这台机器以前刷过别人做的 p7 | 分区尾部（镜像之外那 507,264 B）不是零 | 用下面的分段比对确认镜像段本身正确即可 |

```sh
# 分段比对：前 11 MiB + 剩余 541,312 B，两侧分别相等就说明镜像写对了
# 分区侧
dd if=/dev/mmcblk0p7 bs=1M count=11 2>/dev/null | md5sum
dd if=/dev/mmcblk0p7 bs=1M skip=11 2>/dev/null | head -c 541312 | md5sum
# 镜像侧（对照）
dd if=/mnt/mmc/patch-a2/p7_a2.bin bs=1M count=11 2>/dev/null | md5sum
tail -c 541312 /mnt/mmc/patch-a2/p7_a2.bin | md5sum
```

两对数字分别相同 ⇒ 镜像段写得没问题，结尾差异只是历史残留，不用管。

## 4. 生效

- **正常关机 → 开机**（p7 固件在下次启动加载，正常开关机即可）。
- ⛔ **绝对不要** `systemctl restart di-camera-app` —— 实测会**卡死整机**，只能断电。

## 5. 验证成功

```sh
sh /opt/usr/nx-ks/filmlab.sh pwpush portra400 --yes    # 一键直推一条配方
sh /opt/usr/nx-ks/filmlab.sh check                     # 7 维 vs 配方槽位
```

- 画面**立即变化** + `check` 通过 = 成功。
- 画面没变：先回头看 3.3 回读、以及是否已经「正常关机开机」过一次。

## 6. 回退

```sh
dd if=/mnt/mmc/p7_backup_<时间戳>.bin of=/dev/mmcblk0p7 bs=1M
sync; sync; sync
```

然后**正常关机 → 开机**。也可以直接重刷官方 1.12 整包（会一并覆盖 p7）。

## 7. 风险与纪律

- 写入期间**不要断电、不要拔卡**；接外接电源更稳。
- 官方固件升级会重写 p7 ⇒ **升级后要重新刷 A2**。
- 分区 30 MB 比镜像 12 MB 大，镜像之后的区域保持原样，属正常。
- 社区构建，自担风险；出问题先按 §6 回退，不要连续重试。

## 8. 数字台账

| 物件 | md5 |
| --- | --- |
| `p7_a2.bin`（本目录） | `712c6fd0a49371ec05ce94c367b0d5c7` |
| 12 MiB 回读（镜像 + 尾部零区） | `69050a17ea9fdbcdab4cf32e7b5ffdb2` |
| 完整刷机包 `slp_a2_p7_v117.bin`（352 MB，Release 附件） | `44b61efc0625874b62ef6a45517ffda8` |

## 9. 原理一句话

A2 在 p7 里加了一段「档位池直写」通道：外部发 `seq 0x134..0x13A`（7 个原始值）+ `0x13B`（触发）→ p7 写参数槽 → 走官方「档位应用」链把 7 维一起送进 ISP —— 于是「一键」达成。细节见 `docs/current/A2_PATCH_DESIGN_2026-10-14.md` 与 `A2_READBACK_VERDICT_2026-10-15.md`。
