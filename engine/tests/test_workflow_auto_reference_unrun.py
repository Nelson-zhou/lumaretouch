# SPDX-License-Identifier: GPL-3.0-or-later
"""SOURCE-AUTHORED / UNRUN. Owner contracts, NOT photographic acceptance."""
from copy import deepcopy
from types import SimpleNamespace
import pytest
from lumaretouch_engine import workflow_auto_reference as A
from lumaretouch_engine import workflow_auto_preset as H
from lumaretouch_engine import workflow_owner_protocol as P
from lumaretouch_engine import full_candidate_render as F


def preset():
    return {'modules': {A.RC.OP: {'version': 1, 'strength': 0.7,
        'reference': {'asset_id': 'a' * 64, 'render_sha256': 'b' * 64,
                      'source': {'sha256': 'c' * 64, 'width': 100, 'height': 100}}}}}


def test_reference_profile_is_exact_and_refuses_whole_mixed_presets():
    value = preset()
    assert H.support_reason(value) is None  # catalogue is not job authority
    assert H.support_reason(value, P.AUTOMATIC_REFERENCE_INTENT) is None
    assert H.support_reason(value, P.AUTOMATIC_INTENT)
    assert H.support_reason(value, P.AUTOMATIC_PORTRAIT_INTENT)
    for op in ('lnx.skin_finish.v1', 'lnx.exposure.v1'):
        mixed = deepcopy(value); mixed['modules'][op] = {}
        assert H.support_reason(mixed, P.AUTOMATIC_REFERENCE_INTENT) == 'reference_group_requires_reference_only_intent'
        assert op in mixed['modules']
    assert P.automatic_intent(P.AUTOMATIC_REFERENCE_INTENT) == P.AUTOMATIC_REFERENCE_INTENT
    for changed in ({**P.AUTOMATIC_REFERENCE_INTENT, 'reference_source_policy': 'silently_omit'},
                    {**P.AUTOMATIC_REFERENCE_INTENT, 'portrait_scope': 'all_verified_detected_faces'}):
        with pytest.raises(ValueError): P.automatic_intent(changed)


def fixture(monkeypatch):
    plan = object.__new__(A.TargetReferencePlan)
    plan.row = {'state': {'own': True}, 'undo': [], 'redo': [], 'path': '/own'}
    plan.engine = SimpleNamespace(_capture_state=lambda: plan.row['state'],
        _history_capture=lambda: {'history_before': True},
        _history_record=lambda *args, **kwargs: None)
    plan.load_id = 'loaded'
    plan.batch = SimpleNamespace(versions=SimpleNamespace(version=lambda row: SimpleNamespace(revision=4)))
    plan._row = lambda document: (2, plan.row)
    plan._fit = plan._assessment = None
    plan._fit_started = plan._committed = False
    plan._baseline = plan._live_baseline = A.fingerprint(plan.row['state'])
    plan._history = A.fingerprint(([], []))
    plan._people_baseline = A.fingerprint({})
    monkeypatch.setattr(A, 'people_context', lambda *args: {})
    monkeypatch.setattr(A.SOURCE, 'row_proof', lambda row: {'asset_sha256': 'd' * 64})
    target = {'document_id': 'target', 'revision': '4', 'load_id': 'loaded'}
    calls = []
    def inputs(group, document, value, frozen):
        calls.append(deepcopy(frozen))
        fit = {'own_fit': 'frozen'} if frozen is None else deepcopy(frozen)
        owned = {'before': {'render': {'source_proof': 'own'}}, 'after': {'own': True},
                 'history': 'same', 'context': 'same', 'reference_fit': fit}
        return owned, {}, {'candidate': True}, {}
    monkeypatch.setattr(A.reference, 'inputs', inputs)
    monkeypatch.setattr(F, 'render', lambda *args, **kwargs: None)
    return plan, target, calls


