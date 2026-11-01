/* lutmix.c — blend two native 3D LUT tables on the camera (no PC).
 *
 * Why this is exact: the table is sampled with trilinear interpolation, which
 * is a linear operator, so blending node values is identical to blending the
 * rendered images. Per-node cross-fade therefore needs no hardware support --
 * it is arithmetic on 4,913 entries (see docs/current/LUT_STRENGTH_MIX_*).
 *
 * Two uses, one operation:
 *   crossfade A->B     lutmix a.bin b.bin 500 out.bin    (0 = pure A, 1000 = pure B)
 *   strength of a look lutmix a.bin stock.bin 500 out.bin (0 = stock/baseline)
 *   neutral baseline   lutmix --identity out.bin          (full-range identity)
 *
 * The identity table is NOT the same as the stock A17 table: identity maps
 * every input to itself (white 255,255,255) while A17 has a warm/rolled white
 * point. Using identity as the 0-end of a strength axis makes 0% look colder
 * and brighter than the camera's normal picture -- documented, not a bug.
 *
 * Input:  19,712 B slot image or 19,652 B table (tail rebuilt either way)
 * Output: 19,712 B slot image, tail = last entry x3 + zero padding
 *
 * All-integer, no libc/libm/libgcc: ARM EABI, -nostdlib -static -O0.
 */
#include <asm/unistd.h>
#include <fcntl.h>

#define N16        17u
#define TABLE_LEN  19652u
#define SLOT_LEN   19712u
#define TAIL_LEN   (SLOT_LEN - TABLE_LEN)
#define MAX_FILE   (1024u * 1024u)

static unsigned char buf_a[SLOT_LEN];
static unsigned char buf_b[SLOT_LEN];
static unsigned char out_buf[SLOT_LEN];

static int sc3(int n, int a, int b, int c)
{
    register int r0 __asm__("r0") = a;
    register int r1 __asm__("r1") = b;
    register int r2 __asm__("r2") = c;
    register int r7 __asm__("r7") = n;
    __asm__ volatile("svc 0" : "+r"(r0) : "r"(r1), "r"(r2), "r"(r7) : "memory", "cc");
    return r0;
}

static unsigned slen(const char *s) { unsigned n = 0; while (s[n]) ++n; return n; }
static void say(const char *s)
{
    while (*s) {
        int n = sc3(__NR_write, 1, (int)s, (int)slen(s));
        if (n <= 0) return;
        s += n;
    }
}
static void fail(const char *m) { say("FAIL "); say(m); say("\n"); }

static void putu(const char *label, unsigned v)
{
    char b[64];
    char tmp[16];
    int n = 0, i, p = 0;
    say(label);
    if (!v) tmp[n++] = '0';
    while (v) { tmp[n++] = (char)('0' + (v % 10u)); v /= 10u; }
    for (i = n - 1; i >= 0; --i) b[p++] = tmp[i];
    b[p] = 0;
    say(b);
    say("\n");
}

/* Parse a decimal without libc. Rejects anything that is not all digits. */
static int parse_u(const char *s, unsigned *out)
{
    unsigned v = 0;
    if (!s || !*s) return -1;
    while (*s) {
        if (*s < '0' || *s > '9') return -1;
        v = v * 10u + (unsigned)(*s - '0');
        if (v > 1000000u) return -1;
        ++s;
    }
    *out = v;
    return 0;
}

static int read_file(const char *path, unsigned char *dst, unsigned *size)
{
    int fd = sc3(__NR_open, (int)path, O_RDONLY, 0);
    unsigned total = 0;
    unsigned char scratch;
    if (fd < 0) return -1;
    for (;;) {
        int n;
        /* Never ask for more than the buffer holds: a larger read request is
         * rejected with EFAULT once it crosses into an unmapped page. */
        if (total >= SLOT_LEN) break;
        n = sc3(__NR_read, fd, (int)(dst + total), (int)(SLOT_LEN - total));
        if (n < 0) { if (n == -4) continue; sc3(__NR_close, fd, 0, 0); return -1; }
        if (n == 0) break;
        total += (unsigned)n;
    }
    if (total >= SLOT_LEN) {
        /* Full buffer: anything beyond it means this is not a table. */
        int extra = sc3(__NR_read, fd, (int)&scratch, 1);
        if (extra != 0) { sc3(__NR_close, fd, 0, 0); return -1; }
    }
    sc3(__NR_close, fd, 0, 0);
    *size = total;
    return 0;
}

