#!/bin/sh
# deploy_dropbear.sh —— 相机侧安装 dropbear（/opt/usr/nx-ks/dropbear，p14 刷机安全区）
# 由 telnet 调用：sh /mnt/mmc/_xfer/deploy_dropbear.sh
D=/opt/usr/nx-ks/dropbear
echo "=== 1. 落位二进制 ==="
mkdir -p "$D" || exit 1
cp -f /mnt/mmc/_xfer/dropbear.arm "$D/dropbear" || exit 1
cp -f /mnt/mmc/_xfer/dropbearkey.arm "$D/dropbearkey" || exit 1
chmod 755 "$D/dropbear" "$D/dropbearkey"
sync
ls -l "$D"

echo "=== 2. 生成 ed25519 host key ==="
if [ ! -f "$D/dropbear_ed25519_host_key" ]; then
    "$D/dropbearkey" -t ed25519 -f "$D/dropbear_ed25519_host_key" 2>&1 | grep -E "Fingerprint|Generating|Saving|error" | head -6
else
    echo "(已存在，跳过)"
fi
sync

echo "=== 3. 自检 ==="
"$D/dropbear" -V 2>&1 | head -2
"$D/dropbearkey" -h 2>&1 | head -2

echo "=== 4. 结果 ==="
ls -l "$D"
