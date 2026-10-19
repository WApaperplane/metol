#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-10-19: the RGB table semantics below are a legacy diagnostic model.
# Camera import must use lutpipe/cube_to_crcb_y.py or the corrected cube2lut.arm;
# native slots use Cr,Cb,Y. Do not infer native colour correctness from this
# module's RGB geometry/round-trip tests. See LUT_CRCBY_FIX_2026-10-19.md.
"""nx3dlut.py —— NX500 硬件 3D LUT 原生编解码 + .cube 导入/导出

★ 背景（见 docs/current/3DLUT_TABLE_FORMAT_2026-10-08.md）
  硬件原生表格式（2026-10-08 离线解出，已多表自证）：
      4913 项 × 4B = 19652B ；项 = {R, G, B, pad=0}
      索引 = ((B*17 + G)*17 + R) * 4        ← R 变化最快
      槽步长 = 0x4D00 = 19712（表 19652 + 填充 60B）
      填充  = 末项×3（12B）+ 48×0x00
  ★ 硬件采样格点 **不是均匀的**：level i 对应 8-bit 输入值
      G_i = min(i*16, 255)  ⇒  {0,16,32,…,240,255}
    证据：镜像内置 identity 表（VA 0x80897BC0）三轴 ramp 恰为上式。
  ⇒ 因此「N³ 规范 cube → 17³ 硬件表」**必须按 G_i 采样**，
    用 trilinear 插值，不能直接搬（否则 level 15 会得 239 而非 240）。

★ 与旧工具的差别
  test_server/filmsim/cube2nx17.py 产出 29478B（4913×6，u16/通道）—— 那是**被否掉的旧格式**。
  本工具产出 19652B（4B/项）。旧 .bin 仍可读入（自动识别并转换）。

用法
  python test_server/isp/nx3dlut.py import  in.cube [out.bin] [--slot] [--order auto|rgb|rbg|...] [--verify ref.bin]
  python test_server/isp/nx3dlut.py export  in.bin  out.cube [--n 17|33] [--title T]
  python test_server/isp/nx3dlut.py identity out.bin [--slot]
  python test_server/isp/nx3dlut.py info    in.{cube,bin}
  python test_server/isp/nx3dlut.py preview in.{cube,bin} out.ppm|out.png [--n 33]
  python test_server/isp/nx3dlut.py patch   in.{cube,bin} p7_full.bin out.bin --va 0x80892EC0
  python test_server/isp/nx3dlut.py selftest            # 对内置表做字节级回归

axis order：.cube 规范要求 R 最快（rgb）。本仓 _luttest/identity33.cube 实为 bgr，
  默认 --order auto 会按可分离性自动判定并纠正；判错时用 --order 强制。

纪律：本工具**只产文件，不碰相机**。patch 产物默认视同 DO-NOT-FLASH，除非另行验收。
"""
import os
import struct
import sys

# ---------------------------------------------------------------- 常量

N16 = 17                       # 硬件每轴电平数
NENT = N16 ** 3                 # 4913
ITEM = 4                       # 每项字节数 {R,G,B,pad}
TABLE_LEN = NENT * ITEM         # 19652
SLOT_LEN = 0x4D00              # 19712
TAIL_LEN = SLOT_LEN - TABLE_LEN  # 60
OLD_ITEM = 6                   # 旧格式：u16×3
OLD_LEN = NENT * OLD_ITEM       # 29478

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
BUILTIN_DIR = os.path.join(ROOT, "raw8", "p7", "lut_format")


# ---------------------------------------------------------------- 格点

def hw_grid_u8():
    """硬件 17 个采样电平（8-bit）。= {0,16,32,…,240,255}"""
    return [min(i * 16, 255) for i in range(N16)]


def hw_grid_f():
    """同上，归一化到 [0,1]。"""
    return [v / 255.0 for v in hw_grid_u8()]


def uniform_grid_f(n):
    """规范 cube 的均匀格点 i/(n-1)，i=0..n-1。"""
    if n < 2:
        return [0.0]
    return [i / float(n - 1) for i in range(n)]


def to_u8(v):
    """[0,1] float → 8-bit，round-half-up + clamp。"""
    if v <= 0.0:
        return 0
    if v >= 1.0:
        return 255
    return int(v * 255.0 + 0.5)


