"""Consumer-bound recovery for common background, distinct from dedicated ID.

Only vectors are durable recovery intent. These review/export proofs are
disposable and bind the real common compositor, never an original-file matte
relabelled as an immutable returned source.
"""
from copy import deepcopy
from hashlib import sha256
import json
import math
import numpy as np
from . import effect_recovery_state as S, creative_derived_source as D
from . import common_background_source as B

TARGET = 'background_replace'


def retained(value):
    return any(row['target'] == TARGET for row in S.check(value)['targets'])


def enabled(value):
    return any(row['target'] == TARGET and row['enabled'] for row in S.check(value)['targets'])


def _background(owner):
    return owner.get('_bg') if isinstance(owner, dict) else getattr(owner, '_bg', None)


def _intent(bg):
    """No cached bitmap or allocation identity belongs in retained evidence."""
    recipe = B.check(bg)
    if bg is None:
        return {'recipe': None, 'active': False, 'color': None,
                'backend': None, 'tol': None, 'softness': None}
    if type(bg) is not dict or type(bg.get('active')) is not bool:
        raise ValueError('Common recovery requires an explicit compositor activation state')
    color = bg.get('bg')
    if color is not None:
        if (type(color) not in (list, tuple) or len(color) != 3
                or any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in color)):
            raise ValueError('Common recovery background color is invalid')
        color = list(color)
    if bg['active'] and color is None:
        raise ValueError('Active common recovery consumer has no solid background color')
    backend = bg.get('backend')
    if backend is not None and type(backend) is not str:
        raise ValueError('Common recovery backend identity is invalid')
    parameters = {}
    for key in ('tol', 'softness'):
        value = bg.get(key)
        if value is not None and (type(value) not in (int, float) or not math.isfinite(value)):
            raise ValueError('Common recovery key parameters are invalid')
        parameters[key] = value
    return {'recipe': recipe, 'active': bg['active'], 'color': color,
            'backend': backend, **parameters}


def validate_state(owner, value):
    value = S.check(value)
    if not retained(value):
        return value
    intent = _intent(_background(owner))
    recipe = intent['recipe']
    if recipe is not None and recipe['source'] != value['source']:
        raise ValueError('Common recovery vectors and background key belong to different sources')
    if D.record(owner) is not None:
        if recipe is None or recipe['version'] != 2 or recipe['source'] != D.binding(owner):
            raise ValueError('Derived common recovery requires its owned version-2 color key, including disabled rows')
    elif recipe is not None and recipe['version'] != 1:
        raise ValueError('Derived common recovery key cannot be rebound to an original photo')
    return value


def _activity(engine):
    from . import id_background_state as I, sky_replacement_state as SKY, studio_background_state as ST
    return {'id_background': I.active(getattr(engine, '_id_background', None)),
            'sky_replacement': SKY.check(getattr(engine, '_sky_replacement', None))['enabled'],
            'studio_background': ST.active(getattr(engine, '_studio_background', None))}


def context(engine, *, require_active=False):
    from .creative_derived_id_background import _deformation_key
    validate_state(engine, getattr(engine, '_effect_recovery', None))
    proof = B.consumer_proof(engine)
    if require_active and not proof['active']:
        raise ValueError('Enable the reviewed common background before adding recovery strokes')
    # The producer checks source, color-key recipe and actual installed bytes.
    # Recovery adds the geometry that aligns both the matte and its brush field.
    return deepcopy({'consumer': proof, 'intent': _intent(_background(engine)),
                     'deformation': _deformation_key(engine._vram),
                     'activity': _activity(engine)})


def configure_export(spec, snap):
    spec._common_recovery_recipe = None
    value = validate_state(snap, snap.get('effect_recovery'))
    if retained(value):
        spec._common_recovery_recipe = {'source': deepcopy(value['source']),
                                        'intent': _intent(_background(snap))}


def _array_proof(value):
    if type(value) is not np.ndarray or value.dtype.kind not in 'buif' or not np.isfinite(value).all():
        raise ValueError('Common recovery evidence requires finite numerical fields')
    digest = sha256()
    for row in value:
        digest.update(memoryview(np.ascontiguousarray(row)).cast('B'))
    return {'shape': list(value.shape), 'dtype': value.dtype.str, 'sha256': digest.hexdigest()}


def _content_proof(value):
    """Snapshot analyses contain arrays; compare their content, not ndarray ==."""
    if type(value) is np.ndarray:
        return {'array': _array_proof(value)}
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            raise ValueError('Common recovery geometry snapshot has invalid keys')
        return {key: _content_proof(item) for key, item in value.items()}
    if type(value) in (list, tuple):
        return [_content_proof(item) for item in value]
    if type(value) is bytes:
        return {'byte_count': len(value), 'sha256': sha256(value).hexdigest()}
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    raise ValueError('Common recovery geometry snapshot has unsupported evidence')


