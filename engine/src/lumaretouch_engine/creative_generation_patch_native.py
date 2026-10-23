"""Original ABI-1 generation pixel boundary. Authored source and fixtures UNRUN.

No model inference, fallback, runtime compilation, download or pixel fabrication.
Callers bind snapshots to immutable source/ROI/job identities before publication.
"""
import ctypes as C
from functools import lru_cache
import math
from pathlib import Path
import numpy as np

SIDE = 768
MAX_PIXELS = 32_000_000
MAX_BYTES = 2_147_483_648
P = C.POINTER(C.c_float)
CANCEL = C.CFUNCTYPE(C.c_int)


def available():
    return (Path(__file__).resolve().parent / 'bin/liblrt_creative_generation_patch.so').is_file()


@lru_cache(maxsize=1)
def native():
    path = Path(__file__).resolve().parent / 'bin/liblrt_creative_generation_patch.so'
    if not path.is_file():
        raise RuntimeError('Creative generation Rust pixel boundary is not installed; no fallback')
    lib = C.CDLL(str(path))
    lib.lrt_creative_generation_patch_abi.argtypes = []
    lib.lrt_creative_generation_patch_abi.restype = C.c_uint32
    if lib.lrt_creative_generation_patch_abi() != 1:
        raise RuntimeError('Creative generation patch ABI mismatch')
    lib.lrt_creative_generation_prepare_v1.argtypes = (
        [P, C.c_size_t, C.c_size_t, C.c_size_t] + [P, C.c_size_t] * 2
        + [C.c_size_t] * 4 + [P, C.c_size_t] * 3 + [CANCEL])
    lib.lrt_creative_generation_prepare_v1.restype = C.c_int
    lib.lrt_creative_generation_fuse_v1.argtypes = (
        [P, C.c_size_t] * 3 + [C.c_size_t, C.c_size_t, C.c_float, P, C.c_size_t, CANCEL])
    lib.lrt_creative_generation_fuse_v1.restype = C.c_int
    return lib


def _poll(cancelled):
    if cancelled():
        raise InterruptedError('Creative generation patch cancelled')


def _callback(cancelled):
    errors = []
    def poll():
        try:
            return int(bool(cancelled()))
        except BaseException as error:
            errors.append(error)
            return 1
    return CANCEL(poll), errors


def _result(code, cancelled, errors):
    if errors:
        raise errors[0]
    if code == 3:
        raise InterruptedError('Creative generation patch cancelled')
    _poll(cancelled)
    if code == 4:
        raise MemoryError('Creative generation patch resource budget exceeded')
    if code:
        messages = {1: 'invalid ABI, dimensions, settings or aliasing',
                    2: 'unsupported alpha/HDR, invalid pixels or expanded fusion coverage',
                    5: 'ROI contains no unprotected selected pixels'}
        raise ValueError('Creative generation patch refused: ' + messages.get(code, str(code)))


def _validate(array, shape, label, cancelled):
    if type(array) is not np.ndarray or array.dtype != np.float32 or array.shape != shape:
        raise ValueError(label + ' requires exact float32 shape ' + str(shape))
    for row in array:
        _poll(cancelled)
        if not np.isfinite(row).all() or np.any(row < 0) or np.any(row > 1):
            raise ValueError(label + ' requires finite [0,1] values; no clipping')


def _snapshot(array, shape, label, cancelled):
    # Reject dtype/shape before allocation. Always copy, even already contiguous
    # read-only arrays: their owning base may otherwise still be mutable.
    if type(array) is not np.ndarray or array.dtype != np.float32 or array.shape != shape:
        raise ValueError(label + ' requires exact float32 shape ' + str(shape))
    _poll(cancelled)
    snapshot = np.array(array, dtype=np.float32, order='C', copy=True)
    _validate(snapshot, shape, label, cancelled)
    snapshot.setflags(write=False)
    return snapshot


def _pair(array):
    return array.ctypes.data_as(P), array.size


def _roi(roi, width, height):
    if (type(roi) not in (tuple, list) or len(roi) != 4
            or any(type(v) is not int for v in roi)):
        raise ValueError('ROI must contain integer source x, y, width, height')
    x, y, w, h = roi
    if min(x, y) < 0 or min(w, h) < 1 or max(w, h) > SIDE or x+w > width or y+h > height:
        raise ValueError('ROI must fit the source and have sides between 1 and 768; no resizing')
    return x, y, w, h


