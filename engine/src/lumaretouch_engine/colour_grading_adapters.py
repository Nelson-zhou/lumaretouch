"""Concrete recipe adapters. All paths reuse strict state and the same Rust stage.

No pixels, cached masks, document IDs or native pointers enter a portable preset.
Batch is prepare-all then host-owned group transaction; never writes files here.
"""
from copy import deepcopy
from . import colour_grading_state as S
from .colour_grading_stage import ColourGradingStage


def capture(engine):
    return {S.KEY: S.check(getattr(engine, S.KEY, S.neutral()))}


def restore(engine, state):
    recipe = S.from_state(state)
    setattr(engine, S.KEY, recipe)
    if getattr(engine, '_vram', None) is not None:
        engine._vram.colour_grading = ColourGradingStage(recipe)


def report(engine):
    return {'recipe': capture(engine)[S.KEY], 'algorithm': S.ALGORITHM,
            'note': '独立影调颜色分级；非 AI 追色或 HSL'}


def validate_records(value, *, depth=0, allowed=True):
    if depth > 64:
        raise ValueError('Project nesting exceeds colour grading validation budget')
    if isinstance(value, dict):
        if S.KEY in value:
            if not allowed:raise ValueError('颜色分级配方必须使用工程 v17；旧 schema 不得夹带')
            S.check(value[S.KEY])
        for child in value.values():
            validate_records(child, depth=depth + 1, allowed=allowed)
    elif isinstance(value, list):
        for child in value:
            validate_records(child, depth=depth + 1, allowed=allowed)


def preset_from_state(state):
    return {'version': 1, 'kind': 'colour_grading', 'recipe': S.from_state(state)}


def check_preset(value):
    if not isinstance(value, dict) or set(value) != {'version', 'kind', 'recipe'} or type(value['version']) is not int or value['version'] != 1 or value['kind'] != 'colour_grading':
        raise ValueError('Unsupported colour grading preset')
    return S.check(value['recipe'])


def apply_preset_to_state(state, preset):
    # Replacement avoids accidentally accumulating a grade when replayed.
    return {**state, S.KEY: check_preset(preset)}


def prepare_batch(states, preset):
    if not isinstance(states, list) or not 1 <= len(states) <= 1000:
        raise ValueError('Colour grading batch supports 1–1000 loaded state records')
    recipe = check_preset(preset)
    if any(not isinstance(s, dict) for s in states):
        raise ValueError('Batch state must be an object')
    return [{**s, S.KEY: deepcopy(recipe)} for s in states]


def configure_export(spec, snap):
    # Export snapshots use public key; explicit invalid/null must fail, not reset.
    recipe = S.check(snap['colour_grading']) if 'colour_grading' in snap else S.neutral()
    spec.colour_grading = recipe


def export_snapshot(state):
    return {'colour_grading': S.from_state(state)}


def export_stage(spec):
    recipe = S.check(spec.colour_grading) if hasattr(spec, 'colour_grading') and spec.colour_grading is not None else S.neutral()
    return ColourGradingStage(recipe)


def sync(engine):
    """Resync persisted recipe after any host mutation; retain temporary preview."""
    if getattr(engine,'_vram',None) is None or getattr(engine,'_colour_grading_preview_active',False):return
    restore(engine,capture(engine))
    engine._vram.colour_grading.cancelled=getattr(engine,'_colour_grading_cancelled',lambda:False)
