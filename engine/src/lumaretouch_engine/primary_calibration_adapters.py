"""Concrete recipe adapters. All paths reuse strict state and the same Rust stage.

No pixels, cached masks, document IDs or native pointers enter a portable preset.
Batch is prepare-all then host-owned group transaction; never writes files here.
"""
from copy import deepcopy
from . import primary_calibration_state as S
from .primary_calibration_stage import PrimaryCalibrationStage
from .primary_calibration_native import admit


def capture(engine):
    return {S.KEY: S.check(getattr(engine, S.KEY, S.neutral()))}


def restore(engine, state):
    recipe = admit(S.from_state(state))
    setattr(engine, S.KEY, recipe)
    if getattr(engine, '_vram', None) is not None:
        engine._vram.primary_calibration = PrimaryCalibrationStage(recipe)


def report(engine):
    return {'recipe': capture(engine)[S.KEY], 'algorithm': S.ALGORITHM,
            'note': '原创全局原色基矩阵；非 HSL、ICC 或相机 DCP 配置'}


def validate_records(value, *, depth=0, allowed=True):
    if depth > 64:
        raise ValueError('Project nesting exceeds primary calibration validation budget')
    if isinstance(value, dict):
        if S.KEY in value:
            if not allowed:raise ValueError('RGB 原色校准配方必须使用支持原色校准的新工程 schema；旧 schema 不得夹带')
            admit(value[S.KEY])
        for child in value.values():
            validate_records(child, depth=depth + 1, allowed=allowed)
    elif isinstance(value, list):
        for child in value:
            validate_records(child, depth=depth + 1, allowed=allowed)


def preset_from_state(state):
    return {'version': 1, 'kind': 'primary_calibration', 'recipe': S.from_state(state)}


def check_preset(value):
    if not isinstance(value, dict) or set(value) != {'version', 'kind', 'recipe'} or type(value['version']) is not int or value['version'] != 1 or value['kind'] != 'primary_calibration':
        raise ValueError('Unsupported primary calibration preset')
    return admit(value['recipe'])


def apply_preset_to_state(state, preset):
    # Replacement avoids accidentally accumulating a grade when replayed.
    return {**state, S.KEY: check_preset(preset)}


def prepare_batch(states, preset):
    if not isinstance(states, list) or not 1 <= len(states) <= 1000:
        raise ValueError('Primary calibration batch supports 1–1000 loaded state records')
    recipe = check_preset(preset)
    if any(not isinstance(s, dict) for s in states):
        raise ValueError('Batch state must be an object')
    return [{**s, S.KEY: deepcopy(recipe)} for s in states]


def configure_export(spec, snap):
    # Export snapshots use public key; explicit invalid/null must fail, not reset.
    recipe = S.check(snap['primary_calibration']) if 'primary_calibration' in snap else S.neutral()
    spec.primary_calibration = recipe


def export_snapshot(state):
    return {'primary_calibration': S.from_state(state)}


def export_stage(spec):
    recipe = S.check(spec.primary_calibration) if hasattr(spec, 'primary_calibration') and spec.primary_calibration is not None else S.neutral()
    return PrimaryCalibrationStage(recipe)


def sync(engine):
    """Resync persisted recipe after any host mutation; retain temporary preview."""
    if getattr(engine,'_vram',None) is None or getattr(engine,'_primary_calibration_preview_active',False):return
    restore(engine,capture(engine))
    engine._vram.primary_calibration.cancelled=getattr(engine,'_primary_calibration_cancelled',lambda:False)


def configure_pipeline(pipe, spec):
    """Install on EVERY export pipeline, including extended-tone prepass.

    Shared vram hook invokes this stage after exposure and before tone input.
    Do not apply export_stage again to the completed export image.
    """
    pipe.primary_calibration = export_stage(spec)


def requires_float(spec):
    return export_stage(spec).active