def prepare(full_rgba, selection, protection, roi, *, cancelled=lambda: False):
    """Return immutable (encoded RGB768, binary repaint768, soft eligibility768).

    Caller must not mutate input memory during snapshot copying. Inputs are
    full-source grids, not proxies. The snapshots never alias caller buffers.
    """
    if type(full_rgba) is not np.ndarray or full_rgba.ndim != 3 or full_rgba.shape[2] != 4:
        raise ValueError('Generation requires full-source linear-sRGB premultiplied RGBA')
    h, w, _ = full_rgba.shape
    # Source inputs + independent copies + patch outputs + bounded row scratch.
    if min(h, w) < 1 or max(h, w) > 65536 or h*w > MAX_PIXELS or 48*h*w + 32_000_000 > MAX_BYTES:
        raise MemoryError('Generation full-source snapshot exceeds admitted budget')
    x, y, rw, rh = _roi(roi, w, h)
    source = _snapshot(full_rgba, (h, w, 4), 'source', cancelled)
    for row in source:
        _poll(cancelled)
        if np.any(row[:, 3] != 1):
            raise ValueError('Generation supports opaque SDR only; alpha is not flattened')
    selected = _snapshot(selection, (h, w), 'selection', cancelled)
    protected = _snapshot(protection, (h, w), 'protection', cancelled)
    for row in range(h):
        _poll(cancelled)
        active = (selected[row] > 0) & (protected[row] == 0)
        if y <= row < y + rh:
            outside = active[:x].any() or active[x+rw:].any()
        else:
            outside = active.any()
        if outside:
            raise ValueError('Selected pixels outside ROI would be discarded; enlarge context or edit selection')
    rgb = np.empty((SIDE, SIDE, 3), np.float32)
    mask = np.empty((SIDE, SIDE), np.float32)
    eligible = np.empty((SIDE, SIDE), np.float32)
    callback, errors = _callback(cancelled)
    code = native().lrt_creative_generation_prepare_v1(
        *_pair(source), w, h, *_pair(selected), *_pair(protected), x, y, rw, rh,
        *_pair(rgb), *_pair(mask), *_pair(eligible), callback)
    _result(code, cancelled, errors)
    for array, label in ((rgb, 'prepared RGB'), (mask, 'binary mask'), (eligible, 'eligibility')):
        _validate(array, array.shape, label, cancelled)
        array.setflags(write=False)
    return rgb, mask, eligible


def fuse(generated, eligible, fusion, roi_size, density=1.0, *, cancelled=lambda: False):
    """Return immutable linear-premultiplied RGBA768 from actual generated RGB.

    roi_size is (width, height). Caller authenticates frozen eligibility and
    model/candidate provenance; this bridge cannot authenticate arbitrary arrays.
    """
    if (type(roi_size) not in (tuple, list) or len(roi_size) != 2
            or any(type(v) is not int for v in roi_size)):
        raise ValueError('ROI size requires integer width and height')
    _, _, rw, rh = _roi((0, 0, *roi_size), SIDE, SIDE)
    if isinstance(density, bool) or not isinstance(density, (int, float)) or not math.isfinite(density) or not 0 <= density <= 1:
        raise ValueError('Fusion density requires finite [0,1]')
    rgb = _snapshot(generated, (SIDE, SIDE, 3), 'generated RGB', cancelled)
    cap = _snapshot(eligible, (SIDE, SIDE), 'frozen eligibility', cancelled)
    edit = _snapshot(fusion, (SIDE, SIDE), 'fusion coverage', cancelled)
    output = np.empty((SIDE, SIDE, 4), np.float32)
    callback, errors = _callback(cancelled)
    code = native().lrt_creative_generation_fuse_v1(
        *_pair(rgb), *_pair(cap), *_pair(edit), rw, rh, density, *_pair(output), callback)
    _result(code, cancelled, errors)
    _validate(output, output.shape, 'fused patch', cancelled)
    output.setflags(write=False)
    return output
