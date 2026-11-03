#!/usr/bin/env python3
"""从 GitHub API 下载炼化书单的真 PDF（修复 scripts/docs/ 下的 HTML 伪装文件）。
raw.githubusercontent.com 被阻断，走 api.github.com contents raw（唯一可达通道）。
用法: python3 scripts/docs/fetch-books.py [书名关键词...]  无参数=下载全部缺书
"""
import json
import os
import subprocess
import sys
import urllib.parse

REPO = 'Dujltqzv/Some-Many-Books'
OUT_DIR = os.path.dirname(os.path.abspath(__file__))

BOOKS = [
    # (输出文件名, 仓库路径, 是否必需)
    ('微服务设计.pdf', 'PDF-file/microservice/微服务设计.pdf', True),
    ('程序设计方法.pdf', 'PDF-file/clean-code/程序设计方法.pdf', True),
    ('编写可读代码的艺术.pdf', 'PDF-file/clean-code/编写可读代码的艺术.pdf', True),
    ('设计模式之禅.pdf', 'PDF-file/design-pattern/设计模式之禅.pdf', True),
    ('HeadFirst设计模式.pdf', 'PDF-file/design-pattern/HeadFirst设计模式.pdf', True),
    ('领域驱动设计：软件核心复杂性应对之道.pdf', 'PDF-file/clean-code/领域驱动设计：软件核心复杂性应对之道.pdf', True),
    ('代码整洁之道.pdf', 'PDF-file/clean-code/代码整洁之道.pdf', False),  # 已知扫描版，仅备源
]


def curl(args, timeout='900'):
    return subprocess.run(['curl', '-sL', '--max-time', timeout] + args,
                          capture_output=True, text=False)


def fetch(name, path):
    out = os.path.join(OUT_DIR, name)
    q = urllib.parse.quote(path)
    url = f'https://api.github.com/repos/{REPO}/contents/{q}?ref=main'
    r = curl(['-H', 'Accept: application/vnd.github.raw', '-o', out, url])
    if r.returncode != 0:
        print(f'[{name}] curl exit={r.returncode}')
        return False
    # 查真实 size 并断点续传补齐
    meta = curl(['--max-time', '30', url])
    try:
        size = json.loads(meta.stdout).get('size', 0)
    except Exception:
        size = 0
    if size and os.path.exists(out):
        for _ in range(10):
            cur = os.path.getsize(out)
            if cur >= size:
                break
            r = curl(['-C', '-', '-H', 'Accept: application/vnd.github.raw',
                      '-o', out, url])
            if r.returncode not in (0, 33, 28):
                print(f'[{name}] resume exit={r.returncode}')
                return False
    return os.path.exists(out) and (not size or os.path.getsize(out) >= size)


def main():
    kw = sys.argv[1:]
    for name, path, need in BOOKS:
        if kw and not any(k in name for k in kw):
            continue
        ok = fetch(name, path)
        sz = os.path.getsize(os.path.join(OUT_DIR, name)) if os.path.exists(
            os.path.join(OUT_DIR, name)) else 0
        print(f'[{name}] {"OK" if ok else "FAIL"} {sz} bytes', flush=True)


if __name__ == '__main__':
    main()