# ---------------------------------------------------------------- cube 解析

class Cube(object):
    def __init__(self, n, nodes, title="", dmin=(0.0, 0.0, 0.0),
                 dmax=(1.0, 1.0, 1.0), kind="3D", order="rgb"):
        self.n = n                # 每轴节点数
        self.nodes = nodes        # [(r,g,b)]，长度 n³，索引 r + g*n + b*n²（R 最快）
        self.title = title
        self.dmin = dmin
        self.dmax = dmax
        self.kind = kind          # "3D" / "1D"
        self.order = order        # 原始文件的轴序（fastest→slowest），已归一到 rgb


ORDER_SPEC = "rgb"                # .cube 规范：R 变化最快


def remap_order(nodes, n, order):
    """把「文件轴序 = order（fastest→slowest）」重排为规范 R-最快索引。"""
    if order == ORDER_SPEC:
        return nodes
    pos = {ax: i for i, ax in enumerate(order)}
    out = [None] * (n ** 3)
    for r in range(n):
        for g in range(n):
            for b in range(n):
                val = {"r": r, "g": g, "b": b}
                k = sum(val[ax] * (n ** i) for ax, i in pos.items())
                out[r + g * n + b * n * n] = nodes[k]
    return out


def _sep_score(nodes, n):
    """可分离性打分（越低越好）：通道 c 应只依赖第 c 个轴。"""
    tot = 0.0
    for c in range(3):
        for i in range(n):
            lo, hi = 2.0, -1.0
            for j in range(n):
                for k in range(n):
                    if c == 0:
                        v = nodes[i + j * n + k * n * n][c]
                    elif c == 1:
                        v = nodes[j + i * n + k * n * n][c]
                    else:
                        v = nodes[j + k * n + i * n * n][c]
                    lo = min(lo, v); hi = max(hi, v)
            tot += (hi - lo)
    return tot


def detect_order(nodes, n):
    """推断轴序。返回 (best_order, best_score, spec_score)。"""
    import itertools
    best, bs = ORDER_SPEC, None
    spec = None
    for perm in itertools.permutations("rgb"):
        o = "".join(perm)
        s = _sep_score(remap_order(nodes, n, o), n)
        if o == ORDER_SPEC:
            spec = s
        if bs is None or s < bs:
            best, bs = o, s
    return best, bs, spec


def parse_cube(path, order="auto"):
    """解析 Adobe .cube。支持 LUT_3D_SIZE / LUT_1D_SIZE / DOMAIN_MIN/MAX / TITLE / 注释。

    order：轴序（fastest→slowest）。"auto" = 按可分离性自动判定；
           规范文件为 "rgb"。非规范文件（如本仓 _luttest/identity33.cube 实为 "bgr"）会被自动纠正。
    """
    n3 = n1 = 0
    title = ""
    dmin = [0.0, 0.0, 0.0]
    dmax = [1.0, 1.0, 1.0]
    vals = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            s = raw.strip()
            if not s or s.startswith("#"):
                continue
            u = s.upper()
            if u.startswith("TITLE"):
                title = s[len("TITLE"):].strip().strip('"')
                continue
            if u.startswith("LUT_3D_SIZE"):
                n3 = int(s.split()[1])
                continue
            if u.startswith("LUT_1D_SIZE"):
                n1 = int(s.split()[1])
                continue
            if u.startswith("DOMAIN_MIN"):
                t = s.split()
                dmin = [float(t[1]), float(t[2]), float(t[3])]
                continue
            if u.startswith("DOMAIN_MAX"):
                t = s.split()
                dmax = [float(t[1]), float(t[2]), float(t[3])]
                continue
            if u.startswith("LUT_") or s[0].isalpha():
                continue
            t = s.split()
            if len(t) < 3:
                continue
            try:
                vals.append((float(t[0]), float(t[1]), float(t[2])))
            except ValueError:
                continue

    if n3 == 0 and n1 == 0:
        raise ValueError("找不到 LUT_3D_SIZE / LUT_1D_SIZE")

    if n3:
        if len(vals) != n3 ** 3:
            raise ValueError("节点数不符：读到 %d，期望 %d (%d³)"
                             % (len(vals), n3 ** 3, n3))
        used = ORDER_SPEC
        if order == "auto":
            used, _, _ = detect_order(vals, n3)
        elif order != ORDER_SPEC:
            used = order
        if used != ORDER_SPEC:
            vals = remap_order(vals, n3, used)
        return Cube(n3, vals, title, dmin, dmax, "3D", used)

    # 1D → 展开成 3D 逐通道曲线（每通道独立）
    if len(vals) != n1:
        raise ValueError("1D 节点数不符：读到 %d，期望 %d" % (len(vals), n1))
    nodes = []
    for b in range(n1):
        for g in range(n1):
            for r in range(n1):
                nodes.append((vals[r][0], vals[g][1], vals[b][2]))
    return Cube(n1, nodes, title, dmin, dmax, "1D", ORDER_SPEC)


