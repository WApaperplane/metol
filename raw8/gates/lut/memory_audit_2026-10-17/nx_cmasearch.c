/* nx_cmasearch.c — 在 CMA 区搜索标准 LUT 表（只读）
 * 判据：以 std 表的 16 个 dword 表头为锚点，dword 对齐匹配。
 * 范围：0x8f800000..0x94000000（72MB，每次 1MB）
 */
#define SYS_exit    1
#define SYS_read    3
#define SYS_write   4
#define SYS_open    5
#define SYS_close   6
#define SYS_mmap2 192

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
	__asm__ volatile("svc 0" : "+r"(r0) : "r"(r1), "r"(r2), "r"(r3), "r"(r4), "r"(r5), "r"(r7) : "memory", "cc");
	return r0;
}
static void puts_(const char *s)
{
	int n = 0;
	while (s[n]) n++;
	sc3(SYS_write, 1, (int)s, n);
}
static void putn(int v)
{
	char b[16];
	int i = 15, neg = 0;
	b[i--] = 0;
	if (v == 0) b[i--] = '0';
	if (v < 0) { neg = 1; v = -v; }
	while (v > 0 && i >= 0) { b[i--] = (char)('0' + (v % 10)); v /= 10; }
	if (neg && i >= 0) b[i--] = '-';
	puts_(&b[i + 1]);
}
static const char HEX[] = "0123456789abcdef";
static void puthex(unsigned int v)
{
	char b[9];
	int i;
	for (i = 0; i < 8; i++) b[i] = HEX[(v >> ((7 - i) * 4)) & 0xF];
	b[8] = 0; puts_(b);
}

#define SCAN_START 0x8F800000u
#define SCAN_END   0x94000000u
#define CHUNK      0x100000u
#define NW         16

static unsigned int anchor[NW];

int main(void)
{
	int mfd, ffd, p, i, k, hits = 0;
	unsigned int off, nw;
	unsigned int *w;
	unsigned char ab[64];

	puts_("=== search std-LUT anchor in CMA 0x8f800000+72M ===\n");

	ffd = sc3(SYS_open, (int)"/mnt/mmc/std_baseline.bin", 0, 0);
	if (ffd < 0) { puts_("no baseline\n"); return 0; }
	sc3(SYS_read, ffd, (int)ab, 64);
	sc3(SYS_close, ffd, 0, 0);
	for (i = 0; i < NW; i++)
		anchor[i] = ((unsigned int *)ab)[i];
	puts_("anchor[0]="); puthex(anchor[0]); puts_("\n");

	mfd = sc3(SYS_open, (int)"/dev/mem", 0, 0);
	if (mfd < 0) { puts_("no /dev/mem\n"); return 0; }

	nw = CHUNK / 4;
	for (off = SCAN_START; off < SCAN_END; off += CHUNK) {
		p = (int)sc6(SYS_mmap2, 0, (int)CHUNK, 1, 1, mfd, off >> 12);
		if ((unsigned int)p >= 0xFFFFF000u)
			continue;
		w = (unsigned int *)p;
		for (i = 0; i + NW < (int)nw; i++) {
			if (w[i] != anchor[0])
				continue;
			for (k = 1; k < NW; k++)
				if (w[i + k] != anchor[k]) break;
			if (k == NW) {
				puts_("HIT "); puthex(off + (unsigned int)i * 4); puts_("\n");
				hits++;
				if (hits > 20) { puts_("(limit)\n"); goto out; }
			}
		}
	}
out:
	puts_("=== done hits="); putn(hits); puts_(" ===\n");
	sc3(SYS_close, mfd, 0, 0);
	return 0;
}

void _start(void)
{
	main();
	sc3(SYS_exit, 0, 0, 0);
	for (;;) ;
}
