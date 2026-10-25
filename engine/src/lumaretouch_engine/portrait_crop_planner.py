# SPDX-License-Identifier: GPL-3.0-or-later
"""Original rule-based portrait framing, without image rendering or approval.

Production plan() requires the Rust core. reference_plan() is an explicitly
named scalar oracle for future fixtures, never an automatic runtime fallback.
Both are AUTHORED / UNRUN. Existing ops/geometry.py remains the image sampler.
"""
from __future__ import annotations

import math

from . import portrait_crop_state as S
from . import portrait_crop_native as N


def capability():
    return N.capability()


def _inside(point, bounds):
    left, top, right, bottom = bounds
    return left <= point[0] <= right and top <= point[1] <= bottom


def _reference_vector(width, height, anchors, rules):
    head_height = anchors['chin'][1] - anchors['crown'][1]
    crop_height = head_height / rules['head_fraction']
    crop_width = rules['aspect_ratio'] * crop_height
    top = anchors['crown'][1] - rules['headroom_fraction'] * crop_height
    left = anchors['face_center'][0] - rules['horizontal_position'] * crop_width
    continuous = [left, top, left + crop_width, top + crop_height]
    if (not all(math.isfinite(v) for v in continuous + [crop_width, crop_height])
            or crop_width <= 0.0 or crop_height <= 0.0
            or not 0.0 <= continuous[0] < continuous[2] <= width
            or not 0.0 <= continuous[1] < continuous[3] <= height
            or not all(_inside(anchors[name], continuous) for name in S.ANCHOR_NAMES)):
        raise S.PortraitCropError('infeasible', 'Requested portrait composition does not fit the image and reviewed anchors; no clamp or padding')
    # Reproduce the existing geometry._cut arithmetic in the specified order:
    # normalize first, multiply by dimension, then Python round (ties to even).
    # Its clamps/minimum-one-pixel repair are NOT admitted by this planner.
    ideal_normalized = [continuous[0] / width, continuous[1] / height,
                        continuous[2] / width, continuous[3] / height]
    pixels = [int(round(n * v)) for n, v in zip((width, height, width, height), ideal_normalized)]
    l, t, r, b = pixels
    if (not 0 <= l < r <= width or not 0 <= t < b <= height
            or not all(_inside(anchors[name], pixels) for name in S.ANCHOR_NAMES)):
        raise S.PortraitCropError('pixel_rounding', 'Rounded pixel edges collapse the crop or exclude a reviewed anchor')
    normalized = [l / width, t / height, r / width, b / height]
    cw, ch = r - l, b - t
    achieved = [cw / ch, (anchors['crown'][1] - t) / ch,
                head_height / ch, (anchors['face_center'][0] - l) / cw,
                (anchors['face_center'][1] - t) / ch, head_height, float(cw), float(ch)]
    return continuous + normalized + [float(v) for v in pixels] + achieved


def _inputs(width, height, anchors, rules):
    S.check_size(width, height)
    return S.check_anchors(anchors, width, height), S.check_rules(rules)


def _record(width, height, anchors, rules, vector, backend):
    continuous = vector[:4]
    pixels = [int(v) for v in vector[8:12]]
    names = (*S.RULE_NAMES, 'vertical_position')
    crop_height = (anchors['chin'][1] - anchors['crown'][1]) / rules['head_fraction']
    requested = {name: rules[name] for name in S.RULE_NAMES}
    requested['vertical_position'] = (anchors['face_center'][1] - continuous[1]) / crop_height
    achieved = dict(zip(names, vector[12:17]))
    achieved['head_height_pixels'] = vector[17]
    return {'version': 1, 'convention': S.CONVENTION, 'operation_id': S.OPERATION_ID,
            'rotation_degrees': 0.0, 'source_size': [width, height],
            'anchors': anchors, 'rules': rules, 'continuous_rect_pixels': continuous,
            'rect_normalized': vector[4:8], 'pixel_bounds': pixels,
            'output_size': [int(vector[18]), int(vector[19])],
            'requested': requested, 'achieved': achieved,
            'is_full_frame': pixels == [0, 0, width, height], 'backend': backend}


def plan(width, height, anchors, rules):
    """Native-only production plan. The result never authorizes applying a crop.

    Includes a strict independently calculated numerical cross-check. A bad or
    unavailable native result cannot be replaced by the reference answer.
    Source capture, photographic review, stale-state checks, preview, apply,
    undo, project persistence and export remain the existing host's ownership.
    """
    anchors, rules = _inputs(width, height, anchors, rules)
    reference = _reference_vector(width, height, anchors, rules)
    vector = N.solve(width, height, anchors, rules)
    if (len(vector) != N.RESULT_LENGTH
            or vector[4:12] != reference[4:12]
            or vector[18:20] != reference[18:20]
            or not all(math.isclose(a, b, rel_tol=2e-14, abs_tol=0.0)
                       for a, b in zip(vector, reference))):
        raise RuntimeError('Portrait crop native/reference geometry disagreement; no plan published')
    return _record(width, height, anchors, rules, vector, S.BACKEND)


def reference_plan(width, height, anchors, rules):
    """Explicit analytical oracle, not a deployed backend or acceptance evidence."""
    anchors, rules = _inputs(width, height, anchors, rules)
    return _record(width, height, anchors, rules,
                   _reference_vector(width, height, anchors, rules), 'python-reference-unrun')
