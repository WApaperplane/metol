/* nx_slotwrite.c — write one 19,712-byte LUT slot into the P7 pool.
 *
 * commit : back up the current slot bytes to <backup>, then write <src>
 * restore: write <src> (the backup) back and verify
 * write  : write <src> without touching the backup file
 * read   : dump the slot to <file> (file argument is the destination)
 * dry    : compare <src> against the slot without writing
 *
 * Only addresses inside the relocation window [0x81006000, 0x813EE4C0) are
 * accepted, so a typo cannot land in the code segment.
 * No ioctl, no firmware access, nothing outside the one slot is touched.
 * A power cycle restores the image copy, so every write is reversible.
 *
 * Build: ARM EABI, -nostdlib -static -O0 -marm -mfloat-abi=soft.
 */
#include <asm/unistd.h>
#include <fcntl.h>
#include <sys/mman.h>

#define SLOT_LEN  19712u
#define POOL_LO   0x81006000u
#define POOL_HI   0x813EE4C0u

static unsigned char orig[SLOT_LEN];
static unsigned char src[SLOT_LEN];

static int sc3(int n, int a, int b, int c)
{
    register int r0 __asm__("r0") = a;
    register int r1 __asm__("r1") = b;
    register int r2 __asm__("r2") = c;
    register int r7 __asm__("r7") = n;
    __asm__ volatile("svc 0" : "+r"(r0) : "r"(r1), "r"(r2), "r"(r7) : "memory", "cc");
    return r0;
}

static int sc6(int n, int a, int b, int c, int d, int e, int f)
{
    register int r0 __asm__("r0") = a;
    register int r1 __asm__("r1") = b;
    register int r2 __asm__("r2") = c;
    register int r3 __asm__("r3") = d;
    register int r4 __asm__("r4") = e;
    register int r5 __asm__("r5") = f;
    register int r7 __asm__("r7") = n;
    __asm__ volatile("svc 0" : "+r"(r0) : "r"(r1), "r"(r2), "r"(r3), "r"(r4),
                     "r"(r5), "r"(r7) : "memory", "cc");
    return r0;
}

static int write_all(int fd, const void *buffer, unsigned size)
{
    const char *p = (const char *)buffer;
    while (size) {
        int n = sc3(__NR_write, fd, (int)p, (int)size);
        if (n == -4) continue;
        if (n <= 0) return -1;
        p += n;
        size -= (unsigned)n;
    }
    return 0;
}

static int read_full(int fd, void *buffer, unsigned size)
{
    char *p = (char *)buffer;
    unsigned done = 0;
    while (done < size) {
        int n = sc3(__NR_read, fd, (int)(p + done), (int)(size - done));
        if (n == -4) continue;
        if (n <= 0) return -1;
        done += (unsigned)n;
    }
    return 0;
}

static unsigned length(const char *s) { unsigned n = 0; while (s[n]) ++n; return n; }
static void say(const char *s) { write_all(1, s, length(s)); }
static int equal(const char *a, const char *b)
{ while (*a && *a == *b) { ++a; ++b; } return *a == *b; }

static char *hex(char *p, unsigned int value)
{
    static const char digits[] = "0123456789abcdef";
    int shift;
    *p++ = '0'; *p++ = 'x';
    for (shift = 28; shift >= 0; shift -= 4) *p++ = digits[(value >> shift) & 15];
    return p;
}

static void putu(const char *label, unsigned v)
{
    char b[96], *p = b;
    unsigned d[10], k = 0, j;
    const char *s;
    for (s = label; *s; ++s) *p++ = *s;
    if (!v) d[k++] = 0;
    while (v) { d[k++] = v % 10u; v /= 10u; }
    for (j = k; j > 0; --j) *p++ = (char)('0' + d[j - 1]);
    *p++ = '\n';
    write_all(1, b, (unsigned)(p - b));
}

static unsigned parse_hex(const char *s)
{
    unsigned v = 0;
    if (s[0] == '0' && (s[1] == 'x' || s[1] == 'X')) s += 2;
    while (*s) {
        char c = *s++;
        unsigned d;
        if (c >= '0' && c <= '9') d = (unsigned)(c - '0');
        else if (c >= 'a' && c <= 'f') d = (unsigned)(c - 'a') + 10u;
        else if (c >= 'A' && c <= 'F') d = (unsigned)(c - 'A') + 10u;
        else break;
        v = (v << 4) | d;
    }
    return v;
}

static int load_file(const char *path, unsigned char *dst, unsigned want)
{
    int fd = sc3(__NR_open, (int)path, O_RDONLY, 0);
    int ok;
    if (fd < 0) { say("FAIL open source file\n"); return -1; }
    ok = read_full(fd, dst, want);
    sc3(__NR_close, fd, 0, 0);
    if (ok < 0) { say("FAIL short source file\n"); return -1; }
    return 0;
}

