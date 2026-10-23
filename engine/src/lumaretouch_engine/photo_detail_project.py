"""Explicit project/history/preset/batch/export adapters, no unknown-field stripping."""
from copy import deepcopy
from . import photo_detail_state as S
from .photo_detail_stage import PhotoDetailStage

def capture(engine, record):
    result = deepcopy(record)
    result[S.KEY] = S.check(getattr(engine, S.KEY, None))
    return result

def restore(engine, record):
    setattr(engine, S.KEY, S.check(record.get(S.KEY)))

def validate_records(value, *, allowed=True):
    if isinstance(value, dict):
        if S.KEY in value:
            if not allowed:raise ValueError('照片细节配方必须使用工程 v20，旧 schema 不得夹带或丢弃')
            S.check(value[S.KEY])
        for child in value.values(): validate_records(child, allowed=allowed)
    elif isinstance(value, list):
        for child in value: validate_records(child, allowed=allowed)

def preset_export(spec):
    return {'photo_detail': S.check(spec)}

def preset_apply(record, payload):
    if type(payload) is not dict or set(payload) != {'photo_detail'}: raise ValueError('Invalid photo detail preset payload')
    result = deepcopy(record)
    result[S.KEY] = S.check(payload['photo_detail'])
    return result

def batch_replace(records, spec):
    """Pure preparation, not a fake batch commit. Host's group transaction commits all or none."""
    s = S.check(spec)
    if type(records) is not dict or not records or len(records) > 2000: raise ValueError('Batch requires 1–2000 document records')
    if any(type(k) is not str or not k or type(v) is not dict for k, v in records.items()): raise ValueError('Invalid document records')
    validate_records(records)
    return {doc: {**deepcopy(record), S.KEY: deepcopy(s)} for doc, record in records.items()}

def configure_export(export_spec, snapshot):
    export_spec.photo_detail = S.check(snapshot.get('photo_detail'))

def render_export_full_frame(pixels, spec, *, cancelled=lambda:False):
    # Mandatory after assembled full-resolution upstream stage, BEFORE RGB8 quantization.
    # A tile must never estimate its own spatial support or reset neighborhood boundaries.
    return PhotoDetailStage(spec, scale=1., cancelled=cancelled).apply_np(pixels)