def test_one_fit_then_verify_only_through_canonical_commit(monkeypatch):
    plan, target, calls = fixture(monkeypatch)
    evidence = plan.assess(preset(), target)
    assert plan.assess(preset(), target) == evidence
    committed = []
    def commit(ops, modules, rows, policy, bad, **kwargs):
        assert plan._committed
        assert ops == [A.RC.OP] and rows[0]['_reference_prepared'] == {'own_fit': 'frozen'}
        assert rows[0]['index'] == 2 and rows[0]['_source_proof'] == 'own'
        assert policy == 'recheck' and bad == []
        committed.append(rows)
        return {'targets': [2], 'skipped': [], 'rejected_docs': [], 'batch_id': 'canonical'}
    plan.batch.commit = commit
    history = []
    plan.engine._history_record = lambda *args, **kwargs: history.append((args, kwargs))
    assert plan.commit(preset(), target, 'request', evidence)['success']
    assert calls[0] is None and all(value == {'own_fit': 'frozen'} for value in calls[1:])
    with pytest.raises(ValueError): plan.commit(preset(), target, 'request', evidence)
    assert len(committed) == 1
    assert history == [(('automatic-reference:request', {'history_before': True}), {'coalesce': False})]


def test_reference_alias_rejected_before_fit(monkeypatch):
    plan, target, calls = fixture(monkeypatch)
    monkeypatch.setattr(A.SOURCE, 'row_proof', lambda row: {'asset_sha256': 'c' * 64})
    with pytest.raises(ValueError, match='same_source_rejected'): plan.assess(preset(), target)
    assert not calls and not plan._fit_started
    plan.assert_unchanged()


def test_failed_correspondence_cannot_be_retried(monkeypatch):
    plan, target, calls = fixture(monkeypatch)
    def fail(*args): raise ValueError('insufficient actual correspondences')
    monkeypatch.setattr(A.reference, 'inputs', fail)
    with pytest.raises(ValueError, match='insufficient'): plan.assess(preset(), target)
    plan.assert_unchanged()
    with pytest.raises(ValueError, match='never refit'): plan.assess(preset(), target)


def test_no_effect_requires_recipe_history_and_people(monkeypatch):
    plan, target, calls = fixture(monkeypatch)
    plan.row['undo'].append({'changed': True})
    with pytest.raises(ValueError, match='outcome unknown'): plan.assert_unchanged(loaded=False)
    plan.row['undo'].clear()
    monkeypatch.setattr(A, 'people_context', lambda *args: {'foreign': True})
    with pytest.raises(ValueError, match='outcome unknown'): plan.assert_unchanged()


def test_commit_exception_is_claimed_not_replayable(monkeypatch):
    plan, target, calls = fixture(monkeypatch)
    evidence = plan.assess(preset(), target)
    def lost(*args, **kwargs): raise RuntimeError('lost original history outcome')
    plan.batch.commit = lost
    history = []
    plan.engine._history_record = lambda *args, **kwargs: history.append(args)
    with pytest.raises(RuntimeError): plan.commit(preset(), target, 'request', evidence)
    assert plan._committed and len(history) == 1
    with pytest.raises(ValueError): plan.commit(preset(), target, 'request', evidence)


def test_applied_verification_uses_document_capture_not_ephemeral_preset_dto(monkeypatch):
    plan, target, calls = fixture(monkeypatch)
    expected = {'after': {'render': {'source_proof': 'own', 'candidate_sha256': 'own',
                                   'people_sha256': 'same'},
                          'repair_sha256': 'repairs', 'snapshot_sha256': 'snapshot'}}
    plan._committed = True; plan._assessment = deepcopy(expected)
    plan.engine._people_preset_capture = lambda: pytest.fail('not the reference batch capture domain')
    monkeypatch.setattr(A.review, '_proof', lambda engine, row, state, actual_target:
                        (deepcopy(expected['after']), {}))
    assert plan.verify_applied(expected, target) == expected['after']
    monkeypatch.setattr(A.review, '_proof', lambda *args: ({**expected['after'], 'snapshot_sha256': 'changed'}, {}))
    with pytest.raises(ValueError, match='complete frozen candidate'):
        plan.verify_applied(expected, target)
