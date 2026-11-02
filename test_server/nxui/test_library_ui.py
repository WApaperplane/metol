"""库管理 / 双强度混合：真窗口 + 真 X 事件，引擎用 shell 桩。

交互（2026-11-02 定稿）：
  · 浏览态长按 = 进编辑态（删除 / 排序）。11-02 中途试过改成「标记 A/B」，
    实机一按整排就跳（列表是选中项居中的 5 项窗口），已回退。
  · 左右滑动切项也一并删了，翻页只走滚条 / 上下键 / 拨盘。
  · A/B 在混合态里用「设为A / 设为B」按钮设；强度靠滑杆（调当前焦点）与
    右上拨盘；「应用混合」才真正下发。

被验的是面板与引擎之间的协议，不是观感：
  1. 长按进编辑态、两段式删除、左移，仍走 del / move
  2. 混合态把两个强度换算成 `blend A r B s`
  3. 顶栏按钮与 F2 两条入口等价

表本身怎么混合由 test_lutmix.py / test_dual_strength.py 在 qemu 下验；
库怎么增删由 test_lut_lib.sh 验；这里只验面板这一侧。
"""
from pathlib import Path
import subprocess
import tempfile
import time

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"

ENGINE = '''#!/bin/sh
printf "%s\\n" "$*" >> "$NXUI_CALLS"
case "$1" in
  list) cat "$NXUI_NAMES" ;;
  del)  grep -vx "$2" "$NXUI_NAMES" > "$NXUI_NAMES.t"; mv "$NXUI_NAMES.t" "$NXUI_NAMES" ;;
esac
exit 0
'''

# LUT 面板的固定行位（720x208）：
#   y=20 顶栏（padding 8 + 行高 24/2）· y=60 滤镜条 · y=110 滚动条/强度滑杆
#   y=133 按钮行
STRIP_Y, BAR_Y, BTN_Y, TOP_Y = 60, 110, 133, 20
COL1, COL2, COL3, COL4 = 96, 272, 448, 624
TOP_MIX_X = 540


def run_library_ui(prefix, env, label):
    with tempfile.TemporaryDirectory(prefix="nxui-lib-") as temp:
        root = Path(temp)
        (root / "auto").mkdir()
        calls = root / "calls"
        names = root / "names"
        looks = ["portra400", "velvia50", "acros100", "ektar100", "pro400h"]
        names.write_text("\n".join(looks) + "\n")
        rec = root / "looks.rec"
        rec.write_text("".join("%s|%s|0|0|0|0|0|0|0\n" % (n, n) for n in looks))
        engine = root / "engine.sh"
        engine.write_text(ENGINE)
        engine.chmod(0o755)
        env = dict(env, NXUI_CALLS=str(calls), NXUI_NAMES=str(names))

        log = root / "run.log"
        stream = log.open("w")
        p = subprocess.Popen(
            prefix + ["--live", "--lut", "--root", str(root), "--engine", str(engine),
                      "--recipes", str(rec), "--lifetime-ms", "14000"],
            env=env, stdout=stream, stderr=subprocess.STDOUT)
        try:
            for _ in range(60):
                if "READY" in log.read_text():
                    break
                if p.poll() is not None:
                    raise AssertionError(log.read_text())
                time.sleep(.05)

            def send(*args):
                subprocess.run([str(OUT / "test_input")] + list(args),
                               env=env, check=True, timeout=5)

            def wait_for(needle, limit=4.0):
                """等面板日志出现某串（BACKEND / REFRESH 这类是面板自己打的）。"""
                deadline = time.time() + limit
                while time.time() < deadline:
                    text = log.read_text()
                    if needle in text:
                        return text
                    time.sleep(.05)
                raise AssertionError("%r not in log\n%s" % (needle, log.read_text()[-1500:]))

            def wait_calls(word, n, limit=6.0):
                """等到某类引擎调用累计到 n 条。"""
                deadline = time.time() + limit
                while time.time() < deadline:
                    text = calls.read_text() if calls.exists() else ""
                    got = [l for l in text.splitlines() if l.startswith(word)]
                    if len(got) >= n:
                        return got
                    time.sleep(.05)
                text = calls.read_text() if calls.exists() else ""
                raise AssertionError("%r 只到 %d 条（期望 %d）\ncalls=%r\n--- panel ---\n%s"
                                     % (word, len([l for l in text.splitlines()
                                                   if l.startswith(word)]), n,
                                        text, log.read_text()[-1200:]))

            # 机身 11-02 实测 Left=KP_Left：真 X 事件必须回到前一项。
            send("key", "Right")
            wait_calls("apply velvia50", 1)
            send("key", "KP_Left")
            wait_calls("apply portra400", 1)

            # ── 1. 长按进编辑态；两段式删除 ──
            send("click", str(COL2), str(STRIP_Y), "700")
            time.sleep(.5)

            before = calls.read_text() if calls.exists() else ""
            send("click", str(COL1), str(BTN_Y), "30")     # 第一次只提示
            time.sleep(.4)
            after_one = calls.read_text() if calls.exists() else ""
            assert after_one == before, "第一次点删除就调用了引擎：%r" % after_one

            send("click", str(COL1), str(BTN_Y), "30")     # 第二次才真删
            dels = wait_calls("del ", 1)
            assert len(dels) == 1, "应有且只有一次 del：%r" % dels
            gone = dels[0].split()[1]
            assert gone in looks, "del 的目标不是库里的 key：%r" % gone

            wait_for("REFRESH lut: entries=4", limit=6.0)
            left = names.read_text().split()
            assert gone not in left and len(left) == 4, left

            send("click", str(COL2), str(BTN_Y), "30")     # 左移
            moves = wait_calls("move ", 1)
            assert moves[-1].split()[2] == "up", moves

            send("click", str(COL4), str(BTN_Y), "30")     # 完成
            time.sleep(.4)

            # ── 2. 混合态：设为A / 设为B / 滑杆调焦点 / 应用 ──
            send("key", "F2")
            time.sleep(.4)
            send("click", str(COL1), str(BTN_Y), "30")     # 设为A
            time.sleep(.3)
            send("key", "Down")                            # 换一项（混合态左右键是切 A/B 焦点）
            time.sleep(.3)
            send("click", str(COL2), str(BTN_Y), "30")     # 设为B
            time.sleep(.3)
            send("drag", "160", str(BAR_Y), "450", str(BAR_Y), "10")  # 调当前焦点（B）
            time.sleep(.4)
            send("click", str(COL3), str(BTN_Y), "30")     # 应用混合
            blends = wait_calls("blend ", 1)
            parts = blends[-1].split()
            assert len(parts) == 5, "blend 参数个数不对：%r" % parts
            a, r, b, s = parts[1], parts[2], parts[3], parts[4]
            assert a in looks and b in looks, parts
            assert a != b, "A 与 B 不能是同一张：%r" % parts
            assert r.isdigit() and 0 <= int(r) <= 100, "比例越界：%s" % r
            assert s.isdigit() and 0 <= int(s) <= 100, "强度越界：%s" % s

            send("click", str(COL4), str(BTN_Y), "30")     # 退出混合
            time.sleep(.4)

            # ── 3. 顶栏入口等价：进一次、应用一次 ──
            send("click", str(TOP_MIX_X), str(TOP_Y), "30")
            time.sleep(.5)
            send("click", str(COL3), str(BTN_Y), "30")     # 应用混合
            blends = wait_calls("blend ", 2)
            assert blends[-1].split()[1] in looks, blends

            p.wait(timeout=14)
            return log.read_text()
        finally:
            if p.poll() is None:
                p.kill()
                p.wait()
            stream.close()
