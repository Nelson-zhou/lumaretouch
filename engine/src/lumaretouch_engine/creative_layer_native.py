"""Original Rust image-layer bridge; authored, execution and QA UNRUN.

Only packaged ABI v1 is used. No runtime compiler, Python pixel fallback, tone
mapping, inference, image download, or persistent mutation. Import-only sRGB
decoding is explicit, never implicitly applied during layer compositing.
Arrays are float32 linear-sRGB D65 premultiplied RGBA, including signed/HDR RGB.
The explicitly named display_rgba port alone mattes/clips/quantizes for display.
"""
from __future__ import annotations

import ctypes as C
from dataclasses import dataclass, field
from functools import lru_cache
import math
from pathlib import Path
from typing import Any, Callable

MAX_SOURCE_PIXELS = 100_000_000
MAX_SOURCE_BYTES = MAX_SOURCE_PIXELS * 16
MAX_MASK_BYTES = MAX_SOURCE_PIXELS * 4
MAX_TILE_PIXELS = 65_536
MAX_TILE_BYTES = MAX_TILE_PIXELS * 16
HDR_STRAIGHT_LIMIT = 65_504.0
MAX_EXACT_CANVAS_COORD = 2 ** 50
ENCODING = 'linear-srgb-d65'
BLEND_MODES = ('normal', 'multiply', 'screen', 'lighten', 'darken')
IDENTITY = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
P = C.POINTER(C.c_float)
DP = C.POINTER(C.c_double)
U8P = C.POINTER(C.c_uint8)
_TOKEN = object()
_ERRORS = {
    1: 'invalid buffer layout, extent, overlap, or resource budget',
    2: 'invalid blend mode, opacity, or inverse affine geometry',
    3: 'nonfinite pixels, invalid alpha/mask, or nonzero RGB at zero alpha',
    4: 'bounded tile staging allocation failed',
    5: 'composited result cannot be represented as finite float32',
    6: 'contained native compositor failure',
}


class CreativeLayerNativeUnavailable(RuntimeError):
    """The packaged native component is missing, incompatible, or unloadable."""


class CreativeLayerNativeRejected(ValueError):
    def __init__(self, code: int, operation: str):
        self.code = code
        super().__init__(f'{operation}: {_ERRORS.get(code, "unknown native status")} ({code})')


@lru_cache(maxsize=1)
def native():
    path = Path(__file__).resolve().parent / 'bin' / 'liblrt_creative_layers.so'
    if not path.is_file():
        raise CreativeLayerNativeUnavailable('创意图层 Rust 核心未安装；需要完整打包版本，不会在运行时编译')
    try:
        lib = C.CDLL(str(path))
        lib.lrt_creative_layers_abi.argtypes = []
        lib.lrt_creative_layers_abi.restype = C.c_uint32
        if lib.lrt_creative_layers_abi() != 1:
            raise CreativeLayerNativeUnavailable('Creative image-layer ABI mismatch')
        for name in ('lrt_creative_validate_rgba', 'lrt_creative_validate_mask'):
            function = getattr(lib, name)
            function.argtypes = [P, C.c_size_t, C.c_size_t, C.c_size_t]
            function.restype = C.c_int32
        lib.lrt_creative_linearize_rgba.argtypes = [P, P, C.c_size_t]
        lib.lrt_creative_linearize_rgba.restype = C.c_int32
        lib.lrt_creative_linearize_extended_rgba.argtypes = [P, P, C.c_size_t]
        lib.lrt_creative_linearize_extended_rgba.restype = C.c_int32
        lib.lrt_creative_encode_opaque_sdr_rgb.argtypes = [P, P, C.c_size_t]
        lib.lrt_creative_encode_opaque_sdr_rgb.restype = C.c_int32
        lib.lrt_creative_display_rgb8.argtypes = [P, U8P, C.c_size_t, P]
        lib.lrt_creative_display_rgb8.restype = C.c_int32
        lib.lrt_creative_composite_tile.argtypes = [
            P, C.c_size_t, C.c_size_t, C.c_size_t,
            P, P, C.c_size_t, C.c_size_t, C.c_size_t,
            DP, C.c_double, C.c_double, C.c_float, C.c_uint32,
            P, C.c_size_t,
        ]
        lib.lrt_creative_composite_tile.restype = C.c_int32
    except (OSError, AttributeError) as exc:
        raise CreativeLayerNativeUnavailable('Creative image-layer Rust library cannot be loaded') from exc
    return lib


