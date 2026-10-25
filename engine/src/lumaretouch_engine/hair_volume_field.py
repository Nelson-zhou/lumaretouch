# SPDX-License-Identifier: GPL-3.0-or-later
"""Source-owned crown/side inverse field for the unchanged one-pass sampler.

No face-oval/head-size scaling, lower-hair motion, RGB/mask warp, rounding of
off-grid queries or multiplication by a dense ML mask. AUTHORED / UNRUN.
"""
from copy import deepcopy
import numpy as np
from . import hair_volume_state as S, hair_volume_native as N, hair_volume_support as A


def whole_source_shape(binding, shape):
    binding = A.source(binding)
    if (type(shape) not in (tuple, list) or len(shape) != 2
            or any(type(v) is not int or v < 2 for v in shape)):
        raise ValueError('Hair geometry needs a whole-source render shape')
    h, w = shape; sw, sh = binding['width'], binding['height']
    if (w, h) == (sw, sh):
        return
    if w > sw or h > sh or w % 8 or h % 8 or w*sh >= (h+8)*sw or h*sw >= (w+8)*sh:
        raise ValueError('Hair geometry accepts the whole source or canonical ALIGN=8 proxy, never a crop')


def binding_digest(value, recipe):
    return A.digest({'support_sha256': A.digest(A.check_record(value)), 'recipe': S.check(recipe)})


class HairVolumeField:
    operation_id = S.OPERATION_ID

    def __init__(self, record, recipe, shape):
        self.record = A.check_record(record); self.recipe = S.check(recipe)
        self.source = deepcopy(self.record['source']); self.face_ref = deepcopy(self.record['face_ref'])
        self.face_instance_id = self.face_ref['face_instance_id']; self.shape = tuple(shape)
        whole_source_shape(self.source, self.shape)
        self.input_binding_sha256 = binding_digest(record, recipe)
        self.state = None; self.boxes = (); self.supports = (); self.max_displacement = 0.
        h, w = self.shape
        self.render_scale = np.frombuffer(np.array([(w-1)/(self.source['width']-1),
                                                   (h-1)/(self.source['height']-1)], np.float64).tobytes(), np.float64)
        self.facts = {
            'operation_id': S.OPERATION_ID, 'control_ids': deepcopy(S.CONTROL_IDS),
            'face_ref': deepcopy(self.face_ref), 'source': deepcopy(self.source),
            'status': 'neutral', 'runtime_quality_accepted': False,
            'manual_observed_contours': True, 'model_is_instance_or_crown_segmentation': False,
            'hidden_anatomy_inferred': False, 'head_size_uniform_scale': False,
            'independent_image_resampling': False, 'source_owned_off_grid': True,
            'fixed_lower_and_inner_regions': True, 'background_transition_may_move': True,
            'silent_amount_attenuation': False, 'range_policy': 'original-local-signed-minus1-plus1',
            'input_binding_sha256': self.input_binding_sha256,
        }
        if not S.active(self.recipe):
            return
        self.state = N.prepare(S.vector(self.recipe), A.support_vector(self.record, self.recipe),
                               (self.source['height'], self.source['width']))
        native_facts = N.facts(self.state)
        self.max_displacement = native_facts['max_displacement'] * float(max(self.render_scale))
        boxes, supports = [], []
        for amount, raw in zip(S.amounts(self.recipe), native_facts['support_boxes']):
            if not amount:
                continue
            array = np.array(raw, np.float64).reshape(2, 2)*self.render_scale
            if np.any(array[0] >= array[1]):
                raise ValueError('Rust hair geometry returned invalid support bounds')
            array = np.frombuffer(array.tobytes(), np.float64).reshape(2, 2)
            center = np.frombuffer(((array[0]+array[1])*.5).tobytes(), np.float64)
            boxes.append(array)
            supports.append((center, float(np.linalg.norm(array[1]-array[0])*.5+self.max_displacement)))
        self.boxes, self.supports = tuple(boxes), tuple(supports)
        self.facts.update(status='prepared-not-rendered', requested_recipe=deepcopy(self.recipe),
                          native_source_facts=native_facts, support_sha256=A.digest(self.record),
                          semantic_evidence_sha256=self.record['row']['semantic_evidence_sha256'])

    @staticmethod
    def _points(points):
        out = np.asarray(points, np.float64)
        if out.ndim != 2 or out.shape[1] != 2 or not np.isfinite(out).all():
            raise ValueError('Hair geometry needs finite off-grid Nx2 coordinates')
        return out

    def evaluate(self, points):
        points = self._points(points)
        h, w = self.shape; render_max = np.array([w-1, h-1])
        if np.any(points < 0) or np.any(points > render_max):
            raise ValueError('Hair geometry query leaves the whole-source render domain')
        if self.state is None:
            return np.zeros_like(points)
        query = points/self.render_scale
        source_max = (self.source['width']-1, self.source['height']-1)
        for axis in (0, 1):
            query[points[:, axis] == 0, axis] = 0.
            query[points[:, axis] == render_max[axis], axis] = source_max[axis]
        # Only exact canonical endpoints receive floating-point normalization.
        # Interior off-grid queries are never clipped, rounded or quantized.
        return N.evaluate(self.state, query)*self.render_scale

    def envelopes(self):
        return tuple((box[0]-self.max_displacement, box[1]+self.max_displacement) for box in self.boxes)

    def contains(self, points):
        points = self._points(points); out = np.zeros(len(points), bool)
        for low, high in self.envelopes():
            out |= np.all((points >= low) & (points <= high), axis=1)
        return out

    def resident_bytes(self):
        return (self.render_scale.nbytes + (0 if self.state is None else self.state.nbytes)
                + sum(box.nbytes for box in self.boxes) + sum(center.nbytes for center, _ in self.supports))
