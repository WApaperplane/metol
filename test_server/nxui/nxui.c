/* NX-KS menus + persistent FilmLab strip. Nuklear / Xlib / Xft, no EFL.
 * The viewfinder stays on its existing camera plane: no frame capture or blit.
 * Rendering is event driven; the only timer is backend/debounce housekeeping.
 */
#define _POSIX_C_SOURCE 200809L
#define NK_INCLUDE_FIXED_TYPES
#define NK_INCLUDE_STANDARD_IO
#define NK_INCLUDE_STANDARD_VARARGS
#define NK_INCLUDE_DEFAULT_ALLOCATOR
#define NK_IMPLEMENTATION
#include "vendor/nuklear.h"
#define NK_XLIB_USE_XFT
#define NK_XLIB_IMPLEMENTATION
#include "vendor/nuklear_xlib.h"
#include <X11/keysym.h>
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <sys/file.h>
#include <sys/resource.h>
#include <sys/select.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include "nxui_model.h"
/* evdev（S1 半按快门）：结构手动定义，不依赖内核头 */
struct input_event { long tv_sec, tv_usec; unsigned short type, code; int value; };
#define EV_KEY 1
#include "nxui_services.h"

static struct nx_recipe recipes[NXUI_MAX_RECIPES];
static struct nx_item items[NXUI_MAX_ITEMS];
static struct nx_queue queue;
static const char *root = "/opt/usr/nx-ks", *engine = "/opt/usr/nx-ks/filmlab.sh";
static int count, item_count, selected, menu, page, live, dirty = 1, quit;
/* LUT mode: the same strip UI drives lut.sh instead of filmlab.sh, and the
 * registry/slot state is restored when the panel closes.
 * lut_keep is set when a shutter half-press closed the panel: the half-press
 * is what makes P7 reload the table, so the table must survive the panel. */
static int lut_mode = 0;
static int lut_keep = 0;
static int touch_x, touch_active, close_after_child;
static char enum_cache[16]; static long long enum_cache_ms;
static long long close_flag_check;
static int ev_fd = -1;
static int busy_kind, child_fd = -1, output_len, child_timed_out;
static pid_t child;
static long long child_started, lifetime;
static long long service_due;
static struct nx_services services;
static const char *net_dir = "/proc/net";
static int backend_phase, busy_recipe = -1, pipe_eof;
static char output[4096], status[384] = "选择配方以预览 · 保存后保留设置";
static char menu_path[NXUI_PATH];
static char pending_menu[NXUI_PATH];
static volatile sig_atomic_t interrupted;
static Display *display;
static Window window;
static int screen, width, height;
static struct nk_context *ctx;
/* The camera runs without a window manager: an XSetInputFocus taken by this
 * panel is never taken back by anyone else. Camera menu navigation (jog wheel
 * and arrow keys) arrives as X KeyPress, which is delivered only to the focus
 * window, so the panel has to record the previous focus and hand it back when
 * it closes. Otherwise the native menu looks like its keys stopped working. */
static Window prev_focus;
static int prev_revert = RevertToPointerRoot;
static int focus_saved, focus_restored, panel_unmapped;

static int ignore_xerror(Display *dpy, XErrorEvent *ev) { (void)dpy; (void)ev; return 0; }

static void save_focus(void) {
    XErrorHandler old;
    int revert = RevertToPointerRoot;
    if (!display) return;
    old = XSetErrorHandler(ignore_xerror);
    XGetInputFocus(display, &prev_focus, &revert);
    XSetErrorHandler(old);
    prev_revert = revert;
    focus_saved = 1; focus_restored = 0;
}

static void restore_focus(void) {
    XErrorHandler old;
    if (!display || !focus_saved || focus_restored) return;
    focus_restored = 1;
    old = XSetErrorHandler(ignore_xerror);
    /* The previous window may be gone (an entry script may have killed the old
     * menu). Fall back to PointerRoot so key events still follow the pointer
     * instead of being dropped. */
    XSetInputFocus(display, prev_focus == None ? PointerRoot : prev_focus,
        prev_revert, CurrentTime);
    XSync(display, False);
    XSetErrorHandler(old);
}

