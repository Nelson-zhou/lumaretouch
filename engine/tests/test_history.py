"""M5-b 全局撤销/重做的库层语义（不起子进程，直接拿 Engine 的私有方法验口径）。

为什么这些能留在库层而不必走 IPC：这一步占不占一步、一次手势的身份证、快照里
到底装了什么——都是纯函数级的判断。真正只有端到端才看得见的（画面能不能逐字节
退回去、历史跟着不跟着文档走）在 test_protocol.py 里。
"""

from __future__ import annotations

import time

import pytest

from lumaretouch_engine.server import Engine


@pytest.fixture
def eng():
    return Engine("hist-lib")


def _edit(eng, group, **changes):
    """跑一遍分发器里的三步：执行前抄快照 → 改 live → 记账。

    顺序不能省成改完再抄：那样 before 与 after 永远是同一份，任何一步都不占，
    这个文件里所有关于步数的断言都会以「栈是空的」通过——假绿。
    """
    before = eng._history_capture()
    for k, v in changes.items():
        setattr(eng, k, v)
    eng._history_record(group, before)


def test_group_id_is_the_shape_of_the_request(eng):
    """同一个滑块的连发必须同组，不同滑块必须不同组——组名用参数名，不用值。"""
    a = eng._history_group("set_strength", {"cmd": "set_strength", "value": 0.4})
    b = eng._history_group("set_strength", {"cmd": "set_strength", "value": 0.9})
    c = eng._history_group("set_strength", {"cmd": "set_strength", "mid_gain": 0.3})
    assert a == b, "拖同一个滑块时值一直在变，拿值当组名就等于每次都不合并"
    assert a != c, "换了另一个滑块还合并成一步，撤销就会一次退掉两个动作"
    # action 参与组名：inpaint 的 add 与 clear 是两个动作，不能互相合并
    assert eng._history_group("inpaint", {"cmd": "inpaint", "action": "add"}) \
        != eng._history_group("inpaint", {"cmd": "inpaint", "action": "clear"})


def test_signature_ignores_float_noise_but_sees_a_new_table(eng):
    s0 = eng._hist_sig(eng._history_capture())
    st2 = eng._history_capture()
    st2["_strength"] = float(st2["_strength"]) + 1e-12
    st2["_grade"] = (eng._grade[0] + 1e-12, eng._grade[1], eng._grade[2], eng._grade[3])
    assert eng._hist_sig(st2) == s0, "1e-12 的浮点尾差被当成改过一次：撤销栈会被空步占满"
    # 换一张表（内容相同也算换了动作）必须看得出来；同一张表重复提交不算
    arr = [[float(i) / 7.0 for i in range(4)] for _ in range(4)]
    eng._lut = arr
    with_table = eng._hist_sig(eng._history_capture())
    assert with_table != s0
    eng._lut = list(arr)                  # 内容相同、对象不同 → 身份不同
    assert eng._hist_sig(eng._history_capture()) != with_table
    eng._lut = arr
    assert eng._hist_sig(eng._history_capture()) == with_table


def test_snapshot_drops_precompute_but_state_keeps_it(eng):
    """预计算是检测不是修图，而且它是几 MB 的原件：不进快照，撤销也不许把它退掉。"""
    sentinel = object()
    eng._strength = 0.77
    eng._precompute = sentinel
    eng._precompute_backend = "template"
    snap = eng._history_capture()
    assert set(snap) == (set(Engine.DOC_FIELDS) - set(Engine.HISTORY_SKIP)) | {"_proxy"}
    # 代理档尺寸也在快照里：它决定这一笔坐标成立与否，撤销回去时必须是那一档
    assert "_precompute" not in snap and "_precompute_backend" not in snap
    eng._precompute = None
    eng._strength = 0.2
    eng._history_apply(snap)              # 装回快照
    assert eng._strength == pytest.approx(0.77), "快照里的强度没回来"
    assert eng._precompute is None, "预计算由当前会话带着，快照不许把它退回 None"


def test_rejected_edit_takes_no_step(eng):
    """整条被拒的命令（live 字段没动）不许占一步——分发器统一记账方案的命门。"""
    assert eng._undo == []
    _edit(eng, "set_strength::value")     # 什么都没改：等价于一条被整条拒绝的命令
    assert eng._undo == [], "被拒的命令也占了一步：按撤销会退到一条没发生过的动作"


def test_one_gesture_one_step_and_the_window_bound(eng):
    """窗口内同组合并成一步；跨过窗口（或换参数名）就是新的一步。"""
    _edit(eng, "g", _strength=0.55)       # 第一次手势：占一步
    assert len(eng._undo) == 1
    _edit(eng, "g", _strength=0.6)        # 同组同窗口：同一次拖拽的后续
    assert len(eng._undo) == 1, "同组同窗口内不该新增步"
    # 手工把窗口起点推回过去（等价于睡过 700 ms，但不占测试时间）
    eng._hist_group_ns = time.monotonic_ns() - int((Engine.HISTORY_GROUP_MS + 120) * 1e6)
    _edit(eng, "g", _strength=0.8)
    assert len(eng._undo) == 2, "跨过合并窗口必须是新的一步"
    eng._hist_group_ns = time.monotonic_ns() - int((Engine.HISTORY_GROUP_MS + 120) * 1e6)
    _edit(eng, "h", _strength=0.9)        # 换一组（另一个滑块）
    assert len(eng._undo) == 3
    # 快照存的是这一步执行前的状态：栈底那格必须是出厂强度
    assert eng._undo[0]["_strength"] == pytest.approx(0.5)


def test_new_edit_clears_redo_and_stack_is_capped(eng):
    for v in range(Engine.HISTORY_MAX + 8):
        eng._hist_group, eng._hist_group_ns = "", 0
        eng._redo.append({"stub": True})    # 先摆一条 redo：真编辑必须把它清掉
        _edit(eng, f"g{v}", _strength=0.001 * v)
    assert len(eng._undo) == Engine.HISTORY_MAX, "栈必须封顶，否则长会话会无限吃内存"
    # 每格存的是执行前：丢掉最老的 8 步后，栈底那格是第 8 步之前的值
    assert eng._undo[0]["_strength"] == pytest.approx(0.001 * 7), "丢的必须是最老那一步"
    assert eng._redo == [], "任何一次真编辑都必须断掉 redo 链"
    rep = eng._history_report()
    assert rep["can_undo"] and rep["undo_steps"] == Engine.HISTORY_MAX
    assert rep["history_max"] == Engine.HISTORY_MAX


def test_dispatch_table_registers_history_and_edit_commands(eng):
    """分发表的名单与 EDIT_CMDS 必须对得上：漏一条就是那一层编辑不进历史，
    而用户只在按了 Ctrl+Z 之后才发现——那时已经说不清是谁的责任。"""
    table = {"hello", "bench_start", "bench_stop", "set_device", "shutdown", "load_image",
             "set_strength", "precompute", "inpaint", "light", "deform", "lut", "grade",
             "background", "export", "session", "history"}
    assert set(Engine.EDIT_CMDS) <= table
    assert "history" in table
    assert set(Engine.HISTORY_ACTIONS) == {"undo", "redo", "state", "clear"}
    # 预计算与切文档不是编辑：它们不该被记成一步
    assert "precompute" not in Engine.EDIT_CMDS and "load_image" not in Engine.EDIT_CMDS
    assert "session" not in Engine.EDIT_CMDS
