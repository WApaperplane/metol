"""Full-image string and enum-name index for the p7 chunk.

The p7 chunk is 0xB84280 bytes: code occupies roughly 0x020000-0x560000 and the
remaining ~6.4 MB is data. Rounds 1-4 scanned only the first 0x570000 bytes, so
this module exists to make the data segment searchable. It reads local bytes
only and never touches the camera.

Usage:
    python symbols.py                      # summary by prefix
    python symbols.py --grep AF_MODE       # substring filter
    python symbols.py --prefix eIQ_ID_     # prefix filter
    python symbols.py --near 0x700dd0      # strings around an offset
    python symbols.py --dump-json out/round5/symbols.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from trace_round2 import Survey

CODE_LIMIT = 0x570000          # rounds 1-4 only looked below this
STRING_RE = re.compile(rb"[ -~]{4,200}")

# Enum-name prefixes seen in the data segment. Each maps to the C++ type it
# most likely belongs to; the mapping is a working hypothesis, not proof.
PREFIX_GROUPS = {
    "eIQ_ID_": "IQ parameter identifiers",
    "eSMARTPRO_MODE_": "Smart Pro shooting modes",
    "eFOCUS_MODE_": "still-image AF mode",
    "eFOCUS_MOVIE_MODE_": "movie AF mode",
    "AFMODE_": "AF mode (older enum)",
    "MOVIE_AF_MODE_": "movie AF mode (older enum)",
    "eAF_MOVIE_SPEED_": "movie focus speed",
    "eAF_MOVIE_SENSITIVITY_": "movie focus responsiveness",
    "eAF_FOCUS_LIMIT_": "focus limiter",
    "eAF_ASSIST_LAMP_": "AF assist lamp",
    "eAF_LOCK_STATUS_": "AF lock",
    "FD_MODE_": "face detection mode",
    "MODE_": "object-tracking state",
    "AF_INVALID": "AF frame result",
}


def index_strings():
    s = Survey()
    rows = []
    for m in STRING_RE.finditer(s.image):
        try:
            text = m.group().decode("ascii")
        except UnicodeDecodeError:
            continue
        rows.append((m.start(), text))
    return s, rows


def group_of(text):
    for prefix, label in PREFIX_GROUPS.items():
        if text.startswith(prefix):
            return label
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--grep")
    ap.add_argument("--prefix")
    ap.add_argument("--near")
    ap.add_argument("--dump-json")
    args = ap.parse_args()

    s, rows = index_strings()
    print(f"p7 image {len(s.image):#x} bytes; {len(rows)} printable strings; "
          f"code/data split near {CODE_LIMIT:#x}", file=sys.stderr)

    if args.dump_json:
        payload = [{"offset": hex(off), "text": text, "group": group_of(text)}
                   for off, text in rows]
        out = Path(args.dump_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"wrote {out} ({len(payload)} rows)", file=sys.stderr)

    if args.near:
        centre = int(args.near, 0)
        for off, text in rows:
            if abs(off - centre) <= 0x300:
                print(f"  {off:#08x}  {text}")
        return

    selected = rows
    if args.grep:
        selected = [r for r in selected if args.grep in r[1]]
    if args.prefix:
        selected = [r for r in selected if r[1].startswith(args.prefix)]
    if args.grep or args.prefix:
        for off, text in selected:
            print(f"  {off:#08x}  {text}")
        print(f"--- {len(selected)} matches", file=sys.stderr)
        return

    counts = {}
    for off, text in rows:
        label = group_of(text)
        if label:
            counts.setdefault(label, []).append((off, text))
    for label, items in sorted(counts.items(), key=lambda kv: -len(kv[1])):
        lo = min(o for o, _ in items)
        hi = max(o for o, _ in items)
        print(f"{label:34s} {len(items):4d}  {lo:#08x}-{hi:#08x}")


if __name__ == "__main__":
    main()
