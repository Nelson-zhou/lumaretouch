# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: v2 scalar portability and dedicated-review boundaries.

Synthetic graph evidence specifies routing/ownership only. No imports, test
collection, native execution, inference or photographic acceptance was run.
"""
from copy import deepcopy
import json
import pytest
from lumaretouch_engine import eye_bag_preserve_scope as C, eye_bag_preserve_state as S
from lumaretouch_engine import people_state as P, people_algorithms as A, scope as SC
from lumaretouch_engine import people_transfer_adapter as T
from lumaretouch_engine.people_resolver import resolve

ASSET = 'a' * 64
FACE = 'eye-bag-test-face'


def graph():
    evidence = {'backend': 'manual_region', 'detector_model_sha256': None,
        'semantic_model_sha256': None, 'landmark_digest': None, 'status': 'unresolved',
        'source_width': 640, 'source_height': 480, 'orientation': 'exif_normalized_once'}
    state = P.empty(); face = P.new_face(ASSET, [.1, .1, .8, .9], evidence, manual=True)
    face['face_instance_id'] = FACE; state['faces'][FACE] = face
    return P.check(state)


def params(amount=0., preserve=1.):
    return {'recipe': {'version': 2, 'amount': amount, 'preserve': preserve}}


def capture():
    state = graph(); ref = P.face_ref(state['faces'][FACE])
    return {C.FIELD: S.neutral(), C.TARGET: ref, C.REQUESTED: False,
        C.OWNER: {'document': {'document_id': 'target', 'epoch': 'workspace', 'revision': 2},
            'people_scope': 'project', 'state_revision': state['revision'],
            'association_revision': state['association_revision'], 'graph_sha256': 'd' * 64,
            'source_proof': {'asset_sha256': ASSET, 'creative_source': None, 'original_sha256': ASSET}}}


def test_distinct_operation_and_archive_only_catalogue():
    assert S.OP == 'lnx.eye_bags.v2' and C.OP != A.ENHANCE
    assert A.defaults()[C.OP] == {'/amount': 0., '/preserve': 1.}
    assert SC.MODULES[C.OP]['read'] is C.params_of
    assert SC.MODULES[C.OP]['write'] is C.install
    assert SC.MODULES[C.OP]['state_fields'] == (C.FIELD,)
    assert C.REVIEW_REQUIRED in SC.MODULES[C.OP]['why_not']


@pytest.mark.parametrize('amount,preserve', [(0., 0.), (0., 1.), (.3, .75), (1., 1.)])
def test_portable_roundtrip_carries_only_two_scalar_leaves(amount, preserve):
    portable = {'schema': SC.PRESET_SCHEMA, 'id': 'reviewed-bag', 'name': 'Eye bag',
        'kind': 'portrait', 'modules': {C.OP: params(amount, preserve)}}
    loaded = SC.validate_preset(json.loads(SC.dump_preset(portable)))
    assert loaded['modules'][C.OP] == params(amount, preserve)
    assert set(A.leaves(loaded['modules'][C.OP]['recipe'])) == {'/amount', '/preserve'}


@pytest.mark.parametrize('key', ['source', 'face_ref', 'eyes', 'support_assets', 'mask',
    'landmarks', 'repair_pixels', 'review_id', 'presented', 'automatic_anatomy'])
def test_portable_params_reject_source_support_and_forged_review(key):
    with pytest.raises(ValueError): C.check_params({**params(), key: {}})
    raw = params(); raw['recipe'][key] = {}
    with pytest.raises(ValueError): C.check_params(raw)


@pytest.mark.parametrize('preserve', [0., .4, 1.])
def test_dormant_install_needs_no_analysis_native_or_support(preserve):
    state = capture(); before = deepcopy(state)
    C.install(state, params(0., preserve))
    assert state[C.FIELD] == params(0., preserve)['recipe']
    assert state[C.REQUESTED] is True
    assert state[C.TARGET] == before[C.TARGET] and state[C.OWNER] == before[C.OWNER]
    assert not S.active(state[C.FIELD])


@pytest.mark.parametrize('amount,preserve', [(.1, 0.), (.1, 1.), (1., 1.)])
def test_active_generic_preset_refuses_even_claimed_target_support(amount, preserve):
    state = {**capture(), 'eye_bag_ridge_visibility': {'reviewed': True},
        '_eye_bag_supported': True, '_eye_bag_native_available': True}
    before = deepcopy(state)
    with pytest.raises(ValueError, match='完整前后结果'): C.install(state, params(amount, preserve))
    assert state == before


def test_legacy_intent_is_not_reinterpreted_or_cleared():
    state = graph(); state = P.set_override(state, 'face', FACE, A.ENHANCE, '/eye_bags', .4)
    state = P.set_override(state, 'face', FACE, C.OP, '/preserve', .2)
    recipes = A.recipes(resolve(state, FACE, A.defaults()))
    assert recipes[A.ENHANCE]['eye_bags'] == .4 and recipes[C.OP] == params(0., .2)['recipe']
    A.validate_compatibility(recipes)
    before = deepcopy(recipes); recipes[C.OP]['amount'] = .3
    with pytest.raises(ValueError, match='mutually exclusive'): A.validate_compatibility(recipes)
    assert recipes[A.ENHANCE] == before[A.ENHANCE]


@pytest.mark.parametrize('starting,leaves,refused', [
    (0., [('/amount', .3)], True),
    (.3, [('/preserve', .2)], True),
    (.3, [('/amount', 0.), ('/preserve', .2)], False),
    (0., [('/preserve', .2)], False),
])
def test_batch_target_recipe_checked_without_copying_support(starting, leaves, refused):
    state = graph(); state = P.set_override(state, 'face', FACE, C.OP, '/amount', starting)
    before = deepcopy(state); ref = P.face_ref(state['faces'][FACE])
    payload = {'target_refs': [ref], 'parameters': [
        {'operation_id': C.OP, 'parameter_path': path, 'value': value} for path, value in leaves]}
    if refused:
        with pytest.raises(ValueError, match='完整前后结果'): T._require_reviewed_eye_bag_transfer(payload, state)
    else:
        T._require_reviewed_eye_bag_transfer(payload, state)
    assert state == before


def test_unrelated_batch_does_not_reauthorize_or_drop_existing_active_recipe():
    state = graph(); state = P.set_override(state, 'face', FACE, C.OP, '/amount', .3)
    before = deepcopy(state)
    T._require_reviewed_eye_bag_transfer({'target_refs': [P.face_ref(state['faces'][FACE])],
        'parameters': [{'operation_id': A.ENHANCE, 'parameter_path': '/sclera', 'value': .2}]}, state)
    assert state == before
