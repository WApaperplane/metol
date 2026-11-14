"""Exercise real filmlab.sh against local prefman/st/pwsend doubles.

★ 2026-11-14 重组：filmlab 有两个入口，语义不同，必须分开验。

  CLI  `apply <recipe> [slot]`
      跟随档位。槽由 `getusr20` 解析（或命令行直给），算不出来就 REJECT；
      写槽前先备份该槽，写完把运行时档位切回目标 enum。这条链没变。

  UI   `preview` / `commit`（2026-10-17 快路径）
      preview 一个槽字节都不写、也不备份 —— 画面全部来自 A2 直推（pwsend）。
      commit 只写 CUSTOM1（slot 9）并 prefman save，随后把 enum 切回
      打开面板时那一档（nxui 通过 FILMLAB_ENUM_CACHE 传入，见 nxui.c:260）。

  为什么这组测试以前全红：它拿 UI 入口（preview/commit）去验 CLI 语义。
  旧断言要求 preview 写 7 个参数、按 enum 生成 slot-N 备份、拒绝未知档位 ——
  这些在快路径里都不再发生，不是"断言过期"，是入口选错了。

  另注：把 enum 切回去**不会**让 ISP 重读槽（2026-10-08 实验证伪：切换不搬运
  参数）。所以本会话画面不变，重启后 p7 才按当前档位读槽。测试只断言调用序列，
  不宣称画面 —— 那是 ISP 的事，这里够不着。
"""
from pathlib import Path
import json
import os
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
PW_BASE, PSTEP, SSTEP = 41964, 52, 4

# 期望的直推值从 recipes.json 读，不写字面量 —— 调色改过一次 R_COLOR（106 → 108）
# 就让整组断言红掉的做法已经踩过一次。
_RECIPES = json.loads((REPO / "scripts/filmlab/recipes.json").read_text(encoding="utf-8"))


def push_line(recipe="portra400"):
    r = _RECIPES["recipes"][recipe]
    pairs = [(0x134, r["R_COLOR"]), (0x135, r["G_COLOR"]), (0x136, r["B_COLOR"]),
             (0x137, r["HUE"]), (0x138, r["SATURATION"]), (0x139, r["SHARPNESS"]),
             (0x13A, r["CONTRAST"]), (0x13B, 1)]
    return " ".join(f"0x{reg:03X} {val}" for reg, val in pairs)


class EngineHarness(unittest.TestCase):
    """共用夹具：把 filmlab.sh 装进临时树，prefman/st/pwsend 全用 shell 桩。"""

    #: CLI 的 pw_force_reload 会 sleep 1 秒自证；子类可关掉，免得 12 个子用例跑成 12 秒
    fast_sleep = False

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="nxui-engine-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.bin = self.base / "bin"; self.bin.mkdir()
        self.lab = self.base / "lab"; self.lab.mkdir()
        self.log = self.base / "calls"
        self.current = self.base / "current-pw"
        self.current.write_text("0x140009\n")
        self.env = os.environ.copy()
        self.env.update(PATH=f"{self.bin}:{os.environ['PATH']}",
                        CALLS=str(self.log), CURRENT_PW_FILE=str(self.current))
        self.stub("busybox", self._busybox_shim())
        self.stub("prefman", 'echo "prefman $*" >> "$CALLS"; if [ "$1" = get ]; then '
                             'p=$((($3-41964)/52)); v=10; [ "$p" -ge 3 ] || v=100; '
                             'echo "value = $v"; fi; exit 0')
        self.stub("st", '''echo "st $*" >> "$CALLS"
case "$3" in
  getusr) echo "UserData is CURRENT ($(cat "$CURRENT_PW_FILE"))" ;;
  setusr) [ "${RESTORE_FAIL:-0}" != 1 ] || exit 8; echo "$5" > "$CURRENT_PW_FILE" ;;
esac
exit 0''')
        self.stub("pwsend.arm", 'echo "pwsend $*" >> "$CALLS"; echo 0x140009 > "$CURRENT_PW_FILE"; exit 0')
        self.stub("sync", 'echo "sync" >> "$CALLS"')
        (self.lab / "recipes.json").write_bytes((REPO / "scripts/filmlab/recipes.json").read_bytes())
        self.engine = self.bin / "filmlab.sh"
        self.engine.write_text((REPO / "scripts/filmlab.sh").read_text()
                               .replace("/opt/usr/nx-ks", str(self.bin))
                               .replace("/mnt/mmc/filmlab", str(self.lab)))

    def _busybox_shim(self):
        if not self.fast_sleep:
            return 'cmd="$1"; shift; exec "$cmd" "$@"'
        return 'cmd="$1"; shift; [ "$cmd" != sleep ] || exit 0; exec "$cmd" "$@"'

    def stub(self, name, source):
        p = self.bin / name; p.write_text("#!/bin/sh\n" + source + "\n"); p.chmod(0o755)

    def run_engine(self, *args, conf="", env=None):
        (self.lab / "filmlab.conf").write_text("FILMLAB_PW=1\n" + conf)
        e = dict(self.env, **(env or {}))
        r = subprocess.run(["sh", str(self.engine), *args], env=e,
                           capture_output=True, text=True)
        calls = self.log.read_text() if self.log.exists() else ""
        return r, calls

    # ---- 断言小工具 ----
    def sets(self, calls):
        return [ln for ln in calls.splitlines() if ln.startswith("prefman set")]

    def addrs(self, calls):
        return {int(ln.split()[3], 16) for ln in self.sets(calls)}

    @staticmethod
    def slot_addrs(slot):
        return {PW_BASE + p * PSTEP + slot * SSTEP for p in range(7)}


