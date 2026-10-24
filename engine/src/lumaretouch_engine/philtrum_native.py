# SPDX-License-Identifier: GPL-3.0-or-later
"""Nose-safe philtrum policy over the original shared scalar inverse kernel.

AUTHORED / UNRUN. Reuses mid_face_native's real ABI loader, private snapshots,
Rust inverse and output checks, not its eye-to-nose anatomical operation. The
host supplies actual complete-nose-safe to above-ALL-lips measurement, plus a
measured rigid lower-face plateau. No new solver, binary, inference or fallback.
"""
import numpy as np

from . import mid_face_native as _shared

MAX_POINTS = _shared.MAX_POINTS
PARAMS_LEN = _shared.PARAMS_LEN
GAIN = _shared.GAIN
FRAME_TOLERANCE = _shared.FRAME_TOLERANCE
MIN_TAIL = _shared.MIN_TAIL
MAX_TAIL = _shared.MAX_TAIL
MIN_PLATEAU_END = _shared.MIN_PLATEAU_END
MAX_PLATEAU_END = _shared.MAX_PLATEAU_END
MIN_FORWARD_DERIVATIVE = _shared.MIN_FORWARD_DERIVATIVE
TAIL_FACTOR = 0.5


def _message(error):
    message = str(error)
    if '中庭 Rust' in message:
        return message.replace('中庭 Rust', '人中共用的中庭 Rust')
    if '中庭' in message:
        return message.replace('中庭', '人中')
    return '人中：' + message


def available():
    """Load the shipped shared library and verify ABI 1/versioned symbol.

    There is no liblrt_philtrum.so or separate native cache. Success establishes
    numerical capability only, not a usable measured gap or source acceptance.
    """
    return _shared.available()


def canonical_frame(right, down):
    """Expose shared <=1e-10 orthonormal-roundoff policy, both handednesses.

    All host measurements, support and targets must use these returned axes.
    Skewed frames are rejected; anatomical orientation is never inferred here.
    """
    try:
        return _shared.canonical_frame(right, down)
    except ValueError as error:
        raise ValueError(_message(error)) from error


def evaluate(points, params):
    """Return owned writable float64 D[N,2]=q-source(q), not forward motion.

    Exact native float64 arrays: points[N,2], params[12], N=1..65536. Parameters:
    [ox,oy,rx,ry,dx,dy,H,inner_x,outer_x,P,tail,amount]. Require measured H>0,
    0<inner_x<outer_x, P in [1.25,8], tail in [.25,4], signed amount in [-1,1],
    and tail EXACTLY max(.25,.5*(P-1)). No approximate-equality allowance.

    H is the actual gap from the complete-nose-safe plane to the plane above
    ALL lips, not the mid-face eye-to-nose height. The host must establish all
    claimed retained lips/lower-face points inside source plateau [1,P] and the
    lateral core. A measured extent D with P=D/H>8 must be refused, not rescued
    by moving planes, increasing H, truncating D, clipping P or replacing tail.
    The ABI cannot independently certify anatomical meaning or D/H provenance.

    Both shapes/dtypes are checked before copying. Shared parameter validation
    and the exact derived-tail check use a private read-only parameter snapshot;
    those same values are passed unchanged to the shared evaluator. That
    evaluator snapshots both inputs again before its existing ABI call and
    retains every original error/postcondition. Callers must not mutate inputs
    during copying. Direct neutral calls still require the native shared core;
    portable neutral does not. No dtype conversion, silent repair or fallback.
    """
    try:
        if (type(points) is not np.ndarray or points.ndim != 2
                or points.shape[1] != 2 or not 1 <= len(points) <= MAX_POINTS):
            raise ValueError('查询点必须为 [N,2]，N 在 [1,65536]')
        _shared._shape(points, (len(points), 2), 'points')
        _shared._shape(params, (PARAMS_LEN,), 'params')
        snapshot = _shared._snapshot(params)
        _shared._parameters(snapshot)
        expected_tail = max(MIN_TAIL, TAIL_FACTOR * (float(snapshot[9]) - 1.0))
        if snapshot[10] != expected_tail:
            raise ValueError('tail 必须恰为 max(0.25,0.5*(plateau_end-1))；'
                             '不改写实测比例、支持范围或调用参数')
        return _shared.evaluate(points, snapshot)
    except (ValueError, RuntimeError) as error:
        raise type(error)(_message(error)) from error
