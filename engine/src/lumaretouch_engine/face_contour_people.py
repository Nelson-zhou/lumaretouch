# SPDX-License-Identifier: GPL-3.0-or-later
"""Append one source-owned contour pullback without a second geometry owner.

The four legacy geometry slots remain unchanged. Every retained foreign face,
including disabled/manual/unresolved instances, protects its source box. The
new contour runtime must refuse a complete influence window intersecting one.
AUTHORED / UNRUN: this is not full person-instance or occlusion segmentation.
"""
from dataclasses import dataclass
import numpy as np

from . import face_contour_state as C, people_state as P
from .people_geometry import FaceGeometry


@dataclass(frozen=True)
class ContouredFace(FaceGeometry):
    """Check actual composed coordinates, not only source-domain windows.

    Existing prefix fields can move a query into the contour window. Refuse
    incremental contour work that touches a retained foreign face at its output,
    prior pullback or final source-sampling footprint. No gain attenuation or
    post-hoc masking silently changes an accepted control. The unchanged prefix
    retains its own pre-existing limitations; this does not certify those fields.
    """
    prefix: object
    protected_boxes: tuple

    def evaluate(self, points):
        points = np.asarray(points, dtype=np.float64)
        prior = self.prefix.evaluate(points)
        before = points - prior
        change = self.fields[-1].evaluate(before)
        moving = np.any(change != 0, axis=1)
        if np.any(moving):
            after = before - change
            h, w = self.shape
            affected = tuple(coordinates[moving] for coordinates in (points, before, after))
            if np.any(affected[2] < 0) or np.any(affected[2] > [w-1, h-1]):
                raise ValueError('Composed face contour samples outside the genuine source; no border fill')
            bounds = tuple((coordinates.min(axis=0), coordinates.max(axis=0)) for coordinates in affected)
            for box in self.protected_boxes:
                left, top, right, bottom = np.asarray(box) * [w-1, h-1, w-1, h-1]
                # Include the entire bilinear source footprint, conservatively
                # padded by a pixel on every side for all three coordinate sets.
                for coordinates, (low, high) in zip(affected, bounds):
                    # Reject disjoint bounds before allocating per-sample masks.
                    # This is only acceleration, never a skipped nearby veto.
                    if high[0] < left-1 or low[0] > right+1 or high[1] < top-1 or low[1] > bottom+1:
                        continue
                    inside = ((coordinates[:, 0] >= left-1) & (coordinates[:, 0] <= right+1)
                              & (coordinates[:, 1] >= top-1) & (coordinates[:, 1] <= bottom+1))
                    if np.any(inside):
                        raise ValueError('Composed face contour touches another retained face; separate or reduce edits')
        return prior + change

    def resident_bytes(self):
        # Prefix holds references to the same legacy arrays, not another copy.
        # Account conservatively for the additional retained box tuples too.
        return super().resident_bytes() + 128*len(self.protected_boxes) + 256


def append(field, state, face_ref, analysis, source, recipe):
    recipe = C.check(recipe)
    if not C.active(recipe):
        return field, None
    ref = P.check_ref(face_ref)
    face = state['faces'].get(ref['face_instance_id'])
    if face is None or P.face_ref(face) != ref or not face['enabled']:
        raise ValueError('Face contour requires its exact enabled canonical source face')
    if (field.face_instance_id != ref['face_instance_id']
            or field.shape != tuple(source.shape[:2]) or len(field.fields) != 4):
        raise ValueError('Face contour cannot reuse a foreign or already-composed geometry field')
    from .people_render_runtime import verify_analysis
    landmarks = verify_analysis(face, analysis, source.shape[:2])
    boxes = tuple(tuple(other['box']) for key, other in state['faces'].items()
                  if key != ref['face_instance_id'] and other['asset_sha256'] == ref['asset_sha256'])
    from .face_contour_runtime import build
    contour = build(landmarks, recipe, source, analysis['excluded'],
                    backend=face['evidence']['backend'], analysis=analysis, protected_boxes=boxes)
    if contour is None or contour.state is None:
        raise ValueError('Requested face contour produced no admitted geometry; not silently skipped')
    refused = {key: fact.get('reason') for key, fact in contour.facts.items()
               if fact.get('requested') and not fact.get('applied')}
    if refused:
        raise ValueError('Requested face contour controls were refused: ' + str(refused))
    # Existing FaceGeometry.evaluate composes at real off-grid pullback points.
    # Existing combine validates the final joint map before its ONE sampler.
    return ContouredFace(field.face_instance_id, field.shape, field.automatic,
                         (*field.fields, contour), field, boxes), contour.facts
