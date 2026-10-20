"""P2-9（F18）：验收报告的顶层结论不能被行级 passed 冒充成"可发布"。

缺陷：run-acceptance.py 里每条用例的 status 只看"那条映射的测试节点在 junit 里绿没绿"，
没有一个是能挡住误读的顶层结论——本轮 pytest 整体红（rc≠0）、P0 有红、P0 待人工、非 P0
失败/未证实，都会在一堆 passed 里被读成发布结论（报告出现 passed 也支持不了发布）。

这里 import 那个 dash 命名的脚本，纯函数 overall_verdict 直接判：任一未决条件成立就
release_ok=False；只有干净全绿才 True。纯 CPU、不碰 junit/文件写。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[2] / "tools" / "run-acceptance.py"
_spec = importlib.util.spec_from_file_location("run_acceptance", TOOL)
ra = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ra)


@pytest.mark.parametrize("rc,p0_bad,p0_manual,others,expect_ok", [
    (0, [], [], [], True),                       # 全绿 → 可发布
    (1, [], [], [], False),                      # 本轮跑崩/有红 → 阻断（F18 核心）
    (0, ["CORE-001"], [], [], False),            # P0 有红 → 阻断
    (0, [], ["PORTRAIT-002"], [], False),        # P0 待人工 → 不等同通过
    (0, [], [], [{"id": "GEN-001"}], False),     # 非 P0 失败/未证实 → 要人看
    (5, ["X"], ["Y"], [{"id": "Z"}], False),     # rc 优先级最高
])
def test_overall_verdict_blocks_when_not_clean(rc, p0_bad, p0_manual, others, expect_ok):
    ok, text = ra.overall_verdict(rc, p0_bad, p0_manual, others)
    assert ok is expect_ok
    assert isinstance(text, str) and text
    # 非通过态绝不允许出现"可进入发布流程"这句
    if not expect_ok:
        assert "可进入发布流程" not in text


def test_pass_conclusion_is_unambiguous():
    ok, text = ra.overall_verdict(0, [], [], [])
    assert ok and text.startswith("✅")


def test_rc_nonzero_dominates_even_if_rows_all_pass():
    """即使映射里没有任何红行，rc≠0 也必须压住"可发布"——F18 点名的正是这一形。"""
    ok, text = ra.overall_verdict(1, [], [], [])
    assert ok is False
    assert "退出码" in text
