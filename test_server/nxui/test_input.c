/* Synthetic input driver restricted to the focused NXWA window. */
#define _POSIX_C_SOURCE 200809L
#include <X11/Xlib.h>
#include <X11/keysym.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
static void pause_ms(long ms) { struct timespec t = {ms/1000, (ms%1000)*1000000}; nanosleep(&t, NULL); }
int main(int argc, char **argv) {
    Display *d = XOpenDisplay(NULL); Window w; int revert, i, count; XEvent e; char *name = NULL;
    if (!d || argc < 3) return 2;
    XGetInputFocus(d, &w, &revert);
    XFetchName(d, w, &name);
    if (!name || strcmp(name, "NXWA-Nuklear")) { fprintf(stderr, "UI not focused\n"); return 3; }
    XFree(name); memset(&e, 0, sizeof e);
    if (!strcmp(argv[1], "key")) {
        count = argc > 3 ? atoi(argv[3]) : 1;
        e.xkey.display = d; e.xkey.window = w; e.xkey.root = DefaultRootWindow(d);
        e.xkey.same_screen = True; e.xkey.keycode = XKeysymToKeycode(d, XStringToKeysym(argv[2]));
        for (i = 0; i < count; i++) {
            e.type = KeyPress; XSendEvent(d, w, False, KeyPressMask, &e); XFlush(d);
            pause_ms(argc > 4 ? atol(argv[4]) : 30);
        }
    } else if (!strcmp(argv[1], "click") && argc > 3) {
        e.xbutton.display = d; e.xbutton.window = w; e.xbutton.root = DefaultRootWindow(d);
        e.xbutton.same_screen = True; e.xbutton.button = Button1;
        e.xbutton.x = atoi(argv[2]); e.xbutton.y = atoi(argv[3]);
        e.type = ButtonPress; XSendEvent(d, w, False, ButtonPressMask, &e); XFlush(d);
        pause_ms(argc > 4 ? atol(argv[4]) : 80);
        e.type = ButtonRelease; XSendEvent(d, w, False, ButtonReleaseMask, &e);
    } else if (!strcmp(argv[1], "drag") && argc > 5) {
        /* drag x1 y1 x2 y2 [steps]：按住左键从起点拖到终点，中间补 motion。
         * 滚动条必须靠 motion 才能跟随，只有 press/release 的 click 测不出来。 */
        int x1 = atoi(argv[2]), y1 = atoi(argv[3]), x2 = atoi(argv[4]), y2 = atoi(argv[5]);
        int steps = argc > 6 ? atoi(argv[6]) : 12;
        memset(&e, 0, sizeof e);
        e.xbutton.display = d; e.xbutton.window = w; e.xbutton.root = DefaultRootWindow(d);
        e.xbutton.same_screen = True; e.xbutton.button = Button1;
        e.xbutton.x = x1; e.xbutton.y = y1;
        e.type = ButtonPress; XSendEvent(d, w, False, ButtonPressMask, &e); XFlush(d);
        pause_ms(40);
        for (i = 1; i <= steps; i++) {
            memset(&e, 0, sizeof e);
            e.xmotion.type = MotionNotify; e.xmotion.display = d; e.xmotion.window = w;
            e.xmotion.root = DefaultRootWindow(d); e.xmotion.same_screen = True;
            e.xmotion.x = x1 + (x2 - x1) * i / steps;
            e.xmotion.y = y1 + (y2 - y1) * i / steps;
            e.xmotion.state = Button1Mask;
            XSendEvent(d, w, False, Button1MotionMask, &e); XFlush(d);
            pause_ms(20);
        }
        memset(&e, 0, sizeof e);
        e.xbutton.display = d; e.xbutton.window = w; e.xbutton.root = DefaultRootWindow(d);
        e.xbutton.same_screen = True; e.xbutton.button = Button1;
        e.xbutton.x = x2; e.xbutton.y = y2;
        e.type = ButtonRelease; XSendEvent(d, w, False, ButtonReleaseMask, &e);
    } else if (!strcmp(argv[1], "motion") || !strcmp(argv[1], "expose")) {
        count = atoi(argv[2]);
        for (i = 0; i < count; i++) {
            if (!strcmp(argv[1], "motion")) {
                e.xmotion.type = MotionNotify; e.xmotion.display = d; e.xmotion.window = w;
                e.xmotion.same_screen = True; e.xmotion.x = 20 + (i % 650); e.xmotion.y = 60;
                XSendEvent(d, w, False, NoEventMask, &e);
            } else {
                e.xexpose.type = Expose; e.xexpose.display = d; e.xexpose.window = w;
                e.xexpose.width = 720; e.xexpose.height = 192; e.xexpose.count = 0;
                XSendEvent(d, w, False, ExposureMask, &e);
            }
            XFlush(d); pause_ms(argc > 3 ? atol(argv[3]) : 2);
        }
    } else return 2;
    XSync(d, False); XCloseDisplay(d); return 0;
}
