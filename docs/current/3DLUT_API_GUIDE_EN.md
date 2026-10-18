# NX500 3D LUT Complete Guide (Official API Route)

> ⚠️ **2026-10-18 文档清理：本文结论已被取代。** Describes the **official-API route** (`lutapi` + CMA + guard), no longer the main line. Still useful as a LUT API reference。
> 现行结论见 [`LUT_RETARGET_LIVE_2026-10-18.md`](LUT_RETARGET_LIVE_2026-10-18.md)。


> Last updated: 2026-10-07 00:00
> Target: NX500 / firmware 1.12 / Linux drime5 3.5.0
> Status: **corruption fixed**; **color cast unresolved** (color space hypothesis unverified)

---

## 0. Quick reference

| Question | Answer |
|---|---|
| Can 3D LUT be loaded from userspace? | ★★★ **Yes**. Official API `d5_ep_3dl_load_lut()` |
| Requires firmware patch? | ★★★ **No**. No p7 patch, no kernel patch |
| Does it corrupt the viewfinder? | ★★★ **No** (use `sel=0`, the vendor channel) |
| Why did it corrupt this morning? | I pointed `+0x00c` at an address outside the "data pocket" domain |
| Does p7 overwrite it afterwards? | ★★ **Yes**. `View::_load` rewrites `+0x00c` every time |
| Is the table format determined? | ★ **No**. Both 29478 and 19652 were falsified |
| Color cast root cause | Suspected color space (RGB vs YCbCr), **unverified** |

**The only correct command sequence**:
```sh
/opt/usr/nx-ks/cmapick2.arm 1024 32          # ★ MUST run before every load
/opt/usr/nx-ks/lutapi.arm load <file> <addr> 0 1 17 2 300 0
                                        ↑sel=0 ★★ key: vendor channel, no corruption
```

---

## 1. ★ Core finding: Samsung left a userspace entry point

### 1.1 Official API (NX1 GPL source, `usr/include/drime5/udd/ep.h`)

```c
int d5_ep_3dlut_op_init (d5_ep_lut_op_info_st *);   // configure channel/format
int d5_ep_3dl_load_lut (unsigned *, sel, fmt, timeout);  // load LUT
int d5_ep_3dl_save_lut (unsigned *, sel, fmt, timeout);  // ★ read back (ineffective, see §6)
```

Enums (`ep_type.h`, comments verbatim):
```c
D5_EP_LUT_FORMAT_422 = 0    /**< Color Format of input image  YCC422 */
D5_EP_LUT_FORMAT_420 = 1    /**< YCC420 */
D5_EP_LUT_CBCR_CH0  = 0     D5_EP_LUT_CBCR_CH1 = 1     D5_EP_LUT_CBCR_CH01 = 2
D5_EP_LUT_SEL_LUT0  = 0     D5_EP_LUT_SEL_LUT1 = 1
D5_EP_LUT_SEL_LUT_EXT = 2  /**< ★★ Select Look-up-table Externally */
```

### 1.2 ★★ `SEL_LUT_EXT` is the "external LUT" door

This comment is the project's breakthrough:
> `D5_EP_LUT_SEL_LUT_EXT = 2` — **"Select Look-up-table Externally"**

⇒ Samsung already designed a userspace path for custom LUTs. No firmware patch needed.

### 1.3 libudd5.so exports 23 LUT symbols (all dlsym-able)

```
userspace  d5_ep_3dlut_op_init / d5_ep_3dl_load_lut / d5_ep_3dl_save_lut
library    _udd_ep_3dl_ctrl_{ConfigAccessMode,ConfigBypassMode,ConfigProcessMode}
register   _udd_ep_3dl_reg_{OnOff,Acc_OnOff,SelCbCr_ch,SelLUT,rw_Start,
                           SetAddress,SetColorFormat_LUT0/LUT1,SetReg,GetReg}
DMA        _udd_ep_{mux,demux}_3dlut_{wdxi,rdxi}
```

---

