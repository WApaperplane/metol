# Reddit 发布稿（英文）

> 目标版块：`r/SamsungNX`（主）、`r/cameras`、`r/ReverseEngineering`（技术向）
> 语气要求：不吹、先给结论、明确列出未验证项。Reddit 反感营销腔，但吃"有判据的实验记录"。
> 配图：见文末「附件清单」。

---

## 标题候选

1. **We can now swap the 3D LUT in a Samsung NX500 viewfinder live — no firmware flash, 4 bytes + one half-press**
2. **NX500 3D LUT reverse engineering: the ISP re-reads its lookup-table pointer on every load, so you only need to edit one word**
3. **I got arbitrary 3D LUTs into the NX500's EVF *and* JPEG — two independent chains, no reflash**

（推荐第 1 条：具体、可验证、有数字。）

---

## 正文

**TL;DR** — On a Samsung NX500 (firmware 1.12), the DRIMe5 image processor keeps its 3D LUTs in RAM slots and re-reads a small static registry every time it loads one. Overwrite one 4-byte registry entry, write 19,712 bytes into a spare slot, half-press the shutter, and the viewfinder renders your table. No firmware flash, no code patch, no timing race. The still-image chain is a *separate* registry, so the JPEG can use a different LUT than the EVF.

This is part of an ongoing open reverse-engineering project (AGPL-3.0, forked from `ottokiksmaler/nx500_nx1_modding`). Everything below was measured on one body, firmware 1.12, with the NX-KS2 mod installed.

---

### 1. What the hardware actually is

The NX500 has two processors doing different jobs:

- **AP** — runs Tizen 2.2 and `di-camera-app` (the UI, the menus, the file writing)
- **p7** — a separate Cortex-A9 running T-Kernel 2.01.03. This is the ISP. It owns demosaic, noise reduction, colour, and the 3D LUTs.

The p7 firmware is not in the rootfs. It lives in its own eMMC partition, and it's where all the interesting colour code is. Being a separate core with its own RTOS, it has its own address space, and its firmware is loaded with a flat `VA = 0x80000000 + file_offset` mapping — which makes static analysis unusually pleasant.

### 2. The LUT format

Reverse-engineered from the firmware and confirmed by 42-slot byte comparison:

```
4,913 entries (17 x 17 x 17) x 4 bytes {R, G, B, pad=0}
index = ((B * 17 + G) * 17 + R) * 4
slot size = 19,652 B data + 60 B pad = 19,712 B
slot stride = 0x4D00
```

At boot the p7 firmware copies a 4,097,216-byte region of the image into RAM:

```
image file [0x79BDC0, 0xB84280)  ->  loaded at 0x8079BDC0
  copy 0x3E84C0 bytes           ->  runtime [0x81006000, 0x813EE4C0)
runtime = 0x80000000 + file_offset + 0x86A240
```

That region holds 42 LUT slots — 20 in one block, 22 in another. This is why an earlier negative result ("nothing in the firmware fills these tables") was wrong: the filler *is* in the firmware, it's just a bulk `memcpy` at init, not a per-slot routine.

### 3. Where the "which LUT" decision lives

Three static tables in the code segment:

| Table | Address | Entries | Used by |
|---|---|---|---|
| `View4` | `0x803837F0` | 4 | live view |
| `Still6` | `0x80382C5C` | 6 | still capture |
| `BV12` | `0x80382B00` | 12 | brightness-value indexed |

Each entry is a struct; `+0x00C` is the **load source address**, `+0x010` is the **save address**. These are not pointers that get polled — they're read at load time.

Two things we verified before touching anything:

1. The 16 KB page containing all three tables is **byte-identical to the firmware image** at runtime (22/22 entries matched, 16 KB diff = 0). So `VA = 0x80000000 + file_offset` holds for this region and nothing rewrites it at boot.
2. The page is **writable** via `/dev/mem` with `O_RDWR` + `PROT_WRITE`. A no-op write-back produced zero stray bytes in the window.

### 4. The experiment

Stock behaviour on this body: the live-view chain loads from `0x81115200` (slot A17, a skin-tone table), *not* from the "standard" slot. That single fact invalidated an earlier experiment where we wrote a negative table into the standard slot and saw no change — wrong target, not a failed mechanism.

So:

