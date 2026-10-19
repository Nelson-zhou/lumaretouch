"""源码文本完整性门禁：把"写进去的中文是不是我想写的那个字"变成一条能跑的判据。

为什么单独立一条（不是洁癖，是本轮真付过钱的坑）：非 ASCII 文本在"生成 → 落盘"这条
通路上会被偶发地换成一个**看着像但不同**的字。已经抓到过四次：

· `抄一份` 写成 `拄一份`（engine/tests、server.py、App.tsx、native.ts、main.rs 各一次，
  其中 main.rs 那两处是**人工扫全仓**才发现的——当时只复查了本轮改过的文件，漏了旧轮次
  写进另一个文件的那一处）；
· `蒙版` 写成 `蓙版`、`超过` 写成 `呰过`、`外扩` 掉成 `外扌`（Kangxi 部首那一块是这类
  损坏最常见的落点，所以整段拉黑而不是逐字点名单）。

这类字不会让任何一条测试变红，也不会被 lint 抓到：它是**注释与文案**里的错，读的人只会
以为作者写了个异体字。所以判据只能是对码位的机器扫描，而不是"下次注意"。

扫描范围按文件后缀白名单（源码 + 文档 + 打包脚本），不看内容里的引号或代码块：
一条门禁要有多重语境判断，它就不会在凌晨那次改注释时提醒你。
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# 参与扫描的目录与后缀。docs 也扫：验收报告与 ADR 里写错一个字，是要拿去签字的东西。
SCAN_DIRS = ("engine/src", "engine/tests", "ui/src", "ui/src-tauri/src",
             "docs", "packaging", "tools")
SUFFIXES = (".py", ".ts", ".tsx", ".rs", ".md", ".sh", ".json", ".txt")
SKIP_DIR_NAMES = {"__pycache__", "target", "node_modules", ".git", "venv"}

# 明确点名的历史事故字（每一串都是"本仓写过、但不该出现在这里"的字）。
DENY_CHARS = set("拄蓙呰")
# 整段拉黑：康熙部首块（U+2F00–U+2FDF）。中文文案里出现这一段码位，只可能是损坏，
# 不可能是有意——真正的中文落在 U+4E00–U+9FFF。
RADICAL_BLOCKS = ((0x2F00, 0x2FDF), (0x31C0, 0x31EF))


def _scan_files() -> list[Path]:
    out: list[Path] = []
    for d in SCAN_DIRS:
        root = REPO / d
        if not root.is_dir():
            continue
        for p in sorted(root.rglob("*")):
            if not p.is_file() or p.suffix not in SUFFIXES:
                continue
            if SKIP_DIR_NAMES & set(p.parts):
                continue
            out.append(p)
    return out


def _offenders(text: str, *, deny: bool = True) -> list[tuple[int, str, str]]:
    """返回 (行号, 那个字符, 那一行的前 60 字)。"""
    bad: list[tuple[int, str, str]] = []
    for i, line in enumerate(text.splitlines(), 1):
        for ch in line:
            o = ord(ch)
            if (deny and ch in DENY_CHARS) or any(lo <= o <= hi for lo, hi in RADICAL_BLOCKS):
                bad.append((i, ch, line.strip()[:60]))
                break        # 一行只报一次：一条坏行足够指路，堆五条是噪音
    return bad


def test_repository_text_has_no_mangled_cjk():
    files = _scan_files()
    assert files, f"一个文件都没扫到（REPO 解析成了 {REPO}）——这条门禁会永远绿，先修它"
    problems: list[str] = []
    here = Path(__file__).resolve()
    for p in files:
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError as e:
            problems.append(f"{p.relative_to(REPO)} 不是合法 UTF-8：{e}")
            continue
        # 本文件就是那几个字的定义处（不命名就抓不到）：点名单对它自己关掉，
        # 而那一段码位（康熙部首）照扫——本文件里也不该拿那些码位写字
        deny = p.resolve() != here
        for line, ch, snippet in _offenders(text, deny=deny):
            problems.append(f"{p.relative_to(REPO)}:{line} 码位 U+{ord(ch):04X} "
                            f"「{ch}」→ {snippet}")
    assert not problems, (
        "源码/文档里出现了**损坏或绝不该用**的中文字符（见 ADR-0010 §7：这类字不会让任何"
        "测试变红，只能这样抓）：\n  " + "\n  ".join(problems[:20])
        + (f"\n  …共 {len(problems)} 处" if len(problems) > 20 else ""))


def test_scan_scope_actually_covers_the_repo():
    """守门禁本身：扫描目录里必须真有被扫到的文件，且至少覆盖这几个已知写入点。

    这条不是凑数。上一轮 拄→抄 的清理漏掉了 `ui/src-tauri/src/main.rs` 的两处，就是因为
    复查名单是"本轮改过的文件"而不是"仓库的源码全集"。把全集写死在这里，以后加目录忘了
    登记会当场响，而不是让那条门禁悄悄少扫一棵树。
    """
    files = _scan_files()
    rels = {p.relative_to(REPO).as_posix() for p in files}
    for must in ("engine/src/lumaretouch_engine/server.py",
                 "engine/tests/test_protocol.py",
                 "ui/src/App.tsx",
                 "ui/src-tauri/src/main.rs",
                 "docs/adr/0010-local-color-grade-scope.md"):
        assert must in rels, f"扫描名单没覆盖到 {must}——那条文本门禁会在这里悄悄少扫一片"
