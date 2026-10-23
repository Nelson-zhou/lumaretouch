"""Concrete Engine adapter. Importing does not install or monkeypatch shared host code."""
from copy import deepcopy
from . import extended_tone_state as S
from .extended_tone_controller import ExtendedToneController, Ports
from .extended_tone_stage import ExtendedToneStage

class CommitFailure(RuntimeError):
    def __init__(self, error, rollback_error=None):
        super().__init__(f'Extended tone failed: {error}' + (f'; rollback failed: {rollback_error}' if rollback_error else ''))
        self.outcome_unknown = rollback_error is not None
        self.requires_reload = rollback_error is not None

def sync(engine, *, scale, monochrome=False):
    if engine._vram is not None:
        engine._vram.extended_tone = ExtendedToneStage(getattr(engine, S.KEY, None), scale=scale, monochrome=monochrome,cancelled=getattr(engine,'_extended_tone_cancelled',lambda:False))

def controller(engine, emit, *, preview_scale, monochrome):
    """Host must grant shared hooks listed in integration-map.json before this can commit."""
    owner = engine.__dict__.get('_extended_tone_owner')
    if owner is not None: return owner
    def commit(spec):
        if getattr(engine,'_extended_tone_cancelled',lambda:False)(): raise CommitFailure('请求已取消')
        engine._cancel_snapshot('extended_tone')
        engine._close_owned_previews()
        before = engine._history_capture()
        if S.KEY not in before:
            raise CommitFailure('Extended tone is absent from host history capture; integration refused')
        old = S.check(getattr(engine, S.KEY, None))
        history = engine._history_controller()
        ledger = (list(history.undo), list(history.redo), history.group, history.group_ns)
        dirty = engine._project_dirty
        try:
            setattr(engine, S.KEY, S.check(spec))
            sync(engine, scale=preview_scale(), monochrome=monochrome())
            frame = engine._write_current_frame('extended_tone')
            # This command must NOT also use dispatcher's automatic history recording.
            engine._fence_current_document()
            engine._history_record('extended_tone', before, coalesce=False)
            if S.check(engine._history_capture()[S.KEY]) != spec:
                raise RuntimeError('History capture dropped extended tone')
        except Exception as error:
            rollback_error = None
            try:
                engine._extended_tone_publication=None
                engine._extended_tone_cancelled=lambda:False
                engine._history_apply(before)
                setattr(engine, S.KEY, old)
                sync(engine, scale=preview_scale(), monochrome=monochrome())
                history.undo, history.redo, history.group, history.group_ns = ledger
                engine._project_dirty = dirty
                emit(engine._write_current_frame('extended_tone_rollback'))
            except Exception as failure: rollback_error = failure
            raise CommitFailure(error, rollback_error) from error
        # Emit after successful state/history. Emission failure is not a rollback of an edit.
        proof = {'history': deepcopy(engine._history_report()), 'no_change': False}
        try: emit(frame)
        except Exception: proof['frame_delivery_unknown'] = True
        return proof
    owner = ExtendedToneController(Ports(
        guard=lambda: engine._guard_editable('extended_tone'),
        document=lambda: engine._load_id,
        read=lambda: S.check(getattr(engine, S.KEY, None)),
        monochrome=monochrome, commit=commit, revision=lambda:revision(engine)), emit)
    engine.__dict__['_extended_tone_owner'] = owner
    return owner

def preview_scale(engine):
    if engine._vram is None: return 1.
    index=getattr(engine,'_doc_index',-1)
    if not 0<=index<len(engine._docs): raise ValueError('扩展影调缺少源尺寸记录')
    row=engine._docs[index]
    w,h=row.get('src_w'),row.get('src_h')
    if not w or not h: raise ValueError('扩展影调缺少真实源尺寸')
    return min(1.,engine._vram.w/float(w),engine._vram.h/float(h))

def sync_current(engine):
    if engine._vram is None:return
    spec=S.check(getattr(engine,S.KEY,None))
    sync(engine,scale=preview_scale(engine),monochrome=spec['monochrome'])

def readback(engine):
    from pathlib import Path
    return {'document_id':engine._load_id,'spec':S.check(getattr(engine,S.KEY,None)),
            'revision':revision(engine),'history':engine._history_report(),'available':(Path(__file__).parent/'bin/liblrt_extended_tone.so').is_file(),
            'monochrome_source':'extended-tone-original-output-mode; not XMP profile'}


def revision(engine):
    index=getattr(engine,'_doc_index',-1)
    return engine._document_versions().version(engine._docs[index]).revision if 0<=index<len(engine._docs) else 0
