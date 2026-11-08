#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tc_verify.py — TC 曲线对象链与节点表的只读验证。

本脚本只发 devmem 读取（三个参数，无写入形式），不修改任何设备内存，
不启停录像，不改相机设置。用于在写入实验前确认：

  1. 地址链在当前 boot 可解析
  2. 参数对象 / Gamma 对象的签名正确
  3. 19 个源节点与 19 个缓存节点都等于固件原厂值
  4. 当前 dirty 标记处于什么状态

地址链（固件 1.12 已验证）
--------------------------
  Param0 = read32(0x817dccbc)
  Gamma  = read32(Param0 + 0x170)
  dirty  = Gamma + 4
  Y[i]   = Gamma + 0xe8c + 4i

签名
----
  read32(Param + 0x00) == 0x8062f5f8
  read32(Gamma + 0x00) == 0x8062f6b0

用法
----
  tc_verify.py --dry-run                 # 只打印将执行的读取命令
  tc_verify.py                           # 连默认相机并验证
  tc_verify.py --host 192.168.0.103 --json-out verify.json
"""
import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
import time

N = 19
SRC_BASE = 0x8062F71C
ROOT_PTR = 0x817DCCBC
PARAM1_PTR = 0x817DCCC0
PARAM_SIG = 0x8062F5F8
GAMMA_VTBL = 0x8062F6B0
PARAM_GAMMA_OFF = 0x170
DIRTY_OFF = 0x004
CACHE_OFF = 0xE8C

ADDR_LO, ADDR_HI = 0x80000000, 0x84000000

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
KEY = ROOT / "test_server/dropbear/ssh/nx500_ed25519"
STOCK_JSON = HERE / "curves/stock.json"

EXIT = {
    "ok": 0,
    "ssh": 2,
    "addr": 3,
    "signature": 4,
    "source_mismatch": 5,
    "cache_mismatch": 6,
    "bad_output": 7,
}


def ssh_bin():
    p = pathlib.Path("C:/Windows/System32/OpenSSH/ssh.exe")
    if os.name == "nt" and p.exists():
        return str(p)
    return "ssh"


def valid_addr(a):
    return isinstance(a, int) and ADDR_LO <= a < ADDR_HI and a % 4 == 0


def read_batch(host, addresses, timeout=14, attempts=2):
    """一批 read-only devmem。返回 {addr: value}；失败抛 RuntimeError。"""
    for a in addresses:
        if not valid_addr(a):
            raise ValueError(f"地址越界或未对齐：{a:#x}")
    cmd = "\n".join(f"/opt/usr/nx-ks/busybox devmem {a:#x} 32" for a in addresses)
    last = ""
    for k in range(attempts):
        try:
            p = subprocess.run(
                [ssh_bin(), "-i", str(KEY),
                 "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes",
                 "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=NUL",
                 "-o", "ConnectTimeout=8", "-o", "LogLevel=ERROR",
                 f"root@{host}", cmd],
                capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            last = "ssh timeout"
            time.sleep(0.4)
            continue
        out = p.stdout.decode("utf-8", "replace")
        if p.returncode != 0:
            last = (p.stderr.decode("utf-8", "replace") or out or "ssh rc != 0").strip()
            time.sleep(0.4)
            continue
        vals = [int(v, 16) for v in re.findall(r"(?m)^0x[0-9a-fA-F]+\s*$", out)]
        if len(vals) != len(addresses):
            last = f"回读数量 {len(vals)} != {len(addresses)}"
            time.sleep(0.4)
            continue
        return dict(zip(addresses, vals))
    raise RuntimeError(f"读取失败：{last}")


def plan(host):
    """打印三阶段命令序列（--dry-run 用）。"""
    print("# 阶段 1：参数对象指针")
    print(f"#   Param0 = read32({ROOT_PTR:#x})")
    print(f"#   Param1 = read32({PARAM1_PTR:#x})（可选实例）")
    print("# 阶段 2：对象签名与 Gamma 指针（地址依赖阶段 1）")
    print(f"#   read32(Param0) == {PARAM_SIG:#x} ?")
    print(f"#   Gamma = read32(Param0 + {PARAM_GAMMA_OFF:#x})")
    print(f"#   read32(Gamma) == {GAMMA_VTBL:#x} ?")
    print("# 阶段 3：19 源节点 + dirty + 19 缓存节点")


def verify(host, stock, with_context=False):
    report = {"host": host, "steps": [], "problems": []}

    def step(name, **kw):
        rec = {"step": name, **kw}
        report["steps"].append(rec)
        print(f"  {name}: " + ", ".join(f"{k}={v}" for k, v in kw.items()))

    print("[1/3] 解析参数对象指针")
    roots = read_batch(host, [ROOT_PTR, PARAM1_PTR])
    param0 = roots[ROOT_PTR]
    param1 = roots[PARAM1_PTR]
    step("root", param0=f"{param0:#x}", param1=f"{param1:#x}")
    if not valid_addr(param0):
        report["problems"].append(f"Param0 异常：{param0:#x}")
        return report, EXIT["addr"]

    print("[2/3] 校验签名并解析 Gamma")
    probe = [param0]
    if valid_addr(param1) and param1 != param0:
        probe.append(param1)
    words = read_batch(host, [a + k for a in probe for k in (0, PARAM_GAMMA_OFF)])
    gammas = {}
    for p in probe:
        sig = words[p]
        g = words[p + PARAM_GAMMA_OFF]
        tag = "param0" if p == param0 else "param1"
        step(tag, sig=f"{sig:#x}", gamma=f"{g:#x}")
        if sig != PARAM_SIG:
            msg = f"{tag} 签名不符：{sig:#x} != {PARAM_SIG:#x}"
            if p == param0:
                report["problems"].append(msg)
                return report, EXIT["signature"]
            report["problems"].append(msg + "（可选实例，不阻断）")
            continue
        if not valid_addr(g):
            msg = f"{tag} Gamma 指针异常：{g:#x}"
            if p == param0:
                report["problems"].append(msg)
                return report, EXIT["addr"]
            report["problems"].append(msg + "（可选实例，不阻断）")
            continue
        gammas[tag] = g

    base = gammas["param0"]
    addrs = []
    for tag, g in gammas.items():
        addrs += [g, g + DIRTY_OFF] + [g + CACHE_OFF + 4 * i for i in range(N)]
    addrs += [SRC_BASE + 4 * i for i in range(N)]
    if with_context:
        addrs += [0x81561DF0, 0x81561DF8, 0x81561DFC, 0x81561E7C,
                  0x81561D8C, 0x81561EB4, 0x81561FC8]

    print("[3/3] 回读源表与缓存表")
    w = read_batch(host, addrs)
    source = [w[SRC_BASE + 4 * i] for i in range(N)]
    step("source", values=source)

    caches = {}
    for tag, g in gammas.items():
        vtbl = w[g]
        if vtbl != GAMMA_VTBL:
            report["problems"].append(f"{tag} vtable 不符：{vtbl:#x} != {GAMMA_VTBL:#x}")
            return report, EXIT["signature"]
        caches[tag] = [w[g + CACHE_OFF + 4 * i] for i in range(N)]
        step(tag, vtable=f"{vtbl:#x}", dirty=f"{w[g + DIRTY_OFF]:#x}", cache=caches[tag])

    ok_src = source == stock
    report.update({
        "gamma": {k: f"{v:#x}" for k, v in gammas.items()},
        "dirty": {k: f"{w[g + DIRTY_OFF]:#x}" for k, g in gammas.items()},
        "source": source,
        "caches": caches,
        "stock": stock,
        "source_matches_stock": ok_src,
        "cache_matches_stock": {k: v == stock for k, v in caches.items()},
    })
    if not ok_src:
        diff = [(i, stock[i], source[i]) for i in range(N) if stock[i] != source[i]]
        report["problems"].append(f"源表与原厂不一致：{diff}")
        return report, EXIT["source_mismatch"]
    for tag, c in caches.items():
        if c != stock:
            diff = [(i, stock[i], c[i]) for i in range(N) if stock[i] != c[i]]
            report["problems"].append(f"{tag} 缓存表与原厂不一致（可能有未恢复的改写）：{diff}")
            return report, EXIT["cache_mismatch"]

    if with_context:
        ctx = {k: f"{w[a]:#x}" for k, a in zip(
            ["iso", "tv", "av", "wb", "movie_ae", "app_mode", "movie_gamma"],
            [0x81561DF0, 0x81561DF8, 0x81561DFC, 0x81561E7C,
             0x81561D8C, 0x81561EB4, 0x81561FC8])}
        report["context"] = ctx
        print("  上下文: " + ", ".join(f"{k}={v}" for k, v in ctx.items()))

    return report, EXIT["ok"]


def main():
    ap = argparse.ArgumentParser(description="TC 曲线只读验证（不写内存）")
    ap.add_argument("--host", default=os.environ.get("NXHOST", "192.168.0.103"))
    ap.add_argument("--stock", default=str(STOCK_JSON))
    ap.add_argument("--json-out", default=None)
    ap.add_argument("--with-context", action="store_true", help="附带 ISO/WB/模式等只读字段")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    stock_doc = json.loads(pathlib.Path(a.stock).read_text(encoding="utf-8"))
    stock = stock_doc["y"]
    if len(stock) != N:
        raise SystemExit(f"{a.stock} 不是 {N} 点")

    print(f"只读验证 → {a.host}   原厂基准 {a.stock}")
    if not KEY.exists():
        raise SystemExit(f"私钥不存在：{KEY}")
    if a.dry_run:
        plan(a.host)
        print("dry-run：未连接相机。")
        return 0

    try:
        report, code = verify(a.host, stock, a.with_context)
    except Exception as e:
        print(f"失败：{e}", file=sys.stderr)
        return EXIT["ssh"]

    report["exit_code"] = code
    if a.json_out:
        pathlib.Path(a.json_out).write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"结果写入 {a.json_out}")

    if code == EXIT["ok"]:
        print("\n通过：地址链可解析，签名正确，19 源节点与 19 缓存节点均等于原厂。")
    else:
        print("\n未通过：")
        for p in report["problems"]:
            print("  - " + p)
    return code


if __name__ == "__main__":
    sys.exit(main())
