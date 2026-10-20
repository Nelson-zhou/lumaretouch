"""验收执行器自己的测试：`tools/run-acceptance.py` 里那套映射与状态判定。

为什么这条也得有测试（本轮实证的事故）：COLOR-004 接引擎时，一次 SearchReplace
顺手删掉了两行「验收用例引用：…」注释——那是映射的唯一来源。跑全量 818 passed
一片绿，而验收报告说 "P0 未跑通 2 条"。原因不在产品代码，在**工具自己**：
case-map.json 是一份 committed 的派生物，派生物落后于源码时报告会编出假红。
假红的代价不是难看，是把真红埋进一堆假红里，从此人开始怀疑报告而不是怀疑代码。

所以这里验四件事：① 跑测试前把映射拉齐到源码（并写回，门禁与报告同源）；
② 落后必须被报出来而不是悄悄吞掉；③ 只有写在**测试函数体内**的引用才算覆盖；
④ junit 状态聚合往保守靠（任何一笔失败=失败，有跳过=跳过，skip 不是通过）。

用例 ID 一律用 9000 段（CORE-9001 这种）：冻结件里没有这些 ID，`cite_index()`
扫到也不会进映射表。写真实 ID 的话，这个文件会把自己变成那条真实用例的"证据"，
而它验的是工具不是产品——那正是这个仓最不能出现的假证据形状。
"""
from __future__ import annotations

import ast
import importlib.util
import json
import pathlib
import re

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_TOOL_PATH = _REPO_ROOT / "tools" / "run-acceptance.py"


