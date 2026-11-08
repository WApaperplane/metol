/* NX500 1.12 runtime LUT0 loader. No table writes or firmware persistence.
 * EP RD_FINISH acknowledges the transfer; rendered output is tested separately.
 * Header ioctl definitions: Samsung DRIMe5 GPL EP interface (sysarch/inc).
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <signal.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/file.h>
#include <sys/time.h>
#include <sys/wait.h>
#include <dirent.h>
#include <time.h>
#include <media/drime5/ep/d5_ep_ioctl.h>

static volatile sig_atomic_t stopping;
static void stop(int sig) { (void)sig; stopping=1; }
static void barrier(void) {
    __asm__ volatile("mcr p15, 0, %0, c7, c10, 4" :: "r"(0) : "memory");
}
static double now_ms(void) {
    struct timespec ts; clock_gettime(CLOCK_MONOTONIC,&ts);
    return ts.tv_sec*1000.0+ts.tv_nsec/1000000.0;
}
static int camera_ok(void) {
    char version[32],model[32];FILE *f=fopen("/etc/version.info","r");
    int ok=f && fgets(version,sizeof(version),f) && fgets(model,sizeof(model),f)
        && !strcmp(version,"1.12\n") && !strcmp(model,"NX500\n");
    if(f)fclose(f);return ok;
}
static void dump(const char *tag,volatile unsigned *r) {
    printf("%s on=%08x cfg=%08x access=%08x lut0=%08x lut1=%08x\n",
           tag,r[0],r[1],r[2],r[3],r[4]);fflush(stdout);
}
static int load_main(int argc,char **argv) {
    int fd=-1,mem=-1,lock=-1,rc=1,started=0,wait_only;
    int irq=EP_K_INT_ACC_3DLUT_RD_FINISH,wr,err;
    unsigned addr=0;char *end;
    volatile unsigned *r=MAP_FAILED;
    struct ep_k_acc_intr_wait_info wq;
    double t;
    if(argc==2 && !strcmp(argv[1],"wait-test"))wait_only=1;
    else if(argc==3 && !strcmp(argv[1],"once")) {
        wait_only=0;errno=0;addr=strtoul(argv[2],&end,0);
        /* Six factory/working slots only. A12/A14 are the AdobeRGB view slots,
         * A13 the sRGB+screen-color one, A17 the factory sRGB one; A18/A19 are
         * the working slots lut.sh writes. off() needs A12..A17 so it can kick
         * whichever slot p7 has just selected instead of only the working one. */
        if(errno || !*argv[2] || *end ||
           !(addr==0x810fd100u || addr==0x81101e00u || addr==0x81106b00u ||
             addr==0x81115200u || addr==0x81119f00u || addr==0x8111ec00u)) {
            fprintf(stderr,"REFUSE unsupported slot\n");return 2;
        }
    } else {fprintf(stderr,"usage: nx_lutload.arm once <slot> | wait-test\n");return 2;}
    if(!camera_ok()) {fprintf(stderr,"REFUSE expected NX500 1.12\n");return 3;}
    lock=open("/tmp/nxwa_lutload.lock",O_RDWR|O_CREAT,0600);
    if(lock<0 || flock(lock,LOCK_EX|LOCK_NB)<0) {perror("loader lock");rc=4;goto out;}
    signal(SIGTERM,stop);signal(SIGINT,stop);signal(SIGHUP,stop);
    fd=open("/dev/drime5_ep",O_RDWR);
    if(fd<0) {perror("EP open");goto out;}
    if(ioctl(fd,EP_IOCTL_ACC_INTR_ENABLE,&irq)<0) {perror("IRQ enable");goto out;}
    memset(&wq,0,sizeof(wq));wq.timeout_ms=wait_only?120:500;wq.intr=irq;
    if(ioctl(fd,EP_IOCTL_ACC_INTR_WAIT_QUEUE_INIT,&wq)<0) {perror("IRQ queue");goto out;}
    if(!wait_only) {
        mem=open("/dev/mem",O_RDWR|O_SYNC);
        if(mem<0) {perror("MMIO open");goto out;}
        r=mmap(0,4096,PROT_READ|PROT_WRITE,MAP_SHARED,mem,0x2082b000);
        if(r==MAP_FAILED) {perror("MMIO mmap");goto out;}
        dump("BEFORE",r);
        if(r[1]!=0 && r[1]!=0x100) {fprintf(stderr,"REFUSE unexpected cfg\n");rc=5;goto out;}
        if(stopping) {rc=7;goto out;}
        started=1;r[0]|=1;r[2]&=~1u;r[2]|=1u;
        r[3]=addr;r[1]=(r[1]&~0x30u)|0x100u;barrier();
        r[2]|=0x100u;barrier();r[2]&=~0x100u;barrier();
    }
    t=now_ms();errno=0;wr=ioctl(fd,EP_IOCTL_ACC_INTR_WAIT,&wq);err=errno;
    printf("WAIT rc=%d errno=%d elapsed_ms=%.3f jpeg_err=%u irq=%d trigger=%d\n",
           wr,err,now_ms()-t,wq.jpeg_err,irq,!wait_only);fflush(stdout);
    if(started) {r[2]|=1u;r[2]&=~1u;barrier();dump("PROCESS",r);}
    if(wait_only) {rc=(wr<0 && err==ETIMEDOUT)?0:6;goto out;}
    if(wr<0 || wq.jpeg_err || stopping) {rc=6;goto out;}
    if(!(r[0]&1) || r[1]!=0x100 || (r[2]&1) || r[3]!=addr) {rc=8;goto out;}
    puts("OK DMA_RD_FINISH and processing mode verified");rc=0;
