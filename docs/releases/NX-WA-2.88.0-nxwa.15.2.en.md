# NX-WA 2.88.0-nxwa.15.2 — NXUI enabled by default (hotfix)

Released: 2026-11-10
Kind: **hotfix**. Fixes a problem that has shipped since v2: after installing, the new UI
could not be opened at all — EV+AEL / MENU fell back to the legacy NX-KS popup. Feature set is
identical to 15.1 (which brought the remote-access fix and the `pwrlog` power-off forensics).

## In one line

`nxui.sh available` required a marker file that **no release ever shipped**. It is now
**enabled by default**; only an explicit `nxui.sh disable` returns to the legacy popup.

## 1. Root cause

| # | Fact | Consequence |
|---|---|---|
| 1 | The gate was `[ -x nxui.arm ] && [ -f nxui/enabled ] && is_nx500` | no `enabled` file ⇒ "not available" |
| 2 | Only `nxui.sh enable` creates that file, and that command exists only in the developer SOP (`test_server/nxui/README.md`, the 10-17 doc) | ordinary users never run it |
| 3 | `git log --all -- scripts/nxui/enabled` is empty; every zip from v2 to 15.1 was checked — **not one contains it** | every fresh install is affected |
| 4 | All five entry points ask `available` first: `EV_AEL.sh` / `EV_EV.sh` / `EV_MOBILE.sh` / `loadgui.sh` / `menu.sh` | all fall through to `mod_gui` |

So the symptom is not a crash or a black screen: the launcher **correctly took the fallback path**,
which looks exactly like "this release has no new UI". The maintainer's own camera worked because
`enable` was run by hand once on 2026-10-17 and the marker survived on p10.

## 2. Fix: invert the polarity

```sh
# old
available) [ -x "$BIN" ] && [ -f "$D/nxui/enabled" ] && is_nx500 ;;
# new
available) [ -x "$BIN" ] && [ ! -f "$D/nxui/disabled" ] && is_nx500 ;;
disable)   : > "$D/nxui/disabled"; rm -f "$D/nxui/enabled" ;;
enable)    rm -f "$D/nxui/disabled" "$D/nxui/enabled" ;;
```

Why not the smaller fix "create `enabled` at install time":

- `disable` would be one-shot — the next card insert (incremental sync) would recreate it;
- the semantics would still be "you need a file that does not exist in the package";
- after the inversion the default state needs **no file at all**, so a missing file can never
  mean "disabled" again.

A legacy `enabled` file on old cameras is ignored (no longer required) and removed on `disable`.
NX1 remains unsupported by design (`is_nx500` gate; LUT / FilmLab are only validated on NX500).

## 3. New diagnostic verb

```sh
sh /opt/usr/nx-ks/nxui.sh diag
# bin      : OK
# model    : NX500
# disabled : no
# enabled  : no
# available: yes
```

`onboard.sh` writes the same block into `/opt/usr/nx-ks/onboard.log`, so it is available
right after installation without a network connection.

## 4. Upgrade and acceptance

1. Unzip to the SD-card root → insert the card (incremental sync) → the camera reboots.
2. Press **EV + AEL**: you should get the 720×208 NXUI film strip (dark, horizontally
   scrollable) instead of the old light EFL popup.
3. Press **MENU**: you should get the NXUI menu page (title `NX-KS / 菜单`).
4. To go back to the old popup: `sh /opt/usr/nx-ks/nxui.sh disable`; to restore: `… enable`.

## 5. Verification

- `test_server/nxui/test_enable_gate.py`, 6 cases: fresh install available / disable works /
  enable restores / legacy flag ignored / missing binary unavailable / diag output.
- Together with the existing `test_launcher.py` and `test_lut_launcher.py`: **8 tests OK**
  (WSL, unittest).
- `test_lut_lib.sh` 57 PASS unaffected (lut.sh untouched).

## 6. Checksums

| Item | Value |
|---|---|
| Package | `NX-WA-2.88.0-nxwa.15.2.zip` |
| Size | 10,153,645 B |
| MD5 | `dbe4ea5472058639d6bf16760eb56c07` |
| Entries | 372 = 368 main tree + 3 `patch-a2/` assets + manifest |
| Upgrade | overwrite an existing 15.1 install; incremental sync only overwrites, never deletes |
