# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: actual-owner review boundary and bounded PNG contracts.

Only the complete renderer/identity boundary is mocked. Source/body/face review
validation and PNG encoding remain actual code if explicitly run later. Synthetic
records and float frames prove no anatomy, numerical solver or photo quality.
No product imports, test collection/execution or builds ran while authoring.
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
from lumaretouch_engine import body_pose_project as D, body_pose_state as B
from lumaretouch_engine import waist_length_project as P, waist_length_state as S
from lumaretouch_engine import waist_length_scope as T, waist_length_transfer_review as REVIEW
from lumaretouch_engine import shoulder_shape_state as SHOULDER
from lumaretouch_engine.optics_candidate_identity import fingerprint
from lumaretouch_engine.ops.geometry import out_size
from test_waist_length_support_unrun import fixture


def render_fixture(tmp_path, monkeypatch, *, derived=False, source_size=(1024, 1024)):
    path = tmp_path / 'synthetic-waist-source-not-an-image.bin'
    path.write_bytes(b'synthetic source identity, not a photo or anatomical evidence')
    before = {'_crop_rect': [0., 0., 1., 1.], '_crop_rotation': 0.,
              '_exposure': (0., 0., 0., 0., 0., 0., 0.), 'unrelated_edit': 'retained'}
    width, height = source_size
    if derived:
        from lumaretouch_engine.creative_document_assets import make_asset
        rgba = np.zeros((height, width, 4), dtype='<f4'); rgba[..., 3] = 1.
        before['_creative_base'] = make_asset('rgba', width, height, rgba.tobytes())
    effective = SOURCE.binding(before, str(path), (width, height))
    bank, people, ref, _, _ = fixture(amount=.2, source={**effective, 'orientation': 'exif_normalized_once'})
    before[D.KEY] = P.pack(bank)
    candidate = deepcopy(before); T.install(candidate, {'version': 1, 'amount': -.5})
    row = {'path': str(path), 'src_w': width, 'src_h': height, 'state': before}
    engine = SimpleNamespace(people=people)
    calls = []

    def identity(owner, target, state, document_id, revision):
        assert owner is engine and target is row
        proof = SOURCE.row_proof({**target, 'state': state})
        return {'document_id': document_id, 'revision': str(revision), 'source_proof': proof,
                'candidate_sha256': fingerprint(state), 'people_sha256': fingerprint(owner.people)}, deepcopy(owner.people), {}

    def render(owner, target, state, document_id, revision):
        proof, _, _ = identity(owner, target, state, document_id, revision)
        source = proof['source_proof']['creative_source']
        extent = [source['width'], source['height']] if source else [target['src_w'], target['src_h']]
        width, height = out_size(*extent, state['_crop_rect'], state['_crop_rotation'])
        pixels = np.empty((height, width, 3), dtype=np.float32)
        pixels[:, :, 0] = np.linspace(-.25, 1.25, width, dtype=np.float32)[None, :]
        pixels[:, :, 1] = np.linspace(0., 1., height, dtype=np.float32)[:, None]
        pixels[:, :, 2] = .3 + .2*T.params_of(state)['amount']
        calls.append({'state': deepcopy(state), 'pixels': pixels, 'unchanged': pixels.copy()})
        return pixels, {**proof, 'source_size': extent, 'output_size': [width, height]}

    monkeypatch.setattr(FULL, 'identity', identity); monkeypatch.setattr(FULL, 'render', render)
    return engine, row, before, candidate, calls, ref


def prepare(data):
    return REVIEW.prepare(*data[:4], 'waist-target', '7')


def ack(record):
    return {'document_id': record['document_id'], 'revision': record['revision'],
            'before_sha256': record['before']['sha256'], 'after_sha256': record['after']['sha256']}


