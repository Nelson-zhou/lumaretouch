"""AUTHORED / UNRUN: spill target review adapter and PNG transport contracts.

Nothing in this file was imported, collected or executed during authoring.
The complete renderer and its identity adapter are mocked deliberately. If run
later, these fixtures exercise real bounded PNG encoding and review validation,
not source decoding, numerical spill removal, native rendering or visual quality.
The synthetic float frames are not photographic or manual acceptance evidence.
"""
import base64
from copy import deepcopy
from hashlib import sha256
import io
import json
from types import SimpleNamespace

import numpy as np
from PIL import Image
import pytest

from lumaretouch_engine import creative_derived_source as SOURCE
from lumaretouch_engine import full_candidate_render as FULL
from lumaretouch_engine import id_background_state as ID
from lumaretouch_engine import spill_removal_scope as SPILL
from lumaretouch_engine import spill_removal_state as STATE
from lumaretouch_engine import spill_transfer_review as REVIEW
from lumaretouch_engine.optics_candidate_identity import fingerprint
from lumaretouch_engine.ops.geometry import out_size
from test_spill_transfer_wiring_unrun import owned_id


def render_fixture(tmp_path, monkeypatch, size=(640, 480)):
    """Expose an honest mocked full-frame boundary, not a mock PNG encoder."""
    path = tmp_path / 'synthetic-source-not-an-image.bin'
    path.write_bytes(b'original source identity for unrun adapter regression')
    before = {'_crop_rect': [0., 0., 1., 1.], '_crop_rotation': 0.,
        '_exposure': (0., 0., 0., 0., 0., 0., 0.), 'unscoped_edit': 'retained'}
    before['_id_background'] = owned_id(SOURCE.binding(before, str(path), size))
    candidate = deepcopy(before)
    candidate['_id_background'] = ID.with_spill(candidate['_id_background'],
        {**STATE.neutral(), 'enabled': True, 'strength': 81.})
    row = {'path': str(path), 'src_w': size[0], 'src_h': size[1], 'state': before}
    engine = SimpleNamespace(people={'graph': 'synthetic retained ownership'})
    calls = []

    def identity(owner, target, state, document_id, revision):
        assert owner is engine and target is row
        proof = SOURCE.row_proof({**target, 'state': state})
        return {'document_id': document_id, 'revision': str(revision), 'source_proof': proof,
            'candidate_sha256': fingerprint(state), 'people_sha256': fingerprint(owner.people)}, {}, {}

    def render(owner, target, state, document_id, revision):
        proof, _, _ = identity(owner, target, state, document_id, revision)
        source = proof['source_proof']['creative_source']
        source_size = [source['width'], source['height']] if source else [target['src_w'], target['src_h']]
        width, height = out_size(*source_size, state['_crop_rect'], state['_crop_rotation'])
        pixels = np.empty((height, width, 3), dtype=np.float32)
        # Out-of-display-range values prove reduction/clipping never changes
        # the completed float input. This is not a spill simulation.
        pixels[:, :, 0] = np.linspace(-.25, 1.25, width, dtype=np.float32)[None, :]
        pixels[:, :, 1] = np.linspace(0., 1., height, dtype=np.float32)[:, None]
        pixels[:, :, 2] = .8 if SPILL.params_of(state)['enabled'] else .2
        calls.append({'state': deepcopy(state), 'pixels': pixels, 'unchanged': pixels.copy()})
        return pixels, {**proof, 'source_size': source_size, 'output_size': [width, height]}

    monkeypatch.setattr(FULL, 'identity', identity)
    monkeypatch.setattr(FULL, 'render', render)
    return engine, row, before, candidate, calls


def prepare(fixture):
    engine, row, before, candidate, _ = fixture
    return REVIEW.prepare(engine, row, before, candidate, 'target-1', '7')


def acknowledgment(record):
    return {'document_id': record['document_id'], 'revision': record['revision'],
        'before_sha256': record['before']['sha256'], 'after_sha256': record['after']['sha256']}


