"""Compile an explicitly declared legacy RGB library into native NX500 slots.

Offline only. Use a separate, immutable source backup. Factory references and
identity are preserved. No directory deletions and no device/network access.
"""
import argparse
import hashlib
import json
from pathlib import Path
from native_codec import compile_rgb, record_native, space_for, NATIVE


def migrate(source, destination):
    source,destination=Path(source).resolve(),Path(destination).resolve()
    if source==destination:raise ValueError('source must be a separate immutable backup')
    destination.mkdir(parents=True,exist_ok=True)
    rows=[]
    for p in sorted(source.glob('*.bin')):
        raw=p.read_bytes()
        if len(raw)!=19712:raise ValueError(f'{p}: wrong slot size')
        # The identity bytes have the same semantics in both coordinate systems.
        preserved=space_for(p,raw)==NATIVE or p.stem=='identity17'
        result=raw if preserved else compile_rgb(raw)
        target=destination/p.name
        temp=target.with_suffix('.bin.tmp')
        temp.write_bytes(result)
        temp.replace(target)
        record_native(target,result)
        rows.append({'name':p.name,'source_sha256':hashlib.sha256(raw).hexdigest(),
                     'native_sha256':hashlib.sha256(result).hexdigest(),
                     'preserved':preserved})
    return rows


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--src',type=Path,required=True)
    p.add_argument('--dst',type=Path,required=True)
    p.add_argument('--source-space',choices=['legacy-rgb'],required=True)
    p.add_argument('--manifest',type=Path,required=True)
    a=p.parse_args()
    rows=migrate(a.src,a.dst)
    a.manifest.write_text(json.dumps({'source_space':'explicit legacy-rgb',
        'destination_space':NATIVE,'tables':rows},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'{len(rows)} tables; {sum(r["preserved"] for r in rows)} native references/identity preserved')


if __name__=='__main__':main()
