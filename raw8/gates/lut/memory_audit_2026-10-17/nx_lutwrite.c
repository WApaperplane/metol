/* nx_lutwrite.c — 写-验-还原 一体（目标：肤色池 0x81115200）
 * 1) 读原内容 19712B 存 buf_orig
 * 2) 读 identity_a12.bin 19712B
 * 3) 写入池
 * 4) 读回比对
 * 5) 立即还原 buf_orig，再读回比对
 * 只动 0x81115200 一个槽，全程同一进程内完成，风险窗口最小。
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
static void putb(unsigned char *p, int n)
{
	int i;
	for (i = 0; i < n; i++) {
		char t[3];
		t[0] = HEX[p[i] >> 4]; t[1] = HEX[p[i] & 0xF]; t[2] = 0;
		puts_(t);
	}
}
static void bcopy_(unsigned char *d, unsigned char *s, int n)
{
	int i;
	for (i = 0; i < n; i++) d[i] = s[i];
}
static int bcmp_(unsigned char *a, unsigned char *b, int n)
{
	int i, r = 0;
	for (i = 0; i < n; i++) if (a[i] != b[i]) r++;
	return r;
}

#define BASE    0x81115000u
#define OFF     0x200u
#define LEN     19712u
#define MAPLEN  0x5000u

static unsigned char buf_orig[LEN];
static unsigned char buf_new[LEN];
static unsigned char buf_chk[LEN];

int main(void)
{
	int mfd, ffd, r, p, w;
	unsigned char *m, *slot;

	puts_("=== LUT write test @ 0x81115200 (skin pool) ===\n");

	mfd = sc3(SYS_open, (int)"/dev/mem", 2 /*O_RDWR*/, 0);
	puts_("open /dev/mem O_RDWR = "); putn(mfd); puts_("\n");
	if (mfd < 0) return 0;

	p = (int)sc6(SYS_mmap2, 0, (int)MAPLEN, 3 /*R|W*/, 1 /*SHARED*/, mfd, BASE >> 12);
	if ((unsigned int)p >= 0xFFFFF000u) {
		puts_("mmap RW FAILED\n"); return 0;
	}
	puts_("mmap RW ok\n");
	m = (unsigned char *)p;
	slot = m + OFF;

	bcopy_(buf_orig, slot, LEN);
	puts_("orig head: "); putb(buf_orig, 8); puts_("\n");

	ffd = sc3(SYS_open, (int)"/mnt/mmc/identity_a12.bin", 0, 0);
	puts_("open identity = "); putn(ffd); puts_("\n");
	if (ffd < 0) return 0;
	r = sc3(SYS_read, ffd, (int)buf_new, (int)LEN);
	sc3(SYS_close, ffd, 0, 0);
	puts_("read identity = "); putn(r); puts_("\n");
	if (r != (int)LEN) { puts_("short read, abort\n"); return 0; }
	puts_("new  head: "); putb(buf_new, 8); puts_("\n");

	puts_(">>> writing...\n");
	bcopy_(slot, buf_new, LEN);
	bcopy_(buf_chk, slot, LEN);
	puts_("readback head: "); putb(buf_chk, 8); puts_("\n");
	w = bcmp_(buf_chk, buf_new, LEN);
	puts_("write verify diff = "); putn(w); puts_("\n");

	puts_(">>> restoring...\n");
	bcopy_(slot, buf_orig, LEN);
	bcopy_(buf_chk, slot, LEN);
	puts_("restored head: "); putb(buf_chk, 8); puts_("\n");
	w = bcmp_(buf_chk, buf_orig, LEN);
	puts_("restore verify diff = "); putn(w); puts_("\n");

	sc3(SYS_close, mfd, 0, 0);
	puts_("=== done ===\n");
	return 0;
}

void _start(void)
{
	main();
	sc3(SYS_exit, 0, 0, 0);
	for (;;) ;
}