class CliEngineTests(EngineHarness):
    """`apply <recipe> [slot]` —— 跟随档位、逐槽备份、算不出来就拒绝。"""

    fast_sleep = True

    def apply(self, *extra, conf="FILMLAB_SAVE=0\n", env=None):
        return self.run_engine("apply", "portra400", *extra, conf=conf, env=env)

    def test_every_visible_field_is_preserved(self):
        """12 个可见档位各跑一遍：写对应槽、备份对应槽、档位切回去。"""
        mappings = [(f"0x14000{i:x}", i) for i in range(11)] + [("0x14000c", 11)]
        for enum, slot in mappings:
            with self.subTest(enum=enum, slot=slot):
                self.current.write_text(enum + "\n")
                self.log.write_text("")
                r, calls = self.apply()
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertEqual(self.current.read_text().strip(), enum)
                self.assertEqual(len(self.sets(calls)), 7)
                self.assertEqual(self.addrs(calls), self.slot_addrs(slot))
                backup = self.lab / f"slot-backups/slot-{slot}.txt"
                self.assertEqual(backup.read_text().strip(),
                                 f"{slot}|100|100|100|10|10|10|10")
                if enum != "0x140009":
                    self.assertNotIn("st cap capdtm setusr 20 0x140009", calls)
                    self.assertLess(calls.index("pwsend seq"),
                                    calls.index(f"st cap capdtm setusr 20 {enum}"))

    def test_unknown_or_unreadable_field_rejected_before_writes(self):
        for enum in ("", "0x14000b", "0x14000d", "unreadable"):
            with self.subTest(enum=enum):
                self.current.write_text(enum + "\n"); self.log.write_text("")
                r, calls = self.apply()
                self.assertNotEqual(r.returncode, 0)
                self.assertIn("REJECT", r.stdout)
                self.assertEqual(self.sets(calls), [])
                self.assertNotIn("pwsend seq", calls)

    def test_explicit_slot_overrides_current_field(self):
        self.current.write_text("0x140000\n")
        r, calls = self.apply("3")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.addrs(calls), self.slot_addrs(3))
        self.assertEqual((self.lab / "slot-backups/slot-3.txt").read_text().strip(),
                         "3|100|100|100|10|10|10|10")
        self.assertIn("st cap capdtm setusr 20 0x140003", calls)
        self.assertEqual(self.current.read_text().strip(), "0x140003")

    def test_backup_failure_prevents_any_write(self):
        self.stub("prefman", 'echo "prefman $*" >> "$CALLS"; exit 4')
        r, calls = self.apply()
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.sets(calls), [])

    def test_slot_write_failure_stops_before_backend(self):
        d = self.lab / "slot-backups"; d.mkdir()
        (d / "slot-9.txt").write_text("9|100|100|100|10|10|10|10\n")
        self.stub("prefman", 'echo "prefman $*" >> "$CALLS"; exit 4')
        r, calls = self.apply()
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("pwsend seq", calls)

    def test_failed_send_still_restores_original_field(self):
        self.current.write_text("0x14000a\n")
        self.stub("pwsend.arm", 'echo 0x140009 > "$CURRENT_PW_FILE"; exit 9')
        r, calls = self.apply()
        self.assertEqual(self.current.read_text().strip(), "0x14000a")
        self.assertNotIn("prefman save", calls)

    def test_recipe_out_of_range_is_rejected_before_writes(self):
        data = (self.lab / "recipes.json").read_text().replace('"HUE": 11', '"HUE": 21')
        (self.lab / "recipes.json").write_text(data)
        r, calls = self.apply()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("REJECT", r.stdout)
        self.assertEqual(self.sets(calls), [])