def _numpy():
    # Importing the project/module does not load NumPy or the shared library.
    import numpy as np
    return np


def _check_cancelled(cancelled: Callable[[], bool]) -> None:
    if cancelled():
        raise InterruptedError('Creative image-layer render cancelled')


def _array(pixels: Any, channels: int | None, maximum: int):
    np = _numpy()
    dimensions = 2 if channels is None else 3
    if (not isinstance(pixels, np.ndarray) or pixels.dtype != np.dtype(np.float32)
            or not pixels.dtype.isnative or pixels.ndim != dimensions
            or (channels is not None and pixels.shape[2] != channels)):
        raise ValueError('Creative layers require native-endian float32 image arrays')
    height, width = pixels.shape[:2]
    if width < 1 or height < 1 or width * height > maximum:
        raise ValueError('Creative image extent exceeds the declared pixel budget')
    return np, width, height


def _immutable_payload(pixels, np) -> bytes:
    """Reuse a whole immutable import blob, otherwise take one owned snapshot."""
    owner = pixels
    while isinstance(owner, np.ndarray) and owner.base is not None:
        owner = owner.base
    while isinstance(owner, memoryview):
        owner = owner.obj
    if (isinstance(owner, bytes) and pixels.flags.c_contiguous
            and len(owner) == pixels.nbytes
            and pixels.ctypes.data == np.frombuffer(owner, dtype=np.uint8).ctypes.data):
        return owner
    return pixels.tobytes(order='C')


def linearize_rgba(srgb_rgba: Any, *, cancelled: Callable[[], bool] = lambda: False):
    """Convert straight [0,1] encoded-sRGB RGBA to premultiplied linear float32.

    The file importer must normalize uint8/uint16 and apply ICC colour management
    first. This explicitly named transfer is not applied to existing linear/HDR
    sources. No 8-bit intermediate. Alpha is copied, RGB is decoded then weighted.
    Full output stays private until every bounded Rust call and cancellation check
    succeeds. Source must not be concurrently edited during conversion.
    """
    _check_cancelled(cancelled)
    np, width, height = _array(srgb_rgba, 4, MAX_SOURCE_PIXELS)
    lib = native()
    output = np.empty((height, width, 4), dtype=np.float32)
    for y in range(height):
        for x in range(0, width, MAX_TILE_PIXELS):
            _check_cancelled(cancelled)
            # Only one bounded input chunk is copied, never a second full raster.
            part = srgb_rgba[y, x:x + MAX_TILE_PIXELS]
            immutable = np.frombuffer(part.tobytes(order='C'), dtype='=f4')
            destination = output[y, x:x + MAX_TILE_PIXELS]
            code = lib.lrt_creative_linearize_rgba(
                immutable.ctypes.data_as(P), destination.ctypes.data_as(P), immutable.size,
            )
            if code:
                raise CreativeLayerNativeRejected(code, 'Linearize imported creative RGBA')
    _check_cancelled(cancelled)
    return output