def test_complete_before_after_render_precedes_real_bounded_png_encoding(tmp_path, monkeypatch):
    fixture = render_fixture(tmp_path, monkeypatch); _, row, before, candidate, calls = fixture
    frozen_row = deepcopy(row); record, public = prepare(fixture)
    assert len(calls) == 2 and calls[0]['state'] == before and calls[1]['state'] == candidate
    assert row == frozen_row and record['source_size'] == [640, 480]
    assert record['before_output_size'] == record['after_output_size'] == [640, 480]
    assert record['before']['sha256'] != record['after']['sha256']
    assert set(record) == REVIEW.FIELDS and 'base64' not in json.dumps(record)
    assert REVIEW.checked(record) == record
    for side, call in zip(('before', 'after'), calls):
        np.testing.assert_array_equal(call['pixels'], call['unchanged'])
        image = public[side]; raw = base64.b64decode(image['base64'], validate=True)
        assert len(raw) <= REVIEW.MAX_PNG_BYTES and len(image['base64']) <= REVIEW.MAX_BASE64
        assert sha256(raw).hexdigest() == image['sha256'] == record[side]['sha256']
        assert set(image) == {'mime', 'width', 'height', 'sha256', 'base64'}
        with Image.open(io.BytesIO(raw)) as decoded:
            decoded.load()
            assert decoded.format == 'PNG' and decoded.mode == 'RGB'
            assert decoded.size == (256, 192) == (image['width'], image['height'])


def test_before_after_can_have_different_full_crop_and_preview_geometry(tmp_path, monkeypatch):
    fixture = render_fixture(tmp_path, monkeypatch); candidate = fixture[3]
    candidate['_crop_rect'] = [0., 0., .5, .5]
    candidate['_crop_rotation'] = 90.
    record, public = prepare(fixture)
    assert record['before_output_size'] == [640, 480]
    assert record['after_output_size'] == [240, 320]
    assert (public['before']['width'], public['before']['height']) == (256, 192)
    assert (public['after']['width'], public['after']['height']) == (192, 256)
    assert [call['pixels'].shape for call in fixture[4]] == [(480, 640, 3), (320, 240, 3)]
    assert REVIEW.verify(*fixture[:4], 'target-1', '7', record) == record


def test_small_complete_image_is_not_upscaled_for_review(tmp_path, monkeypatch):
    fixture = render_fixture(tmp_path, monkeypatch, size=(32, 24))
    record, public = prepare(fixture)
    assert (record['before']['width'], record['before']['height']) == (32, 24)
    with Image.open(io.BytesIO(base64.b64decode(public['after']['base64']))) as decoded:
        assert decoded.size == (32, 24)


@pytest.mark.parametrize('changed', ['source', 'people', 'before-unscoped', 'candidate-unscoped', 'candidate-spill', 'crop', 'extent', 'document', 'revision'])
def test_verify_rejects_changed_source_people_or_full_edits_without_rerender(tmp_path, monkeypatch, changed):
    fixture = render_fixture(tmp_path, monkeypatch); record, _ = prepare(fixture)
    engine, row, before, candidate, calls = fixture
    document, revision = 'target-1', '7'
    if changed == 'source': (tmp_path / 'synthetic-source-not-an-image.bin').write_bytes(b'different original')
    elif changed == 'people': engine.people['graph'] = 'different retained owner'
    elif changed == 'before-unscoped': before['unscoped_edit'] = 'changed prior target edit'
    elif changed == 'candidate-unscoped': candidate['unscoped_edit'] = 'changed proposed target edit'
    elif changed == 'candidate-spill': candidate['_id_background']['spill']['strength'] = 40.
    elif changed == 'crop': candidate['_crop_rect'] = [0., 0., .5, 1.]
    elif changed == 'extent': row['src_w'] += 1
    elif changed == 'document': document = 'target-2'
    else: revision = '8'
    with pytest.raises(ValueError): REVIEW.verify(engine, row, before, candidate, document, revision, record)
    assert len(calls) == 2


