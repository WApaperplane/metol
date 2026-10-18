# FilmLab 配方库第二批（+27 条 → 95）2026-10-11

> 用户诉求：**「写更多滤镜色彩配方」**；范围定案：**小幅扩（20~30 条）**，
> 聚焦 **经典彩色负片全谱 + 反转片 E-6 / 电影卷**；归档要求：**仓库 commit + Release 附件**
> （上一批 68 条虽随 `v2.88.0-nxwa.1` 的 zip 交付，但**没有独立可下载的配方库资产**，
> 本次单列 release 附件，根治"配方无从单独取用"的问题）。

---

## 1. 结果速览

| 项 | 值 |
|---|---|
| 配方数 | **68 → 95**（+27） |
| 菜单分页 | 18/页 → **6 页** |
| 权威源 | `scripts/filmlab/recipes.json` |
| md5 | `7ee00bbd23aeb57b4eb61935cc6b1682` |
| 引擎兼容 | `flab.py lint` **PASS**（0 FAIL / 1 warn=分页提示） |
| 离线回归 | `flab_sim.sh` **12/12 PASS**；`check_scripts.py` **0 fail** |
| 追加器 | `test_server/filmlab/add_batch2_recipes.py`（幂等，可重跑） |
| 归档 | 分支 commit `9da9d0b` + tag `filmlab-recipes-v2`（已 push）；release 附件见 §6 |

---

## 1.5 归档状态（2026-10-11）

| 步骤 | 状态 | 备注 |
|---|---|---|
| 仓库 commit（`scripts/filmlab/recipes.json` + 追加器 + 本文档） | ✅ 已 push | commit `9da9d0b`（`6adfa31..9da9d0b nxwa`） |
| tag 锚定 | ✅ 已 push | `filmlab-recipes-v2` → `9da9d0b` |
| Release 附件（`recipes.json` + `recipes.txt`） | ⏳ 待发布 | **本机出网网关拦截 `POST api.github.com`**（Caddy 403/502；`github.com` POST 正常但 API 只在 api.github.com）⇒ 换 API 可达处一键：`bash test_server/filmlab/publish_recipes_release.sh` |

★ 说明：上一批 68 条只随 `v2.88.0-nxwa.1` 的 zip 交付，无独立入口；本批已把「配方库」沉淀为
**分支文件 + tag + 独立 release 附件**三层，其中前两层已完成，第三层待网络放行。

---

## 2. 新增 27 条清单

### 彩色负片全谱（14）

| key | label | R/G/B | HUE | SAT | SHARP | CON |
|---|---|---|---|---|---|---|
| portra400nc | Portra 400NC | 104/100/95 | 10 | 8 | 9 | 7 |
| portra400vc | Portra 400VC | 107/100/92 | 11 | 12 | 9 | 9 |
| portra800_push | Portra 800 推1600 | 110/102/95 | 11 | 10 | 8 | 9 |
| kodak_max400 | Kodak Max 400 | 110/101/90 | 12 | 12 | 8 | 10 |
| fuji_xtra400 | Fuji X-TRA 400 | 99/102/104 | 12 | 11 | 9 | 9 |
| fuji_venus800 | Fuji Venus 800 | 101/100/103 | 12 | 12 | 8 | 10 |
| fuji_superia1600 | Superia 1600 | 100/100/105 | 13 | 12 | 8 | 11 |
| fuji_natura1600 | Natura 1600 | 103/101/104 | 12 | 11 | 8 | 10 |
| agfa_vista100 | Agfa Vista 100 | 104/100/99 | 11 | 12 | 10 | 10 |
| ferrania_solaris400 | Solaris 400 | 103/100/99 | 12 | 13 | 9 | 11 |
| lomography_color100 | Lomo Color 100 | 105/101/97 | 13 | 13 | 9 | 11 |
| konica_centuria400 | Centuria 400 | 102/102/98 | 12 | 12 | 9 | 10 |
| kodak_colorplus400 | ColorPlus 400 | 108/101/89 | 12 | 12 | 8 | 10 |
| rollei_cn200 | Rollei CN 200 | 101/101/101 | 11 | 11 | 10 | 10 |

### 反转片 E-6 / 电影卷（13）