static long long now_ms(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return (long long)t.tv_sec * 1000 + t.tv_nsec / 1000000;
}
static void on_signal(int sig) { (void)sig; interrupted = 1; }
static void on_child(int sig) { (void)sig; } /* interrupt select; waitpid stays in the main loop */
static void message(const char *s) { snprintf(status, sizeof status, "%s", s); dirty = 1; }
static const char *base_name(const char *p) {
    const char *last = strrchr(p, '/'); return last ? last + 1 : p;
}
static int services_visible(void) {
    int i;
    if (!menu) return 0;
    for (i = page*6; i < item_count && i < page*6+6; i++)
        if (!strcmp(base_name(items[i].command), "telnet_toggle.sh")) return 1;
    return 0;
}
static void refresh_services(int force) {
    struct nx_services next; char label[192];
    if (!force && (!services_visible() || now_ms() < service_due)) return;
    nx_services_read(&next, net_dir);
    service_due = now_ms() + 1000;
    if (!nx_services_equal(&services, &next)) {
        services = next; dirty = 1;
        nx_services_label(&services, label, sizeof label);
        fprintf(stderr, "SERVICES known=%d telnet=%d ftp=%d label=%s\n", services.known, services.telnet, services.ftp, label);
    }
}
static void preview_status(void) {
    if (child && busy_kind == 1 && queue.desired >= 0 && queue.desired != queue.running)
        snprintf(status, sizeof status, "已选择 %s · 等待当前预览完成", recipes[queue.desired].label);
    else if (child && busy_kind == 1 && busy_recipe >= 0)
        snprintf(status, sizeof status, "%s：%s", backend_phase == 2 ? "正在确认" : (queue.committing ? "正在保存" : "正在发送"), recipes[busy_recipe].label);
    else snprintf(status, sizeof status, "%s：%s", live ? "准备预览" : "演示选择", recipes[selected].label);
    dirty = 1;
}
static int checked(const char *name) {
    char path[NXUI_PATH];
    snprintf(path, sizeof path, "%s/auto/%s", root, base_name(name));
    return access(path, F_OK) == 0;
}
static void resize_panel(void) {
    height = menu ? 336 : 192;
    if (height > DisplayHeight(display, screen)) height = DisplayHeight(display, screen);
    XMoveResizeWindow(display, window, (DisplayWidth(display, screen)-width)/2,
        DisplayHeight(display, screen)-height, (unsigned)width, (unsigned)height);
    /* Resize the official backend's pixmap as well as the native window. */
    nk_xsurf_resize(xlib.surf, (unsigned)width, (unsigned)height);
    dirty = 1;
}
static int load_menu(const char *source) {
    static struct nx_item pending[NXUI_MAX_ITEMS];
    char next[NXUI_PATH]; int n;
    if (!nx_menu_path(root, source, next, sizeof next) ||
        (n = nx_load_menu(next, pending, NXUI_MAX_ITEMS)) <= 0) {
        message("菜单读取失败 · 详情见日志"); return 0;
    }
    memcpy(items, pending, (size_t)n * sizeof *items);
    snprintf(menu_path, sizeof menu_path, "%s", next);
    item_count = n; page = 0; menu = 1;
    fprintf(stderr, "MENU file=%s items=%d\n", menu_path, item_count);
    resize_panel(); return 1;
}
static void choose(int index) {
    if (count <= 0 || queue.close_requested) return;
    selected = (index + count) % count;
    /* An explicit tap also reapplies after a camera/legacy-menu effect change. */
    queue.applied = -1;
    nx_queue_select(&queue, selected, now_ms());
    preview_status();
}
static void read_output(void) {
    char buf[512]; ssize_t n;
    if (child_fd < 0) return;
    while ((n = read(child_fd, buf, sizeof buf)) > 0) {
        int keep = (int)n;
        if (keep > (int)sizeof(output)-1-output_len) keep = (int)sizeof(output)-1-output_len;
        if (keep > 0) { memcpy(output + output_len, buf, (size_t)keep); output_len += keep; }
    }
    if (n == 0) pipe_eof = 1;
    output[output_len] = 0;
    if (busy_kind == 1 && backend_phase != 2 && strstr(output, "NXUI_STAGE restore")) {
        backend_phase = 2; preview_status();
    }
}
static int start_child(int kind, int index, const char *command) {
    int pipefd[2]; pid_t pid;
    if (child) return 0;
    if (!live) {
        if (kind == 1) {
            nx_queue_done(&queue, 1);
            message("演示模式 · 已选择，未写入相机");
            if (queue.committing) quit = 1;
        } else message("演示模式 · 未执行菜单命令");
        return 1;
    }
    if (pipe(pipefd) < 0) return 0;
    pid = fork();
    if (pid < 0) { close(pipefd[0]); close(pipefd[1]); return 0; }
    if (pid == 0) {
        char envpath[1024]; const char *old = getenv("PATH");
        setpgid(0, 0);
        close(pipefd[0]); dup2(pipefd[1], STDOUT_FILENO); dup2(pipefd[1], STDERR_FILENO);
        close(pipefd[1]); close(ConnectionNumber(display));
        if (chdir(root) != 0) _exit(126);
        snprintf(envpath, sizeof envpath, "%s:%s", root, old ? old : "/usr/bin:/bin");
        setenv("PATH", envpath, 1);
        if (kind == 1 && enum_cache[0]) setenv("FILMLAB_ENUM_CACHE", enum_cache, 1);
        if (kind == 1) {
            /* In LUT mode a dry run must not touch the registry or the slot:
             * "apply" is a real write, so it is only used when live. */
            const char *action = lut_mode ? (live ? "apply" : "status")
                                : (queue.committing ? "commit" : "preview");
            execl("/bin/sh", "sh", engine, action, recipes[index].key, (char *)0);
        }
        else execl("/bin/bash", "bash", "-c", command, (char *)0);
        _exit(127);
    }
    setpgid(pid, pid);
    close(pipefd[1]); fcntl(pipefd[0], F_SETFL, O_NONBLOCK);
    child_fd = pipefd[0]; child = pid; busy_kind = kind;
    busy_recipe = index; backend_phase = 0; pipe_eof = 0;
    child_started = now_ms(); child_timed_out = 0; output_len = 0;
    output[0] = 0;
    if (kind == 1) preview_status(); else message("正在执行…");
    return 1;
}
static void poll_child(void) {
    int code, success, was_commit; pid_t result;
    if (!child) return;
    read_output(); result = waitpid(child, &code, WNOHANG);
    if (result == 0) {
        long long age = now_ms() - child_started;
        if (age > 12000 && !child_timed_out) {
            child_timed_out = 1; kill(-child, SIGTERM);
            message("后端超时 · 正在停止，请检查相机状态");
        }
        if (age > 13000) kill(-child, SIGKILL);
        return;
    }
    if (result < 0 && errno == EINTR) return;
    read_output(); close(child_fd); child_fd = -1; child = 0;
    success = result > 0 && !child_timed_out && WIFEXITED(code) && WEXITSTATUS(code) == 0 &&
        !strstr(output, "VERIFY-FAIL") && !strstr(output, "REJECT");
    fprintf(stderr, "BACKEND kind=%d ok=%d elapsed_ms=%lld output=%s\n", busy_kind, success, now_ms()-child_started, output);
    if (busy_kind == 1) {
        was_commit = queue.committing;
        nx_queue_done(&queue, success);
        if (queue.desired >= 0 && queue.desired != busy_recipe) preview_status();
        else if (success) {
            snprintf(status, sizeof status, "已发送：%s", recipes[busy_recipe].label); dirty = 1;
        } else message("应用失败 · 可重新选择以重试");
        if (was_commit && success) quit = 1;
        if (!success) { queue.close_requested = 0; queue.commit_requested = 0; }
    } else if (busy_kind == 3) {
        if (success && load_menu(pending_menu)) message("请选择菜单项");
        else message("子菜单生成失败 · 可重新进入");
        pending_menu[0] = 0;
    } else if (busy_kind == 4) {
        refresh_services(1);
        if (!services.known) message("服务状态读取失败 · 请重试");
        else {
            snprintf(status, sizeof status, "%sTelnet 已%s · FTP 已%s", success ? "" : "未完全成功 · ",
                services.telnet ? "开启" : "关闭", services.ftp ? "开启" : "关闭");
            dirty = 1;
        }
    } else if (busy_kind == 6) {
        /* 解析 "UserData is PW_CUSTOM1 (0x140009)" → 缓存 hex，供 preview 免读 */
        char *p = strstr(output, "(0x");
        if (p) {
            char *q = p + 1, *e = strchr(q, ')');
            if (e && e - q < (int)sizeof enum_cache) {
                memcpy(enum_cache, q, (size_t)(e - q));
                enum_cache[e - q] = 0;
                enum_cache_ms = now_ms();
                dirty = 1;
            }
        }
    } else {
        if (close_after_child) {
            close_after_child = 0;
            if (success) { quit = 1; queue.close_requested = 1; }
        }
        message(success ? "命令已完成" : "命令失败 · 详情见日志");
    }
    dirty = 1;
}
static int copy_file(const char *from, const char *to) {
    FILE *in = fopen(from, "rb"), *out; char buf[4096]; size_t n; int ok = 1;
    if (!in) return 0;
    out = fopen(to, "wb");
    if (!out) { fclose(in); return 0; }
    while ((n = fread(buf, 1, sizeof buf, in)) > 0)
        if (fwrite(buf, 1, n, out) != n) { ok = 0; break; }
    if (ferror(in)) ok = 0;
    fclose(in); if (fclose(out) != 0) ok = 0;
    if (ok && chmod(to, 0755) != 0) ok = 0;
    if (!ok) unlink(to);
    return ok;
}
static void activate_item(int index) {
    struct nx_item *it = &items[index];
    char source[NXUI_PATH], target[NXUI_PATH], command[1024];
    const char *name = base_name(it->command); size_t i;
    fprintf(stderr, "ACTION item=%d checkbox=%d\n", index, it->checkbox);
    if (child) { message("请等待当前操作完成"); return; }
    if (strstr(it->command, "gui_exit.sh")) { queue.close_requested = 1; return; }
    if (it->command[0] == '@') {
        if (strstr(it->command, "gui_filmlab1b")) { menu = 0; resize_panel(); return; }
        if (live && (!strncmp(it->command, "@/tmp/gui_br.", 13) ||
                     !strncmp(it->command, "@/tmp/gui_ramp.", 15))) {
            /* The legacy generator runs six global syncs. These volatile menu
             * files need no disk flush, and need not delay every UI opening. */
            snprintf(pending_menu, sizeof pending_menu, "%s", it->command);
            if (!start_child(3, -1, "sed '/^sync;/d' ./br_menu.sh | /bin/bash"))
                message("无法生成子菜单");
            return;
        }
        load_menu(it->command); return;
    }
    if (!strcmp(it->command, " ") || !*it->command) return;
    /* A menu operation supersedes any browsing request not yet dispatched. */
    queue.desired = queue.applied = -1;
    if (!it->checkbox && !strcmp(name, "telnet_toggle.sh")) {
        if (!live) { message("演示模式 · 未更改服务"); return; }
        refresh_services(1);
        if (!services.known) { message("无法读取服务状态 · 请重试"); return; }
        snprintf(command, sizeof command, "./telnet_toggle.sh --ui %s", services.telnet && services.ftp ? "disable" : "enable");
        if (start_child(4, -1, command)) message(services.telnet && services.ftp ? "正在关闭 Telnet/FTP…" : "正在开启 Telnet/FTP…");
        else message("服务操作启动失败");
        return;
    }
    if (!it->checkbox) { start_child(2, -1, it->command); return; }
    /* Legacy checkbox semantics: auto/<script> is a copy, off_<script> stops it. */
    for (i = 0; name[i]; i++)
        if (!((name[i] >= 'a' && name[i] <= 'z') || (name[i] >= 'A' && name[i] <= 'Z') ||
            (name[i] >= '0' && name[i] <= '9') || name[i] == '_' || name[i] == '-' || name[i] == '.')) return;
    if (!i || strstr(name, "..") || !strcmp(name, "a_init.sh")) return;
    if (!live) { message("演示模式 · 未更改开关"); return; }
    snprintf(target, sizeof target, "%s/auto/%s", root, name);
    if (checked(name)) {
        if (unlink(target) != 0) { message("无法关闭开关"); return; }
        snprintf(source, sizeof source, "%s/off_%s", root, name);
        snprintf(command, sizeof command, "./off_%s", name);
        if (access(source, R_OK) == 0) start_child(2, -1, command);
        else message("已关闭自动执行");
    } else {
        snprintf(source, sizeof source, "%s/%s", root, name);
        snprintf(command, sizeof command, "./auto/%s", name);
        if (!copy_file(source, target)) { fprintf(stderr, "COPY failed errno=%d\n", errno); message("无法启用开关"); return; }
        start_child(2, -1, command);
    }
    dirty = 1;
}
static void draw(void) {
    char line[320]; int i, start;
    struct nk_color accent = nk_rgb(203, 233, 153);
    if (nk_begin(ctx, "NXWA", nk_rect(0, 0, (float)width, (float)height), NK_WINDOW_NO_SCROLLBAR)) {
        nk_layout_row_begin(ctx, NK_STATIC, 24, 3);
        nk_layout_row_push(ctx, 460);
        nk_label_colored(ctx, menu ? "NX-KS  /  菜单"
                            : (lut_mode ? "LUT  /  3D 滤镜" : "FILMLAB  /  滤镜预览"),
                         NK_TEXT_LEFT, accent);
        nk_layout_row_push(ctx, 104);
        if (nk_button_label(ctx, menu ? "滤镜" : "菜单")) {
            if (menu) { menu = 0; resize_panel(); }
            else { char p[64]; snprintf(p, sizeof p, "gui_ini.NX500"); load_menu(p); }
        }
        nk_layout_row_push(ctx, 104);
        if (nk_button_label(ctx, "关闭")) queue.close_requested = 1;
        nk_layout_row_end(ctx);
        if (menu) {
            start = page * 6;
            nk_layout_row_dynamic(ctx, 55, 2);
            for (i = start; i < start + 6; i++) {
                if (i >= item_count) { nk_spacing(ctx, 1); continue; }
                if (!strcmp(base_name(items[i].command), "telnet_toggle.sh"))
                    nx_services_label(&services, line, sizeof line);
                else snprintf(line, sizeof line, "%s%s", items[i].checkbox ? (checked(items[i].command) ? "[开] " : "[关] ") : "", items[i].label);
                if (nk_button_label(ctx, line)) { activate_item(i); break; }
            }
            nk_layout_row_dynamic(ctx, 32, 3);
            if (nk_button_label(ctx, "上一页")) { page = page > 0 ? page - 1 : (item_count-1)/6; dirty = 1; }
            snprintf(line, sizeof line, "%d / %d", page + 1, (item_count+5)/6);
            nk_label(ctx, line, NK_TEXT_CENTERED);
            if (nk_button_label(ctx, "下一页")) { page = (page+1) % ((item_count+5)/6); dirty = 1; }
        } else if (count > 0) {
            int gi, win = 5, first, idx;
            nk_layout_row_dynamic(ctx, 84, win);
            first = selected - win / 2;
            if (first < 0) first = 0;
            if (first > count - win) first = count - win;
            if (first < 0) first = 0;
            for (gi = 0; gi < win; gi++) {
                idx = first + gi;
                if (idx >= count) { nk_spacing(ctx, 1); continue; }
                nk_bool picked = (idx == selected);
                snprintf(line, sizeof line, "%s%s", idx == selected ? "● " : "", recipes[idx].label);
                /* A tap always applies, including on the highlighted row: the
                 * camera or the legacy menu may have changed ISP state since
                 * the preview, so the marker is not proof the value is live.
                 * Nuklear reports a press once and flips *picked, so the old
                 * "&& idx != selected" guard made the highlighted row inert. */
                if (nk_selectable_label(ctx, line, NK_TEXT_CENTERED, &picked))
                    choose(idx);
            }
            snprintf(line, sizeof line, "%d/%d   R%d G%d B%d   H%d S%d 锐%d 对比%d", selected+1, count,
                recipes[selected].value[0], recipes[selected].value[1], recipes[selected].value[2],
                recipes[selected].value[3], recipes[selected].value[4], recipes[selected].value[5], recipes[selected].value[6]);
            nk_layout_row_dynamic(ctx, 16, 1);
            nk_label_colored(ctx, line, NK_TEXT_LEFT, nk_rgb(171, 182, 190));
            nk_layout_row_dynamic(ctx, 26, 3);
            if (nk_button_label(ctx, "‹ 上一个")) choose(selected-1);
            if (nk_button_label(ctx, "保存并关闭") && !queue.close_requested) {
                if (!child && selected == queue.applied) {
                    /* 当前选中已预览生效：仅保存到闪存，免一次完整 apply */
                    close_after_child = 1;
                    if (!start_child(2, -1, "prefman save 0")) { close_after_child = 0; message("保存启动失败"); }
                } else {
                    nx_queue_select(&queue, selected, now_ms()-NXUI_DEBOUNCE_MS);
                    queue.commit_requested = 1;
                    queue.close_requested = 1;
                }
            }
            if (nk_button_label(ctx, "下一个 ›")) choose(selected+1);
        } else {
            /* Say where to look. The generic message cost an hour of guessing
             * once: three uppercase look names had silently voided the list. */
            nk_layout_row_dynamic(ctx, 60, 1);
            nk_label(ctx, lut_mode ? "滤镜库为空 · 见 /tmp/nxui.log 与 /mnt/mmc/looks"
                                   : "配方表不可用 · 见 /tmp/nxui.log",
                     NK_TEXT_LEFT);
        }
        nk_layout_row_dynamic(ctx, 23, 1);
        nk_label_colored(ctx, live ? status : "演示模式 · 未连接相机", NK_TEXT_LEFT, nk_rgb(171, 182, 190));
    }
    nk_end(ctx);
    nk_xlib_render(window, nk_rgb(24, 29, 33));
    XFlush(display);
}
static void snapshot(const char *path) {
    XImage *img; FILE *f; int x, y;
    XSync(display, False);
    img = XGetImage(display, window, 0, 0, (unsigned)width, (unsigned)height, AllPlanes, ZPixmap);
    if (!img || !(f = fopen(path, "wb"))) { if (img) XDestroyImage(img); return; }
    fprintf(f, "P6\n%d %d\n255\n", width, height);
    for (y = 0; y < height; y++) for (x = 0; x < width; x++) {
        unsigned long p = XGetPixel(img, x, y);
        unsigned long masks[3] = {img->red_mask, img->green_mask, img->blue_mask}; int c;
        for (c = 0; c < 3; c++) {
            unsigned long m = masks[c], v = p & m;
            if (!m) { fputc(0, f); continue; }
            while (!(m & 1)) { m >>= 1; v >>= 1; }
            fputc((int)(v * 255 / m), f);
        }
    }
    fclose(f); XDestroyImage(img);
}
int main(int argc, char **argv) {
    const char *recipe_path = "/mnt/mmc/filmlab/recipes.txt", *initial_menu = NULL, *shot = NULL;
    const char *font_name = "SDIC_GP_US:pixelsize=19";
    XSetWindowAttributes attr; XFont *font; Atom wm_delete; int i, lockfd, render_count = 0;
    long long started, next_frame = 0, max_draw_ms = 0, process_started = now_ms();
    long long recipes_ready, display_ready, font_ready, backend_ready;
    int wakeups = 0, blits = 0;
    for (i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--live")) live = 1;
        else if (!strcmp(argv[i], "--dry-run")) live = 0;
        else if (!strcmp(argv[i], "--lut")) lut_mode = 1;
        else if (i+1 < argc && !strcmp(argv[i], "--root")) root = argv[++i];
        else if (i+1 < argc && !strcmp(argv[i], "--engine")) engine = argv[++i];
        else if (i+1 < argc && !strcmp(argv[i], "--recipes")) recipe_path = argv[++i];
        else if (i+1 < argc && !strcmp(argv[i], "--menu")) initial_menu = argv[++i];
        else if (i+1 < argc && !strcmp(argv[i], "--font")) font_name = argv[++i];
        else if (i+1 < argc && !strcmp(argv[i], "--snapshot")) shot = argv[++i];
        else if (i+1 < argc && !strcmp(argv[i], "--lifetime-ms")) lifetime = atol(argv[++i]);
        else { fprintf(stderr, "Usage: nxui [--live|--dry-run] [--root dir] [--recipes file] [--menu gui_file] [--engine file] [--snapshot ppm] [--lifetime-ms n]\n"); return 2; }
    }
    if (getenv("NXUI_NET_DIR")) net_dir = getenv("NXUI_NET_DIR"); /* isolated service-state tests */
    /* A screenshot is always read-only, regardless of option order. */
    if (shot) live = 0;
    lockfd = open("/tmp/nxwa-nxui.lock", O_CREAT|O_RDWR, 0600);
    if (lockfd < 0 || flock(lockfd, LOCK_EX|LOCK_NB) != 0) return 3;
    fcntl(lockfd, F_SETFD, FD_CLOEXEC);
    signal(SIGINT, on_signal); signal(SIGTERM, on_signal);
    { struct sigaction action; memset(&action, 0, sizeof action); action.sa_handler = on_child;
      sigemptyset(&action.sa_mask); action.sa_flags = SA_NOCLDSTOP; sigaction(SIGCHLD, &action, NULL); }
    /* Launchers may inherit nice -15 from the camera key handler. nice +15 in
     * a shell is relative; set an absolute background priority for UI and jobs. */
    if (setpriority(PRIO_PROCESS, 0, 19) != 0)
        fprintf(stderr, "setpriority failed errno=%d\n", errno);
    nx_queue_init(&queue);
    count = nx_load_recipes(recipe_path, recipes, NXUI_MAX_RECIPES);
    if (count < 0) count = 0;
    recipes_ready = now_ms();
    display = XOpenDisplay(NULL);
    if (!display) { fprintf(stderr, "XOpenDisplay failed\n"); return 4; }
    display_ready = now_ms();
    screen = DefaultScreen(display); width = 720; height = 192;
    if (DisplayWidth(display, screen) < width || DisplayHeight(display, screen) < height) {
        fprintf(stderr, "Display must be at least 720x192\n"); XCloseDisplay(display); return 4;
    }
    memset(&attr, 0, sizeof attr);
    attr.override_redirect = True; attr.background_pixel = BlackPixel(display, screen);
    /* This panel has buttons, no draggable controls. Touch coordinates arrive
     * on press/release; subscribing to motion needlessly repaints while sliding. */
    attr.event_mask = ExposureMask|KeyPressMask|ButtonPressMask|ButtonReleaseMask|StructureNotifyMask;
    window = XCreateWindow(display, RootWindow(display, screen), 0, DisplayHeight(display, screen)-height,
        (unsigned)width, (unsigned)height, 0, DefaultDepth(display, screen), InputOutput,
        DefaultVisual(display, screen), CWOverrideRedirect|CWBackPixel|CWEventMask, &attr);
    XStoreName(display, window, "NXWA-Nuklear");
    wm_delete = XInternAtom(display, "WM_DELETE_WINDOW", False);
    XSetWMProtocols(display, window, &wm_delete, 1);
    font = nk_xfont_create(display, font_name);
    if (!font || !font->ft) { fprintf(stderr, "font unavailable\n"); return 5; }
    font_ready = now_ms();
    ctx = nk_xlib_init(font, display, screen, window, DefaultVisual(display, screen),
        DefaultColormap(display, screen), (unsigned)width, (unsigned)height);
    if (!ctx) { fprintf(stderr, "Nuklear initialization failed\n"); return 5; }
    backend_ready = now_ms();
    /* XCopyArea otherwise emits NoExpose after every blit. Treating that as a
     * reason to redraw creates a self-sustaining busy loop on the camera. */
    XSetGraphicsExposures(display, xlib.surf->gc, False);
    ctx->style.window.padding = nk_vec2(12, 8); ctx->style.window.spacing = nk_vec2(8, 5);
    ctx->style.window.background = nk_rgb(24, 29, 33);
    ctx->style.window.fixed_background = nk_style_item_color(nk_rgb(24, 29, 33));
    ctx->style.button.normal = nk_style_item_color(nk_rgb(45, 53, 59));
    ctx->style.button.hover = ctx->style.button.normal;
    ctx->style.button.active = nk_style_item_color(nk_rgb(88, 111, 79));
    ctx->style.button.text_normal = nk_rgb(234, 239, 231);
    ctx->style.button.rounding = 4;
    if (initial_menu && !load_menu(initial_menu)) return 6;
    save_focus();   /* remember the camera window that owns the keyboard now */
    XMapRaised(display, window); XSync(display, False);
    XSetInputFocus(display, window, RevertToPointerRoot, CurrentTime);
    started = now_ms();
    fprintf(stderr, "READY backend=nuklear-xft live=%d recipes=%d panel=%dx%d nice=%d\n",
        live, count, width, height, getpriority(PRIO_PROCESS, 0));
    fprintf(stderr, "INIT recipes_ms=%lld display_ms=%lld font_ms=%lld backend_ms=%lld map_ms=%lld\n",
        recipes_ready-process_started, display_ready-recipes_ready, font_ready-display_ready,
        backend_ready-font_ready, started-backend_ready);
    if (live) { ev_fd = open("/dev/input/event0", O_RDONLY | O_NONBLOCK); }
    if (live) start_child(6, -1, "st cap capdtm getusr 20");
    while (!quit) {
        XEvent event; fd_set fds; struct timeval wait; int index, pending, events = 0, refresh = 0, painted = 0;
        long long tick = now_ms(), delay = 60000;
        if (interrupted || (lifetime > 0 && now_ms()-started >= lifetime)) queue.close_requested = 1;
        /* 半按快门 S1：/dev/input/event0 code 125 (KEY_LEFTMETA) press ⇒ 关闭 */
        if (ev_fd >= 0) {
            struct input_event iev;
            while (read(ev_fd, &iev, sizeof iev) == (ssize_t)sizeof iev) {
                if (iev.type == EV_KEY && iev.code == 125 && iev.value == 1) {
                    /* A half-press is the operator's "close and apply" gesture:
                     * it makes P7 reload the table, so keep the table. */
                    if (lut_mode) lut_keep = 1;
                    queue.close_requested = 1;
                }
            }
        }
        /* EV_S1.sh 通道（备用）：每 100ms 检查并消费标记 */
        if (tick - close_flag_check >= 100) {
            close_flag_check = tick;
            if (access("/tmp/nxui-close", F_OK) == 0) {
                unlink("/tmp/nxui-close");
                queue.close_requested = 1;
            }
        }
        /* Leave unconsumed input in Xlib until its frame. Resetting Nuklear's
         * input while deferring draw would discard fast taps. Bound each batch
         * and render to 10 Hz, including an expose/key-repeat event storm. */
        if (tick >= next_frame) {
          nk_input_begin(ctx);
          while (events < 64 && XPending(display)) {
            XNextEvent(display, &event);
            events++;
            if (event.type == MotionNotify || event.type == NoExpose) continue;
            if (event.type == Expose) { refresh = 1; continue; }
            if (event.type == ConfigureNotify) {
                /* The event already contains the size. Avoid the upstream
                 * synchronous XGetWindowAttributes on every expose/resize. */
                if (width != event.xconfigure.width || height != event.xconfigure.height) {
                    width = event.xconfigure.width; height = event.xconfigure.height;
                    nk_xsurf_resize(xlib.surf, (unsigned)width, (unsigned)height);
                    dirty = 1;
                }
                continue;
            }
            if (event.type == KeyPress || event.type == ButtonPress || event.type == ButtonRelease) dirty = 1;
            if (event.type == ClientMessage && (Atom)event.xclient.data.l[0] == wm_delete) queue.close_requested = 1;
            if (event.type == KeyPress) {
                KeySym key = XLookupKeysym(&event.xkey, 0);
                /* Only standard keysyms are asserted. Camera wheel mappings need measurement. */
                if (key == XK_Escape) queue.close_requested = 1;
                else if (!menu && (key == XK_Right || key == XK_Down)) choose(selected+1);
                else if (!menu && (key == XK_Left || key == XK_Up)) choose(selected-1);
                else if (!menu && (key == XK_Return || key == XK_KP_Enter) && !child && count > 0) {
                    nx_queue_select(&queue, selected, now_ms()-NXUI_DEBOUNCE_MS);
                    queue.commit_requested = 1; queue.close_requested = 1;
                }
            }
            if (event.type == ButtonPress && !menu && (event.xbutton.button == 4 || event.xbutton.button == 5))
                choose(selected + (event.xbutton.button == 4 ? -1 : 1));
            /* Touchscreens can send a tap without a preceding MotionNotify. */
            if (event.type == ButtonPress || event.type == ButtonRelease)
                nk_input_motion(ctx, event.xbutton.x, event.xbutton.y);
            /* 左右滑动手势：超阈值切换选中；release 移出控件避免被当成点击 */
            if (event.type == ButtonPress && !menu) { touch_x = event.xbutton.x; touch_active = 1; }
            if (event.type == ButtonRelease && touch_active) {
                int dx = event.xbutton.x - touch_x;
                int step = (dx >= 0 ? dx : -dx) / 45;   /* 每 45px 切一项：滑得远切得快 */
                touch_active = 0;
                if (step < 1 && (dx >= 30 || dx <= -30)) step = 1;   /* 轻扫阈值 30px */
                if (!menu && step > 0) {
                    choose(selected + (dx < 0 ? step : -step));
                    nk_input_motion(ctx, -10000, -10000);
                    dirty = 1;
                }
            }
            nk_xlib_handle_event(display, screen, window, &event);
            /* Keep press/release transitions in separate frames, even when a
             * complete short tap was queued while the camera was busy. */
            if (event.type == ButtonPress || event.type == ButtonRelease) break;
          }
          nk_input_end(ctx);
        }
        poll_child();
        refresh_services(0);
        /* Unmap as soon as a close is requested: while the backend finishes
         * (up to the 12 s timeout) the panel must not keep covering the frame
         * or hold the keyboard focus away from the camera UI. */
        if (queue.close_requested && !panel_unmapped) {
            restore_focus();
            XUnmapWindow(display, window);
            XSync(display, False);
            panel_unmapped = 1;
        }
        /* Closing waits for an in-flight write; it discards unapplied browsing requests. */
        if (queue.close_requested && !queue.commit_requested && !child) break;
        if (!child && (!queue.close_requested || queue.commit_requested) && (index = nx_queue_take(&queue, now_ms())) >= 0)
            if (!start_child(1, index, NULL)) { nx_queue_done(&queue, 0); message("后端启动失败"); }
        if (tick >= next_frame && !quit) {
            if (dirty) {
                long long draw_started = now_ms(), elapsed;
                dirty = 0; draw(); render_count++; painted = 1;
                if (render_count == 1) {
                    const char *launch = getenv("NXUI_LAUNCH_UPTIME");
                    long long launch_ms = launch ? (long long)(atof(launch)*1000) : process_started;
                    XSync(display, False); /* one initial fence measures visible first frame */
                    fprintf(stderr, "FIRST_FRAME process_ms=%lld launch_ms=%lld\n",
                        now_ms()-process_started, now_ms()-launch_ms);
                }
                elapsed = now_ms() - draw_started;
                if (elapsed > max_draw_ms) max_draw_ms = elapsed;
            } else if (refresh && render_count) {
                /* Retained pixmap: expose needs one copy, no layout/font work. */
                XSetClipMask(display, xlib.surf->gc, None);
                nk_xsurf_blit(window, xlib.surf, (unsigned)width, (unsigned)height);
                XFlush(display); blits++;
            }
            if (events || painted || refresh) next_frame = now_ms() + 100;
        }
        if (shot && render_count) { snapshot(shot); break; }
        tick = now_ms(); pending = XPending(display);
        if (child) delay = 100; /* only a running backend needs periodic reaping */
        if (services_visible() && service_due - tick < delay) delay = service_due - tick;
        if (!child && queue.desired >= 0 && (queue.desired != queue.applied || queue.commit_requested))
            if (queue.due - tick < delay) delay = queue.due - tick;
        if (lifetime > 0 && !queue.close_requested && started + lifetime - tick < delay)
            delay = started + lifetime - tick;
        if ((dirty || pending) && next_frame - tick < delay) delay = next_frame - tick;
        if (delay < 0) delay = 0;
        FD_ZERO(&fds);
        /* Pending events are already in the client queue. Watching a readable
         * server fd before the frame deadline would spin under an input burst. */
        if (!pending) FD_SET(ConnectionNumber(display), &fds);
        if (child_fd >= 0 && !pipe_eof) FD_SET(child_fd, &fds);
        wait.tv_sec = (long)(delay/1000); wait.tv_usec = (long)(delay%1000)*1000;
        select((child_fd > ConnectionNumber(display) ? child_fd : ConnectionNumber(display))+1, &fds, NULL, NULL, &wait);
        wakeups++;
    }
    fprintf(stderr, "EXIT renders=%d elapsed_ms=%lld wakeups=%d blits=%d max_draw_ms=%lld\n",
        render_count, now_ms()-started, wakeups, blits, max_draw_ms);
    restore_focus();   /* also covers --snapshot / lifetime / signal exits */
    nk_xlib_shutdown(); nk_xfont_del(display, font);
    /* Leaving the LUT panel restores the registry entries and the slot, so the
     * camera is never left with a rewritten table behind the operator's back.
     * A half-press only hides the panel, it does not come through here.
     * A dry run or a snapshot never wrote anything, so it must not restore
     * either -- restoring would be a real write. */
    if (lut_mode && live) {
        if (lut_keep) {
            /* Closed by a half-press: the operator wants the look to stay.
             * Mark the session so the next entry reuses the existing backup
             * instead of restoring and re-snapshotting an already-changed slot. */
            int kfd = open("/mnt/mmc/lut/state/keep", O_CREAT | O_WRONLY, 0644);
            if (kfd >= 0) close(kfd);
        } else {
            pid_t restore_pid = fork();
            if (restore_pid == 0) {
                close(ConnectionNumber(display));
                execl("/bin/sh", "sh", engine, "off", (char *)0);
                _exit(127);
            }
            if (restore_pid > 0) waitpid(restore_pid, NULL, 0);
        }
    }
    XDestroyWindow(display, window); XCloseDisplay(display); close(lockfd);
    return 0;
}
