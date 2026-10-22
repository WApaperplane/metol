#!/bin/sh
# install_key.sh —— 把客户端公钥装到 root 的 authorized_keys（dropbear 读 ~/.ssh/authorized_keys）
# 权限要求：home 不可 group/world 可写；.ssh 700；authorized_keys 600
H=/opt/home/root
K=/opt/storage/sdcard/_xfer/xiaoa.pub

mkdir -p "$H/.ssh" || exit 1
cat "$K" > "$H/.ssh/authorized_keys" || exit 1
chmod 700 "$H/.ssh"
chmod 600 "$H/.ssh/authorized_keys"
chmod 755 "$H"

echo "--- dirs ---"
ls -ld "$H" "$H/.ssh"
echo "--- key ---"
ls -l "$H/.ssh/authorized_keys"
cat "$H/.ssh/authorized_keys"
