"""AUTHORED / UNRUN body-skin ownership and manual support fixtures.

All arrays, pose observations and model digests below are synthetic contract
fixtures. No detector, native rasterizer, photo-quality test or product runtime
was invoked while authoring. Positive numerical fixtures stub only the manual
raster boundary; they are not native execution or visual acceptance evidence.
"""
from copy import deepcopy
from unittest.mock import patch
import numpy as np
import pytest
from lumaretouch_engine import people_state as S, people_associations as A
from lumaretouch_engine import people_binding as F
from lumaretouch_engine import body_pose_state as B, body_pose_evidence as E
from lumaretouch_engine import body_skin_semantics as SEM
from lumaretouch_engine import skin_colour_body_support as V


def fixture():
    source = {'sha256': 'a'*64, 'width': 64, 'height': 64, 'orientation': E.ORIENTATION}
    landmarks = np.full((478, 3), .25, np.float32)
    evidence = {'backend': 'mediapipe', 'detector_model_sha256': 'b'*64,
        'semantic_model_sha256': 'c'*64, 'landmark_digest': F.landmark_digest(landmarks),
        'status': 'verified', 'source_width': 64, 'source_height': 64, 'orientation': E.ORIENTATION}
    state = S.empty(); face = S.new_face(source['sha256'], [.1, .1, .3, .3], evidence)
    state['faces'][face['face_instance_id']] = face
    state, person = A.create_person(state)
    state = A.set_link(state, face['face_instance_id'], person, 'confirmed', user_confirmed=True)
    # Synthetic pose coordinates/zero confidence intentionally make no model
    # quality claim. Body-skin manual visibility does not borrow shape reviews.
    points = [{'index': i, 'x': .5, 'y': .5, 'z': 0., 'visibility': 0., 'presence': 0.}
              for i in range(33)]
    record = E.create(source_frame=source, values=points, backend_version='fixture-only',
        backend_code_sha256='d'*64, model_id='synthetic-unit-fixture', model_sha256='e'*64,
        input_rgb_sha256='f'*64, input_dimensions=(64, 64))
    bank = B.add_run(B.empty(), {'source': source, 'records': [record],
        'detector_limit': 4, 'limit_reached': False, 'census_complete': False})
    bank = B.associate(bank, record['body_ref'], person, state, user_confirmed=True)
    ref = S.face_ref(face)
    analysis = {'face_ref': ref, 'evidence': evidence, 'landmarks': landmarks,
        'body_skin': np.ones((64, 64), np.float32),
        'body_skin_observation': {'contract': SEM.CONTRACT, 'source_sha256': source['sha256'],
            'semantic_model_sha256': 'c'*64, 'detector_model_sha256': 'b'*64,
            'producer_width': 64, 'producer_height': 64}}
    review = {'body_ref': record['body_ref'], 'points_sha256': record['points_sha256'],
        'visible': True, 'unoccluded': True, 'ownership_confirmed': True,
        'recipe': {'version': 1, 'domain': 'source-normalized', 'objects': [{
            'id': 'manual-body', 'name': 'Synthetic visible-region fixture', 'kind': 'brush',
            'enabled': True, 'operation': 'add', 'opacity': 1., 'feather': 0.,
            'points': [[.5, .5], [.5, .8]], 'axes': [[.1, 0.], [0., .1]]}]}}
    return state, {}, ref, bank, analysis, review


def retained():
    state, assets, ref, bank, analysis, review = fixture()
    state, assets = V.retain(state, assets, ref, bank, analysis, review)
    return state, assets, ref, bank, analysis, review


def raster_fixture(state, assets, ref, bank, analysis, manual=None, shape=(64, 64)):
    manual = np.full(shape, 255, np.uint8) if manual is None else manual
    with patch.object(V.M, 'raster', return_value=manual):
        return V.raster(state, assets, ref, bank, analysis, shape, byte_budget=128*1024*1024)


def test_absence_is_face_only_without_any_body_bank_or_analysis():
    state, _, ref, _, _, _ = fixture()
    assert V.resolve(state, {}, ref, None, None) is None
    assert V.raster(state, {}, ref, None, None, (64, 64)) == (None, {'enabled': False})


