/* fontprobe.c — 字体打开成本分解（相机 ABI，qemu-arm 或真机）

   为什么需要它：NXUI 首帧 ~307 ms 里 font_ms=226（74%），而 nxui.c 的注释只
   给出了粗粒度归因（FcFreeTypeQuery 154 ms、FT_New_Face 1 ms）。要判断
   "裁剪字体"是否真的有效，必须先确认这笔开销跟 **cmap 码点数** 相关，而不
   是跟文件字节数相关 —— 两者的优化手段完全不同。

   输出每一行都是 key=value，方便 bench 脚本直接 grep。

   用法: fontprobe <font-file> [repeat]
*/
#define _POSIX_C_SOURCE 199309L
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <ft2build.h>
#include FT_FREETYPE_H
#include <fontconfig/fontconfig.h>
#include <fontconfig/fcfreetype.h>

static long long now_ms(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (long long)ts.tv_sec * 1000 + ts.tv_nsec / 1000000;
}

/* 逐码点调用 FT_Get_Char_Index，模拟 FcFreeTypeQuery 建 charset 的内层循环，
   但去掉 fontconfig 的其它属性解析。两者相减即可看出 charset 构建占多少。 */
static long long scan_charset(FT_Face face, FcCharSet *set)
{
    FT_UInt index = 0, glyph;
    long long n = 0;
    (void)set;
    glyph = FT_Get_First_Char(face, &index);
    while (index) {
        n++;
        glyph = FT_Get_Next_Char(face, glyph, &index);
    }
    return n;
}

int main(int argc, char **argv)
{
    const char *file;
    int repeat = 3, r;
    FcBlanks *blanks;
    FcPattern *pattern;
    FcCharSet *set;
    int count = 0;
    long long best_query = -1, best_scan = -1, best_face = -1;
    FT_Library lib;
    FT_Face face;
    long long t0, t1;
    FILE *f;
    long bytes;

    if (argc < 2) { fprintf(stderr, "usage: fontprobe <font-file> [repeat]\n"); return 2; }
    file = argv[1];
    if (argc > 2) repeat = atoi(argv[2]);
    if (repeat < 1) repeat = 1;

    f = fopen(file, "rb");
    if (!f) { fprintf(stderr, "cannot open %s\n", file); return 3; }
    fseek(f, 0, SEEK_END); bytes = ftell(f); fclose(f);

    FcInit();
    blanks = FcBlanksCreate();
    if (FT_Init_FreeType(&lib) != 0) { fprintf(stderr, "FT_Init_FreeType failed\n"); return 4; }

    for (r = 0; r < repeat; r++) {
        long long q;
        /* 1) 完整 fontconfig 查询：这就是 XftFontOpenName 内部的第一步 */
        t0 = now_ms();
        pattern = FcFreeTypeQuery((const FcChar8 *)file, 0, blanks, &count);
        q = now_ms() - t0;
        if (q < best_query || best_query < 0) best_query = q;
        if (!pattern) { fprintf(stderr, "FcFreeTypeQuery failed\n"); return 5; }
        FcPatternDestroy(pattern);

        /* 2) 只走 FreeType 的 cmap 遍历：纯字符集成本，无 fontconfig 属性 */
        t0 = now_ms();
        if (FT_New_Face(lib, file, 0, &face) != 0) { fprintf(stderr, "FT_New_Face failed\n"); return 6; }
        t1 = now_ms();
        if (t1 - t0 < best_face || best_face < 0) best_face = t1 - t0;
        t0 = now_ms();
        set = FcFreeTypeCharSet(face, blanks);
        t1 = now_ms();
        if (t1 - t0 < best_scan || best_scan < 0) best_scan = t1 - t0;
        if (set) FcCharSetDestroy(set);
        FT_Done_Face(face);
    }

    /* stderr, not stdout: under -nostdlib the process exits through
     * __libc_start_main without a guaranteed stdio flush at the tail, and a
     * probed run that prints nothing is worse than a noisy one. */
    fprintf(stderr, "file=%s\n", file);
    fprintf(stderr, "bytes=%ld\n", bytes);
    fprintf(stderr, "codepoints=%d\n", count);
    fprintf(stderr, "newface_ms=%lld\n", best_face);
    fprintf(stderr, "charset_ms=%lld\n", best_scan);
    fprintf(stderr, "query_ms=%lld\n", best_query);
    fprintf(stderr, "repeat=%d\n", repeat);
    fflush(NULL);
    return 0;
}
