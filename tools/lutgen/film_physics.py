"""Physical film LUT builder for the NX500 Cr,Cb,Y slot.

This is an experimental spectral reference plus explicit grading controls.
Additive RGB/Lab grading is not intrinsically magenta. Counts of invalid YCC
lattice nodes do not measure visible errors on valid RGB inputs. The earlier
achromatic-projection exporter failed the identity test (up to 41 RGB levels).
Builds now evaluate a uniform RGB design cube and extend boundary-cell slopes
when compiling native CrCbY. Old projection helpers remain for audit reproduction.
Neutral balancing and tone/chroma controls are creative choices, not proof that
the result is a calibrated reproduction of a film stock or camera pipeline.

Usage
-----
    python film_physics.py --list
    python film_physics.py --build kodak_portra400 --neg KODAK_PORTRA_400 \
        --print KODAK_ENDURA_PREMIER --out ../looks
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from native_codec import compile_uniform_rgb, record_native

N = 17
GRID = np.array([min(i * 16, 255) for i in range(N)], dtype=np.float64)
TABLE = 19652
SLOT = 19712


# --------------------------------------------------------------------------
# geometry: Cr,Cb,Y lattice  <->  sRGB cube
# --------------------------------------------------------------------------
def ycc_to_rgb(cr, cb, y):
    """BT.601 full range, matching the codec accepted on device 2026-10-19."""
    cr = cr - 128.0
    cb = cb - 128.0
    return (y + 1.402 * cr,
            y - 0.714136 * cr - 0.344136 * cb,
            y + 1.772 * cb)


def rgb_to_ycc(r, g, b):
    return (128.0 + 0.5 * r - 0.418688 * g - 0.081312 * b,
            128.0 - 0.168736 * r - 0.331264 * g + 0.5 * b,
            0.299 * r + 0.587 * g + 0.114 * b)


def project_into_gamut(rgb, y):
    """Map an out-of-gamut node to the sRGB boundary along its own chroma ray.

    Legacy projection used by the first experimental build. It is a possible
    gamut-compression rule but is NOT an identity-preserving native exporter,
    nor does it prove monotonic interpolation. Retained for audit comparisons.

    Returns (rgb_valid, t) where t is the retained chroma fraction in [0,1].
    """
    r, g, b = rgb
    base = y
    delta = np.array([r - base, g - base, b - base], dtype=np.float64)
    t = 1.0
    for d in delta:
        if d > 1e-9:
            t = min(t, (255.0 - base) / d)
        elif d < -1e-9:
            t = min(t, (0.0 - base) / d)
    t = max(0.0, min(1.0, t))
    out = np.clip(base + t * delta, 0.0, 255.0)
    return out, t


# --------------------------------------------------------------------------
# lattice -> evaluation grid
# --------------------------------------------------------------------------
def lattice_report():
    yi, bi, ri = np.meshgrid(np.arange(N), np.arange(N), np.arange(N),
                             indexing='ij')
    r, g, b = ycc_to_rgb(GRID[ri], GRID[bi], GRID[yi])
    inside = ((r >= -1e-9) & (r <= 255 + 1e-9) &
              (g >= -1e-9) & (g <= 255 + 1e-9) &
              (b >= -1e-9) & (b <= 255 + 1e-9))
    return inside


def build_eval_grid():
    """Legacy projected lattice for reproducing the first experiment only."""
    yi, bi, ri = np.meshgrid(np.arange(N), np.arange(N), np.arange(N),
                             indexing='ij')
    y = GRID[yi]
    r, g, b = ycc_to_rgb(GRID[ri], GRID[bi], GRID[yi])
    inside = ((r >= -1e-9) & (r <= 255 + 1e-9) &
              (g >= -1e-9) & (g <= 255 + 1e-9) &
              (b >= -1e-9) & (b <= 255 + 1e-9))
    rgb = np.stack([r, g, b], axis=-1)
    kept = np.ones(inside.shape)
    for idx in np.ndindex(inside.shape):
        if not inside[idx]:
            rgb[idx], kept[idx] = project_into_gamut(rgb[idx], float(y[idx]))
    return rgb, inside, kept


# --------------------------------------------------------------------------
# film pipeline
# --------------------------------------------------------------------------
def load_film(name):
    import spectral_film_lut as sfl
    from spectral_film_lut.film_spectral import FilmSpectral
    data = next((f for f in sfl.FILM_STOCKS if f.name.lower() == name.lower()),
                None)
    if data is None:
        raise SystemExit(f'unknown film stock: {name}')
    return FilmSpectral(data)


def render(rgb255, neg_name, print_name, *, exp_comp=0.0, exp_kelvin=6500,
           tint=0.0, color_masking=None, sat_adjust=1.0, push_pull=0.0,
           white_balance=1, shadow_comp=0.0, rolloff=False):
    """Run the spectral film pipeline on 0..255 sRGB values -> 0..255 sRGB."""
    from spectral_film_lut.utils import film_conversion

    neg = load_film(neg_name)
    neg.set_color_checker()
    prt = None
    if print_name:
        prt = load_film(print_name)
        prt.set_color_checker(negative=neg)

    grid = (np.clip(rgb255, 0.0, 255.0) / 255.0).astype(np.float32)
    out = film_conversion(
        grid, neg, prt, mode='full',
        input_colorspace='sRGB',
        output_gamut='Rec. 709',
        gamma_func='sRGB',
        exp_kelvin=exp_kelvin, tint=tint, exp_comp=exp_comp,
        color_masking=color_masking if color_masking is not None
        else (1.0 if prt is not None else 0.15),
        white_balance=white_balance,
        white_clip=True,
        sat_adjust=sat_adjust,
        push_pull=push_pull,
        shadow_comp=shadow_comp,
    )
    return np.clip(out, 0.0, 1.0) * 255.0


def neutral_axis(rgb_out):
    """Output RGB along the input grey ramp (Cr=Cb=128)."""
    return rgb_out[:, 8, 8, :]


def fit_levels(rgb_out, black_pct=0.0):
    """Stretch so the neutral black and white land on 0 and 255.

    A real print is balanced with printer lights; without this the LUT range
    collapses to roughly 14..246 and the camera JPEG loses contrast.
    Applied identically to all three channels so the neutral axis keeps its
    (physically correct) tiny cool cast.
    """
    neu = neutral_axis(rgb_out)
    lo = float(neu[0].mean())
    hi = float(neu[-1].mean())
    if hi - lo < 1.0:
        return rgb_out, (lo, hi)
    scale = 255.0 / (hi - lo)
    return np.clip((rgb_out - lo) * scale, 0.0, 255.0), (lo, hi)


def to_slot(rgb_out, rgb_in):
    """Encode an sRGB output lattice into the camera Cr,Cb,Y slot bytes.

    rgb_in is the (possibly gamut-projected) input actually evaluated, so the
    inversion uses the same geometry the camera will.
    """
    data = bytearray()
    for yi in range(N):
        for bi in range(N):
            for ri in range(N):
                cr, cb, y = rgb_to_ycc(*rgb_out[yi, bi, ri])
                data.extend((int(round(min(255, max(0, cr)))),
                             int(round(min(255, max(0, cb)))),
                             int(round(min(255, max(0, y)))),
                             0))
    if len(data) != TABLE:
        raise RuntimeError(f'table size {len(data)}')
    return bytes(data) + bytes(data[-4:]) * 3 + bytes(48)


def interp_extrap(x, xp, fp):
    """np.interp with linear extrapolation outside the node range.

    np.interp clamps at the ends, which would crush every saturated colour whose
    channel value lies outside the neutral-axis range.  Extrapolating keeps the
    per-channel slope so saturated colours stay differentiable.
    """
    y = np.interp(x, xp, fp)
    lo = x < xp[0]
    hi = x > xp[-1]
    if lo.any():
        m = (fp[1] - fp[0]) / (xp[1] - xp[0])
        y[lo] = fp[0] + (x[lo] - xp[0]) * m
    if hi.any():
        m = (fp[-1] - fp[-2]) / (xp[-1] - xp[-2])
        y[hi] = fp[-1] + (x[hi] - xp[-1]) * m
    return y


LUMA = np.array([0.299, 0.587, 0.114])


def monotonic_curve(col, n=1024):
    """Envelope-monotonic dense resample of a 17-node response."""
    c = np.maximum.accumulate(np.asarray(col, dtype=np.float64))
    x = np.linspace(0.0, 255.0, len(c))
    xs = np.linspace(0.0, 255.0, n)
    ys = np.interp(xs, x, c)
    floor = (ys[-1] - ys[0]) / (n - 1) * 0.05
    for i in range(1, n):
        if ys[i] <= ys[i - 1]:
            ys[i] = ys[i - 1] + floor
    return xs, ys


def balance_neutral_axis(rgb_out, tone_strength=1.0, chroma_gain=1.0,
                         neutral_response=None):
    """Optional creative neutralisation and tone/chroma normalisation.

    Subtracting an intensity-dependent neutral cast is not the same operation
    as global printer-light balance. It deliberately removes crossover and can
    suppress a desired look's split toning. Shared low tone strengths and fixed
    endpoints can make different stocks converge. These are grading choices;
    the camera's pre-LUT transfer has not been measured.

    Returns balanced RGB and the separately evaluated neutral response.
    """
    neu = neutral_axis(rgb_out) if neutral_response is None else neutral_response
    neu_L = neu @ LUMA
    film_L = np.maximum.accumulate(neu_L)

    span = film_L[-1] - film_L[0]
    if span < 1.0:
        return rgb_out.copy(), neu, neu.copy(), film_L
    film_n = (film_L - film_L[0]) / span
    lin_n = GRID / 255.0
    tone = film_L[0] + (lin_n + tone_strength * (film_n - lin_n)) * span

    # The chain's own cast at each tone step: how far the neutral response sits
    # from its own luminance.  This is what has to be subtracted, otherwise the
    # 19-level warm shadow of the negative/paper pair survives the rebalance.
    cast = neu - neu_L[:, None]                    # (17,3)
    def apply(values):
        L_out = values @ LUMA
        step = np.interp(L_out, film_L, GRID)
        cast_pix = np.stack([np.interp(step, GRID, cast[:, k]) for k in range(3)],axis=-1)
        L_target = np.interp(L_out, film_L, tone)
        return (values-L_out[...,None]-cast_pix)*chroma_gain+L_target[...,None]
    balanced = apply(rgb_out)
    return balanced, neu, apply(neu), tone


def stretch_levels(rgb, lo=None, hi=None):
    """Map the balanced neutral black/white onto 0 and 255."""
    neu = neutral_axis(rgb)
    if lo is None:
        lo = float(neu[0].mean())
    if hi is None:
        hi = float(neu[-1].mean())
    if hi - lo < 1.0:
        return rgb, (lo, hi)
    s = 255.0 / (hi - lo)
    return np.clip((rgb - lo) * s, 0.0, 255.0), (lo, hi)


def build(neg_name, print_name, **kw):
    do_fit = kw.pop('fit_levels', True)
    tone_strength = kw.pop('tone_strength', 1.0)
    chroma_gain = kw.pop('chroma_gain', 1.0)
    n=int(kw.pop('cube_size',33))
    axis=np.linspace(0.,255.,n)
    b,g,r=np.meshgrid(axis,axis,axis,indexing='ij')
    rgb_in=np.stack((r,g,b),axis=-1)
    out = render(rgb_in, neg_name, print_name, **kw)
    gray=np.repeat(GRID[:,None],3,axis=1)
    neutral_response=render(gray.reshape(N,1,1,3),neg_name,print_name,**kw).reshape(N,3)
    levels = None
    balanced, neu_before, neu_after, tone = balance_neutral_axis(
        out, tone_strength, chroma_gain,neutral_response=neutral_response)
    meta = dict(inside_frac=float(lattice_report().mean()),
                boundary_extension='linear RGB cube boundary cells',cube_size=n,
                tone_strength=tone_strength, chroma_gain=chroma_gain,
                neutral_before=neu_before.round(1).tolist(),
                neutral_after_balance=neu_after.round(1).tolist(),
                film_tone=tone.round(1).tolist())
    if do_fit:
        balanced, levels = stretch_levels(balanced,lo=float(neu_after[0].mean()),
                                          hi=float(neu_after[-1].mean()))
        meta['levels'] = levels
    out = balanced
    slot = compile_uniform_rgb(out.reshape(-1,3).tolist(),n)
    # Preserve the historical (17,17,17,3) RGB return shape, but decode the
    # actual quantised native table instead of claiming pre-quantisation QA.
    raw=np.frombuffer(slot[:TABLE],np.uint8).reshape(N,N,N,4).astype(float)
    rr,gg,bb=ycc_to_rgb(raw[...,0],raw[...,1],raw[...,2])
    actual=np.clip(np.stack((rr,gg,bb),axis=-1),0,255)
    return slot, actual, meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--list', action='store_true')
    ap.add_argument('--build')
    ap.add_argument('--neg')
    ap.add_argument('--print')
    ap.add_argument('--out')
    ap.add_argument('--exp-comp', type=float, default=0.0)
    ap.add_argument('--sat', type=float, default=1.0)
    ap.add_argument('--no-fit', action='store_true')
    a = ap.parse_args()

    if a.list:
        import spectral_film_lut as sfl
        for f in sorted(sfl.FILM_STOCKS, key=lambda x: x.name):
            print('%-44s %-9s %-8s %s' % (f.name, f.film_type, f.stage,
                                          f.medium))
        return

    slot, out, meta = build(a.neg, a.print or None,
                            exp_comp=a.exp_comp, sat_adjust=a.sat,
                            fit_levels=not a.no_fit)
    neu = neutral_axis(out)
    print('name            ', a.build)
    print('lattice inside  ', '%.1f%%' % (100 * meta['inside_frac']))
    print('level fit       ', meta['levels'])
    print('neutral axis    ', ' '.join('%3.0f/%3.0f/%3.0f' % tuple(v)
                                       for v in neu))
    gap = np.abs(neu.max(1) - neu.min(1))
    print('neutral chroma  max %.1f  mean %.2f' % (gap.max(), gap.mean()))
    print('black point     ', np.round(neu[0], 1))
    print('white point     ', np.round(neu[-1], 1))
    if a.out:
        p = Path(a.out)
        p.mkdir(parents=True, exist_ok=True)
        target=p / (a.build + '.bin')
        target.write_bytes(slot)
        record_native(target,slot)
        print('written         ', p / (a.build + '.bin'))


if __name__ == '__main__':
    main()
