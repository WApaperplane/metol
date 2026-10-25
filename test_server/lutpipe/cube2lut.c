/* cube2lut.c — Adobe .cube -> Samsung 3D LUT slot table, running on the camera.
 *
 * Why on-device: the camera has no Python. Copy a .cube to the SD card and
 * convert it there, so importing a look never needs a PC round trip.
 *
 * Input : .cube with LUT_3D_SIZE N (LUT_1D_SIZE is reported as unsupported)
 *         and DOMAIN 0..1. Any other DOMAIN is rejected rather than guessed:
 *         a silent misinterpretation yields a plausible but wrong table.
 * Output: 19,712-byte slot image = 4,913 entries x {Cr,Cb,Y,0} + 60B tail.
 *         Index = ((Y*17 + Cb)*17 + Cr) * 4; grid = {0,16,...,240,255}.
 *         Input coordinates are CrCbY -> RGB -> cube -> RGB -> CrCbY.
 *         BT.601 full-range is the visually tested working matrix; this is
 *         not a calibrated camera profile. --legacy-rgb retains the old
 *         RGB-grid bytes for historical comparisons only.
 *
 * All arithmetic is fixed point Q16. No libc, libm or libgcc helpers: float
 * parsing, 64-bit division and variable division are all avoided.
 * Build: ARM EABI, -nostdlib -static -O0 -marm -mfloat-abi=soft.
 */
#include <asm/unistd.h>
#include <fcntl.h>
#include <sys/mman.h>

#define N16        17u
#define NENT       4913u
#define TABLE_LEN  19652u
#define SLOT_LEN   19712u
#define MAX_FILE   (16u * 1024u * 1024u)
#define MAX_NODES  400000u

