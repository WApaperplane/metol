# Metol (formerly NX-WA)

An enhancement mod for the **Samsung NX500 / NX1** (Tizen / DRIMe5), built on the community
[`ottokiksmaler/nx500_nx1_modding`](https://github.com/ottokiksmaler/nx500_nx1_modding) upstream.

**Repository** [WApaperplane/metol](https://github.com/WApaperplane/metol) (a fork; default branch `nxwa`) ·
**License** AGPL-3.0 (lineage in [ATTRIBUTION.md](ATTRIBUTION.md)) ·
**Download** [Releases](https://github.com/WApaperplane/metol/releases)

> 中文版见 [README.md](README.md)

**Latest v2.88.0-nxwa.15.3** (2026-11-10) — bilingual release: every version ships two packages,
`NX-WA-<ver>.zip` (Chinese) and `NX-WA-<ver>-EN.zip` (English menus / English NXUI panel / English
README), with release notes in both languages.

---

## 30-second start

1. Unzip `NX-WA-<ver>-EN.zip` to the **SD-card root** → insert the card → "install complete" → the camera reboots.
2. **Turn Bluetooth on once by hand** (menu → Settings → Enable Bluetooth) — the mod's boot hook is initialised by it.
3. Learn four keys:

| Key | Opens | Note |
|---|---|---|
| **EV + AEL** | FilmLab strip (79 recipes) | tap to preview, `Save & close` persists |
| **EV + WiFi** | 3D LUT panel (86 tables) | tap to switch, **no half-press needed** |
| **Double-tap EV** | Main menu (NXUI paged UI) | items are listed in [Camera menu](#camera-menu) |
| **Half-press** | Closes the current panel | the applied look **stays** after closing |

> All combos are "hold EV, then press the other key". A plain WiFi press is still the camera's own WiFi toggle.

## Troubleshooting: read the log before touching anything

### Three recovery commands

```sh
sh /opt/usr/nx-ks/nxui.sh disable    # UI misbehaving -> back to the legacy mod_gui menu
sh /opt/usr/nx-ks/lut.sh off         # wrong colours -> back to the stock LUT
sh /opt/usr/nx-ks/tc.sh off          # video curve -> back to stock
sh /opt/usr/nx-ks/nxui.sh diag       # is the panel usable? all five checks at once
```

`nxui.sh diag` prints `bin / model / disabled / enabled / available`. `available: no` has only three
causes: the binary is missing, the model is NX1, or someone ran `disable`.

### Where the logs are

| Path | Written by | Survives power-off? |
|---|---|---|
| `/mnt/mmc/nx-ks/pwrlog.txt` | `pwrlog.sh` (15.1+, one line per 30 s, plus a `BOOT` record) | yes — SD |
| `/mnt/mmc/lut/state/*.log` | `lut.sh`, one per step (write / view / still / bv / lutptr / kick) | yes — SD |
| `/mnt/mmc/filmlab/last.log` | last recipe-apply context | yes — SD |
| `/opt/usr/nx-ks/onboard.log` | install self-check (telnet / ssh / nxui diag / IP) | yes — p10 |
| `/tmp/nxui.log` | panel `READY / ACTION / BACKEND ok=…` lines | no |
| `/tmp/db.log` | dropbear (did ssh start, and why not) | no |
| `/tmp/nxwa-lut-video/watch.log` | video LUT watcher | no |

A camera that **powers itself off** is the one case that must be captured in advance: the last
`pwrlog.txt` line (`up=… pwr=… ssh=… ui=… lut=…`) plus `pwrlog.sh dump 60` is the whole story.
Everything under `/tmp` is gone at that moment.

### Symptom → where to look

| Symptom | Look at |
|---|---|
| EV+AEL shows the legacy NX-KS popup | `nxui.sh diag`; `available: no` means binary missing / NX1 / disabled |
| Panel taps do nothing, stuck on "sending" | tail of `/tmp/nxui.log` (`BACKEND ok=0`) + the matching `lut.sh` state log |
| A new LUT changes nothing | `lut.sh status`; then half-press once (p7's own load event) |
| Colours look off — is it the LUT? | compare before/after `lut.sh off`; `lut.sh stock` exports the factory table |
| The camera powers itself off | `/mnt/mmc/nx-ks/pwrlog.txt` → `sh /opt/usr/nx-ks/pwrlog.sh dump 60` |
| SSH unreachable | menu `IP: … [SSH on]`; `sh /opt/usr/nx-ks/ssh_hint.sh --start`; `/tmp/db.log` |

## Install

1. Put `info.tg`, `nx_cs.adj`, `install.sh` and `scripts/` at the **root of the SD card** (or unzip `NX-WA-<version>.zip` there).
2. Insert the card → it installs automatically and shows "install complete".
3. **Turn Bluetooth on once by hand** — the mod's boot hook is initialised by it.

- Firmware: NX500 **1.12** / NX1 **1.41**; anything else is refused.
- Two packages: `NX-WA-<ver>.zip` (Chinese) and `NX-WA-<ver>-EN.zip` (English menus, English NXUI panel, English README). Identical features. Installing the other package swaps the language back; `nxui/lang` is overwritten by the package.
- Inserting the card again = **incremental sync** (overwrite only, never delete, never auto-uninstall); uninstall from the camera menu (`Uninstall`).
- Install / sync / WiFi push / rollback: [SYNC.md](SYNC.md) (bilingual).

## Remote access (SSH)

There is exactly one remote path: **dropbear ssh on port 22** (shipped, started by `init.sh`).
telnet and FTP were retired on 2026-11-02; the `telnetd` binary is **not in the release zip**
(2016 Samsung original, intentionally untracked).

| Method | Command | Requirement |
| --- | --- | --- |
| Blank password | `ssh root@<camera-ip>` | just press Enter (dropbear `-B`); some clients refuse blank passwords |
| Public key (recommended) | append your `id_ed25519.pub` to `/opt/usr/nx-ks/dropbear/authorized_keys`, then `sh /opt/usr/nx-ks/ssh_hint.sh --start` | log in once with the blank password first |
| Menu | camera menu → `IP: 192.168.x.x [SSH on]` | shows state; pressing it pops the login string and starts ssh if it is down |

The host key `dropbear_ed25519_host_key` is generated on first boot (kept on p14, survives reflashing).
For troubleshooting see `/opt/usr/nx-ks/onboard.log` and `/tmp/db.log`.

---

## Camera menu

Six entries on the main page plus one status row. ★ = added by this project,
"upstream" = inherited from NX-KS 2.88 with unchanged behaviour.

### Main page

| Item | Function |
|---|---|
| Time-Lapse → | see "Time-lapse" |
| Custom Func. → | see "Custom functions" |
| Focus + Profiles → | see "Focus" |
| Settings → | see "Settings" |
| Hibernate | sleep immediately (`hibernate.sh`, upstream) |
| Remote Ctr ☑ | web gallery / remote control (nx-rc.sh, upstream) |
| `IP: x.x.x.x [SSH on]` | ★ SSH state; tap to pop the login string, starts dropbear if it is down |

### Time-lapse

| Item | Function |
|---|---|
| Wake Lapse | wake at a set time and start shooting (`wakelapse.sh`, upstream) |
| Ramping → | exposure ramping inside a time-lapse: total duration / interval / start & end exposure / ramp start & length / start delay; `开始` runs `ramping.sh` (upstream) |
| Mod Lapse | `mod_lapse` (upstream binary) |
| Coming soon | placeholder |

### Custom functions

| Item | Function |
|---|---|
| Remote Save ☑ | remote-save toggle (`rem.sh`, config in `remote.cfg`, upstream) |
| Video Bitrate → | five bitrate slots (Pro4K / ProHD / Hq4K / HqHD / HqVGA) plus the current value, template `gui_br.tp` (upstream) |
| ZoomZoom | set a delay → take a shot → zoom back to wide: a zoom-burst tool (`zoomzoom.sh`, upstream) |
| Resolutions → | see "Resolution mapping" |
| Batch Rec | continuous recording in minute-sized batches, optionally with a hidden UI (`brec.sh`, upstream) |
| HDR | five shutter steps (65 / 92 / 119 / 146 / 200) in M mode, five frames, **no in-camera merge** (`1HDR.sh`, upstream) |
| LUT Filter | ★ opens the NXUI LUT panel (same as EV+WiFi) |
| TC Curve → | ★ video tone curve: Stock / Log / Flat / High Contrast |
| `Mod v2.88` | version popup (`ver.sh`) |
| Camcorder ☑ | shutter button becomes a record button (`camcorder_mode.sh` → `shutter_to_rec`, upstream) |

### Focus + Profiles

| Item | Function |
|---|---|
| Focus Stacking | automatic focus stepping by count / interval (`fstack.sh`, config on SD: `/mnt/mmc/scripts/focus_stack.cfg`, upstream) |
| Focus Buttons | long-press to store a position, tap to recall (`/mnt/mmc/scripts/af_positions.txt`, upstream) |
| Profiles → | save / load `EV+UP`, `EV+DN`, full backup (`save_UP.sh` / `EV_UP.sh` / `FullSave.sh` …, upstream) |
| Focus-Pull Speed | pull speed 1–255 (writes the `fps` environment variable, `fpspeed.sh`, upstream) |
| My Checkbox / My Button | template placeholders for your own scripts (`cCheckbox.sh` / `cButton.sh`, upstream) |

### Settings

| Item | Function |
|---|---|
| Silent Shutter ☑ | electronic shutter `ADJUSTSHUTTERTYPE 0x750001` (`rolling_shutter.sh`, upstream) |
| OFF Menu Button ☑ | disables the MENU key's default OSD behaviour (`z_button.sh`, upstream) |
| No Rec Limit ☑ | removes the recording time limit (`prefman 0xc2d9=1`, upstream) |
| Refocus on Boot ☑ | refocus to the position stored before hibernation (`refocus.sh`, upstream) |
| No Lens Release ☑ | release the shutter without a lens (`prefman 0xc2dd=1`, upstream) |
| Enable Bluetooth ☑ | restarts the Bluetooth service (`bt.sh`, upstream) |
| Overlay ☑ | starts the `onscreen_ov` overlay (upstream) |
| Uninstall v2.88 | uninstalls the mod (`uninstall.sh`) |

### Resolution mapping

Maps a capture mode (UHD / DC / VGA) onto a different resolution. The eight switches are mutually
exclusive — enable **one per mode**:

| Mode | Can be mapped to |
|---|---|
| UHD | 2.5K full width (2560×1440) / DC 4K (4096×2160) / FHD (1920×1080) |
| DC | 2.5K / UHD / FHD |
| VGA | UHD / DC 4K |

The switches are stored in the camera preferences; verify the actual output in the viewfinder.
Upstream NX-KS capability.

---

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
- **The full 7-dimension push needs the A2 firmware** (`patch-a2/`, see [A2 p7 patch](#a2-p7-patch-optional)). On stock firmware R/G/B/HUE need one confirmation in **Picture Wizard → Custom 1** — a structural limit of p7's normaliser domain (`0x100–0x12e`), not a script bug.
- Honest limits: WB is not part of a recipe (use the camera's white balance); a recipe is a global colour vector, it cannot do highlight roll-off or zone-based exposure; NX1 is not enabled (the prefman offsets were only proven on NX500 1.12).
- One criterion only: `sh /opt/usr/nx-ks/filmlab.sh check` reads the seven values the ISP is actually using (read-only, zero risk). **"The value changed" ≠ "the value is consumed"**.
- There is also `scripts/nx-rc/MOBILE_MOBILE.sh` (double-tap WiFi = rotate to the next recipe with no UI) — not part of the install chain; copy it to `/opt/usr/nx-ks/` if you want it.

## 3D LUT

| Item | Status |
| --- | --- |
| Table format | `4913×4B {Cr,Cb,Y,pad}`, index `((Y*17+Cb)*17+Cr)*4`, slot 19,712 B, stride `0x4D00` (closed on-device 10-19; the older RGB naming is retired) |
| Retarget | Write 19,712 B into the work slot (A18 `0x81119F00`) + point **all four** registry tables at it + **auto-load after frame end** (`nx_lutload.arm`, no half-press) |
| Registry tables | `View4` (4 entries, colour space × screen colour) + `Still6` (6) + `BV12` (12) — **none may be skipped**, or you get "viewfinder filtered, photo not" |
| Import | `.cube → 19,712 B slot table` via on-camera `cube2lut.arm`, or host-side `test_server/isp/nx3dlut.py` |
| Generation basis | Built for the **measured camera input domain**: response slope `log2(code)/EV = 0.809`, not sRGB's 0.45 (a 1.8× gap). Tables built on the sRGB assumption get crushed twice in the shadows. Of the 86 frozen tables, 47 carry over from the previous release (34 of them regenerated against the real response: 25 G'MIC + 9 recipe tables) and 39 come from the 2026-11-08 community batch |
| Live view / stills | Live view reads only `View4`; stills have **two mutually exclusive branches** (screen colour on → `BV12`, off → `Still6`) and both must be retargeted |
| Video | After `apply`, just press record — **the very first frame already carries the table** (p7's 23-entry slot pointer table is redirected to A18); `off` stops the watcher. Long takes and other frame rates are untested |
| Panel close | **Does not restore**: `Save & close` / half-press only close the panel, the table stays live. To go back, use `Factory` in the panel or `lut.sh off` |
| Limits | Pure memory operations — **power cycle restores stock** (boot-persistent needs an image patch). Colour is trustworthy in sRGB; AdobeRGB only guarantees "it applies" |
| Load sequence | ⛔ Writing `+0x00C` yourself requires all 8 steps: `OnOff` → clear/set Acc → address → Cfg channel bits → bit8 pulse → **reset Acc at the end**, plus waiting for the preview frame to end. Address + pulse alone corrupts the picture — that is the real reason behind the 10-08 "no-go" note |

### Library and blending

| Capability | Command |
| --- | --- |
| Library | `lut.sh list [--fav]` / `fav` / `move up\|down\|top` / `del` / `index` / `stock` |
| Cross-fade | `lut.sh mix <A> <B> <0-100>` |
| Strength of one look | `lut.sh strength <name> <0-100>` (0-end = stock A17; run `lut.sh stock` once first) |
| **Two looks, two strengths** | `lut.sh blend <A> <r 0-100> <B> <s 0-100>` — `r` = A/B ratio, `s` = total strength |
| Video LUT | No separate switch: starts with a successful `apply`, stops on `off`. Diagnose with `lut.sh video on\|off\|status` |

Order and favourites live in `lut/state/order` on the card (one name per line, `*` = favourite).
Removal is a **move to `looks/_trash/`**, never an `rm` — deleting a duplicated name on exFAT
releases the cluster chain and corrupts the siblings.

#### Frozen library and cleaning out old tables

The 86 bundled tables are the **frozen set** (fixed on 2026-11-11 against what was actually kept on the camera); the roster is `looks/MANIFEST.txt` (md5 + size).
The 80 names from earlier batches are listed in `looks/obsolete.txt` — unzipping only overwrites,
never deletes, so without this they stay on the card and the panel mixes old and new.

```sh
sh /opt/usr/nx-ks/lut.sh verify          # against the roster: MISSING / CHANGED / EXTRA
sh /opt/usr/nx-ks/lut.sh prune --dry-run # see what would move
sh /opt/usr/nx-ks/lut.sh prune           # move old batches to looks/_trash/ (move, not delete)
```

`EXTRA` is not necessarily an error — your own looks count as extra. `prune` only touches names
listed in `obsolete.txt`; anything else is left alone, and mistakes are recoverable from
`looks/_trash/`. After changing the library (add / remove / edit any table) you must re-run
`python tools/lutgen/make_manifest.py` and commit it, otherwise `verify` reports `CHANGED` on the
next machine — deliberately: a library change has to be an explicit act.

Blending is **normalised weighting**: `r = B/(A+B)` picks the mix, `s = min(A+B, 100)` the strength,
`T = stock + s·(mix(A,B,r) − stock)`. Both at 100% therefore lands on the midpoint instead of
clipping. See [`docs/current/DUAL_STRENGTH_2026-11-02.md`](docs/current/DUAL_STRENGTH_2026-11-02.md).

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
| Entry | Menu `Custom Func. → TC Curve` (Stock / Log / Flat / High Contrast), or `tc.sh set log\|flat\|hc` |
| Reach | Enters the HEVC stream: same-scene A/B clips, full-frame Y mean **63.26 → 98.83**, mapping 4→17 / 52→102 / 180→186 |
| Rollback | `tc.sh off` restores stock; a reboot does it too (runtime memory only, no firmware write) |

```sh
sh /opt/usr/nx-ks/tc.sh status             # stock?, Y[9], descriptor
sh /opt/usr/nx-ks/tc.sh list               # /mnt/mmc/tc/*.tcy
sh /opt/usr/nx-ks/tc.sh set log|flat|hc    # or any .tcy
sh /opt/usr/nx-ks/tc.sh off
```

Honest limits:

- **A programmable curve is not extra dynamic range.** The container is still 8-bit 4:2:0 with no 10-bit ground; the Y-mean lift is curve shape, not exposure drift, and not a net DR gain.
- The anchor is **mid-grey** (camera 128 ↔ sRGB 128); a white-point anchor shifts everything by ~35 codes and needs an 18% grey card to settle.
- **TC moves the 3D LUT's input domain** — changing both at once requires recalibration.
- Writes are allowed only in idle preview (directory lock, recording detection, item-by-item readback, automatic restore on any failure); **switching while recording, and whether the photo path is affected, are untested**.

Details: [`docs/current/TC_CURVE_ONDEVICE_2026-11-08.md`](docs/current/TC_CURVE_ONDEVICE_2026-11-08.md) · restoration workflow: [`docs/current/TC_RESTORATION_WORKFLOW_2026-11-08.md`](docs/current/TC_RESTORATION_WORKFLOW_2026-11-08.md)

## A2 p7 patch (optional)

The firmware prerequisite for the "all seven PW dimensions in one push". Not flashing it breaks
nothing — R/G/B/HUE simply need one confirmation in Picture Wizard.

| Item | Value |
|---|---|
| Image | `patch-a2/p7_a2.bin` (shipped, 12,075,648 B, md5 `712c6fd0a49371ec05ce94c367b0d5c7`) |
| Target | `/dev/mmcblk0p7` (~30 MB, **a wrong partition is unrecoverable**) |
| Channel A | unzip → write p7 over ssh with `dd` (~1 s) |
| Channel B | Release asset `slp_a2_p7_v117.bin` (352 MB) renamed `nx500.bin`, flashed through the official updater |
| Activation | **normal power off → power on**; ⛔ never `systemctl restart di-camera-app` |
| Rollback | write the `p7_backup_*.bin` back, or reflash official 1.12 |

Full procedure (ssh wording, backup, read-back criteria, split comparison, rollback):
[`fw/v1.12/a2/README-A2_EN.md`](fw/v1.12/a2/README-A2_EN.md) ([中文](fw/v1.12/a2/README-A2.md)).
An official firmware upgrade rewrites p7 ⇒ **re-flash A2 afterwards**.

## Layout

| Path | What |
| --- | --- |
| `install.sh` `info.tg` `nx_cs.adj` | SD-card trigger trio (install / incremental sync) |
| `scripts/` | All modules → synced to the camera's `/opt/usr/nx-ks/` |
| `scripts/filmlab.sh` · `scripts/filmlab/recipes.json` | FilmLab engine / authoritative recipe library (79) |
| `scripts/EV_AEL.sh` · `scripts/EV_MOBILE.sh` · `scripts/EV_EV.sh` | The three key-combo entry points (strip / LUT panel / main menu) |
| `scripts/nxui.sh` · `scripts/nxui/` | NXUI launcher + panel binaries (`nxui.arm` CN / `nxui_en.arm` EN) + fonts + `lang` |
| `scripts/lut.sh` · `scripts/lut/` | 3D LUT entry + toolchain (`cube2lut` / `nx_slotwrite` / `nx_regtabwrite` / `nx_regtabdump` / `nx_lutload` / `nx_lutptr` / `lutmix`) |
| `scripts/lut_video.sh` | video LUT watcher (follows `apply`/`off`, state in `/tmp`) |
| `scripts/tc.sh` · `scripts/tc/*.tcy` | TC curve writer and curve library |
| `scripts/ssh_hint.sh` · `scripts/dropbear/` | SSH state hint + dropbear itself |
| `scripts/pwrlog.sh` | power-off forensics sampler (one line per 30 s to SD) |
| `scripts/gui_*.NX500` | native menu pages (`i18n/en/scripts/` is the English overlay) |
| `tools/tcgen/` · `tools/lutgen/` | host tools: curve generation / read-only chain verification / LUT generation and audit |
| `test_server/` | host-side dev environment (API mocks, toolchain, panel sources and `make_en.py`) |
| `uninstall_pkg/` | camera-menu uninstall entry |

## Docs

- [`docs/README.md`](docs/README.md) — **documentation index** (`current` / `archive` / `evidence`)
- [`docs/current/HANDOVER_2026-10-16.md`](docs/current/HANDOVER_2026-10-16.md) — entry point: conventions, dead ends, gates, order of work
- [`docs/current/NXUI_ENABLE_GATE_2026-11-10.md`](docs/current/NXUI_ENABLE_GATE_2026-11-10.md) — why the UI "did not start" and what `diag` checks
- [`docs/current/TC_CURVE_ONDEVICE_2026-11-08.md`](docs/current/TC_CURVE_ONDEVICE_2026-11-08.md) — TC curve: address chain, write protocol, on-device A/B
- [`docs/current/VIDEO_LUT_FIRSTFRAME_2026-11-07.md`](docs/current/VIDEO_LUT_FIRSTFRAME_2026-11-07.md) — video first frame carries the LUT
- [`fw/v1.12/a2/README-A2_EN.md`](fw/v1.12/a2/README-A2_EN.md) — A2 p7 flashing guide

> Conclusions in old documents (e.g. "View/Still cannot be separated", "user space cannot write
> the LUT") have been overturned; see [`ERROR_CORRECTIONS_2026-10-07.md`](docs/current/ERROR_CORRECTIONS_2026-10-07.md).

## Boundaries

Being accurate matters more than looking complete. Every row below maps to an on-device or static
verification, none is "should work".

| Dimension | ✅ Works | ❌ Not / unverified |
|---|---|---|
| Platform | NX500 firmware **1.12** (all features verified on device) | NX1 1.41 installs, but LUT / FilmLab / NXUI are not enabled there; other firmware versions are refused |
| Colour | sRGB output: viewfinder and JPEG colours are trustworthy (basis of the 86 bundled tables, 34 of them generated against the measured input domain) | **AdobeRGB applies but is not calibrated**; in-camera smart filters (enum 14–18) take another 24-step dynamic path and are not covered |
| Carriers | **JPEG stills + viewfinder + video (first frame carries the table)** | **RAW (`.SRW`) is not promised to be baked**; the ground is 8-bit 4:2:0 (10-bit unreachable, the built-in gamma interface has no consumer); long takes and other frame rates untested |
| Video curve | **Four TC presets, effective within 50 ms, reaches the HEVC stream** | Re-allocates 256 code values only, no extra dynamic range; absolute anchor needs a grey card; switching while recording, stacking with 3D LUT, and the photo path are unverified |
| Activation | LUT auto-loads after a write (waits for frame end, no keypress); TC takes effect in <50 ms | **Not boot-persistent** — power cycle restores stock; persistence needs an image patch |
| Triggering | `nx_lutload.arm once` replays p7's own load sequence, aligned on the `CORE RSZ_OUT1_EOF` frame event | With the screen off or `di-camera-app` gone the ISP does not run, so the DMA-done interrupt never arrives — fall back to "half-press once" |
| Shape | No flashing, no partition rewrite, fully reversible (A2 is the only optional p7 write) | Without touching the firmware partition, a reboot restores stock |

> It is **not** a colour-management system (no input/output profile conversion), **not** a
> WYSIWYG promise (viewfinder and still pipelines differ), **not** a crack (no region unlock, no
> recording limit change). It edits two ISP tables: the 3D look-up table and the video tone curve.

## Hard limits (p7 / firmware, not script bugs)

- **All-seven-dimension PW push needs the A2 firmware**; on stock firmware values outside the normaliser domain are rejected.
- **p7 has no UI** (zero hits for Font/DrawText/Dialog/Widget) ⇒ the interface can only live on the Linux side.
- **Combos of three or more keys are unavailable** (the kernel consumes keys first) ⇒ only "hold EV + one key" works; long-press is detected by NXUI from press/release timing, not by hardware.
- **TC only changes shape, not bit depth**: remapping 256 code values in 8-bit 4:2:0 creates no new dynamic range; `MOVIE_GAMMA_CONTROL` / `IQ[180]` has no consumer and 10-bit encoding does not exist in this firmware.
- Factory LUT tables are **all stylistic** — "writing identity gives neutral" is not a valid test.

> The film-simulation engine and `.cube` assets live in [nx500-filmsim](https://github.com/WApaperplane/nx500-filmsim) (public).
