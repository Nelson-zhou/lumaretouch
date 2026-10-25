# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN schema, ownership, layer and composition contracts.

These fixtures are synthetic and several mock source/native boundaries. They do
NOT establish trusted-decoder correctness, Rust numerical behavior, real skin
segmentation, runtime performance, image quality or representative-photo review.
No product imports or execution occurred while authoring this file.
"""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
import pytest

from lumaretouch_engine import neck_wrinkle_state as S
from lumaretouch_engine import neck_wrinkle_support as C
from lumaretouch_engine import neck_wrinkle_layer as L
from lumaretouch_engine import neck_wrinkle_composition as COMPOSE
from lumaretouch_engine import neck_wrinkle_project as PROJECT
from lumaretouch_engine import neck_wrinkle_measure as N
from lumaretouch_engine import skin_colour_body_support as OWNER
from lumaretouch_engine import body_pose_state as BODY
from test_skin_colour_body_support_unrun import fixture as body_fixture

BUDGET = 512 * 1024**2
OPTIONS = {'family': C.FAMILY, 'operation_id': S.OP}


def neck():
    return {'version': 1, 'domain': 'source-normalized', 'line_half_width': 2/64,
            'protect_recipe': {'version': 1, 'domain': 'source-normalized', 'objects': []},
            'protections_reviewed': True, 'visible_neck_skin_reviewed': True}


def fixture():
    state, assets, ref, bank, analysis, review = body_fixture()
    analysis['excluded'] = np.zeros((64, 64), np.float32)
    return state, assets, ref, bank, analysis, {**review, 'neck': neck()}


def retained():
    state, assets, ref, bank, analysis, review = fixture()
    state, assets = C.retain(state, assets, ref, bank, analysis, review)
    return state, assets, ref, bank, analysis, review


def pixels(value=.4):
    out = np.full((64, 64, 3), value, np.float32)
    out.setflags(write=False)
    return out


def prepared(value=.01):
    field = np.full((8, 16), value, np.float32); field.setflags(write=False)
    eligible = np.ones((8, 16), np.bool_); eligible.setflags(write=False)
    return SimpleNamespace(window_yxhw=(32, 24, 8, 16), source_shape_hw=(64, 64),
        log_gain=field, eligible_mask=eligible, algorithm_version=N.ALGORITHM_VERSION,
        facts={'supported_pixels': 128, 'context_rejected_pixels': 0,
            'line_pixels': 128 if value else 0, 'changed_pixels': 128 if value else 0,
            'no_signal_reason': None if value else 'no_detected_wrinkle_lines',
            'runtime_quality_accepted': False})


def layer(*, amount=.5, result=None, budget=BUDGET, review=False, inputs=None):
    state, assets, ref, bank, analysis, _ = retained() if inputs is None else inputs
    packet = SimpleNamespace(rgb=pixels(), analysis=analysis, resident_bytes=64*64*24,
        proof={'source': {'sha256': ref['asset_sha256'], 'width': 64, 'height': 64},
               'pixel_sha256': '1'*64, 'repair_sha256': '2'*64})
    from lumaretouch_engine import neck_wrinkle_source as SOURCE
    with patch.object(SOURCE, 'resolve', return_value=packet), \
         patch.object(C.M, 'raster', side_effect=[np.full((64, 64), 255, np.uint8), np.zeros((64, 64), np.uint8)]), \
         patch.object(N, 'measure', return_value=prepared() if result is None else result) as measure:
        output = (L.prepare_review if review else L.prepare)(ref, analysis,
            {'version': 1, 'amount': amount}, people_state=state, body_assets=assets,
            body_bank=bank, full_source=object(), byte_budget=budget)
    return output, measure


def effect(value=.01, *, ref_id='face-fixture', window=(20, 20, 8, 12), amount=.5):
    y, x, h, w = window
    gain = np.full((h, w, 1), value, np.float32); gain.setflags(write=False)
    ref = {'asset_sha256': 'a'*64, 'face_instance_id': ref_id, 'analysis_revision': 0}
    return SimpleNamespace(stage='neck_wrinkle', face_ref=ref, window=window,
        log_gain=gain, delta=None, chroma_shift=None, weights=None, amounts={'amount': amount},
        facts={'operation_id': S.OP, 'face_ref': ref, 'source_shape_hw': [64, 64],
               'source_proof': {'pixel_sha256': 'b'*64}, 'measurement_key': 'c'*64,
               'runtime_quality_accepted': False})


def test_stable_leaf_and_amount_only_portability():
    assert S.OP == 'lnx.neck_wrinkle.v1' and S.CONTROL_ID == 'control:PC-32464:19'
    assert C.KIND == 'neck_wrinkle_visibility' and C.FAMILY == 'neck_wrinkle'
    assert S.neutral() == {'version': 1, 'amount': 0.0}
    assert S.portable({'version': 1, 'amount': .6}) == {'version': 1, 'amount': .6}


@pytest.mark.parametrize('amount', [True, False, -.01, 1.01, float('nan'), float('inf'), 10**400, '0.5'])
def test_invalid_amount_is_not_coerced_or_clamped(amount):
    with pytest.raises(ValueError): S.check({'version': 1, 'amount': amount})


@pytest.mark.parametrize('value', [{'version': True, 'amount': 0}, {'version': 2, 'amount': 0},
    {'version': 1, 'amount': .5, 'neck': {}}, {'amount': .5}])
def test_no_review_or_unknown_fields_in_portable_intent(value):
    with pytest.raises(ValueError): S.check(value)


def test_neutral_layer_and_composition_need_no_source_support_backend_or_budget():
    with patch.object(C, 'resolve', side_effect=AssertionError), patch.object(N, 'measure', side_effect=AssertionError):
        assert L.prepare(None, None, S.neutral(), people_state=None, body_assets=None,
                         body_bank=None, full_source=None, byte_budget=0) == []
        assert L.prepare_review(None, None, S.neutral(), people_state=None, body_assets=None,
                         body_bank=None, full_source=None, byte_budget=0) == ([], None)
    sentinel = object()
    assert COMPOSE.apply_records_np(sentinel, [effect(amount=0)], byte_budget=0)[0] is sentinel
    assert COMPOSE.apply_records_t(sentinel, [], source_shape=None, byte_budget=0) is sentinel


@pytest.mark.parametrize('fault', ['missing-ack', 'false-visible', 'version-bool', 'foreign-key',
    'nan-scale', 'bool-scale', 'zero-scale', 'too-small', 'too-large', 'proxy-domain'])
def test_independent_neck_review_and_observed_source_scale_are_required(fault):
    value = neck()
    if fault == 'missing-ack': del value['protections_reviewed']
    elif fault == 'false-visible': value['visible_neck_skin_reviewed'] = False
    elif fault == 'version-bool': value['version'] = True
    elif fault == 'foreign-key': value['clavicle'] = {}
    elif fault == 'nan-scale': value['line_half_width'] = float('nan')
    elif fault == 'bool-scale': value['line_half_width'] = True
    elif fault == 'zero-scale': value['line_half_width'] = 0
    elif fault == 'too-small': value['line_half_width'] = 1.39/64
    elif fault == 'too-large': value['line_half_width'] = 12.01/64
    else: value['domain'] = 'viewport'
    with pytest.raises(ValueError): C.check_neck_review(value, source={'width': 64, 'height': 64})


def test_empty_protection_means_explicit_reviewed_none_not_automatic_occlusion_clearance():
    assert C.check_neck_review(neck())['protect_recipe']['objects'] == []
    value = neck(); value['protections_reviewed'] = False
    with pytest.raises(ValueError): C.check_neck_review(value)


@pytest.mark.parametrize('mutation', [{'operation': 'subtract'}, {'opacity': .99},
    {'enabled': False}, {'feather': 1}, {'kind': 'full'}])
def test_protection_cannot_be_weakened_by_opacity_feather_disabled_or_subtract(mutation):
    *_, review = fixture(); value = neck()
    stroke = deepcopy(review['recipe']['objects'][0]); stroke.update(mutation)
    value['protect_recipe']['objects'] = [stroke]
    with pytest.raises(ValueError): C.check_neck_review(value)


def test_support_remains_in_canonical_bank_and_never_borrows_old_family_consent():
    state, assets, ref, bank, analysis, review = fixture()
    before_bank = deepcopy(bank)
    old = {key: value for key, value in review.items() if key != 'neck'}
    previous, previous_assets = OWNER.retain(state, assets, ref, bank, analysis, old)
    assert C.resolve(previous, previous_assets, ref, None, None) is None
    with pytest.raises(ValueError): C.retain(state, assets, ref, bank, analysis, old)
    new, new_assets = C.retain(state, assets, ref, bank, analysis, review)
    record, key = C.resolve(new, new_assets, ref, bank, analysis)
    assert new['faces'][ref['face_instance_id']]['local_assets'][C.KIND] == {
        'owner': ref, 'content_sha256': key, 'kind': C.KIND}
    assert new_assets[key] == record and new['overrides'] == state['overrides']
    assert assets == {} and bank == before_bank


def test_no_demographic_eligibility_is_inferred_or_copied_from_collarbone():
    state, assets, ref, bank, analysis, review = fixture()
    state['faces'][ref['face_instance_id']]['labels'] = {'gender_label': '男', 'age_band': '儿童'}
    C.retain(state, assets, ref, bank, analysis, review)


@pytest.mark.parametrize('fault', ['unlink', 'disabled', 'body-revision', 'people-revision',
    'missing-semantic', 'missing-excluded', 'merged-only'])
def test_live_source_body_person_and_named_semantic_evidence_fail_closed(fault):
    state, assets, ref, bank, analysis, _ = retained()
    if fault == 'unlink': bank = BODY.unlink(bank, next(iter(bank['bodies'].values()))['record']['body_ref'])
    elif fault == 'disabled': next(iter(bank['bodies'].values()))['enabled'] = False
    elif fault == 'body-revision': bank['association_revision'] += 1
    elif fault == 'people-revision': state['association_revision'] += 1
    elif fault == 'missing-semantic': analysis.pop('body_skin_observation')
    elif fault == 'missing-excluded': analysis.pop('excluded')
    else: analysis['skin'] = analysis.pop('body_skin')
    with pytest.raises(ValueError): C.raster(state, assets, ref, bank, analysis,
                                            (64, 64), byte_budget=BUDGET)


def test_hard_veto_applies_after_positive_paint_even_for_small_known_occluder_weight():
    state, assets, ref, bank, analysis, _ = retained()
    analysis['excluded'][35, 30] = .0001
    protection = np.zeros((64, 64), np.uint8); protection[36, 30] = 1
    with patch.object(C.M, 'raster', side_effect=[np.full((64, 64), 255, np.uint8), protection]):
        admitted, hard, facts = C.raster(state, assets, ref, bank, analysis, (64, 64), byte_budget=BUDGET)
    assert hard[35, 30] and hard[36, 30] and admitted[35, 30] == admitted[36, 30] == 0
    assert not np.any(admitted[5:21, 5:21])
    assert not admitted.flags.writeable and not hard.flags.writeable
    assert facts['manual_protected_pixels'] == 1 and facts['runtime_quality_accepted'] is False


def test_proxy_grid_and_short_budget_refuse_before_raster_allocation():
    state, assets, ref, bank, analysis, _ = retained()
    with patch.object(C.M, 'raster') as raster:
        with pytest.raises(ValueError): C.raster(state, assets, ref, bank, analysis, (32, 32), byte_budget=BUDGET)
        with pytest.raises(MemoryError): C.raster(state, assets, ref, bank, analysis, (64, 64), byte_budget=0)
    raster.assert_not_called()


def test_history_validates_old_record_without_live_rebinding_and_detach_remains_reachable():
    state, assets, ref, bank, analysis, _ = retained()
    before = deepcopy(assets); detached = C.detach(state, ref)
    PROJECT.validate_project({'people_graph': detached, 'people_support_assets': assets,
                              'undo': [{'people_graph': state}]})
    assert C.resolve(detached, assets, ref, None, None) is None and assets == before


@pytest.mark.parametrize('scope', ['all_people', 'person', 'group'])
def test_first_slice_shared_cohorts_batch_and_generic_face_recovery_are_fenced(scope):
    with pytest.raises(ValueError): PROJECT.require_face_scope(scope)
    with pytest.raises(ValueError): PROJECT.refuse_transfer()
    with pytest.raises(ValueError): PROJECT.refuse_recovery()


def test_field_and_exact_eligibility_remain_separate_and_amount_does_not_change_measurement_key():
    inputs = retained()
    (effects, evidence), call = layer(review=True, inputs=inputs)
    other, _ = layer(amount=.9, inputs=inputs)
    assert effects[0].stage == 'neck_wrinkle' and effects[0].delta is None
    assert effects[0].log_gain.shape == (8, 16, 1) and not effects[0].log_gain.flags.writeable
    assert evidence.eligible_mask.shape == (8, 16) and evidence.admitted_weight.shape == (64, 64)
    assert evidence.measurement_key == effects[0].facts['measurement_key']
    assert other[0].facts['measurement_key'] == effects[0].facts['measurement_key']
    assert 'amount' not in call.call_args.kwargs and other[0].amounts == {'amount': .9}


def test_valid_no_lines_is_honest_zero_field_not_absent_context_or_fake_visible_change():
    effects, _ = layer(result=prepared(0))
    assert effects[0].facts['changed_pixels'] == 0
    assert effects[0].facts['native_report']['supported_pixels'] == 128
    assert effects[0].facts['no_signal_reason'] == 'no_detected_wrinkle_lines'


@pytest.mark.parametrize('fault', ['mutable', 'negative', 'nonfinite', 'protected', 'wrong-source',
    'wrong-algorithm', 'eligible-mutable', 'eligible-wrong-count', 'claim-change-on-zero'])
def test_layer_refuses_invalid_or_misreported_native_field(fault):
    value = prepared()
    if fault == 'mutable': value.log_gain.setflags(write=True)
    elif fault in ('negative', 'nonfinite'):
        value = prepared(-.1 if fault == 'negative' else np.nan)
    elif fault == 'protected': value.window_yxhw = (5, 5, 8, 16)
    elif fault == 'wrong-source': value.source_shape_hw = (32, 32)
    elif fault == 'wrong-algorithm': value.algorithm_version = 'unknown'
    elif fault == 'eligible-mutable': value.eligible_mask.setflags(write=True)
    elif fault == 'eligible-wrong-count': value.facts['supported_pixels'] = 127
    else: value = prepared(0); value.facts['changed_pixels'] = 1
    with pytest.raises(ValueError): layer(result=value)


def test_zero_field_and_zero_headroom_avoid_backend_and_roundtrip():
    original = pixels(); white = pixels(1)
    with patch.object(N, 'apply', side_effect=AssertionError), \
         patch.object(COMPOSE, '_admit', return_value=None):
        out, facts = COMPOSE.apply_records_np(original, [effect(0)])
        saturated, saturation = COMPOSE.apply_records_np(white, [effect()])
    assert out is original and saturated is white
    assert facts['changed_pixels'] == saturation['changed_pixels'] == 0


def test_overlap_is_refused_outside_current_tile_before_any_kernel_call():
    records = [effect(ref_id='one'), effect(ref_id='two')]
    tile = np.full((4, 4, 3), .4, np.float32)
    with patch.object(COMPOSE, '_admit', return_value=None), patch.object(N, 'apply') as apply:
        with pytest.raises(ValueError, match='overlap'):
            COMPOSE.apply_records_np(tile, records, source_shape=(64, 64), origin=(0, 0))
    apply.assert_not_called()


def test_exact_expanded_tile_intersection_slices_the_existing_field_without_new_measurement():
    record = effect(window=(20, 20, 8, 12)); source = np.full((64, 64, 3), .4, np.float32)
    def controlled_transport(current, field, amount, *, encoded):
        # Deliberately not a physical/native oracle: transport-origin fixture only.
        result = current.copy(); result[field > 0] = np.float32(.45); return result
    with patch.object(COMPOSE, '_admit', return_value=None), \
         patch.object(COMPOSE, '_native', side_effect=controlled_transport), patch.object(N, 'measure') as measure:
        full, _ = COMPOSE.apply_records_np(source, [record])
        crop, _ = COMPOSE.apply_records_np(source[22:31, 25:36].copy(), [record],
                                          source_shape=(64, 64), origin=(22, 25))
    np.testing.assert_array_equal(crop, full[22:31, 25:36]); measure.assert_not_called()


def test_current_linear_pixels_reach_native_not_source_pixels_and_untouched_signed_zero_stays_exact():
    current = np.full((64, 64, 3), .2, np.float32); current[0, 0, 0] = -0.0
    record = effect()
    def native_stub(rgb, field, *, amount):
        assert np.all(rgb == .2) and amount == .5
        result = rgb.copy(); result[...] = np.float32(.21); return result
    with patch.object(COMPOSE, '_admit', return_value=None), patch.object(N, 'apply', side_effect=native_stub) as native:
        out, facts = COMPOSE.apply_np(current, [record])
    assert native.call_count == 1 and facts['changed_pixels'] == 96
    assert np.signbit(out[0, 0, 0]) and np.array_equal(out[:20].view(np.uint32), current[:20].view(np.uint32))


def test_detected_but_fully_gated_lines_are_distinct_from_no_lines():
    value = prepared(0)
    value.facts.update(line_pixels=12, no_signal_reason='no_positive_wrinkle_lift')
    effects, _ = layer(result=value)
    assert effects[0].facts['changed_pixels'] == 0
    assert effects[0].facts['no_signal_reason'] == 'no_positive_wrinkle_lift'


def test_new_protection_or_scale_changes_measurement_identity_even_when_scalar_amount_does_not():
    inputs = retained(); state, assets, ref, bank, analysis, review = inputs
    record, _ = C.resolve(state, assets, ref, bank, analysis)
    support = {name: str(index)*64 for index, name in enumerate((
        'body_skin_plane_sha256', 'known_occluder_plane_sha256',
        'admitted_plane_sha256', 'hard_protect_plane_sha256'), start=1)}
    proof = {'pixel_sha256': 'a'*64, 'repair_sha256': 'b'*64}
    original = C.measurement_key(record, support, proof, N.ALGORITHM_VERSION)
    changed = deepcopy(record); changed['row']['review']['neck']['line_half_width'] = 3/64
    assert C.measurement_key(changed, support, proof, N.ALGORITHM_VERSION) != original
    assert C.measurement_key(record, support, {**proof, 'repair_sha256': 'c'*64}, N.ALGORITHM_VERSION) != original
    assert C.measurement_key(record, {**support, 'hard_protect_plane_sha256': 'e'*64}, proof, N.ALGORITHM_VERSION) != original


def test_bad_field_or_mixed_actual_source_cannot_hide_behind_an_unrelated_tile():
    first = effect(ref_id='one', window=(20, 20, 8, 12))
    second = effect(ref_id='two', window=(40, 40, 8, 12))
    second.facts['source_proof'] = {'pixel_sha256': 'd'*64}
    tile = np.full((4, 4, 3), .4, np.float32)
    with patch.object(COMPOSE, '_admit', return_value=None), patch.object(N, 'apply') as apply:
        with pytest.raises(ValueError, match='mix'):
            COMPOSE.apply_records_np(tile, [first, second], source_shape=(64, 64), origin=(0, 0))
        first.log_gain = None
        with pytest.raises(ValueError, match='field'):
            COMPOSE.apply_records_np(tile, [first], source_shape=(64, 64), origin=(0, 0))
    apply.assert_not_called()


def test_cancelled_layer_does_not_resolve_or_measure_even_with_active_intent():
    with patch.object(C, 'resolve') as resolve, patch.object(N, 'measure') as measure:
        with pytest.raises(InterruptedError):
            L.prepare(None, None, {'version': 1, 'amount': .5}, people_state=None,
                body_assets=None, body_bank=None, full_source=None, byte_budget=0, cancelled=lambda: True)
    resolve.assert_not_called(); measure.assert_not_called()
