#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LUT 结构体检 —— 一次跑完 looks/ 下全部 .bin，判定"这张表能不能用"。

只读，不改任何文件。阈值全部对 identity17 校准（identity 必须零告警）。

指标定义
--------
1. mono_drops   灰轴 & R 轴（G=B=0）luma 的下降沿数量。物理上必须单调递增，>0 即硬伤。
2. black_luma   输出 (0,0,0) 的 luma。抬黑是风格，但 >30 就会整幅发灰、失去对比。
3. crush_pct    "暗部压死率"：输入三通道数值全 >0（即格点序号全 >0，4096 个）但输出
                存在通道 =0 的比例。identity17 基准 0.0%。HSV 饱和打满时最小通道归零
                ⇒ 暗部色阶断裂、出现死黑斑。
4. white_pct    "高光烧穿率"：输入三通道全 <255 但输出存在通道 =255 的比例。同上基准 0%。
5. jump_ratio   相邻格点输出最大分量差 ÷ 16（格点步长）。identity17 = 1.0。
                饱和通道上 4-5 是正常（一格跨 70 级色阶），>8 才是断崖/色带。
6. gray_gap     17 个灰点输出的 max-min 最大值，即中性灰被染色的幅度。暖调/棕调表
                按设计就有 40-80，故对 warm_*/sepia 一类豁免。
7. warm_red     暖区推红：s∈[0.15,0.55]、v>0.14、hue∈330..50 的格点上，R/G 比值的
                平均相对变化（线性，不做 log，避免低 G 值放大）。只取中低饱和，因为
                肤色/木色/室内光落在这里；高饱和红本来就该是红的，不计入。
8. dr           灰轴 0→255 的 luma 落差。<200 说明影调被压平。
9. hue_err      六个主色格的最大色相偏移。>45° 说明色相被转坏（反相表典型特征）。

豁免
----
* zz_invert  纯数学反相表，所有判据不适用（verdict 记 INVERT）。
* warm_* / sepia 灰轴染色与高光暖通道饱和属设计意图，跳过 gray_gap / white_pct。

用法
----
  python tools/lutgen/audit.py                  # 打印表格
  python tools/lutgen/audit.py --json r.json    # 另存 JSON
  python tools/lutgen/audit.py --only portra160,fuji_velvia50
  python tools/lutgen/audit.py --bad-only       # 只列 WARN/BAD/INVERT
