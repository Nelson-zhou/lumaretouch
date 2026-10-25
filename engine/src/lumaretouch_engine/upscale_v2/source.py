"""Immutable opaque SDR canonical-source validation, with bounded scan chunks.

No image decoder, integer conversion, color-profile guess, resizer or model is
used here. Full current-source capture and ownership remain the caller's job.
"""

from dataclasses import dataclass
from hashlib import sha256
from math import isfinite
import re
from struct import iter_unpack
from typing import Callable

MAX_PIXELS = 100_000_000
MAX_CANONICAL_BYTES = 1_600_000_000
SCAN_BYTES = 1_048_576


@dataclass(frozen=True)
class CanonicalSource:
    width: int
    height: int
    rgba_f32le: bytes
    sha256: str
    encoding: str = "linear-srgb-d65-premultiplied-rgba-f32le"


@dataclass(frozen=True)
class SourceValidation:
    width: int
    height: int
    sha256: str
    validated_pixels: int
    canonical_bytes: int
    opaque_sdr: bool = True


def validate_dimensions(width: int, height: int) -> None:
    if type(width) is not int or type(height) is not int or width < 2 or height < 2:
        raise ValueError("initial native-candidate contract requires dimensions >= 2")
    if width * height > MAX_PIXELS or width * height * 16 > MAX_CANONICAL_BYTES:
        raise ValueError("canonical source exceeds the existing asset bounds")


def validate_source(source: CanonicalSource, *, check_cancelled: Callable[[], None]) -> SourceValidation:
    """Check every pixel and the exact immutable byte digest before inference.

check_cancelled must raise when cancelled. Validation scans include pixels
outside any region. It does not establish the caller's document/source ownership
or authorize allocation; it makes no success claim about a model result.
"""
    if type(source) is not CanonicalSource:
        raise ValueError("an explicit immutable canonical source is required")
    validate_dimensions(source.width, source.height)
    if source.encoding != "linear-srgb-d65-premultiplied-rgba-f32le":
        raise ValueError("unsupported canonical source encoding")
    if type(source.rgba_f32le) is not bytes:
        raise ValueError("source pixels must be immutable bytes, not a mutable array or proxy")
    if len(source.rgba_f32le) != source.width * source.height * 16:
        raise ValueError("canonical source byte length does not match dimensions")
    if type(source.sha256) is not str or re.fullmatch(r"[0-9a-f]{64}", source.sha256) is None:
        raise ValueError("source digest must be lowercase hexadecimal SHA256")
    digest = sha256()
    view = memoryview(source.rgba_f32le)
    for offset in range(0, len(view), SCAN_BYTES):
        check_cancelled()
        block = view[offset:offset + SCAN_BYTES]
        digest.update(block)
        for red, green, blue, alpha in iter_unpack("<ffff", block):
            if not all(isfinite(value) for value in (red, green, blue, alpha)):
                raise ValueError("nonfinite canonical pixels are unsupported")
            if alpha != 1.0:
                raise ValueError("AI clarity candidate supports only fully opaque input")
            if not all(0.0 <= value <= 1.0 for value in (red, green, blue)):
                raise ValueError("AI clarity candidate rejects negative/HDR source pixels")
    check_cancelled()
    actual = digest.hexdigest()
    if actual != source.sha256:
        raise ValueError("canonical source digest mismatch")
    return SourceValidation(source.width, source.height, actual,
                            source.width * source.height, len(view))