@pytest.mark.parametrize('fault', ['integer-proxy', 'reduced-proxy', 'nan', 'infinity', 'wrong-state', 'wrong-people', 'wrong-source', 'wrong-source-size', 'wrong-output-size', 'extra-proof', 'missing-proof'])
def test_incomplete_or_mismatched_full_render_is_rejected_not_relabelled(tmp_path, monkeypatch, fault):
    fixture = render_fixture(tmp_path, monkeypatch); original = FULL.render
    before = deepcopy(fixture[1])

    def invalid(*args):
        pixels, proof = original(*args)
        if fault == 'integer-proxy': pixels = np.zeros_like(pixels, dtype=np.uint8)
        elif fault == 'reduced-proxy': pixels = pixels[::2, ::2]
        elif fault == 'nan': pixels[0, 0, 0] = np.nan
        elif fault == 'infinity': pixels[0, 0, 0] = np.inf
        elif fault == 'wrong-state': proof['candidate_sha256'] = '0' * 64
        elif fault == 'wrong-people': proof['people_sha256'] = '0' * 64
        elif fault == 'wrong-source': proof['source_proof'] = {'asset_sha256': '0' * 64, 'original_sha256': '0' * 64, 'creative_source': None}
        elif fault == 'wrong-source-size': proof['source_size'] = [320, 240]
        elif fault == 'wrong-output-size': proof['output_size'] = [320, 240]
        elif fault == 'extra-proof': proof['proxy_allowed'] = True
        else: proof.pop('people_sha256')
        return pixels, proof

    monkeypatch.setattr(FULL, 'render', invalid)
    with pytest.raises(ValueError): prepare(fixture)
    assert fixture[1] == before and len(fixture[4]) == 1


@pytest.mark.parametrize('changed', ['source', 'people', 'unscoped'])
def test_change_during_render_invalidates_pair_before_return(tmp_path, monkeypatch, changed):
    fixture = render_fixture(tmp_path, monkeypatch); original = FULL.render

    def racing(*args):
        result = original(*args)
        if len(fixture[4]) == 2:
            if changed == 'source': (tmp_path / 'synthetic-source-not-an-image.bin').write_bytes(b'changed while rendering')
            elif changed == 'people': fixture[0].people['graph'] = 'changed while rendering'
            else: fixture[3]['unscoped_edit'] = 'changed while rendering'
        return result

    monkeypatch.setattr(FULL, 'render', racing)
    with pytest.raises(ValueError): prepare(fixture)
    assert len(fixture[4]) == 2


def test_png_budget_failure_rejects_review_without_proxy_or_omitted_after(tmp_path, monkeypatch):
    fixture = render_fixture(tmp_path, monkeypatch); before = deepcopy(fixture[1])
    monkeypatch.setattr(REVIEW, 'MAX_PNG_BYTES', 1)
    with pytest.raises(ValueError, match='transport budget'): prepare(fixture)
    assert fixture[1] == before and len(fixture[4]) == 1


def test_high_entropy_png_reduces_display_only_without_rerender_or_source_proxy(tmp_path, monkeypatch):
    fixture = render_fixture(tmp_path, monkeypatch, size=(256, 256)); original = FULL.render

    def noisy_complete_render(*args):
        pixels, proof = original(*args)
        rng = np.random.default_rng(1042 + len(fixture[4]))
        pixels[:] = rng.integers(0, 256, size=pixels.shape, dtype=np.uint8).astype(np.float32) / 255.
        fixture[4][-1]['unchanged'] = pixels.copy()
        return pixels, proof

    monkeypatch.setattr(FULL, 'render', noisy_complete_render)
    record, public = prepare(fixture)
    assert len(fixture[4]) == 2
    assert record['source_size'] == record['before_output_size'] == record['after_output_size'] == [256, 256]
    for side, call in zip(('before', 'after'), fixture[4]):
        assert call['pixels'].shape == (256, 256, 3)
        np.testing.assert_array_equal(call['pixels'], call['unchanged'])
        assert public[side]['width'] == public[side]['height'] < REVIEW.PREVIEW_EDGE
        raw = base64.b64decode(public[side]['base64'], validate=True)
        assert len(raw) <= REVIEW.MAX_PNG_BYTES and sha256(raw).hexdigest() == record[side]['sha256']
        with Image.open(io.BytesIO(raw)) as decoded:
            assert decoded.size == (record[side]['width'], record[side]['height'])


