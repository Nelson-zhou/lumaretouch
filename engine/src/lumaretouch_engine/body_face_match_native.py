# SPDX-License-Identifier: GPL-3.0-or-later
"""Original body-to-own-face chromatic prepare extension. AUTHORED / UNRUN.

Both inputs are distinct real immutable effective-source ROIs, not matching-size
resamples. The host authenticates their same-source/same-person ownership. Face
samples determine the robust reference; body samples determine local guided
chroma and support. Current-stage luminance-preserving application is unchanged.
No Python effect fallback, learned AI, body-brightness match or runtime build.
"""
import ctypes as C
from functools import lru_cache

import numpy as np

from . import skin_evenness_native as _E
from .cpu_memory_budget import available_estimate as _available_estimate

MAX_PIXELS = _E.MAX_PIXELS
MAX_DIMENSION = _E.MAX_DIMENSION
MIN_RADIUS = _E.MIN_RADIUS
MAX_RADIUS = _E.MAX_RADIUS
MIN_REFERENCE_SAMPLES = _E.MIN_REFERENCE_SAMPLES
MAX_SHIFT = _E.MAX_SHIFT
SHIFT_TOLERANCE = _E.SHIFT_TOLERANCE
LUMINANCE_TOLERANCE = _E.LUMINANCE_TOLERANCE
ENCODING = _E.ENCODING
MAX_WORKING_BYTES = _E.MAX_WORKING_BYTES
SCRATCH_BYTES = _E.SCRATCH_BYTES
NATIVE_BODY_BYTES_PER_PIXEL = 112
NATIVE_FACE_BYTES_PER_PIXEL = 24
ADDITIONAL_BODY_BYTES_PER_PIXEL = 112
ADDITIONAL_FACE_BYTES_PER_PIXEL = 24
TOTAL_BODY_BYTES_PER_PIXEL = 128
TOTAL_FACE_BYTES_PER_PIXEL = 40
P = _E.P
CANCEL = _E.CANCEL


@lru_cache(maxsize=1)
def native():
    """Require the new optional symbol; ABI1 alone never grants this capability."""
    lib = _E.native()
    try:
        lib.lrt_body_face_match_prepare_v1.argtypes = [
            P, C.c_size_t, P, C.c_size_t, C.c_size_t, C.c_size_t,
            P, C.c_size_t, P, C.c_size_t, C.c_size_t, C.c_size_t,
            C.c_float, C.c_size_t, P, C.c_size_t, CANCEL, C.c_void_p,
        ]
        lib.lrt_body_face_match_prepare_v1.restype = C.c_int
    except AttributeError as error:
        raise RuntimeError('Body-face match Rust extension is not installed; no fallback was applied') from error
    return lib


def available():
    """Symbol/ABI availability only, not valid support or photographic acceptance."""
    try:
        native()
        return True
    except (OSError, RuntimeError, AttributeError):
        return False


def _pixels(shape, label):
    if type(shape) not in (tuple, list) or len(shape) != 2:
        raise ValueError(label + ' requires exact (height,width)')
    height, width = shape
    if (type(width) is not int or type(height) is not int
            or min(width, height) < 1 or max(width, height) > MAX_DIMENSION):
        raise ValueError(label + ' dimensions are outside the supported range')
    return height * width


def memory_estimate(body_shape, face_shape):
    """Pure combined additional estimate; counts both actual source ROI sizes.

    Body: snapshots16 + output8 + native scratch88 =112 B/pixel. Face:
    snapshots16 + robust-reference scratch8 =24 B/pixel. The scratch phases do
    not coexist; adding them is deliberately conservative. Existing caller RGB
    and coverage add16 B/pixel on EACH grid. Include8MiB validation allowance.
    Aggregate pixel ceiling32M and total budget4GiB; no native load, allocation,
    live memory probe, proxy solve or assumption that face shape equals body.
    """
    body = _pixels(body_shape, 'Body source memory estimate')
    face = _pixels(face_shape, 'Own-face source memory estimate')
    total = (TOTAL_BODY_BYTES_PER_PIXEL * body
             + TOTAL_FACE_BYTES_PER_PIXEL * face + SCRATCH_BYTES)
    if body + face > MAX_PIXELS or total > MAX_WORKING_BYTES:
        raise MemoryError('Body-face match exceeds its combined memory/pixel budget; no proxy fallback')
    return (ADDITIONAL_BODY_BYTES_PER_PIXEL * body
            + ADDITIONAL_FACE_BYTES_PER_PIXEL * face + SCRATCH_BYTES)


def _poll(cancelled):
    if cancelled():
        raise InterruptedError('Body-face match cancelled; private output discarded')