def test_retain_is_pure_deterministic_and_does_not_change_scalar_overrides():
    state, assets, ref, bank, analysis, review = fixture()
    before = deepcopy(state); before_bank = deepcopy(bank); before_review = deepcopy(review)
    one, a = V.retain(state, assets, ref, bank, analysis, review)
    two, b = V.retain(state, assets, ref, bank, analysis, review)
    assert one == two and a == b and state == before and assets == {}
    assert bank == before_bank and review == before_review
    assert one['overrides'] == state['overrides'] and one['revision'] == state['revision'] + 1
    assert V.retain(one, a, ref, bank, analysis, review) == (one, a)
    record, key = V.resolve(one, a, ref, bank, analysis)
    assert V.check_record(record) == record and V.content_digest(record) == key
    assert record['row']['body_record_sha256'] == E.content_digest(B.target(bank, review['body_ref'])['record'])


def test_choices_need_confirmed_same_person_not_nearest_pose():
    state, assets, ref, bank, analysis, review = fixture()
    assert [row['body_ref'] for row in V.choices(state, bank, ref, analysis)] == [review['body_ref']]
    bank = B.unlink(bank, review['body_ref'])
    assert V.choices(state, bank, ref, analysis) == []
    with pytest.raises(ValueError, match='association'):
        V.retain(state, assets, ref, bank, analysis, review)


@pytest.mark.parametrize('flag', V.FLAGS)
def test_each_visibility_and_ownership_confirmation_is_required(flag):
    state, assets, ref, bank, analysis, review = fixture(); review[flag] = False
    with pytest.raises(ValueError):
        V.retain(state, assets, ref, bank, analysis, review)


@pytest.mark.parametrize('fault', ['merged-only', 'missing-observation', 'wrong-model', 'wrong-detector',
    'wrong-source', 'nan', 'wrong-face', 'wrong-points', 'wrong-dimensions'])
def test_missing_or_relabelled_evidence_never_becomes_body_skin(fault):
    state, assets, ref, bank, analysis, review = fixture()
    if fault == 'merged-only':
        analysis['skin'] = analysis.pop('body_skin'); analysis.pop('body_skin_observation')
    elif fault == 'missing-observation': analysis.pop('body_skin_observation')
    elif fault == 'wrong-model': analysis['body_skin_observation']['semantic_model_sha256'] = '9'*64
    elif fault == 'wrong-detector': analysis['body_skin_observation']['detector_model_sha256'] = '9'*64
    elif fault == 'wrong-source': analysis['body_skin_observation']['source_sha256'] = '9'*64
    elif fault == 'nan': analysis['body_skin'][2, 2] = np.nan
    elif fault == 'wrong-face': analysis['face_ref'] = {**ref, 'analysis_revision': 1}
    elif fault == 'wrong-points': review['points_sha256'] = '9'*64
    else: B.target(bank, review['body_ref'])['record']['source']['width'] = 80
    with pytest.raises(ValueError):
        V.retain(state, assets, ref, bank, analysis, review)


@pytest.mark.parametrize('mutation', ['body-unlink', 'body-reanalyse', 'body-disabled',
    'people-revision', 'body-revision', 'face-link-confirmation', 'body-model', 'observation-grid'])
def test_active_descriptor_refuses_stale_ownership_and_model_evidence(mutation):
    state, assets, ref, bank, analysis, review = retained()
    if mutation == 'body-unlink': bank = B.unlink(bank, review['body_ref'])
    elif mutation == 'body-reanalyse':
        measured = deepcopy(B.target(bank, review['body_ref'])['record'])
        bank = B.reanalyse(bank, review['body_ref'], measured, user_confirmed=True)
    elif mutation == 'body-disabled': B.target(bank, review['body_ref'])['enabled'] = False
    elif mutation == 'people-revision': state['association_revision'] += 1
    elif mutation == 'body-revision': bank['association_revision'] += 1
    elif mutation == 'face-link-confirmation':
        state['links'][0]['confirmation_revision'] = 0
    elif mutation == 'body-model': B.target(bank, review['body_ref'])['record']['model_sha256'] = '9'*64
    else: analysis['body_skin_observation']['producer_width'] = 32
    with pytest.raises(ValueError): V.resolve(state, assets, ref, bank, analysis)