## 2. ★★★ Three traps you must know

### Trap 1: without `d5_ep_open()`, every API silently fails

`d5_ep_sma_virt_to_phys()` disassembly (libudd5 @0x2175c):
```c
unsigned d5_ep_sma_virt_to_phys(unsigned virt) {
    if (g_d5_dev_ctx < 0) return 0;      // ★★ no device handle in our process ⇒ short-circuit
    if (virt == 0)        return 0;
    if (ioctl(g_d5_dev_ctx, 0xc0047302, &virt) < 0) return 0;
    return virt;
}
```

**Symptom**: `lutapi.arm probe` returns 0 for all four CMA addresses
**Control**: `v2p.arm` (opens device itself, raw ioctl) works fine at the same moment (`0x99000000`)
**Root cause**: **it uses the exact same ioctl number** — the only difference is the device handle

⇒ ★★ **The real reason `malloc` / anonymous mmap returns 0 is not "unsupported" —
  the function never reaches the ioctl**

**Correct usage**:
```c
d5_ep_open();                 // ★ mandatory. returns 0 = success
// ep_3dlut_reg_base then changes from 0x00000000 to non-zero (e.g. 0xb6f84000)
d5_ep_close();
```
Precondition: camera **not in capture mode** (no process holds `/dev/drime5_ep`).
Check with `ls /proc/*/fd`.

### Trap 2: the buffer must be an mmap of `/dev/d5_sma`

```c
malloc / anonymous mmap  ⇒ virt_to_phys returns 0 (no handle)
mmap /dev/d5_sma   ⇒ ★★ returns the exact physical address
```
⇒ Use `open("/dev/d5_sma")` + `mmap(phys)` and verify with `virt_to_phys`.
⇒ ★★ **The address expires immediately after `munmap`** — call within the mapping's lifetime.

### Trap 3: the address dies after munmap (measured 23:52)

```
dmesg: d5_uservirt_to_phys:59 invalid userspace address=b6f39000
```
⇒ The driver recognizes the ioctl; it just rejects "expired" addresses.

---

## 3. ★★ Choosing `sel` (the only factor deciding corruption)

