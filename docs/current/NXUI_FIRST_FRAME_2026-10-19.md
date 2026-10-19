# NXUI 首帧：字体链实测与收敛（2026-10-19）

> **一句话**：字体的钱已经赚完了 —— 原厂 10.7 MB 字体打开 147 ms，换成 GB2312 子集后 51 ms。
> 再往下裁（38 KB 面板子集）**一分钱不省**，因为 `FcFreeTypeQuery` 的固定开销与码点数几乎无关。
> 本轮把这条边界实测钉死，并修掉三个会让人误判的缺陷。

## 0. 结论前置

| # | 结论 | 证据 |
|---|---|---|
| 1 | 首帧 101–109 ms（冷 fontconfig 缓存），其中字体 50–54 ms 是最大单项 | `bench_font_tiers.sh`，qemu-arm + 相机 rootfs，3 次取最小 |
| 2 | **38 KB 面板子集没有收益**：按文件开 49 ms ≈ GB2312 family 51 ms | 同上 `opt0` 场景 |
| 3 | 68 个配方名里 **21 个含中文**，所以 FILMLAB 必须用 GB2312 档；只部署面板子集会一路降级到原厂字体，比不优化更慢 | `scripts/filmlab/recipes.json`；`num_non_ascii=21` |
| 4 | 缺字兜底必须走**按文件打开**：生产 `fonts.conf` 刻意不含 `/usr/share/fonts`，家族名在那里不存在 | `scripts/nxui/fonts.conf` |
| 5 | 本轮**没有性能提升**（101 vs 交付时的 122 ms 差异在 qemu 抖动内）；收益是把边界测清楚 + 修 3 个缺陷 | §5 |

## 1. 首帧成本构成

`INIT` 行（冷缓存，`bench_font_tiers.sh lut`，取 3 次最小）：

| 项 | ms | 说明 |
|---|---:|---|
| recipes_ms | 4–5 | 解析 68 条配方表 |
| display_ms | 6–7 | `XOpenDisplay` |
| **font_ms** | **50–54** | 打开 GB2312 子集并做覆盖校验 |
| backend_ms | 20–24 | `nk_xlib_init` |
| map_ms | 16–21 | `XMapRaised` + `XSync` |
| **FIRST_FRAME** | **101–109** | 进程启动到首帧可见 |

字体仍占一半。剩下的 50 ms 里，`FcFreeTypeQuery` 是固定大头（读 name/OS2/post 表、建 pattern），cmap 只占小头。

## 2. 字体候选实测

`bench_font_tiers.sh` 的 `font_ms`（qemu-arm，冷 fontconfig 缓存，3 次取最小）：

| 字体 | 字节 | 码点 | font_ms |
|---|---:|---:|---:|
| SDIC_GP_US（原厂） | 10,680,224 | 44,426 | 147（历史值）/ 165（本次 nomin 场景实测） |
| font-sub-gbk | 6,211,352 | — | 未测（无使用场景） |
| **font-sub-gb2312** | **1,864,592** | **7,547** | **50–54** |
| font-sub-panel | 38,356 | 256 | 49 |

> `fontprobe.arm` 在 qemu 下 `FcFreeTypeQuery` 返回 NULL（`bench_font_sizes.sh` 因此出空表），
> 所以这张表用 nxui 的 `INIT font_ms` 而不是探针的分项。探针的 `stderr` 输出已修
> （原来 `printf` 到 stdout 在 `__libc_start_main` 退出路径上不 flush，一行都不打），
> 真机上可以再用它做分项。

**关键**：38 KB 与 1.9 MB 的打开成本相同。裁到 256 码点只省 2 ms。

原因不是文件大小，也不是 cmap 遍历 —— 是 `FcFreeTypeQuery` 的**固定成本**（表解析 + pattern 构造）。cmap 从 7,547 降到 256 理论上省 ~25 ms，但实测没有，说明这条路径上还有别的固定项吃掉了它。

> 推论：想再省只能**绕开 fontconfig**（自建 pattern 直连 FreeType），那是另一条工程，收益上限约 40 ms，代价是失去字体匹配与缺字检测。当前不做。

## 3. 为什么面板子集不能当生产字体

除了 §2 的"没收益"，还有一个更硬的理由：

```
68 个配方名里 21 个含中文（EK Cyan 冷调 / TriX 400 暖调 / HP5 粗颗粒 / 暖调 棕褐 …）
```

`font_covers_panel()` 逐字检查**全部** label 与菜单项。只要有一条中文，面板子集就整档失效 → 降级。

按文件打开原厂字体是 370 ms。若当时只部署 38 KB 子集而不带 GB2312 中间档，**每次开 FILMLAB 面板都要 370 ms**，比优化前更慢。这是本轮最有价值的一条发现。

## 4. 最终字体链

```
默认（两级）
  tier1  NXUI_CJK（font-sub-gb2312.ttf，1.9 MB，family 打开）  51 ms   ← 常态
  tier2  /usr/share/fonts/SDIC_GP_US_20120720.ttf（按文件）    370 ms  ← 生僻字兜底

实验（显式 NXUI_FONT_MIN=<path> 才启用）
  tier0  面板子集（38 KB，按文件）                              49 ms   ← 已验证无收益，默认关
```