def _result(code, cancelled, errors):
    if errors:
        raise errors[0]
    if code == 4:
        raise InterruptedError('Body-face match cancelled; private output discarded')
    _poll(cancelled)
    if code == 5:
        raise MemoryError('Body-face match Rust combined resource budget exceeded')
    if code == 6:
        raise RuntimeError('Body-face match Rust panic contained; private output discarded')
    if code:
        messages = {1: 'invalid ABI, lengths, dimensions or buffer aliasing',
                    2: 'invalid amount or measured body-scale radius',
                    3: 'nonfinite, non-SDR RGB/coverage or numerical refusal',
                    7: 'insufficient reliable own-body support or own-face reference (64 each required)',
                    8: 'insufficient supported body-source guided context'}
        raise ValueError('Body-face match Rust refused: ' + messages.get(code, str(code)))


def prepare(body_rgb, body_coverage, face_rgb, face_coverage, amount, *, radius,
            cancelled=lambda: False):
    """Return owned read-only body-grid float32 HWC2 log-chroma displacement.

    Body ROI contains all admitted own-body support plus a real2r+1 source halo;
    face ROI contains EVERY admitted own-face reference sample. They need not
    have equal shapes. Neither may be current edited pixels or synthetic face
    pixels expanded onto a body grid. Never solve either reference per tile.
    The host binds exact effective source, face/body/person, source observations,
    exclusions, review and measured source-grid body scale. Arrays cannot prove
    these identities. Face coverage grants reference use, never output writes.

    All four arrays are exact native float32, finite SDR[0,1] and independently
    snapshotted even for amount zero. Active body and face each need64 samples
    with coverage*photometric_reliability>=.75. Only the FACE median is the target;
    body uses the existing guided solve and must have supported local context.
    Radius is strict int4..256. Neither failure masquerades as neutral success.
    """
    amount = _E._control(amount)
    if type(radius) is not int or not MIN_RADIUS <= radius <= MAX_RADIUS:
        raise ValueError('Body-face match radius requires an integer in [4,256] from measured body scale')
    body_shape = _E._rgb_shape(body_rgb, 'Original body source RGB')
    face_shape = _E._rgb_shape(face_rgb, 'Original own-face source RGB')
    _E._shape(body_coverage, body_shape, 'Body skin coverage')
    _E._shape(face_coverage, face_shape, 'Own-face skin coverage')
    if not callable(cancelled):
        raise TypeError('cancelled must be a callable')
    _poll(cancelled)
    estimate = memory_estimate(body_shape, face_shape)
    if estimate > _available_estimate():
        raise MemoryError('Insufficient CPU memory for both body-face source snapshots and native scratch')
    body = _E._snapshot(body_rgb, body_rgb.shape, 'Original body source RGB', cancelled)
    body_weight = _E._snapshot(body_coverage, body_shape, 'Body skin coverage', cancelled)
    face = _E._snapshot(face_rgb, face_rgb.shape, 'Original own-face source RGB', cancelled)
    face_weight = _E._snapshot(face_coverage, face_shape, 'Own-face skin coverage', cancelled)
    _poll(cancelled)
    lib = native()
    _poll(cancelled)
    output = np.empty((*body_shape, 2), dtype=np.float32, order='C')
    callback, errors = _E._callback(cancelled)
    code = lib.lrt_body_face_match_prepare_v1(
        body.ctypes.data_as(P), body.size, body_weight.ctypes.data_as(P), body_weight.size,
        body_shape[1], body_shape[0], face.ctypes.data_as(P), face.size,
        face_weight.ctypes.data_as(P), face_weight.size, face_shape[1], face_shape[0],
        amount, radius, output.ctypes.data_as(P), output.size, callback, None,
    )
    _result(code, cancelled, errors)
    for row, columns in _E._blocks(output.shape):
        _poll(cancelled)
        block = output[row, columns]
        if not _E._valid_shift(block):
            raise RuntimeError('Body-face match returned invalid or unbounded log-chroma field; discarded')
        protected = body_weight[row, columns] == 0.0
        if amount == 0.0:
            protected = np.ones_like(protected, dtype=bool)
        if np.any(block[protected] != 0.0):
            raise RuntimeError('Body-face match returned nonzero neutral or unsupported shift; discarded')
    _poll(cancelled)
    output.setflags(write=False)
    return output


# Exact existing pointwise current-Y application; no new body/face brightness
# operation and no second numerical implementation. New preparation/capability
# still requires the optional extension even if the legacy ABI1 apply exists.
apply = _E.apply
application_memory_estimate = _E.application_memory_estimate
