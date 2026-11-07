/* nx_mempoke.arm -- 把一段字节写到任意物理地址（mmap 写，不设窗口）
 *
 * 仅供实验：p7 数据段的指针表改写。写入是 RAM 操作，重启即恢复，
 * 但改错地址可能让 p7 异常（黑屏/卡死），务必先备份。
 *
 * 用法:
 *   nx_mempoke.arm poke <hexaddr> <file>   # 把 file 全部字节写到 addr
 *   nx_mempoke.arm dry  <hexaddr> <file>   # 只比对，不写
 */
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

static int same(const char *a, const char *b) { return strcmp(a, b) == 0; }

int main(int argc, char **argv) {
    unsigned long addr, page, off, len;
    char *end;
    int mem, fd, dry;
    unsigned char *p, *buf;
    off_t sz;
    unsigned long i, diff = 0;

    if (argc != 4) {
        fprintf(stderr, "usage: nx_mempoke.arm poke|dry <hexaddr> <file>\n");
        return 2;
    }
    if (!same(argv[1], "poke") && !same(argv[1], "dry")) return 2;
    dry = same(argv[1], "dry");

    addr = strtoul(argv[2], &end, 0);
    if (!*argv[2] || *end) return 2;

    fd = open(argv[3], O_RDONLY);
    if (fd < 0) { perror("open src"); return 3; }
    /* 不用 fstat：glibc 2.13 + _TIME_BITS=32 下它是 __fxstat 内联，-nostdlib 链不到 */
    sz = lseek(fd, 0, SEEK_END);
    if (sz <= 0) { fprintf(stderr, "REFUSE empty src\n"); close(fd); return 2; }
    if (lseek(fd, 0, SEEK_SET) != 0) { close(fd); return 3; }
    len = (unsigned long)sz;
    if (len == 0 || len > 4096) { fprintf(stderr, "REFUSE length %lu (1..4096)\n", len); close(fd); return 2; }
    buf = malloc(len);
    if (!buf) { close(fd); return 3; }
    if (read(fd, buf, len) != (ssize_t)len) { fprintf(stderr, "short read\n"); close(fd); free(buf); return 3; }
    close(fd);

    page = addr & ~0xFFFul;
    off = addr - page;
    if (off + len > 4096) { fprintf(stderr, "REFUSE crosses page: off=%lu len=%lu\n", off, len); free(buf); return 2; }

    mem = open("/dev/mem", dry ? (O_RDONLY | O_SYNC) : (O_RDWR | O_SYNC));
    if (mem < 0) { perror("open /dev/mem"); free(buf); return 3; }
    p = mmap(0, 4096, dry ? PROT_READ : (PROT_READ | PROT_WRITE), MAP_SHARED, mem, (off_t)page);
    if (p == MAP_FAILED) { perror("mmap"); close(mem); free(buf); return 4; }

    for (i = 0; i < len; i++) if (p[off + i] != buf[i]) diff++;

    printf("ADDR %08lx LEN %lu DIFF %lu MODE %s\n", addr, len, diff, argv[1]);

    if (!dry && diff) {
        memcpy(p + off, buf, len);
        /* 读回确认 */
        diff = 0;
        for (i = 0; i < len; i++) if (p[off + i] != buf[i]) diff++;
        printf("READBACK_MISMATCH %lu\n", diff);
    }
    munmap(p, 4096);
    close(mem);
    free(buf);
    return 0;
}
