"""Build separately specified, reference-inspired camera/film looks.

Uses perceptual tone, selective hue/chroma and explicit split-tone targets.
This is creative colour design, not a claim of manufacturer calibration.
Evaluation is in valid display-referred RGB. The native boundary extension is
tested with identity, monochrome and affine transforms before use.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.interpolate import PchipInterpolator
from native_codec import compile_uniform_rgb,record_native

HERE=Path(__file__).resolve().parent
PROFILE_PATH=HERE/'style_profiles.json'


def load_profiles():
    return json.loads(PROFILE_PATH.read_text(encoding='utf-8'))


def smooth(lo,hi,x):
    f=np.clip((x-lo)/(hi-lo),0,1)
    return f*f*(3-2*f)


def rgb_lab(rgb):
    f=np.asarray(rgb,dtype=float)/255
    linear=np.where(f<=.04045,f/12.92,((f+.055)/1.055)**2.4)
    xyz=linear@np.array([[.4124564,.2126729,.0193339],
        [.3575761,.7151522,.119192],[.1804375,.072175,.9503041]])/np.array([.95047,1,1.08883])
    q=np.where(xyz>.008856,np.cbrt(xyz),7.787*xyz+16/116)
    return np.stack((116*q[...,1]-16,500*(q[...,0]-q[...,1]),200*(q[...,1]-q[...,2])),axis=-1)


def lab_linear(lab):
    L,a,b=np.moveaxis(lab,-1,0)
    fy=(L+16)/116
    q=np.stack((fy+a/500,fy,fy-b/200),axis=-1)
    xyz=np.where(q>6/29,q**3,(q-16/116)/7.787)*np.array([.95047,1,1.08883])
    return xyz@np.array([[3.2404542,-.969266,.0556434],
        [-1.5371385,1.8760108,-.2040259],[-.4985314,.041556,1.0572252]])


def lab_rgb_gamut(lab):
    """Fit desired output by common linear-RGB offset and scaling.

    Shift negative minima to zero, then scale a maximum above one to one.
    This preserves component ordering and ratios of channel differences in
    linear RGB. L* may change. Fixed-L* chroma compression near paper white
    created a steep yellow-to-white transition that the 17^3 lattice reproduced
    poorly. This operates on valid design outputs, not native input projection.
    """
    linear=lab_linear(lab)
    linear-=np.minimum(linear.min(-1,keepdims=True),0)
    linear/=np.maximum(linear.max(-1,keepdims=True),1)
    srgb=np.where(linear<=.0031308,12.92*linear,1.055*linear**(1/2.4)-.055)
    return np.clip(srgb*255,0,255)


def hsv_hue(rgb):
    maximum=rgb.max(-1);minimum=rgb.min(-1);delta=maximum-minimum
    safe=np.maximum(delta,1e-8)
    r,g,b=np.moveaxis(rgb,-1,0)
    h=np.where(maximum==r,((g-b)/safe)%6,
        np.where(maximum==g,(b-r)/safe+2,(r-g)/safe+4))*60
    s=delta/np.maximum(maximum,1e-8)
    return h,s


def hue_weights(h,table,sigma=28,baseline=0):
    numerator=np.zeros_like(h);denominator=np.zeros_like(h)
    for anchor,value in table.items():
        dist=(h-float(anchor)+180)%360-180
        w=np.exp(-.5*(dist/sigma)**2)
        numerator+=w*(value-baseline);denominator+=w
    return baseline+numerator/np.maximum(1,denominator)


def grade(rgb,profile,tone_input=None):
    rgb=np.asarray(rgb,dtype=float)
    shape=rgb.shape
    rgb=rgb.reshape(-1,3)
    lab=rgb_lab(rgb);L,a,b=lab.T;C=np.hypot(a,b)
    h,s=hsv_hue(rgb)
    tone_input=tone_input or [0,8,20,40,60,80,92,100]
    target_L=PchipInterpolator(tone_input,profile['tone'])(np.clip(L,0,100))
    coloured=C/(C+8)
    skin=np.exp(-.5*(((h-28+180)%360-180)/18)**2)
    skin*=smooth(.10,.25,s)*(1-smooth(.60,.85,s))*smooth(15,35,L)*(1-smooth(80,95,L))
    target_L+=hue_weights(h,profile.get('lightness_hues',{}))*coloured
    angle=np.arctan2(b,a)+np.deg2rad(hue_weights(h,profile.get('hue',{})))*coloured*(1-.4*skin)
    multiplier=profile.get('sat',1)*hue_weights(h,profile.get('sat_hues',{}),baseline=1)
    # Low-light protection is smooth and does not force all styles to neutral.
    multiplier=1+(multiplier-1)*(.60+.40*smooth(5,30,L))
    target_C=C*np.maximum(0,multiplier)
    aa,bb=target_C*np.cos(angle),target_C*np.sin(angle)
    split=profile.get('split',{})
    weights={'shadow':1-smooth(12,58,L),
             'mid':np.exp(-.5*((L-50)/19)**2),
             'highlight':smooth(52,94,L)}
    endpoints=smooth(0,7,L)
    if profile.get('protect_white',True):endpoints*=1-smooth(96,100,L)
    chroma_keep=(.55+.45*28/(28+C))*(1-.3*skin)
    for key,w in weights.items():
        da,db=split.get(key,[0,0])
        aa+=da*w*endpoints*chroma_keep
        bb+=db*w*endpoints*chroma_keep
    aa+=profile.get('skin',{}).get('a',0)*skin
    bb+=profile.get('skin',{}).get('b',0)*skin
    if profile.get('monochrome',False):aa[:]=0;bb[:]=0
    result=np.stack((np.clip(target_L,0,100),aa,bb),axis=-1)
    return lab_rgb_gamut(result).reshape(shape)


def build_profile(name,profile,outdir,n=33,tone_input=None):
    axis=np.linspace(0,255,n)
    b,g,r=np.meshgrid(axis,axis,axis,indexing='ij')
    source=np.stack((r,g,b),axis=-1)
    nodes=grade(source,profile,tone_input)
    raw=compile_uniform_rgb(nodes.reshape(-1,3).tolist(),n,boundary='linear')
    outdir=Path(outdir);outdir.mkdir(parents=True,exist_ok=True)
    target=outdir/('v2_'+name+'.bin')
    target.write_bytes(raw);record_native(target,raw)
    return raw,{'name':name,'label':profile['label'],'family':profile['family'],
        'intent':profile['intent'],'source':profile['source'],
        'status':'creative interpretation; not a measured replica',
        'file':target.name,'sha256':hashlib.sha256(raw).hexdigest(),
        'recipe':profile,'native_boundary':'linear RGB boundary-cell extension'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',required=True,type=Path)
    p.add_argument('--only')
    p.add_argument('--include-variants',action='store_true',help='also export six close-family variants; default is the curated 12')
    args=p.parse_args()
    data=load_profiles();rows=[]
    names=set(args.only.split(',')) if args.only else set(data['profiles'] if args.include_variants else data['selection'])
    if not names.issubset(data['profiles']):raise ValueError('unknown profile name')
    if args.out.exists():
        extras={p.name for p in args.out.glob('*.bin')}-{f'v2_{n}.bin' for n in names}
        if extras:raise ValueError('output contains unselected tables; use a fresh directory')
    for name,profile in data['profiles'].items():
        if name not in names:continue
        _,row=build_profile(name,profile,args.out,tone_input=data['tone_input_L'])
        rows.append(row);print(name,profile['label'],flush=True)
    (args.out/'manifest.json').write_text(json.dumps({'schema':1,
        'interpretation':data['interpretation'],'profiles':rows},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':main()
