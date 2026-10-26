"""批量任务台账（LNX-P0-TASK；验收 TASK-001/002/003/004/006/007/008/009）。

这一层只有状态与审计轨迹，没有线程、没有事件：暂停能不能生效、生效在哪一步，
是**线程间**的事（控制位在 server 那侧），而"现在是什么状态、怎么走到这里的"是
这一层的事。分开写有两个实际收益：八条 TASK 用例全部能在没有 GPU、没有线程的
环境里跑；而转移表只有一份，不会出现"worker 以为能暂停、命令面以为不能"。

状态机（转移不合法就抛，不在调用方各自判断）：

    queued ──▶ running ──▶ succeeded
                  │            ▲
     pause_requested ──▶ paused ──▶ resuming ──▶ running
                  │                                ▲
                  ▼                                │
             cancelling ──▶ cancelled        retrying
    running/paused/failed/cancelled ──▶ retrying ──┘（attempt+1，task_id 与输入快照不变）

几条验收要求落到字段上是什么样：

* TASK-001「状态转移可审计」→ `history` 逐条记 (state, ns, reason)，不是布尔位；
* TASK-002「失败重试固定输入」→ 重试只读 `inputs`（命令当时那一拍的快照），
  绝不读 live 状态；快照与 live 的区别就是这条用例的判据；
* TASK-003「磁盘满及权限失败」→ 逐条目 `failed_reason` 存异常类型与原文，
  批级只报计数，不把失败折成"完成"；
* TASK-006/007「先 pause_requested、到边界才 paused；全部到边界前不显示批次已暂停」
  → `pause_requested` 与 `paused` 是两个状态，批次状态由成员状态**算出来**
  （`batch_state`），不是谁置的一个位；
* TASK-009「已进入原子提交的任务完成后维持成功」→ 安全点只在条目**之间**，
  所以这一层根本不提供"中断当前条目"的入口；删除队列记录也只动台账。
"""
from __future__ import annotations

import time
import copy

SCHEMA = "lrt.task.v1"

QUEUED = "queued"
RUNNING = "running"
PAUSE_REQUESTED = "pause_requested"
PAUSED = "paused"
RESUMING = "resuming"
CANCELLING = "cancelling"
CANCELLED = "cancelled"
RETRYING = "retrying"
SUCCEEDED = "succeeded"
FAILED = "failed"

STATES = (QUEUED, RUNNING, PAUSE_REQUESTED, PAUSED, RESUMING, CANCELLING,
          CANCELLED, RETRYING, SUCCEEDED, FAILED)

# 转移表：唯一一份。不在表里 = 拒，不静默“差不多就当过了”。
LEGAL: dict[str, tuple[str, ...]] = {
    QUEUED: (RUNNING, PAUSE_REQUESTED, CANCELLING, FAILED),
    RUNNING: (PAUSE_REQUESTED, CANCELLING, SUCCEEDED, FAILED),
    PAUSE_REQUESTED: (PAUSED, CANCELLING, RUNNING, SUCCEEDED, FAILED),      # 到边界才 paused
    PAUSED: (RESUMING, CANCELLING, FAILED, PAUSED),              # PAUSED→PAUSED 是幂等重放
    RESUMING: (RUNNING, CANCELLING, FAILED),
    CANCELLING: (CANCELLED, FAILED),
    RETRYING: (RUNNING, PAUSE_REQUESTED, CANCELLING, FAILED),
    SUCCEEDED: (RETRYING,),          # 重跑成功项也是合法操作（换格式重导）
    FAILED: (RETRYING,),
    CANCELLED: (RETRYING,),
}

# 还在跑（或等着被叫停）的那些：批次状态与守卫都按这一集合判
LIVE_STATES = (QUEUED, RUNNING, PAUSE_REQUESTED, PAUSED, RESUMING, CANCELLING, RETRYING)


class TaskError(ValueError):
    """任务台账的错。继承 ValueError：命令面的守卫本来就吃它。"""


def now_ns() -> int:
    return time.time_ns()


