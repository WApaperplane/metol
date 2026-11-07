/* nx_mempeek.arm -- 用 mmap 从 /dev/mem 读任意物理地址，原样写到 stdout
 *
 * 为什么不用 dd：本机 /dev/mem 的 read() 对 RAM 区返回 EFAULT（Bad address），
 * 只有 mmap 能拿到；nx_slotwrite 的 mmap 窗口被限制在 LUT 池，
 * 这里补一个不设窗口的只读探针。
 *
 * 用法: nx_mempeek.arm <hexaddr> <len>      # 输出 len 字节二进制到 stdout
 * 例:   nx_mempeek.arm 0x80383A28 128 | od -An -tx4
 */
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

int main(int argc, char **argv) {
    unsigned long addr, len, page, off, done = 0;
    char *end;
    int mem;
    unsigned char *p;

    if (argc != 3) {
        fprintf(stderr, "usage: nx_mempeek.arm <hexaddr> <len>\n");
        return 2;
    }
    addr = strtoul(argv[1], &end, 0);
    if (!*argv[1] || *end) return 2;
    len = strtoul(argv[2], &end, 0);
    if (!*argv[2] || *end || len == 0 || len > 65536) return 2;

    page = addr & ~0xFFFul;
    off = addr - page;
    mem = open("/dev/mem", O_RDONLY | O_SYNC);
    if (mem < 0) { perror("open /dev/mem"); return 3; }
    p = mmap(0, off + len, PROT_READ, MAP_SHARED, mem, (off_t)page);
    if (p == MAP_FAILED) { perror("mmap"); close(mem); return 4; }

    while (done < len) {
        ssize_t n = write(1, p + off + done, len - done);
        if (n <= 0) { if (errno == EINTR) continue; break; }
        done += (unsigned long)n;
    }
    munmap(p, off + len);
    close(mem);
    return done == len ? 0 : 5;
}