@pytest.mark.parametrize('derived', [False, True])
def test_full_source_pair_freezes_actual_target_body_face_support_and_all_people(tmp_path, monkeypatch, derived):
    data = render_fixture(tmp_path, monkeypatch, derived=derived)
    frozen_row = deepcopy(data[1]); record, public = prepare(data)
    assert data[1] == frozen_row and len(data[4]) == 2
    assert [x['state'] for x in data[4]] == list(data[2:4])
    assert record['body_ref'] == data[5]
    assert record['associated_face'] == {key: T.target(data[2])[3]['data'][key] for key in S.FACE_BINDING_KEYS}
    assert record['before_bank_sha256'] == T.bank_sha256(data[2])
    assert record['candidate_bank_sha256'] == T.bank_sha256(data[3])
    assert set(record) == REVIEW.FIELDS and 'base64' not in json.dumps(record)
    assert REVIEW.checked(record) == record
    for side, call in zip(('before', 'after'), data[4]):
        np.testing.assert_array_equal(call['pixels'], call['unchanged'])
        raw = base64.b64decode(public[side]['base64'], validate=True)
        assert len(raw) <= REVIEW.MAX_PNG_BYTES and len(public[side]['base64']) <= REVIEW.MAX_BASE64
        assert sha256(raw).hexdigest() == record[side]['sha256']
        with Image.open(io.BytesIO(raw)) as image:
            image.load(); assert image.mode == 'RGB' and image.size == (256, 256)


@pytest.mark.parametrize('fault', ['box', 'evidence', 'analysis-revision', 'association-revision', 'manual', 'unresolved'])
def test_actual_graph_drift_refuses_before_any_view_without_rebinding(tmp_path, monkeypatch, fault):
    data = render_fixture(tmp_path, monkeypatch); people = data[0].people
    face = next(iter(people['faces'].values()))
    if fault == 'box': face['box'][0] += .001
    elif fault == 'evidence': face['evidence']['landmark_digest'] = 'f'*64
    elif fault == 'analysis-revision': face['analysis_revision'] += 1
    elif fault == 'association-revision': people['association_revision'] += 1; people['revision'] += 1
    elif fault == 'manual': face['manual'] = True
    else: face['evidence']['status'] = 'unresolved'
    before = deepcopy(data[1])
    with pytest.raises(ValueError): prepare(data)
    assert data[4] == [] and data[1] == before


def test_candidate_cannot_smuggle_another_body_operation_into_waist_review(tmp_path, monkeypatch):
    data = render_fixture(tmp_path, monkeypatch)
    bank = B.set_recipe(D.bank(data[3]), data[5], SHOULDER.neutral(), operation_id=SHOULDER.OPERATION_ID)
    data[3][D.KEY] = P.pack(bank)
    with pytest.raises(ValueError): prepare(data)
    assert data[4] == []


@pytest.mark.parametrize('fault', ['uint8', 'reduced', 'nan', 'wrong-people', 'wrong-source', 'wrong-extent'])
def test_proxy_or_incorrect_full_render_never_becomes_review_evidence(tmp_path, monkeypatch, fault):
    data = render_fixture(tmp_path, monkeypatch); original = FULL.render
    def invalid(*args):
        pixels, proof = original(*args)
        if fault == 'uint8': pixels = np.zeros_like(pixels, dtype=np.uint8)
        elif fault == 'reduced': pixels = pixels[::2, ::2]
        elif fault == 'nan': pixels[0, 0, 0] = np.nan
        elif fault == 'wrong-people': proof['people_sha256'] = '0'*64
        elif fault == 'wrong-source': proof['source_proof']['asset_sha256'] = '0'*64
        else: proof['source_size'] = [512, 512]
        return pixels, proof
    monkeypatch.setattr(FULL, 'render', invalid)
    with pytest.raises(ValueError): prepare(data)
    assert len(data[4]) == 1


def test_crop_keeps_exact_source_support_while_preview_uses_real_output_geometry(tmp_path, monkeypatch):
    data = render_fixture(tmp_path, monkeypatch)
    data[3]['_crop_rect'] = [0., 0., .5, 1.]; data[3]['_crop_rotation'] = 90.
    record, public = prepare(data)
    assert record['source_size'] == [1024, 1024]
    assert record['after_output_size'] == [1024, 512]
    assert (public['after']['width'], public['after']['height']) == (256, 128)


def test_exact_ordered_acknowledgments_refuse_omissions_reorder_duplicates_and_overflow(tmp_path, monkeypatch):
    record, _ = prepare(render_fixture(tmp_path, monkeypatch))
    other = {**deepcopy(record), 'document_id': 'another-target'}
    assert REVIEW.acknowledgments([ack(record), ack(other)], [record, other]) == [ack(record), ack(other)]
    for raw, records in ((True, [record]), ([], [record]), ([ack(other), ack(record)], [record, other]),
                         ([ack(record), ack(record)], [record, record]),
                         ([ack(record)]*9, [record]*9)):
        with pytest.raises(ValueError): REVIEW.acknowledgments(raw, records)


