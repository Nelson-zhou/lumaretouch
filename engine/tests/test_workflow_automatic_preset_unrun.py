"""Authored UNRUN fixtures: automatic intent is not an image-review receipt.

No fixture was executed during source development. Real dispatcher, history,
save, export, interruption and photographic acceptance remain for local QA.
"""
from copy import deepcopy
from contextlib import nullcontext
from hashlib import sha256
from types import SimpleNamespace
import pytest
from lumaretouch_engine import workflow_auto_preset as A
from lumaretouch_engine import workflow_owner_protocol as P
from lumaretouch_engine.workflow_owner_host import WorkflowOwner


def graph():
    nodes = [
        {'id': 'source', 'error_policy': 'stop', 'operation': {'kind': 'directory_source',
            'root': '/source', 'recursive': False, 'include_existing': True,
            'extensions': ['jpg'], 'settle_ms': 500}},
        {'id': 'import', 'error_policy': 'stop', 'operation': {'kind': 'managed_import',
            'project_id': 'project', 'project_path': '/project.lrt', 'managed_root': '/managed'}},
        {'id': 'auto', 'error_policy': 'skip', 'operation': {'kind': 'automatic_preset',
            'preset_id': 'scalar', 'preset_sha256': 'a' * 64, 'when_all_labels': [],
            'intent': deepcopy(P.AUTOMATIC_INTENT)}},
        {'id': 'export', 'error_policy': 'stop', 'operation': {'kind': 'export',
            'output_root': '/output', 'recipe_sha256': P.RECIPE_SHA256}},
    ]
    return {'schema_version': 1, 'workflow_id': 'job', 'revision': 1, 'nodes': nodes,
            'edges': [{'from': left['id'], 'to': right['id']} for left, right in zip(nodes, nodes[1:])]}


def check(value):
    return P.graph(value, sha256(P.encoded(value)).hexdigest())


def test_exact_automatic_intent_is_a_separate_graph_node():
    value = graph()
    assert check(value)[0] == value
    for key, wrong in [('scope', 'all_groups'), ('originals', 'overwrite'),
                       ('unattended', 1), ('collision', 'rename')]:
        changed = deepcopy(value); changed['nodes'][2]['operation']['intent'][key] = wrong
        with pytest.raises(ValueError): check(changed)
    changed = deepcopy(value); changed['nodes'][2]['error_policy'] = 'keep_continue'
    with pytest.raises(ValueError): check(changed)
    changed = deepcopy(value); del changed['nodes'][2]['operation']['intent']
    with pytest.raises(ValueError): check(changed)


def test_complete_preset_refusal_never_drops_portrait_modules():
    scalar = {'modules': {'lnx.exposure.v1': {'ev': 0.2}}}
    assert A.support_reason(scalar) is None
    for unsupported in ('lnx.skin.v1', 'unknown'):
        combined = deepcopy(scalar); combined['modules'][unsupported] = {}
        assert A.support_reason(combined) == 'automatic_requires_supported_global_or_per_face_modules'
        assert unsupported in combined['modules']
    assert A.support_reason({**scalar, 'xmp_import': {}}) == 'automatic_xmp_not_supported'


def test_automatic_owner_never_accepts_human_review_steps():
    owner = A.AutomaticPresetHandoff(SimpleNamespace(engine=SimpleNamespace()))
    for request in ({'step': 'approve', 'payload': {'accepted': True}}, {'step': 'save_project'}):
        with pytest.raises(ValueError, match='do not accept'): owner.step(request)
    with pytest.raises(ValueError, match='not a human-image'): owner.image({})


def test_automatic_public_state_is_truthful_not_reviewed():
    owner = A.AutomaticPresetHandoff(SimpleNamespace(engine=SimpleNamespace()))
    owner.active = dict(version=1, operation_id='op', document_id='doc', preset_id='scalar',
                        preset_sha256='a' * 64, phase='authorized', review=None, message='automatic')
    assert owner.public()['mode'] == 'automatic'
    assert owner.public()['review'] is None
    owner.active['phase'] = 'unknown'
    assert owner.public()['phase'] == 'unknown'


def test_unknown_original_automatic_operation_is_query_only():
    events = []
    owner = WorkflowOwner(SimpleNamespace(), events.append)
    request = {'request_id': 'query', 'session_id': 'session',
               'original_request_id': 'lost-original', 'operation_id': 'a' * 64, 'action': 'query'}
    result = owner._query(request)
    assert result['status'] == 'unknown' and not owner.operations


