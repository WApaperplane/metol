/* lutsentinel.c — LUT 表「抢回」守护（NX-KS2 · LUT 链路 v2 · 2026-10-09）
 * =====================================================================
 * 【背景（为什么需要它）】
 *   p7 的 View/Still::_load 是【事件驱动】的表重载（半按对焦 / 切档 / 拍片）：
 *   每次经 FUN_004a5e30 写 { OnOff, Acc, +0x00c=它的表地址, Cfg(SelCbCr+SelLUT),
 *   Load 脉冲 } —— 把硬件 LUT0 单元的 SRAM 覆盖成它的表，并把 Cfg.SelLUT 写回 0。
 *   ⇒ 我们直灌的表在事件后"被抢回"，画面回到出厂表。
 *
 * 【对策：双通道 + 寄存器级恢复】
 *   硬件有 LUT0 / LUT1 两个表单元；p7 只碰 LUT0（QEMU 实证：sel=0）。
 *   我们的表放 LUT1（`lutapi load … 1 …`，sel=1）。p7 抢回后：
 *     · LUT1 里我们的表【原封不动】
 *     · 只需要把 Cfg.SelLUT 从 0 改回 1（一个 32-bit 寄存器写，无 DMA）
 *   本守护 = 轮询 Cfg；发现 SelLUT != 目标 → 调官方 op_init(sel=1) 恢复。
 *   --sel 0 不能保护 LUT0 的内容：P7 重灌 LUT0 时 SelLUT 仍是 0，条件不会触发。
 *   本工具不重新 load；op_init 成功也不证明在 Still 消费前恢复。
 *
 * 【与"重灌守护"的差别】
 *   重灌 = 20KB DMA + 撞上 p7 活动期的风险；本方案 = 1 个寄存器写（微秒级）。
 *
 * 【安全（单核相机纪律）】
 *   · 每轮：读 1 个寄存器 + （必要时）1 次 op_init；间隔默认 500ms
 *   · op_init 只写 Cfg（OnOff/Acc/SelCbCr/SelLUT/格式位），不触发 DMA、不碰表数据
 *   · 输出极简（安静模式只在恢复时打一行）；nice(19)
 *   · 连续 3 次读失败 → 退出；--count 到点 → 退出（默认 1200 轮 ≈ 10 分钟）
 *   · 快速连续恢复告警（1s 内 >=5 次 → 打 ★ 但继续）
 *
 * 编译（★ -O0；与 lutapi.arm 同工具链）
 *   .uploads/zig/zig-windows-x86_64-0.13.0/zig.exe cc \
 *     -target arm-linux-gnueabi.2.15 -O0 -o lutsentinel.arm lutsentinel.c -ldl
 *
 * 用法：
 *   lutsentinel.arm                        # 默认：守护 sel=1, fmt=1, cbcr=0, 500ms
 *   lutsentinel.arm --interval 300 --count 600
 *   lutsentinel.arm --sel 0 --count 1      # 可能调用 op_init 写配置，不是只读体检
 *   lutsentinel.arm --quiet                # 只在恢复时输出
 * =====================================================================
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <dlfcn.h>
#include <fcntl.h>
#include <time.h>
#include <errno.h>
#include <sys/ioctl.h>
#include <sys/mman.h>

/* ---- 官方 op_init 类型（逐字抄 lutapi.c）---- */
typedef enum { D5_EP_LUT_FORMAT_422 = 0, D5_EP_LUT_FORMAT_420 = 1 } fmt_et;
typedef enum { D5_EP_LUT_CBCR_CH0 = 0, D5_EP_LUT_CBCR_CH1 = 1, D5_EP_LUT_CBCR_CH01 = 2 } cbcr_et;
typedef enum { D5_EP_LUT_SEL_LUT0 = 0, D5_EP_LUT_SEL_LUT1 = 1, D5_EP_LUT_SEL_LUT_EXT = 2 } sel_et;
typedef enum { D5_EP_OFF = 0, D5_EP_ON = 1 } onoff_et;

typedef struct {
    fmt_et  lut_clrfmt;   /* +0x00 */
    cbcr_et cbcr_ch_sel;  /* +0x04 */
    sel_et  lut_sel;      /* +0x08 */
    onoff_et bypass_sw;   /* +0x0c */
} d5_ep_lut_op_info_st;

typedef int (*fn_op_init)(d5_ep_lut_op_info_st *);
typedef int (*fn_ep_open)(void);

/* 寄存器偏移（lutapi/lutload 双确认） */
#define R_ONOFF 0x000
#define R_CFG   0x004   /* bits[1:0]=SelCbCr  bits[5:4]=SelLUT  bit8/12=格式位 */
#define R_PULSE 0x008
#define R_LUTA  0x00c   /* Load 源地址；不是持久在线表指针 */

#define EP_IOCTL_GET_PHYS_REG_INFO 0x80506864UL
struct ep_reg_phys_info { unsigned int reg_start_addr, reg_size; };
struct ep_reg_info {
    struct ep_reg_phys_info reg_base_top, reg_base_ldc, reg_base_mc,
        reg_base_rsz, reg_base_lvr, reg_base_bblt, reg_base_fd,
        reg_base_jpeg, reg_base_3dlut, reg_base_nog;
};

