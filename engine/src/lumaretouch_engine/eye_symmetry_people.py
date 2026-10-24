# SPDX-License-Identifier: GPL-3.0-or-later
"""Outermost source-owned eye-symmetry pullback AFTER optional philtrum.

AUTHORED / UNRUN. Prefix lengths 4..11 preserve the complete existing prefix,
its metadata, every field by identity, and legacy mouth slot 3. No reordering,
legacy exclusions, recipe rewriting, second RGB sampler or dense-field addition.
Source protection does not promise invariance after earlier manual geometry.
"""
from dataclasses import dataclass

import numpy as np

from . import eye_symmetry_state as S, people_state as P
from .people_geometry import FaceGeometry


@dataclass(frozen=True)
class EyeSymmetry(FaceGeometry):
    prefix: object
    protected_boxes: tuple

    def evaluate(self, points):
        points = np.asarray(points, dtype=np.float64)
        if points.ndim != 2 or points.shape[1] != 2:
            raise ValueError('Composed eye symmetry needs finite Nx2 coordinates')
        from .eye_symmetry_runtime import _guard_points
        result = np.empty_like(points)
        for start in range(0, len(points), 65536):
            q = points[start:start + 65536]
            if not np.isfinite(q).all():
                raise ValueError('Composed eye symmetry needs finite Nx2 coordinates')
            symmetry = self.fields[-1].evaluate(q)
            if (type(symmetry) is not np.ndarray or symmetry.dtype != np.float64
                    or symmetry.shape != q.shape or not np.isfinite(symmetry).all()):
                raise ValueError('Composed eye symmetry received an invalid symmetry pullback')
            at = q - symmetry
            prior, baseline = self.prefix.evaluate(at), self.prefix.evaluate(q)
            if any(type(value) is not np.ndarray or value.dtype != np.float64
                   or value.shape != q.shape or not np.isfinite(value).all()
                   for value in (at, prior, baseline)):
                raise ValueError('Composed eye symmetry received an invalid prefix pullback')
            total = symmetry + prior
            if not np.isfinite(total).all():
                raise ValueError('Composed eye symmetry produced a nonfinite source pullback')
            moving = np.any(symmetry != 0., axis=1) | np.any(total != baseline, axis=1)
            # Cancellation cannot hide output, intermediate or actual-source
            # footprints. Existing owner also retains its whole-map fold guard.
            for coordinates in (q[moving], at[moving], (q - total)[moving]):
                _guard_points(coordinates, self.shape, self.protected_boxes)
            result[start:start + len(q)] = total
        return result

    def resident_bytes(self):
        return (self.prefix.resident_bytes() + self.fields[-1].resident_bytes()
                + 128 * len(self.protected_boxes) + 256)


def append(field, state, face_ref, analysis, source, recipe):
    recipe = S.check(recipe)
    if not S.active(recipe):
        return field, None
    ref = P.check_ref(face_ref)
    face = state['faces'].get(ref['face_instance_id'])
    if face is None or P.face_ref(face) != ref or not face['enabled']:
        raise ValueError('Eye symmetry requires its exact enabled canonical source face')
    from .eye_symmetry_runtime import EyeSymmetryField, build
    if (type(source) is not np.ndarray or source.ndim != 3 or source.shape[2] != 3
            or not isinstance(field, FaceGeometry) or field.face_instance_id != ref['face_instance_id']
            or field.shape != tuple(source.shape[:2]) or len(field.fields) not in range(4, 12)
            or isinstance(field, EyeSymmetry) or any(isinstance(part, EyeSymmetryField) for part in field.fields)):
        raise ValueError('Eye symmetry cannot reuse foreign or already-symmetry geometry')
    from .people_render_runtime import verify_analysis
    # This checks actual canonical float32 landmark bytes against the retained
    # digest. The owner authenticates encoded-file source identity separately;
    # decoded RGB is not asserted to hash to the encoded asset_sha256.
    landmarks = verify_analysis(face, analysis, source.shape[:2])
    boxes = tuple(tuple(other['box']) for key, other in state['faces'].items()
                  if key != ref['face_instance_id'] and other['asset_sha256'] == ref['asset_sha256'])
    symmetry = build(landmarks, recipe, source, analysis['excluded'],
                     backend=face['evidence']['backend'], analysis=analysis, protected_boxes=boxes)
    if symmetry is None:
        raise ValueError('Requested eye symmetry produced no measured result; not silently skipped')
    facts = symmetry.facts
    if any(fact.get('requested') and not fact.get('applied') for fact in facts.values()):
        raise ValueError('Requested eye symmetry was refused; no partial result is published')
    # Already-level/equal eyes have a valid measured identity field (state=None).
    # Its requested facts and native availability were still authenticated.
    return EyeSymmetry(field.face_instance_id, field.shape, field.automatic,
                       (*field.fields, symmetry), field, boxes), facts
