/* nx_regtabdump.c — read-only dump of the three static LUT address registries.
 *
 * Purpose: decide whether the code-segment registry constants are readable
 * from the ARM side through /dev/mem, which is the precondition for the
 * "retarget a registry entry" route (change 4 bytes -> P7 loads our table on
 * its next normal load, with no sentinel and no content race).
 *
 * Positive control: the relocation loop instructions at 0x80011620. Their
 * bytes are known from the A2 image, so a mismatch means the code segment is
 * not reachable this way (rather than the registry being absent).
 * Target: 0x80380000..0x80383FFF holds View4 @0x803837F0, Still6 @0x80382C5C
 * and BV12 @0x80382B00 (A2 image layout, T4 registry).
 *
 * No ioctl, no private d5 device, no writable mapping, no register store.
 * Diagnostics go to stdout; the 16 KiB raw dump goes to the SD card.
 * Build: ARM EABI, -nostdlib -static -O0 -marm -mfloat-abi=soft.
 */
#include <asm/unistd.h>
#include <fcntl.h>
#include <sys/mman.h>

#define CTRL_ADDR   0x80011000u
#define CTRL_PAGE   4096u
#define CTRL_ITEM   0x80011620u
#define TAB_ADDR    0x80380000u
#define TAB_SIZE    0x4000u
#define OUT_PATH    "/mnt/mmc/regtab_80380000_16k.bin"

/* Page offsets are absolute_va - TAB_ADDR; the registries live in the last
 * page of the window (0x80383000), not in the first one. */
#define VIEW_AT     0x37F0u
#define STILL_AT    0x2C5Cu
#define BV_AT       0x2B00u

static const unsigned int view_expect[4] = {
    0x810FD100u, 0x81101E00u, 0x81106B00u, 0x81115200u
};
static const unsigned int still_expect[6] = {
    0x81119F00u, 0x81115200u, 0x8111EC00u, 0x8110B800u, 0x81106B00u, 0x81110500u
};
static const unsigned int bv_expect[12] = {
    0x8116C000u, 0x81175A00u, 0x81167300u, 0x81170D00u, 0x81184100u, 0x810FD100u,
    0x81188E00u, 0x81101E00u, 0x8115D900u, 0x8117A700u, 0x81162600u, 0x8117F400u
};
static const unsigned int ctrl_expect[4] = {
    0xE59F1138u, 0xE59F2138u, 0xE59F3138u, 0xF5D1F0C0u
};

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

static unsigned length(const char *s)
{
    unsigned n = 0;
    while (s[n]) ++n;
    return n;
}

static void say(const char *s) { write_all(1, s, length(s)); }

static void hex8(char **out, unsigned int value)
{
    static const char digits[] = "0123456789abcdef";
    int shift;
    char *p = *out;
    *p++ = '0'; *p++ = 'x';
    for (shift = 28; shift >= 0; shift -= 4) *p++ = digits[(value >> shift) & 15];
    *out = p;
}

static void dec(char **out, unsigned int value)
{
    char tmp[12];
    int i = 0, j;
    char *p = *out;
    if (value == 0) tmp[i++] = '0';
    while (value) { tmp[i++] = (char)('0' + (value % 10u)); value /= 10u; }
    for (j = i - 1; j >= 0; --j) *p++ = tmp[j];
    *out = p;
}

/* Emit "addr: v0 v1 ... [ok/total]" for one registry. */
static void report(const char *label, unsigned int base, const volatile unsigned *words,
                   const unsigned int *expect, unsigned count)
{
    char line[256], *out = line;
    unsigned i, ok = 0;
    const char *s;
    for (s = label; *s; ++s) *out++ = *s;
    *out++ = ':';
    for (i = 0; i < count; ++i) {
        unsigned int seen = words[i];
        *out++ = ' ';
        hex8(&out, seen);
        if (seen == expect[i]) ++ok;
    }
    *out++ = ' '; *out++ = '[';
    dec(&out, ok);
    *out++ = '/';
    dec(&out, count);
    *out++ = ']';
    *out++ = '\n';
    write_all(1, line, (unsigned)(out - line));
    (void)base;
}

int nx_main(void)
{
    unsigned int ctrl_ptr, tab_ptr;
    int fd, out_fd, rc;
    volatile unsigned int *ctrl, *tab;

    say("=== regtabdump (read-only, no writes) ===\n");

    fd = sc3(__NR_open, (int)"/dev/mem", O_RDONLY | O_SYNC, 0);
    if (fd < 0) { say("FAIL open /dev/mem O_RDONLY|O_SYNC\n"); return 1; }

    ctrl_ptr = (unsigned int)sc6(__NR_mmap2, 0, (int)CTRL_PAGE, PROT_READ,
                                 MAP_SHARED, fd, (int)(CTRL_ADDR >> 12));
    if (ctrl_ptr >= 0xFFFFF000u) {
        say("FAIL mmap control page 0x80011000 (code segment unreachable)\n");
        sc3(__NR_close, fd, 0, 0);
        return 1;
    }
    ctrl = (volatile unsigned int *)(ctrl_ptr + (CTRL_ITEM - CTRL_ADDR));
    report("CTRL 0x80011620 (known code bytes)", CTRL_ITEM, ctrl, ctrl_expect, 4);

    tab_ptr = (unsigned int)sc6(__NR_mmap2, 0, (int)TAB_SIZE, PROT_READ,
                                MAP_SHARED, fd, (int)(TAB_ADDR >> 12));
    if (tab_ptr >= 0xFFFFF000u) {
        say("FAIL mmap registry page 0x80380000 (target unreachable)\n");
        sc3(__NR_close, fd, 0, 0);
        return 1;
    }
    tab = (volatile unsigned int *)tab_ptr;

    report("VIEW4 @0x803837F0", TAB_ADDR + VIEW_AT, tab + (VIEW_AT >> 2), view_expect, 4);
    report("STILL6 @0x80382C5C", TAB_ADDR + STILL_AT, tab + (STILL_AT >> 2), still_expect, 6);
    report("BV12 @0x80382B00", TAB_ADDR + BV_AT, tab + (BV_AT >> 2), bv_expect, 12);

    out_fd = sc3(__NR_open, (int)OUT_PATH, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (out_fd < 0) {
        say("WARN cannot create raw dump\n");
        rc = -1;
    } else {
        rc = write_all(out_fd, (const void *)tab_ptr, TAB_SIZE);
        sc3(__NR_close, out_fd, 0, 0);
        say(rc == 0 ? "DUMP 16384 bytes ok\n" : "FAIL raw dump write\n");
    }

    sc3(__NR_munmap, (int)tab_ptr, (int)TAB_SIZE, 0);
    sc3(__NR_munmap, (int)ctrl_ptr, (int)CTRL_PAGE, 0);
    sc3(__NR_close, fd, 0, 0);
    say("=== done ===\n");
    return 0;
}

__asm__(".global _start\n"
        "_start:\n"
        "mov r0, sp\n"
        "bl nx_main\n"
        "mov r7, #1\n"
        "svc 0\n");
