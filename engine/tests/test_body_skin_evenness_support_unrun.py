# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN own-body chromatic-evenness support contracts.

No product imports, test collection/execution, native calls, builds, inference or
downloads ran during authoring. Synthetic pixels, pose/model digests and manual
regions are transport/ownership fixtures, not authentic measurements or image
acceptance. Actual review, BodyRef, association, semantic, geometry, exclusion,
budget and historical validators are used. Only manual raster and native
available/prepare boundaries are doubled; these do not test Rust numerical
quality, guided neighborhoods or photographic/learned-AI parity.
"""
from copy import deepcopy
from unittest.mock import patch

import numpy as np
import pytest

from lumaretouch_engine import people_state as P, people_associations as A
from lumaretouch_engine import people_binding as F
from lumaretouch_engine import body_pose_state as B, body_pose_evidence as E
from lumaretouch_engine import body_skin_semantics as SEM
from lumaretouch_engine import skin_colour_body_support as SUPPORT
from lumaretouch_engine import body_skin_evenness_state as S
from lumaretouch_engine import body_skin_evenness_project as PROJECT
from lumaretouch_engine import body_skin_evenness_layer as L
from lumaretouch_engine import skin_evenness_native as N

ACTIVE = {'version': 1, 'amount': .6}
BUDGET = 512*1024**2
OPTIONS = {'family': 'body_skin_evenness', 'operation_id': S.OP}


def fixture(size=256, *, source_size=1024, producer_size=64, attach=True, family='body_skin_evenness'):
    """A genuine schema fixture, never a claim of real detector evidence."""
    frame = {'sha256': 'a'*64, 'width': source_size, 'height': source_size,
             'orientation': E.ORIENTATION}
    landmarks = np.full((478, 3), .2, np.float32)
    evidence = {'backend': 'mediapipe', 'detector_model_sha256': 'b'*64,
        'semantic_model_sha256': 'c'*64, 'landmark_digest': F.landmark_digest(landmarks),
        'status': 'verified', 'source_width': source_size, 'source_height': source_size,
        'orientation': E.ORIENTATION}
    state = P.empty(); face = P.new_face(frame['sha256'], [.1, .1, .3, .3], evidence)
    state['faces'][face['face_instance_id']] = face
    state, person = A.create_person(state)
    state = A.set_link(state, face['face_instance_id'], person, 'confirmed', user_confirmed=True)
    points = [{'index': i, 'x': .5, 'y': .5, 'z': 0., 'visibility': .99, 'presence': .99}
              for i in range(33)]
    for i, x, y in ((11, .3, .3), (12, .7, .3), (23, .35, .7), (24, .65, .7)):
        points[i].update(x=x, y=y)
    record = E.create(source_frame=frame, values=points, backend_version='fixture-only',
        backend_code_sha256='d'*64, model_id='synthetic-unit-fixture', model_sha256='e'*64,
        input_rgb_sha256='f'*64, input_dimensions=(producer_size, producer_size))
    bank = B.add_run(B.empty(), {'source': frame, 'records': [record],
        'detector_limit': 4, 'limit_reached': False, 'census_complete': False})
    bank = B.associate(bank, record['body_ref'], person, state, user_confirmed=True)
    ref = P.face_ref(face)
    analysis = {'face_ref': ref, 'evidence': evidence, 'landmarks': landmarks,
        'excluded': np.zeros((size, size), np.float32),
        'body_skin': np.ones((size, size), np.float32),
        'body_skin_observation': {'contract': SEM.CONTRACT, 'source_sha256': frame['sha256'],
            'semantic_model_sha256': 'c'*64, 'detector_model_sha256': 'b'*64,
            'producer_width': producer_size, 'producer_height': producer_size}}
    review = {'body_ref': record['body_ref'], 'points_sha256': record['points_sha256'],
        'visible': True, 'unoccluded': True, 'ownership_confirmed': True,
        'recipe': {'version': 1, 'domain': 'source-normalized', 'objects': [{
            'id': 'manual-body', 'name': 'Synthetic reviewed body-region fixture', 'kind': 'brush',
            'enabled': True, 'operation': 'add', 'opacity': 1., 'feather': 0.,
            'points': [[.4, .4], [.6, .8]], 'axes': [[.1, 0.], [0., .1]]}]}}
    assets = {}
    if attach:
        state, assets = SUPPORT.retain(state, assets, ref, bank, analysis, review, family=family)
    xx = np.linspace(0., 1., size, dtype=np.float32)[None, :, None]
    source = np.broadcast_to(np.array([.55, .40, .30], np.float32)+xx*.04,
                             (size, size, 3)).copy()
    manual = np.zeros((size, size), np.uint8)
    manual[int(.4*size):int(.8*size), int(.3*size):int(.7*size)] = 255
    return state, assets, ref, bank, analysis, review, source, manual


def native_prepare_double(calls):
    """Bounded visible routing marks only, not a robust-reference solver."""
    def prepare(source, coverage, amount, *, radius, cancelled):
        assert not source.flags.writeable and not coverage.flags.writeable
        assert source.dtype == coverage.dtype == np.float32
        assert source.shape == (*coverage.shape, 3)
        assert type(radius) is int and 4 <= radius <= 256
        if cancelled():
            raise InterruptedError('synthetic preparation cancellation')
        calls.append({'source': source.copy(), 'coverage': coverage.copy(),
                      'amount': amount, 'radius': radius})
        shift = coverage[..., None]*np.float32(amount)*np.array([.03, -.02], np.float32)
        # These fixtures use ordinary midtone skin or exact black/white. The
        # native reliability boundary itself remains untested by this double.
        shift[np.any(source <= .01, axis=2) | np.any(source >= .995, axis=2)] = 0
        shift.setflags(write=False)
        return shift
    return prepare


def prepare(data, *, recipe=ACTIVE, byte_budget=BUDGET, cancelled=None, native=None):
    state, assets, ref, bank, analysis, _, source, manual = data
    calls = []
    with patch.object(SUPPORT.M, 'raster', return_value=manual), \
            patch.object(N, 'available', return_value=True), \
            patch.object(N, 'prepare', side_effect=native or native_prepare_double(calls)):
        records = L.prepare(ref, analysis, source, recipe, people_state=state,
            body_assets=assets, body_bank=bank, byte_budget=byte_budget, cancelled=cancelled)
    return records, calls


def expand(record, field, shape):
    result = np.zeros((*shape, *field.shape[2:]), field.dtype)
    y, x, h, w = record.window
    result[y:y+h, x:x+w] = field
    return result


def test_exact_separate_operation_and_portable_scalar_only():
    assert S.OP == 'lnx.body_skin_evenness.v1'
    assert S.CONTROL_ID == 'LNX-REF-PC-32465-C-d5ac2d4606'
    assert S.VERSION == 1 and S.KEYS == ('amount',)
    assert S.check(None) == S.neutral() == {'version': 1, 'amount': 0.}
    assert not S.active(None) and S.active(ACTIVE)
    assert S.check({'version': 1, 'amount': 1}) == {'version': 1, 'amount': 1.}


@pytest.mark.parametrize('value', [True, False, '0.5', -.01, 1.01, float('nan'), float('inf'), 10**10000])
def test_strict_scalar_rejects_coercion_nonfinite_and_out_of_range(value):
    with pytest.raises(ValueError):
        S.check({'version': 1, 'amount': value})


@pytest.mark.parametrize('extra', ['source', 'body_ref', 'face_ref', 'reference_rgb', 'coverage',
                                  'target_face', 'chroma_shift', 'body_to_face_matching'])
def test_recipes_and_project_leaves_cannot_smuggle_source_or_donor(extra):
    with pytest.raises(ValueError):
        S.check({**ACTIVE, extra: None})
    with pytest.raises(ValueError):
        PROJECT.validate_leaf('/'+extra, None)


@pytest.mark.parametrize('recipe', [{}, {'version': True, 'amount': .5},
    {'version': 1., 'amount': .5}, {'version': 2, 'amount': .5}, {'amount': .5}])
def test_version_and_recipe_shape_are_strict(recipe):
    with pytest.raises(ValueError):
        S.check(recipe)


def test_neutral_needs_no_source_review_body_or_native():
    with patch.object(SUPPORT, 'resolve', side_effect=AssertionError('neutral resolved review')), \
            patch.object(N, 'available', side_effect=AssertionError('neutral loaded native')):
        assert L.prepare(None, None, None, None, people_state=None, body_assets=None,
                         body_bank=None, byte_budget=0) == []


@pytest.mark.parametrize('family', [None, 'skin_colour', 'skin_finish'])
def test_active_requires_its_own_review_not_another_familys_attachment(family):
    data = fixture(attach=family is not None, family=family or L.FAMILY)
    with patch.object(N, 'prepare') as native:
        with pytest.raises(ValueError, match='own reviewed'):
            state, assets, ref, bank, analysis, _, source, _ = data
            L.prepare(ref, analysis, source, ACTIVE, people_state=state,
                      body_assets=assets, body_bank=bank, byte_budget=BUDGET)
        native.assert_not_called()


def test_entire_disconnected_support_uses_one_own_body_reference_and_real_halo():
    data = fixture(); manual = data[-1]; manual[:] = 0
    manual[100:125, 80:110] = 255
    manual[185:215, 180:210] = 255
    records, calls = prepare(data)
    assert len(records) == len(calls) == 1
    record = records[0]; radius = calls[0]['radius']; halo = 2*radius+1
    assert record.stage == 'body_skin_evenness' and record.delta is None
    assert record.weights is None and record.amounts is None
    assert record.window == (100-halo, 80-halo, 115+2*halo, 130+2*halo)
    assert record.chroma_shift.dtype == np.float32 and not record.chroma_shift.flags.writeable
    assert record.chroma_shift.shape == (*record.window[2:], 2)
    assert np.count_nonzero(calls[0]['coverage']) == 25*30+30*30
    y, x, h, w = record.window
    np.testing.assert_array_equal(calls[0]['source'], data[-2][y:y+h, x:x+w])
    assert record.facts['body_ref'] == data[5]['body_ref']
    assert record.facts['reference_samples'] == 25*30+30*30
    assert record.facts['body_to_face_matching'] is False
    assert record.facts['runtime_quality_accepted'] is False


def test_all_faces_semantics_exclusions_and_ineligible_pixels_are_exactly_zero():
    data = fixture(); state, _, ref, _, analysis, _, source, manual = data
    manual[:] = 255
    other = P.new_face(ref['asset_sha256'], [.6, .6, .8, .8], {
        **analysis['evidence'], 'status': 'unresolved', 'landmark_digest': None})
    other['enabled'] = False; state['faces'][other['face_instance_id']] = other
    analysis['body_skin'][:, :12] = 0
    analysis['excluded'][90:110, 110:130] = 1
    source[160:170, 100:110] = 0
    source[180:190, 100:110] = 1
    records, calls = prepare(data); record = records[0]
    field = expand(record, record.chroma_shift, source.shape[:2])
    coverage = expand(record, calls[0]['coverage'], source.shape[:2])
    assert not np.any(coverage[:, :12])
    assert not np.any(coverage[24:78, 24:78])
    assert not np.any(coverage[152:206, 152:206])
    assert not np.any(coverage[90:110, 110:130])
    assert not np.any(field[160:170, 100:110]) and not np.any(field[180:190, 100:110])
    assert not np.any(field[coverage == 0]) and np.any(field != 0)


def test_faces_never_contribute_reference_even_if_their_colour_changes():
    data = fixture(); records, calls = prepare(data)
    data[-2][25:78, 25:78] = [.1, .9, .2]
    changed, changed_calls = prepare(data)
    np.testing.assert_array_equal(records[0].chroma_shift, changed[0].chroma_shift)
    assert records[0].facts['reference_samples'] == changed[0].facts['reference_samples']
    np.testing.assert_array_equal(calls[0]['source'], changed_calls[0]['source'])


def test_halo_clips_only_at_true_source_edges_without_padding_or_per_tile_solve():
    data = fixture(); data[-1][:] = 0; data[-1][0:20, 100:125] = 255
    data[-1][235:256, 200:225] = 255
    records, calls = prepare(data)
    assert len(records) == len(calls) == 1
    record = records[0]; y, x, h, w = record.window
    assert y == 0 and h == 256
    np.testing.assert_array_equal(calls[0]['source'], data[-2][y:y+h, x:x+w])
    assert np.count_nonzero(calls[0]['coverage']) == 20*25+21*25


@pytest.mark.parametrize('fault', ['dtype', 'nan', 'hdr', 'negative'])
def test_source_is_finite_sdr_float32_not_clipped_or_converted(fault):
    data = list(fixture())
    if fault == 'dtype': data[-2] = data[-2].astype(np.float64)
    elif fault == 'nan': data[-2][100, 100, 0] = np.nan
    elif fault == 'hdr': data[-2][100, 100, 0] = 1.001
    else: data[-2][100, 100, 0] = -.001
    with pytest.raises(ValueError):
        prepare(data)


@pytest.mark.parametrize('mutation', ['body-unlink', 'body-disabled', 'body-reanalyse',
    'people-revision', 'body-revision', 'body-model', 'observation-source', 'merged-only'])
def test_stale_or_missing_source_person_and_semantic_evidence_refuses(mutation):
    data = list(fixture()); state, _, ref, bank, analysis, review, _, _ = data
    if mutation == 'body-unlink': data[3] = B.unlink(bank, review['body_ref'])
    elif mutation == 'body-disabled': B.target(bank, review['body_ref'])['enabled'] = False
    elif mutation == 'body-reanalyse':
        data[3] = B.reanalyse(bank, review['body_ref'], B.target(bank, review['body_ref'])['record'],
                            user_confirmed=True)
    elif mutation == 'people-revision': state['association_revision'] += 1
    elif mutation == 'body-revision': bank['association_revision'] += 1
    elif mutation == 'body-model': B.target(bank, review['body_ref'])['record']['model_sha256'] = '9'*64
    elif mutation == 'observation-source': analysis['body_skin_observation']['source_sha256'] = '9'*64
    else:
        analysis['skin'] = analysis.pop('body_skin'); analysis.pop('body_skin_observation')
    with pytest.raises(ValueError):
        prepare(data)


@pytest.mark.parametrize('fault', ['visibility', 'presence', 'outside-frame', 'degenerate', 'tiny'])
def test_genuine_pose_scale_required_even_with_large_reviewed_brush(fault):
    data = list(fixture(attach=False)); state, assets, ref, bank, analysis, review, _, manual = data
    measured = B.target(bank, review['body_ref'])['record']; points = measured['points']
    if fault in ('visibility', 'presence'): points[11][fault] = .49
    elif fault == 'outside-frame': points[11]['x'] = -.01
    elif fault == 'degenerate': points[12].update(x=points[11]['x'], y=points[11]['y'])
    else: points[12].update(x=points[11]['x']+.001, y=points[11]['y'])
    measured['points_sha256'] = E.content_digest(points)
    review['points_sha256'] = measured['points_sha256']
    data[0], data[1] = SUPPORT.retain(state, assets, ref, bank, analysis, review, **OPTIONS)
    manual[:] = 255
    with patch.object(SUPPORT.M, 'raster') as raster:
        with pytest.raises(ValueError, match='scale|radius'):
            state, assets, ref, bank, analysis, _, source, _ = data
            L.prepare(ref, analysis, source, ACTIVE, people_state=state,
                      body_assets=assets, body_bank=bank, byte_budget=BUDGET)
        raster.assert_not_called()


def test_radius_is_current_pose_scale_not_brush_or_producer_dimensions():
    small, small_calls = prepare(fixture(size=256, producer_size=64))
    large, large_calls = prepare(fixture(size=512, producer_size=64))
    assert large_calls[0]['radius'] > small_calls[0]['radius']
    data = fixture(); data[-1][:] = 255
    broad, broad_calls = prepare(data)
    assert broad_calls[0]['radius'] == small_calls[0]['radius']
    assert large[0].facts['source_dimensions'] == [1024, 1024]
    assert large[0].facts['body_support']['semantic_observation']['producer_width'] == 64


def test_radius_upper_bound_is_rejected_without_clamping_or_allocating_body_arrays():
    data = fixture(attach=True, source_size=16384)
    state, assets, ref, bank, analysis, _, _, _ = data
    record, _ = SUPPORT.resolve(state, assets, ref, bank, analysis, **OPTIONS)
    with pytest.raises(ValueError, match='4..256'):
        L._geometry(bank, record, (16384, 16384))


@pytest.mark.parametrize('fault', ['missing', 'dtype', 'shape', 'nan', 'range'])
def test_exclusions_are_required_real_finite_current_grid_evidence(fault):
    data = fixture(); analysis = data[4]
    if fault == 'missing': analysis.pop('excluded')
    elif fault == 'dtype': analysis['excluded'] = analysis['excluded'].astype(np.float64)
    elif fault == 'shape': analysis['excluded'] = analysis['excluded'][::2, ::2]
    elif fault == 'nan': analysis['excluded'][0, 0] = np.nan
    else: analysis['excluded'][0, 0] = 1.1
    with pytest.raises(ValueError):
        prepare(data)


def test_competing_different_family_review_reserves_owner_even_if_disabled():
    data = fixture(); state, assets, ref, _, analysis, _, _, manual = data
    competitor = deepcopy(next(iter(assets.values())))
    other = P.new_face(ref['asset_sha256'], [.7, .05, .9, .2], analysis['evidence'])
    other['enabled'] = False; other_ref = P.face_ref(other)
    competitor['face_ref'] = other_ref
    competitor['row'].update(target=SUPPORT.KIND, operation_id=SUPPORT.OPERATION)
    competitor['row']['face_link']['face_instance_id'] = other_ref['face_instance_id']
    key = SUPPORT.content_digest(SUPPORT.check_record(competitor, family='skin_colour'))
    assets[key] = competitor
    other['local_assets'][SUPPORT.KIND] = {'owner': other_ref, 'kind': SUPPORT.KIND, 'content_sha256': key}
    state['faces'][other_ref['face_instance_id']] = other
    with pytest.raises(ValueError, match='overlap'):
        prepare(data)


@pytest.mark.parametrize('source_value', [0., 1., .005])
def test_unobservable_reference_refuses_before_native(source_value):
    data = fixture(); data[-2][:] = source_value
    with pytest.raises(ValueError, match='64 reliable own-body'):
        prepare(data, native=lambda *a, **k: pytest.fail('unobservable source reached native'))


def test_fewer_than_64_reliable_body_samples_never_fall_back_to_face():
    data = fixture(); data[-1][:] = 0; data[-1][100:107, 100:109] = 255
    with pytest.raises(ValueError, match='64 reliable own-body'):
        prepare(data)


@pytest.mark.parametrize('message', ['insufficient reliable own-body source reference',
                                    'insufficient supported source guided context'])
def test_native_reference_and_context_refusals_are_authoritative(message):
    def refuse(*args, **kwargs):
        raise ValueError(message)
    with pytest.raises(ValueError, match=message):
        prepare(fixture(), native=refuse)


def test_native_zero_correction_is_honest_noop_after_successful_reference_admission():
    records, _ = prepare(fixture(), native=lambda source, coverage, *a, **k:
                         np.zeros((*coverage.shape, 2), np.float32))
    assert records[0].facts['reference_samples'] >= 64
    assert records[0].facts['reason'] == 'no-source-chroma-correction'
    assert not np.any(records[0].chroma_shift)


@pytest.mark.parametrize('fault', ['rgb-delta', 'nan', 'unbounded', 'protected', 'unobservable'])
def test_invalid_native_output_is_never_published(fault):
    data = fixture(); data[-2][120:130, 100:110] = 0
    def invalid(source, coverage, *args, **kwargs):
        if fault == 'rgb-delta': return np.zeros((*coverage.shape, 3), np.float32)
        result = np.zeros((*coverage.shape, 2), np.float32)
        if fault == 'nan': result[0, 0, 0] = np.nan
        elif fault == 'unbounded': result[coverage > 0] = [.08, .08]
        elif fault == 'protected': result[coverage == 0] = [.01, 0.]
        else: result[np.all(source == 0, axis=2)] = [.01, 0.]
        return result
    with pytest.raises(ValueError):
        prepare(data, native=invalid)


def test_full_grid_budget_refuses_before_any_raster_or_native_allocation():
    data = fixture(); state, assets, ref, bank, analysis, _, source, _ = data
    with patch.object(SUPPORT, 'resolve') as resolve, patch.object(SUPPORT.M, 'raster') as raster, \
            patch.object(N, 'prepare') as native:
        with pytest.raises(ValueError, match='memory budget before allocation'):
            L.prepare(ref, analysis, source, ACTIVE, people_state=state,
                      body_assets=assets, body_bank=bank, byte_budget=0)
        resolve.assert_not_called(); raster.assert_not_called(); native.assert_not_called()


def test_complete_support_window_budget_refuses_before_source_snapshot_and_solver():
    data = fixture(size=512); data[-1][:] = 255
    # The support/raster admission fits, but a full-window guided solve does not.
    with pytest.raises(ValueError, match='source-window working set'):
        prepare(data, byte_budget=72*1024**2,
                native=lambda *a, **k: pytest.fail('unadmitted source window reached native'))


def test_missing_native_and_cancellation_never_publish_partial_output():
    data = fixture(); state, assets, ref, bank, analysis, _, source, manual = data
    with patch.object(SUPPORT.M, 'raster', return_value=manual), patch.object(N, 'available', return_value=False):
        with pytest.raises(RuntimeError, match='unavailable'):
            L.prepare(ref, analysis, source, ACTIVE, people_state=state,
                      body_assets=assets, body_bank=bank, byte_budget=BUDGET)
    with pytest.raises(InterruptedError):
        prepare(data, cancelled=lambda: True)
    cancelled = [False]
    def cancel(source, coverage, *a, **k):
        cancelled[0] = True
        return np.zeros((*coverage.shape, 2), np.float32)
    with pytest.raises(InterruptedError):
        prepare(data, native=cancel, cancelled=lambda: cancelled[0])


def test_field_owns_bytes_not_native_result_source_or_review_mutation():
    data = fixture(); returned = []
    def native(source, coverage, *args, **kwargs):
        result = native_prepare_double([])(source, coverage, *args, **kwargs)
        result.setflags(write=True); returned.append(result)
        return result
    records, _ = prepare(data, native=native); field = records[0].chroma_shift
    before = field.copy(); data[-2][:] = 0; data[4]['body_skin'][:] = 0; returned[0][:] = 0
    np.testing.assert_array_equal(field, before)
    assert not field.flags.writeable and not np.shares_memory(field, returned[0])


def test_project_checks_active_undo_and_redo_without_live_body_resolution():
    state, _, ref, _, _, _, _, _ = fixture()
    active = P.set_override(state, 'face', ref['face_instance_id'], S.OP, '/amount', .6)
    value = {'people_graph': active, 'undo': [{'people_graph': state}],
             'redo': [{'_people_state': deepcopy(active)}]}
    before = deepcopy(value)
    with patch.object(SUPPORT, 'resolve', side_effect=AssertionError('history resolved current body')):
        PROJECT.validate_records(value)
    assert value == before
    for branch in ('active', 'undo', 'redo'):
        bad = deepcopy(value)
        graph = bad['people_graph'] if branch == 'active' else bad[branch][0][
            'people_graph' if branch == 'undo' else '_people_state']
        graph['overrides'].append({'scope': 'face', 'target_id': ref['face_instance_id'],
            'operation_id': S.OP, 'parameter_path': '/reference_rgb', 'value': .2})
        with pytest.raises(ValueError):
            PROJECT.validate_records(bad)
