# SPDX-License-Identifier: GPL-3.0-or-later
"""Outermost lower-third pullback after existing contour/slim and whole-face size.

AUTHORED / UNRUN. No new sampler and no replacement for legacy small_chin.
The entire existing per-face image participates, including its earlier mouth
edit. Earlier edited points may enter the compact feather; this does not promise
to pin those positions or preserve their earlier absolute coordinates.
"""
from dataclasses import dataclass

import numpy as np

from . import lower_face_state as S, people_state as P
from .people_geometry import FaceGeometry


@dataclass(frozen=True)
class LowerFace(FaceGeometry):
    prefix: object
    protected_boxes: tuple

    def evaluate(self, points):
        points = np.asarray(points, dtype=np.float64)
        if points.ndim != 2 or points.shape[1] != 2:
            raise ValueError('Composed lower face needs finite Nx2 coordinates')
        result = np.empty_like(points)
        h, w = self.shape
        for start in range(0, len(points), 65536):
            q = points[start:start + 65536]
            if not np.isfinite(q).all():
                raise ValueError('Composed lower face needs finite Nx2 coordinates')
            lower = self.fields[-1].evaluate(q)
            if type(lower) is not np.ndarray or lower.shape != q.shape or not np.isfinite(lower).all():
                raise ValueError('Composed lower face received an invalid lower-third pullback')
            at = q - lower
            prior = self.prefix.evaluate(at)
            baseline = self.prefix.evaluate(q)
            if any(type(value) is not np.ndarray or value.shape != q.shape or not np.isfinite(value).all()
                   for value in (at, prior, baseline)):
                raise ValueError('Composed lower face received an invalid prefix pullback')
            total = lower + prior
            if not np.isfinite(total).all():
                raise ValueError('Composed lower face produced a nonfinite source pullback')
            # Compare the actual new map as well as the lower-field delta.
            # Relocated queries/cancellation must never bypass footprint checks.
            moving = np.any(lower != 0, axis=1) | np.any(total != baseline, axis=1)
            if np.any(moving):
                for coordinates in (q[moving], at[moving], (q - total)[moving]):
                    if np.any(coordinates < 1) or np.any(coordinates > [w - 2, h - 2]):
                        raise ValueError('Composed lower face footprint is outside the genuine source margin')
                    low, high = coordinates.min(0), coordinates.max(0)
                    for normalized in self.protected_boxes:
                        box = np.asarray(normalized) * [w - 1, h - 1, w - 1, h - 1]
                        if np.any(high < box[:2] - 1) or np.any(low > box[2:] + 1):
                            continue
                        if np.any(np.all((coordinates >= box[:2] - 1) & (coordinates <= box[2:] + 1), axis=1)):
                            raise ValueError('Composed lower face touches another retained face')
            result[start:start + len(q)] = total
        # No new safety promise is made for wholly unchanged legacy footprints.
        # Existing combine still checks the final all-face joint displacement map.
        return result

    def resident_bytes(self):
        # Prefix fields are shared, not copied. Preserve any prior wrapper's
        # retained guard metadata, without double-counting the shared fields.
        return (self.prefix.resident_bytes() + self.fields[-1].resident_bytes()
                + 128 * len(self.protected_boxes) + 256)


def append(field, state, face_ref, analysis, source, recipe):
    recipe = S.check(recipe)
    if not S.active(recipe):
        return field, None
    ref = P.check_ref(face_ref)
    face = state['faces'].get(ref['face_instance_id'])
    if face is None or P.face_ref(face) != ref or not face['enabled']:
        raise ValueError('Lower face requires its exact enabled canonical source face')
    from .lower_face_runtime import LowerFaceField, build
    if (type(source) is not np.ndarray or source.ndim != 3 or source.shape[2] != 3
            or not isinstance(field, FaceGeometry) or field.face_instance_id != ref['face_instance_id']
            or field.shape != tuple(source.shape[:2]) or len(field.fields) not in (4, 5, 6)
            or isinstance(field, LowerFace) or any(isinstance(part, LowerFaceField) for part in field.fields)):
        raise ValueError('Lower face cannot reuse foreign or already-lower-third geometry')
    from .people_render_runtime import verify_analysis
    landmarks = verify_analysis(face, analysis, source.shape[:2])
    # All retained same-asset neighbors count, even unresolved or disabled ones.
    boxes = tuple(tuple(other['box']) for key, other in state['faces'].items()
                  if key != ref['face_instance_id'] and other['asset_sha256'] == ref['asset_sha256'])
    lower = build(landmarks, recipe, source, analysis['excluded'],
                  backend=face['evidence']['backend'], analysis=analysis, protected_boxes=boxes)
    if lower is None or lower.state is None:
        raise ValueError('Requested lower face produced no admitted geometry; not silently skipped')
    facts = lower.facts
    if any(fact.get('requested') and not fact.get('applied') for fact in facts.values()):
        raise ValueError('Requested lower face was refused; no partial result is published')
    # First four slots, especially mouth slot 3, are retained by exact identity.
    return LowerFace(field.face_instance_id, field.shape, field.automatic,
                     (*field.fields, lower), field, boxes), facts
