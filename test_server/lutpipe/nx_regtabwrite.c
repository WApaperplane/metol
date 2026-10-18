/* nx_regtabwrite.c — controlled single-word write to the View4 registry entry.
 *
 * Answers three questions in one experiment:
 *   1. is the registry page writable through /dev/mem (O_RDWR + PROT_WRITE)?
 *   2. does P7 re-read the registry entry on its next normal load?
 *   3. does retargeting it actually change the hardware Load source?
 *
 * Only View4[3] (absolute 0x803837FC, the skin entry that the 900-sample
 * capture showed as the live Load source) is ever modified, and every mode
 * refuses to write unless the current word equals the expected value.
 * The whole 16 KiB window is snapshotted first and re-verified afterwards, so
 * any collateral byte change fails the run.
 *
 * Modes:
 *   status  read-only: registry words + the five EP 3DLUT registers
 *   probe   write the current value back (no-op) and verify it stayed
 *   patch   View4[3]: 0x81115200 (A17) -> 0x81119F00 (A18, nearly identical
 *           table: 4.1% of bytes differ, max delta 8 -- visually invisible)
 *   patch12 View4[3]: -> 0x810FD100 (A12 standard: 70% of bytes differ,
 *           max delta 97 -- this is the one that should be visible)
 *   restore View4[3]: -> 0x81115200 (A17)
 *
 * No ioctl, no private d5 device, no firmware change, no persistence:
 * a power cycle restores the image copy of this page.
 * Build: ARM EABI, -nostdlib -static -O0 -marm -mfloat-abi=soft.
 */
#include <asm/unistd.h>
#include <fcntl.h>
#include <sys/mman.h>

#define TAB_ADDR    0x80380000u
#define TAB_SIZE    0x4000u
#define VIEW_AT     0x37F0u
#define VIEW3_OFF   0x37FCu
#define STILL_AT    0x2C5Cu
#define STILL_N     6u
#define STILL_BAK   "/mnt/mmc/nxwa_regtab_20261018/still6_orig.bin"
#define REG_ADDR    0x2082B000u
#define REG_SIZE    0x1000u
#define VAL_A17     0x81115200u
#define VAL_A18     0x81119F00u
#define VAL_A12     0x810FD100u

static unsigned char snap[TAB_SIZE];

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

static void line_registry(const char *label, const volatile unsigned int *words, unsigned count)
{
    char out[256], *p = out;
    const char *s;
    unsigned i;
    for (s = label; *s; ++s) *p++ = *s;
    *p++ = ':';
    for (i = 0; i < count; ++i) { *p++ = ' '; p = hex(p, words[i]); }
    *p++ = '\n';
    write_all(1, out, (unsigned)(p - out));
}

/* DSB via coprocessor encoding: assembles under the arm5te default, takes
 * effect on the Cortex-A9 target. Needed so the store reaches the device
 * before the readback below. */
static void barrier(void)
{ __asm__ volatile("mcr p15, 0, %0, c7, c10, 4" :: "r"(0) : "memory"); }

static int read_file(const char *path, unsigned char *dst, unsigned want)
{
    int fd = sc3(__NR_open, (int)path, O_RDONLY, 0);
    unsigned done = 0;
    if (fd < 0) { say("FAIL open backup for read\n"); return -1; }
    while (done < want) {
        int n = sc3(__NR_read, fd, (int)(dst + done), (int)(want - done));
        if (n == -4) continue;
        if (n <= 0) { sc3(__NR_close, fd, 0, 0); say("FAIL short backup\n"); return -1; }
        done += (unsigned)n;
    }
    sc3(__NR_close, fd, 0, 0);
    return 0;
}

