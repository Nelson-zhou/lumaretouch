# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: narrow derived preset policy, not image acceptance.

Tiny canonical assets exercise source checks. Synthetic captured admission
metadata is not inference, actual anatomy review or production render evidence.
No product imports or tests were executed while authoring this fixture.
"""
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from lumaretouch_engine import collarbone_derived_preset as PRESET
from lumaretouch_engine import collarbone_scope as C
from lumaretouch_engine import creative_derived_source as SOURCE
from lumaretouch_engine import creative_derived_transfer as GENERAL
from lumaretouch_engine import scope as SC
from lumaretouch_engine.creative_document_assets import make_asset
from lumaretouch_engine.creative_transfer_host import require_route
from lumaretouch_engine.repair_record import RepairOp

ROOT = Path(__file__).resolve().parents[1] / 'src/lumaretouch_engine'


def target(*, colour=.25, alpha=1.):
    pixels = np.full((2, 2, 4), colour, dtype='<f4'); pixels[:, :, 3] = alpha
    base = make_asset('rgba', 2, 2, pixels.tobytes())
    source = {'sha256': base['id'][7:], 'width': 2, 'height': 2}
    proof = {'asset_sha256': source['sha256'], 'creative_source': source,
             'original_sha256': 'a'*64}
    ref = {'asset_sha256': source['sha256'], 'face_instance_id': 'fixture-face', 'analysis_revision': 1}
    owner = {'document': {'document_id': 'fixture-doc', 'epoch': 'fixture-epoch', 'revision': 2},
             'people_scope': 'project', 'state_revision': 3, 'association_revision': 0,
             'graph_sha256': 'b'*64, 'source_proof': proof}
    return {'_creative_base': base, C.FIELD: C.S.neutral(), C.TARGET: ref,
            C.OWNER: owner, C.REQUESTED: False, '_collarbone_supported': True,
            '_collarbone_native_available': True, '_repair_ops': [], '_redo_ops': [],
            '_precompute': None, '_unselected_buffer': object()}


def modules(amount=.4):
    return {C.OP: {'recipe': {'version': 1, 'amount': amount}}}


def test_only_intent_changes_and_runtime_buffers_keep_identity():
    before = target(); after = PRESET.candidate(before, modules())
    assert after is not before and before[C.FIELD] == C.S.neutral()
    assert after[C.FIELD] == modules()[C.OP]['recipe'] and after[C.REQUESTED] is True
    assert set(after) == set(before)
    for key in before.keys() - {C.FIELD, C.REQUESTED}:
        assert after[key] is before[key]
    assert PRESET.require_candidate(before, after, modules()) is after


def test_mixed_global_scalar_preserves_shared_exposure_subfields():
    before = target(); before['_exposure'] = (0., .1, .2, .3, .4, .5, .6)
    mixed = {**modules(), SC.OP_EXPOSURE: {'ev': .7}}
    after = PRESET.candidate(before, mixed)
    assert after['_exposure'] == (.7, .1, .2, .3, .4, .5, .6)
    assert PRESET.require_candidate(before, after, mixed) is after
    after['_exposure'] = (.7, .9, .2, .3, .4, .5, .6)
    with pytest.raises(ValueError): PRESET.require_candidate(before, after, mixed)


@pytest.mark.parametrize('key', ['_unselected_buffer', '_precompute', '_repair_ops', C.TARGET, C.OWNER])
def test_candidate_cannot_smuggle_unselected_changes(key):
    before = target(); after = PRESET.candidate(before, modules())
    after[key] = object()
    with pytest.raises((ValueError, TypeError, AttributeError)):
        PRESET.require_candidate(before, after, modules())


@pytest.mark.parametrize('colour,alpha', [(.25, .5), (1.5, 1.)])
def test_real_canonical_alpha_and_hdr_refuse_without_clipping(colour, alpha):
    state = target(colour=colour, alpha=alpha)
    with pytest.raises(ValueError, match='SDR'):
        PRESET.require_modules(state, modules())


@pytest.mark.parametrize('change', ['owner_asset', 'owner_extent', 'face', 'original_owner', 'missing_owner'])
def test_owner_and_face_must_name_actual_effective_source(change):
    state = target(); proof = state[C.OWNER]['source_proof']
    if change == 'owner_asset':
        proof['asset_sha256'] = proof['creative_source']['sha256'] = 'c'*64
        state[C.TARGET]['asset_sha256'] = 'c'*64
    elif change == 'owner_extent': proof['creative_source']['width'] = 3
    elif change == 'face': state[C.TARGET]['asset_sha256'] = 'c'*64
    elif change == 'original_owner':
        proof['creative_source'] = None; proof['asset_sha256'] = proof['original_sha256']
        state[C.TARGET]['asset_sha256'] = proof['asset_sha256']
    else: state[C.OWNER] = None
    with pytest.raises(ValueError): PRESET.require_modules(state, modules())


@pytest.mark.parametrize('kind', ['missing_binding', 'foreign_source', 'wrong_mask_extent'])
def test_retained_precompute_cannot_be_relabelled(kind):
    state = target(); binding = SOURCE.binding(state)
    proof = {**binding, 'proxy_width': 2, 'proxy_height': 2, 'proxy_sha256': 'd'*64}
    pc = SimpleNamespace(input_source_binding=proof, masks={})
    if kind == 'missing_binding': pc.input_source_binding = None
    elif kind == 'foreign_source': proof['sha256'] = 'e'*64
    else: pc.masks['skin'] = np.ones((3, 2), dtype=np.float32)
    state['_precompute'] = pc
    with pytest.raises(ValueError): PRESET.require_modules(state, modules())


@pytest.mark.parametrize('stack', ['_repair_ops', '_redo_ops'])
def test_original_bound_repair_cannot_enter_derived_active_or_redo_stack(stack):
    state = target()
    state[stack] = [RepairOp(1, np.ones((2, 2), dtype=np.uint8))]
    with pytest.raises(ValueError, match='another immutable source'):
        PRESET.require_modules(state, modules())


def test_ambiguous_repair_alias_is_not_silently_ignored():
    state = target(); state['repair_ops'] = []
    with pytest.raises(ValueError, match='ambiguous'):
        PRESET.require_modules(state, modules())


def test_frozen_source_and_dormant_related_sources_cannot_rebind():
    state = target(); other = target(colour=.35)
    with pytest.raises(ValueError):
        PRESET.require_modules(state, modules(), other[C.OWNER]['source_proof'])
    with pytest.raises(ValueError):
        PRESET.require_modules(state, modules(), related_states=(other,))
    original = {**state, '_creative_base': None}
    with pytest.raises(ValueError):
        PRESET.require_modules(original, modules(), state[C.OWNER]['source_proof'])


@pytest.mark.parametrize('key', ['_collarbone_supported', '_collarbone_native_available'])
def test_active_intent_requires_existing_independent_admission(key):
    state = target(); state[key] = False
    with pytest.raises(ValueError): PRESET.require_modules(state, modules())
    # Neutral intent is recovery, not permission to invent anatomy support.
    assert PRESET.require_modules(state, modules(0.)) == modules(0.)


def test_generic_transfer_and_install_remain_closed_even_for_neutral():
    state = target()
    assert C.OP not in SC.DERIVED_PARAMETER_OPS
    with pytest.raises(ValueError): GENERAL.require_modules(state, modules(0.))
    with pytest.raises(ValueError): C.install(state, modules(0.)[C.OP])
    with pytest.raises(ValueError):
        PRESET.require_modules(state, {**modules(), 'lnx.not-admitted.v1': {}})


def test_original_behavior_uses_existing_candidate_and_preserves_modules():
    state = target(); state['_creative_base'] = None
    proof = state[C.OWNER]['source_proof']; proof['creative_source'] = None
    proof['asset_sha256'] = proof['original_sha256']
    state[C.TARGET]['asset_sha256'] = proof['asset_sha256']
    given = modules()
    assert PRESET.require_modules(state, given) is given
    after = PRESET.candidate(state, given)
    assert after[C.FIELD] == given[C.OP]['recipe']
    assert PRESET.require_candidate(state, after, given) is after


def test_only_exact_review_explicitly_selects_derived_planner_admission():
    planner = (ROOT / 'people_scope.py').read_text()
    review = (ROOT / 'collarbone_preset_review.py').read_text()
    assert 'require_active=True,reviewed_collarbone=False' in planner
    assert "if reviewed_collarbone and current.get('_creative_base') is not None:" in planner
    assert "COLLARBONE.install(dict(current),{'recipe':collarbone_recipe})" in planner
    assert 'reviewed_collarbone=True' in review
    legacy = planner[planner.index('def replay_preset('):]
    assert 'reviewed_collarbone=True' not in legacy


def test_exact_read_route_available_but_unknown_actions_still_refuse():
    request = {'cmd': 'preset', 'action': 'collarbone_visual', 'request_id': 'image-read',
               'id': 'fixture-preset', 'document_id': 'fixture-doc', 'revision': '2',
               'side': 'before', 'sha256': 'f'*64, 'preflight_token': 'fixture-token'}
    require_route('preset', request)
    for bad in ({'cmd': 'preset', 'action': 'collarbone_visual'},
                {**request, 'side': 'unknown'}, {**request, 'recipe': modules()}):
        with pytest.raises(ValueError): require_route('preset', bad)
    with pytest.raises(ValueError):
        require_route('preset', {'cmd': 'preset', 'action': 'unreviewed_collarbone_apply'})
    controller = (ROOT / 'preset_controller.py').read_text()
    assert "if action == 'collarbone_visual' and not correlated" in controller
    assert 'evidence = retrieve(self,p)' in controller


def test_review_and_apply_share_specialized_candidate_not_generic_install():
    for name in ('preset_controller.py', 'local_grade_preset_review.py'):
        text = (ROOT / name).read_text()
        assert 'collarbone_derived_preset' in text
        assert 'OA.candidate(' not in text
