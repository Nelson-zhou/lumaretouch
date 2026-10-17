#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""版本号单一出处：packaging/VERSION。

为什么要有这个脚本：M0 起包版本一直钉在 0.0.1，而它同时抄在八个地方
（engine/pyproject.toml、引擎 __init__、ui/package.json、package-lock.json 两处、
tauri.conf.json、Cargo.toml，外加 Cargo.lock 里那一条）。发布物一旦要带真版本号，
手工改必然漏一处——而漏掉的那一处不会被任何测试抓到：deb 的 Version 取自
tauri.conf.json，引擎在 ready 里报的是 __init__ 里那份；两者不一致时，**装机 UI
显示的版本与真正在跑的引擎版本就是两句话**，而这正是「按内容自证」最该拦的事。

纪律与仓里其它判据脚本一致：
  · 每处都先断言「命中且只命中该次数」，任何一处对不上就整段中止，一个字节不改；
  · check 只报账不改文件；sync 写完立刻用同一套 check 复核；
  · gen/engine-stage 是打包暂存的生成物（stage-engine.sh 每次重拷），不参与判定。

用法：
  packaging/release-version.py check            # 门禁（CI 与 build-deb 前置）
  packaging/release-version.py get              # 只打版本号，给 shell 取值
  packaging/release-version.py sync 0.9.0       # 改出处并同步全部落点
"""
from __future__ import annotations

import argparse
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
VERSION_FILE = os.path.join(HERE, "VERSION")

VER_RE = re.compile(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?")

# 每一处 = (相对路径, 人读的落点名, 定位正则, 期望命中次数)。正则的三个捕获组
# 是「前缀 / 旧版本号 / 后缀」，替换时只动中间那段——缩进、键名、等号写法一律保住，
# 免得 package-lock 这种"格式也是产物"的文件被整篇重排。
SOURCES: list[tuple[str, str, re.Pattern, int]] = [
    ("engine/pyproject.toml", "pyproject",
     re.compile(r'(?m)^(version = ")(\d[^"]*)(")$'), 1),
    ("engine/src/lumaretouch_engine/__init__.py", "引擎 __version__",
     re.compile(r'(?m)^(__version__ = ")(\d[^"]*)(")$'), 1),
    ("ui/package.json", "ui package.json",
     re.compile(r'(?m)^(\s{2}"version": ")(\d[^"]*)(",?)$'), 1),
    # package-lock：顶层一条（缩进 2）+ packages[""] 里一条（缩进 6），缩进正好分开
    ("ui/package-lock.json", "lock 顶层",
     re.compile(r'(?m)^(\s{2}"version": ")(\d[^"]*)(",)$'), 1),
    ("ui/package-lock.json", "lock packages[\"\"]",
     re.compile(r'(?m)^(\s{6}"name": "lumaretouch-ui",\n\s{6}"version": ")(\d[^"]*)(",)$'), 1),
    # ↑ 这一处不能只按缩进筛：lock 里缩进 6 的 "version": " 有 135 条（每个依赖一条），
    #   拿缩进当锚等于给一千多个第三方包改版本号。靠紧邻的包名行把锚收到唯一一处。
    ("ui/src-tauri/tauri.conf.json", "tauri.conf（deb 的 Version 来自这里）",
     re.compile(r'(?m)^(\s{2}"version": ")(\d[^"]*)(",)$'), 1),
    ("ui/src-tauri/Cargo.toml", "Cargo.toml",
     re.compile(r'(?m)^(version = ")(\d[^"]*)(")$'), 1),
    # Cargo.lock 里只取我们这一个包那一条，别误伤上千个依赖的版本
    ("ui/src-tauri/Cargo.lock", "Cargo.lock 的 lumaretouch 条目",
     re.compile(r'(?m)^(name = "lumaretouch"\nversion = ")(\d[^"]*)(")$'), 1),
]


def path_of(rel: str) -> str:
    return os.path.join(REPO, rel)


def read_current() -> str:
    if not os.path.isfile(VERSION_FILE):
        sys.exit("× packaging/VERSION 不存在——版本号没有出处，先建它")
    v = io.open(VERSION_FILE, encoding="utf-8").read().strip()
    if not VER_RE.fullmatch(v):
        sys.exit(f"× packaging/VERSION 不是合法语义化版本号：{v!r}")
    return v


def check(verbose: bool = True) -> int:
    want = read_current()
    bad: list[str] = []
    for rel, tag, pat, expect in SOURCES:
        p = path_of(rel)
        if not os.path.isfile(p):
            bad.append(f"{rel}（{tag}）：文件不存在")
            continue
        text = io.open(p, encoding="utf-8").read()
        hits = pat.findall(text)
        got = [h[1] for h in hits]
        if len(got) != expect:
            bad.append(f"{rel}（{tag}）：定位到 {len(got)} 处，应为 {expect} 处")
            continue
        for v in got:
            if v != want:
                bad.append(f"{rel}（{tag}）：写着 {v}，VERSION 是 {want}")
        if verbose and all(v == want for v in got):
            print(f"  ✓ {rel}（{tag}）= {want}")
    if bad:
        print("× 版本号漂移：")
        for b in bad:
            print(f"  · {b}")
        print("  修法：改 packaging/VERSION，再跑 packaging/release-version.py sync <版本>")
        return 1
    if verbose:
        print(f"✓ 版本号一致：{want}（{len(SOURCES)} 处落点全部核对）")
    return 0


def sync(new: str) -> int:
    if not VER_RE.fullmatch(new):
        sys.exit(f"× {new!r} 不是合法语义化版本号")
    # 预演：任何一处定位不上就整段中止——半同步比不同步更坏（.deb 与引擎版本分叉）
    texts: dict[str, str] = {}
    for rel, tag, pat, expect in SOURCES:
        text = texts.get(rel)
        if text is None:
            p = path_of(rel)
            if not os.path.isfile(p):
                sys.exit(f"× {rel}（{tag}）不存在——整段中止，一个字节都没改")
            text = io.open(p, encoding="utf-8").read()
        if len(pat.findall(text)) != expect:
            sys.exit(f"× {rel}（{tag}）：定位到 {len(pat.findall(text))} 处，应为 {expect} 处"
                     f"——整段中止，一个字节都没改")
        texts[rel] = pat.sub(r"\g<1>" + new + r"\g<3>", text)
    io.open(VERSION_FILE, "w", encoding="utf-8").write(new + "\n")
    for rel, text in texts.items():
        io.open(path_of(rel), "w", encoding="utf-8").write(text)
    print(f"→ 已写入 {new}：packaging/VERSION + " + "、".join(sorted(texts)))
    return check()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="op", required=True)
    sub.add_parser("check", help="核对全部落点与 packaging/VERSION 一致")
    sub.add_parser("get", help="只打当前版本号")
    ps = sub.add_parser("sync", help="改版本号并同步全部落点")
    ps.add_argument("new")
    a = ap.parse_args()
    if a.op == "check":
        return check()
    if a.op == "get":
        print(read_current())
        return 0
    return sync(a.new)


if __name__ == "__main__":
    sys.exit(main())
