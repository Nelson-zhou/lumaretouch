# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: body-reference ownership, consent and support contracts.

Synthetic landmarks/model identities/semantic arrays are not inference evidence.
Only the existing Rust manual-raster boundary is stubbed for geometry fixtures;
real structural/ownership/face-protection validators remain exercised when run.
No test collection, product import, build, inference or numerical acceptance ran
while authoring. Native brush fidelity and real-photo quality remain UNRUN.
"""
from copy import deepcopy
import json
from unittest.mock import patch

import numpy as np
import pytest

from lumaretouch_engine import people_state as P, people_associations as A
from lumaretouch_engine import body_pose_state as B, body_pose_evidence as E
from lumaretouch_engine import body_skin_semantics as SEM
from lumaretouch_engine import skin_colour_body_support as LEGACY
from lumaretouch_engine import skin_reference_match_support as FACE
from lumaretouch_engine import skin_reference_body_support as V
from test_skin_reference_match_support_unrun import fixture as face_fixture, add_face

BUDGET = 512 * 1024**2


def fixture(*, own_reference=False, shape=(256, 256)):
    state, assets, target, reference, ta, ra = face_fixture(shape=shape, source_size=512)
    state, person = A.create_person(state)
    state = A.set_link(state, target['face_instance_id'], person, 'confirmed', user_confirmed=True)
    source = {'sha256': target['asset_sha256'], 'width': 512, 'height': 512, 'orientation': E.ORIENTATION}
    points = [{'index': i, 'x': .5, 'y': .5, 'z': 0., 'visibility': 0., 'presence': 0.}
              for i in range(33)]
    record = E.create(source_frame=source, values=points, backend_version='synthetic-fixture',
        backend_code_sha256='d'*64, model_id='synthetic-fixture', model_sha256='e'*64,
        input_rgb_sha256='f'*64, input_dimensions=(256, 256))
    bank = B.add_run(B.empty(), {'source': source, 'records': [record], 'detector_limit': 4,
        'limit_reached': False, 'census_complete': False})
    bank = B.associate(bank, record['body_ref'], person, state, user_confirmed=True)
    ta['body_skin'] = np.ones(shape, np.float32)
    ta['body_skin_observation'] = {'contract': SEM.CONTRACT, 'source_sha256': source['sha256'],
        'semantic_model_sha256': 'c'*64, 'detector_model_sha256': 'b'*64,
        'producer_width': 128, 'producer_height': 128}
    review = {'operation_id': V.OP, 'body_ref': record['body_ref'],
        'points_sha256': record['points_sha256'], **{key: True for key in V.FLAGS},
        'recipe': {'version': 1, 'domain': 'source-normalized', 'objects': [{
            'id': 'reviewed-body', 'name': 'Synthetic reviewed body region', 'kind': 'brush',
            'enabled': True, 'operation': 'add', 'opacity': 1., 'feather': 0.,
            'points': [[.25, .82], [.25, .92]], 'axes': [[.08, 0.], [0., .05]]}]}}
    if own_reference:
        reference, ra = target, ta
    return state, assets, target, reference, bank, ta, ra, review


def retained(**kwargs):
    data = list(fixture(**kwargs))
    data[0], data[1] = V.retain(*data, confirmed=True)
    return tuple(data)


def raster(data, *, shape=None, manual=None, byte_budget=BUDGET, cancelled=None):
    state, assets, target, _, bank, ta, ra, _ = data
    shape = shape or ta['body_skin'].shape
    manual = np.full(shape, 255, np.uint8) if manual is None else manual
    with patch.object(V.M, 'raster', return_value=manual):
        return V.raster(state, assets, target, bank, ta, ra, shape,
                        byte_budget=byte_budget, cancelled=cancelled)


def test_body_storage_is_distinct_without_a_new_face_relation_or_scalar():
    data = fixture(); state, assets, target, reference, bank, ta, ra, review = data
    before = deepcopy(state); before_bank = deepcopy(bank); before_review = deepcopy(review)
    out, saved = V.retain(*data, confirmed=True)
    assert V.OP == 'lnx.skin_reference_body_match.v1' and V.OP != FACE.OP
    assert V.KIND == 'skin_reference_match_body_visibility'
    assert FACE.KIND not in out['faces'][target['face_instance_id']]['local_assets']
    assert out['overrides'] == [] and state == before and assets == {}
    assert bank == before_bank and review == before_review
    assert out['faces'][reference['face_instance_id']] == before['faces'][reference['face_instance_id']]
    assert V.retain(*data, confirmed=True) == (out, saved)
    assert V.retain(out, saved, *data[2:], confirmed=True) == (out, saved)
    record, key = V.resolve(out, saved, target, bank, ta, ra)
    assert V.content_digest(record) == key and V.check_record(record) == record
    assert json.loads(json.dumps(record, allow_nan=False)) == record
    assert record['row']['face_link']['face_instance_id'] == target['face_instance_id']
    assert record['row']['reference_face_ref'] == reference
    assert record['row']['body_link']['body_ref'] == review['body_ref']


def test_absence_needs_no_body_bank_analysis_or_render_support():
    state, _, target, _, _, _, _, _ = fixture()
    assert V.resolve(state, {}, target, None) is None
    assert V.raster(state, {}, target, None, None, None, None, byte_budget=0) == (None, {'enabled': False})


def test_own_face_is_a_valid_body_reference_and_every_face_remains_protected():
    data = retained(own_reference=True)
    state, assets, target, reference, bank, ta, ra, _ = data
    assert target == reference
    assert V.validate_active(state, assets, [target], bank, {target['face_instance_id']: ta}) == reference
    with patch.object(V.M, 'raster', return_value=np.full((256, 256), 255, np.uint8)):
        body, face, facts = V.geometry(state, assets, target, bank, ta, ra, (256, 256), byte_budget=BUDGET)
    assert not np.any((body > 0) & (face > 0))
    assert facts['target']['body_ref'] == data[7]['body_ref']
    assert facts['reference']['face_ref'] == target and facts['protected_measured_face_ovals'] == 1
    assert not body.flags.writeable and not face.flags.writeable


def test_foreign_selected_reference_is_not_mistaken_for_the_body_owner():
    state, assets, target, reference, bank, ta, ra, review = retained()
    record, _ = V.resolve(state, assets, target, bank, ta, ra)
    assert target != reference and record['row']['face_link']['face_instance_id'] != reference['face_instance_id']
    assert record['row']['body_link']['person_id'] == state['links'][0]['person_id']
    # Body-only owner need not have a face-skin sampling plane. Its verified
    # landmarks still protect the entire face; the selected reference has one.
    ta.pop('face_skin'); ta.pop('face_skin_observation')
    assert V.resolve(state, assets, target, bank, ta, ra) is not None
    assert raster((state, assets, target, reference, bank, ta, ra, review))[1]['enabled']


@pytest.mark.parametrize('confirmed', [False, None, 0, 1, 'yes'])
def test_operation_specific_explicit_confirmation_cannot_be_truthy(confirmed):
    with pytest.raises(ValueError, match='explicit'):
        V.retain(*fixture(), confirmed=confirmed)


@pytest.mark.parametrize('flag', V.FLAGS)
@pytest.mark.parametrize('value', [False, None, 1, 'yes'])
def test_every_exact_review_flag_is_required(flag, value):
    data = list(fixture()); data[-1][flag] = value
    with pytest.raises(ValueError): V.retain(*data, confirmed=True)


@pytest.mark.parametrize('operation', ['lnx.skin_colour.v1', 'lnx.skin_finish.v1',
    'lnx.body_skin_evenness.v1', 'lnx.body_face_match.v1', 'lnx.skin_reference_match.v1'])
def test_other_operation_review_never_grants_body_reference_consent(operation):
    data = list(fixture()); data[-1]['operation_id'] = operation
    with pytest.raises(ValueError, match='operation'): V.retain(*data, confirmed=True)


def test_existing_face_only_relation_does_not_create_body_consent():
    state, assets, target, reference, bank, ta, ra, review = fixture()
    state, assets = FACE.retain(state, assets, target, reference, ta, ra, confirmed=True)
    assert V.resolve(state, assets, target, bank) is None
    assert FACE.resolve(state, assets, target, ta, ra) is not None


def test_choices_need_target_manual_person_link_not_reference_or_nearest_body():
    state, assets, target, reference, bank, ta, ra, review = fixture()
    assert [choice['body_ref'] for choice in V.choices(state, bank, target, ta)] == [review['body_ref']]
    unlinked = B.unlink(bank, review['body_ref'])
    assert V.choices(state, unlinked, target, ta) == []
    with pytest.raises(ValueError, match='association'):
        V.retain(state, assets, target, reference, unlinked, ta, ra, review, confirmed=True)
    state, different_person = A.create_person(state)
    wrong = B.associate(bank, review['body_ref'], different_person, state, user_confirmed=True)
    with pytest.raises(ValueError, match='confirmed'):
        V.retain(state, assets, target, reference, wrong, ta, ra, review, confirmed=True)


@pytest.mark.parametrize('fault', ['foreign-source', 'disabled-reference', 'disabled-owner',
    'reference-evidence', 'body-as-face-ref', 'face-as-body-ref', 'stale-points', 'cropped-pose',
    'merged-only', 'missing-body-observation', 'body-model', 'body-detector', 'body-nan',
    'body-grid', 'missing-excluded', 'excluded-nan', 'reference-body-fallback'])
def test_reference_and_body_evidence_cannot_be_relabelled(fault):
    data = list(fixture()); state, _, target, reference, bank, ta, ra, review = data
    if fault == 'foreign-source': data[3] = {**reference, 'asset_sha256': '9'*64}
    elif fault == 'disabled-reference': state['faces'][reference['face_instance_id']]['enabled'] = False
    elif fault == 'disabled-owner': state['faces'][target['face_instance_id']]['enabled'] = False
    elif fault == 'reference-evidence': ra['evidence']['semantic_model_sha256'] = '9'*64
    elif fault == 'body-as-face-ref': data[2] = review['body_ref']
    elif fault == 'face-as-body-ref': review['body_ref'] = target
    elif fault == 'stale-points': review['points_sha256'] = '9'*64
    elif fault == 'cropped-pose': B.target(bank, review['body_ref'])['record']['input_dimensions'] = [128, 256]
    elif fault == 'merged-only': ta['skin'] = ta.pop('body_skin'); ta.pop('body_skin_observation')
    elif fault == 'missing-body-observation': ta.pop('body_skin_observation')
    elif fault == 'body-model': ta['body_skin_observation']['semantic_model_sha256'] = '9'*64
    elif fault == 'body-detector': ta['body_skin_observation']['detector_model_sha256'] = '9'*64
    elif fault == 'body-nan': ta['body_skin'][0, 0] = np.nan
    elif fault == 'body-grid': ta['body_skin'] = np.ones((128, 256), np.float32)
    elif fault == 'missing-excluded': ta.pop('excluded')
    elif fault == 'excluded-nan': ta['excluded'][0, 0] = np.nan
    else: ra['body_skin'] = ra.pop('face_skin'); ra.pop('face_skin_observation')
    with pytest.raises(ValueError): V.retain(*data, confirmed=True)


@pytest.mark.parametrize('fault', ['body-unlink', 'body-reanalyse', 'body-disabled', 'people-revision',
    'body-revision', 'body-model', 'face-confirmation', 'reference-disabled', 'reference-model',
    'body-producer-grid', 'reference-producer-grid'])
def test_live_resolution_refuses_stale_source_models_links_and_reference(fault):
    state, assets, target, reference, bank, ta, ra, review = retained()
    if fault == 'body-unlink': bank = B.unlink(bank, review['body_ref'])
    elif fault == 'body-reanalyse':
        bank = B.reanalyse(bank, review['body_ref'], deepcopy(B.target(bank, review['body_ref'])['record']), user_confirmed=True)
    elif fault == 'body-disabled': B.target(bank, review['body_ref'])['enabled'] = False
    elif fault == 'people-revision': state['association_revision'] += 1
    elif fault == 'body-revision': bank['association_revision'] += 1
    elif fault == 'body-model': B.target(bank, review['body_ref'])['record']['model_sha256'] = '9'*64
    elif fault == 'face-confirmation': state['links'][0]['confirmation_revision'] = 0
    elif fault == 'reference-disabled': state['faces'][reference['face_instance_id']]['enabled'] = False
    elif fault == 'reference-model': state['faces'][reference['face_instance_id']]['evidence']['semantic_model_sha256'] = '9'*64
    elif fault == 'body-producer-grid': ta['body_skin_observation']['producer_width'] = 64
    else: ra['face_skin_observation']['producer_width'] = 64
    with pytest.raises(ValueError): V.resolve(state, assets, target, bank, ta, ra)


@pytest.mark.parametrize('fault', ['full', 'semantic', 'prompted', 'intersect', 'only-subtract', 'zero', 'disabled'])
def test_manual_review_cannot_be_blanket_or_semantic_alias(fault):
    data = list(fixture()); obj = data[-1]['recipe']['objects'][0]
    if fault in ('full', 'semantic', 'prompted'): obj['kind'] = fault
    elif fault == 'intersect': obj['operation'] = 'intersect'
    elif fault == 'only-subtract': obj['operation'] = 'subtract'
    elif fault == 'zero': obj['opacity'] = 0
    else: obj['enabled'] = False
    with pytest.raises(ValueError): V.retain(*data, confirmed=True)


def test_raster_protects_all_faces_complete_reference_oval_and_known_occluders():
    data = list(retained()); state, _, target, reference, _, ta, _, _ = data
    other = P.new_face(target['asset_sha256'], [.45, .81, .55, .91], {
        **ta['evidence'], 'status': 'unresolved', 'landmark_digest': None})
    other['enabled'] = False; state['faces'][other['face_instance_id']] = other
    state['faces'][reference['face_instance_id']]['box'] = [.70, .40, .71, .41]
    ta['body_skin'][230, 25] = .4; ta['body_skin'][:, :4] = 0
    ta['excluded'][230, 35] = .2
    body, facts = raster(tuple(data))
    assert body.dtype == np.float32 and not body.flags.writeable
    assert body[230, 25] == np.float32(.4) and body[230, 35] == 0
    assert not np.any(body[:, :4]) and body[218, 128] == 0
    assert body[110, 205] == 0  # Measured reference oval, outside its narrow box.
    assert body[115, 64] == 0   # Owner's complete face, not sampled face-skin holes.
    assert facts['protected_face_boxes'] == 3 and facts['protected_measured_face_ovals'] == 2
    assert facts['runtime_quality_accepted'] is False


def test_geometry_returns_independent_source_windows_and_no_positive_overlap():
    state, assets, target, _, bank, ta, ra, _ = retained()
    with patch.object(V.M, 'raster', return_value=np.full((256, 256), 255, np.uint8)):
        body, reference, facts = V.geometry(state, assets, target, bank, ta, ra,
            (256, 256), byte_budget=BUDGET)
    assert not np.any((body > 0) & (reference > 0))
    for mask, name in ((body, 'target'), (reference, 'reference')):
        y, x, h, w = facts[name]['source_window']
        assert np.any(mask[y:y+h, x:x+w] > 0) and not mask.flags.writeable
    assert facts['reference']['face_skin_observation']['producer_width'] == 128


def test_semantic_empty_and_bad_native_raster_fail_instead_of_broadening():
    data = list(retained()); data[5]['body_skin'][:] = 0
    with pytest.raises(ValueError, match='no admitted'): raster(tuple(data))
    with pytest.raises(ValueError, match='Rust uint8'):
        raster(retained(), manual=np.ones((256, 256), np.float32))


def _historical_competitor(data, *, legacy=False):
    state, assets, target, reference, bank, ta, ra, review = data
    other = deepcopy(state['faces'][reference['face_instance_id']]); other['enabled'] = False
    other['face_instance_id'] = 'historical-competitor'; other_ref = P.face_ref(other)
    if legacy:
        old_review = {key: deepcopy(value) for key, value in review.items()
                      if key not in ('operation_id', 'reference_unchanged')}
        _, previous = LEGACY.retain(state, {}, target, bank, ta, old_review)
        record = deepcopy(next(iter(previous.values()))); kind = LEGACY.KIND
    else:
        record, _ = V.resolve(state, assets, target, bank); kind = V.KIND
        record = deepcopy(record)
    record['face_ref'] = other_ref
    record['row']['face_evidence'] = deepcopy(other['evidence'])
    record['row']['face_link']['face_instance_id'] = other_ref['face_instance_id']
    checked = LEGACY.check_record(record) if legacy else V.check_record(record)
    key = V.content_digest(checked); assets[key] = checked
    other['local_assets'] = {kind: {'owner': other_ref, 'kind': kind, 'content_sha256': key}}
    state['faces'][other_ref['face_instance_id']] = other
    return state, assets, target, reference, bank, ta, ra, review


@pytest.mark.parametrize('legacy', [False, True])
def test_disabled_foreign_attached_reviews_reserve_ownership_across_families(legacy):
    data = _historical_competitor(retained(), legacy=legacy)
    with pytest.raises(ValueError, match='overlap'): raster(data)


def test_source_normalized_vectors_are_rasterized_on_current_grid_not_enlarged():
    data = list(retained()); shape = (128, 128)
    for index in (5, 6):
        for name in ('body_skin', 'face_skin', 'excluded'):
            if name in data[index]: data[index][name] = data[index][name][::2, ::2].copy()
    with patch.object(V.M, 'raster', return_value=np.full(shape, 255, np.uint8)) as native:
        body, facts = V.raster(data[0], data[1], data[2], data[4], data[5], data[6],
                              shape, byte_budget=BUDGET)
    assert body.shape == shape and native.call_args.args[1] == shape
    assert facts['semantic_observation']['producer_width'] == 128
    with pytest.raises(ValueError): raster(tuple(data), shape=(128, 256))


def test_memory_work_and_cancellation_refuse_before_manual_worker_allocation():
    data = retained(); state, assets, target, _, bank, ta, ra, _ = data
    with patch.object(V.M, 'raster') as native:
        with pytest.raises(ValueError, match='memory budget'):
            V.raster(state, assets, target, bank, ta, ra, (256, 256), byte_budget=0)
        with pytest.raises(InterruptedError):
            V.raster(state, assets, target, bank, ta, ra, (256, 256), byte_budget=BUDGET, cancelled=lambda: True)
        native.assert_not_called()
    with patch.object(V.M, 'validate_budget', return_value={'work': V.M.MAX_WORK + 1}), \
            patch.object(V.M, 'raster') as native:
        with pytest.raises(ValueError, match='aggregate work'):
            V.raster(state, assets, target, bank, ta, ra, (256, 256), byte_budget=BUDGET)
        native.assert_not_called()


def test_active_list_is_exact_and_can_be_metadata_only():
    state, assets, target, reference, bank, ta, ra, _ = retained()
    assert V.validate_active(state, assets, [target], bank) == reference
    assert V.validate_active(state, assets, [], None) is None
    with pytest.raises(ValueError, match='duplicates'):
        V.validate_active(state, assets, [target, target], bank)
    with pytest.raises(ValueError, match='unavailable'):
        V.validate_active(state, assets, [target], bank, {})
    with pytest.raises(ValueError, match='both exact'):
        V.resolve(state, assets, target, bank, ta)


def test_complete_active_body_set_cannot_silently_use_different_references():
    state, assets, target, reference, bank, ta, ra, review = fixture()
    state, second_person = A.create_person(state)
    state = A.set_link(state, reference['face_instance_id'], second_person, 'confirmed', user_confirmed=True)
    second_body = deepcopy(B.target(bank, review['body_ref'])['record'])
    second_body['body_ref']['body_instance_id'] = 'body:second-synthetic'
    bank = B.add_run(bank, {'source': second_body['source'], 'records': [second_body],
        'detector_limit': 4, 'limit_reached': False, 'census_complete': False})
    # Refresh both explicit body associations against the final face/person
    # revision before either operation review is created.
    bank = B.associate(bank, review['body_ref'], state['links'][0]['person_id'], state, user_confirmed=True)
    bank = B.associate(bank, second_body['body_ref'], second_person, state, user_confirmed=True)
    ra['body_skin'] = ta['body_skin'].copy()
    ra['body_skin_observation'] = deepcopy(ta['body_skin_observation'])
    second_review = {**deepcopy(review), 'body_ref': second_body['body_ref']}
    state, assets = V.retain(state, assets, target, reference, bank, ta, ra, review, confirmed=True)
    state, assets = V.retain(state, assets, reference, target, bank, ra, ta, second_review, confirmed=True)
    with pytest.raises(ValueError, match='agree on one'):
        V.validate_active(state, assets, [target, reference], bank)
    # Choosing the reference owner's own face is valid for that owner's body.
    state, assets = V.retain(state, assets, reference, reference, bank, ra, ra, second_review, confirmed=True)
    assert V.validate_active(state, assets, [target, reference], bank) == reference


def test_detach_and_history_do_not_depend_on_todays_live_body_associations():
    state, assets, target, _, bank, ta, ra, review = retained(); before = deepcopy(assets)
    history = {'people_graph': deepcopy(state), 'people_support_assets': assets}
    bank = B.unlink(bank, review['body_ref'])
    with pytest.raises(ValueError): V.resolve(state, assets, target, bank, ta, ra)
    V.validate_project(history)
    state['faces'][target['face_instance_id']]['enabled'] = False
    detached = V.detach(state, target)
    assert V.KIND not in detached['faces'][target['face_instance_id']]['local_assets']
    assert V.detach(detached, target) == detached and assets == before
    bad = deepcopy(history)
    bad['people_graph']['faces'][target['face_instance_id']]['evidence']['semantic_model_sha256'] = '9'*64
    with pytest.raises(ValueError, match='Historical'): V.validate_project(bad)


def test_private_bank_shadowing_never_searches_outer_or_sibling_assets():
    state, assets, *_ = retained()
    V.validate_project({'people_support_assets': {}, 'documents': [
        {'people_graph': state, 'people_support_assets': assets}]})
    with pytest.raises(ValueError):
        V.validate_project({'people_support_assets': assets, 'private': {
            'people_graph': state, 'people_support_assets': {}}})
    with pytest.raises(ValueError):
        V.validate_project({'people_support_assets': {}, 'documents': [
            {'people_graph': state, 'people_support_assets': assets}, {'people_graph': state}]})


def test_selected_reference_change_creates_new_immutable_body_relation_only():
    state, assets, target, reference, bank, ta, ra, review = retained()
    before = deepcopy(assets)
    new_reference, new_analysis = add_face(state, 'new-reference', center=(.74, .45), span=(.10, .20))
    out, saved = V.retain(state, assets, target, new_reference, bank, ta, new_analysis, review, confirmed=True)
    assert len(saved) == len(before) + 1 and all(saved[key] == value for key, value in before.items())
    record, _ = V.resolve(out, saved, target, bank, ta, new_analysis)
    assert record['row']['reference_face_ref'] == new_reference != reference
    assert FACE.KIND not in out['faces'][target['face_instance_id']]['local_assets']
