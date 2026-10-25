# SPDX-License-Identifier: GPL-3.0-or-later
"""Append one reviewed hair field to its existing per-face inverse chain.

No independent RGB warp, dense mask multiplication, duplicate face identity or
alternate body sampler. AUTHORED / UNRUN; shared registration is parent-owned.
"""
from dataclasses import dataclass, replace
import numpy as np
from . import hair_volume_state as S


def append_fields(state, asset_sha256, fields, shape, *, recipes, assets,
                  evidence, source_frame, byte_budget):
    active = {key: value for key, value in recipes.items()
              if state['faces'][key]['enabled'] and S.active(value)}
    if not active:
        return tuple(fields), {}
    from .hair_volume_runtime import prepare_fields, require_prepared
    hair = prepare_fields(state, asset_sha256, shape, recipes=recipes,
                          support_assets=assets, hair_evidence=evidence,
                          source_frame=source_frame, byte_budget=byte_budget)
    require_prepared(state, asset_sha256, hair, recipes=recipes,
                     support_assets=assets, source_frame=source_frame)
    by_face = {field.face_instance_id: field for field in hair}
    if len(by_face) != len(hair) or set(by_face) != set(active):
        raise ValueError('Reviewed hair fields do not match every active target')
    original = {field.face_instance_id: field for field in fields}
    if len(original) != len(fields) or set(by_face) - set(original):
        raise ValueError('Hair geometry has no unique existing source-owned face chain')
    composed = {key: (field if key not in by_face else
                replace(field, fields=field.fields + (by_face[key],)))
                for key, field in original.items()}
    result = []
    for field in fields:
        key = field.face_instance_id
        if key not in by_face:
            result.append(field)
        else:
            # Compare unwrapped immutable chains, never recursively call other
            # wrappers. Checks apply to every actual common/body off-grid query.
            foreign = tuple(other for ident, other in composed.items() if ident != key)
            result.append(ReviewedHairFace(field, by_face[key], composed[key], foreign))
    return tuple(result), {key: field.facts for key, field in by_face.items()}


@dataclass(frozen=True)
class ReviewedHairFace:
    base: object
    hair: object
    composed: object
    foreign: tuple

    @property
    def face_instance_id(self):
        return self.base.face_instance_id

    @property
    def shape(self):
        return self.base.shape

    @property
    def automatic(self):
        return self.base.automatic

    @property
    def fields(self):
        return self.composed.fields

    def resident_bytes(self):
        # Foreign chains are shared immutable references already charged by
        # their own owners, not copies or a second set of field arrays.
        return self.composed.resident_bytes()

    def evaluate(self, points):
        original = self.base.evaluate(points)
        contribution = self.hair.evaluate(points - original)
        active = np.any(contribution != 0, axis=1)
        if np.any(active):
            for other in self.foreign:
                candidate = other.evaluate(points)
                if candidate.shape != points.shape or not np.isfinite(candidate).all():
                    raise ValueError('Foreign face geometry has invalid source-owned evaluation')
                if np.any(active & np.any(candidate != 0, axis=1)):
                    raise ValueError('Reviewed hair geometry intersects another active face owner; separate or reduce the conflicting edits before rendering')
        return original + contribution
