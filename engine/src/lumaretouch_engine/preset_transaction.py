"""Keep failed preset renders from leaving a partially applied live recipe."""
from collections.abc import Callable
from .scope import ScopeError


class PresetApplyError(ScopeError):
    def __init__(self, message: str, *, rolled_back: bool):
        super().__init__(message)
        self.rolled_back = rolled_back
        self.requires_reload = not rolled_back


def apply_with_rollback(replay: Callable, before: dict, after: dict, *, preset_id: str,
                        emit: Callable, invalidate: Callable, strict_local=False) -> dict:
    try:
        return replay(after, mode="preset", replayed_for=f"preset:{preset_id}", **({'strict_local':True} if strict_local else {}))
    except Exception as error:
        try:
            frame = replay(before, mode="preset_rollback", replayed_for=f"preset_rollback:{preset_id}")
        except Exception as rollback_error:
            invalidate()
            raise PresetApplyError(f"应用失败且回滚出帧失败，请重新打开图片；原错误：{error}；"
                                   f"回滚错误：{rollback_error}", rolled_back=False) from error
        if frame is not None:
            emit(frame)
        raise PresetApplyError(f"应用失败，已恢复上一配方：{error}", rolled_back=True) from error
