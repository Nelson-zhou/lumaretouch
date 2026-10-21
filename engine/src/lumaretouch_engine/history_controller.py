"""Live document history owns stacks and gestures, not renderer/session state.

Session owns parked per-document copies. Binding and persisting them remains at
Engine's existing document-transition points. Restore/render is one explicit port
shared by successful undo and its rollback, preserving face/precompute replay.
"""
from dataclasses import dataclass
from typing import Callable

ACTIONS = ("undo", "redo", "state", "clear")

@dataclass(frozen=True)
class HistoryPorts:
    capture: Callable[[], dict]
    signature: Callable[[dict], str]
    restore_frame: Callable[[dict, str], dict]
    guard: Callable[[str], str | None]
    remember_current: Callable[[], None]
    status: Callable[[], dict]
    mark_dirty: Callable[[], None]

class HistoryController:
    def __init__(self, ports: HistoryPorts, emit: Callable[[dict], None],
                 clock: Callable[[], int], limit: int, group_ms: float):
        self.ports = ports
        self.emit = emit
        self.clock = clock
        self.limit = limit
        self.group_ms = group_ms
        self.undo = []
        self.redo = []
        self.group = ""
        self.group_ns = 0

    def record(self, group: str, before: dict) -> None:
        """一条编辑命令执行完（不论成功还是抛错）后调。

        快照是**执行前**抄的，所以"被拒绝的命令"天然不占一步：它整条 return，
        live 字段没动，签名与 before 一致。异常路径也记账（分发器里是 try/finally）：
        半改完的状态正是最需要一次撤销能修回去的时候。
        """
        try:
            after = self.ports.capture()
        except AssertionError:
            return                      # 名单漂移由命令自己响，这里不叠第二份错
        if self.ports.signature(before) == self.ports.signature(after):
            return
        # “这一条真的改了文档状态”与“这一条要占一步历史”是同一件事，所以项目脏标记
        # 也只在这里上：被拒的命令整条 return（签名没变）不脏，看一眼原图（compare）
        # 不在 EDIT_CMDS 里也不脏。刚保存完就亮“未保存”的徽章比不亮更坑：它让人
        # 以为保存没生效，于是一次又一次地存。
        self.ports.mark_dirty()
        now = self.clock()
        same_gesture = False
        if group and self.group == group \
                and (group.startswith(("curves:gesture:", "levels:gesture:")) or
                     (now - self.group_ns) / 1e6 < self.group_ms):
            same_gesture = True
        if not same_gesture:
            self.undo.append(before)
            if len(self.undo) > self.limit:
                # 丢最老的：这一条是内存账，不是功能边界（64 步 × 每份几 KB）
                del self.undo[0]
        if same_gesture and group.startswith(("curves:gesture:", "levels:gesture:")) and self.undo \
                and self.ports.signature(self.undo[-1]) == self.ports.signature(after):
            self.undo.pop()  # dragging/cancelling back to the start is not an undo step
            group = ""
        self.group, self.group_ns = group, now
        # 新编辑一律断掉 redo 链：留着就会出"撤销两次、重做一次跳回最新"那种
        # 看起来像丢工的行为
        self.redo.clear()

    def report(self) -> dict:
        return {"can_undo": bool(self.undo), "can_redo": bool(self.redo),
                "undo_steps": len(self.undo), "redo_steps": len(self.redo),
                "history_max": self.limit}

    def bind(self, row: dict | None) -> None:
        """切文档时把这一格的历史装回 live（与状态同一批，不单独时序）。"""
        self.undo = list((row or {}).get("undo") or [])
        self.redo = list((row or {}).get("redo") or [])
        self.group, self.group_ns = "", 0

    def handle_command(self, p: dict):
        """撤销/重做：整条链只有一份实现——装回快照，然后用 _attach_pipeline 按
        那些字段重放图层（与换设备、切文档同一条路），不写第二份重放。"""
        unknown = set(p) - {"cmd", "action"}
        if unknown:
            self.emit({"event": "error", "error": f"history 收到不认识的参数：{sorted(unknown)}"})
            return
        action = p.get("action", "state")
        if action not in ACTIONS:
            self.emit({"event": "error", "error": f"未知 history action: {action}"
                  f"（可用：{'/'.join(ACTIONS)}）"})
            return
        if action == "state":
            self.emit({"event": "history_state", "action": action, "doc_state": self.ports.status(),
                  **self.report()})
            return
        if action == "clear":
            self.undo, self.redo = [], []
            self.group, self.group_ns = "", 0
            self.ports.remember_current()
            self.emit({"event": "history_state", "action": "clear", "doc_state": self.ports.status(),
                  **self.report()})
            return
        # 与 set_strength 同一条守卫：跑靶线程在写 frame_gpu，这里也写同一块；
        # 导出线程拿着的是"撤销前那一版"的笔迹，画面与账单会分头说话
        reason = self.ports.guard(action)
        if reason:
            self.emit({"event": "error", "error": reason})
            return
        stack = self.undo if action == "undo" else self.redo
        other = self.redo if action == "undo" else self.undo
        if not stack:
            # 退无可退不是错误：快捷键按多了是常态，报 noop 让按钮跟着灰下去
            self.emit({"event": "history_state", "action": action, "noop": True,
                  "doc_state": self.ports.status(), **self.report()})
            return
        snap = stack[-1]
        current = self.ports.capture()
        if tuple(snap.get("_proxy") or ()) != tuple(current.get("_proxy") or ()):
            # 正常路径不会到这里（代理档一变就清历史），留着是为了"清没清干净"这件事
            # 不能靠注释保证——快照的像素坐标与新尺寸不配时重放会渲染出半截画面
            self.emit({"event": "error", "error": f"{action} 那一格的快照属于另一档代理尺寸："
                  f"{snap.get('_proxy')} vs {current.get('_proxy')}，已拒绝"})
            return
        t0 = self.clock()
        try:
            fr = self.ports.restore_frame(snap, f"history_{action}")
        except Exception as e:
            # 半截状态不许留在 live 上：退回执行前那一份，并按它重建一次会话
            try:
                self.ports.restore_frame(current, "history_rollback")
                rolled = True
            except Exception as e2:
                rolled = False
                self.emit({"event": "engine_warn",
                      "warn": f"history {action} 失败后回滚也失败（{type(e2).__name__}: {e2}）："
                              "画面与状态可能不一致，请重新导入这张图"})
            self.emit({"event": "error", "error": f"history {action} 失败："
                  f"{type(e).__name__}: {e}" + ("" if rolled else "；且回滚失败")})
            return
        ms = round((self.clock() - t0) / 1e6, 2)
        stack.pop()
        other.append(current)
        if len(other) > self.limit:
            del other[0]
        self.group, self.group_ns = "", 0
        self.ports.remember_current()
        render_ms = fr.pop("render_ms")
        self.emit({"event": "history_state", "action": action, "history_ms": ms,
              "render_ms": render_ms, "doc_state": self.ports.status(),
              **self.report()})
        self.emit(fr)