out:
    if(started && r!=MAP_FAILED) {r[2]&=~1u;barrier();}
    if(r!=MAP_FAILED)munmap((void*)r,4096);
    if(mem>=0)close(mem);if(fd>=0)close(fd);if(lock>=0)close(lock);
    return rc;
}

static unsigned fingerprint(volatile const unsigned char *p) {
    unsigned i,h=2166136261u;
    for(i=0;i<19712;i++)h=(h^p[i])*16777619u;
    return h;
}
/* A writable MP4 descriptor in the camera process is the recording signal.
 * This was observed on the real device; no guessed capdtm state or key toggle. */
static int recording(int pid,char *name,size_t size) {
    char path[512],target[512],line[128];struct dirent *de;DIR *d;FILE *f;
    snprintf(path,sizeof(path),"/proc/%d/fd",pid);d=opendir(path);
    if(!d)return -1;
    while((de=readdir(d))) {
        ssize_t n;unsigned flags=0;int got=0;
        if(de->d_name[0]<'0'||de->d_name[0]>'9')continue;
        snprintf(path,sizeof(path),"/proc/%d/fd/%s",pid,de->d_name);
        n=readlink(path,target,sizeof(target)-1);if(n<4)continue;target[n]=0;
        if(!strstr(target,"/DCIM/") || strcasecmp(target+n-4,".mp4"))continue;
        snprintf(path,sizeof(path),"/proc/%d/fdinfo/%s",pid,de->d_name);
        f=fopen(path,"r");if(!f)continue;
        while(fgets(line,sizeof(line),f))if(sscanf(line,"flags: %o",&flags)==1){got=1;break;}
        fclose(f);
        if(got && (flags&O_ACCMODE)!=O_RDONLY) {
            snprintf(name,size,"%s",target);closedir(d);return 1;
        }
    }
    closedir(d);return 0;
}
static int registered(volatile const unsigned *v,unsigned addr) {
    return v[0]==addr && v[1]==addr && v[2]==addr && v[3]==addr;
}
static int watch_main(int argc,char **argv) {
    int pid,seconds,mem=-1,lock=-1,rc=1,was=0,failures=0,loads=0,pending=0;
    char path[128],cmd[512],file[512]="",previous[512]="",*end;
    unsigned addr=0x81119f00u,prior_hash,loaded_hash;
    volatile unsigned *reg=MAP_FAILED,*view=MAP_FAILED;
    volatile unsigned char *pool=MAP_FAILED;
    double begin,last_load=-1000,settle_until=0;
    unsigned old_on=0,old_cfg=0,old_source=0;
    FILE *f;
    if(argc!=4)return 2;
    pid=strtol(argv[2],&end,10);if(*end||pid<2)return 2;
    seconds=strtol(argv[3],&end,10);if(*end||seconds<0||seconds>3600)return 2;
    if(!camera_ok())return 3;
    snprintf(path,sizeof(path),"/proc/%d/cmdline",pid);f=fopen(path,"r");
    if(!f)return 3;
    memset(cmd,0,sizeof(cmd));fread(cmd,1,sizeof(cmd)-1,f);fclose(f);
    if(!strstr(cmd,"/di-camera-app")) {fprintf(stderr,"REFUSE camera PID identity\n");return 3;}
    lock=open("/tmp/nxwa_lutwatch.lock",O_RDWR|O_CREAT,0600);
    if(lock<0||flock(lock,LOCK_EX|LOCK_NB)<0){perror("watch lock");rc=4;goto out;}
    mem=open("/dev/mem",O_RDONLY|O_SYNC);if(mem<0)goto out;
    reg=mmap(0,4096,PROT_READ,MAP_SHARED,mem,0x2082b000);
    view=mmap(0,4096,PROT_READ,MAP_SHARED,mem,0x80383000);
    pool=mmap(0,24576,PROT_READ,MAP_SHARED,mem,0x81119000);
    if(reg==MAP_FAILED||view==MAP_FAILED||pool==MAP_FAILED)goto out;
    if(!registered(view+0x7f0/4,addr)) {
        fprintf(stderr,"REFUSE apply a LUT in this boot before video on\n");rc=5;goto out;
    }
    signal(SIGTERM,stop);signal(SIGINT,stop);signal(SIGHUP,stop);
    prior_hash=loaded_hash=fingerprint(pool+0xf00);begin=now_ms();
    printf("READY pid=%d duration=%d slot=%08x hash=%08x\n",pid,seconds,addr,prior_hash);fflush(stdout);
    while(!stopping && (!seconds || now_ms()-begin<seconds*1000.0)) {
        unsigned hash=fingerprint(pool+0xf00),on=reg[0],cfg=reg[1],source=reg[3];
        int stable=on==old_on && cfg==old_cfg && source==old_source;
        int rec=recording(pid,file,sizeof(file));
        int fresh=rec>0 && (!was || strcmp(file,previous));
        if(rec<0){puts("END camera process disappeared");rc=7;goto out;}
        if(!registered(view+0x7f0/4,addr)){puts("END LUT registry disabled");rc=0;goto out;}
        if(fresh){pending=1;settle_until=now_ms()+400;printf("RECORD_START %s\n",file);snprintf(previous,sizeof(previous),"%s",file);}
        if(was && !rec)printf("RECORD_STOP %s\n",previous);
        if(!rec)pending=0;
        if(rec && stable && now_ms()>=settle_until && hash==prior_hash &&
           (pending || hash!=loaded_hash || reg[3]!=addr || !(reg[0]&1)) &&
           now_ms()-last_load>=500) {
            int status;pid_t child;fflush(stdout);child=fork();
            if(child<0){rc=1;goto out;}
            fflush(stdout);
            if(!child) {char *a[]={argv[0],"once","0x81119f00",0};int result;stopping=0;result=load_main(3,a);fflush(stdout);_exit(result);}
            while(waitpid(child,&status,0)<0)if(errno!=EINTR){rc=1;goto out;}
            last_load=now_ms();loads++;
            if(!WIFEXITED(status)||WEXITSTATUS(status)) {
                failures++;printf("LOAD_FAILED status=%d count=%d\n",status,failures);
                if(failures>=2){rc=6;goto out;}
            } else {loaded_hash=hash;failures=0;pending=0;printf("LOADED hash=%08x recording=%s\n",hash,file);}
        }
        prior_hash=hash;old_on=on;old_cfg=cfg;old_source=source;was=rec;fflush(stdout);usleep(200000);
    }
    rc=0;
out:
    printf("END loads=%d rc=%d\n",loads,rc);fflush(stdout);
    if(pool!=MAP_FAILED)munmap((void*)pool,24576);
    if(view!=MAP_FAILED)munmap((void*)view,4096);
    if(reg!=MAP_FAILED)munmap((void*)reg,4096);
    if(mem>=0)close(mem);if(lock>=0)close(lock);return rc;
}
int main(int argc,char **argv) {
    if(argc>1 && !strcmp(argv[1],"watch"))return watch_main(argc,argv);
    return load_main(argc,argv);
}
