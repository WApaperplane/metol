#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tcgen.py — NX500 TC 曲线离线生成与校验。

本工具只处理 JSON / 纯文本，不访问相机、不执行 devmem、不写设备内存。
它的输出需要人工审阅后才可用于实机实验。

术语
----
X      : 14bit 输入节点，19 点，固件固定表
Y      : 10bit 输出节点，19 点，可改
stock  : 固件原厂 Y 表（p7 1.12，源表 0x8062f71c，19 x u32）

合法性规则（写入前必须全部满足）
--------------------------------
1. 恰好 19 点
2. 全部为整数
3. 每点在 0..1023
4. 严格递增 Y[i] < Y[i+1]
5. 端点固定 Y[0] = 0, Y[18] = 1023
6. 若 JSON 携带 X，必须与固件固定表逐项相等

用法
----
  tcgen.py list
  tcgen.py gen log -o curves/log.json
  tcgen.py gen flat --strength 300 -o curves/flat300.json
  tcgen.py check curves/log.json
  tcgen.py show curves/log.json
  tcgen.py diff stock curves/log.json
  tcgen.py devmem curves/log.json          # 只打印，不执行
  tcgen.py svg -o curves/compare.svg stock log flat
"""
import argparse
import json
import math
import pathlib
import sys

N = 19
X_MAX = 16383
Y_MAX = 1023

# 固件固定 X 节点（p7 1.12 运行态表，14bit）
X_STOCK = [0, 32, 74, 140, 232, 365, 550, 810, 1169, 1664,
           2338, 3243, 4438, 5980, 7894, 10180, 12840, 15872, 16383]

# 固件原厂 Y 节点（p7 1.12，源表 0x8062f71c）
Y_STOCK = [0, 16, 36, 64, 105, 156, 223, 305, 397, 500,
           606, 704, 786, 860, 918, 960, 991, 1019, 1023]

HERE = pathlib.Path(__file__).resolve().parent
CURVES = HERE / "curves"


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def ensure_strict(y):
    """把可能出现的平台抬成严格递增；越界直接报错，不静默修补端点。"""
    out = list(y)
    if out[0] != 0 or out[-1] != Y_MAX:
        raise ValueError("端点必须是 0 / 1023，ensure_strict 不修补端点")
    for i in range(1, len(out)):
        if out[i] <= out[i - 1]:
            out[i] = out[i - 1] + 1
    if out[-1] > Y_MAX:
        raise ValueError("抬升后越过 1023，曲线动态范围不足")
    return out


def gen_linear():
    return [round(Y_MAX * x / X_MAX) for x in X_STOCK]


def gen_log(k=63.0):
    """对数形：y = 1023 * log2(1 + k*x/XMAX) / log2(1+k)。

    k=63 与 Codex 第五轮实验用的候选曲线逐点一致（Y[9]=492），作为基准。
    k 越大暗部抬得越高、画面越平；k 越小暗部越沉、对比越强。
    这不是任何标准 Log 传递函数，只是形状参考。
    """
    denom = math.log2(1.0 + k)
    return [round(Y_MAX * math.log2(1.0 + k * x / X_MAX) / denom) for x in X_STOCK]


PRESETS = {
    "stock":  lambda s: list(Y_STOCK),
    "linear": lambda s: gen_linear(),
    "log":    lambda s: gen_log(63.0 if s is None else s),
    "flat":   lambda s: gen_log(255.0 if s is None else s),
    "hc":     lambda s: gen_log(7.0 if s is None else s),
}


def build(name, strength=None):
    if name not in PRESETS:
        raise SystemExit(f"未知预设 {name}，可用：{', '.join(PRESETS)}")
    y = PRESETS[name](strength)
    y = [clamp(v, 0, Y_MAX) for v in y]
    y[0], y[-1] = 0, Y_MAX
    return ensure_strict(y)


def check_curve(y, x=None):
    """返回 (errors, warnings)。errors 非空即拒绝写入。"""
    err, warn = [], []
    if not isinstance(y, list):
        return ["Y 必须是数组"], warn
    if len(y) != N:
        err.append(f"点数 {len(y)} ≠ {N}")
    if any(not isinstance(v, int) or isinstance(v, bool) for v in y):
        err.append("存在非整数节点")
        return err, warn
    if any(v < 0 or v > Y_MAX for v in y):
        err.append(f"存在越界节点（允许 0..{Y_MAX}）")
    if y and y[0] != 0:
        err.append(f"Y[0] = {y[0]}，必须是 0")
    if y and y[-1] != Y_MAX:
        err.append(f"Y[18] = {y[-1]}，必须是 {Y_MAX}")
    for i in range(1, min(len(y), N)):
        if y[i] <= y[i - 1]:
            err.append(f"非严格递增：Y[{i-1}]={y[i-1]} → Y[{i}]={y[i]}")
    if x is not None:
        if len(x) != N:
            err.append(f"X 点数 {len(x)} ≠ {N}")
        elif x != X_STOCK:
            err.append("X 与固件固定表不一致（本工具不允许改 X）")
    if not err:
        span = sum(y[i] - y[i - 1] for i in range(1, N))
        if span < 200:
            warn.append(f"总抬升仅 {span} 码，曲线接近平线")
        if abs(y[9] - Y_STOCK[9]) > 320:
            warn.append(f"Y[9]={y[9]} 与原厂 500 相差过大，建议先在实机小步验证")
    return err, warn


def load(path):
    o = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    return o.get("y"), o.get("x")


def save(path, name, y, note="", gen=""):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    obj = {
        "name": name,
        "note": note,
        "generator": gen,
        "x": X_STOCK,
        "y": y,
    }
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def fmt_table(y):
    lines = [" i        X      Y   ΔY"]
    prev = None
    for i, (x, v) in enumerate(zip(X_STOCK, y)):
        d = "" if prev is None else f"{v - prev:+d}"
        lines.append(f"{i:2d}  {x:7d}  {v:5d}  {d:>5s}")
        prev = v
    return "\n".join(lines)


def cmd_list(_):
    print("预设    说明")
    print("stock   固件原厂（p7 1.12）")
    print("linear  按 X 线性")
    print("log     对数形，默认 k=63（与 Codex 候选曲线一致，Y[9]=492）")
    print("flat    对数形低对比，默认 k=255（暗部更亮、画面更平）")
    print("hc      对数形高对比，默认 k=7（暗部更沉）")


def cmd_gen(a):
    y = build(a.preset, a.strength)
    err, warn = check_curve(y)
    if err:
        raise SystemExit("生成结果不合法：" + "; ".join(err))
    out = a.out or str(CURVES / f"{a.preset}.json")
    p = save(out, a.preset, y,
             note=f"strength={a.strength}" if a.strength is not None else "",
             gen="tcgen.py gen")
    print(f"写出 {p}")
    print(fmt_table(y))
    for w in warn:
        print("警告：" + w, file=sys.stderr)


def cmd_check(a):
    y, x = load(a.file)
    err, warn = check_curve(y, x)
    if err:
        print("拒绝：" + a.file)
        for e in err:
            print("  - " + e)
        raise SystemExit(1)
    print(f"通过：{a.file}  ({N} 点，严格递增，端点 0/1023)")
    for w in warn:
        print("警告：" + w)
    print(fmt_table(y))


def cmd_show(a):
    y, x = load(a.file)
    err, _ = check_curve(y, x)
    print(fmt_table(y))
    if err:
        print("\n不合法：")
        for e in err:
            print("  - " + e)
        raise SystemExit(1)


def cmd_diff(a):
    ya, _ = load(a.file)
    yb, _ = load(a.file2)
    print(f"{'i':>2}  {'Y_a':>5} {'Y_b':>5} {'diff':>6}")
    for i in range(N):
        print(f"{i:2d}  {ya[i]:5d} {yb[i]:5d} {yb[i]-ya[i]:+6d}")


def cmd_devmem(a):
    y, x = load(a.file)
    err, warn = check_curve(y, x)
    if err:
        raise SystemExit("曲线不合法，拒绝生成命令：" + "; ".join(err))
    print("# 仅文本输出，不执行。写入对象为 p7 运行态源表。")
    print("# 写入后仍需 dirty 标记与一次 s1 刷新，且必须回读校验；本工具不负责那一步。")
    for i, v in enumerate(y):
        print(f"/opt/usr/nx-ks/busybox devmem {0x8062f71c + i * 4:#x} 32 {v}")
    for w in warn:
        print("# 警告：" + w)


def cmd_svg(a):
    names = a.names or ["stock", "log", "flat"]
    series = []
    for n in names:
        p = pathlib.Path(n)
        if p.suffix == ".json" and p.exists():
            y, _ = load(p)
            label = p.stem
        else:
            y = build(n)
            label = n
        series.append((label, y))

    W, H = 680, 360
    ml, mr, mt, mb = 56, 24, 44, 48
    pw, ph = W - ml - mr, H - mt - mb

    def sx(x):
        return ml + x / X_MAX * pw

    def sy(v):
        return mt + (1 - v / Y_MAX) * ph

    colors = ["#5F5E5A", "#185FA5", "#0F6E56", "#BA7517", "#534AB7"]
    parts = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" xmlns="http://www.w3.org/2000/svg">',
             f'<title>TC 曲线对比：{", ".join(s[0] for s in series)}</title>']
    parts.append(f'<rect x="{ml}" y="{mt}" width="{pw}" height="{ph}" fill="#FFFFFF" stroke="#D3D1C7" stroke-width="0.5"/>')
    for frac in (0.25, 0.5, 0.75):
        gx = ml + pw * frac
        gy = mt + ph * frac
        parts.append(f'<line x1="{gx:.1f}" y1="{mt}" x2="{gx:.1f}" y2="{mt+ph}" stroke="#F1EFE8" stroke-width="0.5"/>')
        parts.append(f'<line x1="{ml}" y1="{gy:.1f}" x2="{ml+pw}" y2="{gy:.1f}" stroke="#F1EFE8" stroke-width="0.5"/>')
    parts.append(f'<line x1="{ml}" y1="{mt+ph}" x2="{ml+pw}" y2="{mt+ph}" stroke="#888780" stroke-width="0.5"/>')
    parts.append(f'<line x1="{ml}" y1="{mt}" x2="{ml}" y2="{mt+ph}" stroke="#888780" stroke-width="0.5"/>')
    for i, (label, y) in enumerate(series):
        c = colors[i % len(colors)]
        pts = " ".join(f"{sx(x):.1f},{sy(v):.1f}" for x, v in zip(X_STOCK, y))
        parts.append(f'<polyline points="{pts}" fill="none" stroke="{c}" stroke-width="1.5"/>')
        for x, v in zip(X_STOCK, y):
            parts.append(f'<circle cx="{sx(x):.1f}" cy="{sy(v):.1f}" r="2" fill="{c}"/>')
        ly = mt + 16 + i * 18
        parts.append(f'<line x1="{ml+pw-96}" y1="{ly}" x2="{ml+pw-74}" y2="{ly}" stroke="{c}" stroke-width="1.5"/>')
        parts.append(f'<text x="{ml+pw-68}" y="{ly+4}" font-family="system-ui,sans-serif" font-size="12" fill="#2C2C2A">{label}</text>')
    parts.append(f'<text x="{ml}" y="{mt-12}" font-family="system-ui,sans-serif" font-size="13" font-weight="500" fill="#2C2C2A">TC 曲线（X 0–16383 / Y 0–1023）</text>')
    for v in (0, 256, 512, 768, 1023):
        parts.append(f'<text x="{ml-8}" y="{sy(v)+4:.1f}" font-family="system-ui,sans-serif" font-size="11" fill="#5F5E5A" text-anchor="end">{v}</text>')
    for x in (0, 4096, 8192, 12288, 16383):
        parts.append(f'<text x="{sx(x):.1f}" y="{mt+ph+18}" font-family="system-ui,sans-serif" font-size="11" fill="#5F5E5A" text-anchor="middle">{x}</text>')
    parts.append(f'<text x="{ml+pw/2:.1f}" y="{H-14}" font-family="system-ui,sans-serif" font-size="11" fill="#888780" text-anchor="middle">14bit 输入节点 X</text>')
    parts.append('</svg>')
    out = pathlib.Path(a.out or (CURVES / "compare.svg"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(parts) + "\n", encoding="utf-8")
    print(f"写出 {out}")


def main():
    ap = argparse.ArgumentParser(description="NX500 TC 曲线离线生成与校验（不访问相机）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("list", help="列出预设")
    s.set_defaults(fn=cmd_list)

    s = sub.add_parser("gen", help="生成预设曲线")
    s.add_argument("preset")
    s.add_argument("--strength", type=float, default=None)
    s.add_argument("-o", "--out")
    s.set_defaults(fn=cmd_gen)

    s = sub.add_parser("check", help="校验曲线文件")
    s.add_argument("file")
    s.set_defaults(fn=cmd_check)

    s = sub.add_parser("show", help="打印曲线表")
    s.add_argument("file")
    s.set_defaults(fn=cmd_show)

    s = sub.add_parser("diff", help="比较两条曲线")
    s.add_argument("file")
    s.add_argument("file2")
    s.set_defaults(fn=cmd_diff)

    s = sub.add_parser("devmem", help="打印 19 行 devmem 命令（不执行）")
    s.add_argument("file")
    s.set_defaults(fn=cmd_devmem)

    s = sub.add_parser("svg", help="输出曲线对比图")
    s.add_argument("names", nargs="*")
    s.add_argument("-o", "--out")
    s.set_defaults(fn=cmd_svg)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
