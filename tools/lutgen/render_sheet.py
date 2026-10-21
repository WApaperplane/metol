#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用生成的 .bin 表渲染接触印相（每行一个 LUT），检验实际表效果而非设计意图。"""
import os
import struct
import zlib

BASE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(BASE))
BIN = os.path.join(REPO, 'looks')
N = 17
GRID = [16 * i for i in range(16)] + [255]


def read_lut(path):
    data = open(path, 'rb').read()
    return data[:N * N * N * 4]


def coord(v):
    """8bit → (格点索引, 小数部分)"""
    if v <= 0:
        return 0, 0.0
    if v >= 255:
        return 16, 0.0
    i = v // 16
    if i > 15:
        i = 15
    lo = 16 * i
    hi = 16 * (i + 1) if i < 15 else 255
    return i, (v - lo) / float(hi - lo)


def sample(lut, r, g, b):
    ri, rt = coord(r)
    gi, gt = coord(g)
    bi, bt = coord(b)
    out = [0.0, 0.0, 0.0]
    for db in (0, 1):
        for dg in (0, 1):
            for dr in (0, 1):
                ii = min(16, ri + dr)
                jj = min(16, gi + dg)
                kk = min(16, bi + db)
                o = ((kk * N + jj) * N + ii) * 4
                w = ((rt if dr else 1 - rt) *
                     (gt if dg else 1 - gt) *
                     (bt if db else 1 - bt))
                out[0] += lut[o] * w
                out[1] += lut[o + 1] * w
                out[2] += lut[o + 2] * w
    return [max(0, min(255, int(v + 0.5))) for v in out]


PATCHES = [
    (115, 82, 68), (194, 150, 130), (98, 122, 157), (87, 108, 67),
    (133, 128, 177), (103, 189, 170), (214, 126, 44), (80, 91, 166),
    (193, 90, 99), (94, 60, 108), (157, 188, 64), (224, 163, 46),
    (56, 61, 150), (70, 148, 73), (175, 54, 60), (231, 199, 31),
    (187, 86, 149), (8, 133, 161), (243, 243, 242), (200, 200, 200),
    (160, 160, 160), (122, 122, 121), (85, 85, 85), (52, 52, 52),
]
GRAYS = [0, 26, 51, 77, 102, 128, 153, 179, 204, 230, 255]

# 5x7 点阵数字
FONT = {
    '0': ['01110', '10001', '10011', '10101', '11001', '10001', '01110'],
    '1': ['00100', '01100', '00100', '00100', '00100', '00100', '01110'],
    '2': ['01110', '10001', '00001', '00010', '00100', '01000', '11111'],
    '3': ['11111', '00010', '00100', '00010', '00001', '10001', '01110'],
    '4': ['00010', '00110', '01010', '10010', '11111', '00010', '00010'],
    '5': ['11111', '10000', '11110', '00001', '00001', '10001', '01110'],
    '6': ['00110', '01000', '10000', '11110', '10001', '10001', '01110'],
    '7': ['11111', '00001', '00010', '00100', '01000', '01000', '01000'],
    '8': ['01110', '10001', '10001', '01110', '10001', '10001', '01110'],
    '9': ['01110', '10001', '10001', '01111', '00001', '00010', '01100'],
    ' ': ['00000'] * 7,
}


def write_png(path, w, h, rows):
    raw = b''.join(b'\x00' + bytes(r) for r in rows)

    def chunk(t, d):
        c = t + d
        return struct.pack('>I', len(d)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)

    png = b'\x89PNG\r\n\x1a\n'
    png += chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
    png += chunk(b'IDAT', zlib.compress(raw, 6))
    png += chunk(b'IEND', b'')
    open(path, 'wb').write(png)


def build_sheet(names, pw, gh, out_path):
    label_w = 22
    gap = 2
    row_h = pw
    W = label_w + len(PATCHES) * (pw + gap) + 8 + len(GRAYS) * (gh + gap)
    H = len(names) * (row_h + gap) + 6
    rows = []
    for _ in range(3):
        rows.append([24] * (W * 3))
    for idx, name in enumerate(names, 1):
        lut = read_lut(os.path.join(BIN, name + '.bin'))
        row = bytearray([24] * (W * 3))
        # 序号点阵
        s = str(idx)
        for ci, ch in enumerate(s):
            glyph = FONT.get(ch, FONT[' '])
            for gy, line in enumerate(glyph):
                for gx, bit in enumerate(line):
                    if bit == '1':
                        x = 4 + ci * 7 + gx
                        y = gy + 2
                        if 0 <= x < label_w and 0 <= y < row_h:
                            p = (y * W + x) * 3
                            row[p:p + 3] = b'\xff\xff\xff'
        x0 = label_w
        for (r, g, b) in PATCHES:
            o = sample(lut, r, g, b)
            for y in range(row_h):
                for x in range(pw):
                    p = (y * W + x0 + x) * 3
                    row[p:p + 3] = bytes(o)
            x0 += pw + gap
        x0 += 8
        for v in GRAYS:
            o = sample(lut, v, v, v)
            for y in range(row_h):
                for x in range(gh):
                    p = (y * W + x0 + x) * 3
                    row[p:p + 3] = bytes(o)
            x0 += gh + gap
        for _ in range(row_h):
            rows.append(bytes(row))
        for _ in range(gap):
            rows.append(bytes([24] * (W * 3)))
    write_png(out_path, W, len(rows), rows)
    print(f'{out_path}  {W}x{len(rows)}  {len(names)} 个 LUT')


def main():
    import json
    names = sorted(open(os.path.join(BASE, 'films.json'), encoding='utf-8').read() and [k for k in json.load(open(os.path.join(BASE,'films.json'),encoding='utf-8')) if not k.startswith('_')])
    groups = {
        'fuji': [n for n in names if n.startswith('fuji_')],
        'kodak': [n for n in names if n.startswith('kodak_')],
        'rest': [n for n in names if not n.startswith(('fuji_', 'kodak_'))],
    }
    for g, ns in groups.items():
        if ns:
            build_sheet(ns, 18, 11, os.path.join(BASE, f'sheet_{g}.png'))
            print('  ', ', '.join(f'{i+1}={n}' for i, n in enumerate(ns)))


if __name__ == '__main__':
    main()