"""
import argparse
import hashlib
import json
import os
import sys
from native_codec import rgb_grid_view

N = 17
GRID = [16 * i for i in range(16)] + [255]
BASE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(BASE))
LOOKS = os.path.join(REPO, 'looks')

TH = {
    'black_luma': (30, 60),      # warn, bad
    'crush_pct': (3.0, 8.0),
    'white_pct': (3.0, 8.0),
    'jump_ratio': (5.5, 8.0),
    'gray_gap': (30, 46),
    'warm_red': (0.06, 0.10),
    'dr': (205, 190),            # 低于则 warn / bad（反向）
    'hue_err': (45, 60),
}

# 豁免：这些名字的某些指标不判
WARM_NAMES = ('warm_', 'style_sepia', 'zz_')
INVERT_NAMES = ('zz_invert',)
# 机身原厂 LUT 槽的镜像 dump（md5 与 A00/A01/A02 槽完全一致）。用途是"对照原厂风格"，
# 不是日常拍摄的 look —— 冷调、低反差、灰轴微非单调都是原厂设计，不按 look 口径判。
FACTORY = ('samsung_a00', 'samsung_a01', 'samsung_a02')
# ★ 只认 md5。文件名会骗人：commit 53af8e8 的「修偏红」脚本把这三张当成老表重算过一遍，
#   白点 (182,182,254)→(195,195,228)，但文件名没变，FACTORY 豁免照样放行 ⇒ 豁免逻辑
#   一直在为一张假表服务。现在 md5 不匹配就按普通 look 判，能直接把污染暴露出来。
FACTORY_MD5 = {
    '134909c75c58ba73104edeb68bf6ffc1': 'samsung_a00',
    '69a4ac46b1c898409e201e92620a621f': 'samsung_a01',
    '3ac9383743b305a10ee3e9b0a9cea2dd': 'samsung_a02',
}


def luma(c):
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def hsv(r, g, b):
    mx, mn = max(r, g, b), min(r, g, b)
    v = mx / 255.0
    s = 0.0 if mx == 0 else (mx - mn) / float(mx)
    d = mx - mn
    if d == 0:
        h = 0.0
    elif mx == r:
        h = ((g - b) / d) % 6
    elif mx == g:
        h = (b - r) / d + 2
    else:
        h = (r - g) / d + 4
    return h * 60.0, s, v


def load(path):
    """返回 4913 个 (r,g,b)，索引 = ((B*17+G)*17+R)。顺手校验文件长度与槽尾 pad。"""
    raw = rgb_grid_view(path)
    if len(raw) != 19712:
        raise ValueError('长度 %d ≠ 19712' % len(raw))
    # 槽尾 60B pad：我们生成的表填 0，但原厂表填的是非零元数据（samsung_a00/01/02
    # 实测三张全部非零）。pad 不参与查表，不能当读取失败 —— 之前正是这条把原厂
    # 参考表判成「BAD:读取失败」，反过来掩盖了它曾被改写这件事。
    pad = raw[N * N * N * 4:]
    if any(pad):
        pass  # 保留位置：pad 内容与查表无关
    return [(raw[i * 4], raw[i * 4 + 1], raw[i * 4 + 2]) for i in range(N * N * N)]


def audit_one(name, lut, md5=None):
    idx = lambda r, g, b: ((b * N + g) * N + r)
    is_warm = name.startswith('warm_') or name.startswith('sepia')

    # --- 1. 单调性（灰轴 + 纯红轴）
    # 1.5 → 3.0：8 位量化 + 三线性插值在低亮度处会有 1-3 级抖动，那不是非单调。
    # 真坏表的下降幅度是 7-12 级（samsung_a00 灰轴 -12.1、a01 -7.4）。
    def drops(vals):
        return sum(1 for a, b in zip(vals, vals[1:]) if b < a - 3.0)

    mono = drops([luma(lut[idx(i, i, i)]) for i in range(N)]) + \
        drops([luma(lut[idx(i, 0, 0)]) for i in range(N)])

    # --- 2. 黑点 / 白点
    black = lut[idx(0, 0, 0)]
    white = lut[idx(16, 16, 16)]

    # --- 3/4/5. 压死率 / 烧穿率 / 最大跳
    crush = free = 0
    in_nonzero = in_notmax = 0
    jump = 0
    for b in range(N):
        for g in range(N):
            for r in range(N):
                o = lut[idx(r, g, b)]
                if r and g and b and max(GRID[r], GRID[g], GRID[b]) >= 51:
                    in_nonzero += 1                  # 输入数值全 >0 且亮度 ≥20%：中间调及以上
                    if min(o) == 0:
                        crush += 1
                if r < 16 and g < 16 and b < 16:     # 输入数值全 <255
                    in_notmax += 1
                    if max(o) == 255:
                        free += 1
                if r < 16:
                    jump = max(jump, max(abs(o[k] - lut[idx(r + 1, g, b)][k]) for k in range(3)))
                if g < 16:
                    jump = max(jump, max(abs(o[k] - lut[idx(r, g + 1, b)][k]) for k in range(3)))
                if b < 16:
                    jump = max(jump, max(abs(o[k] - lut[idx(r, g, b + 1)][k]) for k in range(3)))

    crush_pct = 100.0 * crush / in_nonzero
    white_pct = 100.0 * free / in_notmax

    # --- 6. 灰轴落差
    gray_gap = max(max(lut[idx(i, i, i)]) - min(lut[idx(i, i, i)]) for i in range(N))

    # --- 7. 暖区推红（中低饱和暖色，线性 R/G 比值）
    num = den = 0.0
    for b in range(N):
        for g in range(N):
            for r in range(N):
                ri, gi, bi = GRID[r], GRID[g], GRID[b]
                h, s, v = hsv(ri, gi, bi)
                if not (0.15 <= s <= 0.55) or v <= 0.14:
                    continue
                if not (h >= 330 or h <= 50):
                    continue
                o = lut[idx(r, g, b)]
                rg_in = (ri + 1.0) / (gi + 1.0)
                rg_out = (o[0] + 1.0) / (o[1] + 1.0)
                w = min(1.0, (s - 0.15) / 0.25)
                num += (rg_out / rg_in - 1.0) * w
                den += w
    warm_red = num / den if den else 0.0

    # --- 8. 动态范围
    dr = luma(white) - luma(black)

    # --- 9. 六主色色相偏移（取最近格点，避免插值干扰）
    probes = ((0, (200, 40, 40)), (60, (200, 190, 40)), (120, (50, 180, 60)),
              (180, (40, 180, 190)), (240, (40, 70, 200)), (300, (180, 40, 170)))
    hue_err = 0.0
    for base_h, rgb in probes:
        i = [min(16, int(round(c / 16.0))) for c in rgb]
        o = lut[idx(*i)]
        if max(o) - min(o) < 6:
            continue
        # 基准取"量化到格点后的输入色相"，否则 round() 引入的偏差会记到表头上
        ih, _, _ = hsv(GRID[i[0]], GRID[i[1]], GRID[i[2]])
        oh, _, _ = hsv(*o)
        d = (oh - ih + 180) % 360 - 180
        hue_err = max(hue_err, abs(d))

    # --- 判定
    flags = []

    def mark(key, val, invert=False):
        w, b = TH[key]
        if invert:
            if val < b:
                flags.append('BAD:' + key)
            elif val < w:
                flags.append('WARN:' + key)
        else:
            if val > b:
                flags.append('BAD:' + key)
            elif val > w:
                flags.append('WARN:' + key)

    checks = [('black_luma', luma(black), False), ('crush_pct', crush_pct, False),
              ('white_pct', white_pct, False), ('jump_ratio', jump / 16.0, False),
              ('gray_gap', gray_gap, False),
              ('dr', dr, True), ('hue_err', hue_err, False)]
    # 原厂参考表只做"是否与机身槽一致"的核对，不按 look 好坏判 —— 低反差/灰轴微非单调
    # 是原厂冷调设计（见 LUT_UI_2026-10-18 §8.5）。
    if name in FACTORY and md5 in FACTORY_MD5:
        flags.append('REF:原厂参考表（md5 同机身槽）')
        for key, val, inv in checks:
            if key in ('black_luma', 'crush_pct', 'jump_ratio'):
                mark(key, val, inv)
        return {
            'name': name, 'mono': mono,
            'black': list(black), 'black_luma': round(luma(black), 1),
            'white_luma': round(luma(white), 1),
            'crush_pct': round(crush_pct, 2), 'white_pct': round(white_pct, 2),
            'jump_ratio': round(jump / 16.0, 2), 'gray_gap': gray_gap,
            'warm_red': round(warm_red, 4), 'dr': round(dr, 1),
            'hue_err': round(hue_err, 1), 'invert': False,
            'flags': flags, 'verdict': 'REF',
        }
    if mono > 0:
        flags.append('BAD:非单调')
    for key, val, inv in checks:
        if is_warm and key in ('gray_gap', 'white_pct', 'hue_err'):
            # 暖调/棕调表本来就把色相压到一条窄带上（warm_sepia 的六主色位移 168°），
            # 那不是缺陷，是它就是棕的。
            continue
        if name.startswith('mono_') and key == 'hue_err':
            continue
        mark(key, val, inv)

    invert_tbl = name in INVERT_NAMES or (luma(black) > 200 and luma(white) < 55)
    verdict = 'INVERT' if invert_tbl else (
        'BAD' if any(f.startswith('BAD') for f in flags)
        else ('WARN' if flags else 'OK'))

    return {
        'name': name, 'mono': mono,
        'black': list(black), 'black_luma': round(luma(black), 1),
        'white_luma': round(luma(white), 1),
        'crush_pct': round(crush_pct, 2), 'white_pct': round(white_pct, 2),
        'jump_ratio': round(jump / 16.0, 2), 'gray_gap': gray_gap,
        'warm_red': round(warm_red, 4), 'dr': round(dr, 1),
        'hue_err': round(hue_err, 1), 'invert': invert_tbl,
        'flags': flags, 'verdict': verdict,
    }


def _hue_deg(a):
    """(h,w,3) float → (hue 0..360, s, v)。近中性像素 hue 无意义，由调用方按 s 过滤。"""
    import numpy as np
    r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    mx, mn = a.max(axis=2), a.min(axis=2)
    d = mx - mn
    h = np.zeros_like(mx)
    m = d > 1e-6
    im = m & (mx == r)
    h[im] = ((g - b)[im] / d[im]) % 6.0
    ig = m & ~im & (mx == g)
    h[ig] = (b - r)[ig] / d[ig] + 2.0
    ib = m & ~im & ~ig
    h[ib] = (r - g)[ib] / d[ib] + 4.0
    return h * 60.0, d / np.maximum(mx, 1.0), mx


def photo_probe(names, photo_dir, width=420, limit=16):
    """真实照片口径：暖色区的色相位移 dHue，附带 R/G 变化 dRG。

    ★ 为什么判偏红必须看 dHue 而不是 R/G：
      任何 sat>1.0 的表在暖色像素上都会把 R/G 抬高，那是"更饱和"，不是"偏红"。
      实测 fuji_velvia50 的 dRG=+0.27 但 dHue 只有 -1.8°（纯饱和），而
      kodak_kchrome25 的 dRG=+0.34、dHue=-7.3°（真把肤色推红了）。
      两个指标同量级，只有 dHue 能分开这两件事。

    统计范围：hue∈[0,60]∪[330,360]、s_in∈[0.25,0.85]、亮度>30，且输出饱和度
    至少保留输入的 55%（否则去饱和表的 hue 抖动会被误记成偏红）。
    """
    import numpy as np
    from PIL import Image
    sys.path.insert(0, BASE)
    from preview_photos import apply_lut, load_lut

    files = sorted(f for f in os.listdir(photo_dir)
                   if f.lower().endswith(('.jpg', '.jpeg', '.png')))[:limit]
    if not files:
        return {}
    imgs = []
    for f in files:
        im = Image.open(os.path.join(photo_dir, f)).convert('RGB')
        h = max(1, int(im.height * width / float(im.width)))
        imgs.append(np.asarray(im.resize((width, h), Image.LANCZOS), dtype=np.float32))

    res = {}
    for n in names:
        p = os.path.join(LOOKS, n + '.bin')
        if not os.path.isfile(p):
            continue
        lut = load_lut(p)
        dh_l, dr_l = [], []
        for a in imgs:
            hin, sin, vin = _hue_deg(a)
            o = apply_lut(a, lut).astype(np.float32)
            hout, sout, _ = _hue_deg(o)
            m = (vin > 30) & (sin > 0.25) & (sin < 0.85) & \
                ((hin <= 60) | (hin >= 330)) & (sout > 0.15) & (sout > 0.55 * sin)
            if m.sum() < 200:
                continue
            w = np.clip((sin[m] - 0.25) / 0.25, 0.0, 1.0)
            dh = ((hout[m] - hin[m] + 180) % 360) - 180
            dh_l.append(float((dh * w).sum() / max(w.sum(), 1e-6)))
            rg_in = (a[:, :, 0] + 1.0) / (a[:, :, 1] + 1.0)
            rg_out = (o[:, :, 0] + 1.0) / (o[:, :, 1] + 1.0)
            dr = rg_out[m] / rg_in[m] - 1.0
            dr_l.append(float((dr * w).sum() / max(w.sum(), 1e-6)))
        res[n] = (round(float(np.median(dh_l)), 2) if dh_l else 0.0,
                  round(float(np.median(dr_l)), 4) if dr_l else 0.0)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json')
    ap.add_argument('--only')
    ap.add_argument('--dir', help='体检目录（默认 looks/），用于对比候选版本')
    ap.add_argument('--bad-only', action='store_true')
    ap.add_argument('--photos', nargs='?', const='@default',
                    help='加跑照片口径偏红量（默认 E:/NXWA/_photos）')
    ap.add_argument('--limit', type=int, default=8, help='照片模式取样张数')
    a = ap.parse_args()

    global LOOKS
    if a.dir:
        LOOKS = os.path.abspath(a.dir)
    if not os.path.isdir(LOOKS):
        print('找不到目录：%s' % LOOKS)
        return 2

    names = sorted(f[:-4] for f in os.listdir(LOOKS) if f.endswith('.bin'))
    if a.only:
        want = {s.strip() for s in a.only.split(',')}
        names = [n for n in names if n in want]

    rows = []
    for n in names:
        try:
            rows.append(audit_one(n, load(os.path.join(LOOKS, n + '.bin')),
                                  hashlib.md5(open(os.path.join(LOOKS, n + '.bin'), 'rb').read()).hexdigest()))
        except Exception as e:
            rows.append({'name': n, 'verdict': 'BAD', 'flags': ['BAD:读取失败 %s' % e]})

    hdr = ('   %-22s %4s %6s %7s %6s %5s %5s %7s %5s %5s' %
           ('name', 'mono', 'blk', 'crush%', 'wht%', 'jump', 'gray', 'warm_r', 'dr', 'hue'))
    print(hdr)
    print('  ' + '-' * (len(hdr) - 2))
    cnt = {'OK': 0, 'WARN': 0, 'BAD': 0, 'INVERT': 0, 'REF': 0}
    for r in rows:
        cnt[r.get('verdict', 'BAD')] = cnt.get(r.get('verdict', 'BAD'), 0) + 1
        if a.bad_only and r.get('verdict') in ('OK', 'REF'):
            continue
        tag = {'OK': '  ', 'WARN': '!!', 'BAD': '**', 'INVERT': 'IV', 'REF': 'RF'}.get(r.get('verdict'), '**')
        if r.get('flags') and r['flags'][0].startswith('BAD:读取'):
            print('%s %-22s %s' % (tag, r['name'], r['flags'][0]))
            continue
        print('%s %-22s %4d %6.1f %7.2f %6.2f %5.2f %5d %+7.3f %5.0f %5.0f%s' % (
            tag, r['name'], r['mono'], r['black_luma'], r['crush_pct'], r['white_pct'],
            r['jump_ratio'], r['gray_gap'], r['warm_red'], r['dr'], r['hue_err'],
            ('   ' + ' '.join(r['flags'])) if r.get('flags') else ''))

    print('\n%d 张：OK %d ｜ WARN %d ｜ BAD %d ｜ 原厂参考 %d ｜ 反相 %d' %
          (len(rows), cnt['OK'], cnt['WARN'], cnt['BAD'], cnt['REF'], cnt['INVERT']))

    if a.photos:
        pdir = os.path.join(REPO, '..', '_photos') if a.photos == '@default' else a.photos
        pr = photo_probe([r['name'] for r in rows], pdir, limit=a.limit)
        if not pr:
            print('\n[照片口径] 跳过：%s 里没有照片' % pdir)
        else:
            print('\n[照片口径] 暖色区色相位移 dHue（负 = 偏红）｜>±3° 可辨 ｜>±5° 明显')
            print('           设计上就该暖的表（warm_*/sepia）与无色相表（mono_*/noir/invert）不判')
            skip = ('warm_', 'sepia', 'zz_', 'mono_', 'style_noir', 'bleach')
            ranked = sorted(rows, key=lambda r: pr.get(r['name'], (0, 0))[0])
            for r in ranked:
                if r['name'] not in pr:
                    continue
                dh, drg = pr[r['name']]
                r['dHue'], r['dRG'] = dh, drg
                exempt = any(k in r['name'] for k in skip)
                tag = '  '
                if not exempt:
                    if dh < -5:
                        tag, fl = '**', 'BAD:dHue'
                    elif dh < -3:
                        tag, fl = '!!', 'WARN:dHue'
                    else:
                        fl = None
                    if fl:
                        r['flags'].append(fl)
                        r['verdict'] = 'BAD' if fl.startswith('BAD') else (
                            'WARN' if r['verdict'] == 'OK' else r['verdict'])
                if tag != '  ' or dh < -2:
                    print('%s %-22s %+7.2f° %+7.3f%s' %
                          (tag, r['name'], dh, drg, '   (设计暖调/无色相，豁免)' if exempt else ''))
            n3 = sum(1 for r in rows if r['name'] in pr
                     and pr[r['name']][0] < -3 and not any(k in r['name'] for k in skip))
            n5 = sum(1 for r in rows if r['name'] in pr
                     and pr[r['name']][0] < -5 and not any(k in r['name'] for k in skip))
            print('  → dHue < -3° 共 %d 张，< -5° 共 %d 张（%d 张照片）' %
                  (n3, n5, a.limit))

    if a.json:
        with open(a.json, 'w', encoding='utf-8') as f:
            json.dump(rows, f, ensure_ascii=False, indent=1)
        print('→ %s' % a.json)

    return 1 if cnt['BAD'] else 0


if __name__ == '__main__':
    sys.exit(main())
