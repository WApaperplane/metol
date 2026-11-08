# Metol (formerly NX-WA)

An enhancement mod for the **Samsung NX500 / NX1** (Tizen / DRIMe5), built on the community
[`ottokiksmaler/nx500_nx1_modding`](https://github.com/ottokiksmaler/nx500_nx1_modding) upstream.

**Repository** [WApaperplane/metol](https://github.com/WApaperplane/metol) (a fork; default branch `nxwa`) ·
**License** AGPL-3.0 (lineage in [ATTRIBUTION.md](ATTRIBUTION.md)) ·
**Download** [Releases](https://github.com/WApaperplane/metol/releases)

> 中文版见 [README.md](README.md)

**Latest v2.88.0-nxwa.15** (2026-11-08) — instant LUT switching: no more half-press.
`lut.sh apply/off` loads the table itself and waits for the DMA-complete interrupt,
so picking a look in the panel updates the finder immediately.

## Install

1. Put `info.tg`, `nx_cs.adj`, `install.sh` and `scripts/` at the **root of the SD card** (or unzip `NX-WA-<version>.zip` there).
2. Insert the card → it installs automatically and shows "install complete".
3. **Turn Bluetooth on once by hand** — the mod's boot hook is initialised by it.

- Firmware: NX500 **1.12** / NX1 **1.41**; anything else is refused.
- Inserting the card again = **incremental sync** (overwrite only, never delete, never auto-uninstall); uninstall from the camera menu (`uninstall.sh`).
- Install / sync / WiFi push / rollback: [SYNC.md](SYNC.md) (bilingual).

## Key shortcuts

| Keys | Opens | Notes |
| --- | --- | --- |
| **EV + AEL** | **Filter strip** (NXUI, 720×208) | 79 recipes, horizontal scroll plus a draggable/tap-to-jump scrollbar; tap = **instant preview** (~1.3 s, always rendered into the Custom 1 canvas); `Save & close` commits and returns the field you started from; press again or **half-press** to close. **NX500 only** — NX1 falls back to the community script |
| **EV + WiFi** | **LUT panel** | Opens NXUI's LUT mode (`nxui.sh lut`); **closing the panel restores nothing** — use the panel's `Restore` button to go back to the factory tables. If NXUI is not enabled you just get a one-line popup |
| **Double-tap EV** | Main menu (NXUI, 720×336) | Paginated screen, replaces the old mod_gui menu |
| **Half-press** | Closes the current panel | For the LUT panel it closes the panel and **keeps the current table**, while letting p7 reload it — shoot with the LUT still applied |

> **EV + WiFi is a combo**: hold EV, then press WiFi. A single WiFi press stays the camera's native behaviour (WiFi on/off); they do not conflict.

The camera menu also has four entries: `IP: x.x.x.x [Telnet关]` (tap to toggle 23/21), `远程控制` (web gallery on/off), `LUT 滤镜` (same UI as EV+WiFi) and `TC 曲线` (Utility → Stock / Log / Flat / High contrast).

## Features

| Capability | In one line |
| --- | --- |
| Film recipes | 79 (negative / slide / B&W / cinema / stylised / camera-look); all seven PW dimensions pushed into the ISP at once |
| 3D LUT | `.cube` converted on-camera in one command; **edit a 4-byte registry entry + write 19,712 B into a spare slot + half-press** to retarget; live view and stills are independent chains; **video follows `apply` — just press record** |
| TC curve | Four video tone-curve presets (Stock / Log / Flat / High contrast): write 19 nodes + set dirty, **the ISP consumes it in <50 ms with no keypress**, reboot restores stock |
| NXUI | Nuklear (MIT) on the camera's own X11/Xft — **no EFL**, no viewfinder capture or blit |
| Web gallery | Collapsed directories + live `dirlist` (new photos appear instantly) + thumbnail pre-warm + over-the-air push |
| Original NX-KS modules | Video bitrate, HDR, batch recording, zoom, resolution tweaks, shooting-parameter API … |

## FilmLab recipes

| Family | Examples (79 total: 71 colour + 8 B&W) |
| --- | --- |
| Colour negative | Portra 400/800, Gold 200, Ektar 100, Superia 400, ProImage 100, Vista 200 … |
| Slide | Velvia 50/100, Provia 100F/400X, Ektachrome E100, Kodachrome 25/200 … |
| B&W | TriX 400, HP5 Plus, Delta 3200, T-MAX 100/400, Acros 100, XP2 Super … |
| Cinema | CineStill 800T/50D, Vision3 250D/500T, Double-X 5222, Eterna 500T |
| Stylised | Teal-orange / warm-faded / cold / bleached / high-key / low-key / sepia / bleach-bypass / blue hour / X-Pro |
| Camera looks | Ricoh GR (Positive / Negative / Retro / Bleach / Cross-process), Pentax Custom Image (Vivid / Reversal / Bleach Bypass / Muted / Satobi / Gold) |

- **Recipes need no code change**: edit `/mnt/mmc/filmlab/recipes.json` → copy back to SD → reopen the menu (it rebuilds itself). The authoritative source in-repo is `scripts/filmlab/recipes.json`; host-side CLI: `test_server/filmlab/flab.py add|edit|rm|lint|deploy`.
- A recipe is a Picture Wizard 7-value vector (R/G/B gain + HUE/SAT/SHARP/CONTRAST), always written into the **Custom 1** slot.
- **The full 7-dimension push needs the A2 firmware** (`patch-a2/`, shipped with a flashing guide and md5). On stock firmware R/G/B/HUE need one confirmation in **Picture Wizard → Custom 1** — a structural limit of p7's normaliser domain (`0x100–0x12e`), not a script bug.
- Honest limits: WB is not part of a recipe (use the camera's white balance); a recipe is a global colour vector, it cannot do highlight roll-off or zone-based exposure; NX1 is not enabled (the prefman offsets were only proven on NX500 1.12).
- One criterion only: `sh /opt/usr/nx-ks/filmlab.sh check` reads the seven values the ISP is actually using (read-only, zero risk). **"The value changed" ≠ "the value is consumed"**.
- There is also `scripts/nx-rc/MOBILE_MOBILE.sh` (double-tap WiFi = rotate to the next recipe with no UI) — it is not part of the install chain; copy it to `/opt/usr/nx-ks/` if you want it.

## 3D LUT

| Item | Status |
| --- | --- |
| Table format | `4913×4B {Cr,Cb,Y,pad}`, index `((Y*17+Cb)*17+Cr)*4`, slot 19,712 B, stride `0x4D00` (closed on-device 10-19; the older RGB naming is retired) |
| Retarget | Write 19,712 B into the work slot (A18 `0x81119F00`) + point **all four** registry tables at it + **half-press once** |
| Registry tables | `View4` (4 entries, colour space × screen colour) + `Still6` (6) + `BV12` (12) — **none may be skipped**, or you get "viewfinder filtered, photo not" |
| Import | `.cube → 19,712 B slot table` via on-camera `cube2lut.arm`, or host-side `test_server/isp/nx3dlut.py` |
| Generation basis | Built for the **measured camera input domain**: response slope `log2(code)/EV = 0.809`, not sRGB's 0.45 (a 1.8× gap). Tables built on the sRGB assumption get crushed twice in the shadows; 34 of the 68 bundled tables have been regenerated against the real response (25 G'MIC + 9 recipe tables), the other 34 have no traceable generator and are untouched |
| Live view / stills | Live view reads only `View4`; stills have **two mutually exclusive branches** (screen colour on → `BV12`, off → `Still6`) and both must be retargeted |
| Video | After `apply`, just press record — **the very first frame already carries the table** (p7's 23-entry slot pointer table is redirected to A18); `off` stops the watcher. Long takes and other frame rates are untested |
| Limits | Pure memory operations — **power cycle restores stock** (boot-persistent needs an image patch). Colour is trustworthy in sRGB; AdobeRGB only guarantees "it applies" |
| No-go | ⛔ Writing `+0x00C` yourself and pulsing the config register makes the ISP read out-of-sequence addresses ⇒ **severe colour corruption**. The only safe reload is **half-press** |

### Library and blending

| Capability | Command |
| --- | --- |
| Library | `lut.sh list [--fav]` / `fav` / `move up\|down\|top` / `del` / `index` / `stock` |
| Cross-fade | `lut.sh mix <A> <B> <0-100>` |
| Strength of one look | `lut.sh strength <name> <0-100>` (0-end = stock A17; run `lut.sh stock` once first) |
| **Two looks, two strengths** | `lut.sh blend <A> <r 0-100> <B> <s 0-100>` — `r` = A/B ratio, `s` = total strength |
| Video LUT | No separate switch: starts with a successful `apply`, stops on `off`. Diagnose with `lut.sh video on\|off\|status` (`on` takes an optional second count) |

Order and favourites live in `lut/state/order` on the card (one name per line, `*` = favourite).
Removal is a **move to `looks/_trash/`**, never an `rm` — deleting a duplicated name on exFAT
releases the cluster chain and corrupts the siblings.

Blending is **normalised weighting**: `r = B/(A+B)` picks the mix, `s = min(A+B, 100)` the strength,
`T = stock + s·(mix(A,B,r) − stock)`. Both at 100% therefore lands on the midpoint instead of
clipping — offset-summing clips 14% of the table, layer-compositing shifts 7–30 levels when you
swap A/B. See [`docs/current/DUAL_STRENGTH_2026-11-02.md`](docs/current/DUAL_STRENGTH_2026-11-02.md).

### Panel keys (NX500 hardware keys, all measured)

| Key | Browse | Edit | Mix |
| --- | --- | --- | --- |
| Up / Down · EV dial | page | — | page |
| Left / Right | page | — | pick A / B focus |
| Centre OK | apply & close | done | apply blend |
| Play ▶ | enter edit | — | — |
| Long-press a row | enter edit | — | — |
| Fn | enter mix | — | leave mix |
| Top-right dial | page | — | adjust focused strength (5%/step) |
| BACK · MENU | close | close | close |

> Only the edit state changes the library. A/B is set with the button row
> (`Set A` / `Set B` / `Apply` / `Exit`); leaving the mix state does **not** apply.
> Keys are overridable via `$NXUI_STATE_DIR/keys.conf`, one `<keysym> <action>` per line, `none` unbinds.

```sh
sh /opt/usr/nx-ks/lut.sh list | begin | apply <name> | off | status   # looks live in /mnt/mmc/looks/
sh /opt/usr/nx-ks/lut.sh video on|off|status                          # recording watcher; normally automatic
```

Details: [`docs/current/LUT_RETARGET_LIVE_2026-10-18.md`](docs/current/LUT_RETARGET_LIVE_2026-10-18.md) · panel design: [`docs/current/LUT_UI_2026-10-18.md`](docs/current/LUT_UI_2026-10-18.md)

## TC curve (video tone curve)

p7's video chain carries a **19-node tone-curve table** ahead of the 3D LUT. It is not
`MOVIE_GAMMA_CONTROL` (that interface has no consumer on NX500 1.12) — it is the data table itself:
write 19 Y values → set the dirty flag → **the ISP consumes it within 50 ms, no keypress**.

| Item | Status |
| --- | --- |
| Table | 19 nodes, X fixed at `0–16383`, Y `0–1023`, first 0 / last 1023, strictly increasing |
| Address chain | `Param0 = read32(0x817dccbc)` → `Gamma = read32(Param0+0x170)` → `Y[i] = Gamma+0xe8c+4i`; **re-resolved with signature checks on every run** — the heap address moves per boot and cannot be hard-coded |
| Entry | Menu `Utility → TC curve` (Stock / Log / Flat / High contrast), or `tc.sh set log\|flat\|hc` |
| Reach | Enters the HEVC stream: same-scene A/B clips, full-frame Y mean **63.26 → 98.83**, mapping 4→17 / 52→102 / 180→186 |
| Rollback | `tc.sh off` restores stock; a reboot does it too (runtime memory only, no firmware write) |

```sh
sh /opt/usr/nx-ks/tc.sh status             # stock?, Y[9], descriptor
sh /opt/usr/nx-ks/tc.sh list               # /mnt/mmc/tc/*.tcy
sh /opt/usr/nx-ks/tc.sh set log|flat|hc    # or any .tcy
sh /opt/usr/nx-ks/tc.sh off
```

Honest limits:

- **A programmable curve is not extra dynamic range.** The container is still 8-bit 4:2:0 with no 10-bit ground; the Y-mean lift is curve shape, not exposure drift, and not a net DR gain (the strict-threshold interval includes zero).
- The anchor is **mid-grey** (camera 128 ↔ sRGB 128); a white-point anchor shifts everything by ~35 codes and needs an 18% grey card to settle.
- **TC moves the 3D LUT's input domain** — changing both at once requires recalibration.
- Writes are allowed only in idle preview (directory lock, recording detection, item-by-item readback, automatic restore on any failure); **switching while recording, and whether the photo path is affected, are untested**.

Details: [`docs/current/TC_CURVE_ONDEVICE_2026-11-08.md`](docs/current/TC_CURVE_ONDEVICE_2026-11-08.md) · restoration workflow: [`docs/current/TC_RESTORATION_WORKFLOW_2026-11-08.md`](docs/current/TC_RESTORATION_WORKFLOW_2026-11-08.md)

## Layout

| Path | What |
| --- | --- |
| `install.sh` `info.tg` `nx_cs.adj` | SD-card trigger trio (install / incremental sync) |
| `scripts/` | All modules → synced to the camera's `/opt/usr/nx-ks/` |
| `scripts/filmlab.sh` · `scripts/filmlab/recipes.json` | FilmLab engine / authoritative recipe library (79) |
| `scripts/EV_AEL.sh` · `scripts/EV_MOBILE.sh` | The two key-combo entry points (`EV+AEL` strip / `EV+WiFi` LUT panel) |
| `scripts/lut.sh` · `scripts/lut/` | 3D LUT entry + toolset (`cube2lut` / `nx_slotwrite` / `nx_regtabwrite` / `nx_regtabdump` / `nx_lutload` / `nx_lutptr` / `lutmix`) |
| `scripts/lut_video.sh` | Recording LUT watcher (starts with `apply`, stops on `off`; locks and state in `/tmp`) |
| `scripts/tc.sh` · `scripts/tc/*.tcy` | TC curve writer + curve library (Stock / Log / Flat / High contrast) |
| `scripts/gui_tc.NX500` | Native menu entry: Utility → TC curve |
| `tools/tcgen/` · `tools/lutgen/` | Host-side tools: curve generation / read-only chain verification / LUT generation and audit |
| `scripts/nx-rc/` | Web remote: `web_root/` `thumb/` `capdtm/` `push/` |
| `test_server/` | Host-side development environment (simulated API, toolchain, gates) |
| `uninstall_pkg/` | Camera-menu uninstall entry |

## Docs

- [`docs/README.md`](docs/README.md) — **documentation index** (`current` / `archive` / `evidence`)
- [`docs/current/HANDOVER_2026-10-16.md`](docs/current/HANDOVER_2026-10-16.md) — master entry: conventions, dead ends, gates, order of execution
- [`docs/current/ONDEVICE_SOP_2026-10-16.md`](docs/current/ONDEVICE_SOP_2026-10-16.md) — on-camera day SOP (setup / criteria / rollback)
- [`docs/current/NXUI_NUKLEAR_2026-10-17.md`](docs/current/NXUI_NUKLEAR_2026-10-17.md) — NXUI install & verification
- [`docs/current/TC_CURVE_ONDEVICE_2026-11-08.md`](docs/current/TC_CURVE_ONDEVICE_2026-11-08.md) — TC curve: address chain, write protocol, on-device A/B
- [`docs/current/VIDEO_LUT_FIRSTFRAME_2026-11-07.md`](docs/current/VIDEO_LUT_FIRSTFRAME_2026-11-07.md) — LUT from video frame 1: p7's slot pointer table
- [`docs/current/LUT_INPUT_CALIBRATION_2026-11-07.md`](docs/current/LUT_INPUT_CALIBRATION_2026-11-07.md) — input-curve measurement protocol and results
- [`docs/current/RE_PROGRESS_2026-10-08.md`](docs/current/RE_PROGRESS_2026-10-08.md) — reverse-engineering overview (with the dead-end list)

> Old conclusions in historical docs (e.g. "View/Still cannot be separated", "user space cannot write LUT data") have been overturned — see
> [`ERROR_CORRECTIONS_2026-10-07.md`](docs/current/ERROR_CORRECTIONS_2026-10-07.md).

## Boundaries

Stated plainly — every row below maps to an on-camera or static verification, not to "should work".

| Dimension | ✅ Works | ❌ Does not / unverified |
|---|---|---|
| Platform | NX500 firmware **1.12** (everything verified on device) | NX1 1.41 installs, but LUT / FilmLab are **not verified on NX1**; other firmware versions are rejected by the installer |
| Colour | Colour is trustworthy in **sRGB** for both live view and JPEG (baseline of the 68 bundled tables, 34 of them generated against the measured input domain) | **AdobeRGB applies but is not colour-calibrated**; the camera's Smart Filter enum 14–18 takes a separate 24-slot dynamic path that this mod does not cover |
| Carrier | **JPEG stills + viewfinder + video (LUT from frame 1)** | **RAW (`.SRW`) is not promised to be baked**; the ground is 8-bit 4:2:0 only (10-bit unreachable, the built-in gamma interface has no consumer); long takes and other frame rates untested |
| Video curve | **Four TC presets, effective in <50 ms and carried into HEVC** | Redistributes 256 code values only — no dynamic range is created; absolute anchor needs a grey card; switching while recording, stacking with the 3D LUT and any effect on the photo path are unverified |
| Taking effect | LUT needs **one half-press** after the memory write; TC is consumed **within 50 ms with no keypress** | **No boot persistence** — a power cycle restores stock; that needs a firmware image patch |
| Trigger | **Half-press** is the only reliable reload | No software trigger found for making p7 re-read the table (`st cap iq af afsta/afsto` is a no-op) |
| Shape | No reflash, no partition writes, fully reversible | No firmware-partition change means a reboot restores stock (LUT writes are RAM-only) |

> It is **not** a colour-management system (no input/output profile conversion), **not** a WYSIWYG promise
> (live view and stills run different pipelines), and **not** a jailbreak (no region unlock, no recording-limit bypass).
> What it edits is two tables inside the ISP: the terminal 3D lookup table and the video tone curve.

## Known ceilings (p7 / firmware level, not script bugs)

- **The full 7-dimension one-tap needs the A2 firmware**; on stock firmware values outside the normaliser domain are rejected.
- **p7 has no UI** (Font/DrawText/Dialog/Widget all zero hits) ⇒ the UI can only live on the Linux side.
- **3+ key combos are not available** (the kernel consumes keys first) ⇒ only "hold EV + one key" style two-key combos work; a long-press is timed by NXUI from press/release, not a hardware event.
- **TC only changes shape, not bit depth**: remapping 256 code values inside an 8-bit 4:2:0 container creates no new dynamic range; `MOVIE_GAMMA_CONTROL` / `IQ[180]` has no consumer and 10-bit encoding does not exist in the firmware.
- Factory LUT tables are **all style tables** — "write identity to get neutral" is not a valid criterion.

> The film-simulation engine and `.cube` assets live in a separate repo:
> [nx500-filmsim](https://github.com/WApaperplane/nx500-filmsim) (public).
