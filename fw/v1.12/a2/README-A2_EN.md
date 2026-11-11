# A2 Patch Image (p7 segment) — Flashing Guide

> **`p7_a2.bin`** in this folder is the **p7-partition image** of the `NXWA-A2` patch (12,075,648 bytes).
> It is the firmware prerequisite for **all-7-dimension PW one-tap**: after it is written to the camera's p7 partition, `filmlab.sh` can push **all seven dimensions at once** (R/G/B/HUE/SAT/SHARP/CON).
> Without A2, everything behaves as before (the push step is silently ineffective — it does not crash); the full-range effect can still be obtained via "Picture Wizard → Custom 1".

> **2026-11-11 wording update**: remote access is **ssh (port 22) only**; telnet and FTP were retired on 2026-11-02.
> Older guides that say "tap the IP row to enable Telnet" or "copy the file over FTP" are obsolete.
> Every command below runs in an **ssh session**.

---

## 0. Two different artifacts

| Artifact | Size | Purpose | Where to get it |
|---|---|---|---|
| `p7_a2.bin` (the subject here) | 12,075,648 B | **Channel A**: writes the p7 partition only, ~1 s | inside every release zip as `patch-a2/p7_a2.bin` |
| `slp_a2_p7_v117.bin` | 352,121,435 B | **Channel B**: full package through the official flashing chain | Release asset (currently on the `v2.88.0-nxwa.2` page; `.md5` included) |

Both write the **same** content into p7. Pick one — do not do both.

## 1. Prerequisites

- **NX500 only** (no NX1 build), verified against official firmware **1.12**.
- The mod is installed and you can **ssh in**: `ssh root@<camera-ip>`, then press Enter for the blank password.
  - Unknown IP / cannot connect: on the camera tap the menu row `IP: x.x.x.x [SSH on]` — it pops the login string.
  - Or start dropbear first: `sh /opt/usr/nx-ks/ssh_hint.sh --start`.
  - Prefer a key instead of the blank password: see the "Remote access (SSH)" section of the README.
- Enough battery (the write takes about one second, but it must not lose power).

### 1.1 Get the image onto the camera's SD card (either way)

```sh
# Option 1: unzip the release to the SD-card root -> on the camera it is /mnt/mmc/patch-a2/p7_a2.bin
#           (NX-WA-<ver>.zip already contains the patch-a2/ folder)

# Option 2: copy it directly from the PC
scp patch-a2/p7_a2.bin root@192.168.0.106:/mnt/mmc/
```

> The SD-card root is `/mnt/mmc` on the camera. Both routes are equivalent; option 1 needs no ssh client.

## 2. Match three numbers first

| Item | Expected |
|---|---|
| File size | `12075648` bytes |
| md5 | `712c6fd0a49371ec05ce94c367b0d5c7` |
| Target partition | `/dev/mmcblk0p7` (~30 MB, p7 = ISP firmware partition) |

```sh
md5sum /mnt/mmc/patch-a2/p7_a2.bin      # must equal 712c6fd0…
cat /proc/partitions | grep mmcblk0p7   # partition must exist, ~30720 blocks (=30 MB)
```

If the md5 does not match, stop here: copy the file again (large files occasionally get corrupted
on exFAT) or re-extract the zip on the PC.

## 3. Flash it (run line by line in the ssh session)

```sh
# 3.1 Back up the current p7 — your only rollback; do NOT skip
dd if=/dev/mmcblk0p7 of=/mnt/mmc/p7_backup_$(date +%s).bin bs=1M
sync
ls -l /mnt/mmc/p7_backup_*.bin          # note the name; rollback needs it

# 3.2 Write A2 (~1 second)
dd if=/mnt/mmc/patch-a2/p7_a2.bin of=/dev/mmcblk0p7 bs=1M
sync; sync; sync

# 3.3 Read-back verification (12 MiB = image 12,075,648 B + 507,264 B zero tail)
dd if=/dev/mmcblk0p7 bs=1M count=12 2>/dev/null | md5sum
#     expected: 69050a17ea9fdbcdab4cf32e7b5ffdb2
```

⚠️ **Read the device name twice before executing**: the target is `/dev/mmcblk0p7`.
Writing e.g. `mmcblk0p1` is irreversible.

### 3.4 If the read-back is not `69050a17…`

Do not panic — two cases:

| Symptom | Meaning | Action |
|---|---|---|
| Completely different | write did not finish, or wrong file | re-run 3.2 once, then read back again |
| Slightly different, on a camera that had a third-party p7 before | the tail (the 507,264 B beyond the image) is not zero | confirm the image range with the split check below |

```sh
# Split check: first 11 MiB + remaining 541,312 B; equal on both sides means the image is in place
# partition side
dd if=/dev/mmcblk0p7 bs=1M count=11 2>/dev/null | md5sum
dd if=/dev/mmcblk0p7 bs=1M skip=11 2>/dev/null | head -c 541312 | md5sum
# image side (reference)
dd if=/mnt/mmc/patch-a2/p7_a2.bin bs=1M count=11 2>/dev/null | md5sum
tail -c 541312 /mnt/mmc/patch-a2/p7_a2.bin | md5sum
```

If the two pairs match, the image range is correct and the tail difference is merely historical
leftover — ignore it.

## 4. Activation

- **Normal power off → power on** (the p7 firmware loads on the next boot; a normal power cycle is enough).
- ⛔ **NEVER** `systemctl restart di-camera-app` — measured to **freeze the whole camera**; only a physical power-off recovers it.

## 5. Verify success

```sh
sh /opt/usr/nx-ks/filmlab.sh pwpush portra400 --yes    # one-tap push a recipe
sh /opt/usr/nx-ks/filmlab.sh check                     # 7 dimensions vs the recipe slot
```

- The image **changes immediately** + `check` passes = success.
- No visible change: re-check the 3.3 read-back, and whether you did one **normal power-off → power-on**.

## 6. Rollback

```sh
dd if=/mnt/mmc/p7_backup_<timestamp>.bin of=/dev/mmcblk0p7 bs=1M
sync; sync; sync
```

Then **normal power off → power on**. Re-flashing the official 1.12 package (which rewrites p7)
also works.

## 7. Risks & discipline

- Do **not** cut power or pull the card while writing; external power is safer.
- Official firmware upgrades rewrite p7 ⇒ **re-flash A2 afterwards**.
- The partition (30 MB) is larger than the image (12 MB); the area after the image stays as it was. Normal.
- Community build, use at your own risk. If something goes wrong, roll back per §6 instead of retrying blindly.

## 8. Numbers for cross-checking

| Artifact | md5 |
| --- | --- |
| `p7_a2.bin` (this folder) | `712c6fd0a49371ec05ce94c367b0d5c7` |
| 12 MiB read-back (image + zero tail) | `69050a17ea9fdbcdab4cf32e7b5ffdb2` |
| Full flashing package `slp_a2_p7_v117.bin` (352 MB, Release asset) | `44b61efc0625874b62ef6a45517ffda8` |

## 9. One-line mechanism

A2 adds a "slot-pool direct write" channel inside p7: an external `seq 0x134..0x13A` (7 raw values) + `0x13B` (trigger) → p7 writes the parameter slots → the official "slot apply" chain pushes all 7 dimensions into the ISP — that is how "one-tap" is achieved. Details: `docs/current/A2_PATCH_DESIGN_2026-10-14.md`, `A2_READBACK_VERDICT_2026-10-15.md`.
