# NX-WA 2.88.0-nxwa.15.4

Released: 2026-11-14
Two reports from GitHub Discussions, plus fixes made after 15.3 that were not shipped yet.

## 1. Switching recipes overwrote another custom field (fixed)

With **Custom 2** active, browsing or committing a FilmLab recipe also changed Custom 2.
The direct-push channel commits while the *currently selected* field is still active, so the camera
attributed the new values to it — and only Custom 1 was written and backed up.

The engine now moves to Custom 1 **before** pushing, and backs up whichever field was active when
the panel opened. Verified on hardware: Custom 2 is byte-identical after a commit.

## 2. No video recording, card stutter (fixed)

The boot script forced 4K Pro to **160 Mbps** and HD Pro to **180 Mbps** (~20 MB/s sustained).
A Class 10 card does 10 MB/s, so the write buffer fills — UI stutter first, then the recording aborts.
Stock 4K Pro is ~60 Mbps.

New defaults are `80 / 100 / 50 / 60 / 40`. The 视频码率 menu still goes higher and now persists
across reboots. Measured: a 4 s take came out at 40.4 MB ≈ 80 Mbps.
**If your card still struggles, drop 4K-ProQ to 50.**

## 3. Other fixes since 15.3

- **"Restore stock" no longer reports success falsely** — a 0-byte A18 backup used to log a warning
  and skip; it now falls back to the shipped baseline and verifies the result.
- **SD state layer** — this card's exFAT does **not** replace an existing target on rename; every
  overwrite leaves a stale directory entry (10 writes → 11 entries). Volatile state moved to tmpfs,
  persistent files now go through `rm`-first atomic replace.
- **Preview speed**: browsing the FilmLab panel 930 → 552/455 ms (only changed dimensions are sent).
- **Docs**: the LUT video first-frame mechanism was replaced by redirecting p7's 23-entry slot
  pointer table to A18; the old "first frame may not carry the LUT" note is obsolete.
  Continuous recording: **4 minutes verified**.

## 4. Packages

| Package | Size | md5 | Entries |
|---|---|---|---|
| `NX-WA-2.88.0-nxwa.15.4.zip` | 10,504,071 B | `2d76d8f2ae538a5502e2d76226d9fe31` | 398 + manifest |
| `NX-WA-2.88.0-nxwa.15.4-EN.zip` | 10,503,272 B | `2578377eeb2ccd666ae7971c0fc70c51` | 398 + manifest |

## 5. Upgrade

Extract to the SD card root → insert → wait for the automatic sync → reboot.
The bitrate change takes effect **after a reboot**.

## Boundaries

Frame-rate combinations for video LUT are still untested; the lower bitrate is a default, not a cap.
