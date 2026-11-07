"""Export selected A32 disassembly and historical decompiler excerpts for review."""
import argparse
import bisect
from pathlib import Path
import re
import struct

from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_LITTLE_ENDIAN
from elftools.elf.elffile import ELFFile


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("kind", choices=["p7", "app", "mcbtest", "bridge"])
    ap.add_argument("addresses", nargs="+", type=lambda x: int(x, 0))
    ap.add_argument("--size", type=lambda x: int(x, 0))
    args = ap.parse_args()
    root = Path("E:/NXWA")
    out = Path(__file__).resolve().parent / "out"
    names = {}
    segments = []
    sizes = {}
    if args.kind == "p7":
        with (root / "fw/v1.12/NX500_v1.12.bin").open("rb") as f:
            f.seek(15680257)
            image = f.read(12075648)
        segments = [(0, len(image), 0)]
        for line in Path("E:/ghidra_out/52_pseudocode_index.txt").read_text(encoding="utf-8").splitlines():
            c = line.split("\t")
            if len(c) >= 3 and c[0].startswith("0x"):
                addr = int(c[0], 16)
                sizes[addr] = int(c[1])
                names[addr] = c[2]
        source = Path("E:/ghidra_out/53_all_pseudocode.c").read_text(encoding="utf-8", errors="replace")
        chunks = re.split(r"(?=^// ====)", source, flags=re.M)
        for chunk in chunks:
            m = re.match(r"// ==== .* @ (0x[0-9a-f]+) size=", chunk)
            if m and int(m.group(1), 16) in args.addresses:
                (out / ("p7_%08x_historical.c" % int(m.group(1), 16))).write_text(chunk, encoding="utf-8")
    else:
        rel = {"app": "fw/v1.12/extract/di-camera-app/com.samsung.di-camera-app/bin/di-camera-app", "mcbtest": "fw/v1.12/extract/usr-bin/mcbtest", "bridge": "fw/v1.12/extract/usr-lib/libmulticore-bridge.so"}[args.kind]
        path = root / rel
        image = path.read_bytes()
        with path.open("rb") as f:
            elf = ELFFile(f)
            segments = [(s["p_vaddr"], s["p_filesz"], s["p_offset"]) for s in elf.iter_segments() if s["p_type"] == "PT_LOAD"]
            for sec in elf.iter_sections():
                if sec.name not in (".symtab", ".dynsym"):
                    continue
                for sym in sec.iter_symbols():
                    if sym["st_value"] and sym["st_info"]["type"] == "STT_FUNC":
                        names[sym["st_value"]] = sym.name
                        sizes[sym["st_value"]] = sym["st_size"]

    def fileoff(addr):
        for base, length, offset in segments:
            if base <= addr < base + length:
                return addr - base + offset
        return None

    def stringval(val):
        if args.kind == "p7" and val >= 0x80000000:
            val -= 0x80000000
        off = fileoff(val)
        if off is None:
            return ""
        s = image[off:off + 240].split(b"\0", 1)[0]
        if len(s) < 3 or not all(x in (9, 10, 13) or 32 <= x <= 126 for x in s):
            return ""
        return repr(s.decode("ascii"))

    md = Cs(CS_ARCH_ARM, CS_MODE_ARM | CS_MODE_LITTLE_ENDIAN)
    for addr in args.addresses:
        size = args.size or sizes.get(addr, 0)
        if not size:
            raise SystemExit("No function size; supply --size")
        off = fileoff(addr)
        if off is None:
            raise SystemExit("Unmapped address")
        span_source = "explicit byte span" if args.size else ("historical boundary hint" if args.kind == "p7" else "ELF symbol size")
        lines = ["# %s @ 0x%x size=%d; disassembled from supplied binary; %s" % (names.get(addr, "unknown"), addr, size, span_source)]
        for ins in md.disasm(image[off:off + size], addr):
            word = struct.unpack("<I", ins.bytes)[0]
            annotation = ""
            if ins.mnemonic.startswith("bl") and ins.op_str.startswith("#"):
                target = int(ins.op_str[1:], 16)
                annotation = names.get(target, "")
            if (word & 0x0F7F0000) == 0x051F0000:
                pool = ins.address + 8 + ((word & 0xFFF) if word & 0x00800000 else -(word & 0xFFF))
                po = fileoff(pool)
                if po is not None and po + 4 <= len(image):
                    value = struct.unpack_from("<I", image, po)[0]
                    annotation = "pool=0x%x value=0x%x %s" % (pool, value, stringval(value))
            lines.append("%08x  %s  %-8s %-27s %s" % (ins.address, ins.bytes.hex(), ins.mnemonic, ins.op_str, annotation))
        dest = out / ("%s_%08x.asm" % (args.kind, addr))
        dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(dest.name, "size", size)


if __name__ == "__main__":
    main()
