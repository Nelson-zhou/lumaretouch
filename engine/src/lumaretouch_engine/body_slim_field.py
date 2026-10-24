# SPDX-License-Identifier: GPL-3.0-or-later
"""Source-pixel whole-person width inverse subfield. AUTHORED / UNRUN.

One source-owned complete contour supplies real measured width. A single map
scales every point of that person horizontally by the same signed factor,
including head/hair, arms/hands and feet, without vertical movement. Only the
explicit reviewed envelope/collar and its internal background gaps may move.
"""
from copy import deepcopy
import numpy as np
from . import body_slim_state as S, body_slim_native as N
from . import body_pose_evidence as E, body_pose_manifest as M, body_pose_operations as O


class BodySlimField:
    operation_id = S.OPERATION_ID

    def __init__(self, row, support_asset, shape):
        self.record = E.check(row['record'])
        self.body_ref = self.record['body_ref']
        self.shape = tuple(shape)
        source = self.record['source']
        E.whole_source_shape(source, self.shape)
        item = row['operations'][self.operation_id]
        self.recipe = S.check(item['recipe'])
        self.input_binding_sha256 = O.field_binding(row, self.operation_id)
        self.association = deepcopy(row['association'])
        self.associated_face_id = None
        self.state = None
        self.supports = ()
        self.bounds = None
        self.plateau_bounds = None
        self.max_displacement = 0.
        h, w = self.shape
        self.render_scale = np.array([(w-1)/(source['width']-1),
                                      (h-1)/(source['height']-1)], np.float64)
        self.render_scale.setflags(write=False)
        self.facts = {
            'operation_id': self.operation_id,
            'requirement_id': S.IDS['amount'],
            'body_ref': deepcopy(self.body_ref),
            'status': 'neutral',
            'source_dimensions': [source['width'], source['height']],
            'render_dimensions': [w, h],
            'input_binding_sha256': self.input_binding_sha256,
            'runtime_quality_accepted': False,
            'hidden_anatomy_inferred': False,
            'ai_segmentation': False,
            'range_policy': 'original-local-minus1-plus1',
            'background_collar_and_internal_gaps_may_move': True,
            'whole_person_horizontal_width': True,
            'manual_complete_silhouette_required': True,
            'single_person_only': True,
            'vertical_displacement': False,
        }
        if not S.active(self.recipe):
            return
        review = item['review']
        if (review is None or review['operation_id'] != self.operation_id
                or review['body_ref'] != self.body_ref
                or review['points_sha256'] != self.record['points_sha256']
                or review['visible_anchors'] != list(S.REQUIRED_ANCHORS)
                or review['ownership_confirmed'] is not True
                or review['support_sha256'] != item['support_sha256']):
            raise ValueError('Whole-body width needs its own actual complete-person contour, all 33 points and collar review')
        asset = O.check_support_record(support_asset)
        if (E.content_digest(asset) != item['support_sha256']
                or asset['operation_id'] != self.operation_id
                or asset['kind'] != S.SUPPORT_KIND
                or asset['body_ref'] != self.body_ref or asset['source'] != source
                or asset['points_sha256'] != self.record['points_sha256']):
            raise ValueError('Whole-body width support cannot cross source, BodyRef, operation or actual pose analysis')
        support = S.policy_check_support(asset['data'], self.record)
        if self.record['model_id'] != M.MODEL_ID or self.record['model_sha256'] != M.MODEL_SHA256:
            raise ValueError('Whole-body width pose model identity changed; explicitly reanalyse')
        points = np.array([[point[key] for key in ('x', 'y', 'z', 'visibility', 'presence')]
                           for point in self.record['points']], np.float64)
        # Prepare the admitted continuous map at ORIGINAL source resolution.
        # Both decoder scales are used, including ALIGN=8 aspect rounding.
        self.state = N.prepare(points, S.vector(self.recipe), S.support_vector(support),
                               (source['height'], source['width']))
        native_facts = N.facts(self.state)
        box = np.asarray(native_facts['support_box'], np.float64).reshape(2, 2)
        plateau = np.asarray(native_facts['plateau_box'], np.float64).reshape(2, 2)
        if (not np.isfinite(box).all() or not np.isfinite(plateau).all()
                or np.any(box[0] >= box[1]) or np.any(plateau[0] >= plateau[1])):
            raise ValueError('Whole-body width native support facts are invalid')
        self.bounds = tuple(np.array(point*self.render_scale, copy=True) for point in box)
        self.plateau_bounds = tuple(np.array(point*self.render_scale, copy=True) for point in plateau)
        for point in (*self.bounds, *self.plateau_bounds):
            point.setflags(write=False)
        self.max_displacement = float(native_facts['max_displacement']*max(self.render_scale))
        if not np.isfinite(self.max_displacement) or self.max_displacement < 0:
            raise ValueError('Whole-body width native displacement bound is invalid')
        center = (self.bounds[0]+self.bounds[1])*.5
        center.setflags(write=False)
        self.supports = ((center, float(np.linalg.norm(self.bounds[1]-self.bounds[0])*.5
                                       + self.max_displacement)),)
        self.facts.update(
            status='prepared-not-rendered', backend=E.BACKEND,
            pose_model_sha256=self.record['model_sha256'],
            points_sha256=self.record['points_sha256'],
            support_sha256=item['support_sha256'], support_policy=S.SUPPORT_KIND,
            requested_recipe=deepcopy(self.recipe),
            measured_silhouette_sha256=E.content_digest(support['outline']),
            complete_person_width_transport=True,
            native_source_facts=deepcopy(native_facts),
        )

    def evaluate(self, points):
        points = self._points(points)
        if self.state is None:
            return np.zeros_like(points)
        h, w = self.shape
        render_max = (w-1, h-1)
        if np.any(points < 0) or np.any(points > np.array(render_max)):
            raise ValueError('Whole-body width query leaves the complete render domain; no clipping')
        source_points = points/self.render_scale
        source = self.record['source']
        source_max = (source['width']-1, source['height']-1)
        # Exact decoder endpoints are known identities, not approximate spatial
        # tolerances. Division can put an exact render edge one ulp beyond its
        # source edge. Canonicalize ONLY exact input endpoints; preserve every
        # interior coordinate and refuse genuinely outside queries above.
        for axis in (0, 1):
            source_points[points[:, axis] == 0, axis] = 0.
            source_points[points[:, axis] == render_max[axis], axis] = source_max[axis]
        return N.evaluate(self.state, source_points)*self.render_scale

    @staticmethod
    def _points(points):
        points = np.asarray(points, np.float64)
        if points.ndim != 2 or points.shape[1] != 2 or not np.isfinite(points).all():
            raise ValueError('Whole-body width field needs finite off-grid xy coordinates')
        return points

    def resident_bytes(self):
        return (self.render_scale.nbytes + (0 if self.state is None else self.state.nbytes)
                + sum(center.nbytes for center, _ in self.supports)
                + sum(point.nbytes for pair in (self.bounds, self.plateau_bounds)
                      if pair is not None for point in pair))

    def contains(self, points):
        points = self._points(points)
        if self.state is None:
            return np.zeros(len(points), bool)
        low, high = self.envelope()
        return np.all((points >= low) & (points <= high), axis=1)

    def envelope(self):
        if self.bounds is None:
            raise ValueError('Neutral whole-body width field has no moving support envelope')
        # Conservative inverse preimage, used for ownership refusal. Expanding
        # both axes is conservative for common-map ownership admission.
        return self.bounds[0]-self.max_displacement, self.bounds[1]+self.max_displacement
