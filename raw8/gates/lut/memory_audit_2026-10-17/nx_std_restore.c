/* nx_std_restore.c — 把 identity 表写入标准池 0x810FD100（不自动还原）
 * 用于验证「写正在使用的池，画面是否实时变化」。
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
static void bcopy_(unsigned char *d, unsigned char *s, int n)
{
	int i;
	for (i = 0; i < n; i++) d[i] = s[i];
}

#define BASE    0x810FD000u
#define OFF     0x100u
#define LEN     19712u
#define MAPLEN  0x5000u

static unsigned char buf[LEN];

int main(void)
{
	int mfd, ffd, r, p;
	unsigned char *m;

	puts_("=== restore std pool from baseline 0x810FD100 ===\n");
	ffd = sc3(SYS_open, (int)"/mnt/mmc/std_baseline.bin", 0, 0);
	if (ffd < 0) { puts_("no identity file\n"); return 0; }
	r = sc3(SYS_read, ffd, (int)buf, (int)LEN);
	sc3(SYS_close, ffd, 0, 0);
	puts_("read identity = "); putn(r); puts_("\n");
	if (r != (int)LEN) return 0;

	mfd = sc3(SYS_open, (int)"/dev/mem", 2, 0);
	p = (int)sc6(SYS_mmap2, 0, (int)MAPLEN, 3, 1, mfd, BASE >> 12);
	if ((unsigned int)p >= 0xFFFFF000u) { puts_("mmap failed\n"); return 0; }

	m = (unsigned char *)p;
	bcopy_(m + OFF, buf, LEN);
	puts_("restored from baseline.\n");
	return 0;
}

void _start(void)
{
	main();
	sc3(SYS_exit, 0, 0, 0);
	for (;;) ;
}