def new_task(kind: str, inputs: dict, items: list, *, task_id: str) -> dict:
    """建一条台账。`inputs` 是**当时那一拍的命令快照**，重试只读它。

    items 必须一进来就定下来：跑一半再改清单，"批次已暂停"就没人说得清是指哪一批。
    """
    if kind not in ("export",):
        raise TaskError(f"本版本的任务种类只有 export（收到 {kind!r}）")
    if not isinstance(items, list) or not items:
        raise TaskError("任务需要非空的条目列表：空批次的“成功”是假指标")
    if not isinstance(inputs, dict) or not inputs:
        raise TaskError("任务必须带着输入快照：TASK-002 的“重试固定输入”全靠它，"
                        "没有快照的重试就是拿当前设置重跑，那是另一件事")
    return {"schema_version": SCHEMA, "task_id": task_id, "kind": kind,
            "state": QUEUED, "attempt": 0, "inputs": copy.deepcopy(inputs),
            "items": [{"path": p, "state": QUEUED, "out": None,
                       "failed_reason": None} for p in items],
            "history": [[QUEUED, now_ns(), "新建"]],
            "created_ns": now_ns(), "updated_ns": now_ns(),
            "persisted": False, "blocked_reason": None}


def transit(task: dict, to: str, reason: str = "") -> dict:
    """按转移表走一步，并记下为什么走。"""
    cur = task["state"]
    if to not in STATES:
        raise TaskError(f"不认识的状态 {to!r}（可用：{'/'.join(STATES)}）")
    if to not in LEGAL.get(cur, ()):
        raise TaskError(f"非法转移：{cur} → {to}（{cur} 只许走 "
                        f"{list(LEGAL.get(cur, ()))}）{('；原因：' + reason) if reason else ''}")
    task["state"] = to
    task["updated_ns"] = now_ns()
    task["history"].append([to, task["updated_ns"], reason or ""])
    # 轨迹不能无限长：一条批次几百个转移，台账又是整份读进内存的
    if len(task["history"]) > 64:
        del task["history"][0]
    return task


def item_result(task: dict, path: str, state: str, *, out: str | None = None,
                reason: str | None = None, detail: dict | None = None) -> dict:
    """记一条目的结局。state 只有三种：succeeded / failed / skipped。

    skipped（冲突策略让路）不是失败也不是成功：它必须能单独数出来，否则
    “12 张里 3 张没写”会被折进“12 张已完成”里。
    """
    if state not in ("succeeded", "failed", "skipped"):
        raise TaskError(f"条目结局只认 succeeded/failed/skipped，收到 {state!r}")
    for it in task["items"]:
        if it["path"] == path:
            it["state"] = state
            it["out"] = out
            it["failed_reason"] = reason
            if detail:
                it.update({k: v for k, v in detail.items() if k not in ("path", "state")})
            task["updated_ns"] = now_ns()
            return task
    raise TaskError(f"任务 {task['task_id']} 的清单里没有这一条：{path}")


def pending_items(task: dict) -> list:
    """重试要跑的条目：没成功的（含 skipped——用户说 retry 就是要它出片）。"""
    return [it["path"] for it in task["items"] if it["state"] != "succeeded"]


def counts(task: dict) -> dict:
    ok = sum(1 for i in task["items"] if i["state"] == "succeeded")
    bad = sum(1 for i in task["items"] if i["state"] == "failed")
    skp = sum(1 for i in task["items"] if i["state"] == "skipped")
    return {"total": len(task["items"]), "succeeded": ok, "failed": bad, "skipped": skp,
            "pending": len(task["items"]) - ok}


def is_live(task: dict) -> bool:
    return task["state"] in LIVE_STATES


def batch_state(tasks: list) -> dict:
    """批次状态**算出来**，不是谁置的一位（TASK-007）。

    “全部到边界前不显示批次已暂停”在这条式子里是自然结果：只要还有一条是
    running / pause_requested（还没到边界），批次就不是 paused。
    """
    live = [t for t in tasks if is_live(t)]
    if not live:
        return {"running": 0, "state": "idle", "counts": _merge_counts(tasks)}
    if all(t["state"] in (PAUSED,) for t in live):
        st = PAUSED
    elif any(t["state"] in (PAUSE_REQUESTED, RESUMING, CANCELLING) for t in live):
        st = "transitioning"
    else:
        st = RUNNING
    return {"running": len(live), "state": st, "counts": _merge_counts(tasks)}


