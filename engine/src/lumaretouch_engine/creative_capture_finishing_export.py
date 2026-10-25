# SPDX-License-Identifier: GPL-3.0-or-later
"""Private versioned allocation request for exact edited-capture finishing.

Not a recipe field, general export mode or callable plugin. The common exporter
keeps its original stages unless this explicit request passes source/spec proof.
Runtime, numerical parity and memory acceptance remain UNRUN.
"""
from dataclasses import dataclass
import json

VERSION = 1
MAX_WORK_BYTES = 2_000_000_000


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


@dataclass(frozen=True, slots=True)
class CaptureFinishingRequest:
    version: int
    max_bytes: int
    width: int
    height: int
    source_json: str
    grading_json: str
    selective_json: str


def _request_shape(request):
    if type(request) is not CaptureFinishingRequest or type(request.version) is not int or request.version != VERSION:
        raise ValueError('Unknown private edited-capture finishing request')
    if type(request.max_bytes) is not int or not 1 <= request.max_bytes <= MAX_WORK_BYTES:
        raise ValueError('Invalid private finishing sub-budget')
    if (type(request.width) is not int or type(request.height) is not int
            or min(request.width, request.height) < 1
            or request.width * request.height > 100_000_000):
        raise ValueError('Invalid private finishing canvas extent')
    if any(type(value) is not str or not 0 < len(value) <= 1_048_576
           for value in (request.source_json, request.grading_json, request.selective_json)):
        raise ValueError('Invalid private finishing source/recipe binding')


def make_request(spec, *, max_bytes, width, height):
    from . import colour_grading_state as CG, selective_colour_state as SC
    source = getattr(spec, '_creative_capture_original_source', None)
    if source is None:
        raise ValueError('Bounded finishing requires the private original-source capture proof')
    result = CaptureFinishingRequest(VERSION, max_bytes, width, height,
        _canonical(source), _canonical(CG.check(spec.colour_grading)),
        _canonical(SC.check(spec.selective_colour)))
    _request_shape(result)
    return result


def validate_request(request, spec, *, geometry, device, tile):
    """Run before any export prepass/creative-source/early-return branch."""
    _request_shape(request)
    if device != 'cpu' or tile != 1024 or spec.creative_base is not None:
        raise ValueError('Private finishing requires the admitted original CPU capture')
    if spec.float_output is not True or spec.provenance_output is not False:
        raise ValueError('Private finishing cannot quantize or publish provenance planes')
    from .creative_edited_capture_admission import validate_spec
    selected = validate_spec(spec, finishing_version=1)
    if 'native-full-colour' not in selected.features:
        raise ValueError('Private finishing request must correspond to an active admitted stage')
    source = getattr(spec, '_creative_capture_original_source', None)
    if source is None or _canonical(source) != request.source_json:
        raise ValueError('Private finishing request belongs to another original source')
    from . import colour_grading_state as CG, selective_colour_state as SC
    if (_canonical(CG.check(spec.colour_grading)) != request.grading_json
            or _canonical(SC.check(spec.selective_colour)) != request.selective_json):
        raise ValueError('Private finishing request differs from the selected colour recipes')
    from .ops import geometry as G
    if type(geometry) not in (tuple, list) or len(geometry) != 2:
        raise ValueError('Private finishing requires its explicit capture geometry')
    if G._snapped_quarter_turn(G.check(*geometry)[-1]) is None:
        raise ValueError('Active private finishing cannot reinterpret arbitrary-angle float64 geometry')


def apply_request(request, pixels, grading_stage, selective_stage, *, cancelled):
    _request_shape(request)
    if pixels.shape != (request.height, request.width, 3):
        raise ValueError('Private finishing canvas differs from the admitted capture extent')
    if (_canonical(grading_stage.recipe) != request.grading_json
            or _canonical(selective_stage.recipe) != request.selective_json):
        raise ValueError('Actual finishing stages differ from the admitted request')
    from .creative_capture_finishing import finish_colour_np_bounded
    return finish_colour_np_bounded(pixels, grading_stage, selective_stage,
        max_bytes=request.max_bytes, cancelled=cancelled)
