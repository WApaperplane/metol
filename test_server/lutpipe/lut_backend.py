#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lut_backend.py — LUT 预览后端 · PC 侧驱动（T5 产品化 · 2026-10-16）

两种模式：
  --sim   离线模拟：内置状态机，输出与 `lut_backend.sh` **同构**的 JSON（契约验证用）
  真实模式：经 `tools/nx-telnet.py` 在相机上执行 `lut_backend.sh` 并解析其 JSON

契约自测（--selftest）：跑 probe→apply→status→rollback 序列并断言：
  · JSON 单行、字段齐全
  · apply 成功 → level=="full"
  · ★ rollback 必须 identity_used == false（关闭语义：不得以 identity 冒充）
  · 表不存在 → level=="failed" 且 error=="table_not_found"

用法:
  python lut_backend.py --sim probe
  python lut_backend.py --sim apply portra400
  python lut_backend.py --sim rollback
  python lut_backend.py --selftest
  python lut_backend.py probe                       # 真实（需相机在线 + 工具已部署）
  python lut_backend.py apply portra400
"""
import argparse
import json
import os
import re
import shlex
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
NX_TELNET = os.path.join(ROOT, "tools", "nx-telnet.py")
REMOTE = "sh /mnt/mmc/filmlab/lut_backend.sh"


class SimBackend:
    """与 lut_backend.sh 同构的离线模拟"""

    def __init__(self):
        self.state = {
            "tools": {"cmasafe": 1, "cmapick2": 1, "lutapi": 1, "lutload": 1,
                      "lutsentinel": 1, "lutpick": 1},
            "luts": ["_identity", "portra400", "gold200", "trix400"],
            "guard": 0,
            "current": "",
            "sel_requested": None,
        }

    def probe(self):
        return {"ok": True, "tools": self.state["tools"],
                "luts_count": len(self.state["luts"]),
                "guard": self.state["guard"],
                "precondition": "apply 前需前置抢回态（先对焦一次）"}

    def apply(self, name, dry=False, sel=1):
        if sel not in (0, 1):
            return {"ok": False, "level": "failed", "error": "invalid_sel"}
        if name not in self.state["luts"]:
            return {"ok": False, "level": "failed", "error": "table_not_found", "table": name}
        if sel == 0 and self.state["guard"]:
            return {"ok": False, "level": "failed", "error": "guard_conflict", "sel_requested": 0}
        if not dry:
            self.state["current"] = name
            self.state["sel_requested"] = sel
        return {"ok": True, "level": "full", "table": name, "sel": sel,
                "sel_requested": sel, "hardware_verified": False, "still_verified": False,
                "guard": self.state["guard"], "dry": bool(dry),
                "note": "sel 为请求通道；守护未自动启动，画面与成片另验"}

    def rollback(self):
        self.state["guard"] = 0
        self.state["current"] = ""
        self.state["sel_requested"] = None
        return {"ok": True, "path": "factory_restore", "identity_used": False,
                "hardware_verified": False, "guard_stopped": True, "restore_rc": 0,
                "note": "恢复命令返回结果，原厂画面另验（非 identity）"}

    def status(self):
        return {"ok": True, "guard": self.state["guard"], "current": self.state["current"],
                "sel": None, "sel_requested": self.state["sel_requested"],
                "hardware_verified": False,
                "note": "current 与 sel_requested 为软件记账；sel 未读取硬件"}


def run_remote(args, timeout=180):
    """经 nx-telnet.py 在相机上执行并提取 JSON 行"""
    if not os.path.isfile(NX_TELNET):
        print("!! 缺 %s" % NX_TELNET, file=sys.stderr)
        return None
    cmd = "%s %s" % (REMOTE, shlex.join(args))
    p = subprocess.run([sys.executable, NX_TELNET, "-c", cmd],
                       capture_output=True, text=True, encoding="utf-8", timeout=timeout)
    for line in (p.stdout or "").splitlines():
        s = line.strip()
        if s.startswith("{") and s.endswith("}"):
            try:
                return json.loads(s)
            except json.JSONDecodeError:
                continue
    print("!! 未在相机输出中找到 JSON；原始输出尾：", file=sys.stderr)
    print("\n".join((p.stdout or "").splitlines()[-8:]), file=sys.stderr)
    return None


def selftest():
    b = SimBackend()
    fails = []

    def chk(ok, msg):
        print("[%s] %s" % ("OK  " if ok else "FAIL", msg))
        if not ok:
            fails.append(msg)

    def one_line(d):
        return json.dumps(d, ensure_ascii=False)

    print("== T5 契约自测（模拟后端）==")
    p = b.probe()
    chk(p["ok"] is True and "tools" in p and "luts_count" in p, "probe JSON 契约")
    print("   " + one_line(p))

    r = b.apply("portra400")
    chk(r["level"] == "full" and r["sel"] == 1, "apply 成功 → level=full / sel=1")
    s = b.status()
    chk(s["guard"] == 0 and s["current"] == "portra400" and s["sel"] is None,
        "apply 后 status：不虚构守护启动或硬件通道读回")

    r2 = b.apply("nonexistent")
    chk(r2["level"] == "failed" and r2["error"] == "table_not_found",
        "表不存在 → failed/table_not_found")

    rd = b.apply("portra400", dry=True)
    chk(rd["dry"] is True and b.status()["current"] == "portra400",
        "dry-run 不改变状态")

    rb = b.rollback()
    chk(rb["identity_used"] is False, "★ rollback 的 identity_used == false（关闭≠identity）")
    chk(rb["path"] == "factory_restore" and rb["guard_stopped"] is True,
        "rollback 走 factory_restore 且停守护")
    chk(b.status()["guard"] == 0 and b.status()["current"] == "",
        "rollback 后状态清空")

    r0 = b.apply("portra400", sel=0)
    chk(r0["sel_requested"] == 0 and not r0["still_verified"] and
        b.status()["sel_requested"] == 0, "sel=0 明确记账，不宣称成片验证通过")
    b.state["guard"] = 1
    chk(b.apply("portra400", sel=0)["error"] == "guard_conflict",
        "sel=0 与运行中的通道守护冲突时拒绝")

    print("\n== 结果：%s ==" % ("PASS" if not fails else "FAIL %s" % fails))
    return 0 if not fails else 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", nargs="?", default=None,
                    choices=["probe", "apply", "rollback", "status"])
    ap.add_argument("name", nargs="?", default=None)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--sel", type=int, choices=(0, 1), default=None,
                    help="apply 请求通道，默认 1；0 为待上机验证的 LUT0 路线")
    ap.add_argument("--sim", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.sel is not None and a.cmd != "apply":
        ap.error("--sel 仅适用于 apply")

    if a.selftest:
        return selftest()

    if a.sim:
        b = SimBackend()
        if a.cmd == "probe":
            print(json.dumps(b.probe(), ensure_ascii=False))
        elif a.cmd == "apply":
            result = b.apply(a.name or "", a.dry, sel=1 if a.sel is None else a.sel)
            print(json.dumps(result, ensure_ascii=False))
            return 0 if result.get("ok") else 2
        elif a.cmd == "rollback":
            print(json.dumps(b.rollback(), ensure_ascii=False))
        elif a.cmd == "status":
            print(json.dumps(b.status(), ensure_ascii=False))
        else:
            print("usage: --sim probe|apply <name>|rollback|status", file=sys.stderr)
            return 2
        return 0

    # 真实模式
    if not a.cmd:
        print("usage: lut_backend.py [--sim] probe|apply <name>|rollback|status", file=sys.stderr)
        return 2
    args = [a.cmd]
    if a.name:
        args.append(a.name)
    if a.dry:
        args.append("--dry")
    if a.sel is not None:
        args.extend(["--sel", str(a.sel)])
    d = run_remote(args)
    if d is None:
        return 3
    print(json.dumps(d, ensure_ascii=False))
    return 0 if d.get("ok") else 2


if __name__ == "__main__":
    sys.exit(main())
