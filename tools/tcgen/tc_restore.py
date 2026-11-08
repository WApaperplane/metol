"""Generate an explicitly uncalibrated RGB technical-restore candidate from TC nodes.

Model: stock_TC(inverse(candidate_TC(code))). Real ISP ordering, channel domain,
gamut and clipping are not established by node coordinates. This is a testable
candidate, not a Samsung colour profile or guaranteed camera-log transform.
"""
import argparse,hashlib,json,pathlib
import numpy as np
from tcgen import X_STOCK,Y_STOCK,build

def restore(values,curve):
 y=np.asarray(build(curve),dtype=float)/1023
 source=np.interp(np.clip(values,0,1),y,np.asarray(X_STOCK)/16383)
 return np.interp(source,np.asarray(X_STOCK)/16383,np.asarray(Y_STOCK)/1023)

def cube(curve,path,size=65):
 if size<2 or size>129:raise ValueError('cube size must be 2..129')
 path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 ramp=restore(np.linspace(0,1,size),curve)
 with path.open('w',encoding='ascii',newline='\n') as f:
  f.write(f'TITLE "NX500 {curve} to stock TC MODEL - uncalibrated"\n# Not an official Samsung transform. No factory 3DLUT baked in.\nLUT_3D_SIZE {size}\nDOMAIN_MIN 0 0 0\nDOMAIN_MAX 1 1 1\n')
  for b in ramp:
   for g in ramp:
    for r in ramp:f.write(f'{r:.8f} {g:.8f} {b:.8f}\n')
 meta={'curve':curve,'size':size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
  'direction':'candidate encoded RGB to stock-TC model RGB','domain':[0,1],
  'model':'stock_TC(inverse(candidate_TC(x))) applied equally to encoded RGB channels',
  'status':'uncalibrated candidate, not a verified colour restoration LUT',
  'factory_lut_included':False,'limitations':['TC coordinate domain may differ from decoded RGB',
   'existing ISP/3DLUT may already transform or clip colour','no colour-chart validation',
   'does not recover clipped or quantized information']}
 path.with_suffix('.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
 return meta

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--curve',choices=['stock','linear','log','flat','hc'],required=True);p.add_argument('--out',required=True);p.add_argument('--size',type=int,default=65);a=p.parse_args()
 print(json.dumps(cube(a.curve,a.out,a.size),indent=2))