def test_regular_scalar_and_geometry_edits_do_not_rebind_or_invalidate_review():
    state, assets, ref, bank, analysis, review = retained()
    state = S.set_override(state, 'face', ref['face_instance_id'], V.OPERATION, '/temperature', .2)
    bank['revision'] += 1  # Ordinary body recipe edits do not change association/evidence.
    assert V.resolve(state, assets, ref, bank, analysis) is not None


@pytest.mark.parametrize('bad', ['full', 'semantic', 'prompted', 'only-subtract', 'no-add', 'intersect'])
def test_review_admits_only_explicit_manual_positive_regions(bad):
    state, assets, ref, bank, analysis, review = fixture(); obj = review['recipe']['objects'][0]
    if bad in ('full', 'semantic', 'prompted'): obj['kind'] = bad
    elif bad == 'only-subtract': obj['operation'] = 'subtract'
    elif bad == 'no-add': obj['opacity'] = 0
    else: obj['operation'] = 'intersect'
    with pytest.raises(ValueError): V.retain(state, assets, ref, bank, analysis, review)


def test_raster_intersects_semantics_and_vetoes_all_retained_faces():
    state, assets, ref, bank, analysis, _ = retained()
    other = S.new_face(ref['asset_sha256'], [.6, .6, .8, .8], {
        **analysis['evidence'], 'status': 'unresolved', 'landmark_digest': None})
    other['enabled'] = False; state['faces'][other['face_instance_id']] = other
    analysis['body_skin'][:, :4] = 0; analysis['body_skin'][40, 30] = .4
    coverage, facts = raster_fixture(state, assets, ref, bank, analysis)
    assert not coverage.flags.writeable and coverage.dtype == np.float32
    assert coverage[40, 30] == np.float32(.4) and not np.any(coverage[:, :4])
    assert not np.any(coverage[5:21, 5:21]) and not np.any(coverage[37:53, 37:53])
    assert facts['enabled'] is True and facts['protected_face_boxes'] == 2
    assert facts['scope'] == 'reviewed-body-skin-not-instance-segmentation'
    assert facts['runtime_quality_accepted'] is False


def test_empty_semantic_intersection_refuses_not_fake_success():
    state, assets, ref, bank, analysis, _ = retained(); analysis['body_skin'][:] = 0
    with pytest.raises(ValueError, match='no admitted'):
        raster_fixture(state, assets, ref, bank, analysis)


def test_competing_attached_review_refuses_even_when_other_face_is_disabled():
    state, assets, ref, bank, analysis, _ = retained()
    original = next(iter(assets.values())); other_record = deepcopy(original)
    other_face = S.new_face(ref['asset_sha256'], [.7, .05, .9, .2], analysis['evidence'])
    other_face['enabled'] = False; other_ref = S.face_ref(other_face)
    other_record['face_ref'] = other_ref
    other_record['row']['face_link']['face_instance_id'] = other_ref['face_instance_id']
    # Historical competitor remains a conservative ownership reservation; live
    # resolution would refuse its missing body link rather than fabricate one.
    key = V.content_digest(V.check_record(other_record)); assets[key] = other_record
    other_face['local_assets'][V.KIND] = {'owner': other_ref, 'kind': V.KIND, 'content_sha256': key}
    state['faces'][other_ref['face_instance_id']] = other_face
    with pytest.raises(ValueError, match='overlap'):
        raster_fixture(state, assets, ref, bank, analysis)


def test_raster_requires_current_whole_source_shape_without_enlarging_proxy():
    state, assets, ref, bank, analysis, _ = retained()
    with patch.object(V.M, 'raster') as native:
        with pytest.raises(ValueError):
            V.raster(state, assets, ref, bank, analysis, (64, 32), byte_budget=128*1024*1024)
        native.assert_not_called()
    proxy = deepcopy(analysis); proxy['body_skin'] = np.ones((32, 32), np.float32)
    with patch.object(V.M, 'raster', return_value=np.full((32, 32), 255, np.uint8)) as native:
        coverage, facts = V.raster(state, assets, ref, bank, proxy, (32, 32), byte_budget=128*1024*1024)
        assert coverage.shape == (32, 32) and native.call_args.args[1] == (32, 32)
        assert facts['semantic_observation']['producer_width'] == 64


