#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pack_release.py -- 把当前 mod 打包为可直接解压到 SD 卡根的发布 zip。

产物：
  dist/NX-WA-<version>.zip          中文包（默认）
  dist/NX-WA-<version>-EN.zip       英文包（--lang en）
  dist/<zip>.md5                    校验值（贴进 Release notes）

用法：
  python tools/pack_release.py                 # 中文包
  python tools/pack_release.py --lang en       # 英文包（菜单/README/面板二进制换成英文）
  python tools/pack_release.py --list          # 只打印将被打包的文件清单

设计原则：
  * 只打"相机真正需要的"：SD 根触发三件套 + scripts/ + 卸载包 + 顶层说明文件
  * 不打：raw8/ .uploads/ backup*/ docs/ test_server/ .git* （含固件镜像/实验产物/内部文档）
  * 过滤开发垃圾（__pycache__ / *.pyc / 编辑器临时文件）
  * 英文包 = 同一棵树 + i18n/en/ 覆盖层 + nxui_en.arm 顶替 nxui.arm + README 换位
"""
import os
import re
import sys
import zipfile
import hashlib
import subprocess
from datetime import datetime

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)

ROOT_FILES = [
    'install.sh', 'info.tg', 'nx_cs.adj',
    'README.md', 'README_EN.md', 'VERSION', 'LICENSE', 'ATTRIBUTION.md', 'SYNC.md',
]
ROOT_DIRS = ['scripts', 'looks', 'uninstall_pkg']

EXCLUDE_DIRS = {'__pycache__', '.git', '.github', '.workbuddy', 'node_modules', '.idea'}
EXCLUDE_FILE_RE = re.compile(
    r'(\.pyc$|\.pyo$|\.swp$|\.orig$|\.rej$|~$|^\.DS_Store$|^Thumbs\.db$|^\.gitignore$|\.log$)'
)

# 额外附件（源路径 → zip 内路径）：随包分发、但不属于 SD 根主树（如 A2 固件补丁镜像）
EXTRA_ASSETS = [
    ('fw/v1.12/a2/p7_a2.bin', 'patch-a2/p7_a2.bin'),
    ('fw/v1.12/a2/README-A2.md', 'patch-a2/README-A2.md'),
    ('fw/v1.12/a2/README-A2_EN.md', 'patch-a2/README-A2_EN.md'),
]

EN_OVERLAY = 'i18n/en'          # 英文覆盖层：i18n/en/scripts/xxx → scripts/xxx
EN_PANEL = ('scripts/nxui/nxui_en.arm', 'scripts/nxui/nxui.arm')


def version():
    for line in open('VERSION', encoding='utf-8'):
        m = re.match(r'^version\s+(\S+)', line.strip())
        if m:
            return m.group(1)
    return 'unknown'


def git(*args):
    try:
        return subprocess.check_output(['git'] + list(args), stderr=subprocess.DEVNULL,
                                       text=True).strip()
    except Exception:
        return ''


def collect():
    out = []
    for f in ROOT_FILES:
        if os.path.isfile(f):
            out.append(f)
        else:
            print('  ! 缺失（跳过）:', f)
    for d in ROOT_DIRS:
        for base, dirs, files in os.walk(d):
            dirs[:] = [x for x in dirs if x not in EXCLUDE_DIRS]
            for fn in sorted(files):
                p = os.path.join(base, fn).replace('\\', '/')
                if EXCLUDE_FILE_RE.search(fn):
                    continue
                out.append(p)
    return sorted(set(out))


def md5_bytes(data):
    return hashlib.md5(data).hexdigest()


def md5(path):
    with open(path, 'rb') as fh:
        return md5_bytes(fh.read())


def build_entries(files, extras, lang):
    """返回 {zip 内路径: bytes}。lang=en 时套覆盖层、换 README、换面板二进制。"""
    entries = {}
    for f in files:
        with open(f, 'rb') as fh:
            entries[f] = fh.read()
    for s, d in extras:
        with open(s, 'rb') as fh:
            entries[d] = fh.read()

    if lang != 'en':
        # 中文包不带英文面板二进制（省 470 KB，也避免两份 arm 混淆）
        entries.pop(EN_PANEL[0], None)
        return entries

    # 1) 覆盖层：i18n/en/** → 同名相对路径
    for base, dirs, names in os.walk(EN_OVERLAY):
        dirs[:] = [x for x in dirs if x not in EXCLUDE_DIRS]
        for fn in names:
            src = os.path.join(base, fn)
            rel = os.path.relpath(src, EN_OVERLAY).replace('\\', '/')
            with open(src, 'rb') as fh:
                entries[rel] = fh.read()
            print('  EN overlay:', rel)

    # 2) 面板二进制：nxui_en.arm 顶替 nxui.arm，原英文件不进包
    src, dst = EN_PANEL
    if src in entries:
        entries[dst] = entries.pop(src)
    else:
        print('  ! 缺 %s —— 英文面板没编？先跑 test_server/nxui/build.sh en' % src)

    # 3) README：英文版当主文档，中文版留成 README.zh-CN.md
    if 'README_EN.md' in entries and 'README.md' in entries:
        en = entries.pop('README_EN.md')
        zh = entries['README.md']
        entries['README.md'] = en
        entries['README.zh-CN.md'] = zh

    return entries


def main():
    lang = 'zh'
    if '--lang' in sys.argv:
        lang = sys.argv[sys.argv.index('--lang') + 1]
    ver = version()
    files = collect()
    extras = [(s, d) for s, d in EXTRA_ASSETS if os.path.isfile(s)]

    if '--list' in sys.argv:
        for f in files:
            print('%9d  %s' % (os.path.getsize(f), f))
        for s, d in extras:
            print('%9d  %s  <- %s' % (os.path.getsize(s), d, s))
        print('共 %d 个文件（lang=%s）' % (len(files) + len(extras), lang))
        return

    entries = build_entries(files, extras, lang)
    suffix = '' if lang == 'zh' else '-' + lang.upper()
    os.makedirs('dist', exist_ok=True)
    zpath = os.path.join('dist', 'NX-WA-%s%s.zip' % (ver, suffix))

    commit = git('rev-parse', '--short', 'HEAD')
    branch = git('rev-parse', '--abbrev-ref', 'HEAD')
    manifest = [
        'NX-WA release manifest',
        '======================',
        'version      : %s' % ver,
        'language     : %s' % lang,
        'git commit   : %s (%s)' % (commit, branch),
        'built at     : %s' % datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'install      : 解压到 SD 卡根目录 -> 插卡自动安装/增量同步',
        '               (install.sh 会把 scripts/ 同步到相机 /opt/usr/nx-ks/)',
        '               unzip to the SD-card root -> insert the card to install/sync',
        '',
        '%9s  %-32s  %s' % ('size', 'md5', 'path'),
        '-' * 78,
    ]
    for name in sorted(entries):
        data = entries[name]
        manifest.append('%9d  %-32s  %s' % (len(data), md5_bytes(data), name))
    manifest.append('')
    manifest.append('共 %d 个文件（不含 manifest）' % len(entries))
    manifest.append('本包不含 raw8/ .uploads/ docs/ test_server/ 等逆向产物（见仓库）。')

    with zipfile.ZipFile(zpath, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name in sorted(entries):
            z.writestr(name, entries[name])
        z.writestr('NX-WA-MANIFEST.txt', '\n'.join(manifest) + '\n')

    size = os.path.getsize(zpath)
    print('已生成: %s  (%.1f MB, %d 文件 + manifest, lang=%s)' %
          (zpath, size / 1048576.0, len(entries), lang))
    print('md5   : %s' % md5(zpath))
    with open(zpath + '.md5', 'w', encoding='utf-8') as fh:
        fh.write('%s  %s\n' % (md5(zpath), os.path.basename(zpath)))
    print('校验  : %s.md5' % zpath)


if __name__ == '__main__':
    main()
