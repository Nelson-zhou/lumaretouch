# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: same-photo selected-face relation/support contracts.

Synthetic anatomy, source identifiers and semantic observations below exercise
real validators and face-scope APIs when eventually run. They are not actual
inference, photographic acceptance, native fitting or an automatic AI feature.
No product import, test collection/execution, build, inference or typecheck ran
during authoring. No geometry/ownership validator is replaced by a test double.
"""
from copy import deepcopy
import hashlib
import json
from unittest.mock import patch

import numpy as np
import pytest

from lumaretouch_engine import face_scope as FACE, people_state as P
from lumaretouch_engine import skin_colour_support as SEM
from lumaretouch_engine import skin_reference_match_state as S
from lumaretouch_engine import skin_reference_match_support as V
from lumaretouch_engine.ops.enhance import EYE_RING_LEFT, EYE_RING_RIGHT

BUDGET = 512 * 1024**2


def add_face(state, name, *, center=(.25, .45), span=(.18, .32), shape=(256, 256), source_size=512):
    """Synthetic official-topology ring fixture, not authenticated model output."""
    cx, cy = center; rx, ry = span
    landmarks = np.full((478, 3), [cx, cy, 0.], dtype='<f4')
    def ellipse(indices, x, y, width, height):
        theta = np.linspace(-np.pi/2, 3*np.pi/2, len(indices), endpoint=False)
        landmarks[list(indices), :2] = np.column_stack((x + width*np.cos(theta), y + height*np.sin(theta)))
    ellipse(FACE.FACE_OVAL, cx, cy, rx, ry)
    ellipse(EYE_RING_LEFT, cx - .4*rx, cy - .22*ry, .16*rx, .08*ry)
    ellipse(EYE_RING_RIGHT, cx + .4*rx, cy - .22*ry, .16*rx, .08*ry)
    ellipse(FACE.BROW_LEFT, cx + .4*rx, cy - .43*ry, .20*rx, .06*ry)
    ellipse(FACE.BROW_RIGHT, cx - .4*rx, cy - .43*ry, .20*rx, .06*ry)
    ellipse(FACE.LIPS, cx, cy + .5*ry, .25*rx, .09*ry)
    evidence = {'backend': 'mediapipe', 'detector_model_sha256': 'b'*64,
                'semantic_model_sha256': 'c'*64, 'landmark_digest': hashlib.sha256(landmarks.tobytes()).hexdigest(),
                'status': 'verified', 'source_width': source_size, 'source_height': source_size,
                'orientation': 'exif_normalized_once'}
    face = P.new_face('a'*64, [cx - rx, cy - ry, cx + rx, cy + ry], evidence)
    face['face_instance_id'] = name
    state['faces'][name] = face
    ref = P.face_ref(face)
    analysis = {'face_ref': deepcopy(ref), 'evidence': deepcopy(evidence), 'landmarks': landmarks,
                'excluded': np.zeros(shape, np.float32), 'skin': np.ones(shape, np.float32),
                'face_skin': np.full(shape, .65, np.float32),
                'face_skin_observation': {'contract': SEM.CONTRACT, 'source_sha256': ref['asset_sha256'],
                    'semantic_model_sha256': evidence['semantic_model_sha256'],
                    'producer_width': 128, 'producer_height': 128}}
    return ref, analysis


def fixture(*, shape=(256, 256), source_size=512):
    state = P.empty()
    target, target_analysis = add_face(state, 'synthetic-target', shape=shape, source_size=source_size)
    reference, reference_analysis = add_face(state, 'synthetic-reference', center=(.74, .43),
                                            span=(.13, .24), shape=shape, source_size=source_size)
    return state, {}, target, reference, target_analysis, reference_analysis


def retained(**kwargs):
    state, assets, target, reference, ta, ra = fixture(**kwargs)
    state, assets = V.retain(state, assets, target, reference, ta, ra, confirmed=True)
    return state, assets, target, reference, ta, ra


def masks(data, *, shape=None, byte_budget=BUDGET, cancelled=None):
    state, assets, target, _, ta, ra = data
    return V.geometry(state, assets, target, ta, ra, shape or ta['face_skin'].shape,
                      byte_budget=byte_budget, cancelled=cancelled)


def test_scalar_is_only_portable_amount_and_neutral_is_not_a_reference():
    assert S.OP == 'lnx.skin_reference_match.v1'
    assert S.CONTROL_ID == 'control:PC-32465:19'
    assert S.neutral() == S.check(None) == {'version': 1, 'amount': 0.0}
    assert not S.active(None) and S.active({'version': 1, 'amount': .001})
    assert S.check({'version': 1, 'amount': 1}) == {'version': 1, 'amount': 1.0}
    assert S.KEYS == ('amount',)


@pytest.mark.parametrize('value', [True, [], {}, {'amount': .5}, {'version': True, 'amount': .5},
    {'version': 2, 'amount': .5}, {'version': 1, 'amount': True}, {'version': 1, 'amount': '0.5'},
    {'version': 1, 'amount': -0.01}, {'version': 1, 'amount': 1.01},
    {'version': 1, 'amount': float('nan')}, {'version': 1, 'amount': float('inf')},
    {'version': 1, 'amount': 10**1000}, {'version': 1, 'amount': .5, 'reference_face_ref': {}},
    {'version': 1, 'amount': .5, 'body': True}, {'version': 1, 'amount': .5, 'transform': [1, 0, 0, 0]}])
def test_non_scalar_reference_body_and_nonfinite_recipe_are_rejected(value):
    with pytest.raises(ValueError):
        S.check(value)


def test_retain_is_pure_content_addressed_and_never_changes_scalars_or_reference_face():
    data = fixture(); state, assets, target, reference, ta, ra = data
    before = deepcopy(state); ta_before = ta['face_skin'].copy(); ra_before = ra['landmarks'].copy()
    one, bank = V.retain(*data, confirmed=True)
    two, bank2 = V.retain(*data, confirmed=True)
    assert one == two and bank == bank2 and state == before and assets == {}
    assert one['revision'] == state['revision'] + 1 and one['overrides'] == []
    assert one['faces'][reference['face_instance_id']] == before['faces'][reference['face_instance_id']]
    assert V.retain(one, bank, target, reference, ta, ra, confirmed=True) == (one, bank)
    record, key = V.resolve(one, bank, target, ta, ra)
    assert V.content_digest(record) == key and V.check_record(record) == record
    assert set(record) == {'version', 'face_ref', 'source', 'row'}
    assert record['row']['reference_face_ref'] == reference
    assert record['row']['target_landmark_digest'] == ta['evidence']['landmark_digest']
    assert record['row']['reference_landmark_digest'] == ra['evidence']['landmark_digest']
    assert record['row']['source_stage'] == V.SOURCE_STAGE
    assert record['row']['review'] == {'confirmed': True, 'scope': 'face-only', 'reference_unchanged': True}
    assert record['source'] == {'sha256': 'a'*64, 'width': 512, 'height': 512}
    # JSON round-trip proves no image/support/landmark array was retained.
    assert json.loads(json.dumps(record, allow_nan=False)) == record
    np.testing.assert_array_equal(ta['face_skin'], ta_before)
    np.testing.assert_array_equal(ra['landmarks'], ra_before)


@pytest.mark.parametrize('confirmed', [False, None, 0, 1, 'yes'])
def test_this_operation_requires_its_own_explicit_confirmation(confirmed):
    with pytest.raises(ValueError, match='explicit'):
        V.retain(*fixture(), confirmed=confirmed)


@pytest.mark.parametrize('fault', ['same-face', 'same-instance-new-revision', 'foreign-source', 'disabled-target',
    'disabled-reference', 'canonical-dimensions', 'target-grid', 'reference-grid'])
def test_relation_requires_distinct_enabled_exact_same_photo_faces(fault):
    data = list(fixture()); state, _, target, reference, ta, ra = data
    if fault == 'same-face': data[3] = target; data[5] = ta
    elif fault == 'same-instance-new-revision': data[3] = {**target, 'analysis_revision': 1}
    elif fault == 'foreign-source': data[3] = {**reference, 'asset_sha256': 'd'*64}
    elif fault == 'disabled-target': state['faces'][target['face_instance_id']]['enabled'] = False
    elif fault == 'disabled-reference': state['faces'][reference['face_instance_id']]['enabled'] = False
    elif fault == 'canonical-dimensions':
        state['faces'][reference['face_instance_id']]['evidence']['source_width'] = 1024
        ra['evidence']['source_width'] = 1024
    elif fault == 'target-grid': ta['face_skin'] = np.full((128, 128), .65, np.float32); ta['excluded'] = np.zeros((128, 128), np.float32)
    else: ra['face_skin'] = np.full((250, 256), .65, np.float32); ra['excluded'] = np.zeros((250, 256), np.float32)
    with pytest.raises(ValueError): V.retain(*data, confirmed=True)


@pytest.mark.parametrize('name', ['target', 'reference'])
@pytest.mark.parametrize('fault', ['owner', 'evidence', 'landmarks', 'landmark-shape', 'landmark-range',
    'merged-only', 'missing-observation', 'observation-source', 'observation-model', 'observation-grid',
    'skin-dtype', 'skin-nan', 'skin-range', 'excluded-missing', 'excluded-dtype', 'excluded-grid', 'excluded-nan'])
def test_each_actual_analysis_is_checked_without_merged_skin_or_bbox_fallback(name, fault):
    data = list(retained()); analysis = data[4 if name == 'target' else 5]
    if fault == 'owner': analysis['face_ref']['analysis_revision'] += 1
    elif fault == 'evidence': analysis['evidence']['status'] = 'synthetic'
    elif fault == 'landmarks': analysis['landmarks'][0, 0] += .01
    elif fault == 'landmark-shape': analysis['landmarks'] = analysis['landmarks'][:477]
    elif fault == 'landmark-range': analysis['landmarks'][0, 0] = 3
    elif fault == 'merged-only': analysis.pop('face_skin'); analysis.pop('face_skin_observation')
    elif fault == 'missing-observation': analysis.pop('face_skin_observation')
    elif fault == 'observation-source': analysis['face_skin_observation']['source_sha256'] = 'd'*64
    elif fault == 'observation-model': analysis['face_skin_observation']['semantic_model_sha256'] = 'd'*64
    elif fault == 'observation-grid': analysis['face_skin_observation']['producer_width'] = 64
    elif fault == 'skin-dtype': analysis['face_skin'] = analysis['face_skin'].astype(np.float64)
    elif fault == 'skin-nan': analysis['face_skin'][0, 0] = np.nan
    elif fault == 'skin-range': analysis['face_skin'][0, 0] = 1.1
    elif fault == 'excluded-missing': analysis['excluded'] = None
    elif fault == 'excluded-dtype': analysis['excluded'] = analysis['excluded'].astype(np.float64)
    elif fault == 'excluded-grid': analysis['excluded'] = np.zeros((16, 16), np.float32)
    else: analysis['excluded'][0, 0] = np.nan
    with pytest.raises(ValueError): masks(data)


@pytest.mark.parametrize('fault', ['version-bool', 'reference-source', 'same-instance', 'source-size', 'operation',
    'kind', 'source-stage', 'extra-body', 'target-digest', 'reference-digest', 'evidence-backend',
    'semantic-model', 'observation-contract', 'observation-bool', 'review-bool', 'review-body', 'reference-change'])
def test_historical_record_schema_never_aliases_other_operations_or_body_consent(fault):
    state, bank, target, _, _, _ = retained(); record, _ = V.resolve(state, bank, target)
    row = record['row']
    if fault == 'version-bool': record['version'] = True
    elif fault == 'reference-source': row['reference_face_ref']['asset_sha256'] = 'd'*64
    elif fault == 'same-instance': row['reference_face_ref']['face_instance_id'] = target['face_instance_id']
    elif fault == 'source-size': record['source']['height'] = 1024
    elif fault == 'operation': row['operation_id'] = 'lnx.body_face_match.v1'
    elif fault == 'kind': row['target'] = 'body_face_match_visibility'
    elif fault == 'source-stage': row['source_stage'] = 'repaired-source'
    elif fault == 'extra-body': row['body_ref'] = {'body_instance_id': 'unexpected'}
    elif fault == 'target-digest': row['target_landmark_digest'] = 'e'*64
    elif fault == 'reference-digest': row['reference_landmark_digest'] = 'e'*64
    elif fault == 'evidence-backend': row['reference_evidence']['backend'] = 'template'
    elif fault == 'semantic-model': row['target_evidence']['semantic_model_sha256'] = None
    elif fault == 'observation-contract': row['reference_face_skin_observation']['contract'] = 'merged-skin'
    elif fault == 'observation-bool': row['target_face_skin_observation']['producer_width'] = True
    elif fault == 'review-bool': row['review']['confirmed'] = 1
    elif fault == 'review-body': row['review']['scope'] = 'face-and-body'
    else: row['review']['reference_unchanged'] = False
    with pytest.raises(ValueError): V.check_record(record)


def test_missing_relation_is_not_a_default_reference_and_partial_analysis_is_rejected():
    state, assets, target, reference, ta, ra = fixture()
    assert V.resolve(state, assets, target) is None
    assert V.validate_active(state, assets, []) is None
    with pytest.raises(ValueError, match='reviewed relation'): V.validate_active(state, assets, [target])
    state, assets = V.retain(state, assets, target, reference, ta, ra, confirmed=True)
    with pytest.raises(ValueError, match='both exact'): V.resolve(state, assets, target, ta)
    with pytest.raises(ValueError, match='both exact'): V.resolve(state, assets, target, reference_analysis=ra)


def test_history_remains_structurally_valid_while_stale_current_relation_fails():
    state, assets, target, reference, ta, ra = retained()
    old_record, old_key = V.resolve(state, assets, target)
    state['faces'][reference['face_instance_id']]['analysis_revision'] += 1
    assert V.check_record(assets[old_key]) == old_record
    with pytest.raises(ValueError, match='face changed'): V.resolve(state, assets, target)
    detached = V.detach(state, target)
    assert V.KIND not in detached['faces'][target['face_instance_id']]['local_assets']
    assert assets[old_key] == old_record and V.resolve(detached, assets, target) is None


def test_reference_switch_appends_new_relation_and_leaves_undo_bytes_and_amounts():
    state, assets, target, reference, ta, ra = retained()
    old_record, old_key = V.resolve(state, assets, target)
    other, oa = add_face(state, 'synthetic-other-reference', center=(.5, .85), span=(.1, .1))
    state = P.set_override(state, 'face', target['face_instance_id'], S.OP, '/amount', .6)
    before = deepcopy(state['overrides'])
    state, assets = V.retain(state, assets, target, other, ta, oa, confirmed=True)
    record, key = V.resolve(state, assets, target, ta, oa)
    assert key != old_key and len(assets) == 2 and assets[old_key] == old_record
    assert record['row']['reference_face_ref'] == other and state['overrides'] == before
    assert V.KIND not in state['faces'][reference['face_instance_id']]['local_assets']


def test_all_active_targets_agree_on_reference_and_reference_cannot_itself_be_active():
    state, assets, target, reference, ta, ra = retained()
    second, sa = add_face(state, 'synthetic-second-target', center=(.5, .85), span=(.1, .1))
    state, assets = V.retain(state, assets, second, reference, sa, ra, confirmed=True)
    analyses = {target['face_instance_id']: ta, reference['face_instance_id']: ra, second['face_instance_id']: sa}
    assert V.validate_active(state, assets, [second, target], analyses) == reference
    with pytest.raises(ValueError, match='duplicates'): V.validate_active(state, assets, [target, target])
    with pytest.raises(ValueError, match='unavailable'): V.validate_active(state, assets, [target], {})
    state, assets = V.retain(state, assets, second, target, sa, ta, confirmed=True)
    with pytest.raises(ValueError, match='agree'): V.validate_active(state, assets, [target, second], analyses)
    state, assets = V.retain(state, assets, reference, target, ra, ta, confirmed=True)
    with pytest.raises(ValueError): V.validate_active(state, assets, [target, reference], analyses)
    # Dormant old relations need not share the current reference.
    assert V.validate_active(state, assets, [target], analyses) == reference


@pytest.mark.parametrize('fault', ['missing', 'record-mutation', 'descriptor-kind', 'descriptor-owner', 'target-evidence', 'reference-disabled'])
def test_current_descriptor_and_both_retained_evidence_are_authenticated(fault):
    state, assets, target, reference, ta, ra = retained(); descriptor = state['faces'][target['face_instance_id']]['local_assets'][V.KIND]
    key = descriptor['content_sha256']
    if fault == 'missing': del assets[key]
    elif fault == 'record-mutation': assets[key]['row']['target_face_skin_observation']['producer_width'] = 64
    elif fault == 'descriptor-kind': descriptor['kind'] = 'skin_colour_body_visibility'
    elif fault == 'descriptor-owner': descriptor['owner'] = reference
    elif fault == 'target-evidence': state['faces'][target['face_instance_id']]['evidence']['detector_model_sha256'] = 'd'*64
    else: state['faces'][reference['face_instance_id']]['enabled'] = False
    with pytest.raises(ValueError): V.resolve(state, assets, target, ta, ra)


def test_real_geometry_yields_independent_readonly_masks_and_no_body_or_pixel_payload():
    data = retained(); before = deepcopy(data[0]); ta_before = data[4]['face_skin'].copy(); ra_before = data[5]['face_skin'].copy()
    target, reference, facts = masks(data)
    assert target.dtype == reference.dtype == np.float32 and target.shape == reference.shape == (256, 256)
    assert target.flags.c_contiguous and reference.flags.c_contiguous
    assert not target.flags.writeable and not reference.flags.writeable
    assert np.any(target > 0) and np.any(reference > 0) and not np.any((target > 0) & (reference > 0))
    assert facts['target']['source_window'] != facts['reference']['source_window']
    assert facts['source_dimensions'] == [512, 512] and facts['render_dimensions'] == [256, 256]
    assert facts['target']['face_skin_observation']['producer_width'] == 128
    assert facts['source_stage'] == V.SOURCE_STAGE and facts['body_extension']['enabled'] is False
    assert facts['runtime_quality_accepted'] is False
    assert facts['photometric_admission'] == 'rust-skin-reference-fit-only'
    assert facts['reference_selection'] == 'explicit-user-selected-not-auto-brightest'
    assert facts['reference_face_unchanged_by_this_operation'] is True
    assert not np.any(target[205:]) and not np.any(reference[180:])
    assert data[0] == before
    np.testing.assert_array_equal(data[4]['face_skin'], ta_before)
    np.testing.assert_array_equal(data[5]['face_skin'], ra_before)
    for coverage, name in ((target, 'target'), (reference, 'reference')):
        y, x, h, w = facts[name]['source_window']
        assert np.count_nonzero(coverage[y:y+h, x:x+w]) == facts[name]['support_pixels']
        assert not np.shares_memory(coverage, data[4]['face_skin'])
        assert not np.shares_memory(coverage, data[5]['face_skin'])
    assert json.loads(json.dumps(facts, allow_nan=False)) == facts


def test_eyes_lips_brows_outer_pixel_footprints_occluders_and_semantic_holes_are_vetoes():
    data = list(retained()); ta = data[4]; ta['face_skin'][125:140, 58:72] = 0; ta['excluded'][120:135, 85:95] = .5
    target, reference, _ = masks(data)
    assert not np.any(target[125:140, 58:72]) and not np.any(target[120:135, 85:95])
    xx = np.arange(256, dtype=np.float64)[None, :] + .5
    yy = np.arange(256, dtype=np.float64)[:, None] + .5
    for coverage, analysis in ((target, data[4]), (reference, data[5])):
        points = analysis['landmarks'][:, :2].astype(np.float64) * 256
        inside, distance = FACE._polygon_field(xx, yy, points[list(FACE.FACE_OVAL)])
        assert not np.any(coverage[~inside | (distance <= np.sqrt(.5))])
        for ring in (EYE_RING_LEFT, EYE_RING_RIGHT, FACE.BROW_LEFT, FACE.BROW_RIGHT, FACE.LIPS):
            inside, distance = FACE._polygon_field(xx, yy, points[list(ring)])
            assert not np.any(coverage[inside | (distance <= np.sqrt(.5))])


def test_all_foreign_retained_faces_including_disabled_unresolved_are_protection_only():
    data = list(retained()); state, _, target_ref, _, ta, _ = data
    evidence = {**ta['evidence'], 'status': 'unresolved', 'landmark_digest': None}
    foreign = P.new_face('a'*64, [.27, .47, .37, .61], evidence)
    foreign['enabled'] = False; state['faces'][foreign['face_instance_id']] = foreign
    target, reference, facts = masks(data)
    assert not np.any(target[121:155, 70:93])
    assert facts['target']['protected_face_boxes'] == facts['reference']['protected_face_boxes'] == 2
    assert np.any(target > 0) and np.any(reference > 0)
    # A foreign photograph's box cannot reserve this photograph's face.
    foreign['asset_sha256'] = 'd'*64
    target_without_foreign, _, facts = masks(data)
    assert np.any(target_without_foreign[121:155, 70:93] > 0)
    assert facts['target']['protected_face_boxes'] == 1


def test_entire_measured_reference_oval_is_protected_even_with_semantic_holes_and_narrow_box():
    state = P.empty()
    target_ref, ta = add_face(state, 'overlap-target', center=(.35, .45), span=(.25, .32))
    reference_ref, ra = add_face(state, 'overlap-reference', center=(.62, .45), span=(.20, .28))
    # The retained rectangle alone does not cover the reference oval overlap.
    state['faces'][reference_ref['face_instance_id']]['box'] = [.7, .4, .78, .5]
    ra['face_skin'][:, :150] = 0
    state, assets = V.retain(state, {}, target_ref, reference_ref, ta, ra, confirmed=True)
    target, _, _ = V.geometry(state, assets, target_ref, ta, ra, (256, 256), byte_budget=BUDGET)
    xx = np.arange(256, dtype=np.float64)[None, :] + .5
    yy = np.arange(256, dtype=np.float64)[:, None] + .5
    reference_oval = ra['landmarks'][list(FACE.FACE_OVAL), :2].astype(np.float64)*256
    interior, distance = FACE._polygon_field(xx, yy, reference_oval)
    assert not np.any(target[interior | (distance <= np.sqrt(.5))])
    assert np.any(target > 0)


def test_soft_and_single_pixel_geometric_support_is_not_old_64_hard_sample_admission():
    data = list(retained()); data[4]['face_skin'][:] = 0; data[5]['face_skin'][:] = 0
    data[4]['face_skin'][135, 64] = .01
    data[5]['face_skin'][124, 190] = .01
    target, reference, facts = masks(data)
    assert np.count_nonzero(target) == np.count_nonzero(reference) == 1
    assert max(target.max(), reference.max()) <= .01
    assert facts['target']['source_window'][2:] == [1, 1]
    assert facts['reference']['source_window'][2:] == [1, 1]
    # This is intentionally NOT fit acceptance; Rust must reject weak evidence.
    assert facts['photometric_admission'] == 'rust-skin-reference-fit-only'


@pytest.mark.parametrize('side', [4, 5])
def test_empty_actual_support_refuses_instead_of_neutral_or_other_person_fallback(side):
    data = list(retained()); data[side]['face_skin'][:] = 0
    with pytest.raises(ValueError, match='no actual'): masks(data)


@pytest.mark.parametrize('shape', [(250, 256), (512, 256), (520, 520), (True, 256), (0, 0), (256,)])
def test_crops_wrong_aspect_enlargement_and_noncanonical_proxy_grids_refuse(shape):
    with pytest.raises(ValueError): masks(retained(), shape=shape)


def test_geometry_rebuilds_at_actual_full_source_grid_without_changing_observation_identity():
    preview = retained(); target_preview, _, _ = masks(preview)
    full = list(preview)
    full[4] = deepcopy(full[4]); full[5] = deepcopy(full[5])
    for analysis in full[4:]:
        analysis['face_skin'] = np.full((512, 512), .65, np.float32)
        analysis['excluded'] = np.zeros((512, 512), np.float32)
        analysis['skin'] = np.ones((512, 512), np.float32)
    target_full, reference_full, facts = masks(full, shape=(512, 512))
    assert target_full.shape == reference_full.shape == (512, 512)
    assert facts['target']['face_skin_observation']['producer_width'] == 128
    assert facts['source_dimensions'] == facts['render_dimensions'] == [512, 512]
    assert np.count_nonzero(target_full) > 3*np.count_nonzero(target_preview)


def test_budget_refuses_before_semantic_validation_or_anatomical_allocation():
    data = retained()
    with patch.object(SEM, 'check_analysis_fields', side_effect=AssertionError('semantic validation before admission')):
        with pytest.raises(ValueError, match='memory budget before allocation'): masks(data, byte_budget=0)
    baseline = V._FIXED_BYTES + 256*256*V._BYTES_PER_PIXEL
    with patch.object(FACE, 'selected_face_skin', side_effect=AssertionError('geometry before ROI admission')):
        with pytest.raises(ValueError, match='anatomical ROI'): masks(data, byte_budget=baseline)


def test_cancellation_never_returns_one_side_or_mutates_the_relation():
    data = retained(); before = deepcopy(data[0]); bank_before = deepcopy(data[1])
    with pytest.raises(InterruptedError): masks(data, cancelled=lambda: True)
    calls = 0
    def stop_during_second_support():
        nonlocal calls
        calls += 1
        return calls >= 4
    with pytest.raises(InterruptedError): masks(data, cancelled=stop_during_second_support)
    assert data[0] == before and data[1] == bank_before
    with pytest.raises(TypeError): masks(data, cancelled=True)
