"""Cluster the library with complete linkage and produce a dedup keep/remove list.

Single linkage chains: with a 3.112 gate it merged 72 of 90 tables into one
"cluster", which is true but useless - A is close to B, B to C, so A ends up with
Z.  Complete linkage guarantees every member of a cluster is within the threshold
of every other member, which is what "these are the same look" actually means.

Also reports the effective diversity of the library: if 90 tables occupy only a
handful of distinguishable appearances, deleting a few near-duplicates changes
nothing and the real fix is to design looks that occupy empty space.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.stdout.reconfigure(encoding='utf-8')
OUT = Path(__file__).resolve().parent / 'audit_out'

# ALWAYS KEEP: reference / calibration / freshly designed.  Everything else is
# a candidate for removal if it duplicates something.
PROTECT = {
    'identity17',                       # neutral baseline, must exist
    'samsung_a00', 'samsung_a01', 'samsung_a02',   # factory reference tables
}
PROTECT_PREFIX = ('v2_',)               # Codex's 12 main designs


def load():
    D = np.load(OUT / 'distance.npy')
    names = json.loads((OUT / 'names.json').read_text(encoding='utf-8'))
    return D, names


def complete_linkage(D, thresh):
    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial.distance import squareform
    Z = linkage(squareform(D, checks=False), method='complete')
    lab = fcluster(Z, t=thresh, criterion='distance')
    groups = {}
    for i, g in enumerate(lab):
        groups.setdefault(int(g), []).append(i)
    return list(groups.values())


def diversity_stats(D, names):
    n = len(names)
    iu = np.triu_indices(n, 1)
    vals = D[iu]
    print('=== library diversity ===')
    print('tables                %d' % n)
    print('pairs                 %d' % len(vals))
    for q in (10, 25, 50, 75, 90, 95):
        print('  p%-3d dE00          %6.2f' % (q, np.percentile(vals, q)))
    print('  max                 %6.2f' % vals.max())
    print('pairwise < 1.0        %5.1f%%' % (100 * (vals < 1.0).mean()))
    print('pairwise < 2.3 (JND)  %5.1f%%' % (100 * (vals < 2.3).mean()))
    print('pairwise < 3.112      %5.1f%%' % (100 * (vals < 3.112).mean()))
    print()
    # effective rank: how many independent directions does the library span?
    from scipy.cluster.hierarchy import linkage
    from scipy.spatial.distance import squareform
    Z = linkage(squareform(D, checks=False), method='complete')
    heights = Z[:, 2]
    print('merger heights (last 15), i.e. distance at which clusters join:')
    print('  ' + ' '.join('%.1f' % h for h in heights[-15:]))
    print()
    return vals


def main():
    D, names = load()
    n = len(names)
    diversity_stats(D, names)

    for thresh in (1.5, 2.3, 3.112):
        clusters = complete_linkage(D, thresh)
        clusters.sort(key=len, reverse=True)
        multi = [c for c in clusters if len(c) > 1]
        print('=' * 78)
        print('complete linkage @ dE00 < %.3f : %d clusters, %d multi-member'
              % (thresh, len(clusters), len(multi)))
        removed = 0
        for c in multi:
            members = sorted((names[i] for i in c))
            keep = []
            for m in members:
                if m in PROTECT or m.startswith(PROTECT_PREFIX):
                    keep.append(m)
            if not keep:
                # keep the one furthest from the rest of the library (most distinct)
                idx = [names.index(m) for m in members]
                best, bestscore = None, -1
                for i in idx:
                    others = [j for j in range(n) if j != i]
                    score = float(np.mean(D[i, others]))
                    if score > bestscore:
                        bestscore, best = score, names[i]
                keep = [best]
            drop = [m for m in members if m not in keep]
            removed += len(drop)
            print('  KEEP %-24s  DROP %s'
                  % (', '.join(keep), ', '.join(drop) if drop else '-'))
        print('  -> removable: %d  (library %d -> %d)'
              % (removed, n, n - removed))
        print()

    # nearest neighbour table for the record
    nn = sorted((min(D[i, j] for j in range(n) if j != i), names[i])
                for i in range(n))
    (OUT / 'nearest_neighbour.json').write_text(
        json.dumps([{'table': nm, 'nn_dE00': round(d, 3)} for d, nm in nn],
                   ensure_ascii=False, indent=1), encoding='utf-8')
    print('top 20 undifferentiated:')
    for d, nm in nn[:20]:
        print('  %6.3f  %s' % (d, nm))


if __name__ == '__main__':
    main()