# ---------------------------------------------------------------- 原生表 IO

def norm_nodes(cube):
    """把 cube 节点从 [dmin,dmax] 归一化到 [0,1]。"""
    lo, hi = cube.dmin, cube.dmax
    span = [(hi[c] - lo[c]) or 1.0 for c in range(3)]
    return [tuple(min(1.0, max(0.0, (v[c] - lo[c]) / span[c])) for c in range(3))
            for v in cube.nodes]


def sample_trilinear(nodes, n, pos):
    """在 n³ 节点表上按归一化位置 pos=(pr,pg,pb)∈[0,1] 做三线性插值。"""
    pr, pg, pb = pos
    f = lambda v: 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)
    x = f(pr) * (n - 1)
    y = f(pg) * (n - 1)
    z = f(pb) * (n - 1)
    x0 = int(x); y0 = int(y); z0 = int(z)
    x1 = min(x0 + 1, n - 1); y1 = min(y0 + 1, n - 1); z1 = min(z0 + 1, n - 1)
    fx = x - x0; fy = y - y0; fz = z - z0

    def at(i, j, k):
        return nodes[i + j * n + k * n * n]

    out = [0.0, 0.0, 0.0]
    for c in range(3):
        c000 = at(x0, y0, z0)[c]; c100 = at(x1, y0, z0)[c]
        c010 = at(x0, y1, z0)[c]; c110 = at(x1, y1, z0)[c]
        c001 = at(x0, y0, z1)[c]; c101 = at(x1, y0, z1)[c]
        c011 = at(x0, y1, z1)[c]; c111 = at(x1, y1, z1)[c]
        c00 = c000 + (c100 - c000) * fx
        c01 = c001 + (c101 - c001) * fx
        c10 = c010 + (c110 - c010) * fx
        c11 = c011 + (c111 - c011) * fx
        c0 = c00 + (c10 - c00) * fy
        c1 = c01 + (c11 - c01) * fy
        out[c] = c0 + (c1 - c0) * fz
    return tuple(out)


def cube_to_native(cube, grid=None):
    """规范 cube → 19652B 原生表。

    grid：17 个归一化输入位置；默认硬件格点 hw_grid_f()={0,16,…,240,255}/255。
    """
    nodes = norm_nodes(cube)
    n = cube.n
    g = grid if grid is not None else hw_grid_f()
    tab = bytearray(TABLE_LEN)
    idx = 0
    for b in range(N16):
        for gg in range(N16):
            for r in range(N16):
                v = sample_trilinear(nodes, n, (g[r], g[gg], g[b]))
                tab[idx] = to_u8(v[0])
                tab[idx + 1] = to_u8(v[1])
                tab[idx + 2] = to_u8(v[2])
                tab[idx + 3] = 0
                idx += 4
    return bytes(tab)


def native_to_cube(tab, n=17, title="", kind_note=""):
    """19652B 原生表 → Cube（把硬件格点重采样到均匀格点，供标准 .cube 使用）。"""
    # 先把原生表包成「格点为 hw_grid」的 cube，再重采样到均匀格点
    hw = hw_grid_f()
    nodes = []
    for b in range(N16):
        for g in range(N16):
            for r in range(N16):
                o = (r + g * N16 + b * N16 * N16) * 4
                nodes.append((tab[o] / 255.0, tab[o + 1] / 255.0, tab[o + 2] / 255.0))
    src = Cube(N16, nodes, title, (0.0, 0.0, 0.0), (1.0, 1.0, 1.0))
    nin = N16
    ug = uniform_grid_f(n)
    out = []
    # 复用 trilinear：把源节点表当成 n³ 均匀网格 → 需要节点位置 = hw 格点而非均匀。
    # 故这里用「逆映射」：对均匀格点 u，找其在 hw 轴上的位置再插值。
    for b in range(n):
        for g in range(n):
            for r in range(n):
                out.append(_sample_hw_axis(nodes, ug[r], ug[g], ug[b]))
    return Cube(n, out, title, (0.0, 0.0, 0.0), (1.0, 1.0, 1.0),
                "3D" + ((" " + kind_note) if kind_note else ""))


