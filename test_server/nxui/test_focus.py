"""Focus handoff regression (host, isolated X server).

The camera runs without a window manager: whatever window calls
XSetInputFocus keeps the keyboard, and camera menu navigation (jog wheel /
arrow keys) arrives as X KeyPress delivered only to that window. If the panel
forgets to hand the focus back, the native menu looks like its keys stopped
working -- the bug this test pins down.

Checks:
  1. a fake camera window owns the focus before the panel starts;
  2. the panel takes the focus while it is open;
  3. the focus is back on the camera window after the panel exits.
"""
from pathlib import Path
import ctypes
import json
import os
import subprocess
import time

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
OUT = HERE / "out"
RF = Path(os.environ.get("NXUI_ROOTFS", "/opt/nxks2/rootfs-112"))
DISPLAY = ":98"
PANEL = "NXWA-Nuklear"
BIN = Path(os.environ.get("NXUI_TEST_BIN", str(OUT / "nxui")))

env = os.environ.copy()
env.update(DISPLAY=DISPLAY, LC_ALL="C", LD_LIBRARY_PATH=str(OUT / "deps/usr/lib/x86_64-linux-gnu"))

lib = ctypes.CDLL("libX11.so.6")
lib.XOpenDisplay.restype = ctypes.c_void_p
lib.XOpenDisplay.argtypes = [ctypes.c_char_p]
lib.XDefaultRootWindow.restype = ctypes.c_ulong
lib.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
lib.XCreateSimpleWindow.restype = ctypes.c_ulong
lib.XCreateSimpleWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_uint, ctypes.c_uint, ctypes.c_uint,
                                    ctypes.c_ulong, ctypes.c_ulong]
lib.XMapWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
lib.XStoreName.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_char_p]
lib.XSetInputFocus.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
lib.XGetInputFocus.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_int)]
lib.XFetchName.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_char_p)]
lib.XFetchName.restype = ctypes.c_int
lib.XFree.argtypes = [ctypes.c_void_p]
lib.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
lib.XFlush.argtypes = [ctypes.c_void_p]

# Xlib's default handler exits the process; a stale focus window is an expected
# negative-control outcome here, so errors must be ignored instead.
ERROR_HANDLER = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)
_error_handler = ERROR_HANDLER(lambda dpy, ev: 0)
lib.XSetErrorHandler.argtypes = [ERROR_HANDLER]
lib.XSetErrorHandler(_error_handler)


def focus(dpy):
    win = ctypes.c_ulong()
    revert = ctypes.c_int()
    lib.XGetInputFocus(dpy, ctypes.byref(win), ctypes.byref(revert))
    lib.XSync(dpy, False)
    title = None
    if win.value not in (0, 1):  # None / PointerRoot have no WM_NAME
        name = ctypes.c_char_p()
        if lib.XFetchName(dpy, win.value, ctypes.byref(name)):
            if name.value:
                title = name.value.decode(errors="replace")
            lib.XFree(name)
    return win.value, title


def wait_focus(dpy, want, timeout=6.0):
    deadline = time.time() + timeout
    seen, title = focus(dpy)
    while time.time() < deadline:
        seen, title = focus(dpy)
        if (want == "panel" and title == PANEL) or (want == "camera" and title != PANEL):
            return seen, title
        time.sleep(0.05)
    raise AssertionError(f"focus never became {want}; last={title!r} win=0x{seen:x}")


def clean_display(num):
    """Remove a stale X lock left by an aborted run; never touch a live server."""
    lock = Path(f"/tmp/.X{num}-lock")
    if not lock.exists():
        return
    pid = lock.read_text().strip()
    if pid.isdigit() and Path(f"/proc/{pid}").exists():
        raise RuntimeError(f"display :{num} is in use by pid {pid}")
    lock.unlink(missing_ok=True)
    Path(f"/tmp/.X11-unix/X{num}").unlink(missing_ok=True)


def main():
    clean_display(98)
    serverenv = env.copy()
    serverenv.update(LD_PRELOAD=str(OUT / "xvfb_local_paths.so"), NXUI_XKB_BINDIR=str(OUT / "deps/usr/bin"))
    serverlog = (OUT / "xvfb-focus.log").open("w")
    server = subprocess.Popen(
        [str(OUT / "deps/usr/bin/Xvfb"), DISPLAY, "-screen", "0", "720x480x24",
         "-nolisten", "tcp", "-ac", "-fp", str(OUT / "deps/usr/share/fonts/X11/misc")],
        env=serverenv, stdout=serverlog, stderr=subprocess.STDOUT)
    panel = None
    try:
        time.sleep(0.5)
        if server.poll() is not None:
            raise RuntimeError((OUT / "xvfb-focus.log").read_text())
        dpy = lib.XOpenDisplay(DISPLAY.encode())
        assert dpy, "cannot open display"
        root = lib.XDefaultRootWindow(dpy)
        cam = lib.XCreateSimpleWindow(dpy, root, 0, 0, 720, 480, 0, 0, 0)
        lib.XStoreName(dpy, cam, b"CAMERA-NATIVE")
        lib.XMapWindow(dpy, cam)
        lib.XSetInputFocus(dpy, cam, 1, 0)  # RevertToPointerRoot
        lib.XSync(dpy, False)
        assert focus(dpy)[1] == "CAMERA-NATIVE", "camera window did not get focus"

        recipes = OUT / "recipes.txt"
        args = [str(BIN), "--root", str(REPO / "scripts"),
                "--recipes", str(recipes), "--font", "DejaVu Sans:pixelsize=19",
                "--lifetime-ms", "1800"]
        panel = subprocess.Popen(args, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        taken_win, taken_title = wait_focus(dpy, "panel")
        assert taken_title == PANEL, taken_title
        output = panel.communicate(timeout=20)[0].decode(errors="replace")
        assert panel.returncode == 0, output
        assert "EXIT renders=" in output, output
        back_win, back_title = wait_focus(dpy, "camera")
        record = {
            "camera_window": f"0x{cam:x}",
            "focus_while_open": taken_title,
            "focus_after_exit": back_title,
            "restored_exact_window": back_win == cam,
            "result": "PASS" if back_win == cam else "FAIL",
        }
        assert back_win == cam, f"focus not restored: 0x{back_win:x} != 0x{cam:x} ({back_title})"
        print(json.dumps(record, ensure_ascii=False))
        (OUT / "focus-result.json").write_text(json.dumps(record, ensure_ascii=False, indent=2))
        return 0
    finally:
        if panel is not None and panel.poll() is None:
            panel.kill()
        server.terminate()
        server.wait(timeout=10)


if __name__ == "__main__":
    raise SystemExit(main())
