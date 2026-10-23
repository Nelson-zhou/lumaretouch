"""Shared genuine-source precision and encoded-sRGB input boundary.

This is not a decoder or a new format adapter. In particular, detecting PNG16
must lead to the existing load_full(want_bits=16) refusal, never Pillow RGB8.
"""


def source_bits(path, image):
    """Inspect bounded PNG IHDR bytes; Pillow's RGB mode does not prove RGB8."""
    from .decode import _source_bits
    if image.format != 'PNG':
        return _source_bits(image)
    with open(path, 'rb') as stream:
        header = stream.read(33)
    if (len(header) != 33 or header[:8] != b'\x89PNG\r\n\x1a\n'
            or header[8:16] != b'\x00\x00\x00\rIHDR'
            or int.from_bytes(header[16:20], 'big') != image.width
            or int.from_bytes(header[20:24], 'big') != image.height
            or header[24] not in (1, 2, 4, 8, 16)):
        raise ValueError('Full source PNG header, precision or dimensions are invalid')
    return header[24]


def require_opaque_8bit(image):
    """Reject actual coverage before the existing RGB decoder discards alpha.

    Call only after checking native precision. High-bit transparency must never
    be inspected through Pillow RGB8; genuine RGB16 TIFF rejects extra channels
    in load_full, and this source boundary does not support PNG16 decoding.
    """
    if 'A' not in image.getbands() and 'transparency' not in image.info:
        return
    rgba = image.convert('RGBA')
    try:
        alpha = rgba.getchannel('A')
        try:
            if alpha.getextrema() != (255, 255):
                raise ValueError('Full RGB source cannot silently discard transparency')
        finally:
            alpha.close()
    finally:
        rgba.close()


def working_rgb(decoded):
    """Return native RGB in the same working space as ordinary edited export.

    load_full's uint8 arm already converted embedded ICC to working sRGB.
    Its uint16 TIFF arm retains source encoding; RAW16 is developed as sRGB.
    Only uint16 embedded profiles need conversion, using the export's existing
    LittleCMS16 path. Never downcast, mutate the decoder or convert RGB8 twice.
    """
    import numpy as np
    pixels = decoded.rgb
    if (type(pixels) is not np.ndarray or pixels.ndim != 3 or pixels.shape[2] != 3
            or pixels.shape[0] < 1 or pixels.shape[1] < 1
            or pixels.dtype not in (np.uint8, np.uint16)):
        raise ValueError('Full working source requires genuine RGB uint8 or uint16')
    if pixels.dtype == np.uint16 and decoded.source_icc:
        from .color16 import convert_rgb16
        from .export import _srgb_bytes
        pixels = convert_rgb16(pixels, decoded.source_icc, _srgb_bytes())
    return pixels
