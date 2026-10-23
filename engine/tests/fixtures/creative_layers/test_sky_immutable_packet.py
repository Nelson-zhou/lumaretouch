"""AUTHORED / UNRUN: canonical OneFormer pixels and isolated transport boundary.

These fixtures do not claim model/visual/runtime acceptance. Prediction and
process ownership are replaced only where the fixture explicitly says so.
"""
from copy import deepcopy
import hashlib
import json

import numpy as np
from PIL import Image
import pytest

from lumaretouch_engine.sky_semantic import immutable_input as I
from lumaretouch_engine.sky_semantic import manifest as M
from lumaretouch_engine.sky_semantic import predict as P
from lumaretouch_engine.sky_semantic import worker as W


def source(width=37, height=19):
    return {'sha256': 'd' * 64, 'width': width, 'height': height}


def canonical(binding=None):
    binding = source() if binding is None else binding
    count = binding['width'] * binding['height'] * 3
    return np.linspace(0, 1, count, dtype=np.float32).reshape(binding['height'], binding['width'], 3)


def packet():
    return I.from_pixels(canonical(), source())


def result(value):
    return {'source': deepcopy(value['source']), 'input_size': list(value['input_size']),
            'input_sha256': value['input_sha256'], '_immutable_input': I.metadata(value),
            'source_image': 'data:image/png;base64,' + W.png(I.array(value)), 'device': 'cpu'}


@pytest.mark.parametrize('width,height', [(1, 1), (37, 19), (512, 1024), (1501, 997), (4000, 31)])
def test_exact_existing_floor_bilinear_contract_from_full_float(width, height):
    binding = source(width, height)
    pixels = canonical(binding)
    before = pixels.copy()
    value = I.from_pixels(pixels, binding)
    scale = min(512 / min(height, width), 1024 / max(height, width))
    target = max(1, int(width * scale)), max(1, int(height * scale))
    expected = np.asarray(Image.fromarray(np.rint(pixels * np.float32(255)).astype(np.uint8))
                          .resize(target, Image.Resampling.BILINEAR))
    digest = hashlib.sha256(M.CONTRACT.encode() + b'\0' + str(target).encode() + expected.tobytes()).hexdigest()
    assert value['input_size'] == list(target)
    assert value['pixels'] == expected.tobytes() and value['input_sha256'] == digest
    assert value['canonical_sha256'] == hashlib.sha256(pixels.astype('<f4').tobytes()).hexdigest()
    assert value['source'] == binding and len(value['pixels']) <= I.MAX_INPUT_BYTES
    assert np.array_equal(pixels, before)


def test_prepared_packet_is_not_resized_twice(monkeypatch):
    real = Image.Image.resize
    calls = []
    def resize(self, size, resample=None, *args, **kwargs):
        calls.append((size, resample))
        return real(self, size, resample, *args, **kwargs)
    monkeypatch.setattr(Image.Image, 'resize', resize)
    value = packet()
    assert len(calls) == 1 and calls[0][1] == Image.Resampling.BILINEAR
    prepared, digest, owned = P.prepare_input(None, immutable_input=value)
    assert len(calls) == 1 and prepared.tobytes() == value['pixels']
    assert digest == value['input_sha256'] and owned == value
    assert prepared.flags.writeable  # Torch need not borrow a read-only buffer.
    prepared[0, 0, 0] ^= 1
    assert owned['pixels'] == value['pixels']


