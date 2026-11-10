# NX-WA 2.88.0-nxwa.15.3 — 双语发行（CN / EN 双包）

发布日期：2026-11-10
性质：发行方式变更。功能与 15.2 相同（NXUI 默认可用 + 远程通路 + `pwrlog` 关机取证），
本版加的是**交付形态**：英文包与英文 release 说明。

## 一句话

从这版起，每次发版出**两个 zip**：`NX-WA-<ver>.zip`（中文）与 `NX-WA-<ver>-EN.zip`（英文），
Release 说明中英并列。

## 一、EN 包里到底翻了什么

| 层 | 内容 | 说明 |
|---|---|---|
| NXUI 面板 | 113 条文案（标题、按钮、状态行、LUT 库管理、混合/编辑对话框） | 重编的 `nxui_en.arm`，逻辑零改动 |
| 相机菜单 | 9 个 `gui_*.NX500` 页（主菜单 / 延时 / 实用功能 / 对焦 / 设置 / 分辨率 / TC / 配置文件 / 模板） | 措辞沿用 NX1 的英文菜单（GO BACK / CANCEL / Focus Stacking…） |
| 文档 | `README.md` 换成英文，中文留成 `README.zh-CN.md` | `README_EN.md` 不再重复出现 |
| 生成型文案 | SSH 状态与弹窗（`ssh_hint.sh`） | 由包内 `scripts/nxui/lang`（`en`）驱动 |

**没翻的**（明确边界，别当成 bug）：

- 老 `mod_gui` 的配方页（`gui_filmlab*.NX500`）—— 只有 `nxui.sh disable` 后才会走到；
- 脚本控制台的输出与日志（`lut.sh` / `filmlab.sh` 的 stdout）；
- `docs/` 与逆向文档（本来就不进包）。

## 二、面板是怎么翻的（可复核）

不做 `#ifdef` 散在 700 行里，而是**生成**：

```
test_server/nxui/i18n/en.json   113 条 中文 → 英文
test_server/nxui/make_en.py     只替换字符串字面量，注释原样保留
test_server/nxui/build.sh en    → out/nxui_en.c → scripts/nxui/nxui_en.arm
```

生成器自带的断言：**所有字面量里不允许残留中文**（注释允许），缺翻译直接报错列出。
复核方式：

```sh
python3 test_server/nxui/make_en.py --check     # 覆盖率
python -c "print(b'\xe4\xbf\x9d\xe5\xad\x98' in open('scripts/nxui/nxui.arm','rb').read())"  # CN=True
python -c "print(b'\xe4\xbf\x9d\xe5\xad\x98' in open('scripts/nxui/nxui_en.arm','rb').read())"  # EN=False
```

## 三、两个包的差异

| 文件 | 中文包 | 英文包 |
|---|---|---|
| `scripts/nxui/nxui.arm` | 479,056 B · `53cea992` | 479,060 B · `99c808ed`（英文构建） |
| `scripts/nxui/lang` | `zh` | `en` |
| `scripts/gui_*.NX500` | 中文 | 英文（9 个文件覆盖） |
| `README.md` | 中文 | 英文（中文在 `README.zh-CN.md`） |
| 其余 | 完全一致 | 完全一致 |

## 四、包与校验

| 包 | 大小 | md5 | 条目 |
|---|---|---|---|
| `NX-WA-2.88.0-nxwa.15.3.zip` | 10,154,115 B | `62e94b8d1e99b01c3e6de638829055cc` | 373 |
| `NX-WA-2.88.0-nxwa.15.3-EN.zip` | 10,153,320 B | `1a2cf33e3b9e14bc7f2b320f51a33587` | 373 |

两个包互斥安装：装 EN 包会把菜单和面板换成英文，装中文包换回来；`nxui/lang` 随包覆盖，
不会残留上一次的语言。

## 五、升级与验收

1. 选一个包解压到 SD 卡根 → 插卡 → 自动增量同步 → 重启。
2. EN 包：按 **EV + AEL** 应出现英文滤镜条（`FILMLAB / PREVIEW`、`Save & close`）；
   按 **MENU** 应出现 `NX-KS / MENU`，菜单项为 `Time-Lapse / Custom Func. / Settings…`。
3. 中文包：与 15.2 完全一致。

## 六、边界（诚实记录）

- 英文面板是**字符串级替换**，逻辑与中文版同源同构建；但**尚未上机目视确认按钮宽度**
  （出这版时相机在休眠）。若发现英文标签被截断，下一版调 `en.json` 文案或按钮宽度即可，
  不需要改逻辑。
- `mod_gui` 两列网格的标签长度铁律（约 6 个全角字符）对英文不适用；英文菜单沿用 NX1 的
  实测措辞，NX1 上已跑过多年。
