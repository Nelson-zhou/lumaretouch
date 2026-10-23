"""Concrete Engine adapter. Importing does not install or monkeypatch shared host code."""
from copy import deepcopy
from . import photo_detail_state as S
from .photo_detail_controller import PhotoDetailController, Ports
from .photo_detail_stage import PhotoDetailStage

class CommitFailure(RuntimeError):
    def __init__(self, error, rollback_error=None):
        super().__init__(f'Photo detail failed: {error}' + (f'; rollback failed: {rollback_error}' if rollback_error else ''))
        self.outcome_unknown = rollback_error is not None
        self.requires_reload = rollback_error is not None

def sync(engine, *, scale):
    if engine._vram is not None:
        engine._vram.photo_detail = PhotoDetailStage(getattr(engine, S.KEY, None), scale=scale,cancelled=getattr(engine,'_photo_detail_cancelled',lambda:False))

def controller(engine, emit, *, preview_scale):
    """Host must grant shared hooks listed in integration-map.json before this can commit."""
    owner = engine.__dict__.get('_photo_detail_owner')
    if owner is not None: return owner
    def commit(spec):
        if getattr(engine,'_photo_detail_cancelled',lambda:False)(): raise CommitFailure('请求已取消')
        engine._cancel_snapshot('photo_detail')
        engine._close_owned_previews()
        before = engine._history_capture()
        if S.KEY not in before:
            raise CommitFailure('Photo detail is absent from host history capture; integration refused')
        old = S.check(getattr(engine, S.KEY, None))
        history = engine._history_controller()
        ledger = (list(history.undo), list(history.redo), history.group, history.group_ns)
        dirty = engine._project_dirty
        try:
            setattr(engine, S.KEY, S.check(spec))
            sync(engine, scale=preview_scale())
            frame = engine._write_current_frame('photo_detail')
            # This command must NOT also use dispatcher's automatic history recording.
            engine._fence_current_document()
            engine._history_record('photo_detail', before, coalesce=False)
            if S.check(engine._history_capture()[S.KEY]) != spec:
                raise RuntimeError('History capture dropped photo detail')
        except Exception as error:
            rollback_error = None
            try:
                engine._photo_detail_publication=None
                engine._photo_detail_cancelled=lambda:False
                engine._history_apply(before)
                setattr(engine, S.KEY, old)
                sync(engine, scale=preview_scale())
                history.undo, history.redo, history.group, history.group_ns = ledger
                engine._project_dirty = dirty
                emit(engine._write_current_frame('photo_detail_rollback'))
            except Exception as failure: rollback_error = failure
            raise CommitFailure(error, rollback_error) from error
        # Emit after successful state/history. Emission failure is not a rollback of an edit.
        proof = {'history': deepcopy(engine._history_report()), 'no_change': False}
        try: emit(frame)
        except Exception: proof['frame_delivery_unknown'] = True
        return proof
    owner = PhotoDetailController(Ports(
        guard=lambda: engine._guard_editable('photo_detail'),
        document=lambda: engine._load_id,
        read=lambda: S.check(getattr(engine, S.KEY, None)),
        commit=commit, revision=lambda:revision(engine)), emit)
    engine.__dict__['_photo_detail_owner'] = owner
    return owner

def preview_scale(engine):
    if engine._vram is None: return 1.
    index=getattr(engine,'_doc_index',-1)
    if not 0<=index<len(engine._docs): raise ValueError('照片细节缺少源尺寸记录')
    row=engine._docs[index]
    w,h=row.get('src_w'),row.get('src_h')
    if not w or not h: raise ValueError('照片细节缺少真实源尺寸')
    return min(1.,engine._vram.w/float(w),engine._vram.h/float(h))

def sync_current(engine):
    if engine._vram is None:return
    sync(engine,scale=preview_scale(engine))

def readback(engine):
    from pathlib import Path
    return {'document_id':engine._load_id,'spec':S.check(getattr(engine,S.KEY,None)),
            'revision':revision(engine),'history':engine._history_report(),'available':available()}


def revision(engine):
    index=getattr(engine,'_doc_index',-1)
    return engine._document_versions().version(engine._docs[index]).revision if 0<=index<len(engine._docs) else 0


def available():
    try:
        from .photo_detail_native import native
        native()  # Runtime ABI verification only; never compile or silently fall back.
        return True
    except (OSError, RuntimeError, AttributeError):
        return False
