"""AUTHORED / UNRUN: bounded Original source-header and decoder-proof cases.

Synthetic headers deliberately do not certify valid compressed pixels. Actual
codec/payload validation is a separate required local integration acceptance.
No test, product import, decoder or fixture has been executed during authoring.
"""
import hashlib
import struct
import zlib
from types import SimpleNamespace

import numpy as np
import pytest

from lumaretouch_engine import export_source_facts as F
from lumaretouch_engine import raw, decode, project


def _chunk(kind, data):
    return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)


def _png(bits=16, *, animated=False):
    header = struct.pack('>IIBBBBB', 3, 2, bits, 2, 0, 0, 0)
    animation = _chunk(b'acTL', struct.pack('>II', 2, 0)) if animated else b''
    return (b'\x89PNG\r\n\x1a\n' + _chunk(b'IHDR', header) + animation
            + _chunk(b'IDAT', b'not-a-compressed-pixel-proof') + _chunk(b'IEND', b''))


def _jpeg(*, mpo=False, bits=8):
    def segment(marker, data):
        return bytes((255, marker)) + struct.pack('>H', len(data) + 2) + data
    frame = struct.pack('>BHHB', bits, 2, 3, 3) + b'\x01\x11\0\x02\x11\0\x03\x11\0'
    scan = b'\x03\x01\0\x02\0\x03\0\0\x3f\0'
    return (b'\xff\xd8' + (segment(0xE2, b'MPF\0') if mpo else b'')
            + segment(0xC0, frame) + segment(0xDA, scan) + b'\xff\xd9')


def _tiff(*, endian='<', photo=2, bits=16, cycle=False):
    # A complete bounded image-IFD skeleton, not an encoded pixel fixture.
    values = [(256, 4, 1, 3), (257, 4, 1, 2), (258, 3, 3, None),
              (259, 3, 1, 1), (262, 3, 1, photo), (274, 3, 1, 1),
              (277, 3, 1, 3), (284, 3, 1, 1)]
    bits_at = 8 + 2 + len(values) * 12 + 4
    body = []
    for tag, typ, count, value in values:
        inline = struct.pack(endian + 'I', bits_at) if value is None else (
            struct.pack(endian + 'H', value) + b'\0\0' if typ == 3 else struct.pack(endian + 'I', value))
        body.append(struct.pack(endian + 'HHI', tag, typ, count) + inline)
    return ((b'II' if endian == '<' else b'MM') + struct.pack(endian + 'HI', 42, 8)
            + struct.pack(endian + 'H', len(values)) + b''.join(body)
            + struct.pack(endian + 'I', 8 if cycle else 0) + struct.pack(endian + 'HHH', bits, bits, bits))


def _owned(path, *, snapshot=None, managed=False):
    row = {'document_id': 'doc-a', 'source_asset_id': 'asset-a', 'path': str(path)}
    if managed:
        row['managed_import'] = {'original_path': '/removed/logical-name.jpg'}
    entry = {**row, 'recipe_version_id': 'recipe-a', 'fingerprint': project.fingerprint(str(path), full=True)}
    return F.freeze(row, entry, snapshot or {})


def _decoded(facts, *, bits=None, kind=None):
    stamp = facts['decoder_stamp']
    bits = facts['precision'] if bits is None else bits
    fmt = {'jpeg': 'JPEG', 'png': 'PNG', 'tiff': 'TIFF', 'webp': 'WEBP'}[facts['container']]
    pixels = np.zeros((stamp['height'], stamp['width'], 3), dtype=np.uint16 if bits == 16 else np.uint8)
    source = kind if kind is not None else 'png16' if bits == 16 and fmt == 'PNG' else 'tiff16' if bits == 16 else None
    return SimpleNamespace(rgb=pixels, fmt=fmt, raw=None if source is None else {'source': source},
                           src_bits=bits, source_orientation=stamp['orientation'], draft_used=False, w=stamp['width'], h=stamp['height'],
                           src_w=stamp['width'], src_h=stamp['height'])


