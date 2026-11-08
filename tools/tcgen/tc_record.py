#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tc_record.py — 录制控制与状态检测（不改曲线，可选设置 ISO）。

只做三件事：判断是否在录制、开录并等到 MP4 句柄出现、停录并等句柄消失。
曲线的切换与恢复由 tc_write.py 负责，两者串行使用。

退出码
  0   成功
 20   di-camera-app 不在
 21  已在录制，拒绝重复开录
 30  按键后未检测到 MP4 句柄
 31  停录后句柄仍未消失
"""
import argparse
import os
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
KEY = ROOT / "test_server/dropbear/ssh/nx500_ed25519"


def ssh_bin():
    p = pathlib.Path("C:/Windows/System32/OpenSSH/ssh.exe")
    if os.name == "nt" and p.exists():
        return str(p)
    return "ssh"


PRELUDE = r'''set -u
export DISPLAY=:0
B=/opt/usr/nx-ks/busybox
PID=$($B pidof di-camera-app)
[ -n "$PID" ] || { echo NO_PROCESS; exit 20; }
DCIM=/mnt/mmc/DCIM
rec(){ ls -l /proc/$PID/fd 2>/dev/null | grep -ai 'l-w.*DCIM/.*\.mp4' >/dev/null; }
toggle(){ st key push rec >/dev/null; sleep 0.15; st key release rec >/dev/null; }
newest(){ ls -t $DCIM/*/*.MP4 2>/dev/null | head -1; }
'''


def status_script():
    return PRELUDE + r'''
if rec; then echo RECORDING=1; else echo RECORDING=0; fi
echo NEWEST=$(newest)
'''


def record_script(seconds, iso_ud=None, settle=0.0):
    post = ""
    if iso_ud is not None:
        post = f'''
st cap capdtm setusr ISO {iso_ud}
sleep 0.3
echo ISO_AFTER=$(st cap capdtm getusr ISO | tr -d '\\r')
sleep {settle}
'''
    return PRELUDE + f'''
if rec; then echo ALREADY_RECORDING; exit 21; fi
owned=0
cleanup() {{
 code=$?; trap - EXIT HUP INT TERM
 if [ "$owned" -eq 1 ] && rec; then
  toggle
  n=0
  while [ $n -lt 60 ]; do rec || break; sleep 0.1; n=$((n+1)); done
  if rec; then echo CLEANUP_FAILED; code=31; fi
 fi
 exit "$code"
}}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
BEFORE=$(newest)
echo BEFORE=$BEFORE
owned=1
toggle
n=0
while [ $n -lt 40 ]; do rec && break; sleep 0.1; n=$((n+1)); done
if ! rec; then echo REC_NOT_STARTED; exit 30; fi
echo STARTED
{post}
sleep {seconds}
toggle
n=0
while [ $n -lt 60 ]; do rec || break; sleep 0.1; n=$((n+1)); done
if rec; then echo REC_NOT_STOPPED; exit 31; fi
owned=0
echo STOPPED
NEW=$(newest)
echo NEW=$NEW
[ -n "$NEW" ] && $B ls -l "$NEW" 2>/dev/null
'''


def run(host, script, timeout=60):
    p = subprocess.run(
        [ssh_bin(), "-i", str(KEY),
         "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes",
         "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=NUL",
         "-o", "ConnectTimeout=8", "-o", "LogLevel=ERROR",
         f"root@{host}", "/bin/sh", "-s"],
        input=script.encode("utf-8"), capture_output=True, timeout=timeout)
    return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")


def main():
    ap = argparse.ArgumentParser(description="录制控制（不改曲线）")
    ap.add_argument("--host", default=os.environ.get("NXHOST", "192.168.0.103"))
    ap.add_argument("--seconds", type=int, default=3)
    ap.add_argument("--iso-ud", default=None, type=lambda v: int(v,0),
                    help="开录后写入的 ISO userdata，如 0x50008；不传则不设")
    ap.add_argument("--settle", type=float, default=1.0, help="设置后等待秒数")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if not 1 <= a.seconds <= 3600 or not 0 <= a.settle <= 10:
        ap.error('seconds must be 1..3600 and settle must be 0..10')

    script = status_script() if a.status else record_script(a.seconds, a.iso_ud, a.settle)
    if a.dry_run:
        print(script)
        return 0
    if not KEY.exists():
        raise SystemExit(f"私钥不存在：{KEY}")

    rc, out, err = run(a.host, script, timeout=60 + a.seconds)
    print(out.strip())
    if err.strip():
        print("stderr:", err.strip())
    if rc != 0:
        return rc if 0 < rc < 126 else 2
    if "NO_PROCESS" in out:
        return 20
    if "ALREADY_RECORDING" in out:
        return 21
    if "REC_NOT_STARTED" in out:
        return 30
    if "REC_NOT_STOPPED" in out:
        return 31
    if not a.status and not all(re.search(r'(?m)^'+marker+r'$',out) for marker in ('STARTED','STOPPED')):
        return 32
    if a.status and not re.search(r'(?m)^RECORDING=[01]$',out):
        return 32
    return 0


if __name__ == "__main__":
    sys.exit(main())
