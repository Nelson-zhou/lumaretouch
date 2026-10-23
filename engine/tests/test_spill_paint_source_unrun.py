"""AUTHORED / UNRUN: whole-source locator and stale paint-token contracts.

No imports, fixtures, native paths or image operations were executed while
authoring. Synthetic orchestration doubles are not image quality/performance,
real decode/native correctness, display acceptance or full export evidence.
"""
from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace
import base64
import io

import numpy as np
import pytest

from lumaretouch_engine import spill_removal_paint_source as P
from lumaretouch_engine import creative_derived_source as D
from lumaretouch_engine import creative_document_base as B
from lumaretouch_engine import creative_document_host as HOST
from lumaretouch_engine import full_candidate_render as FULL
from lumaretouch_engine import local_mask_state as M
from lumaretouch_engine import id_background_state as I
from lumaretouch_engine import spill_removal_coverage as C
from lumaretouch_engine import spill_removal_paint_vectors as V


class EngineDouble:
    def __init__(self):
        self._load_id = 'loaded-photo'
        self._doc_index = 0
        self._docs = [{'path': 'synthetic-original', 'document_id': 'recipe-photo'}]
        self.revision = 3
        self.source = {'sha256': 'a' * 64, 'width': 12, 'height': 8}
        self.state = {'crop': [.2, .1, .8, .9], 'rotate': 90, 'edit': 8}
        self.people = 'person-owner'
        self.provenance = 'b' * 64
        self.stamp = (1, 2, 3, 4, 5)
        self._id_background = {'coverage': None}

    def _capture_state(self):
        return {**deepcopy(self.state), 'id': deepcopy(self._id_background)}

    def _document_versions(self):
        return SimpleNamespace(version=lambda row: SimpleNamespace(
            document_id=row['document_id'], revision=self.revision))


def request(engine, action=P.ACTION):
    return {'cmd': 'background', 'action': action, 'request_id': 'paint-read',
            'document_id': engine._load_id, 'recipe_document_id': 'recipe-photo',
            'recipe_revision': str(engine.revision)}


@pytest.fixture
def target(monkeypatch):
    engine = EngineDouble()
    monkeypatch.setattr(D, 'binding', lambda e: deepcopy(e.source))

    def verify(source, e):
        if source != e.source:
            raise ValueError('Synthetic effective source changed')
        return source

    monkeypatch.setattr(D, 'verify', verify)
    monkeypatch.setattr(M, 'file_stamp', lambda path: engine.stamp)
    monkeypatch.setattr(FULL, 'identity', lambda e, row, state, document, revision:
                        ({'state': deepcopy(state), 'people': e.people,
                          'source': deepcopy(e.source), 'original': e.provenance}, {}, {}))
    monkeypatch.setattr(I, 'spill_of', lambda value: deepcopy(value))
    monkeypatch.setattr(P, 'source_pixels', lambda e, source:
                        np.full((source['height'], source['width'], 3), .25, np.float32))
    monkeypatch.setattr(C, 'verify_source', lambda value, source: deepcopy(value))
    monkeypatch.setattr(C, 'raster', lambda value, shape, **kwargs: np.full(shape, .5, np.float32))
    monkeypatch.setattr(V, 'append', lambda coverage, source, strokes:
                        {'coverage': deepcopy(coverage), 'source': deepcopy(source), 'strokes': deepcopy(strokes)})
    return engine, P.owner(engine)


def test_source_geometry_ignores_crop_rotation_and_retains_no_images(target):
    engine, owner = target
    value = owner.prepare(request(engine))
    assert value['domain'] == 'source-normalized'
    assert (value['image']['width'], value['image']['height']) == (12, 8)
    assert (value['coverage']['width'], value['coverage']['height']) == (12, 8)
    assert value['source'] == engine.source
    assert set(value) == {'version', 'token', 'recipe_document_id', 'recipe_revision',
                          'source', 'domain', 'image', 'coverage'}
    assert not hasattr(owner, 'pending')
    assert 'image' not in owner.record and 'pixels' not in owner.record
    assert not any(isinstance(value, np.ndarray) for value in owner.record.values())


