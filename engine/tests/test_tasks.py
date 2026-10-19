"""任务台账的单元用例（LNX-P0-TASK；TASK-001/002/006/007/008/009）。

这一层没有线程也没有 GPU，所以八条 TASK 用例里关于"状态怎么走的"那半部分在这里
就能全验掉；"到边界才承认"那半部分在 test_protocol.py 里用真批次验。两层合起来
才算覆盖——只跑这一层的话，"转移表对了而 worker 从来不看它"是测不出来的。
"""
from __future__ import annotations

import pytest

from lumaretouch_engine import tasks as T


def _task(n=3, **over):
    inputs = {"out_dir": "/tmp/out", "format": "png", "quality": 90, "bit_depth": 8}
    items = [f"/img/{i}.dng" for i in range(n)]
    t = T.new_task("export", inputs, items, task_id="t-1")
    t.update(over)
    return t


# ---------------------------------------------------------------- 建账
def test_new_task_refuses_empty_batch_and_missing_snapshot():
    with pytest.raises(T.TaskError):
        T.new_task("export", {"out_dir": "/x"}, [], task_id="t")
    with pytest.raises(T.TaskError):
        T.new_task("export", {}, ["/a"], task_id="t")
    with pytest.raises(T.TaskError):
        T.new_task("render", {}, ["/a"], task_id="t")
    # 空批次的"成功"是假指标，没快照的重试是拿当前设置重跑——两条都必须是拒
    assert T.counts(_task()) == {"total": 3, "succeeded": 0, "failed": 0, "skipped": 0,
                                 "pending": 3}


def test_items_are_fixed_at_creation():
    # 验收用例引用：BATCH-002（新编辑不改已入账的目标）
    # 验收用例引用：BATCH-001（目标清单在建立那一刻定死：只改已选的那些）
    """清单进来就定了：跑一半改清单，"批次已暂停"就没人说得清指哪一批。"""
    t = _task()
    assert [i["path"] for i in t["items"]] == ["/img/0.dng", "/img/1.dng", "/img/2.dng"]
    assert all(i["state"] == T.QUEUED for i in t["items"])


# ---------------------------------------------------------------- 转移表
def test_history_is_auditable_with_reasons():
    """TASK-001 的 then：状态转移可审计。"""
    t = _task()
    T.transit(t, T.RUNNING, "worker 开工")
    T.request_pause(t)
    T.transit(t, T.PAUSED, "已到安全点")
    seq = [(h[0], h[2]) for h in t["history"]]
    assert [s for s, _ in seq] == [T.QUEUED, T.RUNNING, T.PAUSE_REQUESTED, T.PAUSED]
    assert any("安全点" in r for _, r in seq), seq
    assert all(h[1] > 0 for h in t["history"]), "没有时刻的轨迹不能事后对账"


@pytest.mark.parametrize("cur,to", [
    (T.QUEUED, T.PAUSED),          # 还没跑就"暂停了"：那一位是谁置的？
    (T.SUCCEEDED, T.RUNNING),      # 成功的批次不能"又开始跑"，只能 retry
    (T.CANCELLED, T.RUNNING),
    (T.PAUSED, T.SUCCEEDED),       # 停在边界上不能直接宣布整批成功
])
def test_illegal_transitions_are_refused(cur, to):
    t = _task()
    t["state"] = cur
    with pytest.raises(T.TaskError):
        T.transit(t, to, "试一下")
    assert t["state"] == cur, "被拒的转移仍然写了状态"


def test_unknown_state_is_refused():
    t = _task()
    with pytest.raises(T.TaskError):
        T.transit(t, "waiting_for_godot")


def test_history_is_capped():
    t = _task()
    t["state"] = T.PAUSED
    for _ in range(200):
        T.transit(t, T.PAUSED, "幂等重放")
    assert len(t["history"]) <= 65, "台账是整份读进内存的，轨迹不能无限长"


