"""Explicit project/history/preset/batch/export adapters, no unknown-field stripping."""
from copy import deepcopy
from . import extended_tone_state as S
from .extended_tone_stage import ExtendedToneStage

def capture(engine, record):
    result = deepcopy(record)
    result[S.KEY] = S.check(getattr(engine, S.KEY, None))
    return result

def restore(engine, record):
    setattr(engine, S.KEY, S.check(record.get(S.KEY)))

def validate_records(value, *, allowed=True):
    if isinstance(value, dict):
        if S.KEY in value:
            if not allowed:raise ValueError('扩展影调配方必须使用工程 v16，旧 schema 不得夹带或丢弃')
            S.check(value[S.KEY])
        for child in value.values(): validate_records(child, allowed=allowed)
    elif isinstance(value, list):
        for child in value: validate_records(child, allowed=allowed)

def preset_export(spec):
    return {'extended_tone': S.check(spec)}

def preset_apply(record, payload):
    if type(payload) is not dict or set(payload) != {'extended_tone'}: raise ValueError('Invalid extended tone preset payload')
    result = deepcopy(record)
    result[S.KEY] = S.check(payload['extended_tone'])
    return result

def batch_replace(records, spec):
    """Pure preparation, not a fake batch commit. Host's group transaction commits all or none."""
    s = S.check(spec)
    if type(records) is not dict or not records or len(records) > 2000: raise ValueError('Batch requires 1–2000 document records')
    if any(type(k) is not str or not k or type(v) is not dict for k, v in records.items()): raise ValueError('Invalid document records')
    validate_records(records)
    return {doc: {**deepcopy(record), S.KEY: deepcopy(s)} for doc, record in records.items()}

def configure_export(export_spec, snapshot):
    export_spec.extended_tone = S.check(snapshot.get('extended_tone'))

def render_export_full_frame(pixels, spec, *, monochrome=False, mask=None):
    # Mandatory after assembled full-resolution upstream stage, BEFORE RGB8 quantization.
    # A tile must never estimate its own airlight or reset neighborhood boundaries.
    return ExtendedToneStage(spec, scale=1., monochrome=monochrome, mask=mask).apply_np(pixels)
