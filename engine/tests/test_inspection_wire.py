from dataclasses import replace
from pathlib import Path
import numpy as np
import pytest
from lumaretouch_engine.full_quality import InspectionPixels
from lumaretouch_engine.inspection_wire import encode_header


def pixels():
    a = np.array([[[1, 2, 3, 255], [4, 5, 6, 255]]], np.uint8)
    return InspectionPixels(a, 10, 10, (1, 2, 2, 1), 16)


def encode(p=None, **options):
    return encode_header(p or pixels(), epoch=options.get('epoch', bytes([7])*16),
                         ticket=options.get('ticket', (9007199254740993, 2, 3, 4, 5)),
                         max_payload=options.get('max_payload', 8))


def test_shared_golden_vector_preserves_u64_above_js_safe_integer():
    p = pixels()
    golden = bytes.fromhex((Path(__file__).resolve().parents[2]/'core/inspection/packet-v1.hex').read_text())
    assert len(encode(p)) == 128
    assert encode(p) + p.rgba.tobytes() == golden


@pytest.mark.parametrize('options', [dict(epoch=bytes(16)), dict(epoch=b'x'),
    dict(ticket=(True, 2, 3, 4, 5)), dict(ticket=(2**64, 2, 3, 4, 5)),
    dict(ticket=(0, 2, 3, 4, 5)), dict(max_payload=7), dict(max_payload=True)])
def test_invalid_identity_and_budget_are_rejected(options):
    with pytest.raises(ValueError):
        encode(**options)


def test_bad_layout_precision_profile_and_alpha_are_rejected():
    p = pixels()
    for bad in [replace(p, canvas_width=0), replace(p, roi=(9, 2, 2, 1)),
                replace(p, roi=(1., 2, 2, 1)), replace(p, decoded_bits=True),
                replace(p, source_bits=33), replace(p, display_profile='DisplayP3'),
                replace(p, quality_mode='proxy'), replace(p, rgba=p.rgba[:, ::-1]),
                replace(p, rgba=p.rgba.astype(np.uint16))]:
        with pytest.raises(ValueError):
            encode(bad)
    p.rgba[0, 0, 3] = 0
    with pytest.raises(ValueError, match='opaque'):
        encode(p)


def test_budget_fails_before_alpha_scan(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('payload accessed before admission')
    monkeypatch.setattr(np, 'any', forbidden)
    with pytest.raises(ValueError, match='budget'):
        encode(max_payload=7)


@pytest.mark.parametrize('roi', [None, (), (1, 2, 3), (1, 2, 3, 4, 5),
    (-1, 2, 2, 1), (True, 2, 2, 1), (2**32, 2, 2, 1)])
def test_roi_shape_and_integer_range_are_explicit(roi):
    with pytest.raises(ValueError):
        encode(replace(pixels(), roi=roi))


def test_canvas_u32_bounds_and_known_precision():
    with pytest.raises(ValueError):
        encode(replace(pixels(), canvas_width=2**32))
    header = encode(replace(pixels(), source_bits=12))
    assert header[106:108] == bytes([12, 0])