| Step | Action | Machine check |
|---|---|---|
| 0 | baseline | `VIEW4 = 810fd100 81101e00 81106b00 81115200`, `cfg=0x100`, `load=0x81115200` |
| 1 | no-op write-back | read back identical, stray = 0 |
| 2 | `View4[3]` -> A18 (`0x81119F00`) | 1 byte changed inside the word, stray = 0 |
| 3 | half-press | `load_addr -> 0x81119F00`; **no visible change** |
| 4 | `View4[3]` -> A12 (`0x810FD100`) | 1 byte changed, stray = 0 |
| 5 | half-press | `load_addr -> 0x810FD100`; "brighter, cooler", no obvious cast |
| 6 | write an inverted table into A18 (19,712 B, backup first) | readback mismatched bytes = 0 |
| 7 | `View4[3]` -> A18 | 2 bytes changed, stray = 0 |
| 8 | half-press | **viewfinder goes clearly negative** |
| 9 | rollback both | registry back to A17, slot `mismatch = 0` |

Step 3 looks like a failure and isn't. A18 and A17 differ in only 806 of 19,712 bytes (4.1 %, max delta 8 levels) — visually identical. **The test was the problem, not the hardware.** A12/A14 differ by ~70 % with a max delta of 97 levels, which is why step 5 produced a visible (if ambiguous) change.

So we skipped interpretation and went for a verdict-proof stimulus: invert every entry, `255 - R/G/B`. No ambiguity at all.

### 5. The interesting part: two independent chains

The still-image chain has its own six-entry registry. We pointed all six at the same inverted slot, left `View4[3]` pointing at the stock A17 table, and took a shot.

**The EVF looked completely normal. The JPEG came out negative.**

That means view and still are separately retargetable. You can preview one look and bake another — or, more usefully, give the EVF a cheap approximation and the JPEG the accurate one.

It also re-explains an old negative result: an earlier experiment put a table into **LUT1** and the JPEG didn't follow. That's not "still images can't take a LUT" — it's "the still `_load` uses `sel=0`, so it only ever reads LUT0."

### 6. Configuration bits (this one cost us a wrong conclusion)

The ISP config register:

| Bits | Meaning |
|---|---|
| `[1:0]` | `SelCbCr` |
| `[5:4]` | **`SelLUT`** |
| `8` | LUT0 format |
| `12` | LUT1 format |

`0x100` and `0x1100` both mean `SelLUT = 0`. Only `0x1110` means `SelLUT = 1`. Treating bit 12 as a selector bit produces a confident, wrong answer ("stills use LUT1"). Read the field, not the flag.

### 7. On-camera `.cube` conversion

The rootfs has no Python, so `cube2lut` is a freestanding ARM binary (no libc, no libm, no libgcc). It takes an Adobe `.cube`, resamples to the 17³ grid `{0,16,...,240,255}`, and writes the 19,712-byte slot table.

I expected to have to tune a fixed-point implementation. Instead it came out **byte-identical to the PC float reference** on the three 17³ test cubes — because the reference quantises to 8-bit before writing, so rounding differences have nowhere to survive.

(Real film cubes are usually 13³ or 33³. Resampling those onto the 17³ grid puts them within **1 level** of the PC reference — that residual is grid interpolation, not a bug.)

It deliberately **refuses** rather than guesses: `.cube` files with `DOMAIN_MIN != 0` / `DOMAIN_MAX != 1`, non-`N³` node counts, or 1D LUTs exit with an error. A wrong axis order or domain still produces a plausible-looking table, and a plausible-looking wrong table is far worse than a visible error.

**And one bug worth admitting, because it nearly shipped.** The first number parser didn't handle scientific notation. G'MIC writes near-black values as `2.2439395252149552e-05`; the parser hit the `e`, returned 0, and — crucially — **didn't advance the pointer**. Every following value parsed as 0. The node counter still incremented to `N³`, so the "did I read 4,913 values?" check passed. The tool exited `OK` and emitted a table that was 93 % black.

12 of 18 real film cubes were affected. The three test cubes we'd used (identity, invert, warm) contained no `e` notation, so the suite was green. Fixed: `e±NN` is parsed, unresolvable input returns `bad number at value index…`, and an all-zero table is rejected outright.

### 8. A practical test you can use on any `.cube`, today

If you've ever downloaded a LUT pack and found that half of them look like a colour-cast disaster on your camera, here's a scene-independent screening metric.

Feed a neutral ramp `(v, v, v)` for `v = 0..255` through the cube and measure, at each v:

```
cast(v) = max(R, G, B) - min(R, G, B)      # in 8-bit levels
score   = max over v of cast(v)
```

Neutral in should mean neutral out. Any deviation is a cast — sometimes intentional, sometimes a broken conversion. It doesn't depend on the image, the lighting, or the scene.

