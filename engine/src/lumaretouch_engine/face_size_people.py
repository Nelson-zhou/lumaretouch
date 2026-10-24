# SPDX-License-Identifier: GPL-3.0-or-later
"""Outermost whole-face-size pullback around the existing per-face image.

AUTHORED / UNRUN. No new image sampler or cached resized image. A size edit
geometrically resizes prior brow/nose/eye/mouth/slim/contour effects, so their
previous absolute positions are intentionally not identity-pinned. The first
four geometry slots, especially the original mouth slot, remain unchanged.
"""
from dataclasses import dataclass

import numpy as np

from . import face_size_state as S, people_state as P
from .people_geometry import FaceGeometry


@dataclass(frozen=True)
class SizedFace(FaceGeometry):
    prefix: object
    protected_boxes: tuple

    def evaluate(self, points):
        points = np.asarray(points, dtype=np.float64)
        if points.ndim != 2 or points.shape[1] != 2:
            raise ValueError('Composed face size needs finite Nx2 coordinates')
        result = np.empty_like(points)
        h, w = self.shape
        # The surrounding joint-map owner can choose larger bands. Every new
        # temporary here and every native call remains at most 65,536 points.
        for start in range(0, len(points), 65536):
            q = points[start:start + 65536]
            if not np.isfinite(q).all():
                raise ValueError('Composed face size needs finite Nx2 coordinates')
            size_delta = self.fields[-1].evaluate(q)
            at = q - size_delta
            prior = self.prefix.evaluate(at)
            total = size_delta + prior
            baseline = self.prefix.evaluate(q)
            if any(value.shape != q.shape or not np.isfinite(value).all()
                   for value in (size_delta, prior, total, baseline)):
                raise ValueError('Composed face size received an invalid prefix or size pullback')
            # Compare the actual new map too: cancellation/query relocation may
            # alter a prior field even where a size-delta-only guard is false.
            moving = np.any(size_delta != 0, axis=1) | np.any(total != baseline, axis=1)
            if np.any(moving):
                affected = tuple(value[moving] for value in (q, at, q - total))
                for coordinates in affected:
                    if np.any(coordinates < 1) or np.any(coordinates > [w - 2, h - 2]):
                        raise ValueError('Composed face size footprint is outside the genuine source margin')
                    low, high = coordinates.min(0), coordinates.max(0)
                    for normalized in self.protected_boxes:
                        box = np.asarray(normalized) * [w - 1, h - 1, w - 1, h - 1]
                        if np.any(high < box[:2] - 1) or np.any(low > box[2:] + 1):
                            continue
                        if np.any(np.all((coordinates >= box[:2] - 1)
                                         & (coordinates <= box[2:] + 1), axis=1)):
                            raise ValueError('Composed face size touches another retained face')
            result[start:start + len(q)] = total
        # No new promise is made about unchanged legacy-prefix footprints.
        # The existing combine owner still checks the final ALL-face joint map.
        return result

    def resident_bytes(self):
        # Count shared fields once while preserving a contour/slim wrapper's
        # additional retained guard metadata, which generic FaceGeometry misses.
        return (self.prefix.resident_bytes() + self.fields[-1].resident_bytes()
                + 128 * len(self.protected_boxes) + 256)


def append(field, state, face_ref, analysis, source, recipe):
    recipe = S.check(recipe)
    if not S.active(recipe):
        return field, None
    ref = P.check_ref(face_ref)
    face = state['faces'].get(ref['face_instance_id'])
    if face is None or P.face_ref(face) != ref or not face['enabled']:
        raise ValueError('Face size requires its exact enabled canonical source face')
    from .face_size_runtime import FaceSizeField, build
    if (type(source) is not np.ndarray or source.ndim != 3 or source.shape[2] != 3
            or field.face_instance_id != ref['face_instance_id']
            or field.shape != tuple(source.shape[:2]) or len(field.fields) not in (4, 5)
            or isinstance(field, SizedFace) or any(isinstance(part, FaceSizeField) for part in field.fields)):
        raise ValueError('Face size cannot reuse a foreign or already-sized geometry field')
    from .people_render_runtime import verify_analysis
    landmarks = verify_analysis(face, analysis, source.shape[:2])
    # Include every retained same-source neighbor, not only resolved/enabled ones.
    boxes = tuple(tuple(other['box']) for key, other in state['faces'].items()
                  if key != ref['face_instance_id'] and other['asset_sha256'] == ref['asset_sha256'])
    size = build(landmarks, recipe, source, analysis['excluded'],
                 backend=face['evidence']['backend'], analysis=analysis, protected_boxes=boxes)
    if size is None or size.state is None:
        raise ValueError('Requested face size produced no admitted geometry; not silently skipped')
    facts = size.facts
    if any(fact.get('requested') and not fact.get('applied') for fact in facts.values()):
        raise ValueError('Requested face size was refused; no partial result is published')
    return SizedFace(field.face_instance_id, field.shape, field.automatic,
                     (*field.fields, size), field, boxes), facts
