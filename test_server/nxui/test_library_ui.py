"""库管理 / 混合 / 长按：真窗口 + 真 X 事件，引擎用 shell 桩。

被验的是面板这一侧的三件事：
  1. 长按（550ms 不动）能进编辑态
  2. 编辑态的"删除"是两段式，第一次只提示、第二次才把 del 交给引擎
  3. 混合态把 A/B 与强度组织成 `mix A B pct` 一条命令，滚条就是强度滑杆

表本身怎么混合由 test_lutmix.py 在 qemu 下验，库怎么增删由
test_lut_lib.sh 验；这里只验面板与引擎之间的协议。
"""
from pathlib import Path
import subprocess
import tempfile
import time

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"

ENGINE = '''#!/bin/sh
printf "%s %s %s %s\\n" "$1" "$2" "$3" "$4" >> "$NXUI_CALLS"
case "$1" in
  list) cat "$NXUI_NAMES" ;;
  del)  grep -vx "$2" "$NXUI_NAMES" > "$NXUI_NAMES.t"; mv "$NXUI_NAMES.t" "$NXUI_NAMES" ;;
  move) ;;
  mix)  : ;;
esac
exit 0
'''

# LUT 面板的固定行位（720x208）：
#   y=20 顶栏（padding 8 + 行高 24/2）· y=60 滤镜条 · y=110 滚动条/强度滑杆
#   y=133 按钮行
STRIP_Y, BAR_Y, BTN_Y = 60, 110, 133
COL1, COL2, COL3, COL4 = 96, 272, 448, 624
# 顶栏四格：起点 x=12（padding），356 + 104 + 104 + 104，格间距 8
TOP_Y, TOP_MIX_X = 20, 540


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
                      "--recipes", str(rec), "--lifetime-ms", "12000"],
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
                """等到某类引擎调用累计到 n 条（同一个动词可能要跑两遍）。"""
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

            # ── 1. 长按进编辑态：700ms 按住，远超 550ms 阈值 ──
            send("click", str(COL2), str(STRIP_Y), "700")
            time.sleep(.5)

            # ── 2. 删除两段式：第一次不调用引擎 ──
            before = calls.read_text() if calls.exists() else ""
            send("click", str(COL1), str(BTN_Y), "30")
            time.sleep(.4)
            after_one = calls.read_text() if calls.exists() else ""
            assert after_one == before, "第一次点删除就调用了引擎：%r" % after_one

            send("click", str(COL1), str(BTN_Y), "30")
            dels = wait_calls("del ", 1)
            assert len(dels) == 1, "应有且只有一次 del：%r" % dels
            gone = dels[0].split()[1]
            assert gone in looks, "del 的目标不是库里的 key：%r" % gone

            # ── 3. 删除后自动重跑 list，面板条目数减一 ──
            wait_for("REFRESH lut: entries=4", limit=6.0)
            names_now = names.read_text().split()
            assert gone not in names_now and len(names_now) == 4, names_now

            # ── 4. 编辑态仍在：左移交给引擎 ──
            send("click", str(COL2), str(BTN_Y), "30")
            moves = wait_calls("move ", 1)
            assert moves[-1].split()[2] == "up", moves

            # ── 5. 完成 → 回浏览态；先进一次混合（键盘 F2），再用顶栏按钮进一次 ──
            send("click", str(COL4), str(BTN_Y), "30")
            time.sleep(.3)
            send("key", "F2")
            time.sleep(.3)
            send("click", str(COL1), str(BTN_Y), "30")   # 设为A
            time.sleep(.3)
            send("key", "Right")
            time.sleep(.3)
            send("click", str(COL2), str(BTN_Y), "30")   # 设为B
            time.sleep(.3)
            send("drag", "160", str(BAR_Y), "450", str(BAR_Y), "10")   # 强度 20% -> 60%
            time.sleep(.4)
            send("click", str(COL3), str(BTN_Y), "30")   # 应用混合
            mixes = wait_calls("mix ", 1)
            parts = mixes[-1].split()
            assert len(parts) == 4, parts
            a, b, pct = parts[1], parts[2], parts[3]
            assert a in looks and b in looks, parts
            assert a != b, "A 与 B 不能是同一张：%r" % parts
            assert pct.isdigit() and 30 <= int(pct) <= 90, "滑杆位置没被读进来：%s" % pct

            # ── 6. 尚未测到机身 F2 等价键，
            #        所以混合态的**唯一**入口是顶栏那个按钮。这里两次点击把它
            #        验全：先「退出混合」回浏览态，再「混合」重新进入。
            #        顶栏几何：padding 12/8，行 24 高，四格 356+104+104+104。
            send("click", str(TOP_MIX_X), str(TOP_Y), "30")     # 退出混合
            time.sleep(.4)
            send("click", str(TOP_MIX_X), str(TOP_Y), "30")     # 触摸进混合
            time.sleep(.4)
            send("click", str(COL2), str(BTN_Y), "30")          # 设为A
            time.sleep(.3)
            send("key", "Right")
            time.sleep(.3)
            send("click", str(COL2), str(BTN_Y), "30")          # 设为B
            time.sleep(.3)
            send("click", str(COL3), str(BTN_Y), "30")          # 应用混合
            mixes = wait_calls("mix ", 2)   # 没进混合态的话这里会等到超时
            assert mixes[-1].split()[1] in looks, mixes

            p.wait(timeout=12)
            return log.read_text()
        finally:
            if p.poll() is None:
                p.kill()
                p.wait()
            stream.close()
