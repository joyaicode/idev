#!/usr/bin/env python3
"""从 GitHub 仓库下载炼化书单的真 PDF（修复 scripts/docs/ 下的 HTML 伪装文件）。
raw.githubusercontent.com 被阻断，三条通道按序回退：
  通道一 gh api raw（已认证 5000 次/h；≤12MB 稳定，大文件 HTTP/2 流易中途 CANCEL）
  通道二 ghproxy.net 代理 raw（HTTP/1.1 + Range 断点续传，大文件可靠）
  通道三 匿名 curl api.github.com（60 次/h，易限流且不支持 Range，兜底）
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
    ('代码大全.pdf', 'PDF-file/clean-code/代码大全.pdf', True),
    ('修改代码的艺术.pdf', 'PDF-file/clean-code/修改代码的艺术.pdf', True),
    ('设计模式：可复用面向对象软件的基础.pdf', 'PDF-file/design-pattern/设计模式：可复用面向对象软件的基础.pdf', True),
    ('测试驱动开发.pdf', 'PDF-file/test/测试驱动开发.pdf', True),
]


def curl(args, timeout='900'):
    return subprocess.run(['curl', '-sL', '--max-time', timeout] + args,
                          capture_output=True, text=False)


def fetch(name, path):
    out = os.path.join(OUT_DIR, name)
    q = urllib.parse.quote(path)
    url = f'https://api.github.com/repos/{REPO}/contents/{q}?ref=main'
    api = f'repos/{REPO}/contents/{path}?ref=main'

    def ok_file():
        """真 PDF 校验：%PDF 头 + 足够大（防限流 JSON 伪装）。"""
        if not os.path.exists(out):
            return False
        with open(out, 'rb') as f:
            head = f.read(4)
        return head == b'%PDF' and os.path.getsize(out) > 100000

    # 通道一：gh（已认证）。大文件 HTTP/2 流可能中途 CANCEL，重试至字节达标。
    size = 0
    try:
        m = subprocess.run(['gh', 'api', api], capture_output=True, timeout=30)
        try:
            size = json.loads(m.stdout).get('size', 0)
        except Exception:
            size = 0
        for _ in range(6):
            r = subprocess.run(
                ['gh', 'api', api, '-H', 'Accept: application/vnd.github.raw'],
                capture_output=True, timeout=900)
            if r.stdout[:4] == b'%PDF' and len(r.stdout) >= (size or 1):
                with open(out, 'wb') as f:
                    f.write(r.stdout)
                return ok_file() and os.path.getsize(out) >= (size or 1)
            print(f'[{name}] gh retry: rc={r.returncode} got={len(r.stdout)}/{size}')
        print(f'[{name}] gh 6 次未达标，回退 ghproxy')
    except FileNotFoundError:
        print(f'[{name}] gh 不可用，回退 ghproxy')
    except Exception as e:
        print(f'[{name}] gh 异常: {e}')

    # 通道二：ghproxy.net 代理 raw（HTTP/1.1 + Range 断点续传，大文件可靠）
    prox = f'https://ghproxy.net/https://raw.githubusercontent.com/{REPO}/main/{q}'
    if not size:
        h = curl(['--http1.1', '-sIL', '--max-time', '30', prox])
        for line in h.stdout.decode('utf-8', 'ignore').splitlines():
            if line.lower().startswith('content-length:'):
                try:
                    size = max(size, int(line.split(':', 1)[1].strip()))
                except ValueError:
                    pass
    for _ in range(10):
        r = curl(['--http1.1', '-C', '-', '-o', out, prox])
        if ok_file() and (not size or os.path.getsize(out) >= size):
            return True
        if r.returncode == 0:
            try:
                os.remove(out)  # 200 但内容不对，删掉防污染续传
            except OSError:
                pass
            print(f'[{name}] ghproxy 200 但非 PDF，放弃该通道')
            break
        print(f'[{name}] ghproxy resume: rc={r.returncode} '
              f'got={os.path.getsize(out) if os.path.exists(out) else 0}/{size}')

    # 通道三：匿名 curl api.github.com（60 次/h，可能 403 限流；不支持 Range）
    r = curl(['-H', 'Accept: application/vnd.github.raw', '-o', out, url])
    if not ok_file():
        print(f'[{name}] curl 结果非 PDF（限流/截断）')
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
    return ok_file() and (not size or os.path.getsize(out) >= size)


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