#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pack_release.py -- 把当前 mod 打包为可直接解压到 SD 卡根的发布 zip。

产物：
  dist/NX-WA-<version>.zip          解压到 SD 卡根即用（install.sh 会自动同步 scripts/）
  dist/NX-WA-<version>.zip.md5      校验值（贴进 Release notes）

用法：
  python tools/pack_release.py            # 正常打包
  python tools/pack_release.py --list     # 只打印将被打包的文件清单

设计原则：
  * 只打"相机真正需要的"：SD 根触发三件套 + scripts/ + 卸载包 + 顶层说明文件
  * 不打：raw8/ .uploads/ backup*/ docs/ test_server/ .git* （含固件镜像/实验产物/内部文档）
  * 过滤开发垃圾（__pycache__ / *.pyc / 编辑器临时文件）
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


def md5(path):
    h = hashlib.md5()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    ver = version()
    files = collect()
    extras = [(s, d) for s, d in EXTRA_ASSETS if os.path.isfile(s)]
    if '--list' in sys.argv:
        for f in files:
            print('%9d  %s' % (os.path.getsize(f), f))
        for s, d in extras:
            print('%9d  %s  <- %s' % (os.path.getsize(s), d, s))
        print('共 %d 个文件' % (len(files) + len(extras)))
        return

    os.makedirs('dist', exist_ok=True)
    zpath = os.path.join('dist', 'NX-WA-%s.zip' % ver)

    commit = git('rev-parse', '--short', 'HEAD')
    branch = git('rev-parse', '--abbrev-ref', 'HEAD')
    manifest = [
        'NX-WA release manifest',
        '======================',
        'version      : %s' % ver,
        'git commit   : %s (%s)' % (commit, branch),
        'built at     : %s' % datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'install      : 解压到 SD 卡根目录 -> 插卡自动安装/增量同步',
        '               (install.sh 会把 scripts/ 同步到相机 /opt/usr/nx-ks/)',
        '',
        '%9s  %-32s  %s' % ('size', 'md5', 'path'),
        '-' * 78,
    ]
    for f in files:
        manifest.append('%9d  %-32s  %s' % (os.path.getsize(f), md5(f), f))
    for s, d in extras:
        manifest.append('%9d  %-32s  %s' % (os.path.getsize(s), md5(s), d))
    manifest.append('')
    manifest.append('共 %d 个文件' % len(files))
    manifest.append('本包不含 raw8/ .uploads/ docs/ test_server/ 等逆向产物（见仓库）。')

    with zipfile.ZipFile(zpath, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in files:
            z.write(f, f)
        for s, d in extras:
            z.write(s, d)
        z.writestr('NX-WA-MANIFEST.txt', '\n'.join(manifest) + '\n')

    size = os.path.getsize(zpath)
    print('已生成: %s  (%.1f MB, %d 文件 + manifest)' % (zpath, size / 1048576.0, len(files)))
    print('md5   : %s' % md5(zpath))
    with open(zpath + '.md5', 'w', encoding='utf-8') as fh:
        fh.write('%s  %s\n' % (md5(zpath), os.path.basename(zpath)))
    print('校验  : %s.md5' % zpath)


if __name__ == '__main__':
    main()
