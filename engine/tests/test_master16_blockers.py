"""P1-5：16-bit 母档直通 blockers 的覆盖完整性。

直通这一路只走「16-bit 解码 → 原样写 TIFF」，图层不进。所以任何**会改像素**的编辑
都必须挡在门外。上一版只拦到 sharpen 为止，曝光/白平衡/影调、八色 HSL、眼/牙增强、
换底、局部调色作用域 五条漏网——用户拉了 EV 却拿到一张「bits=16 readback_max_diff=0
source=libraw」的 TIFF，画面里 EV 没生效。这一堆单元测试就是钉 blockers 覆盖完整。

单元测试走 `Engine.__new__(Engine)` 建 fake 实例，绕开 __init__ 里的 torch/vram/shm——
所以 libraw/torch 缺席的 CI 也能跑（这正是原缺陷逃过 test_export_bit_depth_16 的场合）。
"""
from __future__ import annotations

import numpy as np
import pytest

from lumaretouch_engine.server import Engine


def _mk() -> Engine:
    """一份只带 blockers 用到的字段的假 Engine；绕开 __init__ 的重依赖。

    字段中性位必须齐（与 server.py 里 __init__ 那段同源）：任何一条漏给非默认值，
    就会让「默认应当返回空」这条基线断言假红/假绿。
    """
    e = Engine.__new__(Engine)
    e._strength = 0.0
    e._grade = (0.0, 0.0, 0.0, 1.0)
    e._grade_scope = "all"
    e._lut = None
    e._lut_amount = 0.0
    e._repair_ops = []
    e._light_ops = []
    e._deform = {"amounts": {}, "built": False}
    e._crop_rect = (0.0, 0.0, 1.0, 1.0)
    e._crop_rotation = 0.0
    e._exposure = (0.0,) * 7
    e._hsl = (0.0,) * 24
    e._enhance = {"amounts": {}, "built": False, "box": None}
    e._bg = {"active": False, "matte": None, "bg": None, "backend": None,
             "tol": None, "softness": None}
    return e


def test_master16_blockers_empty_on_neutral():
    """全中立位不能报任何 blocker——否则用户按默认参数也导不出 16-bit，反向挡正常路径。"""
    assert _mk()._master16_blockers(scale=1, sharpen=0.0) == []


@pytest.mark.parametrize("patch,expect_sub", [
    # 原版本已经拦的：回归一下不丢
    (lambda e: setattr(e, "_strength", 0.5), "磨皮强度"),
    (lambda e: setattr(e, "_grade", (0.1, 0.0, 0.0, 1.0)), "色阶增量"),
    (lambda e: (setattr(e, "_lut", np.zeros((2, 2, 2, 3))),
                setattr(e, "_lut_amount", 0.5)), "LUT 强度"),
    # P1-5 补上的五条：这是原始缺陷的现场
    (lambda e: setattr(e, "_exposure", (1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)),
     "曝光/白平衡/影调"),
    (lambda e: setattr(e, "_exposure", (0.0, 500.0, 0.0, 0.0, 0.0, 0.0, 0.0)),
     "曝光/白平衡/影调"),
    (lambda e: setattr(e, "_exposure", (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.2)),
     "曝光/白平衡/影调"),
    (lambda e: setattr(e, "_hsl", (0.0, 0.0, 0.0, 0.05, 0.0, 0.0, 0.0, 0.0,
                                    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                                    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)),
     "八色 HSL"),
    (lambda e: e._enhance.__setitem__("amounts", {"eyes": 0.5, "teeth": 0.0}),
     "眼/牙增强"),
    (lambda e: e._bg.__setitem__("active", True), "换底"),
    (lambda e: (setattr(e, "_grade_scope", "skin"),
                setattr(e, "_grade", (0.05, 0.0, 0.0, 1.0))), "局部调色作用域"),
])
def test_master16_blockers_reports_each_pixel_editing_layer(patch, expect_sub):
    """每一条会改像素的编辑都必须被 blockers 报出来（关键：报错文案含期待子串）。"""
    e = _mk()
    patch(e)
    b = e._master16_blockers(scale=1, sharpen=0.0)
    joined = "、".join(b)
    assert expect_sub in joined, (
        f"blockers 没报出「{expect_sub}」：实际 {b}——"
        f"这条漏拦会让 16-bit 直通把用户设的编辑静默跳过")


def test_master16_blockers_reports_multiple_layers_together():
    """多条同时非中立时 blockers 要一条不落全报出来，不能只报第一条就 return。"""
    e = _mk()
    e._strength = 0.3
    e._exposure = (0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    e._hsl = (0.1,) + (0.0,) * 23
    e._enhance = {"amounts": {"eyes": 0.4, "teeth": 0.0}, "built": True, "box": None}
    e._bg = {"active": True, "matte": np.zeros((4, 4), np.uint8), "bg": [0.0, 0.0, 1.0],
             "backend": "color_key", "tol": 0.1, "softness": 0.1}
    b = e._master16_blockers(scale=1, sharpen=0.0)
    joined = "、".join(b)
    for sub in ("磨皮强度", "曝光/白平衡/影调", "八色 HSL", "眼/牙增强", "换底"):
        assert sub in joined, f"缺报「{sub}」：{b}"


def test_master16_blockers_ignores_enhance_when_all_zero():
    """"条目存在"不等于"作用了"：enhance 有 amounts 字典但都是 0，blocker 不该报。

    与 deform 那条同规——load_image 会把上一次的控制点带进新一张图（位置还在、位移全零），
    拿条目数当判据会把一张干净的图挪成"有图层"而拒掉直通。
    """
    e = _mk()
    e._enhance = {"amounts": {"eyes": 0.0, "teeth": 0.0}, "built": True, "box": None}
    assert e._master16_blockers(scale=1, sharpen=0.0) == []


def test_master16_blockers_ignores_grade_scope_when_grade_neutral():
    """scope 不是 all 但 grade 三项全 0：这一层不点火，blocker 不该拦。

    与上一条同理：作用域只是"选择往哪儿作"，实际作不作由 grade 三个增量决定；
    全 0 时 matte 不会被 apply 到像素上，直通安全。
    """
    e = _mk()
    e._grade_scope = "skin"
    e._grade = (0.0, 0.0, 0.0, 1.0)
    assert e._master16_blockers(scale=1, sharpen=0.0) == []
