#!/usr/bin/env python3
"""生成 SDIC 字体的裁剪变体，用于量化 NXUI 首帧的字体打开成本。

背景（见 fontprobe.c）：FcFreeTypeQuery 一次要 146 ms，其中几乎全部是
遍历 cmap 构建 FcCharSet。原字体有 44,426 个码点，而面板只用得到几百个。
两个变体：

  gb2312  保留 GB2312 全集（6763 汉字 + 符号）+ ASCII + 面板标点
          —— "谁都能用"的保守档，覆盖所有简体中文日常文本
  panel   只保留 ASCII + 面板静态文本里的字符
          —— 激进档，用来测下界（缺字风险由使用方承担）

用法:
    python make_font_subset.py <input.ttf> <outdir>
"""
import re
import subprocess
import sys
from pathlib import Path

# 面板里出现的非 ASCII 符号：‹ › · … 以及全角标点
PANEL_PUNCT = "‹›·…—–、，。：；！？（）【】《》“”‘’　"

# nxui.c 里的中文字面量，外加配方名可能用到的常见字
PANEL_EXTRA = (
    "滤镜预览保存关闭开启已未无法读取服务状态请重试命令失败详情见日志"
    "正在执行子菜单生成可重新进入自动应用选择等待当前完成"
    "上一个下一个页确人认启停开关组件对比锐度灰度黑白彩色"
    "端口网络连接相机检查相册传输拷贝删除确认取消返回退出设置"
)


def gb2312_chars() -> str:
    chars = []
    for hi in range(0xA1, 0xF8):
        for lo in range(0xA1, 0xFF):
            try:
                chars.append(bytes((hi, lo)).decode("gb2312"))
            except UnicodeDecodeError:
                continue
    return "".join(chars)


def panel_chars(source: Path) -> str:
    text = source.read_text(encoding="utf-8")
    found = set()
    for literal in re.findall(r'"((?:[^"\\]|\\.)*)"', text):
        for ch in literal:
            if ord(ch) > 0x7F:
                found.add(ch)
    return "".join(sorted(found)) + PANEL_EXTRA + PANEL_PUNCT


def run_subset(src: Path, dst: Path, text: str, family: str | None = None) -> None:
    subprocess.run(
        [
            sys.executable, "-m", "fontTools.subset", str(src),
            f"--text={text}",
            f"--unicodes=U+0020-007E",
            "--layout-features=",
            "--drop-tables+=DSIG",
            "--name-IDs=*",
            "--recalc-bounds",
            f"--output-file={dst}",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    if family:
        rename_family(dst, family)
    print(f"{dst.name}: {dst.stat().st_size:,} B  ({len(set(text))} 请求码点)"
          + (f"  family={family}" if family else ""))


def rename_family(path: Path, family: str) -> None:
    """改 family 名。同名时 fontconfig 一定选系统那份（实测目录顺序无效），
    所以子集字体必须有自己的名字，代码里按新名打开。"""
    from fontTools.ttLib import TTFont

    font = TTFont(str(path))
    for rec in font["name"].names:
        if rec.nameID in (1, 3, 4, 6, 16):        # family / unique / full / PS / preferred
            rec.string = family
    font.save(str(path))
    font.close()


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    src = Path(sys.argv[1])
    out = Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    here = Path(__file__).resolve().parent

    # 生产只发 gb2312 这一档（38 KB 的 panel 档实测没有收益：按文件打开
    # 49 ms ≈ 按 family 打开 1.9 MB 的 51 ms，见
    # docs/current/NXUI_FIRST_FRAME_2026-10-19.md）。panel 档留在生成器里
    # 只作重测用；两个 family 名不同，才能在同一目录里共存。
    static = panel_chars(here / "nxui.c")
    run_subset(src, out / "font-sub-gb2312.ttf", gb2312_chars() + static,
               family="NXUI_CJK")
    run_subset(src, out / "font-sub-panel.ttf", static, family="NXUI_CJK_MIN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
