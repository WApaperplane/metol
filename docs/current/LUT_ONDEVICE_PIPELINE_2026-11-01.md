# 机内 LUT 链路：现状、缺口与补齐方案（2026-11-01）

> 问题（木一）：**现在 cube 转换是怎么做的？能不能机内铺设 LUT、机内转 cube，不再过电脑。**
> 答案分两半：**转换和铺设已经全在机内了**（10-18 起），漏的只有"文件怎么进卡"这一步。

---

## 0. 结论

| # | 命题 | 状态 |
|---|---|---|
| 1 | 机内已有 `.cube` 转换器 `cube2lut.arm`，与 PC 参考逐字节可比（max 2–3） | ✅ 已部署 |
| 2 | 机内已有完整的"转→写槽→改登记表→半按生效"链路 `lut.sh` | ✅ 已部署 |
| 3 | NXUI 的 LUT 面板就是这个链路的前端（`nxui.sh lut` → `lut.sh`） | ✅ 已接入 |
| 4 | **唯一还需要电脑的环节 = 把 `.cube` 放进 `/mnt/mmc/looks/`** | ⚠️ 缺口 |
| 5 | 这个缺口**零开发**即可补上：相机 FTP 21 默认开、可写、根目录就是 SD 卡 | ✅ 手机即可 |

---

## 1. 现在的三条转换路径

| # | 在哪跑 | 工具 | 输入 | 什么时候用 |
|---|---|---|---|---|
| 1 | PC（浮点） | `native_codec.compile_uniform_rgb` / `film_physics.build` | 33³ RGB 设计立方体 | 自研胶片表：33³ 设计 → 一次浮点量化到 17³ native |
| 2 | PC（导入） | `tools/lutgen/web_import.py` | G'MIC 公开胶片 CLUT（13³/33³ Hald） | 外部 LUT 入库，含蓝通道最快的解码坑 |
| 3 | **相机（定点 Q16）** | `cube2lut.arm`（10,828 B，md5 `b798964d…`） | 任意规范 `.cube` | **机内转换**，33³ 用时 0.478 s |

三者的关系：1 和 2 产出的最终都是 19,712 B 槽表；3 是同一件事的 ARM 定点实现，**不需要 PC**。

### 1.1 cube2lut 的格式契约（不是"什么都能吃"）

| 项 | 规定 |
|---|---|
| 输入 | `LUT_3D_SIZE N`，`N ≥ 2`，节点数必须恰为 N³ |
| 轴序 | **R 变化最快**（Adobe 规范）。非规范文件**不纠正**，直接产出错表 |
| DOMAIN | 只接受 `0..1`，否则报错退出（不猜） |
| 1D cube | 明确报错 |
| 输出 | 4,913 × `{Cr,Cb,Y,0}` + 60 B 填充 = 19,712 B |

> 科学计数法（`2.24e-05`）已于 10-18 修复。**旧发布包里的 8,880 B 版本是 RGB 直通，语义完全错**——若哪天从 GitHub release ≤10 重装，会把它装回来。部署前必核 md5 `b798964d`。

---

## 2. 机内链路现状（已经跑通，不是待设计）

```
/mnt/mmc/looks/<name>.cube  ──┐
/mnt/mmc/looks/<name>.bin   ──┤
                              ▼
                       lut.sh apply <name>
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
   cube2lut.arm          nx_slotwrite.arm      nx_regtabwrite.arm
   （如是 .cube）        （写 A18 槽）        （View4 四项 +
   0.5 s / 33³           读回校验              Still6 + BV12）
                              │
                              ▼
                     半按快门一次 → p7 自己 Load
```

| 命令 | 作用 |
|---|---|
| `lut.sh list` | 列 `/mnt/mmc/looks` 里的 look（同名 .cube 优先） |
| `lut.sh begin` | 备份 A18 + 记录还原点（只读，不写寄存器） |
| `lut.sh apply <名>` | 转（如需）→ 写槽 → 改三张登记表 → 提示半按 |
| `lut.sh off` | 登记表回原厂 + A18 回备份 |
| `lut.sh status` | 当前 look / 备份状态 / 引擎指针 |

**NXUI 面板**：`nxui.sh lut` 用 `lut.sh list` 填列表、`lut.sh apply/off` 当执行器——所以面板上"实用功能 → LUT 滤镜"已经是这条机内链路。

---

## 3. 唯一缺口：文件怎么进 `/mnt/mmc/looks/`

现在只能拔卡或从 PC 走 FTP/ssh。三条补齐路径，按成本排：

