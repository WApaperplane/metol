"""Build a small update package; no camera connection or firmware content."""
from pathlib import Path
import hashlib
import shutil
import zipfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
PAYLOAD = HERE / "out" / "package"
PAYLOAD.mkdir(exist_ok=True)
for name in ("filmlab.sh", "EV_AEL.sh", "EV_EV.sh", "loadgui.sh", "menu.sh", "telnet_toggle.sh", "nxui.sh"):
    dest = PAYLOAD / "scripts" / name; dest.parent.mkdir(exist_ok=True)
    shutil.copyfile(REPO / "scripts" / name, dest)
dest = PAYLOAD / "scripts/nxui"; dest.mkdir(exist_ok=True)
shutil.copyfile(HERE / "out/nxui.arm", dest / "nxui.arm")
shutil.copyfile(HERE / "vendor/LICENSE", dest / "NUKLEAR-LICENSE")
for name in ("install_camera.sh", "rollback_camera.sh", "README.md"):
    shutil.copyfile(HERE / name, PAYLOAD / name)
original = HERE / "out/device/original"
lines = []
for name in ("filmlab.sh", "EV_AEL.sh", "EV_EV.sh", "loadgui.sh", "menu.sh", "telnet_toggle.sh"):
    # Explicit baseline captured from the target camera, never guessed by version.
    lines.append(f"{hashlib.md5((original/name).read_bytes()).hexdigest()} {name}\n")
# A captured preceding NXUI engine is an allowed upgrade source as well. The
# camera's first-install backup stays unchanged for full rollback.
for previous_engine in (HERE / "out/slot-trial/filmlab-before.sh", HERE / "out/responsiveness/before/filmlab.sh"):
    if previous_engine.is_file():
        line = f"{hashlib.md5(previous_engine.read_bytes()).hexdigest()} filmlab.sh\n"
        if line not in lines: lines.append(line)
(PAYLOAD / "expected-original.md5").write_text("".join(lines), newline="\n")
files = sorted(p for p in PAYLOAD.rglob("*") if p.is_file() and p.name != "manifest.md5")
(PAYLOAD / "manifest.md5").write_text("".join(f"{hashlib.md5(p.read_bytes()).hexdigest()}  {p.relative_to(PAYLOAD).as_posix()}\n" for p in files), newline="\n")
for p in PAYLOAD.rglob("*"):
    if p.is_file() and p.suffix in (".sh", ".md5"):
        assert b"\r\n" not in p.read_bytes(), p
target = REPO.parent / "release/NXUI-Nuklear-20261018.zip"
target.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
    for p in sorted(PAYLOAD.rglob("*")):
        if p.is_file():
            info = zipfile.ZipInfo(p.relative_to(PAYLOAD).as_posix())
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o100755 if p.suffix == ".sh" or p.suffix == ".arm" else 0o100644) << 16
            archive.writestr(info, p.read_bytes())
print(target)
print("sha256=" + hashlib.sha256(target.read_bytes()).hexdigest())