@pytest.fixture(scope="module")
def tool():
    """按路径加载执行器（文件名带连字符，不能 import）。"""
    spec = importlib.util.spec_from_file_location("lrt_run_acceptance", _TOOL_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _pick_covered_p0(tool) -> tuple[str, list[str]]:
    """从真实源码里取一条**确有引用**的 P0 用例（不写死 ID，避免本文件成为它的假证据）。"""
    idx = tool.cite_index()
    for c in tool.load_cases():
        if c["phase"] == "P0" and idx.get(c["id"]):
            return c["id"], list(idx[c["id"]])
    pytest.fail("测试源码里找不到任何有引用的 P0 用例——映射整条链子都是空的")


def test_run_refreshes_a_stale_map_before_writing_the_report(tool, tmp_path, monkeypatch):
    """映射少了引用时，`run` 必须先按源码刷新，而不是拿着旧表报一条假红。"""
    cases = tool.load_cases()
    good = tool.build_map(cases, tool.cite_index(), {})
    cid, nodes = _pick_covered_p0(tool)
    stale = json.loads(json.dumps(good))
    stale[cid]["tests"] = []                      # 事故形状：引用注释被编辑删掉

    map_path = tmp_path / "case-map.json"
    monkeypatch.setattr(tool, "MAP", map_path)
    map_path.write_text(json.dumps({"schema": "lrt.acceptance-map.v1",
                                    "cases_sha256": tool.cases_sha256(),
                                    "map": stale}, ensure_ascii=False), encoding="utf-8")
    doc = {"map": stale}

    drift = tool.sync_map_with_sources(doc, cases)
    assert drift == [cid], f"只该报这一条落后，实际：{drift}"
    # 刷新后的 doc 与磁盘上的文件必须同源——`check` 门禁读的是文件，报告读的是 doc，
    # 两者分家的话下一次门禁会拿着旧表验新源码。
    assert doc["map"][cid]["tests"] == nodes
    on_disk = json.loads(map_path.read_text(encoding="utf-8"))["map"][cid]["tests"]
    assert on_disk == nodes
    # 幂等：同源之后不该再有第二次刷新（不然每轮都写一遍文件，diff 里全是噪声）
    assert tool.sync_map_with_sources(doc, cases) == []


def test_human_fields_survive_a_refresh(tool):
    """note/manual/extra 是人工格，重算映射不能把它们抹掉。

    丢了 `manual` 的后果最重：那种"要人眼盲评"的用例会立刻从
    manual_pending 变成 passed——那是报告造假，不是刷新。
    """
    cases = tool.load_cases()
    cid, nodes = _pick_covered_p0(tool)
    old = {cid: {"tests": [], "note": "人写的一句话", "manual": "要人签字",
                 "decision": {"kind": "not_supported", "adr": "ADR-9000"},
                 "extra": ["engine/tests/test_fake.py::test_extra"]}}
    built = tool.build_map(cases, tool.cite_index(), old)
    assert built[cid]["note"] == "人写的一句话"
    assert built[cid]["manual"] == "要人签字"
    assert built[cid]["extra"] == ["engine/tests/test_fake.py::test_extra"]
    assert built[cid]["decision"] == {"kind": "not_supported", "adr": "ADR-9000"}
    assert built[cid]["tests"] == sorted(set(nodes) | {"engine/tests/test_fake.py::test_extra"})


def test_decision_status_requires_an_adr_and_never_overrides_tests(tool):
    """产品决定只对“没有测试引用”的用例生效，而且必须带 ADR。

    这是本次“平账”的门：没有 ADR 的一句话不能把红刷成“支持/范围外”；
    一旦某条用例后来有了测试引用，决定立刻失效——读数说话，决定不能盖过读数。
    """
    no_tests = {"tests": []}
    assert tool.case_status(
        {**no_tests, "decision": {"kind": "not_supported", "adr": "ADR-9000"}}, {}
    ) == "not_supported"
    assert tool.case_status(
        {**no_tests, "decision": {"kind": "deferred"}}, {}
    ) == "uncovered", "没有 ADR 的决定不算数"
    assert tool.case_status(
        {**no_tests, "decision": {"kind": "passed", "adr": "ADR-9000"}}, {}
    ) == "uncovered", "决定只有三种合法 kind，不能拿 passed 冒充"
    st = {"engine/tests/test_fake.py::test_a": ["passed"]}
    assert tool.case_status(
        {"tests": ["engine/tests/test_fake.py::test_a"],
         "decision": {"kind": "deferred", "adr": "ADR-9000"}}, st
    ) == "passed", "有测试引用时决定必须失效"
    st["engine/tests/test_fake.py::test_a"] = ["failed"]
    assert tool.case_status(
        {"tests": ["engine/tests/test_fake.py::test_a"]}, st
    ) == "failed"


def test_committed_map_is_derived_from_the_current_sources(tool):
    """committed 的 case-map.json 必须等于当前源码的派生结果——这一条就是那起事故的守卫。

    它比 `check` 更严：`check` 只保证 P0 有引用、节点存在，而"某条用例新加了引用却没
    重跑 map --write"在它眼里是合法的。这一条把方向反过来钉死：**双向**同源，
    少一条和多一条都响。
    """
    doc = json.loads(tool.MAP.read_text(encoding="utf-8"))
    assert doc["cases_sha256"] == tool.cases_sha256(), "映射与冻结用例集不同源：重跑 map --write"
    derived = tool.build_map(tool.load_cases(), tool.cite_index(), doc["map"])
    drift = sorted(cid for cid, e in derived.items()
                   if sorted(e["tests"]) != sorted((doc["map"].get(cid) or {}).get("tests", [])))
    assert drift == [], f"case-map.json 落后于测试源码：{drift}（跑 tools/run-acceptance.py map --write）"


def test_only_citations_inside_a_test_function_count(tool, tmp_path, monkeypatch):
    """模块级注释不算覆盖：只有引用落在具体那条测试函数体内，才认为那条用例被验过。

    `cite_index()` 用 AST 而不是全文 grep，靠的就是这个边界。写宽了（整文件算），
    一句"顺手提过一嘴"的注释就能把红用例说成绿——那是最容易伪造的一层证据。
    """
    d = tmp_path / "engine" / "tests"
    d.mkdir(parents=True)
    (d / "test_fake.py").write_text(
        "# 验收用例引用：CORE-9001（模块级提过一嘴，不算）\n"
        "def test_module_level_comment_does_not_count():\n"
        "    assert True\n\n"
        "def test_cited_inside_body():\n"
        "    # 验收用例引用：CORE-9002\n"
        "    assert True\n",
        encoding="utf-8")
    monkeypatch.setattr(tool, "REPO", tmp_path)
    idx = tool.cite_index()
    assert "CORE-9001" not in idx, "模块级注释被当成了覆盖——引用边界被写宽了"
    assert idx["CORE-9002"] == ["engine/tests/test_fake.py::test_cited_inside_body"]


def test_this_file_cites_no_real_case_id(tool):
    """本文件验的是工具，不是产品——它不许成为任何真实用例的"证据"。

    这条不是洁癖，是本文件自己刚犯过的错：写这份测试时 docstring 里提了一嘴某条
    真实用例的 ID，`map --write` 立刻把这个文件加进那条用例的证据链——一句解释性
    引用伪造出了一条不存在的覆盖。`cite_index()` 只看字面量落在函数体内与否，它
    分不出"我在验这条用例"和"我在举这条用例当例子"，所以这道边界只能由测试自己钉。
    """
    real = {c["id"] for c in tool.load_cases()}
    here = pathlib.Path(__file__)
    src = here.read_text(encoding="utf-8")
    hit: list[str] = []
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for i in set(tool.ID_RE.findall(ast.get_source_segment(src, node) or "")):
                if i in real:
                    hit.append(f"{node.name} → {i}")
    assert hit == [], f"本文件的函数体内出现了真实用例 ID（会被当成覆盖）：{hit}"


def test_junit_status_aggregation_is_conservative(tool, tmp_path):
    """参数化几笔聚合成一个状态：任何一笔失败=失败，有跳过=跳过，全通过才通过。"""
    xml = """<testsuites><testsuite name="p" tests="4">
<testcase file="engine/tests/test_fake.py" classname="t" name="test_a[cpu-256]" time="0.1"/>
<testcase file="engine/tests/test_fake.py" classname="t" name="test_a[cpu-320]" time="0.1"><failure message="炸">炸</failure></testcase>
<testcase file="engine/tests/test_fake.py" classname="t" name="test_b[cpu-256]" time="0.1"/>
<testcase file="engine/tests/test_fake.py" classname="t" name="test_b[cpu-320]" time="0.1"><skipped message="没装"/></testcase>
<testcase file="engine/tests/test_fake.py" classname="t" name="test_c" time="0.1"/>
</testsuite></testsuites>
"""
    p = tmp_path / "j.xml"
    p.write_text(xml, encoding="utf-8")
    st = tool.parse_junit(p)
    base = "engine/tests/test_fake.py::"
    assert tool.lookup(st, base + "test_a") == "failed"
    assert tool.lookup(st, base + "test_b") == "skipped"   # skip 不是通过
    assert tool.lookup(st, base + "test_c") == "passed"
    assert tool.lookup(st, base + "test_not_collected") is None   # 拿不到状态就是 unverified


def test_write_report_keeps_the_product_version_and_the_run_mode(tool, tmp_path, monkeypatch):
    """报告得写上它验的是哪一版，还得写上这一版是怎么来的（重跑 / 复用 junit）。

    `report-only` 那一档不许伪装成本轮重跑：复用旧 junit 时 pytest 的真实退码拿不到，
    只能从 junit 里的 failure/error 定“有没有红”。不把这个区分写进报告，一份半年前
    的 junit 就能伪装成今天验过的结论。
    """
    cases = [{"id": "CORE-9003", "phase": "P0", "module": "core", "title": "假",
              "then": ["假"]},
             {"id": "CORE-9004", "phase": "P0", "module": "core", "title": "假红",
              "then": ["假"]}]
    mp = {"CORE-9003": {"tests": ["engine/tests/test_fake.py::test_green"]},
          "CORE-9004": {"tests": ["engine/tests/test_fake.py::test_red"]}}
    good = tmp_path / "g.xml"
    good.write_text('<testsuites><testsuite name="p" tests="2">'
                    '<testcase file="engine/tests/test_fake.py" classname="t" name="test_green"/>'
                    '<testcase file="engine/tests/test_fake.py" classname="t" name="test_red"/>'
                    '</testsuite></testsuites>', encoding="utf-8")
    bad = tmp_path / "b.xml"
    bad.write_text('<testsuites><testsuite name="p" tests="2">'
                   '<testcase file="engine/tests/test_fake.py" classname="t" name="test_green"/>'
                   '<testcase file="engine/tests/test_fake.py" classname="t" name="test_red">'
                   '<failure message="x">x</failure></testcase>'
                   '</testsuite></testsuites>', encoding="utf-8")
    perf = tmp_path / "perf.json"
    perf.write_text(json.dumps({"schema": "lrt.acceptance-perf.v1", "at": "x",
                                "samples": 1, "metrics": {}, "notes": []}), encoding="utf-8")
    monkeypatch.setattr(tool, "REPORT_JSON", tmp_path / "报告.json")
    monkeypatch.setattr(tool, "REPORT_MD", tmp_path / "报告.md")
    mode = "report-only（复用已有 junit XML，本轮没重跑测试）"

    assert tool.write_report({"map": mp}, cases, good, perf, [], None, mode) == 0
    rep = json.loads((tmp_path / "报告.json").read_text(encoding="utf-8"))
    assert rep["product_version"] == (_REPO_ROOT / "packaging" / "VERSION").read_text(
        encoding="utf-8").strip()
    assert rep["mode"] == mode and rep["pytest_rc"] == 0
    # 同一份映射、一份红：必须报成 1，而且 md 里要能看见那条红
    assert tool.write_report({"map": mp}, cases, bad, perf, [], None, mode) == 1
    assert "❌" in (tmp_path / "报告.md").read_text(encoding="utf-8")


def test_parse_junit_refuses_doctype(tool, tmp_path):
    """junit 里带 DOCTYPE/ENTITY 直接拒：不给伪造的报告把红说成绿留一条路。"""
    p = tmp_path / "evil.xml"
    p.write_text('<!DOCTYPE x [<!ENTITY y "passed">]><testsuites/>', encoding="utf-8")
    with pytest.raises(SystemExit):
        tool.parse_junit(p)


def test_release_scripts_do_not_hardcode_an_amounts_literal():
    """定版脚本不许拿"整份形变字典字面量"做等式比较（1.7.0 定版那一记假红的产物）。

    当时 m5-release-check.sh 层级那一臂写死了 `== {"slim_face": 0.2, "big_eye": 0.9,
    "small_chin": 0.0}`。引擎 KINDS 新增 smile 之后，逐 kind 合成出来的字典自然多一格，
    于是"期望落后于改动"被报成产品缺陷、VERDICT=FAIL。假红比缺判据贵：它教会人跳过红。

    正确的形状是把两半分开判：这一臂显式设过的那几格逐格等于设计值，而它没碰过的格
    必须全为 0。所以这里禁的是形状，不是判据强度。
    """
    pat = re.compile(r'(?:==|!=)\s*\{[^{}]*"?slim_face"?[^{}]*\}'
                     r'|\{[^{}]*"?slim_face"?[^{}]*\}\s*(?:==|!=)')
    hits = []
    for path in sorted([*(_REPO_ROOT / "packaging").glob("*.sh"),
                        *(_REPO_ROOT / "tools").glob("*.py")]):
        text = path.read_text(encoding="utf-8", errors="replace")
        for m in pat.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            hits.append(f"{path.name}:{line}")
    assert not hits, ("定版脚本里写死了形变字典字面量等式：新增一格就会报假红，"
                      f"改成逐格判（显式设过的等于设计值、没设过的必须为 0）：{hits}")
