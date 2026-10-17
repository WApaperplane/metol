/* nx_lutdump.c — 只读 dump 64KB 物理内存到文件（供 PC 侧分析） */
#define SYS_exit    1
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

#define ADDR  0x810F0000u
#define LEN   0x40000u
#define O_WRONLY 1
#define O_CREAT  0x40
#define O_TRUNC  0x200

int main(void)
{
	int mfd, ofd, p, w;
	unsigned int pgoff = ADDR >> 12;

	puts_("=== dump "); puthex(ADDR); puts_(" len="); putn(LEN); puts_(" ===\n");

	mfd = sc3(SYS_open, (int)"/dev/mem", 0, 0);
	if (mfd < 0) { puts_("open /dev/mem failed\n"); return 0; }
	p = (int)sc6(SYS_mmap2, 0, (int)LEN, 1, 1, mfd, pgoff);
	if ((unsigned int)p >= 0xFFFFF000u) { puts_("mmap failed\n"); return 0; }
	puts_("mmap ok\n");

	ofd = sc3(SYS_open, (int)"/mnt/mmc/dram_pools_256k.bin", O_WRONLY | O_CREAT | O_TRUNC, 0644);
	puts_("open out = "); putn(ofd); puts_("\n");
	if (ofd < 0) return 0;

	w = sc3(SYS_write, ofd, p, (int)LEN);
	puts_("wrote "); putn(w); puts_("\n");
	sc3(SYS_close, ofd, 0, 0);
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
