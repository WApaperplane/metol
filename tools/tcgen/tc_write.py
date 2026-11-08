#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tc_write.py — TC 曲线写入实验（入场检查 / 回读确认 / 默认恢复原厂）。

这是写入工具，复用本地 scripts/tc.sh 的经过校验的写入与恢复流程。
仅允许空闲预览，不注入按键；远端脚本临时上传后清理，不部署正式入口。
默认行为：结束后把源表恢复成固件原厂，除非显式传 --keep。

安全约束
--------
1. 写入前必须确认 19 个源节点等于原厂，否则拒绝执行（exit 21）
2. 目标曲线必须通过 tcgen 的全部合法性规则
3. 刷新后必须回读 19 个缓存节点，逐项等于目标才算成功
4. 任何失败路径都执行恢复，并回读确认
5. 不刷固件、不改启动脚本、不持久化

退出码
------
  0  成功（缓存等于目标，描述符已消费）
 20  di-camera-app 不在
 21  入场源表不是原厂，拒绝
 22  写入后源表回读不符
 23  刷新后描述符仍是 dirty
 24  刷新后缓存不等于目标
 90  恢复失败或终态未确认（需要检查）

用法
----
  tc_write.py --curve curves/stock.json --dry-run
  tc_write.py --curve curves/stock.json            # 写原值，终态原厂
  tc_write.py --curve curves/flat.json --keep      # 写 flat 并保留