def test_metadata_only_png16_reads_no_pixel_decoder(tmp_path, monkeypatch):
    path = tmp_path / 'retained.bin'
    path.write_bytes(_png())
    def prohibited(*_args, **_kwargs):
        raise AssertionError('Preview must not invoke a pixel decoder')
    monkeypatch.setattr(decode, 'load_full', prohibited)
    monkeypatch.setattr(decode.Image, 'open', prohibited)
    facts = _owned(path, managed=True)
    assert (facts['container'], facts['precision'], facts['single_frame']) == ('png', 16, True)
    assert facts['fingerprint']['path'] == str(path)
    assert facts['effective_asset']['sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
    # Valid header facts are intentionally not a claim that fake IDAT decodes.


@pytest.mark.parametrize('endian', ['<', '>'])
def test_classic_tiff_precision_and_bitmap_kind(tmp_path, endian):
    path = tmp_path / 'misnamed.jpg'
    path.write_bytes(_tiff(endian=endian))
    inspected = raw.inspect_tiff(str(path))
    assert inspected['source_kind'] == 'bitmap'
    assert inspected['precision'] == 16 and inspected['single_frame']
    facts = _owned(path)
    assert facts['container'] == 'tiff' and facts['precision'] == 16


def test_content_not_suffix_selects_native_tiff(tmp_path, monkeypatch):
    path = tmp_path / 'actually-tiff.jpg'
    path.write_bytes(_tiff())
    sentinel = object()
    monkeypatch.setattr(decode, '_load_16bit_tiff_full', lambda *_: sentinel)
    assert decode.load_full(str(path), want_bits=16) is sentinel
    wrong = tmp_path / 'actually-jpeg.tif'
    wrong.write_bytes(_jpeg())
    with pytest.raises(ValueError, match='16-bit'):
        decode.load_full(str(wrong), want_bits=16)


@pytest.mark.parametrize('data', [
    _tiff(cycle=True),
    b'II*\0\x08\0\0\0' + struct.pack('<H', 4097),
    b'II+\0\x08\0\0\0' + struct.pack('<Q', 16) + struct.pack('<Q', 2**63),
    b'MM\0*' + struct.pack('>I', 2**32 - 2),
    b'II*\0\x08\0\0\0' + b'\x01\0' + b'\0' * 4,
])
def test_malformed_tiff_is_unknown_not_bitmap(tmp_path, data):
    path = tmp_path / 'unknown.tif'
    path.write_bytes(data)
    inspected = raw.inspect_tiff(str(path))
    assert inspected['source_kind'] == 'unknown'
    with pytest.raises(raw.UnsupportedRaw):
        raw.has_raw_ifd(str(path))
    with pytest.raises(ValueError, match='original_tiff_unknown'):
        _owned(path)


def test_raw_ifd_never_becomes_bitmap_native16(tmp_path):
    path = tmp_path / 'sensor.tif'
    path.write_bytes(_tiff(photo=raw.PHOTOMETRIC_CFA))
    assert raw.inspect_tiff(str(path))['source_kind'] == 'raw'
    assert raw.has_raw_ifd(str(path)) is True
    assert _owned(path)['source_kind'] == 'raw'


@pytest.mark.parametrize('payload,container', [(_png(animated=True), 'png'), (_jpeg(mpo=True), 'jpeg')])
def test_multiframe_headers_do_not_claim_single_image(tmp_path, payload, container):
    path = tmp_path / 'source.bin'
    path.write_bytes(payload)
    facts = _owned(path)
    assert facts['container'] == container and facts['single_frame'] is False


def test_webp_animation_header_refuses_single_frame(tmp_path):
    def chunk(kind, content):
        return kind + struct.pack('<I', len(content)) + content + (b'\0' if len(content) & 1 else b'')
    chunks = chunk(b'VP8X', b'\x02\0\0\0\x02\0\0\x01\0\0') + chunk(b'ANIM', b'\0' * 6)
    path = tmp_path / 'animated.webp'
    path.write_bytes(b'RIFF' + struct.pack('<I', len(chunks) + 4) + b'WEBP' + chunks)
    facts = _owned(path)
    assert facts['container'] == 'webp' and not facts['single_frame']


def test_unsupported_precision_is_not_8bit_default(tmp_path):
    path = tmp_path / 'twelve.jpg'
    path.write_bytes(_jpeg(bits=12))
    facts = _owned(path)
    assert facts['precision'] == 12


def test_nested_fact_tampering_and_unknown_fields_refuse(tmp_path):
    path = tmp_path / 'input.png'
    path.write_bytes(_png())
    facts = _owned(path)
    facts['precision'] = 8
    with pytest.raises(ValueError, match='integrity'):
        F.validate(facts)
    facts = _owned(path)
    facts['decoder_stamp']['client_codec'] = 'jpg'
    with pytest.raises(ValueError, match='stamp_schema'):
        F.validate(facts)


def test_full_decode_must_agree_native_precision_container_and_kind(tmp_path):
    path = tmp_path / 'input.png'
    path.write_bytes(_png())
    facts = _owned(path)
    F.verify_decoded(facts, _decoded(facts), {})
    with pytest.raises(ValueError, match='precision'):
        F.verify_decoded(facts, _decoded(facts, bits=8), {})
    with pytest.raises(ValueError, match='source_disagrees'):
        F.verify_decoded(facts, _decoded(facts, kind='libraw'), {})
    mirrored = _decoded(facts)
    mirrored.source_orientation = 2
    with pytest.raises(ValueError, match='orientation'):
        F.verify_decoded(facts, mirrored, {})
    wrong = _decoded(facts)
    wrong.fmt = 'TIFF'
    with pytest.raises(ValueError, match='source_disagrees'):
        F.verify_decoded(facts, wrong, {})


def test_creative_asset_separately_binds_encoded_ancestor(tmp_path):
    from lumaretouch_engine.creative_document_assets import make_asset
    path = tmp_path / 'input.png'
    original = _png(bits=8)
    path.write_bytes(original)
    content = struct.pack('<ffff', 0., 0., 0., 1.) * 6
    asset = make_asset('rgba', 3, 2, content, original=original)
    facts = _owned(path, snapshot={'creative_base': asset})
    assert facts['variant'] == 'creative'
    assert facts['effective_asset']['id'] == asset['id']
    assert facts['effective_asset']['ancestor_sha256'] == hashlib.sha256(original).hexdigest()
    F.verify_decoded(facts, _decoded(facts), {'creative_base': asset})
    other = make_asset('rgba', 3, 2, content, original=_jpeg())
    with pytest.raises(ValueError, match='ancestor_unauthenticated'):
        _owned(path, snapshot={'creative_base': other})
    with pytest.raises(ValueError, match='ancestor_unauthenticated'):
        F.verify_decoded(facts, _decoded(facts), {'creative_base': other})


def test_legacy_external_path_cannot_become_authenticated_original(tmp_path):
    path = tmp_path / 'input.png'
    path.write_bytes(_png())
    with pytest.raises(ValueError, match='authenticated_document'):
        F.freeze({'path': str(path)}, {'path': str(path), 'fingerprint': project.fingerprint(str(path), full=True)}, {})


@pytest.mark.parametrize('suffix,magic', [('orf', 0x4F52), ('orf', 0x5352), ('rw2', 0x0055)])
@pytest.mark.parametrize('bits', [8, 16])
def test_vendor_raw_magic_retains_existing_libraw_full_route(tmp_path, monkeypatch, suffix, magic, bits):
    path = tmp_path / ('camera.' + suffix)
    path.write_bytes(b'II' + struct.pack('<HI', magic, 8) + b'\0' * 32)
    assert raw.inspect_tiff(str(path))['source_kind'] == 'unknown'
    assert raw.vendor_raw_family(str(path)) == suffix
    assert decode.is_raw(str(path)) is True
    assert raw.has_raw_ifd(str(path)) is False  # bypass self-DNG, not LibRaw
    with pytest.raises(ValueError, match='original_tiff_unknown'):
        _owned(path)
    calls = []
    def native(source, *, output_bps, **_kwargs):
        calls.append((source, output_bps))
        return object(), {'w': 3, 'h': 2}
    sentinel = object()
    monkeypatch.setattr(decode, '_libraw_matrix', native)
    monkeypatch.setattr(decode, '_decoded_from_libraw', lambda *_args, **_kwargs: sentinel)
    assert decode.load_full(str(path), want_bits=bits) is sentinel
    assert calls == [(str(path), bits)]


@pytest.mark.parametrize('magic', [0x4F52, 0x5352, 0x0055])
def test_vendor_raw_proxy_routes_to_libraw_not_self_dng(tmp_path, monkeypatch, magic):
    path = tmp_path / 'camera.bin'
    path.write_bytes(b'II' + struct.pack('<HI', magic, 8) + b'\0' * 32)
    calls = []
    def native(source, *, output_bps, **_kwargs):
        calls.append((source, output_bps))
        return object(), {}
    sentinel = object()
    monkeypatch.setattr(decode, '_libraw_matrix', native)
    monkeypatch.setattr(decode, '_decoded_from_libraw', lambda *_args, **_kwargs: sentinel)
    assert decode._load_rgb_raw(str(path), 4096, None) is sentinel
    assert calls == [(str(path), 8)]


def test_unknown_classic_tiff_is_not_rescued_by_vendor_suffix(tmp_path):
    path = tmp_path / 'not-an-orf.orf'
    path.write_bytes(_tiff(cycle=True))
    assert raw.vendor_raw_family(str(path)) is None
    with pytest.raises(raw.UnsupportedRaw):
        decode.is_raw(str(path))
    with pytest.raises(raw.UnsupportedRaw):
        raw.has_raw_ifd(str(path))


@pytest.mark.parametrize('suffix', ['dng', 'nef'])
@pytest.mark.parametrize('container', ['jpeg', 'webp'])
def test_known_bitmap_content_ignores_misleading_raw_suffix(tmp_path, monkeypatch, suffix, container):
    if container == 'jpeg':
        content = _jpeg()
    else:
        # Bounded lossless-WebP header; fake payload remains a decoder concern.
        image = b'\x2f' + ((3 - 1) | ((2 - 1) << 14)).to_bytes(4, 'little')
        chunks = b'VP8L' + struct.pack('<I', len(image)) + image + b'\0'
        content = b'RIFF' + struct.pack('<I', len(chunks) + 4) + b'WEBP' + chunks
    path = tmp_path / ('bitmap.' + suffix)
    path.write_bytes(content)
    facts = _owned(path)
    assert facts['container'] == container and facts['precision'] == 8
    assert decode.is_raw(str(path)) is False
    sentinel = object()
    monkeypatch.setattr(decode, '_load_full_pillow', lambda *_args: sentinel)
    def prohibited(*_args, **_kwargs):
        raise AssertionError('Known bitmap header must not enter LibRaw')
    monkeypatch.setattr(decode, '_libraw_matrix', prohibited)
    assert decode.load_full(str(path), want_bits=8) is sentinel


def test_header_descriptor_substitution_cannot_borrow_path_fingerprint(tmp_path, monkeypatch):
    # Simulate a pathname restored before the closing path-stat check: metadata
    # open returns a different inode while the original path never changes.
    original = tmp_path / 'original.png'
    substitute = tmp_path / 'substitute.png'
    original.write_bytes(_png(bits=16))
    substitute.write_bytes(_png(bits=8))
    real_open = open
    def metadata_open(path, mode='r', *args, **kwargs):
        return real_open(substitute if str(path) == str(original) and mode == 'rb' else path,
                         mode, *args, **kwargs)
    monkeypatch.setattr(F, 'open', metadata_open, raising=False)
    with pytest.raises(ValueError, match='descriptor_identity'):
        _owned(original)


def test_nested_tiff_descriptor_substitution_is_not_authenticated(tmp_path, monkeypatch):
    # The outer source-facts descriptor is correct; only the additional TIFF
    # inspector open is substituted. Every metadata FD must carry the binding.
    original = tmp_path / 'original.tif'
    substitute = tmp_path / 'substitute.tif'
    original.write_bytes(_tiff(bits=16))
    substitute.write_bytes(_tiff(bits=8))
    real_open = open
    def metadata_open(path, mode='r', *args, **kwargs):
        return real_open(substitute if str(path) == str(original) and mode == 'rb' else path,
                         mode, *args, **kwargs)
    monkeypatch.setattr(raw, 'open', metadata_open, raising=False)
    with pytest.raises(ValueError, match='tiff_inspection_source_identity'):
        _owned(original)
