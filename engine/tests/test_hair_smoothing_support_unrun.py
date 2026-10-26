# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN independent support and persistence fixtures.

Synthetic source/semantic vectors are not photographic evidence. No product
imports, native execution, tests, inference, builds or typechecks ran on authoring.
"""
from copy import deepcopy
from hashlib import sha256
from unittest.mock import patch
import numpy as np
import pytest
from lumaretouch_engine import people_state as P, hair_colour_assets as H, hair_colour_evidence as E
from lumaretouch_engine import hair_smoothing_state as S, hair_smoothing_support as C
from lumaretouch_engine import hair_smoothing_project as PROJECT, hair_smoothing_layer as L


def mask(name='owned', *, protect=False):
    return {'version': 1, 'domain': 'source-normalized', 'objects': [{
        'id': name, 'name': name, 'enabled': True, 'operation': 'add', 'kind': 'brush',
        'opacity': 1., 'feather': 0., 'points': [[.5, .5]], 'axes': [[.4, 0.], [0., .4]]}]}


def fixture():
    source = {'sha256': 'a'*64, 'width': 64, 'height': 64}
    evidence = {'backend': 'mediapipe', 'detector_model_sha256': 'b'*64,
        'semantic_model_sha256': H.MODEL_SHA256, 'landmark_digest': 'c'*64,
        'status': 'verified', 'source_width': 64, 'source_height': 64, 'orientation': 'exif_normalized_once'}
    face = P.new_face(source['sha256'], [.2, .2, .8, .8], evidence)
    state = P.empty(); state['faces'][face['face_instance_id']] = face; ref = P.face_ref(face)
    weight = np.ones((64, 64), np.float32); weight.setflags(write=False)
    semantic = {'domain': 'source-normalized', 'source': source, 'model_sha256': H.MODEL_SHA256,
        'producer': 'mediapipe-six-class-confidence-gated-hair', 'weight': weight,
        'weight_sha256': sha256(weight.tobytes()).hexdigest()}
    owned = H.reviewed(ref, source, mask(), H.MODEL_SHA256, evidence_sha=E.identity(semantic), confirmed=True)
    state, hair = H.retain(state, {}, owned)
    proof = {'version': 1, 'source': source, 'source_proof': {'asset_sha256': source['sha256'],
        'original_sha256': source['sha256'], 'creative_source': None}, 'input_sha256': 'd'*64,
        'repair_sha256': 'e'*64, 'encoding': 'encoded-srgb-f32-v1', 'source_bits': 16,
        'orientation': 'exif_normalized_once', 'stage': 'immutable-source'}
    review = {'version': 1, 'domain': 'source-normalized', 'target_recipe': mask('target'),
        'context_recipe': mask('context'), 'protect_recipe': H.empty_mask(), 'texture_scale': 2/64,
        'visible_hair_reviewed': True, 'protections_reviewed': True, 'ownership_confirmed': True}
    return state, {}, ref, hair, semantic, proof, review


def retained():
    state, assets, ref, hair, semantic, proof, review = fixture()
    state, assets = C.retain(state, assets, ref, hair, review, proof,
                            C.retained_faces_digest(state, ref['asset_sha256'], hair))
    return state, assets, ref, hair, semantic, proof, review


def test_control_leaf_is_independent_not_skin_or_strand_alias():
    assert S.OP == 'lnx.hair_smoothing.v1' and S.CONTROL_ID == 'control:PC-32472:8'
    assert S.KIND == 'hair_smoothing_visibility'
    assert S.neutral() == {'version': 1, 'amount': 0.}
    assert S.portable({'version': 1, 'amount': .4}) == {'version': 1, 'amount': .4}


@pytest.mark.parametrize('amount', [True, False, -1, 1.001, float('nan'), float('inf'), 10**400, '.4'])
def test_amount_never_coerces_or_clamps(amount):
    with pytest.raises(ValueError): S.check({'version': 1, 'amount': amount})


def test_neutral_layer_does_not_read_source_or_ownership():
    with patch.object(C, 'resolve', side_effect=AssertionError):
        assert L.prepare(None, None, S.neutral(), people_state=None, assets=None,
            hair_assets=None, hair_evidence=None, full_source=None, byte_budget=0) == []
        assert L.prepare_review(None, None, S.neutral(), people_state=None, assets=None,
            hair_assets=None, hair_evidence=None, full_source=None, byte_budget=0) == ([], None)


@pytest.mark.parametrize('key', ['visible_hair_reviewed', 'protections_reviewed', 'ownership_confirmed'])
def test_each_independent_acknowledgement_is_mandatory(key):
    *_, review = fixture(); review[key] = False
    with pytest.raises(ValueError): C.check_review(review)


@pytest.mark.parametrize('scale', [True, 0, -1, float('nan'), .9/64, 8.01/64])
def test_native_observed_scale_not_proxy_or_clamped(scale):
    *_, proof, review = fixture(); review['texture_scale'] = scale
    with pytest.raises(ValueError): C.check_review(review, source=proof['source'])


@pytest.mark.parametrize('mutation', [{'opacity': .5}, {'feather': 1}, {'enabled': False}, {'operation': 'subtract'}])
def test_hard_protection_cannot_be_softened(mutation):
    *_, review = fixture(); review['protect_recipe'] = mask('hard', protect=True)
    review['protect_recipe']['objects'][0].update(mutation)
    with pytest.raises(ValueError): C.check_review(review)


def test_retained_envelope_and_detach_do_not_delete_historical_bytes():
    state, assets, ref, hair, *_ = retained(); before = deepcopy(assets)
    record, key = C.resolve(state, assets, ref, hair)
    assert set(record) == {'version', 'face_ref', 'source', 'row'}
    assert record['row']['target'] == S.KIND
    assert C.KIND not in C.detach(state, ref)['faces'][ref['face_instance_id']]['local_assets']
    assert assets == before and assets[key] == record


def test_colour_recovery_only_asset_edit_does_not_invalidate_ownership():
    state, assets, ref, hair, *_ = retained()
    current = H.resolve(state, hair, ref); changed = deepcopy(current); changed['recovery'] = mask('colour-only-recovery')
    state, hair = H.retain(state, hair, changed)
    assert C.resolve(state, assets, ref, hair) is not None


def test_all_source_faces_including_disabled_manual_unresolved_change_retained_digest():
    state, assets, ref, hair, *_ = retained(); old = C.retained_faces_digest(state, ref['asset_sha256'], hair)
    other = P.new_face(ref['asset_sha256'], [.01, .01, .1, .1], {
        'backend': 'manual', 'detector_model_sha256': None, 'semantic_model_sha256': None,
        'landmark_digest': None, 'status': 'unresolved', 'source_width': 64, 'source_height': 64,
        'orientation': 'exif_normalized_once'}, manual=True)
    other['enabled'] = False; state['faces'][other['face_instance_id']] = other
    assert C.retained_faces_digest(state, ref['asset_sha256'], hair) != old
    with pytest.raises(ValueError, match='Retained source people'): C.resolve(state, assets, ref, hair)


def test_disabled_competing_claim_cannot_be_settled_by_face_order():
    state, assets, ref, hair, semantic, proof, review = fixture()
    other = deepcopy(state['faces'][ref['face_instance_id']]); other['face_instance_id'] = 'other-owner'
    other['enabled'] = False; other['local_assets'] = {}; state['faces']['other-owner'] = other
    claim = H.reviewed(P.face_ref(other), proof['source'], mask('second'), H.MODEL_SHA256,
                       evidence_sha=E.identity(semantic), confirmed=True)
    state, hair = H.retain(state, hair, claim)
    state, assets = C.retain(state, assets, ref, hair, review, proof, C.retained_faces_digest(state, ref['asset_sha256'], hair))
    with patch.object(C.M, 'raster', return_value=np.full((64, 64), 255, np.uint8)):
        with pytest.raises(ValueError, match='overlaps'): C.raster(state, assets, ref, hair, semantic, (64,64), byte_budget=256*1024**2)


def test_original_source_and_exact_repair_proof_cannot_be_relabelled_derived():
    *_, proof, _ = fixture(); proof['source_proof']['creative_source'] = deepcopy(proof['source'])
    with pytest.raises(ValueError, match='derived'): C.check_source_proof(proof, proof['source'])


def test_nonzero_transfer_refuses_but_exact_zero_needs_no_donor_support():
    state, _, ref, *_ = fixture()
    nonzero = P.set_override(state, 'face', ref['face_instance_id'], S.OP, '/amount', .5)
    with pytest.raises(ValueError): PROJECT.require_unreviewed_transition(state, nonzero)
    zero = P.set_override(nonzero, 'face', ref['face_instance_id'], S.OP, '/amount', 0.)
    assert PROJECT.require_unreviewed_transition(nonzero, zero) == zero


def test_project_history_pins_nearest_hair_support_and_actual_semantics():
    state, assets, ref, hair, semantic, *_ = retained()
    root = {'people_graph': state, 'people_support_assets': assets, 'hair_colour_assets': hair,
            'hair_colour_evidence': {E.identity(semantic): E.encode(semantic)}}
    PROJECT.validate_project(root)
    root['private_document'] = {'people_graph': state, 'people_support_assets': {},
                                'hair_colour_assets': {}, 'hair_colour_evidence': {}}
    with pytest.raises(ValueError): PROJECT.validate_project(root)