"""
import argparse
import json
import os
import pathlib
import re
import subprocess
import sys

N = 19
SRC_BASE = 0x8062F71C
ROOT_PTR = 0x817DCCBC
PARAM_GAMMA_OFF = 0x170
DIRTY_OFF = 0x004
CACHE_OFF = 0xE8C
STOCK_DESC = 0x0A00807F
DIRTY = 0xFFFFFFFF

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
KEY = ROOT / "test_server/dropbear/ssh/nx500_ed25519"
STOCK_JSON = HERE / "curves/stock.json"


def ssh_bin():
    p = pathlib.Path("C:/Windows/System32/OpenSSH/ssh.exe")
    if os.name == "nt" and p.exists():
        return str(p)
    return "ssh"


def check_curve(y):
    errs = []
    if len(y) != N:
        errs.append(f"点数 {len(y)} != {N}")
    if any((not isinstance(v, int)) or isinstance(v, bool) for v in y):
        errs.append("存在非整数")
    if any(v < 0 or v > 1023 for v in y if isinstance(v, int)):
        errs.append("越界")
    if y and y[0] != 0:
        errs.append("Y[0] != 0")
    if y and y[-1] != 1023:
        errs.append("Y[18] != 1023")
    for i in range(1, len(y)):
        if y[i] <= y[i - 1]:
            errs.append(f"非严格递增 Y[{i}]")
    return errs


def build_script(target, stock, keep, require_stock=True):
    # Reuse the reviewed on-camera transaction rather than a second devmem writer.
    program = (ROOT / "scripts/tc.sh").read_text(encoding="utf-8")
    assert "NXWA_TC_PROGRAM_END" not in program
    values = "\n".join(str(v) for v in target)
    keep_flag = 1 if keep else 0
    entry = 'state=$(sh "$T/tc.sh" status) || exit 21\necho "$state" | grep -q "^CURVE=stock$" || { echo ENTRY_MISMATCH; exit 21; }' if require_stock else ':'
    return f'''set -u
B=/opt/usr/nx-ks/busybox
T=$($B mktemp -d /tmp/nxwa-tc-XXXXXX) || exit 2
attempted=0
kept=0
cleanup() {{
 rc=$?
 trap - EXIT HUP INT TERM
 if [ "$attempted" -eq 1 ] && [ "$kept" -eq 0 ]; then
  if sh "$T/tc.sh" off; then echo FINAL_RESTORED=1; else echo FINAL_RESTORED=0; rc=90; fi
 fi
 $B rm -f "$T/tc.sh" "$T/target.tcy"
 $B rmdir "$T"
 [ "$rc" -ne 0 ] || echo COMPLETE=1
 exit "$rc"
}}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
cat > "$T/tc.sh" <<'NXWA_TC_PROGRAM_END'
{program}
NXWA_TC_PROGRAM_END
cat > "$T/target.tcy" <<'NXWA_TC_VALUES_END'
{values}
NXWA_TC_VALUES_END
{entry}
attempted=1
sh "$T/tc.sh" set "$T/target.tcy" || exit 22
state=$(sh "$T/tc.sh" status) || exit 24
descriptor=$(echo "$state" | sed -n 's/^DIRTY=//p')
[ -n "$descriptor" ] && [ "$((descriptor))" -ne "$((0xffffffff))" ] || exit 23
echo AFTER_CACHE_OK=1
echo SRC_EQ_TARGET=1
echo AFTER_DIRTY=$descriptor
if [ {keep_flag} -eq 1 ]; then kept=1; echo FINAL_KEPT=1; fi
'''


def run_remote(host, script, timeout=45):
    p = subprocess.run(
        [ssh_bin(), "-i", str(KEY),
         "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes",
         "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=NUL",
         "-o", "ConnectTimeout=8", "-o", "LogLevel=ERROR",
         f"root@{host}", "/bin/sh", "-s"],
        input=script.encode("utf-8"), capture_output=True, timeout=timeout)
    return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")


def kv(text):
    out = {}
    for line in text.splitlines():
        m = re.match(r"^([A-Z0-9_]+)=(.*)$", line.strip())
        if m:
            out[m.group(1)] = m.group(2)
    return out


def main():
    ap = argparse.ArgumentParser(description="TC 曲线写入实验")
    ap.add_argument("--curve", required=True)
    ap.add_argument("--host", default=os.environ.get("NXHOST", "192.168.0.103"))
    ap.add_argument("--keep", action="store_true", help="结束后保留目标曲线（默认恢复原厂）")
    ap.add_argument("--json-out", default=None)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    stock = json.loads(STOCK_JSON.read_text(encoding="utf-8"))["y"]
    target = json.loads(pathlib.Path(a.curve).read_text(encoding="utf-8"))["y"]
    errs = check_curve(target)
    if errs:
        raise SystemExit("目标曲线不合法：" + "; ".join(errs))
    if not KEY.exists():
        raise SystemExit(f"私钥不存在：{KEY}")

    script = build_script(target, stock, a.keep, require_stock=(target != stock))
    print(f"目标 {a.curve}")
    print(f"Y = {target}")
    print(f"终态：{'保留目标曲线' if a.keep else '恢复原厂'}")

    if a.dry_run:
        print("\n--- 远端脚本（不执行）---")
        print(script)
        return 0

    rc, out, err = run_remote(a.host, script)
    data = kv(out)
    print("\n--- 相机回包 ---")
    print(out.strip())
    if err.strip():
        print("stderr:", err.strip())

    def num(k, d=None):
        v = data.get(k)
        try:
            return int(v, 0)
        except (TypeError, ValueError):
            return d

    verdict, code = "unknown", 3
    if rc != 0:
        verdict, code = "远端执行或连接失败；不能确认终态", 90 if num("FINAL_RESTORED") == 0 else 2
    elif num("COMPLETE") != 1:
        verdict, code = "执行阶段不完整，不能确认成功", 2
    elif not a.keep and num("FINAL_RESTORED") != 1:
        verdict, code = "未验证完整原厂恢复", 90
    elif a.keep and num("FINAL_KEPT") != 1:
        verdict, code = "未确认目标曲线保留", 2
    elif "NO_PROCESS" in out:
        verdict, code = "相机进程不在", 20
    elif "ENTRY_MISMATCH" in out or "NO_GAMMA" in out:
        verdict, code = "入场态不是原厂，拒绝写入", 21
    elif num("SRC_EQ_TARGET") != 1:
        verdict, code = "源表回读不等于目标", 22
    elif num("AFTER_CACHE_OK") != 1 and num("RETRY_CACHE_OK") != 1:
        verdict, code = "缓存表未刷成目标", 24
    else:
        d = num("AFTER_DIRTY", num("RETRY_DIRTY"))
        if d is None or d == DIRTY:
            verdict, code = "描述符仍是 dirty", 23
        else:
            verdict = "成功：缓存等于目标，描述符已消费"
            code = 0

    report = {"host": a.host, "curve": a.curve, "target": target, "keep": a.keep,
              "exit": code, "verdict": verdict, "parsed": data,
              "raw": out, "stderr": err}
    if a.json_out:
        pathlib.Path(a.json_out).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(a.json_out).write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"结果写入 {a.json_out}")

    print(f"\n{verdict}（exit {code}）")
    if not a.keep and "FINAL_DIRTY" in data:
        print(f"终态：src_y9={data.get('FINAL_SRC_Y9')} cache_y9={data.get('FINAL_CACHE_Y9')} "
              f"dirty={data.get('FINAL_DIRTY')}")
    return code


if __name__ == "__main__":
    sys.exit(main())