# ---------------------------------------------------------------- 暂停两步走
def test_pause_lands_on_the_boundary_not_immediately():
    """TASK-006 的 then：先 pause_requested 并提示等待安全点；到边界才 paused。"""
    t = _task()
    T.transit(t, T.RUNNING, "开工")
    T.request_pause(t)
    assert t["state"] == T.PAUSE_REQUESTED, "按下暂停就当“已暂停”：运行项还在写文件"
    assert "安全点" in t["history"][-1][2]
    T.transit(t, T.PAUSED, "已到条目边界")
    assert t["state"] == T.PAUSED


def test_request_pause_on_paused_is_idempotent():
    t = _task()
    t["state"] = T.PAUSED
    before = len(t["history"])
    T.request_pause(t)
    assert t["state"] == T.PAUSED and len(t["history"]) == before, "重复按暂停多记一步"


def test_resume_requires_paused():
    t = _task()
    T.transit(t, T.RUNNING)
    with pytest.raises(T.TaskError):
        T.request_resume(t)
    T.request_pause(t)
    T.transit(t, T.PAUSED)
    assert T.request_resume(t)["state"] == T.RESUMING


def test_cancel_is_for_things_that_have_not_stopped():
    """TASK-001：取消是对还没停下的东西说的话；已终止的批次取消没有意义。"""
    t = _task()
    T.transit(t, T.RUNNING)
    assert T.request_cancel(t)["state"] == T.CANCELLING
    T.transit(t, T.CANCELLED, "已停止提交新输出")
    with pytest.raises(T.TaskError):
        T.request_cancel(t)


# ---------------------------------------------------------------- 逐条目结局
def test_skipped_is_not_success_nor_failure():
    """EXPORT-001 的冲突跳过与 TASK-003 的失败必须各自数得出来。"""
    t = _task(3)
    T.item_result(t, "/img/0.dng", "succeeded", out="/img/0.png")
    T.item_result(t, "/img/1.dng", "skipped", reason="同名文件已存在（skip_and_report）")
    T.item_result(t, "/img/2.dng", "failed", reason="OSError: 设备上没有空间")
    c = T.counts(t)
    assert c == {"total": 3, "succeeded": 1, "failed": 1, "skipped": 1, "pending": 2}, c
    assert T.pending_items(t) == ["/img/1.dng", "/img/2.dng"]


def test_item_result_rejects_unknown_state_and_path():
    t = _task()
    with pytest.raises(T.TaskError):
        T.item_result(t, "/img/0.dng", "done")
    with pytest.raises(T.TaskError):
        T.item_result(t, "/not/in/batch", "succeeded")


# ---------------------------------------------------------------- 批次状态是算出来的
def test_batch_state_does_not_say_paused_before_everyone_stopped():
    """TASK-007 的 then：全部到边界前不显示批次已暂停。"""
    a, b = _task(), _task()
    a["task_id"], b["task_id"] = "a", "b"
    T.transit(a, T.RUNNING)
    T.transit(b, T.RUNNING)
    T.request_pause(a)
    T.transit(a, T.PAUSED, "到边界")
    st = T.batch_state([a, b])
    assert st["state"] == T.RUNNING, st          # b 还在跑
    T.request_pause(b)
    assert T.batch_state([a, b])["state"] == "transitioning", "一条到边界一条还没：不能说暂停了也不能说在跑"
    T.transit(b, T.PAUSED, "到边界")
    assert T.batch_state([a, b])["state"] == T.PAUSED
    assert T.batch_state([a, b])["running"] == 2
    a["state"] = b["state"] = T.SUCCEEDED
    assert T.batch_state([a, b]) == {"running": 0, "state": "idle",
                                     "counts": {"total": 6, "succeeded": 0, "failed": 0,
                                                "skipped": 0, "pending": 6}}