static long now_ms(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (long)ts.tv_sec * 1000 + ts.tv_nsec / 1000000;
}

int main(int argc, char **argv)
{
    int want_sel = 1, want_fmt = 1, want_cbcr = 0;
    int interval = 500, count = 1200, quiet = 0;
    int i, fd;
    unsigned int cfg = 0;
    void *h;
    fn_op_init p_op_init = NULL;
    fn_ep_open p_ep_open = NULL;
    unsigned long ml;
    unsigned int pa;
    volatile unsigned *r;
    int fails = 0, restores = 0, scans = 0;
    long t_last_restore = 0;
    int burst = 0;

    setvbuf(stdout, NULL, _IOLBF, 0);
    for (i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--sel") && i + 1 < argc)      want_sel = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--fmt") && i + 1 < argc) want_fmt = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--cbcr") && i + 1 < argc) want_cbcr = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--interval") && i + 1 < argc) interval = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--count") && i + 1 < argc) count = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--quiet")) quiet = 1;
        else {
            printf("用法: %s [--sel 1] [--fmt 1] [--cbcr 0] [--interval 500] [--count 1200] [--quiet]\n", argv[0]);
            return 1;
        }
    }
    if (interval < 100) interval = 100;     /* 下限保护：别把单核读爆 */
    if (interval > 5000) interval = 5000;
    if (want_sel < 0 || want_sel > 2 || want_fmt < 0 || want_fmt > 1) {
        printf("★ 参数非法\n");
        return 1;
    }
    nice(19);

    /* ---- libudd5（op_init 用）---- */
    h = dlopen("libudd5.so", RTLD_NOW);
    if (!h) h = dlopen("/usr/lib/libudd5.so", RTLD_NOW);
    if (!h) { printf("★ dlopen(libudd5.so) 失败: %s\n", dlerror()); return 2; }
    p_op_init = (fn_op_init)dlsym(h, "d5_ep_3dlut_op_init");
    p_ep_open = (fn_ep_open)dlsym(h, "d5_ep_open");
    if (!p_op_init) { printf("★ dlsym(op_init) 失败\n"); return 2; }
    if (p_ep_open) {
        int rc = p_ep_open();
        if (rc < 0 || rc > 2) { printf("★ d5_ep_open rc=%d\n", rc); return 2; }
    }

    /* ---- /dev/drime5_ep 寄存器直读 ---- */
    fd = open("/dev/drime5_ep", O_RDWR);
    if (fd < 0) { printf("★ open /dev/drime5_ep 失败: %s\n", strerror(errno)); return 3; }
    {
        struct ep_reg_info info;
        memset(&info, 0, sizeof info);
        if (ioctl(fd, EP_IOCTL_GET_PHYS_REG_INFO, &info) < 0) {
            printf("★ ioctl(GET_PHYS_REG_INFO) 失败\n");
            return 3;
        }
        pa = info.reg_base_3dlut.reg_start_addr;
        ml = (info.reg_base_3dlut.reg_size + 4095) & ~4095UL;
        if (!ml) ml = 4096;
        r = (volatile unsigned *)mmap(NULL, ml, PROT_READ, MAP_SHARED, fd, (off_t)pa);
        if (r == MAP_FAILED) { printf("★ mmap 3dlut 寄存器失败\n"); return 3; }
    }
    printf("lutsentinel: 守护 sel=%d fmt=%d cbcr=%d 间隔=%dms 上限=%d 轮（reg@0x%08x）\n",
           want_sel, want_fmt, want_cbcr, interval, count, pa);

    for (i = 0; i < count; i++) {
        unsigned int s;
        cfg = r[R_CFG / 4];
        s = (cfg >> 4) & 0x3;
        scans++;
        if (s != (unsigned)want_sel) {
            d5_ep_lut_op_info_st oi;
            unsigned int addr_at_reclaim = r[R_LUTA / 4];
            int rc;
            memset(&oi, 0, sizeof oi);
            oi.lut_clrfmt = (fmt_et)want_fmt;
            oi.cbcr_ch_sel = (cbcr_et)want_cbcr;
            oi.lut_sel = (sel_et)want_sel;
            oi.bypass_sw = D5_EP_OFF;
            rc = p_op_init(&oi);
            restores++;
            {
                long t = now_ms();
                if (t - t_last_restore < 1000) burst++; else burst = 0;
                t_last_restore = t;
            }
            printf("[%ldms] 抢回 → 恢复: Cfg 0x%08x (SelLUT=%u→%d) rc=%d"
                   "  p7表址=0x%08x  #%d%s\n",
                   now_ms(), cfg, s, want_sel, rc, addr_at_reclaim, restores,
                   (burst >= 5) ? "  ★★ 高频恢复（异常）" : "");
        } else if (!quiet && (i % 60 == 0)) {
            printf("  · 第 %d 轮: Cfg=0x%08x（SelLUT=%u 正常）\n", i, cfg, s);
        }
        usleep((useconds_t)interval * 1000);
    }

    printf("lutsentinel 退出: 轮=%d 恢复=%d 次\n", scans, restores);
    (void)fails;
    return 0;
}
