# SPDX-License-Identifier: GPL-3.0-or-later
"""All-or-nothing current-photo hair geometry admission. AUTHORED / UNRUN.

The parent resolves scalar inheritance, freezes source/evidence/assets, chooses
the joint chain position and runs its existing common sampler. No image passes
through this module. Actual original and immutable derived sources use the same
exact source contract, never a substituted original-file path.
"""
from copy import deepcopy
import numpy as np
from . import people_state as P, hair_colour_analysis as E
from . import hair_volume_state as S, hair_volume_support as A
from .hair_volume_field import HairVolumeField, binding_digest, whole_source_shape


class HairVolumeRefused(ValueError):
    def __init__(self, refusals):
        self.refusals = refusals
        super().__init__('Hair geometry refused: ' + '; '.join(row['reason'] for row in refusals))


def _overlap(a, b):
    return bool(np.all(a[0] <= b[1]) and np.all(b[0] <= a[1]))


def _box(value, shape):
    h, w = shape
    return np.array(A.box(value), np.float64).reshape(2, 2)*np.array([w-1, h-1])


def _recipes(state, asset_sha256, recipes):
    P.digest(asset_sha256)
    if type(recipes) is not dict or len(recipes) > P.MAX_FACES:
        raise ValueError('Hair geometry needs resolved per-face scalar intent')
    out = {}
    for key, recipe in recipes.items():
        face = state['faces'].get(key)
        if face is None or face['asset_sha256'] != asset_sha256:
            raise ValueError('Resolved hair geometry intent belongs to a different source/face')
        out[key] = S.check(recipe)
    return out


def prepare_fields(people_state, asset_sha256, shape, *, recipes, support_assets,
                   hair_evidence, source_frame, byte_budget, protected_regions=()):
    people = P.check(people_state); binding = A.source(source_frame)
    if binding['sha256'] != asset_sha256:
        raise ValueError('Hair geometry source identity changed')
    whole_source_shape(binding, shape); recipes = _recipes(people, asset_sha256, recipes)
    if type(byte_budget) is not int or byte_budget < 1024*1024:
        raise ValueError('Hair geometry requires an explicit admitted field memory budget')
    assets = A.check_store(support_assets)
    if type(protected_regions) not in (list, tuple) or len(protected_regions) > 4096:
        raise ValueError('Additional observed source protection exceeds its budget')
    observed_protection = tuple(_box(value, shape) for value in protected_regions)
    protection_sha256 = A.digest([A.box(value) for value in protected_regions])
    active = {key: recipe for key, recipe in recipes.items()
              if people['faces'][key]['enabled'] and S.active(recipe)}
    if len(active) > 8:
        raise ValueError('Hair geometry active-owner budget exceeded; no silent truncation')
    if not active:
        return ()  # Exact neutral bypass: no native library or ML required.
    if hair_evidence is None:
        raise ValueError('Active hair geometry lacks actual retained measured source hair evidence')
    E.check(hair_evidence, binding)
    fields, failures = [], []
    for key, recipe in sorted(active.items()):
        face = people['faces'][key]; ref = P.face_ref(face)
        try:
            value = A.resolve(people, assets, ref)
            if value is None or value['source'] != binding:
                raise ValueError('Review observed crown/side source contours for this operation before applying it')
            A.verify_evidence(value, hair_evidence)
            field = HairVolumeField(value, recipe, shape)
            field.input_protection_sha256 = protection_sha256
            # Every retained face owns pixels, even disabled/manual/unresolved.
            # Actual exposed ears/neck and manually reviewed other people are
            # whole fixed regions. Never cut holes in an otherwise unsafe warp.
            protected = list(observed_protection)
            for retained in people['faces'].values():
                if retained['asset_sha256'] == asset_sha256:
                    protected.append(_box(retained['box'], shape))
            for category in ('ears', 'neck', 'other_people'):
                protected.extend(_box(b, shape) for b in value['row']['protection'][category])
            if any(_overlap(envelope, obstacle) for envelope in field.envelopes() for obstacle in protected):
                raise ValueError('Hair transition/reach touches protected face, ear, neck or another person; mark a clear strip')
            for other in fields:
                if any(_overlap(a, b) for a in field.envelopes() for b in other.envelopes()):
                    raise ValueError('Different people’s hair transitions touch; ownership is ambiguous')
            fields.append(field)
        except (ValueError, RuntimeError, OSError, AttributeError) as exc:
            failures.append({'face_ref': deepcopy(ref), 'operation_id': S.OPERATION_ID,
                             'reason': str(exc), 'requested_recipe': deepcopy(recipe), 'applied': False})
    if failures:
        raise HairVolumeRefused(failures)
    if sum(field.resident_bytes() for field in fields) > byte_budget:
        raise ValueError('Retained hair fields exceed the admitted memory budget')
    return tuple(fields)


def require_prepared(people_state, asset_sha256, fields, *, recipes, support_assets, source_frame,
                     protected_regions=()):
    """Host must call before consumption; no missing/extra/stale active fields."""
    people = P.check(people_state); recipes = _recipes(people, asset_sha256, recipes)
    binding = A.source(source_frame)
    if binding['sha256'] != asset_sha256:
        raise ValueError('Prepared hair geometry source differs from the current source')
    if type(protected_regions) not in (list, tuple) or len(protected_regions) > 4096:
        raise ValueError('Additional observed source protection exceeds its budget')
    protection_sha256 = A.digest([A.box(value) for value in protected_regions])
    expected = {key for key, recipe in recipes.items() if people['faces'][key]['enabled'] and S.active(recipe)}
    seen = set()
    for field in fields:
        key = field.face_instance_id
        if key not in expected or key in seen or field.operation_id != S.OPERATION_ID:
            raise ValueError('Prepared hair geometry contains duplicate or unrequested owners')
        record = A.resolve(people, support_assets, P.face_ref(people['faces'][key]))
        if (record is None or field.source != binding or field.record != record
                or field.input_binding_sha256 != binding_digest(record, recipes[key])
                or getattr(field, 'input_protection_sha256', None) != protection_sha256):
            raise ValueError('Prepared hair field has stale source, review, evidence, geometry or intent')
        seen.add(key)
    if seen != expected:
        raise ValueError('Prepared hair fields do not cover every active owner; no partial application')
