# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN current-photo neck host, image and consent fixtures.

The source, diagnostic measurement, and full mixed renderer are synthetic test
doubles. They do NOT prove trusted decoding, native math, repair replay, UI
visibility, runtime memory/performance, or real-photo quality. No test, product
import, inference, build or native execution was performed while authoring.
"""
from collections import OrderedDict
from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace
import base64
import io
import numpy as np
import pytest
from PIL import Image
from lumaretouch_engine import people_state as P
from lumaretouch_engine import neck_wrinkle_actions as A, neck_wrinkle_review as I
from lumaretouch_engine import neck_wrinkle_host as H, neck_wrinkle_support as C
from lumaretouch_engine import full_candidate_render as F, virtual_copy_people as V
from test_neck_wrinkle_support_unrun import fixture as support_fixture


def fixture(monkeypatch):
    state, assets, ref, bank, analysis, review = support_fixture()
    source = {'sha256': ref['asset_sha256'], 'width': 64, 'height': 64}
    target = {'scope': 'face', 'target_id': ref['face_instance_id'], 'face_ref': ref}
    row = {'path': 'synthetic-unread-source.png', 'document_id': 'document'}
    snapshot = {'fixture': 'not a real decoded photograph'}
    version = SimpleNamespace(document_id='document', revision=7)
    provenance = {'asset_sha256': source['sha256'], 'original_sha256': source['sha256'], 'creative_source': None}
    rgb = np.full((64, 64, 3), .25, np.float32); rgb.setflags(write=False)
    engine = SimpleNamespace(_people_support=assets, _people_targets={source['sha256']: target},
        _people_cursors={source['sha256']: ref['face_instance_id']},
        _people_analyses={source['sha256']: {ref['face_instance_id']: analysis}},
        _people_source=lambda: source, _body_bank=lambda: bank, _people_binding=lambda: {'fixture_binding': 1},
        _capture_state=lambda: snapshot, _document_versions=lambda: SimpleNamespace(version=lambda _: version),
        _docs=[row], _doc_index=0, fixture_pixels=rgb, fixture_repair='b'*64,
        fixture_measurement='c'*64, fixture_render_measurement=None, fixture_delta=0., fixture_calls=[])
    owner = SimpleNamespace(snapshot=lambda: deepcopy(state), fence=19)
    engine._people_owner = lambda: owner
    monkeypatch.setattr(H, '_single_document', lambda *args: None)
    monkeypatch.setattr(F, 'identity', lambda *args, **kwargs: (
        {'source_proof': deepcopy(provenance), 'document_id': version.document_id, 'revision': str(version.revision),
         'candidate_sha256': H._fingerprint(snapshot)}, state,
        {'people_graph': deepcopy(state), 'people_support_assets': deepcopy(engine._people_support)}))
    def source_packet(owner, graph, capture, **kwargs):
        proof = {'version': 1, 'source': deepcopy(source), 'source_proof': deepcopy(provenance),
            'input_sha256': sha256(memoryview(owner.fixture_pixels).cast('B')).hexdigest(),
            'repair_sha256': owner.fixture_repair, 'encoding': 'encoded-srgb-f32-v1',
            'source_bits': 8, 'orientation': 'exif_normalized_once', 'stage': 'immutable-source'}
        return SimpleNamespace(rgb=owner.fixture_pixels, analysis=analysis, proof=proof, resident_bytes=rgb.nbytes)
    monkeypatch.setattr(H, '_source', source_packet)
    def diagnostic(owner, graph, capture, candidate, candidate_assets, amount, expected_proof, **kwargs):
        # Synthetic solid cyan instead of native detector/support rasterization.
        image = I.full_image(np.full((64, 64, 3), (.1, .9, .9), np.float32))
        return image, owner.fixture_measurement, H._binding(source_packet(owner, graph, capture), capture)
    monkeypatch.setattr(H, '_diagnostic', diagnostic)
    def render(owner, current, captured, document, revision, **kwargs):
        assert current is row and captured is snapshot and document == version.document_id
        assert revision == str(version.revision) and owner._people_support == assets
        staged = kwargs.get('staged_people_context')
        if staged is not None:
            assert staged['people_graph'] == kwargs['people_graph']
            assert all(staged['people_support_assets'][key] == value for key, value in assets.items())
        owner.fixture_calls.append(deepcopy(kwargs))
        value = np.full((64, 64, 3), .35 if staged is None else .45, np.float32)
        value[30, 30, 0] += owner.fixture_delta
        measurement = owner.fixture_render_measurement or owner.fixture_measurement
        return value, {'source_proof': deepcopy(provenance), 'output_size': [64, 64], 'source_size': [64, 64],
            'neck_wrinkle_measurements': [] if staged is None else [{'face_ref': ref, 'measurement_key': measurement}]}
    monkeypatch.setattr(F, 'render', render)
    return engine, state, target, {'review': review, 'amount': .4}, bank, version


def ready(monkeypatch):
    engine, state, target, payload, bank, version = fixture(monkeypatch)
    reference = H.reference(engine, state, target, {})
    source_crop = H.crop(engine, state, target, {'reference_id': reference['reference_id'],
        'plane': 'source', 'rect': [20, 30, 16, 16]})
    preview = H.preview(engine, state, target, payload)
    return engine, state, target, payload, bank, version, reference, source_crop, preview


def inspected(monkeypatch):
    values = ready(monkeypatch); engine, state, target, *_, preview = values
    rect = [20, 30, 16, 16]
    before = H.crop(engine, state, target, {'preview_id': preview['preview_id'], 'plane': 'before', 'rect': rect})
    after = H.crop(engine, state, target, {'preview_id': preview['preview_id'], 'plane': 'after', 'rect': rect})
    acknowledgement = {'preview_id': preview['preview_id'], 'reviewed': True,
        **{key + '_sha256': preview[key]['sha256'] for key in ('before', 'after', 'support')},
        'inspection': {'rect': rect, 'before_sha256': before['image']['sha256'], 'after_sha256': after['image']['sha256']}}
    return values, acknowledgement


def test_reference_exact_contract_real_source_not_mixed_output(monkeypatch):
    engine, state, target, *_ = fixture(monkeypatch)
    shown = H.reference(engine, state, target, {})
    assert set(shown) == {'kind', 'family', 'operation_id', 'reference_id', 'source', 'face_ref', 'bodies',
        'source_proof', 'source_image', 'attached', 'input_sha256', 'repair_sha256'}
    assert set(shown['bodies'][0]) == {'body_ref', 'points_sha256'}
    assert not engine.fixture_calls and engine._people_support == {}
    assert shown['source_image'] == I.full_image(engine.fixture_pixels)


def test_preview_requires_actual_source_crop_and_stages_without_publication(monkeypatch):
    engine, state, target, payload, *_ = fixture(monkeypatch)
    reference = H.reference(engine, state, target, {})
    with pytest.raises(ValueError, match='1:1'): H.preview(engine, state, target, payload)
    assert not engine.fixture_calls
    H.crop(engine, state, target, {'reference_id': reference['reference_id'], 'plane': 'source', 'rect': [0, 0, 8, 8]})
    before = deepcopy(state)
    shown = H.preview(engine, state, target, payload)
    assert state == before and engine._people_support == {} and len(engine.fixture_calls) == 2
    assert shown['runtime_quality_accepted'] is False and shown['before_output_size'] == [64, 64]
    assert shown['after_output_size'] == [64, 64] and shown['amount'] == payload['amount']
    assert engine.fixture_calls[1]['staged_people_context']['people_graph'] != state


def test_crops_are_true_pixel_pair_and_confirmation_only_appends_canonical_support(monkeypatch):
    values, acknowledgement = inspected(monkeypatch)
    engine, state, target, payload, *_, shown = values
    marks = []; old = deepcopy(state)
    candidate, result = H.confirm(engine, state, target, acknowledgement,
        mark_started=lambda: marks.append(deepcopy(engine._people_support)))
    assert marks == [{}] and state == old and len(engine._people_support) == 1
    assert C.KIND in candidate['faces'][target['target_id']]['local_assets']
    assert result == {'kind': 'confirmed', 'family': A.FAMILY, 'operation_id': A.OP, 'attached': True, 'amount': .4}
    assert engine._neck_wrinkle_preview is None and engine._neck_wrinkle_reference is None
    assert [row for row in candidate['overrides'] if row['operation_id'] == A.OP] == [
        {'scope': 'face', 'target_id': target['target_id'], 'operation_id': A.OP, 'parameter_path': '/amount', 'value': .4}]


@pytest.mark.parametrize('field', ['before_sha256', 'after_sha256', 'support_sha256'])
def test_every_full_display_hash_is_required_before_append(monkeypatch, field):
    values, acknowledgement = inspected(monkeypatch); engine, state, target, *_ = values
    acknowledgement[field] = '0'*64
    with pytest.raises(ValueError, match='three'): H.confirm(engine, state, target, acknowledgement)
    assert engine._people_support == {}


def test_unmatched_output_rectangles_never_become_one_inspection_pair(monkeypatch):
    values, acknowledgement = inspected(monkeypatch); engine, state, target, *_, shown = values
    H.crop(engine, state, target, {'preview_id': shown['preview_id'], 'plane': 'after', 'rect': [21, 30, 16, 16]})
    with pytest.raises(ValueError, match='same actual'): H.confirm(engine, state, target, acknowledgement)
    assert engine._people_support == {}


def test_confirmation_without_issued_output_crops_is_not_authorized_by_forged_hashes(monkeypatch):
    values = ready(monkeypatch); engine, state, target, *_, shown = values
    acknowledgement = {'preview_id': shown['preview_id'], 'reviewed': True,
        **{key + '_sha256': shown[key]['sha256'] for key in ('before', 'after', 'support')},
        'inspection': {'rect': [0, 0, 8, 8], 'before_sha256': '1'*64, 'after_sha256': '2'*64}}
    with pytest.raises(ValueError, match='same actual'): H.confirm(engine, state, target, acknowledgement)


@pytest.mark.parametrize('change', ['document', 'body', 'graph', 'source', 'repair', 'measurement', 'private-amount'])
def test_stale_or_tampered_proof_refuses_without_live_mutation(monkeypatch, change):
    values, acknowledgement = inspected(monkeypatch)
    engine, state, target, _, bank, version, *_ = values
    if change == 'document': version.revision += 1
    elif change == 'body': bank['revision'] += 1
    elif change == 'graph': state['revision'] += 1
    elif change == 'source':
        pixels = np.full((64, 64, 3), .26, np.float32); pixels.setflags(write=False); engine.fixture_pixels = pixels
    elif change == 'repair': engine.fixture_repair = 'd'*64
    elif change == 'measurement': engine.fixture_measurement = 'd'*64
    else: engine._neck_wrinkle_preview['amount'] = .9
    with pytest.raises(ValueError): H.confirm(engine, state, target, acknowledgement)
    assert engine._people_support == {}


def test_sub_png_float_change_cannot_hide_behind_an_unchanged_crop_png(monkeypatch):
    values = ready(monkeypatch); engine, state, target, *_, shown = values
    engine.fixture_delta = 1e-7
    with pytest.raises(ValueError, match='frozen complete'):
        H.crop(engine, state, target, {'preview_id': shown['preview_id'], 'plane': 'after', 'rect': [20, 30, 16, 16]})
    assert engine._neck_wrinkle_preview['inspection'] is None


def test_actual_mixed_renderer_must_match_diagnostic_measurement_key(monkeypatch):
    engine, state, target, payload, *_ = fixture(monkeypatch)
    reference = H.reference(engine, state, target, {})
    H.crop(engine, state, target, {'reference_id': reference['reference_id'], 'plane': 'source', 'rect': [0, 0, 8, 8]})
    engine.fixture_render_measurement = 'd'*64
    with pytest.raises(ValueError, match='mixed renderer'): H.preview(engine, state, target, payload)
    assert engine._people_support == {} and engine._neck_wrinkle_preview is None


def test_private_records_never_keep_full_float_buffers_or_display_pngs(monkeypatch):
    values = ready(monkeypatch); engine = values[0]
    def check(value):
        assert not isinstance(value, (np.ndarray, bytes, bytearray))
        if isinstance(value, dict):
            assert 'base64' not in value
            for item in value.values(): check(item)
        elif isinstance(value, (tuple, list)):
            for item in value: check(item)
    check(engine._neck_wrinkle_reference); check(engine._neck_wrinkle_preview)


def test_atomic_detach_zeros_only_own_amount_without_model_source_or_native_resolution(monkeypatch):
    engine, state, target, payload, bank, _ = fixture(monkeypatch)
    analysis = engine._people_analyses[target['face_ref']['asset_sha256']][target['target_id']]
    state, assets = C.retain(state, {}, target['face_ref'], bank, analysis, payload['review'])
    state = P.set_override(state, 'face', target['target_id'], A.OP, '/amount', .7)
    engine._people_support = deepcopy(assets)
    def forbidden(*args, **kwargs): raise AssertionError('Neutral detach must not resolve pixels, model or native core')
    engine._body_bank = forbidden; engine._people_analyses = {}
    monkeypatch.setattr(H, '_source', forbidden); monkeypatch.setattr(H, '_capture', forbidden)
    monkeypatch.setattr(H, '_diagnostic', forbidden)
    old = deepcopy(state)
    candidate, reply = H.detach(engine, state, target, {})
    assert state == old and engine._people_support == assets
    assert C.KIND not in candidate['faces'][target['target_id']]['local_assets']
    assert [row['value'] for row in candidate['overrides'] if row['operation_id'] == A.OP] == [0.]
    assert reply['amount'] == 0 and reply['attached'] is False


def test_alias_admission_refuses_other_live_same_source_document(monkeypatch):
    from lumaretouch_engine import creative_derived_source as SOURCE
    from lumaretouch_engine import face_style_alias_review as ALIAS
    row = {'document_id': 'one'}; other = {'document_id': 'two'}
    monkeypatch.setattr(V, 'scope_rows', lambda _: [row, other])
    monkeypatch.setattr(SOURCE, 'row_asset', lambda _: 'a'*64)
    monkeypatch.setattr(ALIAS, 'verify_dormant', lambda *args: None)
    with pytest.raises(ValueError, match='current-photo only'):
        H._single_document(SimpleNamespace(), {'sha256': 'a'*64}, row, {})


def test_receipt_images_are_bounded_but_old_request_outcomes_remain():
    records = OrderedDict((str(i), {'result': {'success': True, 'payload': {
        'kind': ('reference', 'preview', 'crop')[i % 3], 'family': A.FAMILY,
        'operation_id': A.OP, 'image': {'base64': 'synthetic'}}}}) for i in range(6))
    H.bound_receipt_payloads(records)
    assert len(records) == 6 and sum('payload' in row['result'] for row in records.values()) == 2
    assert all(row['result']['success'] for row in records.values())
    assert all(records[str(i)]['result']['payload_released'] for i in range(4))


@pytest.mark.parametrize('rect', [[0., 0, 8, 8], [True, 0, 8, 8], [0, 0, 0, 8],
    [-1, 0, 8, 8], [0, 0, 1025, 1], [60, 60, 8, 8]])
def test_crop_edges_are_integer_bounded_and_never_resized(rect):
    with pytest.raises(ValueError): A.check_rect(rect, (64, 64))


def test_exact_crop_png_has_actual_source_pixels_and_hash():
    pixels = np.arange(20*24*3, dtype=np.uint8).reshape(20, 24, 3)
    result = I.crop_image(pixels, [3, 4, 11, 7]); raw = base64.b64decode(result['base64'])
    assert result['width'] == 11 and result['height'] == 7 and result['sha256'] == sha256(raw).hexdigest()
    with Image.open(io.BytesIO(raw)) as image:
        assert np.array_equal(np.asarray(image), pixels[4:11, 3:14])


def test_display_is_bounded_and_non_sdr_is_refused_not_clipped():
    pixels = np.zeros((1200, 2000, 3), np.float32)
    result = I.full_image(pixels)
    assert max(result['width'], result['height']) <= I.DISPLAY_EDGE and result['width'] <= 2000
    pixels[5, 5, 0] = 1.001
    with pytest.raises(ValueError, match='non-SDR'): I.full_image(pixels)


def test_support_display_uses_actual_native_eligibility_not_all_positive_brush_pixels():
    rgb = np.zeros((8, 8, 3), np.float32); admitted = np.ones((8, 8), np.float32)
    hard = np.zeros((8, 8), np.bool_); hard[1, 1] = True; admitted[1, 1] = 0
    eligible = np.zeros((8, 8), np.bool_); eligible[4, 4] = True
    image = I.support_image(rgb, admitted, hard, eligible, (0, 0, 8, 8))
    with Image.open(io.BytesIO(base64.b64decode(image['base64']))) as decoded:
        actual = np.asarray(decoded)
        assert actual[4, 4, 0] == 0 and actual[4, 4, 1] == actual[4, 4, 2] > 0  # Cyan.
        assert actual[1, 1, 1] == 0 and actual[1, 1, 0] == actual[1, 1, 2] > 0  # Magenta.
        assert actual[5, 5, 0] > actual[5, 5, 1] > actual[5, 5, 2] == 0  # Orange.
    eligible[1, 1] = True
    with pytest.raises(ValueError, match='protected support'): I.support_image(rgb, admitted, hard, eligible, (0, 0, 8, 8))


def test_crop_action_cannot_mix_source_and_output_domains_or_override_pixels():
    _, _, ref, *_ = support_fixture()
    target = {'scope': 'face', 'target_id': ref['face_instance_id'], 'face_ref': ref}
    invalid = [
        {'reference_id': 'r', 'preview_id': 'p', 'plane': 'source', 'rect': [0, 0, 1, 1]},
        {'reference_id': 'r', 'plane': 'after', 'rect': [0, 0, 1, 1]},
        {'preview_id': 'p', 'plane': 'source', 'rect': [0, 0, 1, 1]},
        {'reference_id': 'r', 'plane': 'source', 'rect': [0, 0, 1, 1], 'pixels': []}]
    for payload in invalid:
        with pytest.raises(ValueError): A.check_action('neck_wrinkle_crop', payload, target)



def test_direct_activation_cannot_bypass_full_review_publication(monkeypatch):
    engine, state, target, *_ = fixture(monkeypatch)
    candidate = P.set_override(state, 'face', target['target_id'], A.OP, '/amount', .5)
    with pytest.raises(ValueError, match='own reviewed'): H.require_transition(engine, state, candidate)


def test_exact_confirmation_context_admits_only_its_graph_and_bank(monkeypatch):
    values, ack = inspected(monkeypatch); engine, state, target, *_ = values
    candidate, _ = H.confirm(engine, state, target, ack)
    with pytest.raises(ValueError, match='own reviewed'): H.require_transition(engine, state, candidate)
    with H.reviewed_transition(engine, state, candidate):
        assert H.require_transition(engine, state, candidate) == candidate
        changed = P.set_override(candidate, 'face', target['target_id'], A.OP, '/amount', .6)
        with pytest.raises(ValueError, match='changed before publication'): H.require_transition(engine, state, changed)
    assert '_neck_wrinkle_publication_permit' not in engine.__dict__
    assert '_neck_wrinkle_publication_admission' not in engine.__dict__
    with pytest.raises(ValueError, match='private confirmed'): 
        with H.reviewed_transition(engine, state, candidate): pass


def test_publication_admission_clears_even_if_existing_publish_fails(monkeypatch):
    values, ack = inspected(monkeypatch); engine, state, target, *_ = values
    candidate, _ = H.confirm(engine, state, target, ack)
    with pytest.raises(RuntimeError, match='synthetic publish failure'):
        with H.reviewed_transition(engine, state, candidate):
            raise RuntimeError('synthetic publish failure')
    assert '_neck_wrinkle_publication_permit' not in engine.__dict__
    assert '_neck_wrinkle_publication_admission' not in engine.__dict__


def test_neutral_transition_needs_no_fresh_analysis_and_preserves_harmless_edits(monkeypatch):
    engine, state, target, payload, bank, _ = fixture(monkeypatch)
    analysis = engine._people_analyses[target['face_ref']['asset_sha256']][target['target_id']]
    active, assets = C.retain(state, {}, target['face_ref'], bank, analysis, payload['review'])
    active = P.set_override(active, 'face', target['target_id'], A.OP, '/amount', .4)
    engine._people_support = assets
    harmless = deepcopy(active); harmless['faces'][target['target_id']]['labels']['note'] = 'unrelated label'
    harmless['revision'] += 1
    assert H.require_transition(engine, active, harmless) == harmless
    zero = P.set_override(active, 'face', target['target_id'], A.OP, '/amount', 0.)
    engine._people_analyses = {}; engine._body_bank = lambda: (_ for _ in ()).throw(AssertionError('model lookup'))
    assert H.require_transition(engine, active, zero) == zero
    detached = C.detach(zero, target['face_ref'])
    assert H.require_transition(engine, active, detached) == detached
    changed_owner = deepcopy(active); changed_owner['association_revision'] += 1
    with pytest.raises(ValueError, match='ownership changes'): H.require_transition(engine, active, changed_owner)


@pytest.mark.parametrize('value,expected', [(0, True), (0., True), (-0., True), (False, False),
    (True, False), (.1, False), (float('nan'), False), ('0', False)])
def test_exact_neutral_patch_classifier_never_treats_boolean_as_zero(value, expected):
    raw = {'action': 'patch', 'payload': {'patches': [{'operation_id': A.OP,
        'parameter_path': '/amount', 'unset': False, 'value': value}]}}
    assert A.neutral_patch(raw) is expected
    assert A.is_neck_command(raw) is expected
    raw['payload']['patches'].append(deepcopy(raw['payload']['patches'][0]))
    assert not A.neutral_patch(raw)