def _sample_hw_axis(nodes, ur, ug_, ub):
    """在「非均匀 hw 格点」节点表上，按均匀输入 u∈[0,1] 采样（逐轴线性插值）。"""
    hw = hw_grid_f()

    def axis_pos(u):
        if u <= hw[0]:
            return 0, 0, 0.0
        if u >= hw[-1]:
            return N16 - 1, N16 - 1, 0.0
        for i in range(N16 - 1):
            if hw[i] <= u <= hw[i + 1]:
                span = hw[i + 1] - hw[i]
                return i, i + 1, (0.0 if span == 0 else (u - hw[i]) / span)
        return N16 - 1, N16 - 1, 0.0

    r0, r1, fr = axis_pos(ur)
    g0, g1, fg = axis_pos(ug_)
    b0, b1, fb = axis_pos(ub)

    def at(i, j, k):
        return nodes[i + j * N16 + k * N16 * N16]

    out = [0.0, 0.0, 0.0]
    for c in range(3):
        c000 = at(r0, g0, b0)[c]; c100 = at(r1, g0, b0)[c]
        c010 = at(r0, g1, b0)[c]; c110 = at(r1, g1, b0)[c]
        c001 = at(r0, g0, b1)[c]; c101 = at(r1, g0, b1)[c]
        c011 = at(r0, g1, b1)[c]; c111 = at(r1, g1, b1)[c]
        c00 = c000 + (c100 - c000) * fr
        c01 = c001 + (c101 - c001) * fr
        c10 = c010 + (c110 - c010) * fr
        c11 = c011 + (c111 - c011) * fr
        c0 = c00 + (c10 - c00) * fg
        c1 = c01 + (c11 - c01) * fg
        out[c] = c0 + (c1 - c0) * fb
    return tuple(out)


def read_native(path):
    """读原生表，返回 19652B（自动剥尾 / 自动转换旧 29478B 格式）。"""
    with open(path, "rb") as f:
        d = f.read()
    if len(d) == TABLE_LEN:
        return d
    if len(d) == SLOT_LEN:
        return d[:TABLE_LEN]
    if len(d) == OLD_LEN:
        sys.stderr.write("[warn] 输入是旧格式 29478B（u16×3），自动降转为 19652B\n")
        out = bytearray(TABLE_LEN)
        for i in range(NENT):
            o = i * OLD_ITEM
            r = struct.unpack_from("<H", d, o)[0]
            g = struct.unpack_from("<H", d, o + 2)[0]
            b = struct.unpack_from("<H", d, o + 4)[0]
            out[i * 4] = to_u8(r / 65535.0)
            out[i * 4 + 1] = to_u8(g / 65535.0)
            out[i * 4 + 2] = to_u8(b / 65535.0)
        return bytes(out)
    raise ValueError("无法识别的表长度 %d（期望 %d / %d / %d）"
                     % (len(d), TABLE_LEN, SLOT_LEN, OLD_LEN))


def slotwrap(tab):
    """19652B → 19712B 整槽（补 tail = 末项×3 + 48×0）。"""
    assert len(tab) == TABLE_LEN
    last = tab[-4:]
    return tab + last * 3 + b"\x00" * (TAIL_LEN - 12)


def write_native(tab, path, slot=False):
    data = slotwrap(tab) if slot else tab
    with open(path, "wb") as f:
        f.write(data)
    return len(data)


def load_source(path, order="auto"):
    """统一入口：把任意输入变成 19652B 原生表。

      .cube → 解析 + 非均匀格点采样
      .bin  → 读原生（自动剥尾 / 自动降转旧 29478B 格式）
    返回 (tab, 描述串)。
    """
    if path.lower().endswith(".cube"):
        cube = parse_cube(path, order=order)
        desc = "%s %d%s" % (cube.kind, cube.n, ("³" if cube.kind == "3D" else " 节点"))
        if cube.order != ORDER_SPEC:
            desc += "（轴序 %r→rgb 已纠正）" % cube.order
        return cube_to_native(cube), desc
    return read_native(path), "原生表"


