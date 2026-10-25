#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把这批外部 LUT 并入之后，把库收敛回可用的规模。

为什么不用自动聚类：试过按项目门槛 3.112 做完整链接聚类、簇内按"名字短优先"留一张，
结果是 `mono_fp4` 顶掉 Tri-X、`fuji_160c` 顶掉 Portra 160、`cool_arctic` 顶掉 Eterna。
距离矩阵只能回答"像不像"，回答不了"哪张该活"——那个是片种知名度与命名规范的问题。
所以清单在下面逐条写死并附理由，聚类只用来检查有没有漏掉的真重复。

不删除：移到归档目录，可整批移回。

用法：python trim_plan.py [--apply]
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

HERE = Path(__file__).resolve().parent
LOOKS = HERE.parents[1] / 'looks'
ARCHIVE = Path(r'E:/NXWA/_looks_trim_20261025')
OUT = HERE / 'audit_out'

# name -> (kept_instead, median dE00 to it, reason)
TRIM = {
    # --- 同一个片种留了两份，旧命名的一份 ---
    'ektar100':        ('kodak_ektar100', 1.84, '旧命名，与 kodak_ektar100 同片种'),
    'film_portra':     ('kodak_portra400', 7.78, '早期批次，已被 web 版 Portra 400 取代'),
    'film_superia':    ('fuji_superia400', 6.92, '早期批次，已被 web 版 Superia 400 取代'),
    'film_expired':    ('film_faded', 2.58, '两张"过期片"效果只差在抬黑量'),

    # --- 人眼分辨不出的成对（JND ~2.3，全部 <1.5）---
    'fuji_3513':       ('fuji_3510', 0.94, '3513 是 3510 的高感版，色彩映射不可分'),
    'kodak_2393':      ('kodak_2383', 1.20, '2393 是 2383 的高感版，色彩映射不可分'),
    'mono_delta3200':  ('mono_hp5', 1.16, '高感黑白，曲线与 HP5 无差别（LUT 不编码颗粒）'),
    'mono_fp4':        ('mono_delta100', 1.22, '与 Delta 100 在 101 探针上不可分'),
    'style_noir':      ('mono_hard', 1.36, '泛用高反差黑白，与 mono_hard 重复'),
    'style_bleach':    ('pentax_bleach', 2.59, '与 pentax_bleach 同一手法'),
    'agfa_rsx200':     ('pentax_vibrant', 1.93, '与 pentax_vibrant 1.93、pentax_reversal 1.93，三方一点'),

    # --- v2_ 批次：同片种已有公开来源版本，留着只会让菜单出现两个近同名项 ---
    'v2_kodak_portra400':   ('kodak_portra400', 5.80, 'web 版 Portra 400 已就位'),
    'v2_fuji_velvia50':     ('fuji_velvia50', 4.62, 'web 版 Velvia 50 已就位'),
    'v2_kodak_kchrome64':   ('kodak_kchrome64', 7.27, 'web 版 Kodachrome 64 已就位'),
    'v2_fuji_classicchrome': ('fuji_classicchrome', 6.93, 'web 版 Classic Chrome 已就位'),
    'v2_ilford_hp5':        ('mono_hp5', 2.70, 'web 版 HP5 已就位'),
    'v2_kodak_gold200':     ('kodak_gold200', 2.03, '同片种重复'),
    'v2_polaroid600':       ('polaroid_600', 4.08, '同片种重复'),
    'v2_ricoh_bleach':      ('ricoh_bleach', 5.30, '同片种重复'),
    'v2_pentax_gold':       ('pentax_gold', 5.00, '同片种重复'),
    'v2_pentax_satobi':     ('pentax_satobi', 5.40, '同片种重复'),
    'v2_fuji_eterna':       ('fuji_eterna500', 4.40, '同片种重复'),

    # --- 第二批：收敛到 90 之后重算，JND(2.3) 内仍有 21 对，其中 8 张属真重复 ---
    # 其余 13 对是设计对立，不动：3510(冷)/2383(暖)、pro_neg_hi/pro_neg_std、
    # warm_gold/warm_honey/warm_rust、hp5/panf50(ISO50 超细颗粒)、kchrome64/kchrome200、
    # eterna500/pentax_satobi、pentax_vibrant/ricoh_xpro、400h/portra160。
    'fuji_fp3000b':     ('mono_trix400', 1.44, '黑白撕拉片，LUT 层面与 Tri-X 无差别'),
    'mono_tmax100':     ('mono_acros', 1.67, '同为细颗粒 100 度黑白，探针上几乎重合'),
    'fuji_160c':        ('fuji_400h', 1.72, '富士 Pro 负片三兄弟，160C 已停产'),
    'fuji_800z':        ('fuji_400h', 2.11, '同上，与 400H 差 2.11、与 160C 差 1.89'),
    'cool_arctic':      ('fuji_eterna500', 1.87, '自建冷调，与 Eterna500 同向且更弱'),
    'kodak_ultramax400': ('kodak_gold200', 1.94, '两张柯达民用负片，Gold 200 更经典'),
    'fuji_xtrans_provia': ('fuji_provia100f', 2.07, '机内 Provia 与真 Provia 100F 语义重复'),
    'polaroid_itype':   ('polaroid_600', 2.09, '两代整幅拍立得，色调差 2.09'),
}

# v2_canon_landscape 保留：品牌风光风格，库里没有别的表覆盖它。


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()

    present = [n for n in TRIM if (LOOKS / (n + '.bin')).is_file()]
    missing = sorted(set(TRIM) - set(present))
    total = len(list(LOOKS.glob('*.bin')))

    print('库 %d 张 → 归档 %d → %d 张' % (total, len(present), total - len(present)))
    if missing:
        print('清单里这些已不存在：%s' % ', '.join(missing))
    print()
    print('%-26s %-24s %6s  %s' % ('归档', '保留', 'dE00', '理由'))
    print('-' * 104)
    for name in sorted(TRIM, key=lambda k: (TRIM[k][0], k)):
        if name not in present:
            continue
        kept, d, why = TRIM[name]
        print('%-26s %-24s %6.2f  %s' % (name, kept, d, why))

    rows = [dict(name=n, kept=TRIM[n][0], dE00=TRIM[n][1], reason=TRIM[n][2]) for n in present]
    (OUT / 'trim_plan.json').write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding='utf-8')
    print('\n→ audit_out/trim_plan.json')

    if not args.apply:
        print('\n（未执行，加 --apply 才移动文件）')
        return 0

    ARCHIVE.mkdir(parents=True, exist_ok=True)
    for name in present:
        shutil.move(str(LOOKS / (name + '.bin')), str(ARCHIVE / (name + '.bin')))
    print('已移入 %s' % ARCHIVE)
    print('库现在 %d 张' % len(list(LOOKS.glob('*.bin'))))
    return 0


if __name__ == '__main__':
    sys.exit(main())
