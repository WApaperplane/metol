import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_LITTLE_ENDIAN
from trace_round2 import Survey

s = Survey()
md = Cs(CS_ARCH_ARM, CS_MODE_ARM | CS_MODE_LITTLE_ENDIAN)
N = len(s.image)


def calls_to(target):
    out = []
    for off in range(0, N - 4, 4):
        w = s.u32(off)
        if w >> 28 == 0xF:
            continue
        if (w & 0x0E000000) != 0x0A000000 or not (w & 0x1000000):
            continue
        delta = (w & 0xFFFFFF) << 2
        if delta & 0x2000000:
            delta -= 0x4000000
        if ((off + 8 + delta) & 0xFFFFFFFF) == target:
            out.append(off)
    return out


hits = calls_to(0x236A10)
print(f"callers of 0x236a10 (lens attribute by id): {len(hits)}")
for at in hits:
    r2 = None
    for back in range(at - 4, max(at - 0x30, 0), -4):
        got = list(md.disasm(s.image[back:back + 4], back, count=1))
        if not got:
            continue
        ins = got[0]
        ops = [o.strip() for o in ins.op_str.split(",")]
        if len(ops) >= 2 and ops[0] in ("r2", "r3") and ins.mnemonic in ("mov", "movw"):
            try:
                val = int(ops[1].lstrip("#"), 16)
            except ValueError:
                continue
            if ins.mnemonic == "movw":
                r2 = val
                break
            if r2 is None:
                r2 = val
    ow = s.owner(at)
    print(f"  {at:#09x}  id_guess={r2 if r2 is None else hex(r2)}"
          f"  owner={ow['name_hint'] if ow else None}")
