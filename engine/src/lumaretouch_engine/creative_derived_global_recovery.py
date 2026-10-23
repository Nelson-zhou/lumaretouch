"""Derived global recovery vectors, not original-image pixels or face assets.

Only the adapted fabric operator is admitted. Contexts are ephemeral export
proofs; durable intent remains the existing source-bound normalized vectors.
"""
from copy import deepcopy
from hashlib import sha256
import json
from . import effect_recovery_state as S, local_mask_state as M
from . import creative_derived_source as D

TARGETS = frozenset(('fabric_fine',))


def validate(value, source):
    """Check disabled rows too; face rows are owned by the people bank."""
    value = S.check(value)
    if value['source'] is not None and value['source'] != source:
        raise ValueError('Recovery vectors belong to another immutable source')
    from .facial_wrinkle_recovery import FACE_TARGETS
    if any(row['target'] not in TARGETS | set(FACE_TARGETS) for row in value['targets']):
        raise ValueError('Derived global recovery supports fabric only; smoothing/background remain unadapted')
    value['targets'] = [row for row in value['targets'] if row['target'] in TARGETS]
    if not value['targets']:value['source'] = None
    value = S.check(value)
    S.validate_budget(value, (source['height'], source['width']))
    return value


def recipe_digest(value):
    return sha256(json.dumps(S.check(value), sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def capture(state_or_engine, value, path):
    source = D.binding(state_or_engine)
    value = validate(value, source)
    if not value['targets']:return None
    return {'version': 1, 'source': source, 'original_sha256': M.source_digest(path),
            'recipe_sha256': recipe_digest(value)}


def verify_context(context, source, value, path=None):
    value = validate(value, source)
    if (type(context) is not dict or set(context) != {'version', 'source', 'original_sha256', 'recipe_sha256'}
            or type(context['version']) is not int or context['version'] != 1 or context['source'] != source
            or context['recipe_sha256'] != recipe_digest(value)):
        raise ValueError('Derived global recovery lacks its exact source and recipe context')
    from .people_state import digest
    digest(context['original_sha256'])
    if path is not None and M.source_digest(path) != context['original_sha256']:
        raise ValueError('Recovery original-file provenance changed')
    return deepcopy(context)


def verify_snapshot(snapshot, path=None, shape=None):
    source = D.binding(snapshot)
    value = validate(snapshot.get('effect_recovery', snapshot.get('_effect_recovery')), source)
    if shape is not None and tuple(shape) != (source['height'], source['width']):
        raise ValueError('Derived recovery output is not its immutable source grid')
    if value['targets']:
        verify_context(snapshot.get('creative_recovery_context'), source, value, path)
    return value


def raster(value, source, shape, *, cancelled=lambda: False):
    from .effect_recovery_stage import check_fields
    value = validate(value, source)
    S.validate_budget(value, shape)
    result = []
    for row in S.enabled(value):
        if cancelled():raise InterruptedError('Recovery rasterization cancelled')
        result.append({'target': row['target'], 'weight': M.R.raster(row['recipe'], shape)})
    return check_fields(result, shape, state=value)


def preview_fields(engine, value):
    source = D.binding(engine)
    from .creative_derived_repair_runtime import verify_pipeline
    verify_pipeline(engine._vram, source)
    return raster(value, source, (engine._vram.h, engine._vram.w))


def _pixels(spec, pixels):
    from .creative_derived_repair_export import _pixels as pixel_digest
    source = D.binding({'creative_base': spec.creative_base})
    verify_context(spec.creative_recovery_context, source, spec.effect_recovery)
    return source, recipe_digest(spec.effect_recovery), pixel_digest(source, pixels)


def stamp_pixels(spec, pixels):
    """INTERNAL only: immediately after canonical immutable source resolution."""
    spec._creative_recovery_pixels = _pixels(spec, pixels)


def verify_pixels(spec, pixels):
    if getattr(spec, '_creative_recovery_pixels', None) != _pixels(spec, pixels):
        raise ValueError('Recovery export pixels or recipe changed after canonical resolution')


def mutation_binding(engine, target):
    if target not in TARGETS:
        raise ValueError('This global recovery operator has no derived-source consumer')
    source = D.binding(engine)
    validate(getattr(engine, '_effect_recovery', None), source)
    from .creative_derived_repair_runtime import verify_pipeline
    verify_pipeline(engine._vram, source)
    D.verify_precompute(engine, engine._precompute)
    return source


def validate_state(state):
    """Durable vectors need no ephemeral raster/context, but own every source."""
    if D.record(state) is None:return
    source = D.binding(state)
    if isinstance(state, dict):
        if 'effect_recovery' in state and '_effect_recovery' in state:
            if S.check(state['effect_recovery']) != S.check(state['_effect_recovery']):
                raise ValueError('Conflicting persisted recovery state aliases')
        raw = state.get('effect_recovery', state.get('_effect_recovery'))
    else:
        raw = getattr(state, '_effect_recovery', None)
    validate(raw, source)