# ---------------------------------------------------------------- 身份表

def make_identity_native():
    """构造原生 identity 表 = 硬件格点自映射，即 {G_i,G_i,G_i}。"""
    tab = bytearray(TABLE_LEN)
    g = hw_grid_u8()
    idx = 0
    for b in range(N16):
        for gg in range(N16):
            for r in range(N16):
                tab[idx] = g[r]; tab[idx + 1] = g[gg]; tab[idx + 2] = g[b]
                tab[idx + 3] = 0
                idx += 4
    return bytes(tab)


def make_identity_cube(n):
    """规范 identity cube（均匀格点）。"""
    ug = uniform_grid_f(n)
    out = []
    for b in range(n):
        for g in range(n):
            for r in range(n):
                out.append((ug[r], ug[g], ug[b]))
    return Cube(n, out, "identity", (0, 0, 0), (1, 1, 1))


# ---------------------------------------------------------------- 统计

def axis_ramps(tab):
    return ([tab[4 * r] for r in range(N16)],
            [tab[4 * (17 * g) + 1] for g in range(N16)],
            [tab[4 * (289 * b) + 2] for b in range(N16)])


def diff_max(tabA, tabB):
    """两表最大绝对差（按项·通道）。"""
    m = 0
    for i in range(NENT):
        for c in range(3):
            m = max(m, abs(tabA[4 * i + c] - tabB[4 * i + c]))
    return m


def is_identity(tab):
    ids = make_identity_native()
    return tab == ids


# ---------------------------------------------------------------- 命令

def cmd_import(a, fl):
    src, dst = a[0], (a[1] if len(a) > 1 else None)
    order = fl[fl.index("--order") + 1] if "--order" in fl else "auto"
    cube = parse_cube(src, order=order)
    sys.stdout.write("源 %s: %s %d³ = %d 节点  title=%r\n"
                     % (src, cube.kind, cube.n, cube.n ** 3, cube.title))
    if cube.order != ORDER_SPEC:
        sys.stdout.write("  ★ 轴序非规范：文件实为 %r（fastest→slowest），"
                         "已重排为 rgb\n" % cube.order)
    tab = cube_to_native(cube)
    if is_identity(tab):
        sys.stdout.write("  ★ 注意：转换结果 = identity，灌进去画面不会变\n")
    sys.stdout.write("  输出 %d 字节（%d³×4 + pad）%s\n"
                     % (len(tab), N16,
                        "  → 整槽 %d" % SLOT_LEN if "--slot" in fl else ""))
    if dst:
        n = write_native(tab, dst, slot="--slot" in fl)
        sys.stdout.write("  已写 %s (%d 字节)\n" % (dst, n))
        r, g, b = axis_ramps(tab)
        sys.stdout.write("  R 轴 ramp: %s\n" % r)
        sys.stdout.write("  前 16B: %s\n" % " ".join("%02x" % x for x in tab[:16]))
    if "--verify" in fl:
        ref = read_native(fl[fl.index("--verify") + 1])
        d = diff_max(tab, ref)
        sys.stdout.write("  对照 %s: 最大偏差 %d  %s\n"
                         % (fl[fl.index("--verify") + 1], d,
                            "字节级一致" if d == 0 else "★不一致"))
        return 0 if d == 0 else 2
    return 0


def cmd_export(a, fl):
    src, dst = a[0], a[1]
    n = int(fl[fl.index("--n") + 1]) if "--n" in fl else 17
    title = fl[fl.index("--title") + 1] if "--title" in fl else os.path.basename(src)
    tab = read_native(src)
    cube = native_to_cube(tab, n=n, title=title)
    with open(dst, "w", encoding="utf-8") as f:
        f.write("TITLE \"%s\"\n" % title)
        f.write("# generated by nx3dlut.py from %s\n" % os.path.basename(src))
        f.write("# NOTE: resampled from native (nonuniform {0,16,..,240,255} grid)\n")
        f.write("LUT_3D_SIZE %d\n" % n)
        for (r, g, b) in cube.nodes:
            f.write("%.6f %.6f %.6f\n" % (r, g, b))
    sys.stdout.write("已写 %s (%d³, %d 节点)\n" % (dst, n, n ** 3))
    return 0