def _geometry(spec):
    """Full-export geometry intent, not the preview's disposable proxy warp."""
    value = {name: _content_proof(getattr(spec, name, None)) for name in
             ('deform_amounts', 'body_pose', 'brow_shape', 'nose_shape', 'eye_shape',
              'mouth_shape', 'manual_liquify', 'people')}
    landmarks = getattr(spec, 'landmarks', None)
    value['landmarks'] = None if landmarks is None else _array_proof(landmarks)
    return value


def _export_proof(spec):
    expected = getattr(spec, '_common_recovery_recipe', None)
    if type(expected) is not dict or set(expected) != {'source', 'intent'}:
        raise ValueError('Common recovery lacks its retained full-resolution consumer intent')
    source = S.check(spec.effect_recovery)['source']
    if source != expected['source']:
        raise ValueError('Common recovery export vectors changed their effective source')
    intent = expected['intent']
    if type(intent) is not dict or set(intent) != {'recipe', 'active', 'color', 'backend', 'tol', 'softness'}:
        raise ValueError('Common recovery full-resolution consumer intent is invalid')
    retained = _intent({'key_recipe': intent['recipe'], 'active': intent['active'],
                        'backend': intent['backend'], 'bg': intent['color'],
                        'tol': intent['tol'], 'softness': intent['softness']})
    if retained != intent or (intent['recipe'] is not None and intent['recipe']['source'] != source):
        raise ValueError('Common recovery retained key and vector sources disagree')
    key = getattr(spec, 'common_background_key', None)
    color = getattr(spec, 'common_background_color', None)
    matte, background = getattr(spec, 'bg_matte', None), getattr(spec, 'bg_ref', None)
    active = matte is not None or background is not None
    if active != intent['active'] or (active and (matte is None or background is None)):
        raise ValueError('Common recovery full-resolution consumer activation changed')
    if key != (intent['recipe'] if active else None):
        raise ValueError('Common recovery full-resolution key differs from retained intent')
    if getattr(spec, 'creative_base', None) is not None:
        effective = D.binding({'creative_base': spec.creative_base})
        if source != effective or intent['recipe'] is None or intent['recipe']['version'] != 2:
            raise ValueError('Common recovery export requires its actual derived version-2 consumer')
    proof = {'source': source, 'intent': intent, 'active': active,
             'key': key, 'color': color, 'geometry': _geometry(spec)}
    if getattr(spec, 'creative_base', None) is not None and active:
        canonical = getattr(spec, '_common_canonical_pixels', None)
        if (type(canonical) is not tuple or len(canonical) != 2
                or canonical[0] != json.dumps(key, sort_keys=True, allow_nan=False)
                or type(canonical[1]) is not str or len(canonical[1]) != 64
                or any(c not in '0123456789abcdef' for c in canonical[1])):
            raise ValueError('Common recovery export lacks canonical full-source pixel preparation evidence')
        proof['input'] = _content_proof(canonical)
    if active:
        if type(matte) is not np.ndarray or matte.shape != (source['height'], source['width']):
            raise ValueError('Common recovery requires the complete source-size prepared matte, not a proxy')
        if matte.dtype not in (np.uint8, np.float32):
            raise ValueError('Common recovery prepared matte dtype is invalid')
        if not np.isfinite(matte).all() or np.any(matte < 0) or np.any(matte > (255 if matte.dtype == np.uint8 else 1)):
            raise ValueError('Common recovery prepared matte exceeds its coverage domain')
        if type(background) not in (list, tuple) or list(background) != intent['color']:
            raise ValueError('Common recovery full-resolution background color changed')
        if key is not None:
            checked = B.check({'active': True, 'key_recipe': key, 'backend': intent['backend'],
                               'tol': intent['tol'], 'softness': intent['softness'], 'bg': color})
            if checked != intent['recipe'] or list(color) != intent['color'] or matte.dtype != np.float32:
                raise ValueError('Common recovery deterministic key needs its genuine full float matte and color')
            B.finish_export(spec)
            if (spec.common_background_path != spec.effect_recovery_path
                    or spec.common_background_stamp != spec.effect_recovery_stamp):
                raise ValueError('Common recovery and background decoded different original-file provenance')
            proof.update(path=spec.common_background_path, stamp=spec.common_background_stamp)
        proof.update(matte=_array_proof(matte), background=list(background))
    return deepcopy(proof)


def export_prepare(spec):
    """Called only after the common owner prepares its genuine full matte."""
    spec._common_recovery_consumer = None
    if enabled(spec.effect_recovery):
        spec._common_recovery_consumer = _export_proof(spec)


def verify_export(spec):
    if not enabled(spec.effect_recovery):
        return
    expected = getattr(spec, '_common_recovery_consumer', None)
    if expected is None or _export_proof(spec) != expected:
        raise ValueError('Common recovery source, recipe, color, geometry or full matte changed')


def assert_consumer(engine, stage):
    expected = getattr(stage, 'common_recovery_context', None)
    # Explicit review evidence survives deleting the last row or disabling it.
    if expected is not None and context(engine) != expected:
        raise ValueError('Common recovery consumer changed during reviewed application')