def test_memory_and_work_refuse_before_native_raster_allocation():
    state, assets, ref, bank, analysis, _ = retained()
    with patch.object(V.M, 'raster') as native:
        with pytest.raises(ValueError, match='memory budget'):
            V.raster(state, assets, ref, bank, analysis, (64, 64), byte_budget=0)
        native.assert_not_called()
    with patch.object(V.M, 'validate_budget', return_value={'work': V.M.MAX_WORK + 1}), \
            patch.object(V.M, 'raster') as native:
        with pytest.raises(ValueError, match='aggregate work'):
            V.raster(state, assets, ref, bank, analysis, (64, 64), byte_budget=128*1024*1024)
        native.assert_not_called()


def test_detach_remains_available_with_stale_analysis_preserving_immutable_assets():
    state, assets, ref, bank, analysis, _ = retained(); before = deepcopy(assets)
    state['faces'][ref['face_instance_id']]['enabled'] = False
    detached = V.detach(state, ref)
    assert V.KIND not in detached['faces'][ref['face_instance_id']]['local_assets']
    assert V.KIND in state['faces'][ref['face_instance_id']]['local_assets'] and assets == before
    assert V.detach(detached, ref) == detached


def test_historical_validation_is_structural_not_current_link_resolution():
    state, assets, ref, bank, analysis, review = retained()
    history = {'people_graph': deepcopy(state), 'people_support_assets': deepcopy(assets)}
    bank = B.unlink(bank, review['body_ref'])
    with pytest.raises(ValueError): V.resolve(state, assets, ref, bank, analysis)
    V.validate_project(history)
    bad = deepcopy(history); key = next(iter(bad['people_support_assets']))
    bad['people_support_assets'][key]['row']['review']['recipe']['objects'][0]['opacity'] = .5
    with pytest.raises(ValueError): V.validate_project(bad)


def test_observation_json_checker_needs_no_manufactured_array():
    _, _, ref, _, analysis, _ = fixture()
    assert SEM.check_observation(analysis['body_skin_observation'], ref, analysis['evidence']) == analysis['body_skin_observation']
    bad = deepcopy(analysis['body_skin_observation']); bad['detector_model_sha256'] = '9'*64
    with pytest.raises(ValueError): SEM.check_observation(bad, ref, analysis['evidence'])


def test_nested_private_support_banks_shadow_enclosing_owner_without_leaking_to_siblings():
    state, assets, ref, _, _, _ = retained()
    private = {'people_graph': state, 'people_support_assets': assets}
    project = {'people_support_assets': {}, 'documents': [{'people_context': private}]}
    V.validate_project(project)
    # Root has the right bytes, but an explicitly empty private store must not
    # inherit them. Private-owner isolation is not a search for any matching hash.
    invalid = {'people_support_assets': assets, 'people_context': {
        'people_graph': state, 'people_support_assets': {}}}
    with pytest.raises(ValueError, match='asset'):
        V.validate_project(invalid)
    sibling = deepcopy(project)
    sibling['documents'].append({'people_graph': state})
    with pytest.raises(ValueError, match='asset'):
        V.validate_project(sibling)


def test_historical_face_evidence_cannot_be_relabelled_under_same_descriptor():
    state, assets, ref, _, _, _ = retained()
    state['faces'][ref['face_instance_id']]['evidence']['semantic_model_sha256'] = '9'*64
    with pytest.raises(ValueError, match='Historical'):
        V.validate_project({'people_graph': state, 'people_support_assets': assets})


def test_cropped_pose_input_is_not_a_whole_source_body_observation():
    state, assets, ref, bank, analysis, review = fixture()
    B.target(bank, review['body_ref'])['record']['input_dimensions'] = [32, 64]
    with pytest.raises(ValueError, match='aspect'):
        V.retain(state, assets, ref, bank, analysis, review)
