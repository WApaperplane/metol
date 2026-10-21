# Metol (formerly NX-WA)

An enhancement mod for the **Samsung NX500 / NX1** (Tizen / DRIMe5), built on the community
[`ottokiksmaler/nx500_nx1_modding`](https://github.com/ottokiksmaler/nx500_nx1_modding) upstream.

**Repository** [WApaperplane/metol](https://github.com/WApaperplane/metol) (a fork; default branch `nxwa`) ·
**License** AGPL-3.0 (lineage in [ATTRIBUTION.md](ATTRIBUTION.md)) ·
**Download** [Releases](https://github.com/WApaperplane/metol/releases)

> 中文版见 [README.md](README.md)

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
| **EV + AEL** | **Filter strip** (NXUI, 720×208) | 68 recipes, horizontal scroll plus a draggable/tap-to-jump scrollbar; tap = **instant preview** (~1.3 s, always rendered into the Custom 1 canvas); `Save & close` commits and returns the field you started from; press again or **half-press** to close. **NX500 only** — NX1 falls back to the community script |
| **EV + WiFi** | **LUT panel** | Opens NXUI's LUT mode (`nxui.sh lut`); **closing the panel restores nothing** — use the panel's `Restore` button to go back to the factory tables. If NXUI is not enabled you just get a one-line popup |
| **Double-tap EV** | Main menu (NXUI, 720×336) | Paginated screen, replaces the old mod_gui menu |
| **Half-press** | Closes the current panel | For the LUT panel it closes the panel and **keeps the current table**, while letting p7 reload it — shoot with the LUT still applied |

> **EV + WiFi is a combo**: hold EV, then press WiFi. A single WiFi press stays the camera's native behaviour (WiFi on/off); they do not conflict.

The camera menu also has `IP: x.x.x.x [Telnet关]` (tap to toggle 23/21), `远程控制` (web gallery on/off) and `LUT 滤镜` (same UI as EV+WiFi).

## Features

| Capability | In one line |
| --- | --- |
| Film recipes | 68 (negative / slide / B&W / cinema / stylised); all seven PW dimensions pushed into the ISP at once |
| 3D LUT | `.cube` converted on-camera in one command; **edit a 4-byte registry entry + write 19,712 B into a spare slot + half-press** to retarget; live view and stills are independent chains |
| NXUI | Nuklear (MIT) on the camera's own X11/Xft — **no EFL**, no viewfinder capture or blit |
| Web gallery | Collapsed directories + live `dirlist` (new photos appear instantly) + thumbnail pre-warm + over-the-air push |
| Original NX-KS modules | Video bitrate, HDR, batch recording, zoom, resolution tweaks, shooting-parameter API … |

## FilmLab recipes

| Family | Examples (68 total: 60 colour + 8 B&W) |
| --- | --- |
| Colour negative | Portra 400/800, Gold 200, Ektar 100, Superia 400, ProImage 100, Vista 200 … |
| Slide | Velvia 50/100, Provia 100F/400X, Ektachrome E100, Kodachrome 25/200 … |
| B&W | TriX 400, HP5 Plus, Delta 3200, T-MAX 100/400, Acros 100, XP2 Super … |
| Cinema | CineStill 800T/50D, Vision3 250D/500T, Double-X 5222, Eterna 500T |
| Stylised | Teal-orange / warm-faded / cold / bleached / high-key / low-key / sepia / bleach-bypass / blue hour / X-Pro |

- **Recipes need no code change**: edit `/mnt/mmc/filmlab/recipes.json` → copy back to SD → reopen the menu (it rebuilds itself). The authoritative source in-repo is `scripts/filmlab/recipes.json`; host-side CLI: `test_server/filmlab/flab.py add|edit|rm|lint|deploy`.
- A recipe is a Picture Wizard 7-value vector (R/G/B gain + HUE/SAT/SHARP/CONTRAST), always written into the **Custom 1** slot.
- **The full 7-dimension push needs the A2 firmware** (`patch-a2/`, shipped with a flashing guide and md5). On stock firmware R/G/B/HUE need one confirmation in **Picture Wizard → Custom 1** — a structural limit of p7's normaliser domain (`0x100–0x12e`), not a script bug.
- Honest limits: WB is not part of a recipe (use the camera's white balance); a recipe is a global colour vector, it cannot do highlight roll-off or zone-based exposure; NX1 is not enabled (the prefman offsets were only proven on NX500 1.12).
- One criterion only: `sh /opt/usr/nx-ks/filmlab.sh check` reads the seven values the ISP is actually using (read-only, zero risk). **"The value changed" ≠ "the value is consumed"**.
- There is also `scripts/nx-rc/MOBILE_MOBILE.sh` (double-tap WiFi = rotate to the next recipe with no UI) — it is not part of the install chain; copy it to `/opt/usr/nx-ks/` if you want it.

## 3D LUT

| Item | Status |
| --- | --- |
| Table format | `4913×4B {R,G,B,pad}`, index `((B*17+G)*17+R)*4`, slot 19,712 B, stride `0x4D00` |
| Retarget | Write 19,712 B into the work slot (A18 `0x81119F00`) + point **all four** registry tables at it + **half-press once** |
| Registry tables | `View4` (4 entries, colour space × screen colour) + `Still6` (6) + `BV12` (12) — **none may be skipped**, or you get "viewfinder filtered, photo not" |
| Import | `.cube → 19,712 B slot table` via on-camera `cube2lut.arm`, or host-side `test_server/isp/nx3dlut.py` |
| Live view / stills | Live view reads only `View4`; stills have **two mutually exclusive branches** (screen colour on → `BV12`, off → `Still6`) and both must be retargeted |
| Limits | Pure memory operations — **power cycle restores stock** (boot-persistent needs an image patch). Colour is trustworthy in sRGB; AdobeRGB only guarantees "it applies" |
| No-go | ⛔ Writing `+0x00C` yourself and pulsing the config register makes the ISP read out-of-sequence addresses ⇒ **severe colour corruption**. The only safe reload is **half-press** |

```sh
sh /opt/usr/nx-ks/lut.sh list | begin | apply <name> | off | status   # looks live in /mnt/mmc/looks/
```

Details: [`docs/current/LUT_RETARGET_LIVE_2026-10-18.md`](docs/current/LUT_RETARGET_LIVE_2026-10-18.md) · panel design: [`docs/current/LUT_UI_2026-10-18.md`](docs/current/LUT_UI_2026-10-18.md)

## Layout

| Path | What |
| --- | --- |
| `install.sh` `info.tg` `nx_cs.adj` | SD-card trigger trio (install / incremental sync) |
| `scripts/` | All modules → synced to the camera's `/opt/usr/nx-ks/` |
| `scripts/filmlab.sh` · `scripts/filmlab/recipes.json` | FilmLab engine / authoritative recipe library (68) |
| `scripts/EV_AEL.sh` · `scripts/EV_MOBILE.sh` | The two key-combo entry points (`EV+AEL` strip / `EV+WiFi` LUT panel) |
| `scripts/lut.sh` · `scripts/lut/` | 3D LUT entry + toolset (`cube2lut` / `nx_slotwrite` / `nx_regtabwrite` / `nx_regtabdump`) |
| `scripts/nx-rc/` | Web remote: `web_root/` `thumb/` `capdtm/` `push/` |
| `test_server/` | Host-side development environment (simulated API, toolchain, gates) |
| `uninstall_pkg/` | Camera-menu uninstall entry |

## Docs

- [`docs/README.md`](docs/README.md) — **documentation index** (`current` / `archive` / `evidence`)
- [`docs/current/HANDOVER_2026-10-16.md`](docs/current/HANDOVER_2026-10-16.md) — master entry: conventions, dead ends, gates, order of execution
- [`docs/current/ONDEVICE_SOP_2026-10-16.md`](docs/current/ONDEVICE_SOP_2026-10-16.md) — on-camera day SOP (setup / criteria / rollback)
- [`docs/current/NXUI_NUKLEAR_2026-10-17.md`](docs/current/NXUI_NUKLEAR_2026-10-17.md) — NXUI install & verification
- [`docs/current/RE_PROGRESS_2026-10-08.md`](docs/current/RE_PROGRESS_2026-10-08.md) — reverse-engineering overview (with the dead-end list)

> Old conclusions in historical docs (e.g. "View/Still cannot be separated", "user space cannot write LUT data") have been overturned — see
> [`ERROR_CORRECTIONS_2026-10-07.md`](docs/current/ERROR_CORRECTIONS_2026-10-07.md).

## Boundaries

Stated plainly — every row below maps to an on-camera or static verification, not to "should work".

| Dimension | ✅ Works | ❌ Does not / unverified |
|---|---|---|
| Platform | NX500 firmware **1.12** (everything verified on device) | NX1 1.41 installs, but LUT / FilmLab are **not verified on NX1**; other firmware versions are rejected by the installer |
| Colour | Colour is trustworthy in **sRGB** for both live view and JPEG (baseline of the 45 bundled tables) | **AdobeRGB applies but is not colour-calibrated** (tables are built in sRGB coordinates); the camera's Smart Filter enum 14–18 takes a separate 24-slot dynamic path that this mod does not cover |
| Carrier | **JPEG stills + viewfinder** | **RAW (`.SRW`) is not promised to be baked**; video is out of scope |
| Taking effect | Memory write takes effect immediately (half-press once to load) | **No boot persistence** — a power cycle restores stock; that needs a firmware image patch |
| Trigger | **Half-press** is the only reliable reload | No software trigger found for making p7 re-read the table (`st cap iq af afsta/afsto` is a no-op) |
| Shape | No reflash, no partition writes, fully reversible | No firmware-partition change means a reboot restores stock (LUT writes are RAM-only) |

> It is **not** a colour-management system (no input/output profile conversion), **not** a WYSIWYG promise
> (live view and stills run different pipelines), and **not** a jailbreak (no region unlock, no recording-limit bypass).
> What it edits is one 3D lookup table inside the ISP.

## Known ceilings (p7 / firmware level, not script bugs)

- **The full 7-dimension one-tap needs the A2 firmware**; on stock firmware values outside the normaliser domain are rejected.
- **p7 has no UI** (Font/DrawText/Dialog/Widget all zero hits) ⇒ the UI can only live on the Linux side.
- **Long-press / 3+ key combos are not available** (the kernel consumes keys first) ⇒ only "hold EV + one key" style two-key combos work.
- Factory LUT tables are **all style tables** — "write identity to get neutral" is not a valid criterion.

> The film-simulation engine and `.cube` assets live in a separate repo:
> [nx500-filmsim](https://github.com/WApaperplane/nx500-filmsim) (public).