# ---------------------------------------------------------------- 重试固定输入
def test_retry_keeps_the_snapshot_and_the_identity():
    # 验收用例引用：BATCH-001（task_id/attempt 与输入快照保留）
    """TASK-002：attempt+1、task_id 不变、**输入快照不变**。"""
    t = _task(3)
    snap = dict(t["inputs"])
    T.transit(t, T.RUNNING)
    T.item_result(t, "/img/0.dng", "succeeded", out="/img/0.png")
    T.item_result(t, "/img/1.dng", "failed", reason="OSError: 权限不够")
    T.transit(t, T.FAILED, "1 条失败")
    t2, pend = T.begin_retry(t)
    assert pend == ["/img/1.dng", "/img/2.dng"], "重试要跑的是没成功的，不是全批"
    assert t2["attempt"] == 1 and t2["task_id"] == "t-1"
    assert t2["inputs"] == snap, "重试改了输入就不叫重试了"
    assert t2["state"] == T.RETRYING


def test_retry_refuses_a_running_batch_and_a_fully_succeeded_one():
    # 验收用例引用：BATCH-002（跑到一半的批次不许被另一次编辑覆盖着重启）
    t = _task()
    T.transit(t, T.RUNNING)
    with pytest.raises(T.TaskError):
        T.begin_retry(t)
    t2 = _task(task_id="t-2")
    t2["state"] = T.SUCCEEDED
    for it in t2["items"]:
        it["state"] = "succeeded"
    with pytest.raises(T.TaskError):
        T.begin_retry(t2)


# ---------------------------------------------------------------- 落盘与重开
def test_for_json_round_trip_and_no_auto_resume():
    # 验收用例引用：TASK-004（台账往返：提交标记与状态一致，未跑完的可重试）
    """TASK-008：paused 后关闭进程，重开仍然 paused 等待用户继续；不自动重跑。"""
    t = _task()
    T.transit(t, T.RUNNING)
    T.request_pause(t)
    T.transit(t, T.PAUSED, "到边界")
    back = T.from_json(T.for_json(t))
    assert back["state"] == T.PAUSED and back["persisted"] is True
    assert back["task_id"] == t["task_id"] and back["inputs"] == t["inputs"]


@pytest.mark.parametrize("interrupted", [T.QUEUED, T.RUNNING, T.PAUSE_REQUESTED,
                                         T.RESUMING, T.CANCELLING, T.RETRYING])
def test_an_interrupted_run_comes_back_paused_never_running(interrupted):
    # 验收用例引用：TASK-004（中断后回来只会 paused，不自动重跑已成功项）
    """进程没了，"正在做"的说法一律不再成立。

    回落成 running 等于自动重跑（008 明令禁止）；回落成 failed 等于把中断算成失败，
    用户会去查一个并不存在的错误。paused + 一句"进程曾中断"是唯一说得清的写法。
    """
    t = _task()
    t["state"] = interrupted
    back = T.from_json(T.for_json(t))
    assert back["state"] == T.PAUSED, (interrupted, back["state"])
    assert any("中断" in h[2] for h in back["history"]), back["history"]


def test_from_json_rejects_foreign_records():
    with pytest.raises(T.TaskError):
        T.from_json({"task_id": "t", "kind": "export", "state": "paused",
                     "items": [], "inputs": {}})          # 缺 schema_version
    with pytest.raises(T.TaskError):
        T.from_json({"schema_version": "lrt.task.v0", "task_id": "t", "kind": "export",
                     "state": "paused", "items": [], "inputs": {}})
    bad = T.for_json(_task())
    bad["state"] = "waiting_for_godot"
    with pytest.raises(T.TaskError):
        T.from_json(bad)


def test_terminal_states_come_back_unchanged():
    """succeeded/failed/cancelled 是**结局**，重开不许改写它。"""
    for st in (T.SUCCEEDED, T.FAILED, T.CANCELLED):
        t = _task()
        t["state"] = st
        assert T.from_json(T.for_json(t))["state"] == st
