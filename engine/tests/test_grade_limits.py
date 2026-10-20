"""P2-3：肤色定向滑杆选的量程必须与后端 check_params 的有效带对齐。

UI 侧（ui/src/gradeLimits.ts + node:test）已钉住"滑杆量程来自引擎报的 grade_limits、
整数上限 dh=5/ds=dv=60（×100）"。这一条从后端一侧把契约焊死：这些换算回原生浮点的值
必须真被 check_params 接受，而旧滑杆的 ±100（=±1.0）必须被拒——否则"界面给的值后端收不收"
这句话就没有一手证据。纯 CPU：只 import ops.grade（不拉 torch/GPU）。
"""
from __future__ import annotations

import pytest

from lumaretouch_engine.ops.grade import (
    DH_LIMIT, DS_LIMIT, DV_LIMIT, GradeError, check_params,
)


def test_reported_limits_match_constants():
    """引擎报出去的 grade_limits 就是这三个常量（UI 拿它们当上限的依据成立）。"""
    assert (DH_LIMIT, DS_LIMIT, DV_LIMIT) == (0.05, 0.60, 0.60)


def test_check_params_accepts_the_new_ui_bounds():
    """新滑杆整数上限换算回后端：dh=5→0.05、ds/dv=60→0.60，必须正好落在有效带内。"""
    # 不抛就是接受；抛了会带 GradeError 栈
    dh, ds, dv, amount = check_params(5 / 100, 60 / 100, 60 / 100, amount=100 / 100)
    assert dh == pytest.approx(0.05) and ds == pytest.approx(0.60) and dv == pytest.approx(0.60)


def test_check_params_rejects_just_beyond_the_limit():
    """越过上限一档就必须拒——UI 若把上限再放宽半点，后端会拦下。"""
    with pytest.raises(GradeError):
        check_params(DH_LIMIT + 1e-3, 0.0, 0.0)
    with pytest.raises(GradeError):
        check_params(0.0, DS_LIMIT + 1e-3, 0.0)
    with pytest.raises(GradeError):
        check_params(0.0, 0.0, DV_LIMIT + 1e-3)


def test_check_params_rejects_the_old_ui_extremes():
    """旧滑杆 min=-100 max=100 发 v/100 → 能到 ±1.0，全落在有效带之外：这是 P2-3 的现场。"""
    with pytest.raises(GradeError):
        check_params(1.0, 0.0, 0.0)      # 旧 dh 上限
    with pytest.raises(GradeError):
        check_params(0.0, 1.0, 0.0)      # 旧 ds 上限（> 0.60）
