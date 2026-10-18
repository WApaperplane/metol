# NX500 3D LUT Deep-Dive Investigation Log (2026-10-07)

> **This document records the complete investigation and its conclusions from the
> morning of 2026-10-07.**
> Status: **API path working**; **color cast unsolved** (root cause narrowed to "table format")
> Companion to [`3DLUT_API_GUIDE_EN.md`](3DLUT_API_GUIDE_EN.md) (the operations manual).
> This document covers what the GUIDE does not: the falsification process, the full
> register map, the p7-side reverse engineering, and the address-space model.

---

## 0. ★ Thirty-second summary

| Question | Answer |
|---|---|
| Biggest takeaway? | ★★★ **The official flow is three steps; I only did two** (missed the interrupt wait) |
| Is the LUT table format determined? | ★ **No**. Worse: **the registers contain no format fields at all** (§3) |
| How narrow is the color-cast cause? | ★★ Narrowed to "table data format"; axis order / parameters / size ruled out (§2) |
| Can p7 read Linux CMA? | ★★★ **Yes** (identity mapping over 4GB, §6) |
| Can Linux read p7's tables? | ✘ **No** — every channel eliminated (§7) |
| Is the official data path (IPCC) usable? | ✘ `IPCC_INIT` triggers a **p7 (A9) Oops** (§8) |
| ★ Bottom line | **This is an engineering-effort problem**: continuing requires modifying p7 firmware |

---

## 1. ★ The official flow is three steps; I only did two

### 1.1 Static analysis finding

`sub_3a888` (the real LoadLut implementation inside `libudd5`) **returns without
waiting for the DMA**:

```c
sub_3a888(p) {
    OnOff(1); Acc_OnOff(0); Acc_OnOff(1);
    switch (p->sel) { case 0/1/2: SetAddress + SetColorFormat... }
    SelLUT(p->sel);
    rw_Start(1);        // ★ start DMA
}                        // ★ push{fp,lr} / pop{fp,pc} — no wait whatsoever
```

And `d5_ep_3dl_load_lut`'s 4th parameter `timeout` is **never used**
(confirmed by disassembly: it is stored into r3 and never participates in any
computation).

★ A whole-library cross-reference scan shows: `load_lut` / `save_lut` / the
`intr_wait` family have **no internal callers inside libudd5**
⇒ **the library does not wait; the application must.**

### 1.2 The complete answer from the official header

```c
D5_EP_INT_ACC_3DLUT_RD_FINISH = 7,  /**< End of Load LUT from DDR on 3DLUT */
D5_EP_INT_ACC_3DLUT_WR_FINISH  = 8, /**< End of Save LUT to DDR on 3DLUT */
int d5_ep_udd_acc_intr_init_wait_queue(struct ep_acc_intr_wait_info *);
int d5_ep_udd_acc_intr_wait        (struct ep_acc_intr_wait_info *);
struct ep_acc_intr_wait_info { int timeout_ms; unsigned jpeg_err; intr; }; // 12B
```

### 1.3 Implementation and measurement

`lutapi.arm` now implements the three-step flow (steps ⓪①②③):

```
⓪ d5_ep_top_acc_intr_en(RD_FINISH=7)          => 0    ★ new: enable the interrupt
① d5_ep_udd_acc_intr_init_wait_queue(1000ms)  => 0
② d5_ep_3dl_load_lut(virt, sel=0, fmt=1, 0)   => 0
③ d5_ep_udd_acc_intr_wait(RD_FINISH)          => 1000 ★ still no interrupt
```

★ **Plan A did have an effect**: after adding `intr_en`, the kernel message
`EP_IOCTL_ACC_INTR_WAIT fail` (`d5_ep_ioctl.c:251`) **no longer appears in dmesg**.
But the interrupt still never arrives.

★ The return value equals the passed `timeout_ms` exactly (300→300, 1000→1000,
2000→2000), while the kernel header explicitly states "on timeout, a **negative**
value `-ETIMEDOUT` is returned" ⇒ **the interrupt genuinely never arrives**.

---

## 2. ★★★ Color-cast investigation: 7 tables and 3 falsified models

### 2.1 Observation summary (the only trustworthy image-layer data)