def cmd_identity(a, fl):
    dst = a[0]
    tab = make_identity_native()
    n = write_native(tab, dst, slot="--slot" in fl)
    sys.stdout.write("已写 identity %s (%d 字节)\n" % (dst, n))
    sys.stdout.write("  R 轴 ramp: %s\n" % axis_ramps(tab)[0])
    return 0


def cmd_info(a, fl):
    src = a[0]
    if src.lower().endswith(".cube"):
        cube = parse_cube(src)
        if cube.kind == "3D":
            size = "%d³ = %d 节点" % (cube.n, cube.n ** 3)
        else:
            size = "%d 节点（逐通道曲线，展开为 %d³）" % (cube.n, cube.n)
        sys.stdout.write("%s: %s  %s  title=%r  domain=%s..%s\n"
                         % (src, cube.kind, size, cube.title, cube.dmin, cube.dmax))
        if cube.order != ORDER_SPEC:
            sys.stdout.write("  ★ 轴序非规范：文件实为 %r（fastest→slowest）\n" % cube.order)
        nd = norm_nodes(cube)
        if cube.kind == "1D":
            # 三条独立曲线：展开后 R 通道沿 r 轴、G 沿 g 轴、B 沿 b 轴
            n = cube.n
            for c, name in enumerate("RGB"):
                step = n ** c
                curve = [nd[i * step][c] for i in range(n)]
                mono = all(curve[i] <= curve[i + 1] + 1e-6 for i in range(n - 1))
                sys.stdout.write("  %s 曲线: %s%s\n"
                                 % (name, " ".join("%.4f" % v for v in curve),
                                    "" if mono else "  (非单调)"))
            return 0
        sys.stdout.write("  node[0]=%s  node[Rmax]=%s  node[last]=%s\n"
                         % (tuple(round(x, 4) for x in nd[0]),
                            tuple(round(x, 4) for x in nd[cube.n - 1]),
                            tuple(round(x, 4) for x in nd[-1])))
        return 0

    tab = read_native(src)
    r, g, b = axis_ramps(tab)
    sys.stdout.write("%s: 原生表 %d 字节（%d³×4）\n" % (src, len(tab), N16))
    sys.stdout.write("  R 轴: %s\n  G 轴: %s\n  B 轴: %s\n" % (r, g, b))
    sys.stdout.write("  对角(diag): %s\n" % [tab[4 * (307 * i)] for i in range(N16)])
    ids = make_identity_native()
    sys.stdout.write("  与 identity: %s（最大偏差 %d）\n"
                     % ("一致" if tab == ids else "不同", diff_max(tab, ids)))
    return 0


def write_png(path, w, h, rgb):
    """纯标准库 PNG 写出（RGB8）。供 preview 的 .png 输出——无需 Pillow。"""
    import zlib

    def chunk(typ, data):
        c = struct.pack(">I", len(data)) + typ + data
        c += struct.pack(">I", zlib.crc32(typ + data) & 0xffffffff)
        return c

    raw = bytearray()
    stride = w * 3
    for y in range(h):
        raw.append(0)                        # filter = None
        raw += rgb[y * stride:(y + 1) * stride]
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)


