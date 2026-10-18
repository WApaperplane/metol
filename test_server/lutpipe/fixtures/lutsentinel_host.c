/* Replay the real sentinel control flow with every device/library call replaced.
 * No device files, shared camera library, DMA or sleeping are used by this harness.
 * The table generation is a model of a reload, not a hardware SRAM simulation.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <dlfcn.h>
#include <fcntl.h>
#include <time.h>
#include <errno.h>
#include <stdarg.h>
#include <sys/ioctl.h>
#include <sys/mman.h>

static void *fake_dlopen(const char *, int);
static void *fake_dlsym(void *, const char *);
static int fake_open(const char *, int, ...);
static int fake_ioctl(int, unsigned long, ...);
static void *fake_mmap(void *, size_t, int, int, int, off_t);
static int fake_usleep(useconds_t);
static int fake_nice(int);

#define dlopen fake_dlopen
#define dlsym fake_dlsym
#define open fake_open
#define ioctl fake_ioctl
#define mmap fake_mmap
#define usleep fake_usleep
#define nice fake_nice
#define main sentinel_entry
#include "../lutsentinel.c"
#undef main

static unsigned regs[1024];
static int op_calls, reloads, table_generation;

static int fake_ep_open(void) { return 0; }
static int fake_op_init(d5_ep_lut_op_info_st *p)
{
    op_calls++;
    regs[R_CFG / 4] = (regs[R_CFG / 4] & ~0x30u) | ((unsigned)p->lut_sel << 4);
    return 0;
}
static void *fake_dlopen(const char *p, int flags)
{
    (void)p; (void)flags;
    return (void *)1;
}
static void *fake_dlsym(void *h, const char *name)
{
    (void)h;
    if (!strcmp(name, "d5_ep_open")) return (void *)fake_ep_open;
    if (!strcmp(name, "d5_ep_3dlut_op_init")) return (void *)fake_op_init;
    fprintf(stderr, "unexpected library call: %s\n", name);
    exit(90);
}
static int fake_open(const char *path, int flags, ...)
{
    if (strcmp(path, "/dev/drime5_ep") || flags != O_RDWR) exit(91);
    return 42;
}
static int fake_ioctl(int fd, unsigned long req, ...)
{
    va_list ap;
    struct ep_reg_info *p;
    if (fd != 42 || req != EP_IOCTL_GET_PHYS_REG_INFO) exit(92);
    va_start(ap, req);
    p = va_arg(ap, struct ep_reg_info *);
    va_end(ap);
    p->reg_base_3dlut.reg_start_addr = 0x2082b000;
    p->reg_base_3dlut.reg_size = sizeof regs;
    return 0;
}
static void *fake_mmap(void *addr, size_t len, int prot, int flags, int fd, off_t off)
{
    if (addr || len != sizeof regs || prot != PROT_READ || flags != MAP_SHARED ||
        fd != 42 || off != 0x2082b000) exit(93);
    return regs;
}
static int fake_usleep(useconds_t t)
{
    (void)t;
    /* P7 reselects LUT0 and replaces its contents between polling iterations. */
    regs[R_CFG / 4] = 0x1100;
    table_generation++;
    reloads++;
    return 0;
}
static int fake_nice(int increment) { (void)increment; return 0; }

int main(int argc, char **argv)
{
    int rc;
    regs[R_CFG / 4] = 0x1100;
    regs[R_LUTA / 4] = 0x81115200;
    rc = sentinel_entry(argc, argv);
    printf("HARNESS op_init_calls=%d simulated_reloads=%d table_generation=%d cfg=0x%x\n",
           op_calls, reloads, table_generation, regs[R_CFG / 4]);
    return rc;
}
