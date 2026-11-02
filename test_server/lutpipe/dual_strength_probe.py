"""双 LUT 各自强度：三种混合模型的静态对比。

被比较的三种语义（B0 = 原厂 A17，A/B = 两张 look，wa/wb ∈ [0,1]）：

  M1 偏移叠加   T = B0 + wa(A-B0) + wb(B-B0)
                两张表各按自己的强度贡献偏移，互不覆盖；双 100% 时外推。
  M2 顺层叠加   T = mix(mix(B0, A, wa), B, wb)      （图层/松下语义）
                先按 wa 打 A，再按 wb 盖 B；wb=100% 时 A 完全被覆盖。
  M3 归一叠加   T = B0 + (wa(A-B0) + wb(B-B0)) / max(1, wa+wb)
                权重语义，双 100% = 两张表的中点，恒不外推。wa+wb<=1 时与 M1 等价。

全部逐节点算，与机内 `lutmix` 一致（表节点线性混合等价于输出域混合，
见 LUT_STRENGTH_MIX_2026-10-31）。

★ 溢出只统计"混合产生的越界"，即 clamp 之前 raw 落在 [0,255] 之外的节点。
  直接数「输出 Y 贴 0/255」是错的：胶片表本来就把黑白端点压死，
  portra400 自己就有 533 个这样的节点。
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "tools/lutgen"))
from native_codec import ycc_to_rgb, rgb_to_ycc, sample  # noqa: E402

TABLE = 19652
SLOT = 19712


def load(path):
    raw = Path(path).read_bytes()
    if len(raw) == SLOT:
        return list(raw[:TABLE])
    if len(raw) == TABLE:
        return list(raw)
    raise SystemExit("bad table size %d: %s" % (len(raw), path))


def clamp8(v):
    return 0 if v < 0 else (255 if v > 255 else int(v + 0.5))


def m1(base, a, b, wa, wb):
    return [base[i] + wa * (a[i] - base[i]) + wb * (b[i] - base[i]) for i in range(TABLE)]


def m2(base, a, b, wa, wb):
    stage = [base[i] + wa * (a[i] - base[i]) for i in range(TABLE)]
    stage = [float(clamp8(v)) for v in stage]          # 第一层结果落回 8 位再进第二层
    return [stage[i] + wb * (b[i] - stage[i]) for i in range(TABLE)]


def m3(base, a, b, wa, wb):
    s = wa + wb
    k = 1.0 if s <= 1.0 else 1.0 / s
    return [base[i] + (wa * (a[i] - base[i]) + wb * (b[i] - base[i])) * k
            for i in range(TABLE)]


MODELS = [("M1 offset", m1), ("M2 layered", m2), ("M3 normalized", m3)]


def overflow(raw):
    """clamp 之前越界的节点数：Y 越界 = 死黑/死白，Cb/Cr 越界 = 偏色。"""
    yo = co = 0
    for i in range(0, TABLE, 4):
        if raw[i + 2] < 0 or raw[i + 2] > 255:
            yo += 1
        if raw[i] < 0 or raw[i] > 255 or raw[i + 1] < 0 or raw[i + 1] > 255:
            co += 1
    return yo, co


def dist(t1, t2):
    return sum(abs(a - b) for a, b in zip(t1, t2)) / len(t1)


def look(tab, rgb):
    cr, cb, y = rgb_to_ycc(rgb)
    out = sample([float(v) for v in tab], (cr, cb, y))
    return tuple(int(round(v)) for v in ycc_to_rgb(out))


def main():
    stock = HERE / "build" / "_stock_A17.bin"
    if not stock.exists():
        raise SystemExit("缺 build/_stock_A17.bin（从相机 /mnt/mmc/looks/ 取回）")
    base = load(stock)
    pairs = [
        ("warm-cold", REPO / "looks/kodak_portra400.bin", REPO / "looks/brand_teal_green.bin"),
        ("color-mono", REPO / "looks/kodak_portra400.bin", REPO / "looks/mono_acros.bin"),
        ("same-dir", REPO / "looks/warm_sepia.bin", REPO / "looks/warm_candle.bin"),
    ]
    steps = [0.0, 0.5, 1.0]

    print("=== 混合导致的越界节点数（Y / CbCr，总计 4913）与顺序依赖 ===")
    print("%-11s %-14s %4s %4s %6s %6s %8s" % ("pair", "model", "wa", "wb", "Yovf", "Covf", "orderDep"))
    for pname, pa, pb in pairs:
        a, b = load(pa), load(pb)
        for mname, fn in MODELS:
            for wa in steps:
                for wb in steps:
                    if wa == 0 and wb == 0:
                        continue
                    raw = fn(base, a, b, wa, wb)
                    yo, co = overflow(raw)
                    od = "-"
                    if wa > 0 and wb > 0:
                        od = "%.2f" % dist([clamp8(v) for v in raw],
                                           [clamp8(v) for v in fn(base, b, a, wb, wa)])
                    print("%-11s %-14s %4.1f %4.1f %6d %6d %8s"
                          % (pname, mname, wa, wb, yo, co, od))
        print()

    print("=== wa=wb=0.5 的关键色读数（RGB） ===")
    print("%-11s %-14s %-16s %-16s %-16s" % ("pair", "model", "gray(128)", "skin(200,140,110)", "white(245)"))
    for pname, pa, pb in pairs:
        a, b = load(pa), load(pb)
        for mname, fn in MODELS:
            t = [clamp8(v) for v in fn(base, a, b, 0.5, 0.5)]
            print("%-11s %-14s %-16s %-16s %-16s"
                  % (pname, mname, look(t, (128, 128, 128)),
                     look(t, (200, 140, 110)), look(t, (245, 245, 245))))
        print()


if __name__ == "__main__":
    main()
