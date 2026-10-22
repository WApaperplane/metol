#!/bin/bash
# build_dropbear.sh —— 交叉编译 dropbear 到「相机 ABI」
#
# 依据（2026-10-22 探针实测 abi_probe.arm 已在相机上跑通）：
#   · 头文件：glibc 2.13 sysroot（eglibc 2.13-20ubuntu5.3 armel）
#     —— 宿主的 2.39 头会让 stat 变成裸符号，而相机 libc 只有 __xstat@GLIBC_2.4
#   · crt1.o/crti.o/crtn.o/libc_nonshared.a：同款 2.13（宿主 crt1.o 会要 GLIBC_2.34）
#   · 运行库：直链相机 /lib/libc-2.13.so 等（rootfs-112 提取）
#   · 必须在 -O0（项目硬性）
#
# 运行：wsl -d NXKS2 bash /mnt/e/NXWA/nx500-modding-work/test_server/dropbear/build_dropbear.sh
set -uo pipefail

ROOT=/mnt/e/NXWA/nx500-modding-work/test_server/dropbear
SYS=$ROOT/dl/sysroot-g213
RF=/opt/nxks2/rootfs-112
LIBDIR=$SYS/usr/lib/arm-linux-gnueabi
GCCINC=$(arm-linux-gnueabi-gcc -print-file-name=include)
BUILD=/tmp/dropbear-build
SRCVER=dropbear-2024.86

# ★ 优化级别可切：默认 -O0（项目历史铁律，来源是 zig 0.13 的 ARM 后端，见 README「-O0 溯源」）
#   传 -O2 会输出到 out-O2/，用于对比，不覆盖正式产物
OPT=${1:--O0}
EXTRA=${2:-}
OUTDIR="$ROOT/out"
[ "$OPT" != "-O0" ] && OUTDIR="$ROOT/out${OPT}"
[ -n "$EXTRA" ] && OUTDIR="$ROOT/out-test"

export CFLAGS="$OPT -nostdinc \
 -isystem $SYS/usr/include -isystem $SYS/usr/include/arm-linux-gnueabi -isystem $GCCINC \
 -U_TIME_BITS -D_TIME_BITS=32 \
 -U_FILE_OFFSET_BITS -D_FILE_OFFSET_BITS=32 \
 -mfloat-abi=soft -fno-pic -fno-stack-protector $EXTRA"

export LDFLAGS="-nostartfiles -nodefaultlibs -no-pie \
 -Wl,-e,_start -Wl,--dynamic-linker=/lib/ld-linux.so.3 \
 -Wl,--allow-shlib-undefined -Wl,-rpath-link,$RF/lib -Wl,-rpath-link,$RF/usr/lib \
 $LIBDIR/crt1.o $LIBDIR/crti.o"

export LIBS="-Wl,--start-group \
 $RF/lib/libc-2.13.so $LIBDIR/libc_nonshared.a \
 $RF/lib/libutil.so.1 $RF/lib/libcrypt.so.1 \
 -Wl,--end-group -lgcc $LIBDIR/crtn.o"

echo "== 准备源码树（拷到 /tmp 避免 drvfs mtime 问题）=="
rm -rf "$BUILD"
cp -a "$ROOT/$SRCVER" "$BUILD" || exit 1
cd "$BUILD" || exit 1

# ★ 根分区是 ext4(ro) 只读 ⇒ /usr/libexec 写不进去，
#   sftp-server 只能落在 p14（/opt/usr），所以路径要编译期改掉，不能靠装到默认位置
sed -i 's|^#define SFTPSERVER_PATH .*|#define SFTPSERVER_PATH "/opt/usr/nx-ks/dropbear/sftp-server"|' \
    src/default_options.h
grep -n 'SFTPSERVER_PATH' src/default_options.h | head -2


echo "== configure =="
./configure --host=arm-linux-gnueabi \
    --enable-bundled-libtom \
    --disable-zlib \
    --disable-syslog \
    --disable-shadow \
    --disable-lastlog \
    --disable-utmp --disable-utmpx \
    --disable-wtmp --disable-wtmpx \
    --disable-pututline --disable-pututxline \
    CC=arm-linux-gnueabi-gcc \
    LTM_CFLAGS="$OPT $EXTRA" \
    > /tmp/dropbear-conf.log 2>&1
rc=$?
echo "configure rc=$rc"
[ $rc -ne 0 ] && tail -25 /tmp/dropbear-conf.log && exit 1
grep -E "^(Host type|CFLAGS|LDFLAGS|LIBS)" Makefile | head -5

# ★ configure 探测到宿主支持 PIE 会往 LDFLAGS 塞 -Wl,-pie，必须去掉：
#   相机的 crt1.o（glibc 2.13）是 non-PIE 的；而 -march=armv7-a 会生成 movw/movt
#   ⇒ R_ARM_MOVW_ABS_NC 重定位在 PIE 下非法（"can not be used when making a shared object"）
sed -i 's/ -Wl,-pie//g' Makefile 2>/dev/null
sed -i 's/ -fPIE//g' Makefile 2>/dev/null

echo "== make =="
make -j4 PROGRAMS="dropbear dropbearkey" > /tmp/dropbear-make.log 2>&1
rc=$?
echo "make rc=$rc"
if [ $rc -ne 0 ]; then
    grep -E "error|Error|undefined" /tmp/dropbear-make.log | head -25
    exit 1
fi

echo "== 产物 =="
mkdir -p "$OUTDIR"
for p in dropbear dropbearkey; do
    if [ -f "$p" ]; then
        cp "$p" "$OUTDIR/$p.arm"
        echo "--- $p.arm ---"
        ls -lh "$OUTDIR/$p.arm"
        arm-linux-gnueabi-readelf -d "$OUTDIR/$p.arm" | grep NEEDED
        echo -n "version needs: "
        arm-linux-gnueabi-readelf -V "$OUTDIR/$p.arm" | grep -oE 'GLIBC_[0-9.]+' | sort -u -V | tr '\n' ' '
        echo
    fi
done
