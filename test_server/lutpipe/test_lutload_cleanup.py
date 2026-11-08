#!/usr/bin/env python3
"""Execute load_main with host device stubs; logging must see processing mode.

Run on Linux/WSL with gcc. NXWA_LUTLOAD_SOURCE selects an unmodified baseline.
Only the ARM memory barrier is replaced in the temporary host translation unit.
No camera, mounts, or device IO is used.
"""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(os.environ.get('NXWA_LUTLOAD_SOURCE', Path(__file__).with_name('nx_lutload.c')))

HARNESS = r'''
#include <stdarg.h>
#include <assert.h>
static unsigned regs[1024];
static int scenario, waiting, logged_in_access, frame_waits, dma_waits;
FILE *__wrap_fopen(const char *path, const char *mode) {
    FILE *f;
    (void)path; (void)mode;
    f=tmpfile(); assert(f); fputs("1.12\nNX500\n",f); rewind(f); return f;
}
int __wrap_open(const char *path, int flags, ...) {(void)path;(void)flags;return 20;}
int __wrap_close(int fd) {(void)fd;return 0;}
int __wrap_flock(int fd,int op) {(void)fd;(void)op;return 0;}
void *__wrap_mmap(void *p,size_t n,int prot,int flags,int fd,off_t off) {
    (void)p;(void)n;(void)prot;(void)flags;(void)fd;(void)off;return regs;
}
int __wrap_munmap(void *p,size_t n) {(void)p;(void)n;return 0;}
int __wrap_ioctl(int fd,unsigned long request,...) {
    va_list ap;struct ep_k_acc_intr_wait_info *q;(void)fd;
    if(request==EP_IOCTL_CORE_INTR_WAIT) {
        frame_waits++;
        if(scenario==6){errno=ETIMEDOUT;return -1;}
        return 100;
    }
    if(request!=EP_IOCTL_ACC_INTR_WAIT)return 0;
    dma_waits++;
    waiting=1;
    if(scenario==1 || scenario==5){errno=ETIMEDOUT;return -1;}
    if(scenario==2){va_start(ap,request);q=va_arg(ap,void*);va_end(ap);q->jpeg_err=1;}
    if(scenario==3){stopping=1;errno=EINTR;return -1;}
    return 120;
}
int __wrap_printf(const char *fmt,...) {
    (void)fmt;
    /* A slow output sink here must never keep the LUT in access mode.
     * Inspect the register at entry: no timing threshold or scheduler luck. */
    if(waiting && (regs[2]&1u))logged_in_access++;
    return 0;
}
int __wrap_fflush(FILE *f) {
    (void)f;if(waiting && (regs[2]&1u))logged_in_access++;return 0;
}
int main(int argc,char **argv) {
    int rc,expected;char *a[]={"loader","once","0x81119f00",NULL};
    assert(argc==2);scenario=atoi(argv[1]);
    regs[0]=1;regs[1]=0x100;regs[2]=0;regs[3]=0x81115200;
    if(scenario==4)regs[1]=0x10;
    if(scenario==5)a[1]="wait-test";
    rc=load_main(scenario==5?2:3,a,scenario!=7);
    expected=scenario==6?9:(scenario==4?5:((scenario>=1 && scenario<=3)?6:0));
    if(frame_waits!=((scenario==4 || scenario==5 || scenario==7)?0:1))return 2;
    if(scenario==6 && (dma_waits || regs[3]!=0x81115200 || regs[2]))return 3;
    if(rc!=expected || logged_in_access || regs[2]&1u) {
        fprintf(stderr,"scenario=%d rc=%d expected=%d log_in_access=%d access=%x\n",
                scenario,rc,expected,logged_in_access,regs[2]);return 1;
    }
    return 0;
}
'''


class CleanupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='nxwa-lutload-')
        cls.addClassCleanup(cls.temp.cleanup)
        folder = Path(cls.temp.name)
        source = SOURCE.read_text(encoding='utf-8')
        start = source.index('static void barrier(void) {')
        end = source.index('\n}', start) + 2
        source = source[:start] + 'static void barrier(void) {}' + source[end:]
        source = source.replace('int main(int argc,char **argv)', 'int device_main(int argc,char **argv)')
        host = folder / 'host.c'
        host.write_text(source + HARNESS, encoding='utf-8')
        cls.binary = folder / 'host'
        wrapped = ['fopen', 'open', 'close', 'flock', 'mmap', 'munmap', 'ioctl', 'printf', 'fflush']
        subprocess.run(['gcc', '-O0', '-fno-builtin', '-Wall', '-Wextra',
                        '-Werror', '-Wno-misleading-indentation',
                        '-I' + str(ROOT / 'test_server/sysarch/inc'), str(host),
                        *['-Wl,--wrap=' + name for name in wrapped], '-o', str(cls.binary)],
                       check=True, capture_output=True, text=True)

    def test_cleanup_before_logging(self):
        for scenario, name in enumerate(['success', 'timeout', 'jpeg_error',
                                         'signal', 'cfg_refused', 'wait_only',
                                         'frame_timeout', 'video_unsynced']):
            with self.subTest(name=name):
                result = subprocess.run([str(self.binary), str(scenario)],
                                        capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
