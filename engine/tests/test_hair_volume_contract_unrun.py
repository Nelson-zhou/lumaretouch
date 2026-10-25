# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN. Static-only authorization; synthetic contracts, not photos."""
from copy import deepcopy
import hashlib
from unittest import mock
import numpy as np
import pytest
from lumaretouch_engine import people_state as P
from lumaretouch_engine import hair_volume_state as S, hair_volume_support as A
from lumaretouch_engine import hair_volume_native as N, hair_volume_runtime as R
from lumaretouch_engine import hair_colour_evidence as SAVED


def fixture():
    source = {'sha256': 'a'*64, 'width': 1001, 'height': 1001}
    people = P.empty()
    face = {'face_instance_id': 'owner', 'asset_sha256': source['sha256'], 'analysis_revision': 0,
            'box': [.4, .45, .6, .7], 'manual': False, 'enabled': True, 'labels': {}, 'local_assets': {},
            'evidence': {'backend': 'mediapipe', 'detector_model_sha256': 'd'*64,
                         'semantic_model_sha256': A.MODEL_SHA256, 'landmark_digest': 'e'*64,
                         'status': 'verified', 'source_width': 1001, 'source_height': 1001,
                         'orientation': 'exif_normalized_once'}}
    people['faces']['owner'] = face
    regions = {
        'crown': {'x': [.25, .35, .65, .75], 'y': [.05, .15, .25, .35],
                  'contour': [[.35, .18], [.5, .18], [.65, .18]],
                  'hair_samples': [[.35, .23], [.5, .23], [.65, .23]],
                  'background_samples': [[.35, .08], [.5, .08], [.65, .08]]},
        'left': {'x': [.1, .15, .25, .3], 'y': [.25, .4, .6, .75],
                 'contour': [[.18, .4], [.18, .5], [.18, .6]],
                 'hair_samples': [[.23, .4], [.23, .5], [.23, .6]],
                 'background_samples': [[.12, .4], [.12, .5], [.12, .6]]},
        'right': {'x': [.7, .75, .85, .9], 'y': [.25, .4, .6, .75],
                  'contour': [[.82, .4], [.82, .5], [.82, .6]],
                  'hair_samples': [[.77, .4], [.77, .5], [.77, .6]],
                  'background_samples': [[.88, .4], [.88, .5], [.88, .6]]}}
    protection = {'ears': [[.31, .48, .39, .65], [.61, .48, .69, .65]],
                  'neck': [[.44, .71, .56, .85]], 'other_people': [],
                  'visible_anatomy_reviewed': True, 'whole_source_reviewed': True}
    weight = np.zeros((101, 101), np.float32)
    for part in regions.values():
        for x, y in part['hair_samples']:
            ix, iy = round(x*100), round(y*100); weight[iy-1:iy+2, ix-1:ix+2] = 1
    evidence = {'domain': 'source-normalized', 'source': source, 'model_sha256': A.MODEL_SHA256,
                'producer': 'mediapipe-six-class-confidence-gated-hair', 'weight': weight,
                'weight_sha256': hashlib.sha256(weight.tobytes()).hexdigest()}
    record = A.reviewed(people, P.face_ref(face), source, regions, protection, evidence, confirmed=True)
    state, bank = A.retain(people, {}, record)
    return state, bank, source, evidence, record


def test_exact_ids_independent_versions_and_original_directions():
    assert S.OPERATION_ID == 'lnx.hair_volume.v1'
    assert S.CONTROL_IDS == {'crown': 'control:PC-32472:2', 'sides': 'control:PC-32472:3'}
    value = S.neutral(); value['crown']['amount'] = -1
    value['sides'].update(linked=False, left=-.3, right=.7)
    assert S.vector(value) == [1., -1., -.3, .7]
    assert set(S.transferable(value)) == {'version', 'crown', 'sides'}
    value['sides']['linked'] = True
    with pytest.raises(ValueError): S.check(value)


@pytest.mark.parametrize('amount', [True, '1', float('nan'), float('inf'), -1.01, 1.01])
def test_invalid_scalar_is_not_clamped(amount):
    value = S.neutral(); value['crown']['amount'] = amount
    with pytest.raises(ValueError): S.check(value)


