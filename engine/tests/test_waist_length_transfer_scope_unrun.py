# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: scalar scope and target-owned waist dependency contracts.

Synthetic pose/face records exercise schema routing only. They are not model
outputs, source photographs, native numerical results or visual acceptance.
No product imports, test collection/execution or build ran while authoring.
"""
from copy import deepcopy
import pytest

from lumaretouch_engine import body_pose_state as B, body_pose_project as D
from lumaretouch_engine import waist_length_project as P, waist_length_state as S
from lumaretouch_engine import waist_length_scope as T, shoulder_shape_state as SHOULDER
from test_waist_length_support_unrun import fixture, synthetic_record, SOURCE


def state(amount=.2, **kwargs):
    bank, people, ref, data, source = fixture(amount=amount, **kwargs)
    return {D.KEY: P.pack(bank)}, people, ref, data, source


def test_only_version_and_amount_travel_and_all_target_support_is_retained():
    value, _, ref, _, _ = state()
    before = D.bank(value)
    T.install(value, {'version': 1, 'amount': -.75})
    after = D.bank(value)
    expected = B.set_recipe(before, ref, {'version': 1, 'amount': -.75}, operation_id=S.OP)
    assert after == expected
    assert after['support_assets'] == before['support_assets']
    assert B.target(after, ref)['association'] == B.target(before, ref)['association']
    assert T.params_of(value) == {'version': 1, 'amount': -.75}


@pytest.mark.parametrize('params', [
    {'version': 1, 'amount': True}, {'version': True, 'amount': 0},
    {'version': 1, 'amount': float('nan')}, {'version': 1, 'amount': float('inf')},
    {'version': 1, 'amount': 1.01}, {'version': 1, 'amount': -1.01},
    {'recipe': {'version': 1, 'amount': .5}},
    {'version': 1, 'amount': .5, 'support': {}},
    {'version': 1, 'amount': .5, 'associated_face_ref': None},
])
def test_non_scalar_and_noncanonical_parameter_shapes_refuse(params):
    with pytest.raises(ValueError): T.check_params(params)


def test_neutral_noop_preserves_exact_packed_body_bank():
    value, _, _, _, _ = state(amount=0)
    before = deepcopy(value)
    T.install(value, {'version': 1, 'amount': 0})
    assert value == before


@pytest.mark.parametrize('fault', ['disabled-body', 'disabled-operation', 'missing-operation',
                                  'missing-review', 'missing-association', 'missing-support'])
def test_zero_cannot_create_or_enable_an_unreviewed_target(fault):
    value, _, ref, _, _ = state()
    bank = D.bank(value); row = B.target(bank, ref); item = row['operations'][S.OP]
    if fault == 'disabled-body': row['enabled'] = False
    elif fault == 'disabled-operation': item['enabled'] = False
    elif fault == 'missing-operation': del row['operations'][S.OP]
    elif fault == 'missing-review': item['review'] = None
    elif fault == 'missing-association': row['association'] = None
    else: item.update(review=None, support_sha256=None)
    value[D.KEY] = P.pack(bank); before = deepcopy(value)
    with pytest.raises(ValueError): T.install(value, {'version': 1, 'amount': 0})
    assert value == before


def add_second(value, *, enabled=True, other_source=False):
    bank = D.bank(value)
    record = synthetic_record(source={**SOURCE, 'sha256': 'f'*64} if other_source else SOURCE)
    frame = record['source']
    bank = B.add_run(bank, {'source': frame, 'records': [record], 'detector_limit': 4,
        'limit_reached': False, 'census_complete': False}, initial_operations=(S.OP,))
    B.target(bank, record['body_ref'])['enabled'] = enabled
    value[D.KEY] = P.pack(bank)
    return record['body_ref']


def test_params_of_refuses_ambiguous_body_instead_of_first_list_item():
    value, _, _, _, _ = state()
    add_second(value)
    with pytest.raises(ValueError): T.params_of(value)
    with pytest.raises(ValueError): T.install(value, {'version': 1, 'amount': .6})


def test_disabled_foreign_source_still_refuses_multi_source_bank():
    value, _, _, _, _ = state()
    add_second(value, enabled=False, other_source=True)
    with pytest.raises(ValueError): T.params_of(value)


def test_disabled_same_source_body_stays_retained_for_full_renderer_protection():
    value, _, _, _, _ = state()
    second = add_second(value, enabled=False)
    before = deepcopy(B.target(D.bank(value), second))
    T.install(value, {'version': 1, 'amount': .5})
    assert B.target(D.bank(value), second) == before


def test_restore_only_scalar_preserves_sibling_operation_and_monotonic_revision():
    prior, _, ref, _, _ = state()
    current = deepcopy(prior)
    T.install(current, {'version': 1, 'amount': .8})
    bank = B.set_recipe(D.bank(current), ref, SHOULDER.neutral(), operation_id=SHOULDER.OPERATION_ID)
    current[D.KEY] = P.pack(bank)
    revision = bank['revision']; sibling = deepcopy(B.target(bank, ref)['operations'][SHOULDER.OPERATION_ID])
    T.restore(current, prior)
    restored = D.bank(current)
    assert T.params_of(current) == T.params_of(prior)
    assert restored['revision'] == revision + 1
    assert B.target(restored, ref)['operations'][SHOULDER.OPERATION_ID] == sibling
    assert restored['support_assets'] == bank['support_assets']


def test_scoped_history_key_ignores_only_overall_mutation_revision():
    before, _, ref, _, _ = state()
    current = deepcopy(before)
    original_key = T.undo_key(current); original_bank = T.bank_sha256(current)
    T.install(current, {'version': 1, 'amount': -.7}); T.restore(current, before)
    assert T.undo_key(current) == original_key
    assert T.bank_sha256(current) != original_bank
    bank = B.set_recipe(D.bank(current), ref, SHOULDER.neutral(), operation_id=SHOULDER.OPERATION_ID)
    current[D.KEY] = P.pack(bank)
    assert T.undo_key(current) != original_key  # An unrelated body edit is a conflict, not overwritten.


def test_restore_refuses_foreign_body_even_when_source_and_scalar_match():
    current, _, _, _, _ = state()
    previous, _, _, _, _ = state()
    frozen = deepcopy(current)
    with pytest.raises(ValueError): T.restore(current, previous)
    assert current == frozen


@pytest.mark.parametrize('field', S.WAIST_MARKERS)
def test_a_marker_cannot_be_omitted_from_target_support(field):
    value, _, ref, _, _ = state()
    bank = D.bank(value)
    support = B.support(bank, ref, S.OP)
    del support['data'][field]
    # Even a producer with a recomputed content hash cannot turn three manual
    # points into independently reviewed four-point waist evidence.
    from lumaretouch_engine import body_pose_evidence as E
    support['data_sha256'] = E.content_digest(support['data'])
    key = E.content_digest(support)
    bank['support_assets'][key] = support
    item = B.operation(bank, ref, S.OP)
    item['support_sha256'] = item['review']['support_sha256'] = key
    value[D.KEY] = {'version': 2, 'state': bank, 'content_sha256': E.content_digest(bank)}
    frozen = deepcopy(value)
    with pytest.raises(ValueError): T.install(value, {'version': 1, 'amount': 0})
    assert value == frozen


def test_torso_support_never_satisfies_independent_waist_admission():
    from test_torso_length_support_unrun import fixture as torso_fixture
    from lumaretouch_engine import torso_length_state as TORSO
    bank, _, ref, _, _ = torso_fixture()
    bank = B.set_recipe(bank, ref, S.neutral(), operation_id=S.OP)
    value = {D.KEY: P.pack(bank)}
    original = deepcopy(value)
    assert B.operation(bank, ref, TORSO.OP)['review'] is not None
    with pytest.raises(ValueError): T.install(value, {'version': 1, 'amount': 0})
    assert value == original


def test_reanalysis_preserves_scalar_but_cannot_reuse_old_markers_or_identity():
    value, _, ref, _, _ = state()
    measured = synthetic_record()
    bank = B.reanalyse(D.bank(value), ref, measured, user_confirmed=True)
    value[D.KEY] = P.pack(bank)
    frozen = deepcopy(value)
    with pytest.raises(ValueError): T.params_of(value)
    with pytest.raises(ValueError): T.install(value, {'version': 1, 'amount': .1})
    assert value == frozen


def test_changed_reviewed_markers_conflict_with_undo_without_copying_old_support():
    before, _, ref, data, _ = state()
    current = deepcopy(before); T.install(current, {'version': 1, 'amount': .7})
    data['waist_upper_left'][1] += .001
    data['waist_upper_right'][1] += .001
    bank = B.set_support(D.bank(current), ref, S.OP, S.SUPPORT_KIND, data)
    bank = B.review(bank, ref, operation_id=S.OP,
        points_sha256=B.target(bank, ref)['record']['points_sha256'],
        visible_anchors=list(S.REQUIRED_ANCHORS), ownership_confirmed=True,
        support_sha256=B.operation(bank, ref, S.OP)['support_sha256'])
    current[D.KEY] = P.pack(bank); frozen = deepcopy(current)
    assert T.undo_key(current) != T.undo_key(before)
    with pytest.raises(ValueError): T.restore(current, before)
    assert current == frozen


@pytest.mark.parametrize('extra', [
    {'waist_upper_left': [.4, .5]}, {'body_ref': {}}, {'associated_face_ref': {}},
    {'support_assets': {}}, {'source': {}}, {'region_mask': {}},
    {'ownership_confirmed': True}, {'model_output': {}},
])
def test_portable_payload_never_carries_target_evidence(extra):
    with pytest.raises(ValueError): T.check_params({'version': 1, 'amount': .5, **extra})