行为矩阵（`bench_font_tiers.sh`，冷缓存，3 次取最小）：

| 场景 | 档位 | font_ms | first_ms | 判定 |
|---|---|---:|---:|---|
| LUT 面板（英文 look 名） | 1 | 54 | 109 | 常态 |
| FILMLAB（68 条，21 条中文） | 1 | 50 | 103 | 常态 |
| look 名含 GB2312 汉字 | 1 | 51 | 101 | 常态 |
| look 名含 GB2312 以外（龍） | 2 | 49 | 251 | 罕见，可接受 |
| 原厂菜单（`--menu`） | 1 | 50 | 108 | 常态 |
| 二级 family 打不开 | 2 | 166 | 220 | 兜底仍有画面 |
| 显式开面板子集 | 0 | 49 | 100 | 与 tier1 相同 → 不启用 |

`READY` 行新增 `tier=N`，`INIT` 行新增 `font_total_ms`（进程启动到字体链确定的累计时间），缺字时日志给出具体码点：

```
FONT tier1=NXUI_CJK:pixelsize=19 (tier0 missing U+9F8D)
FONT tier2=/usr/share/fonts/SDIC_GP_US_20120720.ttf (tier1 missing U+9F8D)
```

## 5. 本轮修的三个缺陷

| # | 缺陷 | 影响 | 修法 |
|---|---|---|---|
| 1 | **降级后无条件再降一级**：`if (font_tier==0){…; font_tier=1;} if (font_tier==1){…}` —— 二级成功也会进三级 | 任何缺中文的面板都会白开一次 10.7 MB 字体（多付 150–170 ms），且日志看起来"二级也缺字" | 改用局部 `covered` 标志，只在真的缺字时才继续降级 |
| 2 | `XftCharExists` 在相机这套 Xft/libfontconfig 上对 CJK 返回 0 | 覆盖校验形同虚设，一路降级到原厂字体 | 改查 `XftFont->charset` + `FcCharSetHasChar`，纯本地、无 X 往返 |
| 3 | `nk_xfont_del()` 会无条件 `XftFontClose(font->ft)`，而 `ft` 为 NULL 时崩溃 | 字体打开失败的分支反而让面板崩掉 | 失败对象改 `free()`，只在 `ft` 有效时交给 Xft |

另修 `fontprobe.c` 的输出：进程通过 `__libc_start_main` 退出时不保证 stdio flush，`printf` 版本在 qemu 下**一行都不打**，导致之前的字体成本只能靠 nxui 的 `font_ms` 间接推断。改 `fprintf(stderr)` + `fflush`。

> 缺陷 1、2 都是本轮新增三级链时自己引入的；缺陷 3 与原 `fontprobe` 是既有问题。

## 6. 工具

| 脚本 | 作用 |
|---|---|
| `bench_font_sizes.sh` | 四个候选字体的字节/码点/query_ms 对照（fontprobe） |
| `bench_font_tiers.sh` | 七个场景的档位与首帧，冷缓存 × 3 取最小 |
| `bench_font_prod.sh` | 生产布局等价测试（GB2312 + 缺字回退），旧脚本，保留 |
| `bench_font_panel.sh` | 面板子集下界，一次性结论已并入本文 §2 |
| `build_fontprobe.sh` | 交叉编译 fontprobe.arm |

## 7. 回归（2026-10-19 17:50）

| 项 | 结果 |
|---|---|
| `build.sh`（host `test_model` + `test_services` + ARM 交叉） | PASS |
| `verify_display.py`（host + arm × filmlab/menu/idle/interaction/service-interaction/performance + focus-handoff） | 13/13 PASS |
| `test_regtabwrite.py` | 10 PASS（Windows；WSL 下按路径跳过） |
| `test_lut_sh_rotation.py` | 8 PASS |
| `test_cube2lut.py` | 14 PASS |
| `test_regtabdump.py` | 7 PASS（Windows） |
| GLIBC 上限 / NEEDED | 2.7 / `libX11 libXft libc librt`，与上版一致 |

产物：`scripts/nxui/nxui.arm` md5 `fcd8b1d4844104a39249627949561ec2`，456,132 B。

## 8. 还能往哪走（未做）

| 方向 | 上限收益 | 代价 |
|---|---:|---|
| 绕开 fontconfig 直连 FreeType 建 `XftFont` | ~40 ms | 自管字体匹配与缺字检测，跨固件风险 |
| 把首帧降到"先映射窗口再加载字体" | ~50 ms（但会先显示空面板） | 观感倒退，不可取 |
| 静态文本烘焙成位图 | ~10 ms | 只对固定文案有效，look 名仍要真字体 |
| `backend_ms`（Nuklear 初始化 20 ms） | ~5 ms | 收益小 |
| `map_ms`（X 服务器映射 16–21 ms） | ~10 ms | 受 X 服务器调度，不可控 |

结论：**字体这条线到此为止**。首帧 ~105 ms，其中 50 ms 是字体、20 ms 是 UI 后端、20 ms 是 X 映射、12 ms 是启动与解析。继续压需要换实现路径，不是调参能解决的。
