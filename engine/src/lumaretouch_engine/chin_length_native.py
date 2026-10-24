# SPDX-License-Identifier: GPL-3.0-or-later
"""Chin-length policy bridge to the original shared scalar inverse kernel.

AUTHORED / UNRUN. Reuses lower_face_native's actual ABI loader, bounded snapshots,
Rust inverse and output checks, not the lower-face operation or its anatomy.
The chin-length host supplies an origin strictly below ALL measured lip points
and H to actual chin proxy 152. No fallback, inference, sampling or runtime build.
"""
import numpy as np

from . import lower_face_native as _shared

MAX_POINTS = _shared.MAX_POINTS
PARAMS_LEN = _shared.PARAMS_LEN
GAIN = _shared.GAIN
FRAME_TOLERANCE = _shared.FRAME_TOLERANCE
TAIL = 0.5
MIN_FORWARD_DERIVATIVE = 0.7


def _message(error):
    message = str(error)
    if '下庭 Rust' in message:
        return message.replace('下庭 Rust', '下巴长短共用的下庭 Rust')
    if '下庭' in message:
        return message.replace('下庭', '下巴长短')
    return '下巴长短：' + message


def available():
    """Verify the shipped shared library, ABI 1 and versioned evaluate symbol.

    There is deliberately no liblrt_chin_length.so or independent native cache.
    Readiness does not imply usable below-lips anatomy, support or image quality.
    """
    return _shared.available()


def canonical_frame(right, down):
    """Shared <=1e-10 orthonormal-roundoff convention, both handednesses.

    The host uses the returned frame for all measurement, support and targets.
    Anatomical orientation is not inferred and skewed frames are not repaired.
    """
    try:
        return _shared.canonical_frame(right, down)
    except ValueError as error:
        raise ValueError(_message(error)) from error


def evaluate(points, params):
    """Return owned writable float64 D[N,2]=q-source(q), not forward motion.

    Exact native float64 arrays: points[N,2], params[11], N=1..65536.
    Params: [ox,oy,rx,ry,dx,dy,H,inner_x,outer_x,tail,amount]. Require tail==.5
    exactly, H>0, 0<inner_x<outer_x and finite amount in [-1,1]. Geometry and
    points share source units. The host must measure below ALL lips, not use the
    nose-to-chin lower-third interval, and must admit actual chin152 in the core.
    All inherited boundary validation/postconditions remain authoritative.

    Both shapes/dtypes are refused before copying. Take a private parameter
    snapshot before the chin-specific tail check so the shared evaluator uses
    the same validated values, even if the caller later mutates its parameters.
    The shared boundary takes its own immutable input snapshots before the ABI.
    Callers must not mutate inputs during copying. No parameter is replaced,
    clipped, inferred or reinterpreted. Even direct neutral calls require native.
    """
    try:
        if (type(points) is not np.ndarray or points.ndim != 2
                or points.shape[1] != 2 or not 1 <= len(points) <= MAX_POINTS):
            raise ValueError('查询点必须为 [N,2]，N 在 [1,65536]')
        _shared._shape(points, (len(points), 2), 'points')
        _shared._shape(params, (PARAMS_LEN,), 'params')
        snapshot = _shared._snapshot(params)
        if snapshot[9] != TAIL:
            raise ValueError('tail 必须恰为 0.5；不改写调用参数或套用其他支持范围')
        return _shared.evaluate(points, snapshot)
    except (ValueError, RuntimeError) as error:
        raise type(error)(_message(error)) from error
