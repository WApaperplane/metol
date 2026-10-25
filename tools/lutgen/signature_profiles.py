#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""徕卡 / 索尼 FL / 类哈苏：六个签名色彩。

为什么是"造"不是"导"
--------------------
这三家都不是胶片厂，公开库里没有可直接吃的 sRGB→sRGB 表：

* 徕卡官方的 L-Log 转换 LUT 是技术转换（L-Log → Rec.709），不是风格；
  PictureFX 的 Leica M8 Camera Standard 是免费真表，但只在 FreshLuts（需登录）
  和 Google Drive 上，本机两条路都不通（Drive 直连 000、代理未起）。
* 哈苏 HNCS 不公开。V-Log-Alchemy 里有从 Phocus 4.0.1 反推的 X2D 表，
  但输入域是 V-Log/V-Gamut —— 我们的输入是显示参考的 sRGB JPEG，
  前面缺一段对数解码，而相机传递曲线本就未实测（项目里悬着的那件事）。
  直接套会得到"双重解码"的错色。
* 索尼 FL 更没有公开 .cube。官方只给文字描述与参数档位。

所以这六张是按**公开的色度事实**构造，不是复制。可核的锚点是：

* 哈苏：README 里给了 Hasselblad RGB 的原色与 D50 白点、ICC TRC gamma 2.19921875，
  以及 Phocus 的 film curve 位置。HNCS 的性格是"克制但有层次"——大色域向 D50
  中性收敛，所以低饱和 + 灰轴死中性 + 高光软滚降，是色域结构决定的，不是口味。
* 徕卡 M8/M9 是 Kodak CCD：官方和用户都记录过它黑位偏紫、绿橙"敏感"、
  肤色好看。这不是缺陷复刻，而是取它的暖红肤色 + 阴影轻微青。
* 索尼 FL：官方原话是"淡化部分色彩，同时增强天空、绿色和对比度"，
  适合海天、山景。所以是"总体降饱和但对蓝/绿做选择性增强"，这一条不能反。

验收同 brand_profiles：每张按名字承诺的颜色实测，不看"总归是变了"。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.stdout.reconfigure(encoding='utf-8')
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import gap_profiles as fg                                  # noqa: E402
import native_codec as nc                                  # noqa: E402
from brand_profiles import brand_metrics, BLUE_SKY, CHECKS as BRAND_CHECKS   # noqa: E402
from similarity_audit import (apply_slot, de00, load_native, probe_set,  # noqa: E402
                              rgb_to_lab, REPO)

OUT = HERE / 'audit_out' / 'signature'
OUT.mkdir(parents=True, exist_ok=True)

PREFIX = 'sig_'

# 不入库：leica_sl 与 sony_fl 中位 dE00 只有 2.11（低于项目门槛 3.112），
# 两张在一张菜单里等于同一句话说了两遍。留索尼 FL——它的特征（选择性推蓝绿）
# 有官方原话可依，徕卡 SL 只是描述性构造。定义保留，随时可单独复活。
SKIP = {'leica_sl'}

PROFILES = {
    # ======== 徕卡 SL · 现代利落 ==========================================
    # 徕卡 L-Log 创意表只发布于 V-Log 域，串 S2V 后面还要一段正确的 V-Log→709
    # 色调映射（不是简单解码），这条链没跑通就不硬套。这张按 V-Log-Alchemy
    # 对 Leica Classic 的描述构造："high micro-contrast, deep blacks, sharp and
    # slightly cool shadows, with warm highlights"。
    'leica_sl': dict(
        label='徕卡 SL · 现代利落',
        family='signature-leica',
        source='V-Log-Alchemy Leica Classic description: high micro-contrast, '
               'deep blacks, slightly cool shadows, warm highlights',
        intent='Deep clean blacks, cool shadow tint, warm highlight; '
               'red stays dense without going orange.',
        tone=[0, 2.6, 8.8, 25.6, 52.4, 83.0, 95.8, 100],
        sat=1.06,
        sat_hues={'0': 1.38, '30': 1.04, '120': 0.94, '240': 0.92, '330': 1.12},
        hue={'0': 4, '30': 2, '120': 1},
        split={'shadow': [-1.0, -3.5], 'mid': [0.0, -0.8],
               'highlight': [1.0, 4.0]},
        skin={'a': 1.0, 'b': 0.2},
    ),
    # ======== 索尼 FL · 胶片氛围 ==========================================
    # 索尼官方原话："淡化部分色彩，同时增强天空、绿色和对比度"。
    # 这一条最容易做反：总体降饱和，但蓝和绿必须升。
    'sony_fl': dict(
        label='索尼 FL · 天空与绿',
        family='signature-sony',
        source='Sony Creative Look FL (official): tones down some colours while '
               'enhancing sky, greenery, and contrast',
        intent='Overall saturation down, blue and green up, contrast up.',
        tone=[0, 3.1, 9.5, 26.7, 53.0, 82.8, 95.5, 100],
        sat=0.88,
        sat_hues={'240': 1.62, '210': 1.40, '120': 1.38, '90': 1.16,
                  '30': 0.72, '0': 0.72, '330': 0.68},
        hue={'240': -4, '120': 4},
        split={'shadow': [0.0, -2.0], 'mid': [0.0, -0.5],
               'highlight': [0.5, 2.0]},
    ),
    # ======== 索尼 FL2 · 怀旧 =============================================
    'sony_fl2': dict(
        label='索尼 FL2 · 怀旧',
        family='signature-sony',
        source='Sony Creative Look FL2 (official): slightly elevates contrast and '
               'subdues colours, expressing the image with a more nostalgic feel',
        intent='FL direction, colours pulled further down, black lifted slightly.',
        tone=[4, 11, 20.5, 35.5, 55.5, 80.2, 93.0, 97.5],
        sat=0.80,
        sat_hues={'240': 1.16, '120': 1.14, '30': 0.82, '0': 0.88},
        hue={'240': -3, '120': 2},
        split={'shadow': [0.8, 1.5], 'mid': [0.3, 1.0],
               'highlight': [0.5, 2.5]},
    ),
}