def encode_opaque_sdr_rgb(rgba: Any, *, cancelled: Callable[[], bool] = lambda: False):
    """Strict float32 encoded-sRGB bridge for legacy opaque-SDR RGB exporters.

    Input is canonical premultiplied linear RGBA. Every alpha must be exactly one
    and every RGB must be finite in [0,1]. Otherwise the entire operation fails;
    it never silently drops transparency, mattes, clamps HDR, or quantizes to 8bit.
    The input stays unchanged; only the successfully completed private RGB output
    is returned. Source must not be concurrently edited during conversion.
    """
    _check_cancelled(cancelled)
    np, width, height = _array(rgba, 4, MAX_SOURCE_PIXELS)
    lib = native()
    output = np.empty((height, width, 3), dtype=np.float32)
    for y in range(height):
        for x in range(0, width, MAX_TILE_PIXELS):
            _check_cancelled(cancelled)
            part = rgba[y, x:x + MAX_TILE_PIXELS]
            immutable = np.frombuffer(part.tobytes(order='C'), dtype='=f4')
            destination = output[y, x:x + MAX_TILE_PIXELS]
            code = lib.lrt_creative_encode_opaque_sdr_rgb(
                immutable.ctypes.data_as(P), destination.ctypes.data_as(P), immutable.size,
            )
            if code:
                raise CreativeLayerNativeRejected(code, 'Opaque SDR export requires alpha=1 and RGB in [0,1]')
    _check_cancelled(cancelled)
    return output


def linearize_extended_rgba(srgb_rgba: Any, *, cancelled: Callable[[], bool] = lambda: False):
    """Capture explicit signed extended-sRGB straight RGBA into canonical assets.

    This is not the ordinary SDR-file import port. Input RGB must be finite;
    alpha is coverage in [0,1]. Rust uses the odd-sign extended inverse sRGB
    transfer, validates decoded straight |RGB| <= 65504, then premultiplies. The
    rounded stored result is checked against 65504*alpha; violations reject the
    whole conversion, never clip. Source must not change during conversion.
    """
    _check_cancelled(cancelled)
    np, width, height = _array(srgb_rgba, 4, MAX_SOURCE_PIXELS)
    lib = native()
    output = np.empty((height, width, 4), dtype=np.float32)
    for y in range(height):
        for x in range(0, width, MAX_TILE_PIXELS):
            _check_cancelled(cancelled)
            part = srgb_rgba[y, x:x + MAX_TILE_PIXELS]
            immutable = np.frombuffer(part.tobytes(order='C'), dtype='=f4')
            destination = output[y, x:x + MAX_TILE_PIXELS]
            code = lib.lrt_creative_linearize_extended_rgba(
                immutable.ctypes.data_as(P), destination.ctypes.data_as(P), immutable.size,
            )
            if code:
                raise CreativeLayerNativeRejected(code, 'Capture extended-sRGB creative RGBA')
    _check_cancelled(cancelled)
    return output


def display_rgba(rgba: Any, *, matte, cancelled: Callable[[], bool] = lambda: False):
    """DISPLAY ONLY: explicit linear-sRGB matte and SDR clipping to uint8 RGB.

    This function returns HWC3 RGB, despite accepting canonical HWC4 RGBA. Matte
    is required: three finite linear-sRGB [0,1] values, never implicit black/white.
    Rust composites onto that opaque matte, clips the presentation copy to [0,1],
    encodes sRGB and rounds to RGB8. Original signed/HDR/alpha source is untouched.
    Do not call this for source persistence, baked-base storage or actual export.
    """
    _check_cancelled(cancelled)
    if (not isinstance(matte, (tuple, list)) or len(matte) != 3
            or any(isinstance(v, bool) or not isinstance(v, (int, float))
                   or not 0.0 <= v <= 1.0 or not math.isfinite(v) for v in matte)):
        raise ValueError('Display matte must contain three explicit linear-sRGB values in [0,1]')
    np, width, height = _array(rgba, 4, MAX_SOURCE_PIXELS)
    lib = native()
    output = np.empty((height, width, 3), dtype=np.uint8)
    background = (C.c_float * 3)(*matte)
    for y in range(height):
        for x in range(0, width, MAX_TILE_PIXELS):
            _check_cancelled(cancelled)
            part = rgba[y, x:x + MAX_TILE_PIXELS]
            immutable = np.frombuffer(part.tobytes(order='C'), dtype='=f4')
            destination = output[y, x:x + MAX_TILE_PIXELS]
            code = lib.lrt_creative_display_rgb8(
                immutable.ctypes.data_as(P), destination.ctypes.data_as(U8P), immutable.size, background,
            )
            if code:
                raise CreativeLayerNativeRejected(code, 'Display creative RGBA')
    _check_cancelled(cancelled)
    return output


