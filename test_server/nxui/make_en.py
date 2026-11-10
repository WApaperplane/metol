#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_en.py -- 从 nxui.c 生成英文源码 out/nxui_en.c（只替换字符串字面量）。

为什么用"生成"而不是在源码里加 #ifdef：
  * nxui.c 有 135 条用户可见中文，散在 700 行里，改 #ifdef 会污染每一处；
  * 生成器能机械校验"是否还有漏翻的中文"，翻译单独放 i18n/en.json，改文案不动 C；
  * 注释里的中文不受影响（只替换带引号的字面量）。

用法：
  python3 make_en.py            # 生成 out/nxui_en.c 并报告
  python3 make_en.py --check    # 只检查覆盖率，不写文件
"""
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
SRC = HERE / "nxui.c"
TABLE = HERE / "i18n" / "en.json"
OUT = HERE / "out" / "nxui_en.c"

CJK = re.compile("[\u4e00-\u9fff]")
LIT = re.compile(r'"((?:[^"\\]|\\.)*)"')


def unescape(s: str) -> str:
    return s.replace('\\"', '"').replace("\\\\", "\\")


def escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def main() -> int:
    src = SRC.read_text(encoding="utf-8")
    table = json.loads(TABLE.read_text(encoding="utf-8"))

    missing, used = [], set()

    def repl(m: re.Match) -> str:
        raw = m.group(1)
        text = unescape(raw)
        if not CJK.search(text):
            return m.group(0)
        if text not in table:
            missing.append(text)
            return m.group(0)
        used.add(text)
        return '"' + escape(table[text]) + '"'

    out = LIT.sub(repl, src)

    if missing:
        print("!! 缺翻译 %d 条：" % len(missing))
        for s in missing:
            print("   ", s)
        return 2

    # 断言：剩下的 CJK 只允许出现在注释里（注释保留中文，不影响编译产物）
    body = LIT.sub('""', out)                       # 去掉字面量
    body = re.sub(r"/\*.*?\*/", "", body, flags=re.S)  # 去掉块注释
    body = re.sub(r"//[^\n]*", "", body)               # 去掉行注释
    if CJK.search(body):
        hit = CJK.search(body)
        line = body[: hit.start()].count("\n") + 1
        print("!! 第 %d 行仍有字面量外的中文（多半是新加的字符串没进 en.json）" % line)
        return 3

    unused = sorted(set(table) - used)
    print("替换 %d 条；表内未用 %d 条" % (len(used), len(unused)))
    for s in unused[:10]:
        print("   未用:", s)

    if "--check" in sys.argv:
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("/* 由 make_en.py 从 nxui.c 生成，勿手改。文案见 i18n/en.json */\n" + out,
                   encoding="utf-8")
    print("已写:", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