| # | Table content | Screen result | What it implies |
|---|---|---|---|
| 1 | all `0x0000` | pink / magenta | 0 is a chroma extreme |
| 2 | all `0x8000` | **magenta** | ★ the numeric midpoint is **not** neutral |
| 3 | all `0xFFFF` | cyan-green / magenta-shift | symmetric with #1 |
| 4 | 17-step ramp `0x0000→0xFFFF` | uniform pink, **no bands** | indices don't cover the whole table |
| 5 | checkerboard (alternating 0/FF) | uniform, **no pattern** | ★ probe frequency mismatch |
| 6 | `uniq_seq` (unique value per node) | **pale green-white**, very faint outlines | the index **is** moving |
| 7 | `d1_only` (only ch0 ramps) | magenta (identical to #2) | ★ **ch0 changes have no effect** |

### 2.2 ★ Three theoretical deductions falsified by my own data

```
Deduction 1: all 0 → YCbCr(0,0,0) → green;        actual: pink        ✗
Deduction 2: all 0xFFFF → YCbCr(1,1,1) → magenta; actual: cyan-green ✗
Deduction 3: all 0x8000 = neutral → no shift;    actual: magenta      ✗
```

⇒ Any model of the form "output maps directly to RGB or YCbCr" contradicts the
observations.

★ Dimensions ruled out:

| Dimension | Experiment | Result |
|---|---|---|
| Table size | 17³ (29478B) / 33³ (215622B) | identical symptoms ⇒ not the main cause |
| Axis order | 6 permutations (`gen_axis.py`) | all color-shifted, different directions |
| Parameters | 6 combinations of `fmt × cbcr_ch` | none neutral |
| Call order | added the missing `op_init` | still color-shifted |
| Channel | `d1_only` / `d2_only` / `d3_only` | ch0 has no effect |

---

## 3. ★★★ Full register map: the format fields do not exist

`lutapi.arm regdump` has been extended to dump the entire 4096 bytes:

```
3D LUT @ 0x2082b000 size=4096
★ the 4096 bytes are 16 【identical】 register replicas (one per 0x100)

Each replica has 6 non-zero entries:
  +0x000 OnOff = 0x00000001
  +0x004 Cfg   = 0x00000100   bit8=1  SelLUT=0  CbCr=0
  +0x008 Pulse = 0x00000000
  +0x00c LUT0  = 0x81115200   ★ points into p7 memory
  +0x010 LUT1  = 0x00000000
  +0x0fc       = 0x13020619   ★ repeated 16×, never read before
```

⇒ ★★★★★ **There is no "table depth", "dimension count", or "2D mode" field anywhere**

⇒ ★★★ **"The index only uses some dimensions" is hard-wired in hardware, not
configurable via registers**
⇒ ★★ This directly explains observation #7: `d1_only` has no effect while
`uniq_seq` does
⇒ ★ **No further table experiments can solve the dimension problem**

★ `libudd5` only exposes 5 register offsets (`0x00/0x04/0x08/0x0c/0x10`);
disassembly confirms `SetReg` writes `base+0x0c` (LUT0) and `base+0x10` (LUT1).

---

## 4. ★ `load_lut` has no size parameter

```c
int d5_ep_3dl_load_lut(unsigned *virt, int sel, int fmt, unsigned timeout);
//                     ^^^^ address         ^^^ format       ★ no size

// _udd_ep_3dl_reg_SetAddress @0x1fea4
ldr r3,[r3] ; add r2, r3, #0xc ; ldr r3,[fp,#-8]  → SetReg(base+0x0c, addr)
                                             ★ no length register anywhere

// _udd_ep_3dl_reg_SetColorFormat_LUT0 @0x1fc04
uxtb r3,r3,#0 ; and r3,r3,#1 ; bfi r3,r2,#8,#1
                  ↑ takes only bit0 ★ ORs into Cfg bit8
```

⇒ `fmt` only affects `Cfg` bit8 (420/422 sampling format), **unrelated to table size**
⇒ ★★ **The DMA transfer length is entirely hardware-determined and cannot be
specified from user space**

### 4.1 ★ `ipcc_write_pkt` structure (authoritative)

```c
struct ipcc_buf_info {
    int            core_id;    // +0
    unsigned int   len;        // +4
    int            ret;        // +8
    unsigned char *buf;        // +12
};  // 12 bytes (ARM EABI 32-bit)
```

---

## 5. ★★★ The p7-side `load_lut` (cross-validated against libudd5)

The p7 firmware contains a **same-origin implementation**; both sides cross-validate:

| Evidence | p7 side | libudd5 |
|---|---|---|
| Parameter bounds | `sel < 3 && fmt < 2` | `sel > 2 → -1`, `fmt > 1 → -1` |
| `sel==2` behavior | writes both channels | `sub_3a888` case 2 writes LUT0+LUT1 |
| Prelude sequence | `OnOff(1); Acc(0); Acc(1)` | same |
| Error code | `-300` | `D5_EP_ERR_3DLUT = -300` |

### 5.1 Complete call chain

```c
View::_load  (FUN_0011e20c)
  ├─ FUN_000f6474()                 // GetDataPocket(): fetch the data pocket
  ├─ FUN_000f1b58()                 // read param_1[0x3a]
  ├─ if == 0 → FUN_0009a3e8()       // ★ static 4 slots (pure table lookup)
  └─ if != 0 → FUN_0009a408()       // dynamic 24 slots
        ↓
  FUN_00179314(table, 0, bypass, 0)
     └─ FUN_004a5c44(ptr, sel, fmt)      // validation layer
          └─ FUN_004a5e30(&packed)      // ★★★ the real load_lut
```

### 5.2 Struct layout revealed by `FUN_004a5e30` (★ authoritative)

```c
FUN_004a5e30(int param_1, ...) {
    if (param_1[+1] == 1) {          // ★ [+1] = op mode: 1=Load 2=Save
        FUN_004cf3d4(1);             // OnOff(1)
        FUN_004cf45c(0);             // Acc(0)
        FUN_004cf45c(1);             // Acc(1)
        cVar1 = param_1[+0xc];      // ★ [+0xc] = sel (0/1/2)
        if (sel == 1) { FUN_004cf4b4(*(ptr*)[+8], ...);    // +8 = LUT1 descriptor
                        FUN_004a5de4(sel, *(u8*)(*(int*)[+8] + 8)); }
        if (sel == 0) { FUN_004cf4b4(*(ptr*)[+4], ...);    // +4 = LUT0 descriptor
                        FUN_004a5de4(sel, *(u8*)(*(int*)[+4] + 8)); }
        if (sel == 2) { ★★ both paths }
    }
    else if (param_1[+1] == 2) { ... }// Save path
}
```

⇒ ★★★ **Byte `+8` of the descriptor is `fmt`**
　　(`FUN_004a5de4(sel, *(u8*)(descriptor + 8))`)

### 5.3 p7's four static slots (★ key)

```c
undefined4 FUN_0009a3e8(ctx, fmt, cbcr) {     // ★ pure lookup, no conversion
    uVar2 = DAT_003837f4; uVar1 = DAT_003837f0;
    if (param_3 != 1) { uVar2 = DAT_003837fc; uVar1 = DAT_003837f8; }
    if (param_2 == 1) { uVar2 = uVar1; }
    return uVar2;
}
```

Actual contents at those image offsets (dual-verified against on-device `regdump`):

| Symbol | Value | Slot |
|---|---|---|
| `DAT_003837f0` | `0x810fd100` | Standard |
| `DAT_003837f4` | `0x81101e00` | Black & white |
| `DAT_003837f8` | `0x81106b00` | Cinema |
| `DAT_003837fc` | `0x81115200` | Skin tone ★ currently active |

---

## 6. ★★★ p7 address-space model: identity mapping over 4GB

p7's MMU initialization (`FUN_00000140`, verified with capstone):

```c
coproc_moveto_Control(uVar2 | 0x30000400);       // enable MMU
uVar2 = DAT_00000240;                // = 0x402
puVar3 = (uint *)&DAT_81000000;      // page table base 0x81000000
uVar4 = 0;
do {
    *puVar3 = uVar4 | uVar2;         // PTE[i] = (i*1MB) | 0x402
    uVar4 += 0x100000;
} while (uVar4 != 0);                // ★ 4096 entries, covers 0x0-0xF0000000

puVar5 = 0x80000000; puVar3 = 0x81002000;
do {
    *puVar3 = (uint)puVar5 | 0x1c0e;  // 2nd round: 0x80000000-0x80FFFFFF
    puVar5 += 0x100000;
} while (puVar5 != 0x81000000);      // ★ only 16 entries
```

### 6.1 Per-address resolution

| Address | Purpose | PTE | Origin | Conclusion |
|---|---|---|---|---|
| `0x8f800000` | **Linux CMA region 2** | `0x8f800402` | slot 2296 | ★★★ **visible to p7** |
| `0x94411000` | CMA region 1 | `0x94400402` | slot 2372 | ★ visible to p7 |
| `0x810fd100` | p7 static slot (standard) | `0x81000402` | slot 2064 | ✔ |
| `0x81115200` | p7 static slot (skin tone) | `0x81100402` | slot 2065 | ✔ |

⇒ ★★★ **The first round is an identity mapping (VA == PA) covering 0–3840MB**
⇒ ★★ The second round only changes attributes of `0x80xxxxxx` (`0x1c0e` = coarse
page); it does **not** affect the `0x8f` range

### 6.2 Dual-core structure, empirically proven

The kernel crash print shows `CA9 user fault`; combined with `d5_lib.h`:

```c
enum d5_intr_type {
    INT_IPCC_CA7_1, INT_IPCC_CA7_2,      // ★ CA7 = Linux (Cortex-A7)
    INT_IPCC_CA9_1, INT_IPCC_CA9_2,      // ★ CA9 = p7   (Cortex-A9)
    INT_IPCC_CM4_1, INT_IPCC_CM4_2, INT_IPCC_CM4_3,   // CM4 = coprocessor
    INT_IPCC_SRP, INT_IPCC_MAX, ... };
```

⇒ **Camera = CA7 (Linux) + CA9 (p7) + CM4 (coprocessor), three cores**

---

## 7. ★ Linux reading p7 memory: every channel eliminated

| Channel | Measured result |
|---|---|
| `/dev/mem` | ✘ **unavailable entirely** (even the known-readable `0x2082b000` gives Bad address) |
| `/proc/iomem` | ✘ empty |
| `/proc/maps` | ✘ only ordinary user-space segments |
| EP `GET_PHYS_REG_INFO` | ✘ only returns `0x2082b000` (hardware registers) |
| SMA `/dev/d5_sma` mmap | ✘ restricted to declared regions |
| IPCC | ✘ see §8 |

⇒ ★★★ **`/dev/mem` is entirely unusable on this device** (kernel built without
`CONFIG_STRICT_DEVMEM`)
⇒ ★★ This **corrects** the earlier conclusion "p7 memory is not in Linux iomem"
— the real reason is that **there is no read channel at all**

### 7.1 Complete address-space model

```
┌─ p7 (Cortex-A9) ─────────────────────────┐
│ identity mapping 0x0-0xF0000000 (4GB)    │
│ valid: 0x80xxxxxx (image) + 0x81xxxxxx    │
│ static slots: 0x810fd100 ... 0x81115200   │
└──────────────────────────────────────────┘
┌─ Linux (Cortex-A7) ─────────────────────┐
│ CMA usable: 0x94000000(144MB)/0x8f800000  │
│ cannot read p7 memory (no channel)        │
└──────────────────────────────────────────┘
            ↓ same physical DRAM ↓
```

⇒ **Two software address spaces; the physical memory is shared**
⇒ ★ p7 can see Linux CMA; **Linux cannot see p7's tables**

---

## 8. ★★★ The official IPCC interface: complete API, but p7 Oops

### 8.1 The complete official API (`ipcc.h:28-37`)

```c
int      ipcc_open(void);
void     ipcc_close(void);
void     ipcc_int_set_callback(enum d5_intr_type, void (*)(void));
unsigned int ipcc_get_write_available(int core_id);
unsigned int ipcc_get_read_available(int core_id);
unsigned int ipcc_get_read_pkt_lenth(int core_id);
unsigned int ipcc_read_pkt (unsigned char *buf, int core_id, unsigned len);
unsigned int ipcc_write_pkt(unsigned char *buf, int core_id, unsigned len);
unsigned int ipcc_raw_send_interrupt(enum d5_intr_type);
```

`libudd5` exports **14 `ipcc_*` symbols, all `STB_GLOBAL`**; 12 resolve via
`dlsym` on the real device.

### 8.2 Bypassing the library lock: raw ioctl works

`ipccraw.c` successfully uses `open("/dev/d5_ipcc")` + raw `ioctl` to bypass
`libudd5`'s `pthread_mutex` + `d5_udd_open(2,1)` locking.

★ **But the ioctl numbers must come from the library's actual code** (§8.4).

### 8.3 ★★ `IPCC_INIT` triggers a p7 (A9) Oops

```
ipccraw.arm scan  ⇒ process killed by kernel, zero output
dmesg:
  [<c00c91dc>] (sys_ioctl+0x74/0x7c) from [<c000eb00>] (ret_fast_syscall)
  ret = 0                              ← open succeeded
  A9 kernel fault(Oops - BUG)          ← ★★ p7 side crashes
  ---[ end trace 8dd9f487dc7dedaa ]---
Camera survives (loadavg normal, SSH up, audio path continues)
```

⇒ ★★★★ **`IPCC_INIT` (0xc0087401) crashes p7**
⇒ ★★ This explains the segfault when `ipccprobe` called `ipcc_open()` — it was
never a lock problem: **the IPCC initialization itself crashes p7**

### 8.4 ioctl numbers (★ authoritative = library-measured, do NOT use header macros)

| Name | Value | vs NX1 GPL header |
|---|---|---|
| `IPCC_INIT` | `0xc0087401` | — |
| `IPCC_GET_WRITE_AVAIL` | `0xc0087403` | ✔ match |
| `IPCC_GET_READ_AVAIL` | `0xc0087404` | ✔ match |
| `IPCC_GET_READ_PKT_LENTH` | `0xc0087405` | ✔ match |
| `IPCC_READ_PKT` | `0xc0107406` | ✘ header gives `0xc00c7406` (size 12 vs 16) |
| `IPCC_WRITE_PKT` | `0xc0107407` | ✘ same |
| `IPCC_RAW_INT_WAIT` | `0xc008740b` | ✘ header nr=10, library says nr=11 |

⇒ ★★★★★ **The NX1 GPL header and the real `libudd5` disagree on ioctl size/nr**
　⇒ ★ **Use the library-measured values**

---

## 9. ★★ The official data entry point, on the p7 side

`FUN_000f6474` is "fetch the data pocket". Its DAT constants, after
two-level dereferencing:

```
DAT_000f655c -> 0x806ede0c  "Assertion Failed! %s --- File %s Line %d\n"
DAT_000f6560 -> 0x8070eed4  "product/Liveview/common/CLiveviewFactory.cpp"
DAT_000f6564 -> 0x8070dcc0  "m_pcLiveviewDataPocket != __null"
DAT_000f6568 -> 0x806ede04  "ASSERT"
DAT_000f656c -> 0x8057e458  "GetDataPocket"          ★ method name
```

⇒ ★★★ **"Data pocket" is Samsung's own naming** (`GetDataPocket`)
⇒ ★ Source file: `product/Liveview/common/CLiveviewFactory.cpp`

★ **Dereferencing technique**: DAT variables (Ghidra address `0x000f6xxx`) hold
runtime load addresses `0x8xxxxxx` ⇒ `file offset = va - 0x80000000`
⇒ ★★ This is the way around "string xrefs are always 0"

### 9.1 It is not a socket

The PAL layer consists entirely of system-call stubs:

```c
FUN_004d9ee8(){ software_interrupt(6); }   // recv
FUN_004d9a8c(){ software_interrupt(6); }   // send
// whole-library SVC tally: #0x08 × 105, #0x06 × 86, #0x09 × 7
```

⇒ The SVC handler is **not inside `p7_full.bin`** (that is the user-space image)
⇒ Camera-side verification: `/proc/net/tcp` listens on `21/22/23/53/80/8080`
with **no p7 IPC port**; `/proc/net/unix` contains only X11/dbus/pulse/alsa
⇒ ★★★ **The data pocket does not go through sockets** (shared memory / mailbox / IPC)

---

## 10. ★★ Verdict on "reuse the official p7 path"

| Plan | Approach | Verdict |
|---|---|---|
| **A** | patch p7's `DAT_003837f0` to point at my table | ✘ **Linux has no channel to write p7 memory** |
| B | patch the pointer initial values in the p7 firmware image | ✘ requires reflashing p7, high risk |
| C | load an identity table to neutralize the picture, then layer on top | ✘ no neutral table produced yet |

★ Physical preconditions for plan A:
① patch p7's pointer → **✘ all channels eliminated (§7)**
② p7 can read Linux CMA → **✔ yes (§6)**
③ will p7 overwrite it → untested

---

## 11. ★★★ Tool inventory (new today)

| Tool | Purpose | Status |
|---|---|---|
| `test_server/sysarch/ipccprobe.c/.arm` | IPCC symbol resolution + `ipcc_open` probe | ★ `scan` segfaults (p7 Oops) |
| `test_server/sysarch/ipccraw.c/.arm` | **raw ioctl IPCC** (bypasses library lock) | ★ `scan` triggers A9 Oops |
| `test_server/filmsim/coverprobe.py` | coverage probes (all-zero / all-FF / half) | ✔ self-test passes |
| `test_server/filmsim/ramp.py` | step-ramp probe (17 steps, u16) | ✔ self-test passes |
| `test_server/sysarch/lutapi.c` | `regdump` extended to a **full 4096B dump** | ✔ deployed |

Probe tables (in `test_server/sysarch/verify/`, covered by `.gitignore`):

```
pz_14739/19652/29478/39304.bin   all-zero, varying lengths
pf_29478.bin                    all-FF
ph_29478.bin                    first half FF, second half 00
ramp16.bin / ramp8.bin          step ramps
chk_alt.bin / chk_axes.bin      checkerboards
uniq_seq.bin                    unique value per node
d1_only / d2_only / d3_only.bin single-dimension ramps
pfx_000006 .. pfx_029478.bin    first K bytes FF
```

---

## 12. ★★★ Methodological lessons (all from actual failures today)

### 78 ★★ Always rule out display-chain artifacts before interpreting

I was interpreting the screen **by photographing an LCD with a phone**, so the
pixel grid, moiré, and brightness non-uniformity were all mixed into the signal.
**Three times in a row I mistook display artifacts for data corruption**:

| What I said | What it actually was |
|---|---|
| "tearing artifacts" | the wood grain of the user's desk |
| "colored dot matrix" | the AMOLED subpixel structure |

⇒ ★ In color-shift experiments, **"is the image structure intact" is the easiest
thing to misjudge**, because when the chroma LUT is wrong the luma passes
through and the structure looks naturally fine

### 79 ★★ Vendor GPL headers ≠ real library implementation

`ipcc_read_pkt`: header computes `0xc00c7406`; the real library uses
`0xc0107406` (size field 16 vs 12).
★ I got the ioctl encoding **wrong three times** (type/nr order, size field,
`RAW_WAIT`'s nr)
⇒ ★★ **The same class of error three times in a row means: change method**
　The correct approach: read the value straight out of the `movw/movt` immediate
field; do not hand-roll bitfield extraction

### 80 ★★ Compute magnitudes before proposing timing/race hypotheses

I hypothesized "didn't wait for the DMA interrupt → table is half-written →
posterization":

```
29478 bytes ÷ DDR2 2GB/s = 14.74 µs
my settle wait          = 200000 µs      ← 10,000× larger
```

⇒ ★★★ **The table contents were complete long before 200ms**; the hypothesis
is physically impossible
⇒ ★ The detour into "waiting for the interrupt" would not have fixed the color
cast even if completed

### 81 ★★ A probe's spatial frequency must match the signal being measured

The checkerboard probe (period 2) produced cancelling patterns when the index
jumps by larger steps, making it look like "the table isn't being read" — yet
`pfx_000006` (only 6 bytes changed) produced a strong pattern.
⇒ ★ **When a carefully designed probe shows no response, suspect the probe's
assumptions first**

### 82 ★★ Cross-process/cross-core memory maps must be computed by hand

p7's page table lives at `0x81000000`, while `/dev/mem` is unusable on the Linux
side.
⇒ ★ The rule: **address spaces are separate; only physical memory is shared**

---

## 13. ★ Conclusions and next steps

### 13.1 Fully working (reusable)

```
★ Official user-space API (op_init + load_lut; sel=0 does not garble)
★ CMA landing-spot probing (dual region + adjustable granularity, 216MB @ 116ms)
★ Full 3D LUT register map (16 replicas; format fields hard-wired)
★ Complete p7 call chain + cross-validation against libudd5 (same-origin)
★ p7 address-space model (identity map over 4GB; CA7 + CA9 + CM4)
★ Official IPC API (12 symbols resolve; raw ioctl bypasses the library lock)
```

### 13.2 Two blockers

```
✖ Color cast: LUT table format (dimensions hard-wired + readback unusable)
✖ Data-pocket writes (IPCC_INIT → p7 A9 Oops)
```

⇒ ★★ **Both require modifying p7 firmware** — a different order of engineering

### 13.3 ★★ Reflection on ordering

> I spent 7 tables and 3 falsified models trying to guess the LUT format —
> but **the format is decided by p7**. The correct order is to **open the data
> pocket first, then talk about format**.

⇒ ★ If I did this again, the first thing would be investigating IPCC, not
loading the first table

---

*End of document. Companion: [`3DLUT_API_GUIDE_EN.md`](3DLUT_API_GUIDE_EN.md)
(operations manual),
[`LIBUDD5_EP_API_MAP_2026-10-06.md`](LIBUDD5_EP_API_MAP_2026-10-06.md) (API map).*