| Score | Verdict |
|---|---|
| ≤ 12 | safe |
| 13 – 25 | mild |
| 26 – 50 | strong |
| > 50 | extreme |

I ran this over 296 community Film-Luts:

- safe 157 / mild 62 / strong 28 / extreme 49
- one entire category labelled "instant consumer" scored 4/54 safe — it's almost unusable
- all 25 B&W cubes scored safe

The casts are **not** a conversion bug. We checked with an axis-order matrix on 18 samples and every one was diagonally dominant, i.e. the channel mapping is right and the cast is in the source data.

### 9. What is NOT verified

Being explicit, because this is where mod posts usually overreach:

- **Persistence.** All of this is RAM. Power cycle restores stock behaviour. Boot-time LUTs still need a firmware image edit.
- **Reload trigger.** Half-press definitely triggers a reload. Whether mode changes, drive-mode changes, or wake-from-sleep also do is untested.
- **Multiple slots at once.** The registries have 4 and 6 entries. Whether four different custom tables can be bound to four positions (i.e. a LUT dial) is untested.
- **Other firmware.** Everything here is on 1.12 with one specific p7 build.
- **Other table formats.** Only the 4913×4B layout was tested. 16-bit and 4:2:2 variants are not.
- **Focus handover after this change** — unrelated, but we also fixed a UI bug where our overlay panel stole the X11 input focus and never gave it back, which made the camera's own menu arrow keys flaky. Details in the repo.

### 10. One safety note, because it bites hard

You can trigger a reload yourself by writing `+0x00C` and pulsing the config register. **Don't.** The ISP then reads an address combination that has never existed in the original sequence and you get severe colour corruption / garbage.

The only safe reload is letting the camera do it: **half-press the shutter.** Our apply/restore scripts deliberately do not auto-reload.

Rollback is complete and verified: the spare slot's pre-write backup was byte-identical to the firmware image slice (`md5 4c0cc78c…`), and both the registry and the slot restore cleanly in either direction.

---

### Repository

`https://github.com/WApaperplane/NXWA-nx500_modding` — branch `nxwa`. AGPL-3.0, derived from `ottokiksmaler/nx500_nx1_modding`.

Today's work landed in `docs/current/`:

- `LUT_RETARGET_LIVE_2026-10-18.md` — the full experiment chain and data
- `LUT_REGTAB_READ_2026-10-18.md` — config bit definitions and registry readback
- `CUBE2LUT_2026-10-18.md` — on-camera converter and its format contract
- `LUT_UI_2026-10-18.md` — the on-camera UI mode
- `NXUI_FOCUS_HANDOFF_2026-10-18.md` — the X11 focus bug

Tools: `test_server/lutpipe/{nx_regtabdump,nx_regtabwrite,nx_slotwrite,cube2lut}.c`, entry point `scripts/lut.sh`.

**Prerequisites:** this assumes the NX-KS2 mod is already installed (telnet/FTP root on the body). It is not a one-click install for a stock camera, and you should be comfortable with `/dev/mem` before trying it.

Questions and corrections welcome — especially if you have a different p7 build and want to check whether the slot map matches.

---

## 附件清单（发帖时上传）

| 文件 | 用途 |
|---|---|
| `raw8/gates/lut/regtab_2026-10-18/lut_ui2.png` | 机上 LUT 面板（720×192，identity17 / neg / warm33） |
| `raw8/gates/lut/regtab_2026-10-18/photos/SAM_0044.JPG` | ★ 关键证据：取景器正常、成片负片 |
| 取景器前后的对比图 | 需要现拍：同一场景 apply 前后各一张 |

> 注意：照片与 png 都在 `.gitignore` 里（`*.jpg` / `*.png`），只存在于本地，需手动上传到 Reddit 的图床。SAM_0044.JPG 是 7.7 MB，Reddit 会压缩，建议先导出一份 2048px 长边的版本。

## 评论区预案

| 会被问 | 回答要点 |
|---|---|
| "能装到我的 NX300/NX1 吗" | NX1 是同一代 DRIMe5，p7 很可能同源但未验；NX300 是 DRIMe4，不要假设 |
| "会砖吗" | 全程内存操作，断电即回原状；不写分区、不刷固件。前提是已有 mod 的 telnet 权限 |
| "为什么不用 LUT1 而用 LUT0" | Still 的 `_load` 固定 `sel=0`；LUT1 对成片无效 |
| "能实时预览不同 LUT 吗" | 目前靠半按触发重载；真正的多档切换未验 |
| "这算 HDR 吗/能拍 log 吗" | 不算，这是把成片前的色彩查找表换掉，不增加动态范围 |