def test_frozen_rollback_uses_prior_bank_people_and_images_without_rebase(tmp_path, monkeypatch):
    data = render_fixture(tmp_path, monkeypatch); record, _ = prepare(data)
    rollback = REVIEW.rollback_record(record, data[2], '8')
    assert rollback['candidate_bank_sha256'] == record['before_bank_sha256']
    assert rollback['candidate_people_sha256'] == record['before_people_sha256']
    assert rollback['after'] == record['before']
    assert REVIEW.verify(data[0], data[1], data[2], data[2], 'waist-target', '8', rollback) == rollback


def test_history_identity_checks_current_face_consent_without_render_or_state_mutation(tmp_path, monkeypatch):
    data = render_fixture(tmp_path, monkeypatch); before = deepcopy(data[1])
    proof = REVIEW.history_identity(data[0], data[1], data[2], 'waist-target', '7')
    assert set(proof) == REVIEW.IDENTITY_FIELDS and data[4] == [] and data[1] == before
    face = next(iter(data[0].people['faces'].values())); face['box'][0] += .001
    with pytest.raises(ValueError): REVIEW.history_identity(data[0], data[1], data[2], 'waist-target', '7')
    assert data[4] == []


def test_mid_render_graph_drift_invalidates_completed_pair(tmp_path, monkeypatch):
    data = render_fixture(tmp_path, monkeypatch); original = FULL.render
    def racing(*args):
        result = original(*args)
        if len(data[4]) == 2:
            face = next(iter(data[0].people['faces'].values())); face['evidence']['landmark_digest'] = 'f'*64
        return result
    monkeypatch.setattr(FULL, 'render', racing)
    with pytest.raises(ValueError): prepare(data)
    assert len(data[4]) == 2


@pytest.mark.parametrize('changed', ['source', 'full-state', 'bank', 'proof-body', 'proof-face', 'proof-support', 'proof-bank', 'proof-pixels'])
def test_stale_or_widened_compact_proof_cannot_authorize_replay(tmp_path, monkeypatch, changed):
    data = render_fixture(tmp_path, monkeypatch); record, _ = prepare(data)
    if changed == 'source': (tmp_path / 'synthetic-waist-source-not-an-image.bin').write_bytes(b'changed original bytes')
    elif changed == 'full-state': data[3]['unrelated_edit'] = 'changed after view'
    elif changed == 'bank':
        bank = D.bank(data[3]); bank['revision'] += 1; data[3][D.KEY] = P.pack(bank)
    elif changed == 'proof-body': record['body_ref']['body_instance_id'] = 'foreign-body'
    elif changed == 'proof-face': record['associated_face']['associated_face_ref']['face_instance_id'] = 'foreign-face'
    elif changed == 'proof-support': record['body_support_sha256'] = '0'*64
    elif changed == 'proof-bank': record['candidate_bank_sha256'] = '0'*64
    else: record['after']['base64'] = 'not-retainable'
    with pytest.raises(ValueError): REVIEW.verify(*data[:4], 'waist-target', '7', record)
    assert len(data[4]) == 2


def test_original_target_dimensions_and_file_digest_are_not_inferred_from_body_record(tmp_path, monkeypatch):
    data = render_fixture(tmp_path, monkeypatch)
    T.validate_target(data[3], data[1]['path'], (1024, 1024))
    with pytest.raises(ValueError): T.validate_target(data[3], data[1]['path'], (512, 512))
    (tmp_path / 'synthetic-waist-source-not-an-image.bin').write_bytes(b'different original')
    with pytest.raises(ValueError): T.validate_target(data[3], data[1]['path'], (1024, 1024))


def test_derived_target_uses_immutable_extent_not_physical_original_dimensions(tmp_path, monkeypatch):
    data = render_fixture(tmp_path, monkeypatch, derived=True)
    T.validate_target(data[3], data[1]['path'], (17, 29))
    record, _ = prepare(data)
    assert record['source_size'] == [1024, 1024]
    assert record['source_proof']['creative_source']['sha256'] == data[5]['asset_sha256']
    assert record['source_proof']['original_sha256'] != data[5]['asset_sha256']