@pytest.mark.parametrize('fault', ['private-pixels', 'unknown-field', 'missing-field', 'digest', 'dimension', 'oversized-preview', 'wrong-aspect', 'boolean-version'])
def test_private_record_requires_exact_compact_schema(tmp_path, monkeypatch, fault):
    fixture = render_fixture(tmp_path, monkeypatch); record, public = prepare(fixture)
    if fault == 'private-pixels': record['before'] = public['before']
    elif fault == 'unknown-field': record['preview_jpeg'] = 'not allowed'
    elif fault == 'missing-field': record.pop('candidate_people_sha256')
    elif fault == 'digest': record['before']['sha256'] = 'not a digest'
    elif fault == 'dimension': record['source_size'][0] = True
    elif fault == 'oversized-preview': record['before']['width'] = REVIEW.PREVIEW_EDGE + 1
    elif fault == 'wrong-aspect': record['before']['height'] = 1
    else: record['version'] = True
    with pytest.raises(ValueError): REVIEW.checked(record)


def test_checked_and_acknowledgments_return_detached_compact_values(tmp_path, monkeypatch):
    fixture = render_fixture(tmp_path, monkeypatch); record, public = prepare(fixture)
    checked = REVIEW.checked(record); ack = acknowledgment(record)
    accepted = REVIEW.acknowledgments([ack], [record])
    checked['before']['sha256'] = '0' * 64
    accepted[0]['after_sha256'] = '0' * 64
    public['after']['base64'] = 'changed presentation payload'
    assert record['before']['sha256'] != '0' * 64 and ack['after_sha256'] != '0' * 64
    assert 'base64' not in json.dumps(record)


@pytest.mark.parametrize('fault', ['missing', 'boolean', 'partial', 'target-order', 'image-order', 'duplicate-ack', 'duplicate-target', 'extra-field', 'overbudget'])
def test_acknowledgments_require_exact_ordered_complete_target_pairs(tmp_path, monkeypatch, fault):
    fixture = render_fixture(tmp_path, monkeypatch); record, _ = prepare(fixture)
    other = {**deepcopy(record), 'document_id': 'target-2'}
    records = [record, other]; acks = [acknowledgment(value) for value in records]
    if fault == 'missing': acks = None
    elif fault == 'boolean': acks = True
    elif fault == 'partial': acks.pop()
    elif fault == 'target-order': acks.reverse()
    elif fault == 'image-order':
        acks[0]['before_sha256'], acks[0]['after_sha256'] = acks[0]['after_sha256'], acks[0]['before_sha256']
    elif fault == 'duplicate-ack': acks[1] = deepcopy(acks[0])
    elif fault == 'duplicate-target': records[1] = deepcopy(records[0]); acks[1] = deepcopy(acks[0])
    elif fault == 'extra-field': acks[0]['approved'] = True
    else:
        records = [{**deepcopy(record), 'document_id': f'target-{index}'} for index in range(REVIEW.MAX_TARGETS + 1)]
        acks = [acknowledgment(value) for value in records]
    with pytest.raises(ValueError): REVIEW.acknowledgments(acks, records)


def test_exact_maximum_target_ack_list_is_not_silently_shortened(tmp_path, monkeypatch):
    fixture = render_fixture(tmp_path, monkeypatch); record, _ = prepare(fixture)
    records = [{**deepcopy(record), 'document_id': f'target-{index}'} for index in range(REVIEW.MAX_TARGETS)]
    acks = [acknowledgment(value) for value in records]
    assert REVIEW.acknowledgments(acks, records) == acks and len(acks) == 8