def test_half_up_display_geometry_is_whole_frame_not_proxy_rounding():
    source = {'sha256': 'a' * 64, 'width': 1024, 'height': 513}
    assert P.dimensions(source) == (512, 257)
    assert P.dimensions({**source, 'width': 1, 'height': 1024}) == (1, 512)


def test_actual_png_digest_and_opaque_gray_coverage(target):
    from PIL import Image
    engine, owner = target
    value = owner.prepare(request(engine))
    for name in ('image', 'coverage'):
        image = value[name]
        data = base64.b64decode(image['base64'], validate=True)
        assert sha256(data).hexdigest() == image['sha256']
        with Image.open(io.BytesIO(data)) as decoded:
            assert decoded.mode == 'RGB' and decoded.size == (12, 8)
            pixels = np.asarray(decoded)
            assert np.all(pixels[:, :, 0] == pixels[:, :, 1])
            assert np.all(pixels[:, :, 1] == pixels[:, :, 2])
            if name == 'coverage':
                assert np.all(pixels == 255)


def test_read_then_reusable_previews_never_consume_source_token(target):
    engine, owner = target
    value = owner.prepare(request(engine))
    paint = {'token': value['token'], 'strokes': []}
    a = owner.coverage(request(engine, 'id_spill_preview'), paint)
    b = owner.coverage(request(engine, 'id_spill_preview'), paint)
    assert a == b and owner.record['token'] == value['token']
    assert engine._id_background == {'coverage': None}


@pytest.mark.parametrize('change', ['source', 'revision', 'state', 'people', 'provenance', 'stamp'])
def test_any_source_recipe_or_ownership_change_rejects_stale_paint(target, change):
    engine, owner = target
    value = owner.prepare(request(engine))
    frozen_request = request(engine, 'id_spill_preview')
    if change == 'source': engine.source['sha256'] = 'c' * 64
    elif change == 'revision': engine.revision += 1
    elif change == 'state': engine.state['edit'] += 1
    elif change == 'people': engine.people = 'other-person'
    elif change == 'provenance': engine.provenance = 'c' * 64
    else: engine.stamp = (1, 2, 3, 4, 6)
    with pytest.raises(ValueError):
        owner.coverage(frozen_request, {'token': value['token'], 'strokes': []})


def test_new_capture_or_expiry_invalidates_old_token(target, monkeypatch):
    engine, owner = target
    old = owner.prepare(request(engine))
    current = owner.prepare(request(engine))
    with pytest.raises(ValueError):
        owner.coverage(request(engine), {'token': old['token'], 'strokes': []})
    monkeypatch.setattr(P.time, 'monotonic', lambda: owner.record['expires'] + 1)
    with pytest.raises(ValueError):
        owner.coverage(request(engine), {'token': current['token'], 'strokes': []})


def test_failed_new_source_discards_old_token(target, monkeypatch):
    engine, owner = target
    owner.prepare(request(engine))
    def fail(*args): raise ValueError('Synthetic decode refused')
    monkeypatch.setattr(P, 'source_pixels', fail)
    with pytest.raises(ValueError): owner.prepare(request(engine))
    assert owner.record is None


def test_capture_change_during_pixel_read_cannot_publish(target, monkeypatch):
    engine, owner = target
    def changed(e, source):
        e.state['edit'] += 1
        return np.zeros((8, 12, 3), np.float32)
    monkeypatch.setattr(P, 'source_pixels', changed)
    with pytest.raises(ValueError): owner.prepare(request(engine))
    assert owner.record is None


def test_saved_coverage_is_owned_snapshot_not_mutable_panel_input(target):
    engine, owner = target
    engine._id_background['coverage'] = {'version': 1, 'objects': ['saved-vector']}
    value = owner.prepare(request(engine))
    assert owner.record['coverage'] == engine._id_background['coverage']
    assert owner.record['coverage'] is not engine._id_background['coverage']
    with pytest.raises(ValueError):
        owner.coverage(request(engine), {'token': value['token'], 'strokes': [], 'source': engine.source})


