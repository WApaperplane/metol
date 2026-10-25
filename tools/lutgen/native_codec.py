"""NX500 Cr,Cb,Y slot codec, separate from display-referred RGB designs.

BT.601 full range is the working matrix accepted by camera probes on 2026-10-19
and rechecked on 2026-10-25. It is not a measured camera colour profile.
Unlabelled historical files retain explicit legacy-RGB analysis behaviour;
known factory hashes and encoding.json declare native files. Hash mismatches
fail instead of silently reinterpreting stale metadata.
"""
import hashlib
import json
from pathlib import Path

GRID = [min(i * 16, 255) for i in range(17)]
TABLE = 19652
SLOT = 19712
NATIVE = 'CrCbY-BT601-full-v1'
LEGACY = 'legacy-RGB-grid-v1'
FACTORY = {'134909c75c58ba73104edeb68bf6ffc1',
           '69a4ac46b1c898409e201e92620a621f',
           '3ac9383743b305a10ee3e9b0a9cea2dd'}


def clamp(v):
    return max(0., min(255., v))


def rgb_to_ycc(values):
    r, g, b = (float(v) for v in values)
    return tuple(clamp(v) for v in (128+.5*r-.418688*g-.081312*b,
        128-.168736*r-.331264*g+.5*b, .299*r+.587*g+.114*b))


def ycc_to_rgb(values, *, clip=True):
    cr, cb, y = (float(v) for v in values)
    cr, cb = cr-128, cb-128
    result=(y+1.402*cr,y-.714136*cr-.344136*cb,y+1.772*cb)
    return tuple(clamp(v) for v in result) if clip else result


def sample(raw, values, *, extrapolate=False):
    axes=[]
    for v in values:
        v=float(v) if extrapolate else clamp(v)
        i=max(0,min(15, int(v//16)))
        axes.append((i,(v-GRID[i])/(GRID[i+1]-GRID[i])))
    out=[0.,0.,0.]
    for z in (0,1):
        for y in (0,1):
            for x in (0,1):
                w=1.
                for (i,f),j in zip(axes,(x,y,z)):w*=f if j else 1-f
                o=(((axes[2][0]+z)*17+axes[1][0]+y)*17+axes[0][0]+x)*4
                for c in range(3):out[c]+=raw[o+c]*w
    return tuple(out)


def slotwrap(table):
    if len(table)!=TABLE:raise ValueError('expected 4913 four-byte entries')
    return bytes(table)+bytes(table[-4:])*3+bytes(48)


def compile_rgb(raw, *, boundary='linear'):
    """Compile a known RGB design, extending its boundary-cell derivatives.

    Linear extrapolation preserves affine transforms, including identity and
    monochrome. 'clamp' reproduces the older importer for controlled comparison;
    out-of-gamut node counts alone do not establish which extension is better.
    """
    if len(raw) not in (TABLE,SLOT):raise ValueError('invalid RGB design length')
    if hashlib.md5(raw).hexdigest() in FACTORY:raise ValueError('factory table is already native')
    if boundary not in ('linear','clamp'):raise ValueError('unknown boundary extension')
    data=bytearray()
    for y in GRID:
        for cb in GRID:
            for cr in GRID:
                result=rgb_to_ycc(sample(raw,ycc_to_rgb((cr,cb,y),clip=boundary=='clamp'),
                                        extrapolate=boundary=='linear'))
                data.extend((*[int(v+.5) for v in result],0))
    return slotwrap(data)


def compile_uniform_rgb(nodes, n, *, boundary='linear'):
    """Uniform RGB cube (float values in 0..255) -> native CrCbY grid.

    No intermediate 8-bit RGB quantisation. Final quantisation is in native
    CrCbY. This is a boundary extension, not a measured camera gamut transform.
    """
    if len(nodes)!=n**3 or n<2:raise ValueError('invalid RGB cube geometry')
    if boundary not in ('linear','clamp'):raise ValueError('unknown boundary extension')
    data=bytearray()
    for y in GRID:
        for cb in GRID:
            for cr in GRID:
                rgb=ycc_to_rgb((cr,cb,y),clip=boundary=='clamp')
                axes=[]
                for value in rgb:
                    pos=value*(n-1)/255
                    i=max(0,min(n-2,int(pos//1)))
                    axes.append((i,pos-i))
                out=[0.,0.,0.]
                for dz in (0,1):
                    for dy in (0,1):
                        for dx in (0,1):
                            w=1.
                            for (_,f),step in zip(axes,(dx,dy,dz)):w*=f if step else 1-f
                            o=((axes[2][0]+dz)*n+axes[1][0]+dy)*n+axes[0][0]+dx
                            for c in range(3):out[c]+=w*nodes[o][c]
                result=rgb_to_ycc(out)
                data.extend((*[int(v+.5) for v in result],0))
    return slotwrap(data)


def space_for(path, raw=None):
    path=Path(path)
    raw=path.read_bytes() if raw is None else raw
    manifest=path.parent/'encoding.json'
    if manifest.is_file():
        row=json.loads(manifest.read_text(encoding='utf-8')).get('tables',{}).get(path.name)
        if row:
            if row['sha256']!=hashlib.sha256(raw).hexdigest():
                raise ValueError(f'{path}: encoding metadata/hash mismatch; do not guess the colour space')
            if row['space'] not in (NATIVE,LEGACY):raise ValueError('unknown LUT encoding')
            return row['space']
    return NATIVE if hashlib.md5(raw).hexdigest() in FACTORY else LEGACY


def record_native(path, raw):
    path=Path(path)
    manifest=path.parent/'encoding.json'
    meta=json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else {'version':1,'tables':{}}
    meta['tables'][path.name]={'space':NATIVE,'sha256':hashlib.sha256(raw).hexdigest()}
    temp=manifest.with_suffix('.json.tmp')
    temp.write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    temp.replace(manifest)


def sample_rgb(raw, space, values):
    if space==LEGACY:return sample(raw,values)
    if space!=NATIVE:raise ValueError('unknown LUT encoding')
    return ycc_to_rgb(sample(raw,rgb_to_ycc(values)))


def rgb_grid_view(path, raw=None):
    """Decode native nodes on the RGB probe grid for legacy RGB audit metrics."""
    path=Path(path)
    raw=path.read_bytes() if raw is None else raw
    space=space_for(path,raw)
    if space==LEGACY:return raw
    data=bytearray()
    for b in GRID:
        for g in GRID:
            for r in GRID:
                out=sample_rgb(raw,space,(r,g,b))
                data.extend((*[int(v+.5) for v in out],0))
    return slotwrap(data)