@dataclass(frozen=True, slots=True)
class FrozenRGBA:
    """Full-resolution immutable source; construct with freeze_rgba, not directly."""
    width: int
    height: int
    _payload: bytes = field(repr=False)
    _token: object = field(repr=False, compare=False)

    @property
    def pixels(self):
        # A new view prevents clients changing shape/flags of our internal view.
        return _numpy().frombuffer(self._payload, dtype='=f4').reshape(self.height, self.width, 4)

    @property
    def nbytes(self) -> int:
        return len(self._payload)


@dataclass(frozen=True, slots=True)
class FrozenMask:
    """Source-local immutable coverage, same extent as the corresponding source."""
    width: int
    height: int
    _payload: bytes = field(repr=False)
    _token: object = field(repr=False, compare=False)

    @property
    def pixels(self):
        return _numpy().frombuffer(self._payload, dtype='=f4').reshape(self.height, self.width)

    @property
    def nbytes(self) -> int:
        return len(self._payload)


def freeze_rgba(pixels: Any, *, encoding: str = ENCODING, premultiplied: bool = True,
                cancelled: Callable[[], bool] = lambda: False) -> FrozenRGBA:
    """Freeze real decoded/imported pixels as an immutable owned bytes snapshot.

    This is not an sRGB decoder or alpha premultiplier. The import colour pipeline
    must supply the explicitly declared colour/alpha contract. Validation is Rust.
    Whole immutable bytes-backed arrays are reused; other owners need one copy.
    The caller's allocation + one immutable snapshot may coexist during import.
    """
    if encoding != ENCODING or premultiplied is not True:
        raise ValueError('Creative layers require explicitly premultiplied linear-sRGB D65 RGBA')
    _check_cancelled(cancelled)
    if isinstance(pixels, FrozenRGBA):
        if pixels._token is not _TOKEN:
            raise ValueError('Creative source was not frozen by this module')
        return pixels
    np, width, height = _array(pixels, 4, MAX_SOURCE_PIXELS)
    lib = native()
    # NumPy's writeable=False alone is insufficient: a caller may still mutate
    # another alias or turn its flag back on. Bytes ownership is irreversible.
    payload = _immutable_payload(pixels, np)
    view = np.frombuffer(payload, dtype='=f4')
    code = lib.lrt_creative_validate_rgba(view.ctypes.data_as(P), view.size, width, height)
    if code:
        raise CreativeLayerNativeRejected(code, 'Freeze creative source')
    _check_cancelled(cancelled)
    return FrozenRGBA(width, height, payload, _TOKEN)


def freeze_mask(pixels: Any, *, cancelled: Callable[[], bool] = lambda: False) -> FrozenMask:
    _check_cancelled(cancelled)
    if isinstance(pixels, FrozenMask):
        if pixels._token is not _TOKEN:
            raise ValueError('Creative mask was not frozen by this module')
        return pixels
    np, width, height = _array(pixels, None, MAX_SOURCE_PIXELS)
    lib = native()
    payload = _immutable_payload(pixels, np)
    view = np.frombuffer(payload, dtype='=f4')
    code = lib.lrt_creative_validate_mask(view.ctypes.data_as(P), view.size, width, height)
    if code:
        raise CreativeLayerNativeRejected(code, 'Freeze creative mask')
    _check_cancelled(cancelled)
    return FrozenMask(width, height, payload, _TOKEN)


