"""Extract byte-exact native Cr,Cb,Y factory LUTs. No device access or RGB guessing."""
import argparse,hashlib,json,pathlib
SHA256='f8e417cb5b55768851ba7e2b8017d3a98dc0b0c8444cc0a5061265cc08dbbf7f'
TABLE=17**3*4
SLOT=0x4d00
BLOCKS={'a':(0x8592c0,20),'b':(0x8b9ac0,22)}

def extract(image,out):
 image=pathlib.Path(image).read_bytes()
 if image[:4]==b'\x7fELF':image=image[0x1000:]
 digest=hashlib.sha256(image).hexdigest()
 if digest!=SHA256:raise ValueError('not the verified NX500 1.12 p7 image: '+digest)
 rows={};out=pathlib.Path(out);out.mkdir(parents=True,exist_ok=True)
 for block,(base,count) in BLOCKS.items():
  for i in range(count):
   off=base+i*SLOT;raw=image[off:off+SLOT]
   if len(raw)!=SLOT or any(raw[3:TABLE:4]):raise ValueError(f'invalid native table at {off:#x}')
   name=f'samsung_{block}{i:02d}.bin';target=out/name
   if target.exists() and target.read_bytes()!=raw:raise ValueError('refusing to overwrite different '+str(target))
   target.write_bytes(raw)
   rows[name]={'space':'CrCbY-BT601-full-v1','sha256':hashlib.sha256(raw).hexdigest(),
     'offset':hex(off),'va':hex(0x80000000+off),'bytes':len(raw),
     'neutral_axis':[list(raw[((k*17+8)*17+8)*4:((k*17+8)*17+8)*4+3]) for k in range(17)],
     'note':'native factory bytes; working matrix is not a measured camera colour profile; not an inverse TC'}
 (out/'encoding.json').write_text(json.dumps({'version':1,'tables':rows},indent=2),encoding='utf-8')
 (out/'provenance.json').write_text(json.dumps({'p7_sha256':digest,'tables':rows,
  'scope':'offline byte extraction; no camera deployment; do not apply these as RGB cubes or inverse TC'},indent=2),encoding='utf-8')
 return rows

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--image',required=True);p.add_argument('--out',required=True);a=p.parse_args()
 print('Extracted',len(extract(a.image,a.out)),'native factory tables')
