/* nx_lutptr.arm -- 读写 p7 的 3DLUT 档位指针表（23 项，VA 0x80383A28）
 *
 * 为什么需要它：
 *   录像启动时 p7 会把 3DLUT 的 LUT0 指向它自己的内置档位表（实测在
 *   0x81158C00 / 0x8113BE00 之间变化），而不是用户 LUT 所在的 A18，
 *   所以"开录首帧带 LUT"不能靠开录后补写，只能让这张表本身指向 A18。
 *   表有 23 项（92 B），紧跟其后就是 ARM 代码（e12fff1e = bx lr），长度可判。
 *
 * 语义：
 *   dump <file>        导出 92 字节原表
 *   save <file>        当前表不是"全 A18"时才导出（避免把改过的表当原值）
 *   set <hexaddr>      23 项全部写成 addr
 *   check <hexaddr>    23 项是否全等于 addr（是则 exit 0，否则 1）
 *   restore <file>     从 92 字节文件恢复
 *
 * 安全性：地址与长度都在本文件内写死，不接受任意地址；写入是 RAM 操作，
 * 重启即回原值。改错只会让画面颜色不对，不会写固件。
 */
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#define LUTPTR_BASE 0x80383A28u
#define LUTPTR_N    23
#define LUTPTR_LEN  (LUTPTR_N * 4)
#define A18         0x81119F00u

static int same(const char *a, const char *b) { return strcmp(a, b) == 0; }

static unsigned char *map_table(int writable, int *mem_out, unsigned long *page_out)
{
    int mem;
    unsigned long page = LUTPTR_BASE & ~0xFFFu;
    void *p;
    mem = open("/dev/mem", writable ? (O_RDWR | O_SYNC) : (O_RDONLY | O_SYNC));
    if (mem < 0) { perror("open /dev/mem"); return NULL; }
    p = mmap(0, 4096, writable ? (PROT_READ | PROT_WRITE) : PROT_READ,
             MAP_SHARED, mem, (off_t)page);
    if (p == MAP_FAILED) { perror("mmap"); close(mem); return NULL; }
    *mem_out = mem;
    *page_out = page;
    return (unsigned char *)p;
}

static void unmap_table(unsigned char *p, int mem, unsigned long page)
{
    (void)page;
    msync(p, 4096, MS_SYNC);
    munmap(p, 4096);
    close(mem);
}

static unsigned long rd32(const unsigned char *p, int i)
{
    const unsigned char *q = p + (LUTPTR_BASE & 0xFFF) + i * 4;
    return (unsigned long)q[0] | ((unsigned long)q[1] << 8) |
           ((unsigned long)q[2] << 16) | ((unsigned long)q[3] << 24);
}

static void wr32(unsigned char *p, int i, unsigned long v)
{
    unsigned char *q = p + (LUTPTR_BASE & 0xFFF) + i * 4;
    q[0] = (unsigned char)(v & 0xFF);
    q[1] = (unsigned char)((v >> 8) & 0xFF);
    q[2] = (unsigned char)((v >> 16) & 0xFF);
    q[3] = (unsigned char)((v >> 24) & 0xFF);
}

static int all_a18(const unsigned char *p)
{
    int i;
    for (i = 0; i < LUTPTR_N; i++) if (rd32(p, i) != A18) return 0;
    return 1;
}

static int write_file(const char *path, const unsigned char *p)
{
    int fd = open(path, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    unsigned long i, off = LUTPTR_BASE & 0xFFF;
    ssize_t n;
    if (fd < 0) { perror("open out"); return 1; }
    n = write(fd, p + off, LUTPTR_LEN);
    close(fd);
    if (n != LUTPTR_LEN) { fprintf(stderr, "short write %ld\n", (long)n); return 1; }
    (void)i;
    return 0;
}

static int read_file(const char *path, unsigned char *buf)
{
    int fd = open(path, O_RDONLY);
    ssize_t n;
    if (fd < 0) { perror("open in"); return 1; }
    n = read(fd, buf, LUTPTR_LEN);
    close(fd);
    if (n != LUTPTR_LEN) { fprintf(stderr, "REFUSE: %s is %ld bytes, need %d\n", path, (long)n, LUTPTR_LEN); return 1; }
    return 0;
}

int main(int argc, char **argv)
{
    int mem = -1;
    unsigned long page = 0, addr = 0;
    unsigned char *p, buf[LUTPTR_LEN];
    char *end;
    int i;

    if (argc < 3) {
        fprintf(stderr, "usage: nx_lutptr.arm dump|save <file> | set|check <hexaddr> | restore <file>\n");
        return 2;
    }

    if (same(argv[1], "set") || same(argv[1], "check")) {
        addr = strtoul(argv[2], &end, 0);
        if (!*argv[2] || *end) return 2;
    }

    if (same(argv[1], "set")) {
        p = map_table(1, &mem, &page);
        if (!p) return 3;
        for (i = 0; i < LUTPTR_N; i++) wr32(p, i, addr);
        unmap_table(p, mem, page);
        p = map_table(0, &mem, &page);
        if (!p) return 3;
        {
            int bad = 0;
            for (i = 0; i < LUTPTR_N; i++) if (rd32(p, i) != addr) bad++;
            unmap_table(p, mem, page);
            printf("SET %08lx ITEMS %u MISMATCH %d\n", addr, LUTPTR_N, bad);
            return bad ? 4 : 0;
        }
    }

    if (same(argv[1], "check")) {
        int bad = 0;
        p = map_table(0, &mem, &page);
        if (!p) return 3;
        for (i = 0; i < LUTPTR_N; i++) if (rd32(p, i) != addr) bad++;
        unmap_table(p, mem, page);
        printf("CHECK %08lx MISMATCH %d\n", addr, bad);
        return bad ? 1 : 0;
    }

    if (same(argv[1], "dump") || same(argv[1], "save")) {
        int is_a18;
        p = map_table(0, &mem, &page);
        if (!p) return 3;
        is_a18 = all_a18(p);
        if (same(argv[1], "save") && is_a18) {
            unmap_table(p, mem, page);
            printf("ALREADY_A18 keep existing backup\n");
            return 0;
        }
        {
            int rc = write_file(argv[2], p);
            unmap_table(p, mem, page);
            if (rc) return rc;
        }
        printf("%s %s ITEMS %u\n", same(argv[1], "save") ? "SAVED" : "DUMPED", argv[2], LUTPTR_N);
        return 0;
    }

    if (same(argv[1], "restore")) {
        if (read_file(argv[2], buf)) return 2;
        p = map_table(1, &mem, &page);
        if (!p) return 3;
        for (i = 0; i < LUTPTR_N; i++) {
            unsigned long v = (unsigned long)buf[i * 4] | ((unsigned long)buf[i * 4 + 1] << 8) |
                              ((unsigned long)buf[i * 4 + 2] << 16) | ((unsigned long)buf[i * 4 + 3] << 24);
            wr32(p, i, v);
        }
        unmap_table(p, mem, page);
        printf("RESTORED %s\n", argv[2]);
        return 0;
    }

    fprintf(stderr, "unknown verb %s\n", argv[1]);
    return 2;
}