def test_derived_source_uses_exact_canonical_provider_not_proxy(monkeypatch):
    engine = EngineDouble()
    base = {'canonical': 'actual-immutable-source'}
    pixels = np.full((8, 12, 3), .7353569, np.float32)
    calls = []
    monkeypatch.setattr(D, 'verify', lambda source, e: source)
    monkeypatch.setattr(D, 'record', lambda e: base)
    monkeypatch.setattr(HOST, 'memory_budget', lambda: 100_000_000)
    monkeypatch.setattr(B, 'export_source', lambda actual, **kwargs: calls.append(actual) or pixels)
    def no_proxy(*args, **kwargs): raise AssertionError('No proxy/original route')
    monkeypatch.setattr(D, 'analysis_rgb', no_proxy)
    monkeypatch.setattr(P, '_original_pixels', no_proxy)
    assert P.source_pixels(engine, engine.source) is pixels
    assert calls == [base]  # Already encoded by export_source; no second transfer.


def test_source_display_never_clips_hdr():
    for value in (-.1, 1.1, float('nan')):
        with pytest.raises(ValueError): P._png(np.full((2, 2, 3), value, np.float32), 2, 2)


@pytest.mark.parametrize('refusal', ['rgb8', 'draft', 'preview'])
def test_rgb16_decode_contract_refuses_surrogates(monkeypatch, refusal):
    from PIL import Image
    from lumaretouch_engine import decode
    from lumaretouch_engine import full_source_working as WORKING
    source = {'sha256': 'a' * 64, 'width': 12, 'height': 8}
    class Header:
        width, height, n_frames = 12, 8, 1
        def __enter__(self): return self
        def __exit__(self, *args): return False
    decoded = SimpleNamespace(rgb=np.ones((8, 12, 3), np.uint16), h=8, w=12,
                              src_h=8, src_w=12, draft_used=False, raw={}, source_icc=None)
    if refusal == 'rgb8': decoded.rgb = decoded.rgb.astype(np.uint8)
    elif refusal == 'draft': decoded.draft_used = True
    else: decoded.raw = {'used_preview': True}
    monkeypatch.setattr(Image, 'open', lambda path: Header())
    monkeypatch.setattr(decode, 'is_raw', lambda path: False)
    monkeypatch.setattr(WORKING, 'source_bits', lambda path, header: 16)
    monkeypatch.setattr(decode, 'load_full', lambda *args, **kwargs: decoded)
    monkeypatch.setattr(M, 'file_stamp', lambda path: (1, 2, 3, 4, 5))
    monkeypatch.setattr(M, 'source_digest', lambda path: source['sha256'])
    with pytest.raises(ValueError): P._original_pixels('synthetic-original', source, 100_000_000)


def test_rgb16_source_normalizes_actual_shared_working_pixels(monkeypatch):
    from PIL import Image
    from lumaretouch_engine import decode
    from lumaretouch_engine import full_source_working as WORKING
    source = {'sha256': 'a' * 64, 'width': 2, 'height': 1}
    class Header:
        width, height, n_frames = 2, 1, 1
        def __enter__(self): return self
        def __exit__(self, *args): return False
    decoded = SimpleNamespace(rgb=np.zeros((1, 2, 3), np.uint16), h=1, w=2,
                              src_h=1, src_w=2, draft_used=False, raw={}, source_icc=b'profile')
    converted = np.array([[[32768, 32769, 65535], [1, 2, 3]]], np.uint16)
    calls = []
    monkeypatch.setattr(Image, 'open', lambda path: Header())
    monkeypatch.setattr(decode, 'is_raw', lambda path: False)
    monkeypatch.setattr(WORKING, 'source_bits', lambda path, header: 16)
    monkeypatch.setattr(WORKING, 'working_rgb', lambda value: calls.append(value) or converted)
    monkeypatch.setattr(decode, 'load_full', lambda *args, **kwargs: decoded)
    monkeypatch.setattr(M, 'file_stamp', lambda path: (1, 2, 3, 4, 5))
    monkeypatch.setattr(M, 'source_digest', lambda path: source['sha256'])
    actual = P._original_pixels('synthetic-original', source, 100_000_000)
    assert calls == [decoded]
    assert np.array_equal(actual, converted.astype(np.float32) / np.float32(65535.))
    assert actual[0, 0, 0] != actual[0, 0, 1]  # Adjacent genuine 16-bit bins survive.
