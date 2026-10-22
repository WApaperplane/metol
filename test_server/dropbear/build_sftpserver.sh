#!/bin/bash
# build_sftpserver.sh —— 单编 OpenSSH 的 sftp-server（补 dropbear 缺的 SFTP 子系统）
#
# dropbear 官方不提供 sftp-server（default_options.h 里明写），所以 scp/sftp 全废。
# 这里从 OpenSSH 源码只编 sftp-server 一个目标，用同一套「相机 ABI 三件套」链接：
#   glibc 2.13 的 crt1/crti/crtn + libc_nonshared.a + 机身 libc-2.13.so
#
# 运行：wsl -d NXKS2 bash /mnt/e/NXWA/nx500-modding-work/test_server/dropbear/build_sftpserver.sh
set -uo pipefail
OPT=${1:--O0}

ROOT=/mnt/e/NXWA/nx500-modding-work/test_server/dropbear
SYS=$ROOT/dl/sysroot-g213
RF=/opt/nxks2/rootfs-112
LIBDIR=$SYS/usr/lib/arm-linux-gnueabi
GCCINC=$(arm-linux-gnueabi-gcc -print-file-name=include)
BUILD=/tmp/openssh-build
VER=openssh-9.9p1

export CFLAGS="$OPT -nostdinc \
 -isystem $SYS/usr/include -isystem $SYS/usr/include/arm-linux-gnueabi -isystem $GCCINC \
 -U_TIME_BITS -D_TIME_BITS=32 \
 -U_FILE_OFFSET_BITS -D_FILE_OFFSET_BITS=32 \
 -mfloat-abi=soft -fno-pic -fno-stack-protector"

export LDFLAGS="-nostartfiles -nodefaultlibs -no-pie \
 -Wl,-e,_start -Wl,--dynamic-linker=/lib/ld-linux.so.3 \
 -Wl,--allow-shlib-undefined -Wl,-rpath-link,$RF/lib -Wl,-rpath-link,$RF/usr/lib \
 $LIBDIR/crt1.o $LIBDIR/crti.o"

export LIBS="-Wl,--start-group \
 $RF/lib/libc-2.13.so $LIBDIR/libc_nonshared.a \
 $RF/lib/libutil.so.1 \
 -Wl,--end-group -lgcc $LIBDIR/crtn.o"

echo "== 准备源码 =="
rm -rf "$BUILD"
mkdir -p "$BUILD"
tar xzf "$ROOT/dl/openssh.tar.gz" -C "$BUILD" || exit 1
cd "$BUILD/$VER" || exit 1

# OpenSSH 的 Makefile 给 sftp-server 硬编码了 -lutil，得让 -L 能找到 libutil.so
# （机身只提供 libutil.so.1，SONAME 就是 libutil.so.1，改个名不影响结果）
if [ ! -e "$LIBDIR/libutil.so" ]; then
    ln -sf "$RF/lib/libutil.so.1" "$LIBDIR/libutil.so"
    echo "  + libutil.so -> 机身 libutil.so.1"
fi

echo "== configure =="
./configure --host=arm-linux-gnueabi \
    --without-openssl --without-zlib \
    --without-pam --disable-strip \
    --disable-etc-default-login \
    --prefix=/opt/usr/nx-ks/dropbear \
    CC=arm-linux-gnueabi-gcc \
    > /tmp/ssh-conf.log 2>&1
rc=$?
echo "configure rc=$rc"
if [ $rc -ne 0 ]; then
    tail -30 /tmp/ssh-conf.log
    exit 1
fi

echo "== make sftp-server =="
# 先让 make 编完所有 .o；链接若因 -lutil 路径失败，下面改手动链接
make -j4 sftp-server > /tmp/ssh-make.log 2>&1
rc=$?
echo "make rc=$rc"

OBJS=$(grep -oE '[A-Za-z0-9_./-]+\.o' /tmp/ssh-make.log | sort -u | tr '\n' ' ')
if [ -z "$OBJS" ]; then
    echo "拿不到对象列表，看 make 日志："
    grep -E "error|Error" /tmp/ssh-make.log | head -20
    exit 1
fi

if [ -f sftp-server ] && [ $rc -eq 0 ]; then
    echo "== make 直接成功 =="
else
    echo "== 手动链接（绕开 Makefile 的 -lutil）=="
    arm-linux-gnueabi-gcc $LDFLAGS -o sftp-server $OBJS $LIBS -Wl,-rpath-link,"$LIBDIR" || {
        echo "手链失败"; grep -E "undefined reference" /tmp/ssh-make.log | sort -u | head -20; exit 1; }
fi

echo "== 产物 =="
mkdir -p "$ROOT/out"
cp sftp-server "$ROOT/out/sftp-server.arm"
ls -lh "$ROOT/out/sftp-server.arm"
echo -n "NEEDED: "; arm-linux-gnueabi-readelf -d "$ROOT/out/sftp-server.arm" | grep NEEDED | sed 's/.*\[//;s/\]//' | tr '\n' ' '; echo
echo -n "version needs: "; arm-linux-gnueabi-readelf -V "$ROOT/out/sftp-server.arm" | grep -oE 'GLIBC_[0-9.]+' | sort -u -V | tr '\n' ' '; echo