@pytest.mark.parametrize('field', ['_brow_shape', '_nose_shape', '_eye_shape', '_mouth_shape', '_lip_makeup',
    '_eye_light_preset', '_blush_makeup_preset', '_lipstick_preset', '_eyeliner_preset',
    '_eyelash_preset', '_brow_makeup_preset', '_iris_makeup_preset'])
def test_managed_face_patch_cannot_be_shown_as_retained_graph_candidate(field):
    asset = 'a' * 64
    graph = {'faces': {'face': {'asset_sha256': asset}}}
    before = {field: {'strength': 0}}
    candidate = {field: {'strength': 1}}
    with pytest.raises(ValueError, match='混合预设'):
        REVIEW._require_retained_people_candidate(before, candidate, graph, asset)
    # No new graph/mask is invented, and already committed unchanged intent is fine.
    REVIEW._require_retained_people_candidate(candidate, candidate, graph, asset)
    REVIEW._require_retained_people_candidate(before, candidate, graph, 'b' * 64)


@pytest.mark.parametrize('mismatch', ['missing-owner', 'missing-key', 'asset', 'precompute', 'owner-fence'])
def test_live_people_analysis_must_already_match_exact_owner_binding(mismatch):
    row = {}; asset = 'a' * 64; pc = object(); owner = SimpleNamespace(fence=4); binds = []
    engine = SimpleNamespace(_docs=[row], _doc_index=0, _vram=object(), _precompute=pc,
        _people_graph_owner=owner, _people_analysis_key=(asset, id(pc), owner.fence),
        _people_bind=lambda *args: binds.append(args))
    if mismatch == 'missing-owner': engine._people_graph_owner = None
    elif mismatch == 'missing-key': del engine._people_analysis_key
    elif mismatch == 'asset': engine._people_analysis_key = ('b' * 64, id(pc), owner.fence)
    elif mismatch == 'precompute': engine._precompute = object()
    else: owner.fence += 1
    before = dict(engine.__dict__); graph = {'faces': {}, 'unresolved_legacy': []}
    with pytest.raises(ValueError, match='稳定绑定'):
        REVIEW._require_stable_live_people(engine, row, graph, asset)
    assert engine.__dict__ == before and not binds
    assert graph == {'faces': {}, 'unresolved_legacy': []}


def test_stable_live_people_analysis_is_read_only_and_does_not_bind_again():
    row = {}; asset = 'a' * 64; pc = object(); owner = SimpleNamespace(fence=4); binds = []
    engine = SimpleNamespace(_docs=[row], _doc_index=0, _vram=object(), _precompute=pc,
        _people_graph_owner=owner, _people_analysis_key=(asset, id(pc), owner.fence),
        _people_bind=lambda *args: binds.append(args))
    before = dict(engine.__dict__)
    REVIEW._require_stable_live_people(engine, row, {'faces': {}}, asset)
    assert engine.__dict__ == before and not binds


@pytest.mark.parametrize('marker', ['missing', 'wrong-asset', 'wrong-kind'])
def test_live_people_without_analysis_needs_exact_completed_migration(marker):
    row = {}; asset = 'a' * 64; binds = []
    engine = SimpleNamespace(_docs=[row], _doc_index=0, _vram=object(), _precompute=None,
        _people_graph_owner=SimpleNamespace(fence=4), _people_bind=lambda *args: binds.append(args))
    item = {'legacy_key': '_migration_complete', 'asset_sha256': asset}
    if marker == 'wrong-asset': item['asset_sha256'] = 'b' * 64
    elif marker == 'wrong-kind': item['legacy_key'] = 'unresolved-edit'
    graph = {'unresolved_legacy': [] if marker == 'missing' else [item]}
    before = deepcopy(graph)
    with pytest.raises(ValueError, match='来源迁移'):
        REVIEW._require_stable_live_people(engine, row, graph, asset)
    assert graph == before and not binds
    graph['unresolved_legacy'] = [{'legacy_key': '_migration_complete', 'asset_sha256': asset}]
    REVIEW._require_stable_live_people(engine, row, graph, asset)
    assert not binds