/* hardware sampling levels 0,16,...,240,255 expressed as Q16 fractions */
static const unsigned int level_q16[N16] = {
    0, 4112, 8224, 12336, 16448, 20560, 24672, 28784,
    32896, 37008, 41120, 45232, 49344, 53456, 57568, 61680, 65536
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

static unsigned slen(const char *s) { unsigned n = 0; while (s[n]) ++n; return n; }
static void say(const char *s) { write_all(1, s, slen(s)); }
static void fail(const char *m) { say("FAIL "); say(m); say("\n"); }

static void putu(const char *label, unsigned v)
{
    char b[64], *p = b;
    unsigned d[10], k = 0, j;
    const char *s;
    for (s = label; *s; ++s) *p++ = *s;
    if (!v) d[k++] = 0;
    while (v) { d[k++] = v % 10u; v /= 10u; }
    for (j = k; j > 0; --j) *p++ = (char)('0' + d[j - 1]);
    *p++ = '\n';
    write_all(1, b, (unsigned)(p - b));
}

static int is_digit(char c) { return c >= '0' && c <= '9'; }
static int is_space(char c) { return c == ' ' || c == '\t' || c == '\r' || c == '\n'; }

static int starts_with(const char *s, const char *p)
{
    while (*p) { if (*s != *p) return 0; ++s; ++p; }
    return 1;
}

static void *map_anon(unsigned size)
{
    /* MAP_PRIVATE(0x02) | MAP_ANONYMOUS(0x20), fd = -1 */
    unsigned got = (unsigned)sc6(__NR_mmap2, 0, (int)size,
                                 PROT_READ | PROT_WRITE, 0x22, -1, 0);
    if (got >= 0xFFFFF000u) return 0;
    return (void *)got;
}

/* Parse "d.ddddd[e±NN]" into Q16 using four fractional digits (missing ones
 * are zeros, extra ones are dropped). Division by the constant 10000 lets the
 * compiler emit a multiply instead of a divide helper.
 *
 * Scientific notation is required in practice: G'MIC writes very dark values
 * as "2.2439395252149552e-05". The first version of this parser stopped at
 * 'e' and returned 0 *without advancing the cursor*, so every subsequent value
 * on every subsequent line also became 0 -- while rows_seen still counted up
 * to N^3 and the "node count" check passed. Twelve of eighteen real film cubes
 * produced a table that was 93% zeros and reported success.
 *
 * Hence: return an error instead of a silent 0, and always advance the cursor.
 * Returns 0 on success, -1 when the input is not a number.
 * Negative values are clamped to 0 by the caller (the slot table is 0..255). */
static int fixed16(const char **pp, unsigned *out)
{
    const char *s = *pp;
    unsigned ip = 0, fp = 0, v;
    int k, neg = 0, expo = 0;
    while (is_space(*s)) ++s;
    if (*s == '-') { neg = 1; ++s; }
    else if (*s == '+') ++s;
    if (!is_digit(*s)) return -1;
    while (is_digit(*s)) { ip = ip * 10u + (unsigned)(*s - '0'); ++s; }
    if (*s == '.') {
        ++s;
        for (k = 0; k < 4; ++k) {
            fp *= 10u;
            if (is_digit(*s)) { fp += (unsigned)(*s - '0'); ++s; }
        }
        while (is_digit(*s)) ++s;
    }
    if (*s == 'e' || *s == 'E') {
        int eneg = 0;
        ++s;
        if (*s == '+') ++s;
        else if (*s == '-') { eneg = 1; ++s; }
        if (!is_digit(*s)) return -1;
        while (is_digit(*s)) {
            if (expo < 40) expo = expo * 10 + (int)(*s - '0');
            ++s;
        }
        if (eneg) expo = -expo;
    }
    *pp = s;

    v = ip * 65536u + (fp * 65536u) / 10000u;
    while (expo > 0) {
        if (v >= 65536u) { v = 65536u; break; }
        v *= 10u;
        --expo;
    }
    while (expo < 0) { v /= 10u; ++expo; }
    if (neg) v = 0;
    if (v > 65536u) v = 65536u;
    *out = v;
    return 0;
}

static unsigned atou(const char **pp)
{
    const char *s = *pp;
    unsigned v = 0;
    while (*s == ' ') ++s;
    while (is_digit(*s)) { v = v * 10u + (unsigned)(*s - '0'); ++s; }
    *pp = s;
    return v;
}

static unsigned to_u8(int q16)
{
    int v;
    if (q16 <= 0) return 0;
    if (q16 >= 65536) return 255;
    v = (q16 * 255 + 32768) >> 16;
    if (v > 255) v = 255;
    return (unsigned)v;
}

static int mul_q16(int a, int b)
{ return (int)(((long long)a * (long long)b + 32768) >> 16); }

/* Interpolation weight may leave [0,1]: see the note on sample(). */
static int lerp_s(int a, int b, int f)
{
    long long d = (long long)(b - a) * (long long)f;
    return a + (int)(d / 65536);
}

/* Neutral chroma is the actual 8-bit value 128, not 127.5. */
#define CHROMA_ZERO 32896

/* No clipping here. About 80% of the 17^3 CrCbY grid lands outside sRGB
 * (release 10 measured 80.5%), and clamping those points to 0..255 destroys
 * the transform: an identity .cube comes back as (71,83,80)...(184,173,176)
 * instead of identity. Out-of-range values are carried into sample(), which
 * extrapolates linearly -- the same boundary rule native_codec uses. */
static void crcb_y_to_rgb(int cr, int cb, int y, int *rgb)
{
    int vr = cr - CHROMA_ZERO, vb = cb - CHROMA_ZERO;
    rgb[0] = y + mul_q16(91881, vr);
    rgb[1] = y - mul_q16(46802, vr) - mul_q16(22554, vb);
    rgb[2] = y + mul_q16(116130, vb);
}

static void rgb_to_crcb_y(const int *rgb, unsigned char *out)
{
    int r = (int)rgb[0], g = (int)rgb[1], b = (int)rgb[2];
    int y = mul_q16(19595, r) + mul_q16(38470, g) + mul_q16(7471, b);
    int cr = CHROMA_ZERO + mul_q16(32768, r) - mul_q16(27439, g) - mul_q16(5329, b);
    int cb = CHROMA_ZERO - mul_q16(11059, r) - mul_q16(21709, g) + mul_q16(32768, b);
    out[0] = (unsigned char)to_u8(cr);
    out[1] = (unsigned char)to_u8(cb);
    out[2] = (unsigned char)to_u8(y);
    out[3] = 0;
}

/* Trilinear sample of a cubical node grid, channels packed as RGB.
 *
 * The three positions are signed Q16 and may fall outside [0,1]. The corner
 * index is clamped to the last cell while the weight keeps its true offset, so
 * a position past the edge continues along the same straight line the last
 * cell describes. Clamping the weight instead would flatten every out-of-range
 * grid point onto the boundary plane, which is exactly what broke the identity
 * transform. Linear extrapolation also keeps affine transforms (identity,
 * monochrome) exact, so it is the only boundary rule worth having. */
static void sample(const unsigned int *nodes, unsigned n,
                   int pr, int pg, int pb, int *out3)
{
    int idx[3], fr[3], ch, c;
    int box[8][3];
    int pos[3];
    int ip, i, j, k;
    unsigned n1 = n - 1u;

    pos[0] = pr; pos[1] = pg; pos[2] = pb;
    for (c = 0; c < 3; ++c) {
        long long p = (long long)pos[c] * (long long)n1;
        ip = (int)(p / 65536);
        if (p < 0 && (long long)ip * 65536 != p) ip -= 1;   /* floor, not trunc */
        if (ip < 0) ip = 0;
        if (ip > (int)n - 2) ip = (int)n - 2;
        idx[c] = ip;
        fr[c] = (int)(p - (long long)ip * 65536);
    }

    for (c = 0; c < 8; ++c) {
        i = idx[0] + (c & 1);
        j = idx[1] + ((c >> 1) & 1u);
        k = idx[2] + ((c >> 2) & 1u);
        if (i > (int)n1) i = (int)n1;
        if (j > (int)n1) j = (int)n1;
        if (k > (int)n1) k = (int)n1;
        {
            const unsigned int *nn = nodes + ((k * (int)n + j) * (int)n + i) * 3u;
            box[c][0] = (int)nn[0];
            box[c][1] = (int)nn[1];
            box[c][2] = (int)nn[2];
        }
    }

    for (ch = 0; ch < 3; ++ch) {
        int c00 = lerp_s(box[0][ch], box[1][ch], fr[0]);
        int c10 = lerp_s(box[2][ch], box[3][ch], fr[0]);
        int c01 = lerp_s(box[4][ch], box[5][ch], fr[0]);
        int c11 = lerp_s(box[6][ch], box[7][ch], fr[0]);
        int c0 = lerp_s(c00, c10, fr[1]);
        int c1 = lerp_s(c01, c11, fr[1]);
        out3[ch] = lerp_s(c0, c1, fr[2]);
    }
}

int nx_main(unsigned *initial_stack)
{
    unsigned argc = initial_stack[0];
    char **argv = (char **)(initial_stack + 1);
    int in_fd, out_fd, size;
    char *text;
    const char *p;
    unsigned n = 0, nodes_count, i, r, g, b, rows_seen = 0;
    unsigned int *nodes = 0;
    unsigned char *out = 0;
    int legacy_rgb = 0;

    say("=== cube2lut (cube -> 19712B slot table) ===\n");
    if (argc < 3) {
        say("usage: cube2lut.arm <input.cube> <output.bin> [--legacy-rgb]\n");
        return 1;
    }
    if (argc > 3) {
        if (argc != 4 || slen(argv[3]) != 12 || !starts_with(argv[3], "--legacy-rgb")) {
            fail("unknown output option");
            return 1;
        }
        legacy_rgb = 1;
    }
    say(legacy_rgb ? "SPACE legacy RGB (historical diagnostic only)\n"
                   : "SPACE CrCbY (BT.601 full range)\n");

    in_fd = sc3(__NR_open, (int)argv[1], O_RDONLY, 0);
    if (in_fd < 0) { fail("open input cube"); return 1; }
    size = sc3(__NR_lseek, in_fd, 0, 2);
    if (size <= 0 || (unsigned)size > MAX_FILE) { fail("input size unsupported"); sc3(__NR_close, in_fd, 0, 0); return 1; }
    sc3(__NR_lseek, in_fd, 0, 0);
    text = (char *)map_anon((unsigned)size + 1u);
    if (!text) { fail("mmap input"); sc3(__NR_close, in_fd, 0, 0); return 1; }
    if (sc3(__NR_read, in_fd, (int)text, size) != size) { fail("read input"); sc3(__NR_close, in_fd, 0, 0); return 1; }
    text[size] = 0;
    sc3(__NR_close, in_fd, 0, 0);
    putu("INPUT bytes = ", (unsigned)size);

    /* ---- header: grid size and domain ---- */
    p = text;
    while (*p) {
        const char *eol = p;
        while (*eol && *eol != '\n') ++eol;
        if (starts_with(p, "LUT_3D_SIZE")) {
            const char *q = p + 11;
            n = atou(&q);
        } else if (starts_with(p, "LUT_1D_SIZE")) {
            fail("1D cube is not supported");
            return 1;
        } else if (starts_with(p, "DOMAIN_MIN")) {
            const char *q = p + 10;
            unsigned a, b, c;
            if (fixed16(&q, &a) < 0 || fixed16(&q, &b) < 0 || fixed16(&q, &c) < 0) {
                fail("DOMAIN_MIN is malformed");
                return 1;
            }
            if (a || b || c) {
                fail("DOMAIN_MIN is not 0; convert externally first");
                return 1;
            }
        } else if (starts_with(p, "DOMAIN_MAX")) {
            const char *q = p + 10;
            unsigned a, b, c;
            if (fixed16(&q, &a) < 0 || fixed16(&q, &b) < 0 || fixed16(&q, &c) < 0) {
                fail("DOMAIN_MAX is malformed");
                return 1;
            }
            if (a != 65536u || b != 65536u || c != 65536u) {
                fail("DOMAIN_MAX is not 1; convert externally first");
                return 1;
            }
        }
        p = (*eol == '\n') ? eol + 1 : eol;
    }
    if (n < 2) { fail("LUT_3D_SIZE not found or < 2"); return 1; }
    putu("GRID n = ", n);
    nodes_count = n * n * n;
    if (nodes_count > MAX_NODES) { fail("grid too large"); return 1; }
    nodes = (unsigned int *)map_anon(nodes_count * 3u * 4u);
    if (!nodes) { fail("mmap nodes"); return 1; }

    /* ---- data rows: from the first line that starts with a digit ---- */
    p = text;
    while (*p) {
        const char *eol = p;
        while (*eol && *eol != '\n') ++eol;
        if (is_digit(*p)) break;
        p = (*eol == '\n') ? eol + 1 : eol;
    }
    for (i = 0; i < nodes_count * 3u; ++i) {
        unsigned v;
        if (!*p) { fail("cube data ends early"); return 1; }
        if (fixed16(&p, &v) < 0) {
            putu("FAIL bad number at value index = ", i);
            return 1;
        }
        nodes[i] = v;
        if ((i % 3u) == 2u) ++rows_seen;
    }
    putu("NODES parsed = ", rows_seen);
    if (rows_seen != nodes_count) { fail("cube node count mismatch"); return 1; }
    {
        /* A table that parsed "successfully" but is entirely zero means the
         * data section was not understood. Refuse rather than ship a black LUT. */
        unsigned nz = 0;
        for (i = 0; i < nodes_count * 3u; ++i) if (nodes[i]) { nz = 1; break; }
        if (!nz) { fail("parsed table is all zeros"); return 1; }
    }

    /* ---- resample to the 17^3 hardware grid ---- */
    out = (unsigned char *)map_anon(SLOT_LEN);
    if (!out) { fail("mmap output"); return 1; }
    for (i = 0; i < SLOT_LEN; ++i) out[i] = 0;

    for (b = 0; b < N16; ++b) {
        for (g = 0; g < N16; ++g) {
            for (r = 0; r < N16; ++r) {
                int rgb[3], input[3];
                unsigned o = ((b * N16 + g) * N16 + r) * 4u;
                if (legacy_rgb) {
                    sample(nodes, n, (int)level_q16[r], (int)level_q16[g], (int)level_q16[b], rgb);
                    out[o + 0] = (unsigned char)to_u8(rgb[0]);
                    out[o + 1] = (unsigned char)to_u8(rgb[1]);
                    out[o + 2] = (unsigned char)to_u8(rgb[2]);
                    out[o + 3] = 0;
                } else {
                    crcb_y_to_rgb((int)level_q16[r], (int)level_q16[g], (int)level_q16[b], input);
                    sample(nodes, n, input[0], input[1], input[2], rgb);
                    rgb_to_crcb_y(rgb, out + o);
                }
            }
        }
    }
    if (!legacy_rgb) {
        for (i = 0; i < 12; ++i) out[TABLE_LEN + i] = out[TABLE_LEN - 4u + (i & 3u)];
    }

    out_fd = sc3(__NR_open, (int)argv[2], O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (out_fd < 0) { fail("create output"); return 1; }
    if (write_all(out_fd, out, SLOT_LEN) < 0) { fail("write output"); sc3(__NR_close, out_fd, 0, 0); return 1; }
    sc3(__NR_close, out_fd, 0, 0);

    putu("OUTPUT bytes = ", SLOT_LEN);
    putu("first entry component0 = ", out[0]);
    putu("first entry component1 = ", out[1]);
    putu("first entry component2 = ", out[2]);
    putu("last entry  component0 = ", out[TABLE_LEN - 4u]);
    putu("last entry  component1 = ", out[TABLE_LEN - 3u]);
    putu("last entry  component2 = ", out[TABLE_LEN - 2u]);
    say("=== done ===\n");
    return 0;
}

__asm__(".global _start\n"
        "_start:\n"
        "mov r0, sp\n"
        "bl nx_main\n"
        "mov r7, #1\n"
        "svc 0\n");