@pytest.mark.parametrize('dtype', [np.uint8, np.uint16])
def test_original_decoded_rgb8_rgb16_preprocessing_remains_identical(dtype):
    rgb = np.arange(19 * 37 * 3, dtype=np.uint16).reshape(19, 37, 3)
    rgb = (rgb * 31).astype(dtype)
    expected_rgb = (((rgb.astype(np.uint32) + 128) // 257).astype(np.uint8)
                    if dtype == np.uint16 else rgb)
    scale = min(512 / 19, 1024 / 37)
    target = max(1, int(37 * scale)), max(1, int(19 * scale))
    expected = np.asarray(Image.fromarray(expected_rgb).resize(target, Image.Resampling.BILINEAR))
    prepared, digest = P.prepare_image(rgb, {})
    assert np.array_equal(prepared, expected)
    assert digest == hashlib.sha256(M.CONTRACT.encode() + b'\0' + str(target).encode() + expected.tobytes()).hexdigest()


def test_complete_source_hash_not_only_quantized_model_hash():
    pixels = np.full((19, 37, 3), .123456, np.float32)
    first = I.from_pixels(pixels, source())
    pixels[0, 0, 0] = np.nextafter(pixels[0, 0, 0], np.float32(1))
    second = I.from_pixels(pixels, source())
    assert first['input_sha256'] == second['input_sha256']
    assert first['canonical_sha256'] != second['canonical_sha256'] and I.key(first) != I.key(second)


def test_noncontiguous_float_source_has_real_logical_bytes_and_owned_packet():
    pixels = canonical()[:, ::-1]
    value = I.from_pixels(pixels, source())
    expected = hashlib.sha256(np.ascontiguousarray(pixels, dtype='<f4').tobytes()).hexdigest()
    assert value['canonical_sha256'] == expected
    copied = I.check(value)
    value['source']['sha256'] = 'e' * 64
    value['input_size'][0] = 1
    pixels.fill(.1)
    assert copied['source'] == source() and copied['input_size'] == list(I.target_size(37, 19))
    assert type(copied['pixels']) is bytes and I.check(copied) == copied


@pytest.mark.parametrize('bad', [np.nan, np.inf, -np.inf, -.001, 1.001])
def test_no_hdr_clipping_or_nonfinite_input(bad):
    pixels = canonical()
    pixels[0, 0, 0] = bad
    with pytest.raises(ValueError):
        I.from_pixels(pixels, source())


@pytest.mark.parametrize('change', [
    lambda p: p.astype(np.float64), lambda p: (p * 255).astype(np.uint8),
    lambda p: (p * 65535).astype(np.uint16), lambda p: p[::2],
    lambda p: np.concatenate((p, np.ones((*p.shape[:2], 1), np.float32)), axis=2),
])
def test_reject_proxy_integer_alpha_or_noncanonical_precision(change):
    with pytest.raises(ValueError):
        I.from_pixels(change(canonical()), source())


@pytest.mark.parametrize('change', [
    lambda p: p.update(version=True), lambda p: p.update(contract='sam-2048-lanczos'),
    lambda p: p.update(input_size=[512, 512]), lambda p: p.update(input_sha256='f' * 64),
    lambda p: p.update(canonical_sha256='not-a-hash'),
    lambda p: p.update(pixels=bytearray(p['pixels'])),
    lambda p: p.update(pixels=p['pixels'][:-1]),
    lambda p: p.update(pixels=bytes([p['pixels'][0] ^ 1]) + p['pixels'][1:]),
    lambda p: p.update(path='/physical-original.png'),
])
def test_packet_rejects_wrong_transform_payload_and_extra_fields(change):
    value = packet()
    change(value)
    with pytest.raises(ValueError):
        I.check(value)


def test_source_binding_and_input_modes_cannot_be_relabelled():
    value = packet()
    different = {**source(), 'sha256': 'a' * 64}
    with pytest.raises(ValueError):
        I.check(value, different)
    with pytest.raises(ValueError):
        P.prepare_input(canonical(), immutable_input=value)
    with pytest.raises(ValueError):
        P.prepare_input(None)


def test_raw_transport_is_bounded_fixed_file_and_round_trips(tmp_path):
    value = packet()
    manifest = I.write_packet(tmp_path, value)
    assert 'pixels' not in manifest and len(json.dumps(manifest)) < 65536
    assert (tmp_path / 'input.rgb').read_bytes() == value['pixels']
    assert I.read_packet(tmp_path, manifest, source()) == value
    with pytest.raises(FileExistsError):
        I.write_packet(tmp_path, value)


@pytest.mark.parametrize('change', [lambda raw: raw[:-1], lambda raw: raw + b'x',
                                  lambda raw: bytes([raw[0] ^ 1]) + raw[1:]])
def test_raw_transport_refuses_truncation_growth_and_corruption(tmp_path, change):
    value = packet()
    manifest = I.write_packet(tmp_path, value)
    (tmp_path / 'input.rgb').write_bytes(change(value['pixels']))
    with pytest.raises(ValueError):
        I.read_packet(tmp_path, manifest, source())


def test_raw_transport_rejects_symlink_and_metadata_path_injection(tmp_path):
    value = packet()
    target = tmp_path / 'other.rgb'
    target.write_bytes(value['pixels'])
    (tmp_path / 'input.rgb').symlink_to(target)
    with pytest.raises(OSError):
        I.read_packet(tmp_path, I.metadata(value), source())
    manifest = I.metadata(value)
    manifest['path'] = str(target)
    with pytest.raises(ValueError):
        I.read_packet(tmp_path, manifest, source())


@pytest.mark.parametrize('change', [
    lambda r: r['source'].update(sha256='a' * 64),
    lambda r: r.update(input_sha256='a' * 64),
    lambda r: r.update(input_size=[512, 512]),
    lambda r: r['_immutable_input'].update(canonical_sha256='b' * 64),
    lambda r: r.pop('_immutable_input'),
    lambda r: r.update(source_image='data:image/png;base64,' + W.png(np.zeros((512, 512, 3), np.uint8))),
])
def test_returned_source_input_hash_extent_and_display_are_all_checked(change):
    value = packet()
    returned = result(value)
    assert I.validate_result(value, returned) is returned
    change(returned)
    with pytest.raises(ValueError):
        I.validate_result(value, returned)


def test_returned_locator_rejects_same_size_altered_pixels():
    value = packet()
    returned = result(value)
    pixels = I.array(value)
    pixels[0, 0, 0] ^= 1
    returned['source_image'] = 'data:image/png;base64,' + W.png(pixels)
    with pytest.raises(ValueError):
        I.validate_result(value, returned)