| key | label | R/G/B | HUE | SAT | SHARP | CON |
|---|---|---|---|---|---|---|
| kodak_ektachrome64 | Ektachrome 64 | 100/102/104 | 11 | 12 | 11 | 12 |
| kodachrome25 | Kodachrome 25 | 108/99/91 | 12 | 13 | 13 | 14 |
| kodachrome200 | Kodachrome 200 | 107/99/91 | 12 | 12 | 11 | 13 |
| fuji_sensia200 | Sensia 200 | 101/102/105 | 11 | 11 | 10 | 10 |
| fuji_sensia400 | Sensia 400 | 100/102/106 | 11 | 12 | 10 | 11 |
| fuji_fortia | Fortia SP | 102/110/109 | 10 | 15 | 12 | 14 |
| agfachrome_ct100 | Agfachrome CT100 | 102/100/101 | 11 | 12 | 11 | 12 |
| agfachrome_rsx100 | Agfachrome RSX100 | 103/99/99 | 12 | 13 | 12 | 13 |
| ektachrome100d | Ektachrome 100D | 99/102/106 | 11 | 12 | 10 | 11 |
| vision3_50d | Vision3 50D | 103/101/100 | 11 | 11 | 10 | 10 |
| vision3_200t | Vision3 200T | 96/102/111 | 13 | 12 | 8 | 10 |
| fuji_eterna500 | Eterna 500T | 97/101/108 | 12 | 9 | 7 | 8 |
| cinestill_400d | CineStill 400D | 104/101/99 | 11 | 12 | 9 | 10 |

---

## 3. 取值逻辑（与首批一致）

- `R/G/B` 88–125（**100 = 中性增益**）：暖调 R↑ B↓；富士系（负片/电影）R↓ B↑ 偏青；
  柯达暖调（Gold/Max/ColorPlus）R↑ B↓↓；中性纪实（Portra NC / Rollei）贴 100。
- `HUE` 9–15（10 中性）：越高越偏黄/暖，风格化用 12–15。
- `SATURATION` 0–16（0 = 纯黑白）：负片 8–13、反转/电影 11–15、Eterna 走低对比（9）。
- `SHARPNESS` 7–13：消费级 8–10、专业/反转 10–13。
- `CONTRAST` 3–16：负片 7–11、反转 12–15、Eterna（电影低反差）8。

---

## 4. 诚实边界（沿用，未变）

- **PW 只有 SAT / SHARP / CON 三维能外部直推**；`R/G/B/HUE` 无外部 MCB 通路
  （归一化器只认 `0x100–0x12e`）⇒ 配方的色彩倾向靠**槽位 + 机身「画面向导 → 自定义1」**体现。
- 配方为 **NX500 专属**；NX1 上 `EV+AEL` 回退社区原版脚本。
- 菜单是 mod_gui 覆盖层：**点击即退，不能滚动对比**。

---

## 5. 复现

```bash
# 追加（幂等；已存在 key 自动跳过）
python test_server/filmlab/add_batch2_recipes.py --apply

# 校验
python test_server/filmlab/flab.py lint
bash test_server/filmlab/flab_sim.sh

# 上机部署（相机在线时；默认 host 已为 192.168.0.105）
python test_server/filmlab/flab.py deploy

# 发布 release + 附件（需 API 可达 / 已登 gh）
bash test_server/filmlab/publish_recipes_release.sh
```

---

## 6. 归档闭环（2026-10-11 18:0x，已完成）

| 项 | 状态 |
| --- | --- |
| 仓库 commit + tag | ✅ `9da9d0b` / `d5c9a09` / `f3d5bb5`，tag `filmlab-recipes-v2` |
| Release `filmlab-recipes-v2` | ✅ 已建；附件 `recipes.json` 21216 B + `recipes.txt` 4359 B |
| 相机上机 | ✅ `flab.py deploy` 跑通；机上 md5 = `7ee00bbd23aeb57b4eb61935cc6b1682`（与本地一致）；export 95 条；mkgui 第 2/6 页 |
| filmsim 镜像 | ✅ `nx500_recipes.txt` + `recipes/recipes.json` 均已刷新到 95 条 |

★ **对上批「Release 未存档」的根因修正**：当时的失败**不是** API 权限/网关能力问题，
而是**线路未走 VPN**。用户开启 VPN 后，`publish_recipes_release.sh` **原样跑通**（HTTP 201×3）。
⇒ 建 release 前先确认 VPN 在线，不必再改脚本或绕道。

★ **filmsim 同步口径**：`test_server/filmsim/recipes/recipes.json` 是**生成物**
（`mk_recipes_json.py` 从 `nx500_recipes.txt` 生成），因此同步必须"换源 + 重生成"，
否则下次跑生成器会退回旧版。已确认重生成结果与 `flab.render(权威源)` **逐字节相同**
（sha1 `0aaf1036571b247d02c7719b14d66375ea7e902d`，21216 B）。

---

*生成：2026-10-11 · 分支 `nxwa` · 离线校验 + 上机验证双口径*