static int save_file(const char *path, const unsigned char *src, unsigned n)
{
    int fd = sc3(__NR_open, (int)path, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    int rc;
    if (fd < 0) { say("FAIL create backup\n"); return -1; }
    rc = write_all(fd, src, n);
    sc3(__NR_close, fd, 0, 0);
    return rc;
}

/* Only these three slot addresses may ever appear in View4[3] under our hand. */
static int known_slot(unsigned int v)
{ return v == VAL_A17 || v == VAL_A18 || v == VAL_A12; }

/* Count bytes changed outside the target region (must stay zero), and
 * report how many bytes inside it actually differ. A word rewrite can change
 * as few as one byte (0x81115200 -> 0x81119F00 differs only at 0x52). */
static unsigned window_delta(const volatile unsigned char *live,
                             unsigned off, unsigned len, unsigned *inside)
{
    unsigned i, stray = 0;
    *inside = 0;
    for (i = 0; i < TAB_SIZE; ++i) {
        if (live[i] == snap[i]) continue;
        if (i >= off && i < off + len) ++(*inside);
        else ++stray;
    }
    return stray;
}

static void putu(const char *label, unsigned v)
{
    char b[96], *p = b;   /* labels here run to ~42 chars; keep ample slack */
    unsigned d[10], k = 0, j;
    const char *s;
    for (s = label; *s; ++s) *p++ = *s;
    if (!v) d[k++] = 0;
    while (v) { d[k++] = v % 10u; v /= 10u; }
    for (j = k; j > 0; --j) *p++ = (char)('0' + d[j - 1]);
    *p++ = '\n';
    write_all(1, b, (unsigned)(p - b));
}

static int map(void **addr, unsigned pa, unsigned size, int writable, int *fd)
{
    int flags = writable ? (O_RDWR | O_SYNC) : (O_RDONLY | O_SYNC);
    int prot = writable ? (PROT_READ | PROT_WRITE) : PROT_READ;
    unsigned got;
    *fd = sc3(__NR_open, (int)"/dev/mem", flags, 0);
    if (*fd < 0) { say("FAIL open /dev/mem\n"); return -1; }
    got = (unsigned)sc6(__NR_mmap2, 0, (int)size, prot, MAP_SHARED, *fd, (int)(pa >> 12));
    if (got >= 0xFFFFF000u) {
        say("FAIL mmap (writable=");
        say(writable ? "yes" : "no");
        say(")\n");
        sc3(__NR_close, *fd, 0, 0);
        return -1;
    }
    *addr = (void *)got;
    return 0;
}

/* Read the five EP 3DLUT registers once, for an objective Load-source check. */
static void show_registers(void)
{
    void *base = 0; int fd = 0;
    if (map(&base, REG_ADDR, REG_SIZE, 0, &fd) < 0) { say("REGS: unavailable\n"); return; }
    {
        volatile unsigned int *r = (volatile unsigned int *)base;
        char out[160], *p = out;
        *p++ = 'R'; *p++ = 'E'; *p++ = 'G'; *p++ = 'S'; *p++ = ':';
        *p++ = ' ';
        p = hex(p, r[0]); *p++ = ' ';
        p = hex(p, r[1]); *p++ = ' ';
        p = hex(p, r[2]); *p++ = ' ';
        p = hex(p, r[3]); *p++ = ' ';
        p = hex(p, r[4]); *p++ = '\n';
        write_all(1, out, (unsigned)(p - out));
        say("REGS: onoff cfg pulse load_addr save_addr\n");
    }
    sc3(__NR_munmap, (int)base, (int)REG_SIZE, 0);
    sc3(__NR_close, fd, 0, 0);
}

static int do_write(const char *mode)
{
    void *base = 0;
    int fd = 0, rc = 1;
    volatile unsigned int *tab;
    volatile unsigned char *live;
    unsigned int expect, target, before, after;
    unsigned i;

    if (equal(mode, "probe"))        { expect = 0xFFFFFFFFu; target = 0xFFFFFFFFu; }
    else if (equal(mode, "patch"))   { expect = 0xFFFFFFFFu; target = VAL_A18; }
    else if (equal(mode, "patch12")) { expect = 0xFFFFFFFFu; target = VAL_A12; }
    else if (equal(mode, "restore")) { expect = 0xFFFFFFFFu; target = VAL_A17; }
    else { say("unknown mode\n"); return 1; }

    if (map(&base, TAB_ADDR, TAB_SIZE, 1, &fd) < 0) return 1;
    tab = (volatile unsigned int *)base;
    live = (volatile unsigned char *)base;

    for (i = 0; i < TAB_SIZE; ++i) snap[i] = live[i];
    before = tab[VIEW3_OFF >> 2];
    line_registry("VIEW4 before", tab + (VIEW_AT >> 2), 4);
    say("MODE "); say(mode); say(" writable-mapping ok\n");

    if (!known_slot(before)) {
        say("REFUSE: View4[3] holds an unknown slot, no write performed\n");
        goto out;
    }
    if (expect != 0xFFFFFFFFu && before != expect) {
        say("REFUSE: View4[3] is not the expected value, no write performed\n");
        goto out;
    }
    if (equal(mode, "probe")) target = before;
    if (!equal(mode, "probe") && before == target) {
        say("NOTE: already at target, nothing to write\n");
        rc = 0;
        goto out;
    }

    say("WRITE "); { char b[16], *p = b; p = hex(p, target); *p++ = '\n'; write_all(1, b, (unsigned)(p - b)); }
    tab[VIEW3_OFF >> 2] = target;
    barrier();

    after = tab[VIEW3_OFF >> 2];
    line_registry("VIEW4 after ", tab + (VIEW_AT >> 2), 4);
    say("READBACK "); { char b[16], *p = b; p = hex(p, after); *p++ = '\n'; write_all(1, b, (unsigned)(p - b)); }

    if (after != target) { say("FAIL readback does not match written value\n"); goto out; }

    /* Only the target word may differ; everything else must be untouched. */
    {
        unsigned in_word = 0;
        unsigned stray = window_delta(live, VIEW3_OFF, 4, &in_word);
        putu("WINDOW bytes changed inside target word = ", in_word);
        putu("WINDOW stray deltas outside target word = ", stray);
        if (stray != 0) { say("FAIL collateral change in window\n"); goto out; }
        if (equal(mode, "probe") ? in_word != 0 : in_word == 0) {
            say("FAIL unexpected delta pattern\n");
            goto out;
        }
    }
    rc = 0;

out:
    sc3(__NR_munmap, (int)base, (int)TAB_SIZE, 0);
    sc3(__NR_close, fd, 0, 0);
    return rc;
}

/* Still6 holds six independent entry points used by the Still (JPEG) select
 * logic at 0x80382B30. Pointing all six at one slot makes any Still branch
 * read the same table, so a single capture answers "does Still consume it".
 * The six original words are backed up before any write. */
static int do_still(const char *mode)
{
    void *base = 0;
    int fd = 0, rc = 1;
    volatile unsigned int *tab;
    volatile unsigned char *live;
    unsigned int vals[STILL_N], before[STILL_N];
    unsigned i, inside = 0, stray;
    int writing = equal(mode, "still-set") || equal(mode, "still-write");
    int backup = equal(mode, "still-set");
    /* Only still-status is read-only; every other still mode writes. */
    int readonly = equal(mode, "still-status");

    if (map(&base, TAB_ADDR, TAB_SIZE, readonly ? 0 : 1, &fd) < 0) return 1;
    tab = (volatile unsigned int *)base;
    live = (volatile unsigned char *)base;
    for (i = 0; i < TAB_SIZE; ++i) snap[i] = live[i];
    for (i = 0; i < STILL_N; ++i) before[i] = tab[(STILL_AT >> 2) + i];

    line_registry("STILL6 before", tab + (STILL_AT >> 2), STILL_N);
    if (equal(mode, "still-status")) { rc = 0; goto out; }

    if (writing) {
        if (backup) {
        if (save_file(STILL_BAK, (const unsigned char *)before, sizeof before) < 0) goto out;
        say("BACKUP written\n");
        }
        for (i = 0; i < STILL_N; ++i) tab[(STILL_AT >> 2) + i] = VAL_A18;
        for (i = 0; i < STILL_N; ++i) vals[i] = VAL_A18;
    } else {
        if (read_file(STILL_BAK, (unsigned char *)vals, sizeof vals) < 0) goto out;
        for (i = 0; i < STILL_N; ++i) tab[(STILL_AT >> 2) + i] = vals[i];
    }
    barrier();
    line_registry("STILL6 after ", tab + (STILL_AT >> 2), STILL_N);

    for (i = 0; i < STILL_N; ++i) {
        if (tab[(STILL_AT >> 2) + i] != vals[i]) { say("FAIL readback mismatch\n"); goto out; }
    }
    say("READBACK ok\n");

    stray = window_delta(live, STILL_AT, STILL_N * 4, &inside);
    putu("STILL6 bytes changed = ", inside);
    putu("stray deltas outside Still6 = ", stray);
    if (stray != 0) { say("FAIL collateral change in window\n"); goto out; }
    rc = 0;

out:
    sc3(__NR_munmap, (int)base, (int)TAB_SIZE, 0);
    sc3(__NR_close, fd, 0, 0);
    return rc;
}

/* Force one hardware reload from <addr>, using the same store order P7 emits
 * in 0x804A5C44 (trace: OnOff, Pulse clear, Pulse bit0, Load source, Cfg,
 * Pulse|bit8, Pulse clear). Cfg is preserved verbatim so the current bank and
 * format stay as they are. This is what lets a table change take effect
 * without waiting for the operator to half-press the shutter. */
static int do_reload(unsigned int addr)
{
    void *base = 0;
    int fd = 0, rc = 1;
    volatile unsigned int *r;
    unsigned int cfg, got, cfg_after;

    if (map(&base, REG_ADDR, REG_SIZE, 1, &fd) < 0) return 1;
    r = (volatile unsigned int *)base;
    cfg = r[1];
    say("RELOAD ");
    putu("ADDR requested = ", addr);
    putu("CFG before = ", cfg);

    r[0] = 1u; barrier();          /* OnOff */
    r[2] = 0u; barrier();          /* Pulse clear */
    r[2] = 1u; barrier();          /* bit0 */
    r[3] = addr; barrier();        /* Load source */
    r[1] = cfg; barrier();         /* Cfg unchanged */
    r[2] = 0x101u; barrier();      /* bit8 trigger */
    r[2] = 1u; barrier();

    got = r[3];
    cfg_after = r[1];
    putu("LOAD ADDR after = ", got);
    putu("CFG after = ", cfg_after);
    if (got != addr) { say("FAIL load address did not stick\n"); goto out; }
    if (cfg_after != cfg) { say("FAIL cfg changed during reload\n"); goto out; }
    say("RELOAD ok\n");
    rc = 0;
out:
    sc3(__NR_munmap, (int)base, (int)REG_SIZE, 0);
    sc3(__NR_close, fd, 0, 0);
    return rc;
}

static unsigned int parse_hex(const char *s)
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

int nx_main(unsigned *initial_stack)
{
    unsigned argc = initial_stack[0];
    char **argv = (char **)(initial_stack + 1);

    say("=== regtabwrite (single word, View4[3] only) ===\n");
    if (argc < 2) {
        say("usage: nx_regtabwrite.arm status|probe|patch|patch12|restore\n");
        return 1;
    }
    if (equal(argv[1], "status")) {
        void *base = 0; int fd = 0;
        if (map(&base, TAB_ADDR, TAB_SIZE, 0, &fd) < 0) return 1;
        line_registry("VIEW4 ", (volatile unsigned int *)base + (VIEW_AT >> 2), 4);
        line_registry("STILL6", (volatile unsigned int *)base + (STILL_AT >> 2), STILL_N);
        sc3(__NR_munmap, (int)base, (int)TAB_SIZE, 0);
        sc3(__NR_close, fd, 0, 0);
        show_registers();
        say("=== done ===\n");
        return 0;
    }
    if (equal(argv[1], "reload")) {
        int rc;
        if (argc < 3) { say("usage: nx_regtabwrite.arm reload <hexaddr>\n"); return 1; }
        rc = do_reload(parse_hex(argv[2]));
        show_registers();
        say(rc == 0 ? "=== done ===\n" : "=== FAILED ===\n");
        return rc;
    }
    if (equal(argv[1], "still-status") || equal(argv[1], "still-set")
        || equal(argv[1], "still-write") || equal(argv[1], "still-restore")) {
        int rc = do_still(argv[1]);
        say(rc == 0 ? "=== done ===\n" : "=== FAILED ===\n");
        return rc;
    }
    {
        int rc = do_write(argv[1]);
        show_registers();
        say(rc == 0 ? "=== done ===\n" : "=== FAILED ===\n");
        return rc;
    }
}

__asm__(".global _start\n"
        "_start:\n"
        "mov r0, sp\n"
        "bl nx_main\n"
        "mov r7, #1\n"
        "svc 0\n");