@pytest.mark.parametrize('unknown', [False, True])
def test_automatic_apply_uses_normal_dispatch_then_verified_save_return(monkeypatch, unknown):
    """Test-local receipts only; this is not a real photo/history acceptance run."""
    from lumaretouch_engine import preset_store as PS, preset_organisation_store as PO
    calls, receipts = [], {}
    identity = {'operation_id': 'preflight', 'input_occurrence_id': 'input', 'document_id': 'doc'}
    document = {'document_id': 'doc', 'document_revision': '1'}
    assessment = {'requires_review': False, 'review': None}
    row, people, context = {}, object(), object()
    engine = SimpleNamespace(_preset_controller=lambda: SimpleNamespace(_receipts=receipts),
                             _remember_current=lambda: calls.append('remember'))
    owner = A.AutomaticPresetHandoff(SimpleNamespace(engine=engine, _encoded_recipe=lambda row: {'saved': 'canonical'}))
    owner.active = {'phase': 'authorized', 'assessment': assessment, 'initial_document': document,
        'preset_id': 'scalar', 'document_id': 'doc', 'preflight': {'command': {'identity': identity}},
        'automatic_evidence': {'exact': True}, 'people_owner': people, 'people_context': context,
        'target': {'revision': '1'}, 'row': row}
    owner._inputs = lambda: ({'exact': True}, (row, object(), people, context))
    owner._check = lambda **kwargs: (None, row)
    owner._version = lambda row: '2'
    owner._verify_applied = lambda: calls.append('verify')
    owner._save = lambda: calls.append('save')
    owner._return = lambda: calls.append('return')
    monkeypatch.setattr(PS, 'preset_dir', lambda: '/fixture-only')
    monkeypatch.setattr(PO, 'catalogue_lock', lambda path: nullcontext())
    def dispatched(actual_engine, payload, recheck):
        calls.append('dispatch'); recheck()
        assert actual_engine is engine and payload['cmd'] == 'preset' and payload['action'] == 'apply'
        assert set(payload) == {'cmd', 'action', 'request_id', 'id', 'document_id'}
        receipts[payload['request_id']] = ('fixture-only', {'success': not unknown, 'outcome_unknown': unknown})
    monkeypatch.setattr(A, 'dispatch', dispatched)
    record = {'command': {'identity': {**identity, 'operation_id': 'apply'},
        'operation': {'assessment': assessment, 'document': document, 'preset_id': 'scalar'}}, 'dispatch_started': False}
    if unknown:
        with pytest.raises(ValueError, match='no definite'): owner.apply(record)
        assert calls == ['dispatch']
    else:
        owner.apply(record)
        assert calls == ['dispatch', 'remember', 'verify', 'save', 'return']
    assert record['dispatch_started'] is True


def test_portrait_support_requires_exact_opt_in_and_whole_preset():
    from lumaretouch_engine import skin_finish_scope as F
    recipe = F.S.neutral()
    # Neutral recipes remain rejected; nonzero leaves need explicit scope.
    assert A.support_reason({'modules': {F.OP: {'recipe': recipe}}}) is not None
    preset = {'modules': {F.OP: {'recipe': {**recipe, 'whitening': .2}}}}
    assert A.support_reason(preset) is None  # catalogue only
    assert A.support_reason(preset, P.AUTOMATIC_INTENT) == 'automatic_requires_explicit_all_verified_detected_faces_scope'
    assert A.support_reason(preset, P.AUTOMATIC_PORTRAIT_INTENT) is None
    preset['modules']['lnx.exposure.v1'] = {'ev': .2}
    assert A.support_reason(preset, P.AUTOMATIC_PORTRAIT_INTENT) is None
    from lumaretouch_engine import portrait_group_retained as G
    assert A.PORTRAIT_MODULES == G.OPERATIONS
    assert A.support_reason({'modules': {'lnx.skin.v1': {'strength': .2}}}, P.AUTOMATIC_PORTRAIT_INTENT)


def test_known_automatic_refusal_is_not_mislabelled_user_image_decline():
    owner = A.AutomaticPresetHandoff(SimpleNamespace(engine=SimpleNamespace()))
    owner._version = lambda row: '3'
    result = owner._cancel_result({'automatic_rejection': 'no genuine own face support',
        'initial_document': {'document_id': 'target', 'document_revision': '1'}}, {})
    assert result['code'] == 'automatic_target_ineligible'
    assert result['retained_document']['document_revision'] == '3'
    assert 'review' not in result


@pytest.mark.parametrize('lost_proof', [False, True])
def test_preapply_refusal_requires_observed_preparation_and_verified_return(monkeypatch, lost_proof):
    from lumaretouch_engine.workflow_preset_handoff import PresetHandoff
    calls = []
    owner = A.AutomaticPresetHandoff(SimpleNamespace(engine=SimpleNamespace()))
    owner._intent = lambda: {'operation': {'intent': deepcopy(P.AUTOMATIC_INTENT)}}
    owner._check = lambda **kw: calls.append('check')
    owner._version = lambda row: '2'
    monkeypatch.setattr(A, 'resolve', lambda *args: {'modules': {'lnx.exposure.v1': {'ev': .2}}})
    preparation = SimpleNamespace(started=True, expected=None if lost_proof else ('observed',))
    def start(self, record, row):
        self.active = {'phase': 'awaiting_preparation', 'target': {}, 'preparation': preparation}
    monkeypatch.setattr(PresetHandoff, 'start', start)
    def opening():
        raise ValueError('unsupported own analysis')
    owner._open = opening
    def returned():
        calls.append('verified-return-and-rollback')
        owner.active = None
    owner._return = returned
    record = {'command': {'operation': {'preset_id': 'fixed', 'preset_sha256': 'a' * 64}}}
    if lost_proof:
        with pytest.raises(ValueError): owner.start(record, {})
        assert record['dispatch_started'] and not calls
    else:
        owner.start(record, {})
        assert calls == ['check', 'verified-return-and-rollback']
        assert record['dispatch_started'] is False and owner.active is None
