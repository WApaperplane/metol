#!/bin/bash
# test_link.sh —— 用 /tmp/dropbear-build 里已编好的 .o 试链接（验证 armv7-a 能否在非 PIE 下成立）
set -uo pipefail
SYS=/mnt/e/NXWA/nx500-modding-work/test_server/dropbear/dl/sysroot-g213
RF=/opt/nxks2/rootfs-112
LIBDIR=$SYS/usr/lib/arm-linux-gnueabi
cd /tmp/dropbear-build || exit 1
[ -d obj ] || { echo "obj/ 不存在"; exit 1; }

COMMON="-Wl,-z,now -Wl,-z,relro -nostartfiles -nodefaultlibs -Wl,-e,_start
 -Wl,--dynamic-linker=/lib/ld-linux.so.3 -Wl,--allow-shlib-undefined
 -Wl,-rpath-link,$RF/lib -Wl,-rpath-link,$RF/usr/lib
 $LIBDIR/crt1.o $LIBDIR/crti.o"

LIBS="-Wl,--start-group $RF/lib/libc-2.13.so $LIBDIR/libc_nonshared.a
 $RF/lib/libutil.so.1 $RF/lib/libcrypt.so.1 -Wl,--end-group -lgcc $LIBDIR/crtn.o"

for variant in "-no-pie" "-no-pie -Wl,-no-pie" "-no-pie -Wl,-no-pie -Wl,--no-dynamic-linker"; do
    echo "=== 尝试: $variant ==="
    arm-linux-gnueabi-gcc $COMMON $variant -o /tmp/db.test \
        obj/*.o libtomcrypt/libtomcrypt.a libtommath/libtommath.a $LIBS 2>/tmp/link.err
    if [ $? -eq 0 ]; then
        echo "  链接成功"
        ls -l /tmp/db.test | awk '{print "  size:", $5}'
        arm-linux-gnueabi-readelf -h /tmp/db.test | grep Type
        vfp=$(arm-linux-gnueabi-objdump -d /tmp/db.test | grep -cE '^\s+[0-9a-f]+:\s+[0-9a-f]+\s+v[a-z]')
        ldrd=$(arm-linux-gnueabi-objdump -d /tmp/db.test | grep -cE '\b(ldrd|strd)\b')
        movw=$(arm-linux-gnueabi-objdump -d /tmp/db.test | grep -cE '\b(movw|movt)\b')
        echo "  VFP/NEON=$vfp  ldrd/strd=$ldrd  movw/movt=$movw"
        break
    else
        echo "  失败:"; grep -oE "relocation [A-Z_]+|cannot find [^ ]+|undefined reference to [^']*" /tmp/link.err | sort -u | head -3
    fi
done
