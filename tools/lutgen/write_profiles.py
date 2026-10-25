"""Write the 12 gap-filling profiles into looks/ and record them as native."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
LUTGEN = Path(__file__).resolve().parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

import gap_profiles as fg                      # noqa: E402
from native_codec import record_native      # noqa: E402

LOOKS = Path(r'E:/NXWA/nx500-modding-work/looks')
OUT = Path(__file__).resolve().parent / 'audit_out'
PREFIX = 'gap_'


def main():
    admitted = json.loads((OUT / 'admitted.json').read_text(encoding='utf-8'))
    rows = []
    for name in admitted:
        prof = fg.PROFILES[name]
        raw = fg.build_one(name, prof)
        target = LOOKS / (PREFIX + name + '.bin')
        target.write_bytes(raw)
        record_native(target, raw)
        rows.append(dict(file=target.name, name=name,
                         label=prof['label'], family=prof['family'],
                         intent=prof['intent'], source=prof['source'],
                         recipe=prof))
        print('%-30s %6d bytes' % (target.name, len(raw)))
    (OUT / 'gap_manifest.json').write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding='utf-8')
    print('\n%d written + recorded as CrCbY-BT601-full-v1' % len(rows))


if __name__ == '__main__':
    main()
