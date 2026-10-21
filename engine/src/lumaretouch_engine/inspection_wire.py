"""Fixed identity-bearing inspection header; transport lifecycle is separate."""
from __future__ import annotations
import struct
import numpy as np
from .full_quality import InspectionPixels

HEADER_BYTES = 128
_LAYOUT = struct.Struct('<4sHH16s5Q6IQI4H20s')


def encode_header(pixels: InspectionPixels, *, epoch: bytes, ticket: tuple[int, ...],
                  max_payload: int) -> bytes:
    """Validate before creating the small header. Does not copy the pixel payload.

    The caller needs a separate lease for all SHM/IPC/display copies and must use
    a host-issued epoch/ticket. This format does not establish source authenticity.
    """
    if type(epoch) is not bytes or len(epoch) != 16 or epoch == bytes(16):
        raise ValueError('A nonzero 16-byte host engine epoch is required')
    if type(ticket) is not tuple or len(ticket) != 5 or any(type(n) is not int or not 0 <= n < 2**64 for n in ticket) or ticket[0] == 0:
        raise ValueError('Ticket must contain five exact u64 integers with nonzero id')
    if type(max_payload) is not int or max_payload < 0:
        raise ValueError('Explicit payload byte budget required')
    if pixels.display_profile != 'sRGB' or pixels.quality_mode != 'full_source_export':
        raise ValueError('Inspection format only supports verified full-source sRGB output')
    if type(pixels.roi) not in (tuple, list) or len(pixels.roi) != 4:
        raise ValueError('Inspection ROI must contain four integers')
    dimensions = (pixels.canvas_width, pixels.canvas_height, *pixels.roi)
    if len(dimensions) != 6 or any(type(n) is not int or not 0 <= n < 2**32 for n in dimensions):
        raise ValueError('Canvas/ROI must be exact u32 integers')
    cw, ch, x, y, w, h = dimensions
    if min(cw, ch, w, h) == 0 or x+w > cw or y+h > ch:
        raise ValueError('Inspection ROI outside canvas')
    payload = w*h*4
    if payload > max_payload or payload + HEADER_BYTES > np.iinfo(np.intp).max:
        raise ValueError('Inspection payload exceeds byte budget/address space')
    a = pixels.rgba
    if type(a) is not np.ndarray or a.dtype != np.dtype('uint8') or a.dtype.metadata is not None or a.shape != (h, w, 4) or not a.flags.c_contiguous:
        raise ValueError('Inspection payload must be C-contiguous RGBA8')
    # Small bounded temporary masks; do not allocate a whole-image boolean array.
    flat = a.reshape(-1, 4)
    for start in range(0, len(flat), 65536):
        if np.any(flat[start:start+65536, 3] != 255):
            raise ValueError('Inspection RGBA must be opaque')
    bits = pixels.decoded_bits
    source = 0 if pixels.source_bits is None else pixels.source_bits
    if type(bits) is not int or bits not in (8, 16) or type(source) is not int or not 0 <= source <= 32:
        raise ValueError('Invalid inspection precision metadata')
    return _LAYOUT.pack(b'LRIF', 1, HEADER_BYTES, epoch, *ticket, *dimensions,
                        payload, 0x41424752, 1, 1, bits, source, bytes(20))