@pytest.mark.parametrize('context', ['parked', 'no-live-renderer'])
def test_spill_review_never_activates_or_migrates_an_unbound_parked_target(context):
    row = {}; binds = []
    engine = SimpleNamespace(_docs=[row if context == 'no-live-renderer' else {}], _doc_index=0,
        _vram=None if context == 'no-live-renderer' else object(), _precompute=object(),
        _people_graph_owner=None, _people_bind=lambda *args: binds.append(args))
    before = dict(engine.__dict__)
    REVIEW._require_stable_live_people(engine, row, {}, 'a' * 64)
    assert engine.__dict__ == before and not binds


def test_unstable_live_people_blocks_spill_pair_before_either_render(tmp_path, monkeypatch):
    fixture = render_fixture(tmp_path, monkeypatch); engine, row, _, _, calls = fixture
    engine._docs = [row]; engine._doc_index = 0; engine._vram = object()
    engine._precompute = object(); engine._people_graph_owner = None
    before = deepcopy(row)
    with pytest.raises(ValueError, match='稳定绑定'): prepare(fixture)
    assert row == before and not calls


def test_rollback_record_uses_only_frozen_before_state_people_images_and_geometry(tmp_path, monkeypatch):
    fixture = render_fixture(tmp_path, monkeypatch); engine, row, before, candidate, calls = fixture
    candidate['_crop_rect'] = [0., 0., .5, .5]; candidate['_crop_rotation'] = 90.
    record, _ = prepare(fixture); frozen = deepcopy(record)
    rollback = REVIEW.rollback_record(record, before, '8')
    assert rollback['revision'] == '8' and record == frozen
    assert rollback['candidate_sha256'] == rollback['before_sha256'] == record['before_sha256']
    assert rollback['candidate_people_sha256'] == rollback['before_people_sha256'] == record['before_people_sha256']
    assert rollback['after_output_size'] == rollback['before_output_size'] == [640, 480]
    assert rollback['after'] == rollback['before'] == record['before']
    assert rollback['parameters'] == SPILL.params_of(before) != record['parameters']
    assert 'base64' not in json.dumps(rollback)
    assert REVIEW.verify(engine, row, before, deepcopy(before), 'target-1', '8', rollback) == rollback
    assert len(calls) == 2
    rollback['after']['sha256'] = '0' * 64
    rollback['after_output_size'][0] = 1
    assert rollback['before'] == record['before'] and record == frozen


@pytest.mark.parametrize('changed', ['source', 'people', 'state'])
def test_rollback_verification_cannot_rebase_proof_to_current_drift(tmp_path, monkeypatch, changed):
    fixture = render_fixture(tmp_path, monkeypatch); engine, row, before, _, calls = fixture
    record, _ = prepare(fixture); frozen = deepcopy(record); actual = deepcopy(before)
    if changed == 'source': (tmp_path / 'synthetic-source-not-an-image.bin').write_bytes(b'changed during failed apply')
    elif changed == 'people': engine.people['graph'] = 'externally changed during failed apply'
    else: actual['unscoped_edit'] = 'rollback returned an inexact state'
    rollback = REVIEW.rollback_record(record, before, '8')
    assert rollback['candidate_people_sha256'] == frozen['before_people_sha256']
    assert rollback['candidate_sha256'] == frozen['before_sha256']
    assert rollback['source_proof'] == frozen['source_proof']
    with pytest.raises(ValueError):
        REVIEW.verify(engine, row, before, actual, 'target-1', '8', rollback)
    assert record == frozen and len(calls) == 2


def test_managed_wrinkle_change_cannot_reuse_retained_people_graph():
    asset = 'a' * 64; graph = {'faces': {'face': {'asset_sha256': asset}}}
    before = {'_enhance': {'amounts': {'wrinkle_nose': 0.}}}
    candidate = {'_enhance': {'amounts': {'wrinkle_nose': .5}}}
    with pytest.raises(ValueError, match='混合预设'):
        REVIEW._require_retained_people_candidate(before, candidate, graph, asset)
    REVIEW._require_retained_people_candidate(candidate, candidate, graph, asset)
