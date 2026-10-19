#!/bin/sh
# install_20261019.sh — 把 _xfer/20261019 里的新版本装到 /opt/usr/nx-ks
#
# 幂等：重复执行只是再拷一次。备份目录保留首次执行时的旧文件（.prev 不覆盖）。
# 输出同时写 stdout 与 /mnt/mmc/install_20261019.log，便于 FTP 取回核对。
set -u
B=/opt/usr/nx-ks
BK=$B/nxui/backup-lut-20261019
X=/mnt/mmc/_xfer/20261019
BB=$B/busybox
LOG=/mnt/mmc/install_20261019.log
: > "$LOG"

say() { echo "$@" | tee -a "$LOG"; }

say "=== NXUI 2026-10-19 安装 ==="
mkdir -p "$BK" || { say "FAIL mkdir $BK"; exit 1; }

# 备份：第一次才写 .prev，重复执行不会把"已装新版"当成旧版备份
for f in nxui/nxui.arm lut.sh lut/nx_regtabwrite.arm nxui.sh filmlab.sh; do
    n=$(echo "$f" | $BB tr '/' '_')
    if [ -f "$B/$f" ] && [ ! -f "$BK/$n.prev" ]; then
        cp "$B/$f" "$BK/$n.prev" && say "BACKUP $f -> $n.prev"
    fi
done

# 先落到临时名再 mv，避免面板正好启动时读到半个文件
for pair in \
    "nxui.arm:nxui/nxui.arm" \
    "lut.sh:lut.sh" \
    "nx_regtabwrite.arm:lut/nx_regtabwrite.arm" \
    "nxui.sh:nxui.sh" \
    "filmlab.sh:filmlab.sh"
do
    src=${pair%%:*}; dst=${pair##*:}
    [ -f "$X/$src" ] || { say "FAIL missing $X/$src"; exit 1; }
    cp "$X/$src" "$B/$dst.new" || { say "FAIL copy $src"; exit 1; }
    chmod 755 "$B/$dst.new"
    mv -f "$B/$dst.new" "$B/$dst" || { say "FAIL install $dst"; exit 1; }
    say "INSTALL $dst"
done
sync

say ""
say "=== MD5 (期望 n xui=8a7001d4 lut.sh=813b6d22 regtabwrite=896de680 nxui.sh=b0acc066 filmlab=48fe58a9) ==="
$BB md5sum "$B/nxui/nxui.arm" "$B/lut.sh" "$B/lut/nx_regtabwrite.arm" "$B/nxui.sh" "$B/filmlab.sh" | tee -a "$LOG"

say ""
say "=== BACKUP DIR ==="
ls -l "$BK" | tee -a "$LOG"
say "=== DONE ==="