@pytest.mark.parametrize('derived', [False, True])
@pytest.mark.parametrize('size', [(800, 1200), (1600, 900)])
def test_different_target_sizes_use_own_source_geometry_and_complete_frames(tmp_path, monkeypatch, derived, size):
    data = render_fixture(tmp_path, monkeypatch, derived=derived, source_size=size)
    record, public = prepare(data)
    assert record['source_size'] == list(size)
    assert record['before_output_size'] == record['after_output_size'] == list(size)
    assert all(call['pixels'].shape == (size[1], size[0], 3) for call in data[4])
    for side in ('before', 'after'):
        raw = base64.b64decode(public[side]['base64'], validate=True)
        assert sha256(raw).hexdigest() == record[side]['sha256']
        with Image.open(io.BytesIO(raw)) as image:
            image.load()
            assert image.size == (public[side]['width'], public[side]['height'])
            assert image.format == 'PNG' and image.mode == 'RGB'
    support = T.target(data[3])[3]
    assert all(key in support['data'] for key in S.WAIST_MARKERS)
    assert support['source']['width'] == size[0] and support['source']['height'] == size[1]


@pytest.mark.parametrize('fault', ['missing-link', 'different-person', 'pending-link'])
def test_current_own_face_consent_is_required_even_with_retained_four_markers(tmp_path, monkeypatch, fault):
    data = render_fixture(tmp_path, monkeypatch)
    people = data[0].people
    if fault == 'missing-link': people['links'] = []
    elif fault == 'different-person':
        people['persons']['another-person'] = {'anonymous': True}
        people['links'][0]['person_id'] = 'another-person'
    else: people['links'][0]['state'] = 'candidate'
    frozen = deepcopy(data[1])
    with pytest.raises(ValueError): prepare(data)
    assert data[4] == [] and data[1] == frozen


@pytest.mark.parametrize('fault', ['bad-hash', 'oversized', 'mime', 'pixels', 'wrong-aspect'])
def test_compact_proof_rejects_malformed_images_not_a_client_display_authorization(tmp_path, monkeypatch, fault):
    record, public = prepare(render_fixture(tmp_path, monkeypatch))
    if fault == 'bad-hash': record['after']['sha256'] = 'invalid-hash'
    elif fault == 'oversized': record['after']['width'] = 257
    elif fault == 'mime': record['after']['mime'] = 'image/jpeg'
    elif fault == 'pixels': record['after']['base64'] = public['after']['base64']
    else: record['after']['height'] = 1
    with pytest.raises(ValueError): REVIEW.checked(record)


def test_changed_manual_points_after_display_conflict_without_rebinding(tmp_path, monkeypatch):
    data = render_fixture(tmp_path, monkeypatch); record, _ = prepare(data)
    bank, row, item, support = T.target(data[3]); changed = deepcopy(support['data'])
    for key in S.WAIST_MARKERS[:2]: changed[key][1] += .001
    bank = B.set_support(bank, data[5], S.OP, S.SUPPORT_KIND, changed)
    bank = B.review(bank, data[5], operation_id=S.OP,
        points_sha256=row['record']['points_sha256'], visible_anchors=list(S.REQUIRED_ANCHORS),
        ownership_confirmed=True, support_sha256=B.operation(bank, data[5], S.OP)['support_sha256'])
    data[3][D.KEY] = P.pack(bank)
    frozen = deepcopy(data[3])
    with pytest.raises(ValueError): REVIEW.verify(*data[:4], 'waist-target', '7', record)
    assert data[3] == frozen and len(data[4]) == 2


def test_unrelated_existing_body_and_image_edits_are_in_both_complete_views(tmp_path, monkeypatch):
    data = render_fixture(tmp_path, monkeypatch)
    bank = B.set_recipe(D.bank(data[2]), data[5], SHOULDER.neutral(), operation_id=SHOULDER.OPERATION_ID)
    data[2][D.KEY] = P.pack(bank)
    data[3].clear(); data[3].update(deepcopy(data[2])); T.install(data[3], {'version': 1, 'amount': -.5})
    prepare(data)
    for call in data[4]:
        assert call['state']['unrelated_edit'] == 'retained'
        assert B.operation(D.bank(call['state']), data[5], SHOULDER.OPERATION_ID)['recipe'] == SHOULDER.neutral()
