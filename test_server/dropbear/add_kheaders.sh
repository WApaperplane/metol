#!/bin/bash
# add_kheaders.sh —— 给 glibc 2.13 sysroot 补上内核头（libc6-dev 不含 linux/ 与 asm/）
# 只要内核 uapi 头，绝不能把宿主的 glibc 头混进来（会造成 bits/ 错配）
SYS=/mnt/e/NXWA/nx500-modding-work/test_server/dropbear/dl/sysroot-g213
SRC=/usr/arm-linux-gnueabi/include
echo "== 宿主交叉内核头是否存在 =="
ls -d "$SRC/linux" "$SRC/asm" "$SRC/asm-generic" 2>&1
echo "== linux/ 条目数 =="
ls "$SRC/linux" 2>/dev/null | wc -l
echo "== 拷贝 =="
for d in linux asm asm-generic mtd sound video rdma; do
    if [ -d "$SRC/$d" ] && [ ! -e "$SYS/usr/include/$d" ]; then
        cp -a "$SRC/$d" "$SYS/usr/include/$d" && echo "  + $d"
    fi
done
echo "== 验证 =="
ls -l "$SYS/usr/include/linux/errno.h" 2>&1
ls -l "$SYS/usr/include/asm/unistd.h" 2>&1
