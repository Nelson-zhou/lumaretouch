"""Keep failed preset renders from leaving a partially applied live recipe."""
from collections.abc import Callable
from .scope import ScopeError


def apply_with_rollback(replay: Callable, before: dict, after: dict, *, preset_id: str,
                        emit: Callable, invalidate: Callable) -> dict:
    try:
        return replay(after, mode="preset", replayed_for=f"preset:{preset_id}")
    except Exception as error:
        try:
            frame = replay(before, mode="preset_rollback", replayed_for=f"preset_rollback:{preset_id}")
        except Exception as rollback_error:
            invalidate()
            raise ScopeError(f"应用失败且回滚出帧失败，请重新打开图片；原错误：{error}；"
                             f"回滚错误：{rollback_error}") from error
        if frame is not None:
            emit(frame)
        raise ScopeError(f"应用失败，已恢复上一配方：{error}") from error
