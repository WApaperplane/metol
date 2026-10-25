"""Produce the dedup keep/remove list and move redundant tables to an archive.

Rules, in order of precedence:

  1. PROTECT set never gets removed: identity17, the three factory tables, and
     everything from the v2_ (Codex) and gap_ (this round) batches.  Those are
     the current design intent; an old table that duplicates them is the one
     that goes.
  2. Within a complete-linkage cluster at the JND threshold (median dE00 < 1.5,
     i.e. two looks a person cannot reliably tell apart), keep exactly one.
     Preference: protected > shorter name (the base film name rather than a
     variant suffix) > alphabetical, so kodak_portra400 survives before
     kodak_portra400nc.
  3. Nothing is deleted.  Files move to an archive directory so the operation is
     reversible, and the remove list is written before anything moves.

Writes: dedup_plan.json (full decision record), remove_list.txt
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import numpy as np

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, str(Path(__file__).parent))
from cluster_audit import complete_linkage, load  # noqa: E402

OUT = Path(__file__).resolve().parent / 'audit_out'
LOOKS = Path(r'E:/NXWA/nx500-modding-work/looks')
ARCHIVE = OUT / 'archived_redundant'
THRESH = 1.5

PROTECT = {'identity17', 'samsung_a00', 'samsung_a01', 'samsung_a02'}
PROTECT_PREFIX = ('v2_', 'gap_')

# Manual keep decisions.  A length-based tie-break produced nonsense - it wanted
# to drop Kodak Portra 400 in favour of Leica M9, and Kodak Gold 200 in favour of
# Agfa Vista 200 - because "shorter name" is not a proxy for "the look people
# actually reach for".  Where two tables are at JND distance, keep the one with
# the clearer film/stock identity; these overrides encode that.
KEEP_OVERRIDE = {
    frozenset({'fuji_provia100f', 'canon_landscape', 'kodak_e100'}): 'fuji_provia100f',
    frozenset({'cool_blue', 'cool_cyan', 'fuji_400h'}): 'fuji_400h',
    frozenset({'polaroid_600', 'ricoh_negative'}): 'polaroid_600',
    frozenset({'fuji_superia400', 'fuji_superia400p'}): 'fuji_superia400',
    frozenset({'cool_steel', 'fuji_classicchrome'}): 'fuji_classicchrome',
    frozenset({'film_faded', 'style_dream'}): 'film_faded',
    frozenset({'cool_arctic', 'cool_mint'}): 'cool_arctic',
    frozenset({'agfa_rsx200', 'leica_m10'}): 'agfa_rsx200',
    frozenset({'pentax_reversal', 'ricoh_positive'}): 'pentax_reversal',
    frozenset({'polaroid_itype', 'pentax_muted'}): 'polaroid_itype',
    frozenset({'pentax_vibrant', 'style_vivid'}): 'pentax_vibrant',
    frozenset({'fuji_astia100f', 'leica_m240', 'canon_portrait',
               'fuji_proneg_std'}): 'fuji_astia100f',
    frozenset({'kodak_ultramax400', 'kodak_portra400vc'}): 'kodak_ultramax400',
    frozenset({'polaroid_expired', 'polaroid_sx70'}): 'polaroid_expired',
    frozenset({'kodak_gold200', 'agfa_vista200'}): 'kodak_gold200',
    frozenset({'kodak_portra400', 'kodak_portra160', 'kodak_portra400nc',
               'fuji_proneg_hi', 'leica_m9'}): 'kodak_portra400',
    frozenset({'fuji_velvia50', 'fuji_velvia100'}): 'fuji_velvia50',
    frozenset({'identity17', 'film_provia', 'samsung_a02'}): 'identity17',
    frozenset({'film_astia', 'film_portra'}): 'film_portra',
    frozenset({'pentax_satobi', 'cool_slate'}): 'pentax_satobi',
}


def pick_keep(members):
    key = frozenset(members)
    if key in KEEP_OVERRIDE:
        chosen = KEEP_OVERRIDE[key]
        if chosen in members:
            return chosen
    return sorted(members, key=rank)[0]


def rank(name):
    if name in PROTECT:
        return (0, len(name), name)
    if name.startswith(PROTECT_PREFIX):
        return (1, len(name), name)
    return (2, len(name), name)


def main(do_move=False):
    D, names = load()
    clusters = complete_linkage(D, THRESH)
    plan, remove = [], []
    for c in clusters:
        members = sorted((names[i] for i in c))
        if len(members) == 1:
            continue
        keep = pick_keep(members)
        drop = [m for m in members if m != keep]
        # never drop a protected table even if rank says so
        drop = [m for m in drop if m not in PROTECT
                and not m.startswith(PROTECT_PREFIX)]
        for m in drop:
            i, j = names.index(m), names.index(keep)
            plan.append(dict(remove=m, keep=keep,
                             dE00=round(float(D[i, j]), 3),
                             cluster=members))
            remove.append(m)

    (OUT / 'dedup_plan.json').write_text(
        json.dumps(plan, ensure_ascii=False, indent=1), encoding='utf-8')
    (OUT / 'remove_list.txt').write_text('\n'.join(sorted(remove)) + '\n',
                                         encoding='utf-8')

    print('threshold: complete-linkage, median dE00 < %.2f' % THRESH)
    print('redundant tables: %d  (%d -> %d)'
          % (len(plan), len(names), len(names) - len(plan)))
    print()
    print('%-26s %-26s %8s' % ('REMOVE', 'KEEP', 'dE00'))
    for row in sorted(plan, key=lambda r: r['dE00']):
        print('%-26s %-26s %8.3f' % (row['remove'], row['keep'], row['dE00']))

    if do_move:
        ARCHIVE.mkdir(exist_ok=True)
        moved = 0
        for m in sorted(remove):
            src = LOOKS / (m + '.bin')
            if src.exists():
                shutil.move(str(src), str(ARCHIVE / src.name))
                moved += 1
        print()
        print('archived %d files to %s' % (moved, ARCHIVE))

        # drop their encoding.json entries so the manifest stays truthful
        enc = LOOKS / 'encoding.json'
        meta = json.loads(enc.read_text(encoding='utf-8'))
        for m in remove:
            meta['tables'].pop(m + '.bin', None)
        enc.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n',
                       encoding='utf-8')
        print('encoding.json now lists %d tables' % len(meta['tables']))
        print('remaining bin files: %d'
              % len(list(LOOKS.glob('*.bin'))))


if __name__ == '__main__':
    main(do_move='--move' in sys.argv)