def composite_tile(backdrop: Any, source: FrozenRGBA, *, inverse_affine=IDENTITY,
                   canvas_origin=(0, 0), opacity: float = 1.0,
                   blend_mode: str = 'normal', mask: FrozenMask | None = None,
                   cancelled: Callable[[], bool] = lambda: False):
    """Return a private H×W×4 float32 tile, never mutate any caller image.

    Source is a full-resolution immutable image. Destination coordinates are
    canvas_origin + (x+0.5, y+0.5). Inverse ordering is (a,b,c,d,e,f):
    sx=a*cx+b*cy+c; sy=d*cx+e*cy+f. Pixel centers in source are also n+0.5.
    Thus identity maps unchanged, and translation +tx/+ty uses c=-tx,f=-ty.
    Sampling uses four source taps and transparent exterior, not tile-clamped
    edges. Mask coverage multiplies each source texel before bilinear sampling.

    Isolated groups are composed by the caller into a transparent private tile,
    then submitted once with the group's opacity/mode/mask. For a flattened tile
    at canvas (x,y), use inverse (1,0,-x,0,1,-y), not the global identity.
    Cancellation is checked before and after each bounded native tile operation;
    the caller is responsible for generation/snapshot checks before publication.
    """
    _check_cancelled(cancelled)
    if not isinstance(source, FrozenRGBA) or source._token is not _TOKEN:
        raise ValueError('Freeze the actual imported RGBA image before compositing')
    if blend_mode not in BLEND_MODES:
        raise ValueError('Unsupported creative image-layer blend mode')
    if (isinstance(opacity, bool) or not isinstance(opacity, (int, float))
            or not 0.0 <= opacity <= 1.0 or not math.isfinite(opacity)):
        raise ValueError('Opacity must be a finite value in [0,1]')
    if (not isinstance(canvas_origin, tuple) or len(canvas_origin) != 2
            or any(type(v) is not int or abs(v) > MAX_EXACT_CANVAS_COORD for v in canvas_origin)):
        raise ValueError('Canvas origin requires two exact, representable integer coordinates')
    if not isinstance(inverse_affine, (tuple, list)) or len(inverse_affine) != 6:
        raise ValueError('Inverse affine requires six ordered coefficients')
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in inverse_affine):
        raise ValueError('Inverse affine coefficients must be finite numbers')
    try:
        coefficients = tuple(float(v) for v in inverse_affine)
    except (OverflowError, ValueError) as exc:
        raise ValueError('Inverse affine coefficients must be finite numbers') from exc
    if not all(math.isfinite(v) for v in coefficients):
        raise ValueError('Inverse affine coefficients must be finite numbers')
    determinant = coefficients[0] * coefficients[4] - coefficients[1] * coefficients[3]
    if not math.isfinite(determinant) or determinant == 0.0:
        raise ValueError('Inverse affine must be finite and invertible')
    if mask is not None and (not isinstance(mask, FrozenMask) or mask._token is not _TOKEN
            or (mask.width, mask.height) != (source.width, source.height)):
        raise ValueError('Frozen mask extent must match the source image')
    np, width, height = _array(backdrop, 4, MAX_TILE_PIXELS)
    lib = native()
    # C calls release the GIL. Protect backdrop from simultaneous caller edits,
    # including aliases, instead of relying on a temporary read-only flag.
    base = np.frombuffer(backdrop.tobytes(order='C'), dtype='=f4')
    output = np.empty((height, width, 4), dtype=np.float32)
    source_pixels = source.pixels
    mask_pixels = mask.pixels if mask is not None else None
    transform = (C.c_double * 6)(*coefficients)
    _check_cancelled(cancelled)
    code = lib.lrt_creative_composite_tile(
        source_pixels.ctypes.data_as(P), source_pixels.size, source.width, source.height,
        base.ctypes.data_as(P), output.ctypes.data_as(P), output.size, width, height,
        transform, canvas_origin[0], canvas_origin[1], opacity, BLEND_MODES.index(blend_mode),
        mask_pixels.ctypes.data_as(P) if mask_pixels is not None else P(),
        mask_pixels.size if mask_pixels is not None else 0,
    )
    if code:
        raise CreativeLayerNativeRejected(code, 'Composite creative tile')
    _check_cancelled(cancelled)
    return output