def cmd_preview(a, fl):
    """把 LUT 应用到一张测试图上，输出 PPM（P6）/ PNG。便于 R3 目视验收。"""
    src, dst = a[0], a[1]
    n = int(fl[fl.index("--n") + 1]) if "--n" in fl else 33
    if src.lower().endswith(".cube"):
        cube = parse_cube(src)
        nd, cn = norm_nodes(cube), cube.n
        sample = lambda p: sample_trilinear(nd, cn, p)
    else:
        tab = read_native(src)
        hw = hw_grid_f()
        node_l = []
        for bb in range(N16):
            for gg in range(N16):
                for rr in range(N16):
                    o = (rr + gg * N16 + bb * N16 * N16) * 4
                    node_l.append((tab[o] / 255.0, tab[o + 1] / 255.0, tab[o + 2] / 255.0))
        sample = lambda p: _sample_hw_axis(node_l, p[0], p[1], p[2])

    W = H = 256
    px = bytearray()
    for y in range(H):
        for x in range(W):
            u = x / (W - 1.0)
            v = 1.0 - y / (H - 1.0)
            # 上半：灰阶楔；下半：RG 色平面 @ 3 个 B 台阶
            if y < H // 2:
                g = u
                p = (g, g, g)
            else:
                band = (y - H // 2) * 3 // (H - H // 2)
                p = (u, v, band / 2.0)
            o = sample(p)
            px.append(to_u8(o[0])); px.append(to_u8(o[1])); px.append(to_u8(o[2]))
    if dst.lower().endswith(".png"):
        write_png(dst, W, H, bytes(px))
        sys.stdout.write("已写预览 %s (%dx%d PNG)\n" % (dst, W, H))
        return 0
    with open(dst, "wb") as f:
        f.write(b"P6\n%d %d\n255\n" % (W, H))
        f.write(bytes(px))
    sys.stdout.write("已写预览 %s (%dx%d)\n" % (dst, W, H))
    return 0


def cmd_patch(a, fl):
    """把 cube / 原生 bin 转成原生表后，按 VA 补进 p7_full.bin 的副本。"""
    src, p7in, dst = a[0], a[1], a[2]
    va = int(fl[fl.index("--va") + 1], 0)
    order = fl[fl.index("--order") + 1] if "--order" in fl else "auto"
    tab, desc = load_source(src, order=order)
    sys.stdout.write("源 %s: %s\n" % (src, desc))
    with open(p7in, "rb") as f:
        img = bytearray(f.read())
    off = va - 0x80000000
    if off < 0 or off + SLOT_LEN > len(img):
        sys.stderr.write("[err] VA 0x%08X 越界（映像 %d 字节）\n" % (va, len(img)))
        return 1
    # 双保险：目标处必须是合法槽（pad 全 0 + tail 指纹），否则拒绝写
    if any(img[off + r] for r in range(3, TABLE_LEN, 4)):
        sys.stderr.write("[err] 0x%08X 处不是合法槽（pad 非零），拒绝覆盖\n" % va)
        return 1
    img[off:off + TABLE_LEN] = tab
    img[off + TABLE_LEN:off + SLOT_LEN] = slotwrap(tab)[TABLE_LEN:]
    with open(dst, "wb") as f:
        f.write(bytes(img))
    sys.stdout.write("已写 %s（在 VA 0x%08X 覆盖一槽）\n" % (dst, va))
    sys.stdout.write("★ 该产物需另行验收；未验收前视同 DO-NOT-FLASH\n")
    return 0


# ---------------------------------------------------------------- 自测

def find_builtin_tables():
    if not os.path.isdir(BUILTIN_DIR):
        return []
    out = []
    for fn in sorted(os.listdir(BUILTIN_DIR)):
        if fn.startswith("tab_") and fn.endswith(".bin"):
            p = os.path.join(BUILTIN_DIR, fn)
            if os.path.getsize(p) == TABLE_LEN:
                out.append(p)
    return out


def selftest():
    fails = 0
    ids = make_identity_native()

    sys.stdout.write("=== T1 格点重采样：identity cube(N) → 原生 ===\n")
    for n in (17, 33, 65):
        got = cube_to_native(make_identity_cube(n))
        d = diff_max(got, ids)
        ok = (d == 0)
        fails += 0 if ok else 1
        sys.stdout.write("  %s  identity %2d³ → 原生：最大偏差 %d\n"
                         % ("OK  " if ok else "FAIL", n, d))

    sys.stdout.write("=== T2 负对照：改用「均匀格点」必须失败 ===\n")
    even = [round(i * 255.0 / 16.0) / 255.0 for i in range(N16)]
    got_e = cube_to_native(make_identity_cube(17), grid=even)
    d_e = diff_max(got_e, ids)
    ok = (d_e >= 1)
    fails += 0 if ok else 1
    sys.stdout.write("  %s  均匀格点采样 → 最大偏差 %d（level15: %d vs %d，应为 1）\n"
                     % ("OK  " if ok else "FAIL", d_e, got_e[4 * 15], ids[4 * 15]))

    sys.stdout.write("=== T3 格点实证：内置表 level15 落点（多样本）===\n")
    tabs = find_builtin_tables()
    c240 = c239 = 0
    for p in tabs:
        t = read_native(p)
        v15 = t[4 * 15]
        if v15 == 240:
            c240 += 1
        elif v15 == 239:
            c239 += 1
    ok = (c240 >= 4 and c239 == 0)
    fails += 0 if ok else 1
    sys.stdout.write("  %s  %d 个内置表中 level15==240（hw 格点）: %d，==239（均匀格点）: %d\n"
                     % ("OK  " if ok else "FAIL", len(tabs), c240, c239))

    sys.stdout.write("=== T4 索引顺序（corner 断言）===\n")
    idx_ok = True
    for (r, g, b, want) in [(16, 0, 0, (255, 0, 0)), (0, 16, 0, (0, 255, 0)),
                            (0, 0, 16, (0, 0, 255)), (16, 16, 16, (255, 255, 255))]:
        i = r + g * 17 + b * 289
        if tuple(ids[4 * i + c] for c in range(3)) != want:
            idx_ok = False
    if idx_ok:
        sys.stdout.write("  OK   R/G/B 轴角落映射正确（R 最快，((B*17+G)*17+R)*4）\n")
    else:
        sys.stdout.write("  FAIL 索引顺序错误\n")
        fails += 1

    sys.stdout.write("=== T5 整槽长度与 tail 指纹 ===\n")
    sw = slotwrap(ids)
    ok = (len(sw) == SLOT_LEN
          and sw[TABLE_LEN:TABLE_LEN + 12] == sw[TABLE_LEN - 4:TABLE_LEN] * 3
          and sw[TABLE_LEN + 12:] == b"\x00" * 48)
    fails += 0 if ok else 1
    sys.stdout.write("  %s  槽长 %d，tail = 末项×3(12B) + 48×0\n"
                     % ("OK  " if ok else "FAIL", len(sw)))

    sys.stdout.write("=== T6 内置表 export→import 往返（全部 %d 个）===\n" % len(tabs))
    mono, non = [], []
    for p in tabs:
        t0 = read_native(p)
        R = [t0[4 * r] for r in range(N16)]
        ok_curve = all(R[i] <= R[i + 1] for i in range(N16 - 1))
        d = diff_max(t0, cube_to_native(native_to_cube(t0, n=17)))
        (mono if ok_curve else non).append(d)
    if mono:
        sys.stdout.write("  单调族(R 轴非降, %d 表): 偏差 min%d 中位%d max%d\n"
                         % (len(mono), min(mono), sorted(mono)[len(mono) // 2], max(mono)))
    if non:
        sys.stdout.write("  非单调族(疑 +0x400 移位伪读, %d 表): 偏差 min%d max%d\n"
                         % (len(non), min(non), max(non)))
    ok = bool(mono) and max(mono) <= 4
    fails += 0 if ok else 1
    sys.stdout.write("  %s  单调族往返须 ≤4（证明格点+索引正确；>4 说明逻辑有误）\n"
                     % ("OK  " if ok else "FAIL"))

    sys.stdout.write("=== 自测%s（%d 项失败）===\n"
                     % ("通过" if fails == 0 else "失败", fails))
    return 0 if fails == 0 else 1


# ---------------------------------------------------------------- main

USAGE = __doc__


def main(argv):
    if len(argv) < 2:
        sys.stdout.write(USAGE)
        return 0
    cmd = argv[1]
    rest = argv[2:]
    args = [x for x in rest if not x.startswith("--")]
    flags = []
    i = 0
    while i < len(rest):
        if rest[i].startswith("--"):
            flags.append(rest[i])
            if i + 1 < len(rest) and not rest[i + 1].startswith("--"):
                flags.append(rest[i + 1])
                i += 1
        i += 1

    table = {
        "import": cmd_import, "export": cmd_export, "identity": cmd_identity,
        "info": cmd_info, "preview": cmd_preview, "patch": cmd_patch,
    }
    if cmd == "selftest":
        return selftest()
    if cmd not in table:
        sys.stderr.write("未知命令 %r\n\n%s" % (cmd, USAGE))
        return 1
    try:
        return table[cmd](args, flags)
    except (IOError, OSError) as e:
        sys.stderr.write("[err] %s\n" % e)
        return 1
    except ValueError as e:
        sys.stderr.write("[err] %s\n" % e)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