def test_same_people_graph_append_only_assets_and_exact_review():
    people, bank, source, evidence, record = fixture()
    ref = record['face_ref']; key = A.digest(record)
    assert people['faces']['owner']['local_assets'][A.KIND] == {
        'owner': ref, 'content_sha256': key, 'kind': A.KIND}
    assert A.resolve(people, bank, ref) == record
    detached = A.detach(people, ref)
    assert A.resolve(detached, bank, ref) is None
    assert key in bank
    wrong = deepcopy(record); wrong['row']['operation_id'] = 'lnx.head_size.v1'
    with pytest.raises(ValueError): A.check_record(wrong)
    wrong = deepcopy(record); wrong['row']['review']['method'] = 'explicit_source_review'
    with pytest.raises(ValueError): A.check_record(wrong)
    wrong = deepcopy(record); wrong['source']['sha256'] = 'b'*64
    with pytest.raises(ValueError): A.check_record(wrong)
    saved = {SAVED.identity(evidence): SAVED.encode(evidence)}
    assert A.validate_project(people, bank, saved, source_frame=source) == bank


def test_source_or_retained_disabled_foreign_face_change_requires_review():
    people, bank, source, _, record = fixture()
    foreign = deepcopy(people['faces']['owner'])
    foreign.update(face_instance_id='other', enabled=False, box=[.01, .8, .1, .9], local_assets={})
    people['faces']['other'] = foreign
    with pytest.raises(ValueError): A.resolve(people, bank, record['face_ref'])


def test_actual_hair_probes_not_an_all_image_or_foreign_evidence_shortcut():
    _, _, _, evidence, record = fixture()
    wrong = deepcopy(evidence); wrong['weight'] = np.zeros_like(evidence['weight'])
    wrong['weight_sha256'] = hashlib.sha256(wrong['weight'].tobytes()).hexdigest()
    with pytest.raises(ValueError): A.verify_evidence(record, wrong)
    wrong = deepcopy(evidence); wrong['source']['sha256'] = 'b'*64
    with pytest.raises(ValueError): A.verify_evidence(record, wrong)
    wrong = deepcopy(evidence); wrong['producer'] = 'face-box-as-hair'
    with pytest.raises(ValueError): A.verify_evidence(record, wrong)


def test_contour_pair_order_protected_review_and_clipping_fail_closed():
    _, _, source, _, record = fixture()
    raw = record['row']['regions']['crown']
    for mutate in (
        lambda p: p['hair_samples'].__setitem__(0, [.35, .17]),
        lambda p: p['background_samples'].pop(),
        lambda p: p['contour'].reverse(),
        lambda p: p['x'].__setitem__(0, 0.),
    ):
        wrong = deepcopy(raw); mutate(wrong)
        with pytest.raises(ValueError): A.patch(wrong, 'crown', source)
    with pytest.raises(ValueError): A.protection({**record['row']['protection'], 'whole_source_reviewed': False})


def test_active_region_cannot_borrow_other_region_and_neutral_needs_no_native():
    people, bank, source, _, record = fixture()
    value = S.neutral()
    with mock.patch.object(N, 'native', side_effect=AssertionError('native called')):
        assert R.prepare_fields(people, source['sha256'], (1001, 1001), recipes={'owner': value},
                                support_assets=bank, hair_evidence=None, source_frame=source,
                                byte_budget=1_048_576) == ()
    value['crown']['amount'] = 1
    wrong = deepcopy(record); wrong['row']['regions']['crown'] = None
    del wrong['row']['review']
    wrong['row']['review'] = {'method': 'explicit_source_hair_geometry_review',
                              'operation_id': S.OPERATION_ID, 'confirmed': True, 'review_key': A.digest(wrong)}
    with pytest.raises(ValueError): A.support_vector(wrong, value)


def test_known_missing_native_is_a_blocker_not_a_python_identity_warp():
    people, bank, source, evidence, _ = fixture()
    value = S.neutral(); value['crown']['amount'] = 1
    with mock.patch.object(N, 'native', side_effect=RuntimeError('not installed')):
        with pytest.raises(R.HairVolumeRefused, match='not installed'):
            R.prepare_fields(people, source['sha256'], (1001, 1001), recipes={'owner': value},
                             support_assets=bank, hair_evidence=evidence, source_frame=source,
                             byte_budget=1_048_576)
