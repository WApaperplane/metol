#!/bin/sh
# cleanup_20261025.sh —— SD 卡过时产物清理
# 原则：一律 mv 到 _trash_20261025/，不 rm，可回滚
# 不碰：DCIM / scripts / looks / lut / luts / emmcbak / filmlab(除两个误生成txt)
B=/opt/usr/nx-ks/busybox
T=/mnt/mmc/_trash_20261025
cd /mnt/mmc || exit 1

echo "=== 清理前 ==="
df -k /mnt/mmc | tail -1

mkdir -p "$T"

mvone() {
    if [ -e "$1" ]; then
        d=$(dirname "$1")
        [ "$d" != "." ] && mkdir -p "$T/$d"
        mv "$1" "$T/$1" 2>/dev/null && echo "MVD  $1"
    fi
}

# ---- ① 明确垃圾 ----
mvone filmlab/luts/mcbtest_usage.txt
mvone filmlab/luts/mcb_help.txt
mvone FOUND.000
mvone "System Volume Information"
mvone lut.sh.bak
mvone filmlab.sh.new
mvone filmlab.sh.bak
mvone filmlab/filmui.log
for f in *.log *.info; do mvone "$f"; done
for f in nxwa_fetch_13928.bin looks_94_20261025.tgz keysym_probe.out install_20261019.log evdev_probe.out; do mvone "$f"; done

# ---- ② 大件与实验产物 ----
mvone nx500.bin
for d in _xfer looks_bak_20261025 stage prefdump prefdump2 looks_94_20261025.tar \
         a1verify u5verify u6 u1; do mvone "$d"; done

# lc*/lb* 扇区实验目录（只匹配目录，且排除脚本）
for d in lc* lb*; do
    [ -d "$d" ] && mvone "$d"
done

# 早期零散产物
for f in dram_810f0000.bin dram_9e006000.bin dram_pools_256k.bin neg_test.bin \
         identity_a12.bin iq.txt lacc.sh CustomButtons-example.zip; do mvone "$f"; done

sync
echo "=== 清理后 ==="
df -k /mnt/mmc | tail -1
echo "trash 项数=$(ls -1 "$T" | wc -l)"
echo "looks=$(ls -1 /mnt/mmc/looks/*.bin 2>/dev/null | wc -l) 张"
echo "scripts 仍在: $([ -d /mnt/mmc/scripts ] && echo YES || echo NO)"
echo "DCIM 仍在: $([ -d /mnt/mmc/DCIM ] && echo YES || echo NO)"
echo "emmcbak 仍在: $([ -d /mnt/mmc/emmcbak ] && echo YES || echo NO)"
echo "=== done ==="
