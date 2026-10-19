"""package_nxui_release.py — 打 NXUI 上机包（LUT 修复 + 字体优化）

一个包解决两件事，因为它们共用同一个 nxui.arm：
  1. LUT 切换修复（双槽交替、退出不还原、半按排水）
  2. 首帧优化（GB2312 子集字体 + 只含 mod 目录的 fonts.conf）

包的用法见 docs/current/LUT_SWITCH_NOT_EFFECTIVE_2026-10-19.md §8。

用法: python package_nxui_release.py [输出路径]
"""
import hashlib
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
SCRIPTS = REPO / "scripts"
OUT = REPO.parent / "release" / "NXUI-LUT-FIX-20261019.zip"

# 包内路径 -> 仓库内源文件
FILES = {
    "scripts/nxui/nxui.arm": SCRIPTS / "nxui/nxui.arm",
    "scripts/nxui/fonts/NXUI_CJK.ttf": SCRIPTS / "nxui/fonts/NXUI_CJK.ttf",
    "scripts/nxui/fonts.conf": SCRIPTS / "nxui/fonts.conf",
    "scripts/nxui/install_nxui_fonts.sh": SCRIPTS / "nxui/install_nxui_fonts.sh",
    "scripts/nxui.sh": SCRIPTS / "nxui.sh",
    "scripts/filmlab.sh": SCRIPTS / "filmlab.sh",
    "scripts/lut.sh": SCRIPTS / "lut.sh",
    "scripts/lut/nx_regtabwrite.arm": SCRIPTS / "lut/nx_regtabwrite.arm",
    "scripts/lut/nx_slotwrite.arm": SCRIPTS / "lut/nx_slotwrite.arm",
    "scripts/lut/cube2lut.arm": SCRIPTS / "lut/cube2lut.arm",
    "scripts/lut/nx_regtabdump.arm": SCRIPTS / "lut/nx_regtabdump.arm",
    "lut_accept_20261019.sh": HERE.parent / "lutpipe/lut_accept_20261019.sh",
}


def main() -> int:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else OUT
    target.parent.mkdir(parents=True, exist_ok=True)

    missing = [str(src) for src in FILES.values() if not src.is_file()]
    if missing:
        print("missing:\n  " + "\n  ".join(missing))
        return 1

    # 清单先算，再一起写进包；确保 manifest 与包内字节一致
    manifest = "".join(
        f"{hashlib.md5(src.read_bytes()).hexdigest()}  {name}\n"
        for name, src in sorted(FILES.items())
    )
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for name, src in sorted(FILES.items()):
            info = zipfile.ZipInfo(name)
            info.compress_type = zipfile.ZIP_DEFLATED
            executable = src.suffix in (".sh", ".arm")
            info.external_attr = (0o100755 if executable else 0o100644) << 16
            z.writestr(info, src.read_bytes())
        info = zipfile.ZipInfo("manifest.md5")
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o100644 << 16
        z.writestr(info, manifest.encode())

    data = target.read_bytes()
    print(f"{target}")
    print(f"bytes={len(data)}")
    print(f"sha256={hashlib.sha256(data).hexdigest()}")
    print("--- manifest.md5 ---")
    print(manifest, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
