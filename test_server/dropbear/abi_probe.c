/* abi_probe.c —— 验证「宿主 gcc-13 + 相机 glibc 2.13」这条 ABI 链是否可用
 * 目的：在正式编 dropbear 之前，用最小代价确认下列硬约束全部成立：
 *   - crt0 替换后不报 GLIBC_2.34
 *   - getpwnam / openpty / crypt / fork / select / pthread 都能在 2.13 上落位
 *   - -D_FILE_OFFSET_BITS=32 下 stat 布局正确
 * 输出一行 "PROBE OK ..."，失败则打印 errno 并返回非 0。
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <unistd.h>
#include <fcntl.h>
#include <pwd.h>
#include <crypt.h>
#include <pty.h>
#include <termios.h>
#include <sys/select.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <pthread.h>
#include <time.h>

static int fails = 0;
#define CHK(name, cond) do { if (!(cond)) { printf("FAIL %s errno=%d(%s)\n", name, errno, strerror(errno)); fails++; } } while (0)

static void *thr(void *p) { return p; }

int main(void)
{
    /* 1. passwd 数据库（dropbear 登录必须） */
    struct passwd *pw = getpwnam("root");
    CHK("getpwnam", pw != NULL);
    if (pw) printf("  root uid=%d gid=%d dir=%s shell=%s\n", pw->pw_uid, pw->pw_gid, pw->pw_dir, pw->pw_shell);

    /* 2. pty（dropbear 会话必须，来自 libutil） */
    int mfd = -1, sfd = -1;
    struct termios tio;
    CHK("openpty", openpty(&mfd, &sfd, NULL, NULL, NULL) == 0);
    if (mfd >= 0) { printf("  pty master=%d slave=%d\n", mfd, sfd); close(mfd); close(sfd); }

    /* 3. crypt（密码认证，来自 libcrypt） */
    char *c = crypt("test", "$1$abcdefgh$");
    CHK("crypt", c != NULL && strlen(c) > 10);
    if (c) printf("  crypt=%s\n", c);

    /* 4. stat / file offset 布局 */
    struct stat st;
    CHK("stat", stat("/etc/passwd", &st) == 0);
    printf("  stat size=%ld (sizeof off_t=%d, struct stat=%d)\n", (long)st.st_size, (int)sizeof(off_t), (int)sizeof(struct stat));

    /* 5. fork + waitpid + pipe */
    int pfd[2];
    CHK("pipe", pipe(pfd) == 0);
    pid_t pid = fork();
    CHK("fork", pid >= 0);
    if (pid == 0) { close(pfd[0]); if (write(pfd[1], "z", 1) != 1) _exit(3); _exit(0); }
    close(pfd[1]);
    char ch = 0;
    ssize_t r = read(pfd[0], &ch, 1);
    int wst = 0;
    waitpid(pid, &wst, 0);
    CHK("child io", r == 1 && ch == 'z' && WEXITSTATUS(wst) == 0);
    close(pfd[0]);

    /* 6. socket + bind（dropbear 监听必须） */
    int sk = socket(AF_INET, SOCK_STREAM, 0);
    CHK("socket", sk >= 0);
    if (sk >= 0) {
        struct sockaddr_in sa;
        memset(&sa, 0, sizeof sa);
        sa.sin_family = AF_INET;
        sa.sin_port = htons(0);
        sa.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
        CHK("bind", bind(sk, (struct sockaddr *)&sa, sizeof sa) == 0);
        CHK("listen", listen(sk, 5) == 0);
        close(sk);
    }

    /* 7. select */
    fd_set rf;
    FD_ZERO(&rf);
    struct timeval tv;
    tv.tv_sec = 0; tv.tv_usec = 1000;
    CHK("select", select(0, &rf, NULL, NULL, &tv) == 0);

    /* 8. pthread（dropbear 不重度用，但链接要能落位） */
    pthread_t t;
    CHK("pthread_create", pthread_create(&t, NULL, thr, NULL) == 0);
    pthread_join(t, NULL);

    /* 9. 时钟 */
    struct timespec ts;
    CHK("clock_gettime", clock_gettime(CLOCK_MONOTONIC, &ts) == 0);

    if (fails) { printf("PROBE FAILED: %d check(s)\n", fails); return 1; }
    printf("PROBE OK (all checks passed)\n");
    return 0;
}