static int save_file(const char *path, const unsigned char *data, unsigned n)
{
    int fd = sc3(__NR_open, (int)path, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    int ok;
    if (fd < 0) { say("FAIL create backup file\n"); return -1; }
    ok = write_all(fd, data, n);
    sc3(__NR_close, fd, 0, 0);
    return ok;
}

static void barrier(void)
{ __asm__ volatile("mcr p15, 0, %0, c7, c10, 4" :: "r"(0) : "memory"); }

static unsigned diff_count(const unsigned char *a, const unsigned char *b)
{
    unsigned i, n = 0;
    for (i = 0; i < SLOT_LEN; ++i) if (a[i] != b[i]) ++n;
    return n;
}

int nx_main(unsigned *initial_stack)
{
    unsigned argc = initial_stack[0];
    char **argv = (char **)(initial_stack + 1);
    const char *mode, *src_path, *bak_path = 0;
    unsigned addr, page, span, off;
    void *base = 0;
    int fd = 0, rc = 1;
    unsigned char *slot;
    unsigned diff;

    say("=== slotwrite (one 19712-byte LUT slot) ===\n");
    if (argc < 4) {
        say("usage: nx_slotwrite.arm commit|restore|dry <hexaddr> <file> [backup]\n");
        return 1;
    }
    mode = argv[1];
    addr = parse_hex(argv[2]);
    src_path = argv[3];
    if (argc >= 5) bak_path = argv[4];

    if (!(equal(mode, "commit") || equal(mode, "restore") || equal(mode, "dry")
          || equal(mode, "read") || equal(mode, "write"))) {
        say("FAIL unknown mode\n");
        return 1;
    }
    if (addr < POOL_LO || addr + SLOT_LEN > POOL_HI) {
        say("REFUSE: address outside the relocation window\n");
        return 1;
    }
    if ((addr & 3u) != 0) { say("REFUSE: address not word aligned\n"); return 1; }
    if (equal(mode, "commit") && !bak_path) { say("REFUSE: commit needs a backup path\n"); return 1; }

    page = addr & ~0xFFFu;
    off = addr - page;
    span = (off + SLOT_LEN + 0xFFFu) & ~0xFFFu;

    {
        int writable = !(equal(mode, "dry") || equal(mode, "read"));
        fd = sc3(__NR_open, (int)"/dev/mem", (writable ? O_RDWR : O_RDONLY) | O_SYNC, 0);
        if (fd < 0) { say("FAIL open /dev/mem\n"); return 1; }
        base = (void *)(unsigned)sc6(__NR_mmap2, 0, (int)span,
                                     writable ? (PROT_READ | PROT_WRITE) : PROT_READ,
                                     MAP_SHARED, fd, (int)(page >> 12));
    }
    if ((unsigned)base >= 0xFFFFF000u) { say("FAIL mmap\n"); sc3(__NR_close, fd, 0, 0); return 1; }
    slot = (unsigned char *)base + off;

    say("MODE "); say(mode); say("\nADDR "); { char b[16], *p = b; p = hex(p, addr); *p++ = '\n'; write_all(1, b, (unsigned)(p - b)); }

    for (off = 0; off < SLOT_LEN; ++off) orig[off] = slot[off];

    /* read mode: the file argument is the destination, nothing is written to RAM */
    if (equal(mode, "read")) {
        if (save_file(src_path, orig, SLOT_LEN) < 0) { rc = 1; goto out; }
        say("SLOT dumped to output path\n");
        rc = 0;
        goto out;
    }

    if (load_file(src_path, src, SLOT_LEN) < 0) { rc = 1; goto out; }

    diff = diff_count(orig, src);
    putu("SOURCE differs from current slot bytes = ", diff);

    if (equal(mode, "dry")) { rc = 0; goto out; }

    if (equal(mode, "commit")) {
        if (save_file(bak_path, orig, SLOT_LEN) < 0) { rc = 1; goto out; }
        say("BACKUP written\n");
    }

    {
        unsigned i;
        for (i = 0; i < SLOT_LEN; ++i) slot[i] = src[i];
    }
    barrier();

    diff = diff_count((const unsigned char *)slot, src);
    putu("READBACK mismatched bytes = ", diff);
    if (diff != 0) { say("FAIL readback\n"); rc = 1; goto out; }
    say("READBACK ok\n");
    rc = 0;

out:
    sc3(__NR_munmap, (int)base, (int)span, 0);
    sc3(__NR_close, fd, 0, 0);
    say(rc == 0 ? "=== done ===\n" : "=== FAILED ===\n");
    return rc;
}

__asm__(".global _start\n"
        "_start:\n"
        "mov r0, sp\n"
        "bl nx_main\n"
        "mov r7, #1\n"
        "svc 0\n");
