# NX-WA 2.88.0-nxwa.15.3 — bilingual release (CN / EN packages)

Released: 2026-11-10
Kind: distribution change. The feature set is the same as 15.2 (NXUI on by default, remote
access fix, `pwrlog` power-off forensics). What is new is how it ships: an English package and
bilingual release notes.

## In one line

From this version every release carries **two zips**: `NX-WA-<ver>.zip` (Chinese) and
`NX-WA-<ver>-EN.zip` (English). Release notes are published in Chinese and English together.

## 1. What is translated in the EN package

| Layer | Content | Notes |
|---|---|---|
| NXUI panel | 113 strings (titles, buttons, status line, LUT library management, mix/edit dialogs) | rebuilt `nxui_en.arm`, zero logic change |
| Camera menus | 9 `gui_*.NX500` pages (main / time-lapse / functions / focus / settings / resolutions / TC / profiles / template) | wording follows the long-standing NX1 English menus |
| Docs | `README.md` becomes English; the Chinese one stays as `README.zh-CN.md` | `README_EN.md` is not duplicated |
| Generated text | SSH state and popup (`ssh_hint.sh`) | driven by `scripts/nxui/lang` = `en` |

**Not translated** (known boundary, not a bug):

- the legacy `mod_gui` recipe pages (`gui_filmlab*.NX500`) — only reachable after `nxui.sh disable`;
- shell console output and logs (`lut.sh` / `filmlab.sh` stdout);
- `docs/` and the reverse-engineering notes (never shipped in the zip anyway).

## 2. How the panel is translated (verifiable)

No `#ifdef` sprinkled through 700 lines — the English source is **generated**:

```
test_server/nxui/i18n/en.json   113 Chinese → English entries
test_server/nxui/make_en.py     replaces string literals only; comments untouched
test_server/nxui/build.sh en    → out/nxui_en.c → scripts/nxui/nxui_en.arm
```

The generator asserts that **no string literal still contains CJK** (comments may), and fails
with a list of missing entries.

## 3. Differences between the two packages

| File | Chinese package | English package |
|---|---|---|
| `scripts/nxui/nxui.arm` | 479,056 B · `53cea992` | 479,060 B · `99c808ed` (EN build) |
| `scripts/nxui/lang` | `zh` | `en` |
| `scripts/gui_*.NX500` | Chinese | English (9 files overlaid) |
| `README.md` | Chinese | English (Chinese kept as `README.zh-CN.md`) |
| everything else | identical | identical |

## 4. Packages and checksums

| Package | Size | MD5 | Entries |
|---|---|---|---|
| `NX-WA-2.88.0-nxwa.15.3.zip` | 10,154,115 B | `62e94b8d1e99b01c3e6de638829055cc` | 373 |
| `NX-WA-2.88.0-nxwa.15.3-EN.zip` | 10,153,320 B | `1a2cf33e3b9e14bc7f2b320f51a33587` | 373 |

The packages are mutually exclusive: installing the EN package swaps menus and panel to
English, the CN package swaps them back. `nxui/lang` is overwritten by the package, so no stale
language remains.

## 5. Upgrade and acceptance

1. Unzip either package to the SD-card root → insert the card → incremental sync → reboot.
2. EN package: **EV + AEL** should show the English film strip (`FILMLAB / PREVIEW`,
   `Save & close`); **MENU** should show `NX-KS / MENU` with `Time-Lapse / Custom Func. /
   Settings …`.
3. CN package: identical to 15.2.

## 6. Boundaries (honest notes)

- The English panel is a **string-level substitution** from the same source and build as the
  Chinese one, but the **button widths have not been visually confirmed on a camera yet**
  (the camera was asleep when this build was made). If a label is clipped, the next version
  only needs a copy or width tweak in `en.json` — no logic change.
- The `mod_gui` 2-column label limit (about 6 full-width characters) does not apply to English;
  the English menus reuse wording already proven on NX1 for years.