### 3.1 方案 A：手机 FTP 客户端（零开发，推荐先用）

事实：`onboard.sh` 开机无条件拉起 `tcpsvd -u root -vE 0.0.0.0 21 ftpd -w /opt/storage/sdcard`——
**FTP 21 默认开、可写、根目录就是 SD 卡**。

流程：
1. 相机连上 WiFi（或手机热点），记下屏幕 IP
2. 手机装任意 FTP 客户端（Solid Explorer / FE File Explorer / Documents）
3. 连 `ftp://<相机IP>`，root 空密码
4. 把 `.cube` 拖进 `looks/`
5. 相机面板 → LUT 滤镜 → 选它 → apply → 半按

**全程不碰电脑。**

### 3.2 方案 B：网页上传（约 40 行，产品化）

相机已有 `busybox httpd` + `push-cgi`（8080，`/opt/usr/nx-ks/capdtm/www/cgi-bin/`）。
现有 `push` CGI 把目标路径硬限制在 `nx-rc/web_root/`，**不能写 SD 卡**。

新增一个 `lutpush` CGI 即可：

```sh
# 允许 path=looks/<name>.cube -> /mnt/mmc/looks/<name>.cube
# 校验：只允许 [A-Za-z0-9._-]+\.cube，禁 "/"、".."；单文件 ≤ 2 MB
# 写盘：.part → mv → sync（与 push-cgi 同款原子替换）
# 可选：写完后自动调 cube2lut 预热转换
```

再配一个极简页面（`<input type=file>` + 一个按钮），手机浏览器打开相机 IP 就能传。

优势：不装 App、不输密码、可顺便显示"当前 look / 库列表"。

### 3.3 方案 C：相机直接拉（需确认相机能否出网）

NX500 的 WiFi 是 STA 模式（连路由器）。若路由器有外网：

```sh
wget -O /mnt/mmc/looks/xxx.cube http://<某处>/xxx.cube
```

再往上可以做"LUT 库订阅"：机上一个 URL 清单，开机比对 mtime 自动同步。
**前提未验证**：相机侧的 DNS/路由/证书。总线上一堆 TLS 依赖，`wget http` 比 `https` 稳。

---

## 4. 要"像原生一样用"，还缺四件事

| # | 缺什么 | 现状 | 代价 |
|---|---|---|---|
| 1 | **面板状态回显** | `state/current` 有文件名，但面板未显示"当前：Portra 400" | 小（读一个文件） |
| 2 | **转换进度** | 33³ 要 0.5 s，面板目前会静等 | 小（转成后台 + 轮询） |
| 3 | **库管理** | `/mnt/mmc/looks` 已 60+ 张，只按文件名排序 | 中（分组/收藏/删除） |
| 4 | **强度** | 无（见 `LUT_STRENGTH_MIX_2026-10-31`） | 中（预生成 11 档） |

---

## 5. 风险与坑

| # | 坑 | 说明 |
|---|---|---|
| 1 | **发布包里的旧二进制** | release ≤10 的 `cube2lut.arm` 是 8,880 B RGB 直通版。重装/升级会把它带回来，部署前必核 `b798964d` |
| 2 | **不能从 ARM 侧强制 reload** | 裸写 `+0x00c` + 脉冲会花屏。`lut.sh` 刻意不自动 reload，只能半按 |
| 3 | **`lut.sh apply` 会关"屏幕色彩"** | 首次记原值，`off` 还原。若进程被 kill，可能停在关闭态 |
| 4 | **SD 卡 exfat 重复目录项** | 反复覆盖同名 `.cube`（手机 FTP 尤其容易）会积累重复项。上传用新文件名，定期 `tar` 备份→改名重建 |
| 5 | **同名 .cube/.bin** | `apply` 优先 `.cube`。改了 `.bin` 但目录里还有旧 `.cube`，会被旧 cube 覆盖 |

---

## 6. 建议

| 优先 | 动作 | 收益 |
|---|---|---|
| P0 | **用方案 A 试一次**：手机 FTP 传一张 `.cube` 进 `looks/`，面板 apply | 验证"无电脑"闭环成立 |
| P1 | 若顺手，写方案 B 的 `lutpush` CGI + 上传页 | 手机浏览器一步到位 |
| P2 | 面板加"当前 look"回显 + 转换中提示 | 体验接近原生 |
| P3 | 验证相机出网（`wget` 到 /tmp 看能否成功） | 决定方案 C 可行性 |

---

*生成：2026-11-01 · 基于本地脚本与文档核对；相机当前离线，未上机验证*
