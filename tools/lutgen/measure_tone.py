#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""measure_tone.py —— 标定机内 tone response（3DLUT 的输入曲线）。

测量对象：ISP 末端、JPEG 编码器之前的 8bit 码值（约等于 JPG 像素值），
即 3DLUT 实际看到的输入。做法：均匀中性靶 + 固定光圈/ISO/WB + 逐档改快门，
取画面中心区平均码值，得到「相对曝光 EV → 码值」曲线。

输出（写到图片目录）：
  tone_samples.csv   每张样品明细
  tone_curve.svg     曲线 + 线性段拟合（浏览器直接打开）
  tone_lut.csv       0-255 码值 → 相对 EV 反查表（设计 LUT 时用）
  tone_report.txt    结论摘要

用法：
  python measure_tone.py <图片目录> [--center 0.34] [--seq --step 1.0]
  --seq 忽略 EXIF，按文件名排序推定快门（序号越大曝光越少）
"""
import sys, csv, math, argparse
from pathlib import Path

import numpy as np
from PIL import Image, ExifTags

HIGHLIGHT_LIMIT = 0.02      # clip 超过 2% 视为过曝
UNIFORM_LIMIT = 0.12        # std/mean 超过 12% 视为靶面不均


def read_exif(img):
    out = {}
    try:
        ex = img.getexif()
        for k, v in ex.items():
            out[ExifTags.TAGS.get(k, str(k))] = v
        for k, v in ex.get_ifd(0x8769).items():
            out[ExifTags.TAGS.get(k, str(k))] = v
    except Exception:
        pass
    return out


def parse_shutter(exif):
    v = exif.get('ExposureTime')
    if v is None:
        return None
    try:
        f = float(v)
        if f > 0:
            return f
    except Exception:
        pass
    try:
        num, den = v
        return float(num) / float(den)
    except Exception:
        return None


def center_stats(path, frac):
    img = Image.open(path).convert('RGB')
    w, h = img.size
    cw, ch = int(w * frac), int(h * frac)
    x0, y0 = (w - cw) // 2, (h - ch) // 2
    a = np.asarray(img.crop((x0, y0, x0 + cw, y0 + ch)), dtype=np.float64)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    y = 0.299 * r + 0.587 * g + 0.114 * b
    return dict(w=w, h=h, R=r.mean(), G=g.mean(), B=b.mean(),
                Y=y.mean(), Ymed=float(np.median(y)), Ystd=float(y.std()),
                clip=float((y >= 254).mean()), dark=float((y <= 1).mean()))


def fit_linear(evs, ys):
    """在中段（Y 在 15..245）拟合 log2(Y) = k*EV + b，返回 k,b,斜率EV范围。"""
    sel = [(e, y) for e, y in zip(evs, ys) if 15 <= y <= 245]
    if len(sel) < 3:
        sel = sorted(zip(evs, ys), key=lambda t: t[1])[2:-1] or list(zip(evs, ys))
    if len(sel) < 2:
        return None
    X = np.array([t[0] for t in sel], dtype=float)
    Yl = np.log2(np.array([max(t[1], 1e-6) for t in sel], dtype=float))
    k, b = np.polyfit(X, Yl, 1)
    resid = Yl - (k * X + b)
    return dict(k=float(k), b=float(b), gamma=1.0 / k if k else None,
                rmse=float(np.sqrt((resid ** 2).mean())),
                ev_lo=float(X.min()), ev_hi=float(X.max()), n=len(sel))


def make_svg(points, fit, path, title):
    """x=rel_ev  y=码值；自绘 SVG，无第三方依赖。"""
    W, H, ML, MR, MT, MB = 760, 420, 70, 24, 44, 56
    pw, ph = W - ML - MR, H - MT - MB
    evs = [p[0] for p in points]
    e0, e1 = min(evs), max(evs)
    if e1 - e0 < 1e-6:
        e1 = e0 + 1

    def sx(e):
        return ML + (e - e0) / (e1 - e0) * pw

    def sy(y):
        return MT + (1 - y / 255.0) * ph

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
             f'viewBox="0 0 {W} {H}" font-family="system-ui,sans-serif">',
             f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
             f'<text x="{ML}" y="24" font-size="15" font-weight="500" fill="#2C2C2A">{title}</text>']
    # 网格
    for i in range(0, 256, 51):
        y = sy(i)
        parts.append(f'<line x1="{ML}" y1="{y:.1f}" x2="{ML+pw}" y2="{y:.1f}" stroke="#E5E3DC" stroke-width="1"/>')
        parts.append(f'<text x="{ML-10}" y="{y+4:.1f}" font-size="11" fill="#888780" text-anchor="end">{i}</text>')
    for e in range(int(math.ceil(e0)), int(math.floor(e1)) + 1):
        if (e - int(math.ceil(e0))) % 2:
            continue
        x = sx(e)
        parts.append(f'<line x1="{x:.1f}" y1="{MT}" x2="{x:.1f}" y2="{MT+ph}" stroke="#F1EFE8" stroke-width="1"/>')
        parts.append(f'<text x="{x:.1f}" y="{MT+ph+18}" font-size="11" fill="#888780" text-anchor="middle">{e:+d}</text>')
    parts.append(f'<line x1="{ML}" y1="{MT}" x2="{ML}" y2="{MT+ph}" stroke="#5F5E5A" stroke-width="1"/>')
    parts.append(f'<line x1="{ML}" y1="{MT+ph}" x2="{ML+pw}" y2="{MT+ph}" stroke="#5F5E5A" stroke-width="1"/>')
    parts.append(f'<text x="{ML+pw/2}" y="{H-14}" font-size="12" fill="#5F5E5A" text-anchor="middle">相对曝光 EV（0 = 本组最长快门）</text>')
    parts.append(f'<text x="16" y="{MT+ph/2}" font-size="12" fill="#5F5E5A" text-anchor="middle" transform="rotate(-90 16 {MT+ph/2})">输出码值</text>')
    # 拟合线
    if fit:
        xs = [fit['ev_lo'], fit['ev_hi']]
        ys = [2 ** (fit['k'] * x + fit['b']) for x in xs]
        parts.append(f'<line x1="{sx(xs[0]):.1f}" y1="{sy(ys[0]):.1f}" x2="{sx(xs[1]):.1f}" y2="{sy(ys[1]):.1f}" '
                     f'stroke="#1D9E75" stroke-width="2" stroke-dasharray="6 4"/>')
    # 数据点
    for e, y in points:
        parts.append(f'<circle cx="{sx(e):.1f}" cy="{sy(min(y,255)):.1f}" r="3.5" fill="#378ADD" stroke="#185FA5" stroke-width="1"/>')
    if fit:
        parts.append(f'<text x="{ML+12}" y="{MT+18}" font-size="12" fill="#0F6E56">'
                     f'线性段 gamma≈{fit["gamma"]:.2f}  rmse={fit["rmse"]:.3f}  n={fit["n"]}</text>')
    parts.append('</svg>')
    Path(path).write_text('\n'.join(parts), encoding='utf-8')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('folder')
    ap.add_argument('--center', type=float, default=0.34)
    ap.add_argument('--seq', action='store_true')
    ap.add_argument('--step', type=float, default=1.0)
    ap.add_argument('--title', default='NX500 tone response')
    args = ap.parse_args()

    folder = Path(args.folder)
    exts = {'.jpg', '.jpeg', '.png', '.tif', '.tiff'}
    files = sorted([p for p in folder.iterdir() if p.suffix.lower() in exts])
    if not files:
        print(f'目录里没有图片: {folder}')
        return 1

    rows = []
    for i, p in enumerate(files):
        img = Image.open(p)
        exif = read_exif(img)
        rows.append(dict(file=p.name, order=i, shutter=parse_shutter(exif),
                         iso=exif.get('ISOSpeedRatings') or exif.get('ISOSpeed'),
                         fnum=exif.get('FNumber'), **center_stats(p, args.center)))

    known = [r['shutter'] for r in rows if r['shutter']]
    if args.seq or not known:
        for r in rows:
            r['rel_ev'] = r['order'] * (-args.step)
        mode = f'序号推定 {args.step:g}EV/张'
    else:
        tmax = max(known)
        for r in rows:
            r['rel_ev'] = math.log2(r['shutter'] / tmax)
        mode = 'EXIF 快门'

    rows.sort(key=lambda r: r['rel_ev'])

    with open(folder / 'tone_samples.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['file', 'order', 'shutter', 'iso', 'fnum', 'rel_ev',
                                          'R', 'G', 'B', 'Y', 'Ymed', 'Ystd', 'clip', 'dark', 'w', 'h'])
        w.writeheader()
        for r in rows:
            w.writerow({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items() if k in w.fieldnames})

    evs = [r['rel_ev'] for r in rows]
    ys = [r['Y'] for r in rows]
    fit = fit_linear(evs, ys)

    lines = [f'样本 {len(rows)} 张   EV 来源: {mode}', '']
    lines.append(f'{"file":26}{"t(s)":>9}{"relEV":>8}{"Y":>8}{"std":>7}{"clip%":>7}  判定')
    for r in rows:
        flag = []
        if r['clip'] > HIGHLIGHT_LIMIT:
            flag.append('过曝')
        if r['Y'] > 0 and r['Ystd'] / r['Y'] > UNIFORM_LIMIT:
            flag.append('不均')
        t = f"{r['shutter']:.5g}" if r['shutter'] else '-'
        lines.append(f"{r['file'][:26]:26}{t:>9}{r['rel_ev']:+8.2f}{r['Y']:8.2f}"
                     f"{r['Ystd']:7.2f}{r['clip']*100:7.1f}  {'/'.join(flag)}")

    bad = [r for r in rows if r['Y'] > 0 and r['Ystd'] / r['Y'] > UNIFORM_LIMIT]
    if bad:
        lines += ['', f'警告: {len(bad)} 张中心区不均匀（std/mean > {UNIFORM_LIMIT:.0%}），'
                      f'靶面可能有纹理/反光/阴影，这些点不要用于拟合']

    if fit:
        lines += ['', f'线性段拟合: log2(Y) = {fit["k"]:.4f}*EV + {fit["b"]:.3f}',
                  f'  等效 gamma = {fit["gamma"]:.3f}   rmse = {fit["rmse"]:.4f}   n = {fit["n"]}',
                  f'  覆盖 EV 区间 {fit["ev_lo"]:+.2f} .. {fit["ev_hi"]:+.2f}']
        k, b = fit['k'], fit['b']
        # 反查表：码值 -> EV
        ev_of = lambda code: (math.log2(code) - b) / k if code > 0 else None
        lut_rows = []
        for code in range(256):
            e = ev_of(code) if code >= 2 else None
            lut_rows.append((code, e))
        with open(folder / 'tone_lut.csv', 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['code', 'rel_ev', 'y_norm', 'in_measured_range'])
            for code, e in lut_rows:
                ok = 1 if (e is not None and fit['ev_lo'] <= e <= fit['ev_hi']) else 0
                w.writerow([code, '' if e is None else round(e, 4), round(code / 255, 4), ok])
        lines += ['', '反查表已写入 tone_lut.csv（in_measured_range=0 表示由拟合外推，勿直接采信）']

        # 肩部/趾部偏离
        devs = []
        for r in rows:
            pred = 2 ** (k * r['rel_ev'] + b)
            if pred > 3:
                devs.append((r['rel_ev'], r['Y'], pred, r['Y'] - pred))
        high = [d for d in devs if d[1] > 200]
        low = [d for d in devs if d[1] < 40]
        if high:
            worst = min(high, key=lambda d: d[3])
            lines.append(f'  肩部（码值>200）最大偏离: EV={worst[0]:+.2f} 实测{worst[1]:.1f} 线性预期{worst[2]:.1f} '
                         f'压缩{worst[2]-worst[1]:.1f}码')
        if low:
            worst = max(low, key=lambda d: d[3])
            lines.append(f'  趾部（码值<40）最大偏离: EV={worst[0]:+.2f} 实测{worst[1]:.1f} 线性预期{worst[2]:.1f} '
                         f'抬升{worst[1]-worst[2]:.1f}码')

    clipped = [r for r in rows if r['clip'] > HIGHLIGHT_LIMIT]
    usable = [r for r in rows if r['clip'] <= HIGHLIGHT_LIMIT and r['Y'] > 2]
    if usable:
        lo, hi = min(usable, key=lambda r: r['rel_ev']), max(usable, key=lambda r: r['rel_ev'])
        lines += ['', f'可用段: EV {lo["rel_ev"]:+.2f}(Y={lo["Y"]:.1f}) .. {hi["rel_ev"]:+.2f}(Y={hi["Y"]:.1f})'
                      f'  ≈ {hi["rel_ev"]-lo["rel_ev"]:.2f} EV']
    if clipped:
        c = max(clipped, key=lambda r: r['rel_ev'])
        lines.append(f'高光裁切最早出现于: {c["file"]}  EV={c["rel_ev"]:+.2f}  clip={c["clip"]*100:.1f}%')

    report = '\n'.join(lines)
    print(report)
    (folder / 'tone_report.txt').write_text(report, encoding='utf-8')
    make_svg([(r['rel_ev'], r['Y']) for r in rows], fit, folder / 'tone_curve.svg', args.title)
    print(f'\n输出: {folder}/tone_samples.csv  tone_lut.csv  tone_report.txt  tone_curve.svg')
    return 0


if __name__ == '__main__':
    sys.exit(main())