class UiEngineTests(EngineHarness):
    """`preview` / `commit` —— 快路径契约：commit 只写 CUSTOM1，preview 一个字节都不写。"""

    #: nxui 打开面板时读一次当前档位，apply 时通过环境变量传回来（nxui.c:260）
    panel_enum = "0x140009"

    def ui(self, verb, *, conf="", env=None):
        e = {"FILMLAB_ENUM_CACHE": self.panel_enum}
        e.update(env or {})
        return self.run_engine(verb, "portra400", conf=conf, env=e)

    # ---- preview：不动任何持久状态 ----
    def test_preview_writes_no_slot_and_never_saves(self):
        r, calls = self.ui("preview", conf="FILMLAB_SAVE=1\n")   # conf 要求落盘也必须被忽略
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.sets(calls), [])
        self.assertNotIn("prefman save", calls)
        self.assertFalse((self.lab / "slot-backups").exists(),
                         "preview 不应创建备份目录")
        self.assertIn(push_line(), calls)

    def test_preview_does_not_touch_the_profile_pointer(self):
        r, calls = self.ui("preview", env={"FILMLAB_ENUM_CACHE": "0x140003"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("setusr 20", calls)
        self.assertEqual(self.current.read_text().strip(), "0x140009")

    # ---- commit：只写 slot 9，且必须落盘 ----
    def test_commit_writes_slot9_and_saves(self):
        r, calls = self.ui("commit", conf="FILMLAB_SAVE=0\n")    # conf 想关掉也必须落盘
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(len(self.sets(calls)), 7)
        self.assertEqual(self.addrs(calls), self.slot_addrs(9))
        self.assertEqual(calls.count("prefman save 0"), 1)
        self.assertEqual((self.lab / "slot-backups/slot-9.txt").read_text().strip(),
                         "9|100|100|100|10|10|10|10")
        for other in (0, 1, 3, 10, 11):
            self.assertFalse((self.lab / f"slot-backups/slot-{other}.txt").exists(),
                             f"commit 不该碰 slot {other}")

    def test_commit_restores_panel_enum(self):
        self.panel_enum = "0x140000"
        r, calls = self.ui("commit")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertLess(calls.index("st cap capdtm setusr 20 0x140000"),
                        calls.index("prefman save 0"))
        self.assertEqual(self.current.read_text().strip(), "0x140000")

    def test_commit_on_custom1_skips_pointer_move(self):
        r, calls = self.ui("commit")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("setusr 20", calls)

    def test_restore_failure_does_not_save(self):
        self.panel_enum = "0x14000c"
        r, calls = self.ui("commit", env={"RESTORE_FAIL": "1"})
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("VERIFY-FAIL", r.stdout)
        self.assertNotIn("prefman save", calls)

    # ---- 后端契约 ----
    def test_missing_backend_rejects_before_slot_writes(self):
        (self.bin / "pwsend.arm").unlink()
        r, calls = self.ui("preview")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("REJECT", r.stdout)
        self.assertEqual(self.sets(calls), [])

    def test_backend_failure_is_not_reported_as_success(self):
        self.stub("pwsend.arm", "exit 9")
        r, calls = self.ui("preview")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("REJECT", r.stdout)
        self.assertNotIn("prefman save", calls)

    def test_commit_does_not_save_if_backend_fails(self):
        self.stub("pwsend.arm", "exit 9")
        r, calls = self.ui("commit")
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("prefman save", calls)

    # ---- 指针回读：不信 setusr 的退出码 ----
    def test_ready_readback_does_not_wait(self):
        self.panel_enum = "0x140003"
        self.stub("busybox", 'cmd="$1"; shift; [ "$cmd" != sleep ] || '
                             '{ echo WAITED >> "$CALLS"; exit 9; }; exec "$cmd" "$@"')
        r, calls = self.ui("commit")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("WAITED", calls)

    def test_delayed_readback_is_polled_until_confirmed(self):
        # 桩：setusr 只写 .next；getusr 第 3 次才把 .next 扶正（模拟 ISP 回读延迟）
        self.panel_enum = "0x140003"
        self.stub("st", '''echo "st $*" >> "$CALLS"
case "$3" in
  getusr)
    if [ -f "$CURRENT_PW_FILE.next" ]; then
      n=$(cat "$CURRENT_PW_FILE.n" 2>/dev/null || echo 0); n=$((n+1))
      echo "$n" > "$CURRENT_PW_FILE.n"
      [ "$n" -lt 3 ] || mv "$CURRENT_PW_FILE.next" "$CURRENT_PW_FILE"
    fi
    echo "UserData is CURRENT ($(cat "$CURRENT_PW_FILE"))" ;;
  setusr) echo "$5" > "$CURRENT_PW_FILE.next" ;;
esac
exit 0''')
        r, calls = self.ui("commit")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.current.read_text().strip(), "0x140003")
        self.assertGreaterEqual(calls.count("getusr 20"), 3)
        self.assertNotIn("VERIFY-FAIL", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