static int write_file(const char *path, const unsigned char *src, unsigned size)
{
    int fd = sc3(__NR_open, (int)path, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    unsigned done = 0;
    if (fd < 0) return -1;
    while (done < size) {
        int n = sc3(__NR_write, fd, (int)(src + done), (int)(size - done));
        if (n <= 0) { if (n == -4) continue; sc3(__NR_close, fd, 0, 0); return -1; }
        done += (unsigned)n;
    }
    sc3(__NR_close, fd, 0, 0);
    return 0;
}

/* The slot image carries 60 extra bytes: the last entry repeated three times
 * then zeros. The hardware ignores them, but every other tool in this repo
 * produces exactly this layout, so byte comparison stays meaningful. */
static void fix_tail(unsigned char *t)
{
    unsigned i;
    for (i = 0; i < 12u; ++i) t[TABLE_LEN + i] = t[TABLE_LEN - 4u + (i & 3u)];
    for (; i < TAIL_LEN; ++i) t[TABLE_LEN + i] = 0;
}

static unsigned level(unsigned i) { return i < N16 - 1u ? i * 16u : 255u; }

static int build_identity(unsigned char *t)
{
    unsigned cr, cb, y;
    for (y = 0; y < N16; ++y)
        for (cb = 0; cb < N16; ++cb)
            for (cr = 0; cr < N16; ++cr) {
                unsigned o = ((y * N16 + cb) * N16 + cr) * 4u;
                t[o + 0] = (unsigned char)level(cr);   /* Cr */
                t[o + 1] = (unsigned char)level(cb);   /* Cb */
                t[o + 2] = (unsigned char)level(y);    /* Y  */
                t[o + 3] = 0;
            }
    fix_tail(t);
    return 0;
}

int nx_main(unsigned *initial_stack)
{
    unsigned argc = initial_stack[0];
    char **argv = (char **)(initial_stack + 1);
    unsigned size_a = 0, size_b = 0, permille = 0, i;

    say("=== lutmix (native table crossfade) ===\n");

    if (argc == 3 && argv[1][0] == '-' && argv[1][1] == '-' && argv[1][2] == 'i') {
        build_identity(out_buf);
        if (write_file(argv[2], out_buf, SLOT_LEN) < 0) { fail("create output"); return 1; }
        say("MODE identity\n");
        putu("OUTPUT bytes = ", SLOT_LEN);
        say("=== done ===\n");
        return 0;
    }
    if (argc != 5) {
        say("usage: lutmix <a.bin> <b.bin> <permille 0-1000> <out.bin>\n");
        say("       lutmix --identity <out.bin>\n");
        return 2;
    }
    if (parse_u(argv[3], &permille) != 0 || permille > 1000u) { fail("bad permille (0-1000)"); return 2; }

    if (read_file(argv[1], buf_a, &size_a) < 0) { fail("read A"); return 1; }
    if (read_file(argv[2], buf_b, &size_b) < 0) { fail("read B"); return 1; }
    putu("A bytes = ", size_a);
    putu("B bytes = ", size_b);
    if (size_a != SLOT_LEN && size_a != TABLE_LEN) { fail("A is not a native table (19712 or 19652 bytes)"); return 1; }
    if (size_b != SLOT_LEN && size_b != TABLE_LEN) { fail("B is not a native table (19712 or 19652 bytes)"); return 1; }

    /* Entry-wise blend. Rounding is (x*1000 + 500)/1000, so 0 and 1000 return
     * the endpoints bit-exact instead of drifting by one level. */
    for (i = 0; i < TABLE_LEN; ++i) {
        unsigned a = buf_a[i], b = buf_b[i];
        unsigned v = (a * (1000u - permille) + b * permille + 500u) / 1000u;
        out_buf[i] = (unsigned char)(v > 255u ? 255u : v);
    }
    fix_tail(out_buf);

    if (write_file(argv[4], out_buf, SLOT_LEN) < 0) { fail("create output"); return 1; }
    say("MODE blend\n");
    putu("S permille = ", permille);
    putu("OUTPUT bytes = ", SLOT_LEN);
    say("=== done ===\n");
    return 0;
}

__asm__(".global _start\n"
        "_start:\n"
        "mov r0, sp\n"
        "bl nx_main\n"
        "mov r7, #1\n"
        "svc 0\n");
