#!/usr/bin/env python3
"""Stage a read-only collector in a new SD folder; launch detached; fetch evidence.

Uses the existing nx-probe Telnet transport. Never installs into mod paths,
loads a LUT, writes registers, or changes App lifecycle.
"""
import argparse
import ftplib
import hashlib
import importlib.util
import io
import json
import os
import re
import shlex
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SESSION = ROOT / "raw8/gates/lut/ondevice_selection_2026-10-17/session.json"
spec = importlib.util.spec_from_file_location("nxprobe", ROOT / "tools/nx-probe.py")
nxprobe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nxprobe)


def connect(host):
    ftp = ftplib.FTP()
    ftp.connect(host, 21, timeout=10)
    ftp.login("root", "")
    return ftp


def launch(session, body):
    folder = session["remote_folder"]
    if not re.fullmatch(r"nxwa_lutsel_[0-9TZ]+", folder):
        raise ValueError("unexpected remote evidence directory")
    nxprobe.HOST = session["host"]
    remote = "/mnt/mmc/" + folder
    command = (f"chmod 755 {remote}/lutobserve.arm && "
               f"/usr/bin/setsid /bin/sh -c {shlex.quote(body)} "
               f"> {remote}/launcher.log 2>&1 < /dev/null &")
    nxprobe.telnet_send(command, timeout=10)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("stage", "baseline", "identity", "watch", "fetch"))
    parser.add_argument("--session", type=Path, default=DEFAULT_SESSION)
    parser.add_argument("--tag", default="watch", help="name for one watch capture")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,23}", args.tag):
        raise ValueError("invalid capture tag")
    args.session.parent.mkdir(parents=True, exist_ok=True)
    if args.action == "stage":
        if args.session.exists():
            raise ValueError("session already exists; use another --session path")
        data = (Path(__file__).parent / "build/lutobserve.arm").read_bytes()
        session = {"host": os.environ.get("NXHOST", "192.168.0.106"),
                   "remote_folder": "nxwa_lutsel_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
                   "collector_sha256": hashlib.sha256(data).hexdigest(),
                   "collector_md5": hashlib.md5(data).hexdigest(),
                   "events": []}
        with connect(session["host"]) as ftp:
            ftp.mkd(session["remote_folder"])
            name = session["remote_folder"] + "/lutobserve.arm"
            ftp.storbinary("STOR " + name, io.BytesIO(data))
            readback = io.BytesIO()
            ftp.retrbinary("RETR " + name, readback.write)
        if readback.getvalue() != data:
            raise ValueError("SD collector upload readback mismatch")
        (args.session.parent / "lutobserve.arm").write_bytes(data)
        args.session.write_text(json.dumps(session, indent=2) + "\n", encoding="utf-8")
        print("Staged and FTP byte-verified", session["remote_folder"], len(data), "bytes")
        return
    session = json.loads(args.session.read_text(encoding="utf-8"))
    folder = session["remote_folder"]
    if not re.fullmatch(r"nxwa_lutsel_[0-9TZ]+", folder):
        raise ValueError("unexpected remote evidence directory")
    remote = "/mnt/mmc/" + folder
    if args.action in ("baseline", "identity", "watch"):
        if any(e["action"] == args.action and
               (args.action != "watch" or e.get("tag", "watch") == args.tag)
               for e in session["events"]):
            raise ValueError("capture already launched; use a new session for another run")
        executable = remote + "/lutobserve.arm"
        if args.action == "baseline":
            body = (f"{executable} snapshot > {remote}/before.csv 2> {remote}/before.err; a=$?; "
                    f"{executable} pools > {remote}/pools.bin 2> {remote}/pools.err; b=$?; "
                    f"{executable} snapshot > {remote}/after.csv 2> {remote}/after.err; c=$?; "
                    f"md5sum {remote}/pools.bin {executable} > {remote}/baseline.md5; "
                    f"printf '%s %s %s\\n' $a $b $c > {remote}/baseline.done; sync")
        elif args.action == "identity":
            body = (f"dd if=/dev/mmcblk0p7 of={remote}/p7.bin bs=4096 count=2949 "
                    f"2> {remote}/p7.err; a=$?; md5sum {remote}/p7.bin > {remote}/p7.md5; "
                    f"printf '%s\\n' $a > {remote}/p7.done; sync")
        else:
            body = (f"{executable} watch > {remote}/{args.tag}.csv 2> {remote}/{args.tag}.err; a=$?; "
                    f"printf '%s\\n' $a > {remote}/{args.tag}.done; sync")
        started = datetime.now(timezone.utc).isoformat()
        launch(session, body)
        session["events"].append({"action": args.action, "tag": args.tag,
                                  "host_started_utc": started})
        args.session.write_text(json.dumps(session, indent=2) + "\n", encoding="utf-8")
        print("Launched detached", args.action, folder)
        return
    names = ("before.csv", "before.err", "pools.bin", "pools.err", "after.csv", "after.err",
             "baseline.md5", "baseline.done", "watch.csv", "watch.err", "watch.done", "launcher.log",
             "p7.bin", "p7.err", "p7.md5", "p7.done",
             args.tag + ".csv", args.tag + ".err", args.tag + ".done")
    with connect(session["host"]) as ftp:
        available = {Path(name).name for name in ftp.nlst(folder)}
        for name in dict.fromkeys(names):
            if name not in available:
                continue
            data = io.BytesIO()
            ftp.retrbinary("RETR " + folder + "/" + name, data.write)
            (args.session.parent / name).write_bytes(data.getvalue())
            print("Fetched", name, len(data.getvalue()))
    session["last_fetch_utc"] = datetime.now(timezone.utc).isoformat()
    args.session.write_text(json.dumps(session, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