| sel | meaning | measured |
|---|---|---|
| **0** | LUT0 (vendor's own slot) | ★★★ **use this, no corruption** |
| 1 | LUT1 | untested |
| 2 | LUT_EXT (external) | loads, but `Cfg` gets modified (`0x100` → `0x1020`) |

**Measured comparison**:

| | baseline | `sel=0` | `sel=2` |
|---|---|---|---|
| `Cfg` | `0x00000100` | **`0x00000100` (unchanged)** | `0x00001020` (modified) |
| `bit8/bit12` | 1 / 0 | **1 / 0 preserved** | 0 / 1 flipped |
| `SelLUT` | 0 | **0 preserved** | 2 |
| corruption | — | ★ **none** | ★ high |

⇒ ★★ **With `sel=0` the official API only writes the address, never touches `Cfg`**
     — exactly what a "vendor channel" should do
⇒ ⇒★ **True cause of this morning's corruption**: I made the ISP read an address
     outside the "data pocket" domain; `sel=0` is **the channel the vendor itself uses**
     ⇒ completely legitimate

### The official flow is two steps, not one

```c
d5_ep_3dlut_op_init(&info);    // → ConfigProcessMode → writes Cfg register
d5_ep_3dl_load_lut(...);       // → writes address + DMA
```
`ConfigProcessMode` (@0x3abb4) disassembly:
```c
_udd_ep_3dl_reg_OnOff(1); Acc_OnOff(1); Acc_OnOff(0);
SelCbCr_ch(p->+0x14)          -> Cfg bits[1:0]
SelLUT(p->+0x10)              -> Cfg bits[5:4]
SetColorFormat(sel, p->+0x18) -> Cfg bit8/bit12
```
★ `lutapi.arm load` now calls `op_init` automatically.

---

## 4. ★★ CMA placement (Rule 61)

### 4.1 `/dev/d5_sma` reports only ONE region

```
ioctl(SMA_GET_REGION_START_ADDR) => 0x94000000, size 0x09000000 (144MB)
★★ but dmesg shows: cma: reserved 288MiB at 94000000 / 72MiB at 8f800000
⇒ ★★ the second 72MB region can only come from dmesg; ioctl won't tell you
⇒ ★★ "no error returned" ≠ "there is only one region"
```

### 4.2 Measured occupancy (2026-10-06 23:10)

```
region#1  0x94000000  144MB  ⇒★ fully non-zero (ISP occupies it entirely)
region#2  0x8f800000   72MB  ⇒ partially non-zero, 4096 KB contiguous zeros ★
```
⇒ ★★ **The v1 tool missed exactly this region.** One region difference flips the
     conclusion from "guaranteed crash" to "4MB available".

### 4.3 The measured cost of Rule 61

Writing to `0x94000000` ⇒ **whole camera froze, only battery removal recovered**
```
dmesg: alloc_contig_range test_pages_isolated(...) failed
```
⇒ That region is the **ISP's WDMA hardware workspace**; "probed as all-zero" ≠ "safe to own"

### 4.4 Must re-probe before every load

The same address has different occupancy at different times
(observed `0x8f800000` / `0x8f808000` / `0x8f810000` rotating).

**Scan time**: 216MB @1MB granularity = **116ms** (bottleneck is page faults, not CPU)

---

## 5. ★ Tools

### 5.1 lutapi.arm — official API tool

```sh
lutapi.arm probe                ★ zero-risk: symbols + d5_ep_open + mmap probe
lutapi.arm info                 read-only: 23 symbols
lutapi.arm regdump              read-only: 3D LUT register snapshot
lutapi.arm opinit <sel><fmt><cbcr><bypass>   configure only
lutapi.arm load <file> <phys> [sel] [fmt] [size] [stride] [settle] [cbcr_ch]
lutapi.arm save <out> <phys> [sel] [fmt] [bytes]    ★ readback ineffective (see §6)
lutapi.arm verify <file> <phys> ...     load+save compare (★ based on ineffective save)
lutapi.arm idgen <out> [size] [stride]  generate identity table
lutapi.arm probe-size <phys> <n> ...    self-test whether save_lut outputs anything
```

Build:
```sh
zig cc -target arm-linux-gnueabi.2.15 -O0 -o lutapi.arm lutapi.c -ldl
```

**Six safety gates**:
1. `load` requires an explicit physical address (never guess)
2. `SMA_VIRT_TO_PHYS` verification; abort on mismatch
3. `memcmp` readback after write
4. Block when `ep_3dlut_reg_base == 0` (requires `d5_ep_open` first)
5. No zeroing, no munmap during DMA settle
6. ★ **(added after the 23:58 incident)** `probe-size` refuses addresses overlapping live `LUT0`/`LUT1`

### 5.2 cmapick2.arm — CMA placement finder

```sh
cmapick2.arm [step_kb] [need_kb]
```
- Scans both regions (`0x94000000` + `0x8f800000`)
- Tri-state verdict: all-zero / partially non-zero / fully non-zero
- `usleep(2000)` every 4MB to yield (Rule 3)

### 5.3 eptest_open.arm — tests whether `d5_ep_open` works

```sh
eptest_open.arm
```
`d5_udd_open` return values: `0`=first open success, `1`=already open, `2`=refcount++, negative=error

### 5.4 PC-side converters

| Tool | Purpose |
|---|---|
| `filmsim/cube2nx17.py` | `.cube`(33³) → 17³×3×u16, with `--selftest` |
| `filmsim/rgb2ycc.py` | RGB table → YCbCr table, **★ hypothesis unverified** |
| `filmsim/ycc_variants.py` | generate identity layout candidates for reverse-engineering |
| `isp/udd5dis.py` | libudd5 PLT-aware disassembler (reusable) |

---

## 6. ★★★★★★ [IMPORTANT FALSIFICATION] `save_lut` cannot read the hardware table

### 6.1 Measurement

```
Gave a【brand-new, zeroed】262144-byte buffer to save_lut:
  save_lut returns 0, but the readback is【all zeros】
Swept all 9 combinations (sel × cbcr_ch × fmt) ⇒ all zero
```

### 6.2 ⇒ Consequentially falsified conclusions

| Previously asserted | Status |
|---|---|
| "hardware table = 29478 bytes = 17³×3×u16" | ★★ **does not hold** |
| "readback matches identity on all 14739 channels" | ★ **void** |
| "19652 is wrong, 29478 is right" | ★★ **both uncertain** |

### 6.3 Why this is a self-confirming loop

```
I use load_lut to write the table into CMA buffer A
I then use save_lut to read back from buffer A
⇒ what I read is exactly what I wrote
⇒ this only proves the DMA path is symmetric; it says nothing about the hardware SRAM
```

### 6.4 Possible causes (to investigate)

1. ★★★ The read direction needs `rw_Start(2)` (bit4); the official `save_lut` may not trigger it
   → the hand-written dump sequence from daytime did read out data
2. The read direction requires a different `fmt`
3. The hardware table lives in a different SRAM region; `+0x00c` is write-only

---

## 7. ★★ Unresolved: the color cast

### 7.1 Observations

| Table loaded | User observation |
|---|---|
| Portra 400 (RGB) | strong red cast |
| Kodachrome 64 (RGB) | strong blue-purple cast |
| Portra 400 (YCbCr) | magenta/green separation + severe posterization |
| identity table | **still cast** (★ even identity is not neutral) |

**★ Photo confirms**: UI icons/text are perfectly normal; only the image is cast
⇒ the LUT affects the image path only, not OSD overlay

### 7.2 Single-axis discrimination (partially done)

Halving one axis at a time:

| axis darkened | observation | inference |
|---|---|---|
| axis 1 | image darker, colors more saturated | ★ **Y** (luma) |
| axis 2 | white wall turns salmon (blue lost) | ★ **Cb** |
| axis 3 | pending | expected **Cr** |

⇒ ★★ suspected axes = **(Y, Cb, Cr)**, matching the `YCC420` naming

### 7.3 ★ Failed hypotheses

| Hypothesis | Result |
|---|---|
| interleaved (Y,Cb,Cr) full-range | ★ cast |
| planar (three separate planes) | ★ "extremely bad" |
| missing `op_init` call | ★ fixed, but**still casts** |

⇒ ⇒★ **Even the identity table is not neutral ⇒ my identity table itself isn't identity**
⇒ ⇒★★ means the "index ↔ value" correspondence is wrong, not just the layout

### 7.4 The key logical flaw

★★ **I concluded "table length = 29478" from the fact that `save_lut` read back
    29478 non-zero bytes** — but those bytes are what I myself wrote, so of course
    the length matches.
⇒ ★★ **If the real table is 33³ (215622 bytes), my 29478 bytes cover only 1/8 of
    the input domain and the rest is uninitialized garbage**
    ⇒ this fully explains "every table casts"

### 7.5 Next step (no more guessing)

★ **Since we cannot read it out, the image becomes the only judge**:
1. ★ Single-axis table: deviate only one axis from identity, observe which dimension changes
2. ★ Saturation ramp: stretch linearly along Cb, check chroma linearity
3. ★★★ **First rule out "table too small"**: build the identity table at 215622 bytes (33³)
   ⇒ if the larger identity becomes neutral ⇒ ★★★ size is the root cause

---

## 8. ★★ p7 steals the pointer back

Measured (20 consecutive samples, 1 second apart):
```
[1-6]  LUT0 = 0x8f808000   ← my address
[7-20] LUT0 = 0x81115200   ← after half-press focus, p7 took it back
```

⇒ ★★ p7's `View::_load` rewrites `+0x00c` every time
⇒ ★⇒ **As long as no View reload is triggered (no half-press), my table stays active**
⇒ ⇒★★ **"recovers after half-press" is not a rollback failure — it's p7 working normally**

Key code from `View::_load` (capstone, layer by layer):
```c
FUN_000f6474();                    // ★ socket receive of the "data pocket" (688-byte buffer)
if (FUN_000f1b58() == 0)
     iVar5 = FUN_0009a3e8(ctx, uVar4, uVar3);  // static 4 slots
else
     iVar5 = FUN_0009a408(ctx, uVar2, uVar3);  // dynamic 24 slots
FUN_00179314(iVar5, 0, cVar1 != 1, 0);         // submit
```

---

## 9. ★ Methodology rules (added tonight)

| # | Rule | Cost |
|---|---|---|
| 65 | After falsifying a conclusion, sweep all documents for it | — |
| 66 | ★★★★★ **With static sources at hand, read code before experimenting** | 11 daytime experiments were avoidable |
| 67 | ★★★★★ Instruction-level conclusions must use capstone | — |
| 68 | ★★★★ To judge "is there an independent datapath", find the【data source log】 | — |
| 69 | ★★★ **Replicate C logic on PC and compare byte by byte** | caught reversed index order in `make_identity` |
| 70 | ★★★ **Self-test must use the same mapping as the code under test** | caught "the self-test itself was wrong" |
| 71 | ★★★★★ **Multi-entry APIs require figuring out call order first** | missed `op_init` |
| 72 | ★★★★★★ **"I can write it and read it back" ≠ "what I read back came from hardware"** | ★★ **self-confirming loop wasted 3 hours** |
| 73 | ★★★★★ **Probe tools must refuse to write regions hardware is using** | ★ zeroed the live table |

---

## 10. Complete operating manual

### Loading a LUT

```sh
# 1. Camera stays in the menu (not in capture mode)
# 2. Pick an address (★ MUST re-run every time)
telnet/ssh: /opt/usr/nx-ks/cmapick2.arm 1024 32
#    note "4KB granularity hit: 0x........ contiguous XX KB"

# 3. Load (★ sel=0)
/opt/usr/nx-ks/lutapi.arm load /mnt/mmc/luts/<table>.bin 0x........ 0 1 17 2 300 0

# 4. Look at the viewfinder — the image should change
# ★ do NOT half-press the shutter (triggers p7 stealing the pointer back)
```

### Rollback

```sh
/opt/usr/nx-ks/lutload.arm restore    # only rewrites the pointer to 0x81115200, no DMA
then half-press focus                  # let p7 re-load
```

### Troubleshooting

| Symptom | Cause | Action |
|---|---|---|
| gate blocks, `reg_base==0` | `d5_ep_open` not called | wait until camera returns to menu |
| `virt_to_phys` returns 0 | buffer wasn't `/dev/d5_sma` mmap | check the tool |
| corrupted viewfinder | `sel=2` | ★ use `sel=0` |
| recovers after half-press | p7 stole the pointer | ★ normal, ignore |
| color cast | color space mismatch | see §7, **unresolved** |

---

## 11. References

### Official docs
- `usr/include/drime5/udd/ep.h` — 3D LUT API prototypes
- `usr/include/drime5/udd/ep_type.h` — enum definitions (comments are authoritative)

### This project's docs
- `docs/current/3DLUT_API_GUIDE.md` (this file)
- `docs/evidence/p7/` — p7 disassembly evidence fragments
- `docs/evidence/discovery/01..06` — static inventory reports

### Hardware facts
- EP 3D LUT register base `0x2082b000`, size 4096
- `+0x000` OnOff / `+0x004` Cfg / `+0x008` Pulse / `+0x00c` LUT0 / `+0x010` LUT1
- Factory LUT0 = `0x81115200` (skin tone slot), LUT1 = `0`
- `Cfg` bit8/bit12 = color format, bits[1:0] = CbCr channel, bits[5:4] = SelLUT

---

*End of document. **§6 and §7 are the two most important sections** — the first records my
self-confirming loop, the second is the only unresolved problem.*