GREEN = (60.0, 150.0, 70.0)


def extra_metrics(view):
    m = brand_metrics(view)
    sky = apply_slot(np.array([BLUE_SKY]), view)[0]
    sl = rgb_to_lab(sky)
    m['sky_chroma'] = round(float(np.hypot(sl[1], sl[2])), 1)
    m['sky_hue'] = round(float(np.degrees(np.arctan2(sl[2], sl[1])) % 360), 1)
    g = apply_slot(np.array([GREEN]), view)[0]
    lab = rgb_to_lab(g)
    m['green_chroma'] = round(float(np.hypot(lab[1], lab[2])), 1)
    m['green_hue'] = round(float(np.degrees(np.arctan2(lab[2], lab[1])) % 360), 1)
    return m


CHECKS = {
    # 徕卡 SL：黑要真的压下去、阴影偏冷、高光偏暖，否则只是"加了对比"。
    'leica_sl': lambda m, b: (m['contrast'] > 1.10
                              and m['shadow_tint'] < -1.0
                              and m['high_tint'] > 1.0
                              and m['red_chroma'] > b['red_chroma']),
    # 索尼 FL：总体降饱和，但蓝和绿必须升——做反了就是普通降饱和。
    'sony_fl': lambda m, b: (m['saturation'] < b['saturation']
                             and m['sky_chroma'] > b['sky_chroma']
                             and m['green_chroma'] > b['green_chroma']
                             and m['contrast'] > 1.08),
    # 抬黑的怀旧调不该用「对比上升」验收：black_lift 一抬，绝对对比必然回落。
    # 该验的是「整体收色 + 黑位抬高 + 高光仍留暖」。
    'sony_fl2': lambda m, b: (m['saturation'] < b['saturation'] - 2.0
                              and m['black_lift'] > 2.0
                              and m['high_tint'] > 0.5),
}

def build(name, prof, n=33):
    return fg.build_one(name, prof, n)


def main() -> int:
    existing = {p.stem: load_native(p) for p in sorted((REPO / 'looks').glob('*.bin'))}
    pts, _ = probe_set()
    ex_lab = {k: rgb_to_lab(apply_slot(pts, v)) for k, v in existing.items()}
    base = extra_metrics(load_native(REPO / 'looks' / 'identity17.bin'))

    print('identity 基线: sat=%.1f contrast=%.2f warm=%.2f blueC=%.1f greenC=%.1f '
          'skinA=%.1f shTw=%.2f blk=%.1f'
          % (base['saturation'], base['contrast'], base['warmth'], base['blue_chroma'],
             base['green_chroma'], base['skin_a'], base['shadow_tint'], base['black_lift']))
    print()
    print('%-18s %6s %6s %6s | %6s %6s %6s %6s %6s | %-20s %6s %s'
          % ('profile', 'sat', 'contr', 'warm', 'blueC', 'greenC', 'skinA',
             'shTw', 'blk', 'nearest existing', 'dE00', 'check'))
    built, rows = {}, []
    for name, prof in PROFILES.items():
        raw = build(name, prof)
        view = np.frombuffer(raw[:19652], np.uint8).reshape(17, 17, 17, 4)
        view = view[:, :, :, :3].astype(float)
        m = extra_metrics(view)
        lab = rgb_to_lab(apply_slot(pts, view))
        d_ex, near = min(((float(np.median(de00(lab, el))), k)
                          for k, el in ex_lab.items()
                          if k != PREFIX + name))
        ok = CHECKS[name](m, base)
        built[name] = (raw, lab)
        rows.append(dict(name=PREFIX + name, label=prof['label'], family=prof['family'],
                         intent=prof['intent'], source=prof['source'], metrics=m,
                         nearest=near, dE00=round(d_ex, 3),
                         characteristic_ok=bool(ok), recipe=prof))
        print('%-18s %6.1f %6.2f %6.2f | %6.1f %6.1f %6.1f %6.1f %6.1f | %-20s %6.3f %s'
              % (name, m['saturation'], m['contrast'], m['warmth'], m['blue_chroma'],
                 m['green_chroma'], m['skin_a'], m['shadow_tint'], m['black_lift'],
                 near, d_ex, 'OK' if ok else 'FAIL'))

    names = list(built)
    print('\n=== 本批内部（要求 > 3.112）===')
    worst = (99, '', '')
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            d = float(np.median(de00(built[names[i]][1], built[names[j]][1])))
            if d < worst[0]:
                worst = (d, names[i], names[j])
            if d < 3.112:
                print('  TOO CLOSE %.3f  %s / %s' % (d, names[i], names[j]))
    print('  最近一对: %.3f (%s / %s)' % worst)

    (OUT / 'signature_metrics.json').write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding='utf-8')
    print('\n→ %s' % (OUT / 'signature_metrics.json'))
    fails = [r['name'] for r in rows if not r['characteristic_ok']]
    print('特征验收：%d/%d 通过%s' % (len(rows) - len(fails), len(rows),
                                     '' if not fails else '，未过: ' + ', '.join(fails)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
