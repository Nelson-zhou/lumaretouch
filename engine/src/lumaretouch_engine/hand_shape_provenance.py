# SPDX-License-Identifier: GPL-3.0-or-later
"""Strict retained hand proposal schema, not authentication of client JSON.

Only the host's retained actual producer result may enter a new recipe. This
validator cannot prove that arbitrary hashes came from inference or that any
point is visible. No proposal, even genuine, supplies its own anatomy review.
"""
from copy import deepcopy
import math
from . import hand_shape_manifest as M
from . import hand_shape_state as S


def check_proposal(value):
    keys = {'version', 'source', 'proposal_id', 'model_id', 'model_sha256',
            'backend_version', 'backend_code_sha256', 'input_rgb_sha256',
            'input_dimensions', 'points', 'handedness'}
    if (type(value) is not dict or set(value) != keys
            or type(value['version']) is not int or value['version'] != 1):
        raise ValueError('Invalid retained hand proposal schema')
    frame = S.source(value['source'])
    S.token(value['proposal_id'])
    if value['model_id'] != M.MODEL_ID or value['model_sha256'] != M.MODEL_SHA256:
        raise ValueError('Hand proposal model differs from reviewed exact version/pin')
    if value['backend_version'] != M.RUNTIME_VERSION:
        raise ValueError('Hand proposal runtime differs from reviewed packaging version')
    for key in ('backend_code_sha256', 'input_rgb_sha256', 'model_sha256'):
        S.digest(value[key])
    dims = value['input_dimensions']
    if (type(dims) is not list or len(dims) != 2
            or any(type(n) is not int or not 2 <= n <= 65536 for n in dims)):
        raise ValueError('Hand proposal must retain actual input width and height')
    from .body_pose_evidence import whole_source_shape, ORIENTATION
    whole_source_shape({**frame, 'orientation': ORIENTATION}, (dims[1], dims[0]))
    points = value['points']
    if type(points) is not list or len(points) != 21:
        raise ValueError('Hand proposal must retain exactly 21 actual raw points')
    for i, point in enumerate(points):
        if (type(point) is not dict or set(point) != {'index', 'x', 'y', 'z'}
                or type(point['index']) is not int or point['index'] != i):
            raise ValueError('Hand proposal raw point indices/schema changed')
        if any(type(point[k]) not in (int, float) or not math.isfinite(point[k])
               for k in ('x', 'y', 'z')):
            raise ValueError('Hand proposal coordinates must be actual finite numbers')
        # Out-of-frame values are meaningful negative evidence, not an error to
        # repair. Visibility is supplied only by a separate visible-source review.
    categories = value['handedness']
    if type(categories) is not list or len(categories) > 8:
        raise ValueError('Hand proposal category list exceeds its budget')
    for item in categories:
        if type(item) is not dict or set(item) != {'index', 'score', 'category_name', 'display_name'}:
            raise ValueError('Hand proposal must retain actual category fields')
        index = item['index']
        if index is not None and (type(index) is not int or not -(2**31) <= index < 2**31):
            raise ValueError('Invalid actual handedness category index')
        score = item['score']
        if type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 1:
            raise ValueError('Invalid actual handedness category score')
        for key in ('category_name', 'display_name'):
            label = item[key]
            if label is not None and (type(label) is not str or len(label) > 256):
                raise ValueError('Invalid actual handedness category label')
    return deepcopy(value)
