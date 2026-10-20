#!/usr/bin/env python3
"""验收执行器：把《开发验收用例.json》的 80 条逐条落到真测试上，并出一份能复查的报告。

为什么要有这个工具（DoD §4：逐项执行并跑通 P0/P1，记录真实性能分位数）：
"跑通了 752 个测试"这句话证明不了验收——测试数量与用例数量是两件事，缺的正是
**用例 ID → 具体测试节点** 这一层映射。没有它，"覆盖"只能靠人脑记，而人脑记的
覆盖在评审桌上等于没有。

三条判据（都是硬的）：
① 每条用例必须被**至少一个测试直接引用其 ID**（引用写在测试函数体/文档串里，
   由本脚本解析，不是手工抄一份清单）；P0 缺引用 = 红。
② 映射到的节点必须在 `pytest --collect-only` 里真的存在：改了函数名不更新引用，
   就是"幽灵映射"，比没映射更坏（它看起来是绿的）。
③ 报告里的状态只来自 junit XML（ pytest 亲口说的），不来自任何自报。skip 对 P0
   记成 `unverified`（没跑过就是没跑过，不算通过）——本仓踩过的坑：开发 venv 没
   torch 时那批协议用例全 skip，看上去"一片绿"而产品面一次都没验。

用法：
    python3 tools/run-acceptance.py map                     # 只看当前引用情况（不跑测试）
    python3 tools/run-acceptance.py map --write              # 把候选映射写进 case-map.json（保留人工 note）
    ~/.local/share/LumaRetouch/engine/venv/bin/python \
        tools/run-acceptance.py run --junit /tmp/j.xml       # 跑测试 + 出报告（推荐在运行时 venv）
    python3 tools/run-acceptance.py report --junit /tmp/j.xml # 只用已有 junit 重生成报告（不重跑）
    python3 tools/run-acceptance.py check                    # 发布门禁用的轻量校验（不跑测试）
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CASES = REPO / "docs" / "acceptance" / "cases-frozen.json"
MAP = REPO / "docs" / "acceptance" / "case-map.json"
REPORT_JSON = REPO / "docs" / "acceptance" / "验收报告.json"
REPORT_MD = REPO / "docs" / "acceptance" / "验收报告.md"
# 默认拿运行时 venv：产品口径的性能与协议测试都要 torch，开发 venv 里那批会整片
# skip（skip 不是通过），用它收集节点只会得到一份"看着全绿而一次没跑"的报告。
DEFAULT_PY = os.environ.get("LRT_PYTEST_PYTHON") or str(
    Path.home() / ".local/share/LumaRetouch/engine/venv/bin/python")

TEST_GLOBS = ("engine/tests/test_*.py", "tests/test_*.py", "ui/tests/test_*.py")
# P0-* 那一组（P0-EXPOSURE-NEUTRAL 等）的 ID 自己带 "P0" 前缀，别忘了列进首段：
# 少了它，那 10 条会被当成"没人引用"，而实际上测它们的那批用例一直在跑。
# 尾段允许再带连字符：P0-EXPOSURE-NEUTRAL 这一族的名字里有**两个**连字符，
# 只写一段会把 "P0-EXPOSURE-NEUTRAL" 截成 "P0-EXPOSURE" ——那 10 条会永远显示"没人引用"，
# 而引用它们的测试其实一直在跑（本轮就是这么被骗过一次）。
# 尾段也要能吃下划线：冻结件里白平衡那一族叫 P0-WHITE_BALANCE-NEUTRAL，不带 `_` 的字符
# 类会在下划线处截断（\b 把 `_` 当词字符，所以连 \b 都拦不住）——症状与上面一模一样：
# 测试在跑，报告说没覆盖。
ID_RE = re.compile(r"\b(?:P0|CORE|RENDER|COLOR|PORTRAIT|MANUAL|PRESET|BATCH|TASK|EXPORT|"
                   r"LINUX|PICK|BACKGROUND|GEN|CLOUD|RAW|SEC|DIFF|SCOPE|FORMAT|UI)"
                   r"(?:-[A-Z0-9_]+)+\b")


def disp(p: Path) -> str:
    """给人看的路径：仓内写相对路径，仓外（比如把报告指到 /tmp）写绝对路径。

    `relative_to` 在仓外会抛 ValueError：一个只是打印用的路径不值得让报告工具因为
    产物换了地方就崩在半路（写都写完了，最后一步响一声，人看到的是没产物）。
    """
    try:
        return str(Path(p).relative_to(REPO))
    except ValueError:
        return str(p)


def load_cases() -> list[dict]:
    doc = json.loads(CASES.read_text(encoding="utf-8"))
    return doc["cases"]


def cases_sha256() -> str:
    return hashlib.sha256(CASES.read_text(encoding="utf-8").encode()).hexdigest()[:16]


def test_files() -> list[Path]:
    out: list[Path] = []
    for g in TEST_GLOBS:
        out.extend(sorted(REPO.glob(g)))
    return [f for f in out if f.name != "conftest.py"]


def cite_index() -> dict[str, list[str]]:
    """用例 ID → 引用它的测试节点（`相对路径::函数名`）。

    引用认两处：函数体/文档串里出现该 ID。用 AST 而不是全文 grep，是因为"文件里
    提过一嘴"不算覆盖——只有具体那条测试真的验它才算。
    """
    idx: dict[str, list[str]] = {}
    for f in test_files():
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError as e:
            raise SystemExit(f"× 解析 {f} 失败：{e}")
        rel = f.relative_to(REPO).as_posix()
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not node.name.startswith("test_"):
                continue
            src = ast.get_docstring(node) or ""
            body = ast.get_source_segment(f.read_text(encoding="utf-8"), node) or ""
            for cid in set(ID_RE.findall(src)) | set(ID_RE.findall(body)):
                idx.setdefault(cid, []).append(f"{rel}::{node.name}")
    for v in idx.values():
        v.sort()
    return idx


def collect_nodes(python: str) -> dict[str, list[str]] | None:
    """`pytest --collect-only -q` → **函数名（去参数化后缀）** → 具体节点 id 列表。

    为什么按键聚合而不是直接存全名：`@pytest.mark.parametrize` 的测试在收集结果里是
    `test_foo[cpu-256]` 好几条，而源码引用与映射只能记函数名（引用是写在代码里的
    字面量，它不可能预知参数）。只按全名精确匹配的后果是本轮实测到的三条
    "幽灵映射"假红——节点明明在跑，工具说它不存在。

    放宽只在这一处，而且不是前缀匹配：键必须**去掉 `[...]` 后与函数名逐字符相等**，
    所以改了函数名依旧响成幽灵映射，硬判据没被磨掉。
    """
    try:
        # PYTHONPATH 必须给：不导 lumaretouch_engine 的话整个收集阶段就是 ImportError，
        # 而"收集不到节点"如果被当成"没有幽灵映射"，这条门禁会在最该响的时候闭嘴。
        env = dict(os.environ, PYTHONPATH=str(REPO / "engine" / "src"))
        p = subprocess.run([python, "-m", "pytest", "--collect-only", "-q",
                            *(str(f.relative_to(REPO)) for f in test_files())],
                           cwd=REPO, capture_output=True, text=True, timeout=600, env=env)
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"! 收集失败（不判幽灵映射）：{e}")
        return None
    got: dict[str, list[str]] = {}
    for line in p.stdout.splitlines():
        m = re.match(r"^(\S+\.py)::(\S+)$", line.strip())
        if not m:
            continue
        rel, fn = m.group(1), m.group(2)
        # pytest 打的是相对 **rootdir** 的节点名，而 rootdir 由 engine/pytest.ini 定：
        # 于是收集到的是 `tests/test_x.py::t`，而引用索引给的是 `engine/tests/...`。
        # 不归一就会满屏"幽灵映射"——那是工具的错认，不是映射的错。
        if not (REPO / rel).exists():
            for base in ("engine", "ui"):
                if (REPO / base / rel).exists():
                    rel = f"{base}/{rel}"
                    break
        got.setdefault(f"{rel}::{fn.split('[')[0]}", []).append(f"{rel}::{fn}")
    for v in got.values():
        v.sort()
    if not got:
        print(f"! 收集输出没解析到节点（不判幽灵映射）：{p.stdout[:200]!r}")
    return got or None


def build_map(cases: list[dict], idx: dict[str, list[str]], old_map: dict) -> dict[str, dict]:
    """用例集 + 引用索引 → 映射表（**纯派生**：同一份源码必然得到同一张表）。

    人工补的三格（note/manual/extra）从旧表里继承——它们不是派生物，是评审桌上
    要读的话，以及"这条得人签字"这类自动化伪造不了的边界。
    """
    new: dict[str, dict] = {}
    for c in cases:
        cid = c["id"]
        tests = idx.get(cid, [])
        prev = old_map.get(cid) or {}
        entry = {"tests": tests, "phase": c["phase"], "module": c["module"],
                 "title": c["title"]}
        if prev.get("note"):
            entry["note"] = prev["note"]
        if prev.get("manual"):
            # “这条要人签字”是我们在映射里加的一格，不是冻结件里的字段（冻结件只读）。
            # 没有它，PORTRAIT-002 这种人眼盲评会被自动化那半假装通过——那是报告造假。
            entry["manual"] = prev["manual"]
        if prev.get("extra"):
            entry["extra"] = prev["extra"]      # 人工补的引用（非 ID 字面量，脚本认不出来那种）
            entry["tests"] = sorted(set(tests) | set(prev["extra"]))
        if prev.get("decision"):
            # 产品决定（不支持/范围外/缓期）与 note 一样是人工格：ADR 编号必须
            # 跟着映射走，重算时不能把它丢成 uncovered。
            entry["decision"] = prev["decision"]
        new[cid] = entry
    return new


def write_map(new: dict[str, dict]) -> None:
    MAP.parent.mkdir(parents=True, exist_ok=True)
    MAP.write_text(json.dumps({"schema": "lrt.acceptance-map.v1",
                               "cases": CASES.relative_to(REPO).as_posix(),
                               "cases_sha256": cases_sha256(),
                               "generated_at": time.strftime("%FT%T"),
                               "map": new}, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")


def cmd_map(write: bool, python: str) -> int:
    cases = load_cases()
    idx = cite_index()
    old = json.loads(MAP.read_text(encoding="utf-8")) if MAP.exists() else {}
    new = build_map(cases, idx, old.get("map", {}))
    red = sum(1 for c in cases if c["phase"] == "P0" and not new[c["id"]]["tests"])
    nodes = collect_nodes(python)
    ghosts = []
    if nodes is not None:
        for cid, e in new.items():
            for t in e["tests"]:
                if t not in nodes:
                    ghosts.append(f"{cid} → {t}")
    by_phase = {}
    for c in cases:
        e = new[c["id"]]
        by_phase.setdefault(c["phase"], [0, 0, 0])
        has = bool(e["tests"])
        decided = (not has) and bool((e.get("decision") or {}).get("adr"))
        by_phase[c["phase"]][0] += 1
        by_phase[c["phase"]][1] += 1 if has else 0
        by_phase[c["phase"]][2] += 1 if decided else 0
    for ph in sorted(by_phase):
        tot, cov, dec = by_phase[ph]
        mark = "✓" if cov + dec == tot else "×"
        tail = f"（另 {dec} 条有 ADR 决定）" if dec else ""
        print(f"{mark} {ph}: {cov}/{tot} 条用例有测试引用{tail}")
    if ghosts:
        print(f"× 幽灵映射 {len(ghosts)} 条（映射指向不存在的节点）：")
        for g in ghosts[:10]:
            print(f"    {g}")
    if write:
        write_map(new)
        print(f"✓ 写入 {disp(MAP)}")
    else:
        miss = [c["id"] for c in cases if c["phase"] == "P0" and not new[c["id"]]["tests"]]
        if miss:
            print(f"  P0 缺引用：{miss}")
    return 1 if (red or ghosts) else 0


def read_map() -> dict:
    if not MAP.exists():
        raise SystemExit(f"× 没有 {MAP}：先跑 `tools/run-acceptance.py map --write`")
    doc = json.loads(MAP.read_text(encoding="utf-8"))
    if doc.get("cases_sha256") != cases_sha256():
        raise SystemExit("× 用例集与映射不同源（cases_sha256 对不上）："
                         "重跑 map --write，别拿旧映射对新用例")
    return doc


def sync_map_with_sources(doc: dict, cases: list[dict]) -> list[str]:
    """把报告要用的映射拉齐到当前测试源码，返回发生变动的用例 ID（无变动返回空表）。

    只认 `tests` 集合的差：note/manual/extra 是人工格，build_map 从旧表继承它们，
    重算不会丢。有差就把新表写回 case-map.json——committed 的那份必须与报告同源，
    否则下一轮 `check` 门禁会拿旧表验新源码，红绿就变成了一件时序的事。
    """
    fresh = build_map(cases, cite_index(), doc.get("map", {}))
    old = doc.get("map", {})
    drift = sorted(cid for cid, e in fresh.items()
                   if sorted(e["tests"]) != sorted((old.get(cid) or {}).get("tests", [])))
    if drift:
        print(f"↻ case-map.json 落后于测试源码：本轮按源码刷新 {len(drift)} 条 → {drift[:12]}")
        write_map(fresh)
        doc["map"] = fresh
    else:
        print("· 映射与测试源码同源")
    return drift


def cmd_check(python: str) -> int:
    doc = read_map()
    cases = load_cases()
    idx = cite_index()
    nodes = collect_nodes(python)
    fail = 0
    for c in cases:
        e = doc["map"].get(c["id"])
        dec = (e or {}).get("decision") or {}
        if dec:
            if dec.get("kind") not in DECISION_KINDS or not dec.get("adr"):
                print(f"× {c['id']} 的 decision 缺 kind/adr：{dec}")
                fail += 1
            if (e or {}).get("tests"):
                print(f"× {c['id']} 既有测试引用又有 decision：决定不能盖过读数")
                fail += 1
        if not e or not e["tests"]:
            if c["phase"] == "P0":
                print(f"× P0 {c['id']} 没有测试引用")
                fail += 1
            continue
        if nodes is not None:
            for t in e["tests"]:
                if t not in nodes:
                    print(f"× {c['id']} 指向不存在的节点：{t}")
                    fail += 1
                elif t not in idx.get(c["id"], []) and not (e.get("extra") and t in e["extra"]):
                    print(f"× {c['id']} 的映射与源码引用不符：{t}")
                    fail += 1
    print(f"✓ 映射校验通过（{len(cases)} 条用例）" if not fail else f"× {fail} 项不过")
    return 1 if fail else 0


def parse_junit(path: Path) -> dict[str, list[str]]:
    """junit XML → `文件::测试名` → **状态列表**。只认 pytest 自己写出来的东西。

    XML 不防实体不防外部引用：这份文件只能是本工具自己跑 pytest 生的（产物位置在
    /tmp），但“只认自己生的”这句话得能守住——带 DOCTYPE 的直接拒，不给伪造的
    junit 报告把红说成绿的机会。

    一个键对多条状态是故意的：参数化测试在 junit 里是 `test_foo[cpu-256]`、
    `test_foo[cpu-320]` 好几笔，映射只能记函数名，于是它的状态是**这些笔的集合**。
    聚合规则在 lookup 里，而且往保守那边靠。
    """
    raw = path.read_text(encoding="utf-8", errors="replace")
    if "<!DOCTYPE" in raw or "<!ENTITY" in raw:
        raise SystemExit("× junit XML 里带 DOCTYPE/ENTITY：拒解析（伪造报告的一条路）")
    root = ET.fromstring(raw)
    out: dict[str, list[str]] = {}

    def put(key: str, st: str) -> None:
        out.setdefault(key, []).append(st)

    for tc in root.iter("testcase"):
        f = (tc.get("file") or "").replace("\\", "/")
        if not f:                       # 旧版 pytest 只给 classname（点分模块名）
            cls = (tc.get("classname") or "").split(".")
            f = "/".join(cls[:-1] + [cls[-1] + ".py"]) if cls else ""
        name = tc.get("name", "")
        st = "failed" if (tc.find("failure") is not None or tc.find("error") is not None) \
            else ("skipped" if tc.find("skipped") is not None else "passed")
        base = name.split("[")[0]
        put(f"{f}::{name}", st)
        if base != name:
            put(f"{f}::{base}", st)
        if f:
            tail = f"**{Path(f).name}::{name}"
            put(tail, st)
            if base != name:
                put(f"**{Path(f).name}::{base}", st)
    return out


def lookup(statuses: dict[str, list[str]], node: str) -> str | None:
    """映射里的节点名对 junit 读数：先精确，再按“文件名::测试名”兜一层，多笔时聚合。

    兜不中就算 `unverified` 而不是当通过——rootdir 一变（在打包目录里跑）路径前缀
    就不同，拿不到状态时谎称“绿”是报告的结构性失信。

    聚合往保守靠：任何一笔失败就是失败；没有失败但有跳过就是跳过（skip 不是通过，
    参数化里少跑一档也不能说这条用例全验过了）；全通过才是通过。
    """
    if not statuses:
        return None
    hits = [v for k in (node, f"**{node.split('::')[0].split('/')[-1]}::{node.split('::')[-1]}")
            if (v := statuses.get(k)) is not None]
    if not hits:
        return None
    got = [s for v in hits for s in v]
    if any(s == "failed" for s in got):
        return "failed"
    if any(s == "skipped" for s in got):
        return "skipped"
    return "passed" if got else None


DECISION_KINDS = ("not_supported", "out_of_scope", "deferred")


def case_status(entry: dict, statuses: dict[str, list[str]]) -> str:
    """一条用例的结论：junit 读数优先，其次才是映射里的产品决定。

    `decision` 只允许落在**没有测试引用**的用例上，而且必须带 ADR 编号：
    - 没有 ADR 的“决定”只是空白，仍记 uncovered（不许拿一句话把红刷掉）；
    - 有测试引用时决定不生效——测试说红就是红，决定不能盖过读数。
    三种决定都不计入通过，报告里单独计列。
    """
    tests = entry.get("tests") or []
    if not tests:
        dec = entry.get("decision") or {}
        if dec.get("kind") in DECISION_KINDS and dec.get("adr"):
            return dec["kind"]
        return "uncovered"
    got = [lookup(statuses, t) for t in tests]
    if any(g is None for g in got):
        return "unverified"
    if any(g == "failed" for g in got):
        return "failed"
    if all(g == "passed" for g in got):
        return "passed"
    return "skipped"


def product_version() -> str:
    """报告里得写上它验的是哪一版（验收与定版同源）。

    只读 packaging/VERSION 一处：发布链已经把"版本号多处必须一致"钉成门禁，
    这一处再自己算一份就是第二个会漂的地方。
    """
    p = REPO / "packaging" / "VERSION"
    return p.read_text(encoding="utf-8").strip() if p.is_file() else ""


def overall_verdict(pytest_rc: int, p0_bad: list, p0_manual: list,
                    others: list) -> tuple[bool, str]:
    """P2-9（F18）：从整体读数算一个不能被误读成“可发布”的顶层结论。

    逐条 status=passed 只说“那条映射的测试节点绿”，它盖不住：本轮 pytest 整体红
    （rc≠0）、P0 有红、P0 待人工、非 P0 失败/未证实——这些情冴下行级 passed 会被
    读成发布结论。任一成立就 release_ok=False。
    """
    if pytest_rc != 0:
        return False, (f"⛔ 验收不通过：本轮 pytest 退出码 {pytest_rc}（有红项/跑崩）。"
                       "行级 passed 只说那条映射的测试节点绿，不等于整套可发布。")
    if p0_bad:
        return False, f"⛔ 验收不通过：P0 有 {len(p0_bad)} 条未跑通：{p0_bad[:12]}"
    if p0_manual:
        return False, f"🖐 尚不可发布：P0 有 {len(p0_manual)} 条待人工签署（自动化绿不等于人签过）"
    if others:
        return False, f"⚠ 非 P0 有 {len(others)} 条失败/未证实（pytest rc={pytest_rc}），需人工看"
    return True, "✅ 验收通过：P0 全绿、无待人工、无失败/未证实项——可进入发布流程"


def write_report(doc: dict, cases: list[dict], junit: Path, perf_out: Path,
                 stale: list[str], pytest_rc: int | None, mode: str) -> int:
    """从 junit + 性能 JSON 生成两份报告并打印结论；返回建议退码。

    `pytest_rc` 为 None 表示这份 junit 不是本轮跑的（report-only 重生式），这时
    rc 从 junit 自己的 failure/error 定——能定"有没有红"，定不出"跑崩在收集阶段"
    那一类，所以 mode 一并写进报告，不留"看着像重跑过"的余地。
    """
    statuses = parse_junit(junit)
    if pytest_rc is None:
        pytest_rc = 1 if any("failed" in v for v in statuses.values()) else 0
    perf = json.loads(perf_out.read_text(encoding="utf-8")) if perf_out.exists() else None
    if perf is None:
        print("! 没给/没有性能 JSON：报告里性能那一节写『本轮未量』，不编数")

    rows, counters = [], {}
    for c in cases:
        e = doc["map"].get(c["id"]) or {}
        tests = e.get("tests") or []
        st = case_status(e, statuses)
        if e.get("manual") and st == "passed":
            # 自动化那半绿了不等于这条过了：`manual` 标的是“还必须由人签字的那一半”。
            st = "manual_pending"
        counters.setdefault(c["phase"], {})
        counters[c["phase"]][st] = counters[c["phase"]].get(st, 0) + 1
        rows.append({"id": c["id"], "phase": c["phase"], "module": c["module"],
                     "title": c["title"], "status": st,
                     "then": c["then"], "tests": tests, "note": e.get("note"),
                     "decision": e.get("decision")})
    # P2-9（F18）：逐条 status 只说“那条映射的测试节点绿没绿”，它盖不住两个坑：
    # ① 本轮 pytest 整体红（rc≠0）时，行级 passed 会被读成“可发布”；② P0 待人工、
    # 非 P0 失败/未证实也会在一堆绿勾里隐身。所以额外算一个顶层总体结论：
    # 只要 rc≠0、或 P0 有红、或有待人工、或有非 P0 未决项，release_ok 就是 False。
    p0_bad = [r["id"] for r in rows if r["phase"] == "P0" and r["status"] not in ("passed", "manual_pending")]
    p0_manual = [r["id"] for r in rows if r["phase"] == "P0" and r["status"] == "manual_pending"]
    others = [r for r in rows if r["phase"] != "P0" and r["status"] in ("failed", "unverified")]
    release_ok, conclusion = overall_verdict(pytest_rc, p0_bad, p0_manual, others)
    report = {"schema": "lrt.acceptance-report.v1", "at": time.strftime("%FT%T"),
              "product_version": product_version(), "mode": mode,
              "cases_sha256": cases_sha256(), "pytest_rc": pytest_rc,
              "release_ok": release_ok, "conclusion": conclusion,
              "map_refreshed": stale,
              "counts": counters, "rows": rows,
              "perf": perf, "junit": str(junit)}
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n",
                           encoding="utf-8")
    write_md(report)
    print(f"报告（{mode}）：{disp(REPORT_JSON)} / {disp(REPORT_MD)}")
    for ph in sorted(counters):
        print(f"  {ph}: " + " ".join(f"{k}={v}" for k, v in sorted(counters[ph].items())))
    if p0_bad:
        print(f"× P0 未跑通 {len(p0_bad)} 条：{p0_bad}")
        return 1
    # 上一版这里写的是 `return 0 if rc == 0 else 0`——两个分支同一个值，等于把 pytest 的
    # 退出码当场勾销：非 P0 炸了报告也是一片绿，那是报告的结构性失信。现在 P0 全绿
    # 而仍有其他用例失败时，把数量报出来并回退码 2（红是 P0 定的，2 是“要人看”）。
    print("✓ P0 没有红项")
    if p0_manual:
        # 自动化那半过了不等于这条过了：人没签字就不能替人签。退码 3 就是专门给
        # “只差人工”这个状态留的（与“有红项”的 1 分开，不让它摸进绿）。
        print(f"🖐 P0 待人工 {len(p0_manual)} 条（不算通过）：{p0_manual}")
    dec_rows = [r for r in rows if r["status"] in DECISION_KINDS]
    if dec_rows:
        by: dict[str, int] = {}
        for r in dec_rows:
            by[r["status"]] = by.get(r["status"], 0) + 1
        print("· 决策项（有 ADR、不计入通过）："
              + " ".join(f"{k}={v}" for k, v in sorted(by.items())))
    if others or pytest_rc != 0:
        print(f"! 非 P0 待看 {len(others)} 条（pytest rc={pytest_rc}）："
              f"{[r['id'] for r in others][:12]}")
        return 2
    return 3 if p0_manual else 0


def cmd_run(args) -> int:
    doc = read_map()
    cases = load_cases()
    # 映射是从测试源码解析出来的**派生物**，而 case-map.json 是一份 committed 文件：
    # 派生物落后于源码就是本轮实测到的事故形状——接局部调色那一笔编辑顺手删掉两行
    # 「验收用例引用」注释，重跑 junit 全绿而报告报 "P0 未跑通 2 条"。假红不只是难看：
    # 它把真红混进一堆假红里，而 7 分钟的重跑会让人开始怀疑工具而不是怀疑代码。
    # 所以这一遍先按源码重算；不一致就当场刷新（写回文件，让 `check` 门禁与报告同源），
    # 并把变动条目报出来——落后必须是喊出来的事实，不能悄悄吞掉或悄悄改写。
    stale = sync_map_with_sources(doc, cases)
    junit = Path(args.junit)
    cmd = [args.python, "-m", "pytest", "-q", "--no-header",
           f"--junit-xml={junit}", *(args.extra or [])]
    env = dict(os.environ, PYTHONPATH=str(REPO / "engine" / "src"))
    # 性能那一臂必须由这一遍真跑：CORE-002（秒开）、RENDER-001（不断帧）、
    # PORTRAIT-001、EXPORT-002 的**唯一证据**就是 test_perf_report 那几条，而它
    # 不设 LRT_PERF_OUT 就整模块 skip——上一轮就是这个形状红着四条 P0：“没量”
    # 不等于“量过且没问题”。报告里的性能段拿的就是这一遍写出的那一份。
    perf_out = Path(args.perf) if args.perf else Path("/tmp/lrt-perf.json")
    env.setdefault("LRT_PERF_OUT", str(perf_out))
    if not env.get("LRT_PERF_DNG"):
        for cand in ("/tmp/lrt-perf-dng.dng",
                     str(REPO / "engine" / "tests" / "fixtures" / "perf-3000.dng")):
            if Path(cand).is_file():
                env["LRT_PERF_DNG"] = cand
                break
    dng_note = (f"RAW 臂用 {env['LRT_PERF_DNG']}" if env.get("LRT_PERF_DNG")
                else "没有 LRT_PERF_DNG：RAW/秒开 DNG 那一档本轮不收（报告里会写“没量”）")
    print(f"· 性能读数→{env['LRT_PERF_OUT']}（{dng_note}）")
    print("$ " + " ".join(cmd))
    t0 = time.monotonic()
    rc = subprocess.call(cmd, cwd=REPO, env=env)
    print(f"pytest 退出码 {rc}（{time.monotonic() - t0:.1f}s）")
    if not junit.exists():
        print("× 没有 junit XML：报告不生成（没有证据就不写结论）")
        return 1
    return write_report(doc, cases, junit, perf_out, stale, rc, "run（这一遍重跑了 pytest）")


def cmd_report(args) -> int:
    """拿已有的 junit XML 重生成报告（不重跑测试）。

    为什么要有这一子命令：报告版式/元数据（比如这一轮要加的 product_version）改一下
    就要付 7 分钟的全量重跑，而性能分位数只有在机器相对空闲时量出来才算数——为了
    一行文案去重跑一整遍，代价是拿一份被构建任务污染的新读数换掉刚量好的那一份。
    所以重生成与重跑分开，而 mode 字段把两者区分写进报告：复用旧 junit 时不许假装本轮重跑过。
    """
    doc = read_map()
    cases = load_cases()
    stale = sync_map_with_sources(doc, cases)
    junit = Path(args.junit)
    if not junit.exists():
        print(f"× junit XML 不存在：{junit}（report-only 不跑测试，没证据就不写结论）")
        return 1
    perf_out = Path(args.perf) if args.perf else Path("/tmp/lrt-perf.json")
    print(f"· 复用 junit {junit}（本轮没重跑 pytest）、性能读数 {perf_out}")
    return write_report(doc, cases, junit, perf_out, stale, None,
                        "report-only（复用已有 junit XML，本轮没重跑测试）")


PH_STATE = {"passed": "✅ 通过", "failed": "❌ 失败", "skipped": "⚠️ 跳过",
            "unverified": "⚠️ 未证实", "uncovered": "🔴 未覆盖",
            "manual_pending": "🖐 待人工",
            "not_supported": "⛔ 不支持（有依据）",
            "out_of_scope": "➖ 范围外",
            "deferred": "⏸ 缓期（有退出条件）"}


def write_md(rep: dict) -> None:
    L = ["# LumaRetouch 验收报告", "",
         f"- 生成时间：{rep['at']}",
         f"- 产品版本：`{rep.get('product_version') or '（没读到 packaging/VERSION）'}`",
         f"- 结论来源：{rep.get('mode') or '（未标注）'}"
         f"（junit：{rep['junit']}）",
         f"- 用例集指纹：`{rep['cases_sha256']}`（《开发验收用例.json》冻结件）",
         f"- pytest 退出码：{rep['pytest_rc']}", ""]
    # P2-9（F18）：把一个不能误读的总体结论放在最前面——行级 passed 不等于可发布。
    L += [f"## 验收结论", "",
          f"- **{rep.get('conclusion') or '（旧报告无此字段）'}**",
          f"- 发布门禁 `release_ok`：{'✅ 通过' if rep.get('release_ok') else '⛔ 未通过'}"
          "（逐条 passed 只表示该条映射的测试节点绿；pytest_rc≠0、P0 有红、待人工"
          "、非 P0 失败/未证实任一成立即不得当发布结论）", ""]
    L += ["## 汇总", "",
          "| 阶段 | 通过 | 待人工 | 不支持 | 范围外 | 缓期 | 失败 | 跳过 | 未证实 | 未覆盖 |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for ph in sorted(rep["counts"]):
        c = rep["counts"][ph]
        L.append(f"| {ph} | {c.get('passed', 0)} | {c.get('manual_pending', 0)} | "
                 f"{c.get('not_supported', 0)} | {c.get('out_of_scope', 0)} | "
                 f"{c.get('deferred', 0)} | "
                 f"{c.get('failed', 0)} | "
                 f"{c.get('skipped', 0)} | {c.get('unverified', 0)} | {c.get('uncovered', 0)} |")
    L += ["", "## 逐条用例", ""]
    cur = None
    for r in rep["rows"]:
        if r["phase"] != cur:
            cur = r["phase"]
            L += [f"### {cur}", "", "| 用例 | 标题 | 状态 | 证据（测试节点） |", "|---|---|---|---|"]
        ev = "<br>".join(f"`{t}`" for t in r["tests"]) or "—"
        if r["status"] in DECISION_KINDS and r.get("decision"):
            ev = f"决策：{r['decision'].get('adr')}"
        L.append(f"| {r['id']} | {r['title']} | {PH_STATE.get(r['status'], r['status'])} | {ev} |")
        if r.get("note"):
            L.append(f"| | ↳ 备注 | | {r['note']} |")
    L += ["", "## 真实性能分位数", ""]
    perf = rep.get("perf")
    if not perf:
        L += ["本轮未量（没给性能 JSON）。缺数就写缺数，不拿旧数或估计填表。", ""]
    else:
        env = perf.get("env", {})
        rt = env.get("runtime", {})
        L += [f"- 设备：`{env.get('device')}`（cuda={env.get('cuda')}），"
              f"预热 {env.get('warm_ms')} ms；引擎 {env.get('engine_version')}，"
              f"python {rt.get('python')}，torch {rt.get('torch')}",
              f"- 形状：代理档 `{perf.get('proxy_max_px')}`，"
              f"样本数 {perf.get('samples')}", ""]
        m = perf.get("metrics", {})
        L += ["| 指标 | n | p50 | p95 | p99 | max |", "|---|---|---|---|---|---|"]

        def row(name: str, key: str) -> None:
            b = m.get(key)
            if isinstance(b, dict) and "p50" in b:
                L.append(f"| {name} | {b['n']} | {b['p50']} | {b['p95']} | {b['p99']} | {b['max']} |")
        row("拖拽逐帧渲染 ms", "drag_render_ms")
        row("缩略图逐张 ms", "thumbnail_ms")
        row("面部重塑应用 ms", "deform_apply_ms")
        row("导出逐张 ms", "export_per_image_ms")
        L.append(f"\n- 拖拽期滤波缓存命中：{m.get('drag_filter_cached_ratio')}")
        L.append(f"- 首次建层 total_ms：{m.get('deform_build_ms')}；拖动期重建次数："
                 f"{m.get('deform_builds_during_drag')}")
        L.append(f"- 批次导出墙钟：{m.get('export_total_ms')} ms（tile {m.get('export_tile')}，"
                 f"失败 {m.get('export_failed')}，进度事件 {m.get('export_progress_events')} 条）")
        shape = m.get("shape") or {}
        L.append(f"- 导入（JPEG {shape.get('source')}→代理 {shape.get('proxy')}）："
                 f"{json.dumps(m.get('import_jpg'), ensure_ascii=False)}")
        if "import_dng" in m:
            ds = (m.get("import_dng") or {}).get("shape") or {}
            L.append(f"- 导入（DNG {ds.get('source')}→代理 {ds.get('proxy')}）："
                     f"{json.dumps(m.get('import_dng'), ensure_ascii=False)}")
            L.append(f"- 导入（DNG 第二次，稳态）：{json.dumps(m.get('import_dng_second'), ensure_ascii=False)}")
        for n in perf.get("notes", []):
            L.append(f"- 注：{n}")
    L += ["", "## 判据说明", "",
          "- 状态只来自 junit XML（pytest 亲口说的），不来自任何自报文本；",
          "- P0 用例 `skipped/unverified/uncovered` 都不算通过——没跑过就是没跑过；",
          "- `manual_pending`（待人工）是**映射里标的“这一半要人签字”**：自动化读数全绿也不算通过，"
          "报告里单独颜色列出来（PORTRAIT-002 的盲评规程见 docs/acceptance/）；",
          "- `not_supported/out_of_scope/deferred` 是映射里带 ADR 的产品决定：单独计列、"
          "不计入通过；没有 ADR 的空白仍算 `uncovered`，不许用一句话把红刷掉；"
          "有测试引用时决定不生效（读数说话）；",
          "- 每条用例的证据必须是一段真存在的测试节点，测试里逐条引用用例 ID，"
          "改名不更新引用会在 `check` 里响成幽灵映射。", ""]
    REPORT_MD.write_text("\n".join(L), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="op", required=True)
    m = sub.add_parser("map", help="从测试源码解析用例 ID 引用，生成/更新 case-map.json")
    m.add_argument("--write", action="store_true")
    m.add_argument("--python", default=DEFAULT_PY, help="用来 --collect-only 的解释器（要有 pytest）")
    c2 = sub.add_parser("check", help="只校验映射（P0 必须有引用、不得有幽灵映射）")
    c2.add_argument("--python", default=DEFAULT_PY, help="用来 --collect-only 的解释器（要有 pytest）")
    r = sub.add_parser("run", help="跑测试并出验收报告")
    r.add_argument("--python", default=DEFAULT_PY,
                   help="跑测试的解释器（默认运行时 venv：产品口径的协议/性能用例要 torch，"
                        "开发 venv 里那批会整片 skip，而 skip 不是通过）")
    r.add_argument("--junit", default="/tmp/lrt-acceptance-junit.xml")
    r.add_argument("--perf", default=os.environ.get("LRT_PERF_OUT", "/tmp/lrt-perf.json"))
    r.add_argument("extra", nargs="*", help="传给 pytest 的额外参数")
    # report-only：复用已有 junit 重生成报告。报告版式改了不再逼人为了一行文案重跑 7 分钟
    # （那一遍会把性能那一节换成在非空闲机器上量出来的数）。
    rp = sub.add_parser("report", help="只从已有 junit XML 重生成报告（不跑测试）")
    rp.add_argument("--junit", default="/tmp/lrt-acceptance-junit.xml")
    rp.add_argument("--perf", default=os.environ.get("LRT_PERF_OUT", "/tmp/lrt-perf.json"))
    a = ap.parse_args()
    if a.op == "map":
        return cmd_map(a.write, a.python)
    if a.op == "check":
        return cmd_check(a.python)
    if a.op == "report":
        return cmd_report(a)
    return cmd_run(a)


if __name__ == "__main__":
    sys.exit(main())