def _merge_counts(tasks: list) -> dict:
    out = {"total": 0, "succeeded": 0, "failed": 0, "skipped": 0, "pending": 0}
    for t in tasks:
        c = counts(t)
        for k in out:
            out[k] += c[k]
    return out


def request_pause(task: dict) -> dict:
    """用户按下暂停：先 pause_requested，等 worker 到边界再承认 paused。

    已经在 paused 上是幂等的（重复按暂停不该报错，也不该多记一步轨迹）。
    """
    if task["state"] in (PAUSED, PAUSE_REQUESTED):
        return task
    return transit(task, PAUSE_REQUESTED, "用户请求暂停（等待安全点）")


def request_resume(task: dict) -> dict:
    if task["state"] == RESUMING:
        return task
    if task["state"] != PAUSED:
        raise TaskError(f"只能恢复 paused 的任务，而它是 {task['state']}："
                        "没暂停过就没有“继续”这一步")
    return transit(task, RESUMING, "用户请求继续")


def request_cancel(task: dict) -> dict:
    if task["state"] in (CANCELLED, SUCCEEDED, FAILED):
        raise TaskError(f"任务已经是 {task['state']}，取消是对**还没停下的东西**说的话")
    return transit(task, CANCELLING, "用户请求取消")


def begin_retry(task: dict) -> tuple[dict, list]:
    """重试：attempt+1，task_id 不变，输入用**当时那份快照**。

    返回 (task, 要重跑的条目)。TASK-002 的 then 写着"固定输入"——这里刻意不接受
    任何新的 inputs 参数：能从命令面改输入就不是重试，那是新任务。
    """
    if task["state"] in LIVE_STATES and task["state"] != PAUSED:
        raise TaskError(f"任务在 {task['state']}：先暂停或取消再重试")
    pend = pending_items(task)
    if not pend:
        raise TaskError("这一批全部成功了：retry 无事可做（要重跑成功项请新建任务，"
                        "那样 attempt 与输入的归属才说得清）")
    transit(task, RETRYING, f"第 {task['attempt'] + 1} 次尝试，重跑 {len(pend)} 条")
    task["attempt"] += 1
    for it in task["items"]:
        if it["path"] in pend:
            it["state"] = QUEUED
            it["failed_reason"] = None
    return task, pend


def for_json(task: dict) -> dict:
    """进工程文件的那一份（纯 JSON，无活对象）。"""
    t = {k: v for k, v in task.items() if k not in ("control", "_control_token", "_control_result", "_control_owner")}
    t["counts"] = counts(task)
    return t


def from_json(obj: dict) -> dict:
    """从工程文件读回一条任务（TASK-008：paused 的回来仍然 paused，等待用户继续）。

    回来时**一律不进队列**：自动重跑是"崩溃后偷偷干活"，而 008 的 then 明写着
    "不自动重跑或切换最新配方"。依赖变化在这一层判不了（要靠源文件指纹），
    由 server 那侧置 `blocked_reason`。
    """
    if not isinstance(obj, dict) or obj.get("schema_version") != SCHEMA:
        raise TaskError(f"任务记录不是 {SCHEMA}：{obj.get('schema_version') if isinstance(obj, dict) else type(obj).__name__}")
    for k in ("task_id", "kind", "state", "items", "inputs"):
        if k not in obj:
            raise TaskError(f"任务记录缺 {k!r}")
    if obj["state"] not in STATES:
        raise TaskError(f"任务 {obj['task_id']} 的状态不认识：{obj['state']!r}")
    t = {**obj, "persisted": True}
    t.pop("_control_owner", None)
    t.pop("_control_token", None)
    t.pop("_control_result", None)
    t.setdefault("history", [[t["state"], t.get("updated_ns", 0), "从工程文件读回"]])
    t.setdefault("attempt", 0)
    t.setdefault("blocked_reason", None)
    if t["state"] in (QUEUED, RUNNING, PAUSE_REQUESTED, RESUMING, CANCELLING, RETRYING):
        # 进程都没了，这些"正在做"的说法一律不再成立：回落到 paused 等用户。
        # 不回落成 running 就等于自动重跑；不回落成 failed 就等于把中断算成失败。
        t["state"] = PAUSED
        t["history"].append([PAUSED, now_ns(), "进程曾中断：等待用户继续或取消"])
    return t
