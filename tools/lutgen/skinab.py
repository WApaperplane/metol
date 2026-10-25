#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""skinab.py — 真实照片里「肤色区」的 Lab 偏移。偏粉/偏红只有在这一层看得准。"""
import os, sys
import numpy as np
from PIL import Image
BASE=os.path.dirname(os.path.abspath(__file__))
REPO=os.path.dirname(os.path.dirname(BASE))
sys.path.insert(0,BASE)
from preview_photos import apply_lut, load_lut

def lab(a):
    f=a.astype(np.float32)/255.0
    lin=np.where(f<=0.04045,f/12.92,((f+0.055)/1.055)**2.4)
    r,g,b=lin[:,:,0],lin[:,:,1],lin[:,:,2]
    x=(0.4124564*r+0.3575761*g+0.1804375*b)/0.95047
    y=0.2126729*r+0.7151522*g+0.0721750*b
    z=(0.0193339*r+0.1191920*g+0.9503041*b)/1.08883
    f_=lambda t: np.where(t>0.008856,np.cbrt(t),7.787*t+16/116.0)
    fx,fy,fz=f_(x),f_(y),f_(z)
    return 116*fy-16, 500*(fx-fy), 200*(fy-fz)

def hsv(a):
    f=a.astype(np.float32)/255.0
    mx=f.max(axis=2); mn=f.min(axis=2); d=mx-mn
    r,g,b=f[:,:,0],f[:,:,1],f[:,:,2]
    h=np.zeros_like(mx)
    m=d>1e-6
    im=m&(mx==r); h[im]=((g-b)[im]/d[im])%6.0
    ig=m&~im&(mx==g); h[ig]=(b-r)[ig]/d[ig]+2.0
    ib=m&~im&~ig; h[ib]=(r-g)[ib]/d[ib]+4.0
    return h*60.0, np.where(mx>0,d/np.maximum(mx,1e-6),0), mx

PDIR=os.path.join(REPO,'..','_photos')
files=sorted(f for f in os.listdir(PDIR) if f.lower().endswith(('.jpg','.jpeg')))
imgs=[]
for f in files:
    im=Image.open(os.path.join(PDIR,f)).convert('RGB')
    w=260; h=max(1,int(im.height*w/float(im.width)))
    imgs.append(np.asarray(im.resize((w,h),Image.LANCZOS)))

# 肤色掩码：hue 5–45°, s 0.15–0.65, v 0.25–0.95（覆盖浅/深肤色，排除纯红与高饱和橙）
# ★ 另加「亮白区」掩码 L*>72 —— 暖光下的白布/白墙最容易暴露偏粉：削黄即变粉，
#   而纯灰轴 (v,v,v) 测不到（它不是被暖光照亮的中性面）。
masks=[]; wmasks=[]
for a in imgs:
    H,S,V=hsv(a)
    masks.append((H>=5)&(H<=45)&(S>=0.15)&(S<=0.65)&(V>=0.25)&(V<=0.95))
    L,_,_=lab(a)
    wmasks.append((L>72)&(S<0.45))
base=[]
for a,m in zip(imgs,masks):
    L,A,B=lab(a)
    base.append((A[m].mean(),B[m].mean(),m.sum()))
bA=np.mean([x[0] for x in base]); bB=np.mean([x[1] for x in base])
print('肤色区基线：a* %+.1f  b* %+.1f  （%d 张，每张中位 %d 像素）'
      %(bA,bB,len(imgs),int(np.median([x[2] for x in base]))))
print()
looks=os.path.join(REPO,'looks')
only=sys.argv[1:] or None
names=sorted(f[:-4] for f in os.listdir(looks) if f.endswith('.bin'))
if only: names=[n for n in names if n in only]
print('%-20s %6s %6s %6s %6s %6s  %s'%('表','肤A*','肤B*','白A*','白B*','白余量','判读'))
print('-'*76)
rows=[]
for n in names:
    lut=load_lut(os.path.join(looks,n+'.bin'))
    aa=[];bb=[];wa=[];wb=[]
    for a,m,wm in zip(imgs,masks,wmasks):
        o=apply_lut(a.astype(np.float32),lut)
        L,A,B=lab(o)
        if m.sum()>=50: aa.append(A[m].mean()); bb.append(B[m].mean())
        if wm.sum()>=200: wa.append(A[wm].mean()); wb.append(B[wm].mean())
    if not aa: continue
    rows.append((n,np.mean(aa),np.mean(bb),np.mean(aa)-bA,
                 np.mean(wa) if wa else 0, np.mean(wb) if wb else 0))
for n,A,B,dA,wA,wB in sorted(rows,key=lambda r:(r[5]-r[4])):
    wl=wB-wA; tag=''
    if wl<-2: tag='★★白区发粉'
    elif wl<1: tag='★白区偏粉'
    elif wl>10: tag='白区过黄'
    print('%-20s %+6.1f %+6.1f %+6.1f %+6.1f %+6.1f  %s'%(n,A,B,wA,wB,wl,tag))
