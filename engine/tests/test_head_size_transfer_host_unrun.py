# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: exact head preflight routing and recovery boundaries.

No product imports, collection, tests, builds or runtime work ran in authoring.
These are synthetic routing fixtures, not evidence of rendered/photo quality.
"""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from lumaretouch_engine.creative_transfer_host import head_preflight_read_only, require_route
from lumaretouch_engine.creative_document_host import guard_command
from lumaretouch_engine import project_recovery_runtime as RECOVERY

HEAD = 'lnx.head_size.v1'


def request(kind):
    base = {'cmd': kind, 'action': 'preflight', 'request_id': 'head-review', 'module_scope': [HEAD]}
    if kind == 'preset': return {**base, 'id': 'head-preset', 'document_id': 'target'}
    return {**base, 'docs': ['one', 'two'], 'conflict_policy': 'skip_and_report'}


@pytest.mark.parametrize('kind', ['batch', 'preset'])
@pytest.mark.parametrize('failed', [False, True])
@pytest.mark.parametrize('already_tainted', [False, True])
def test_exact_head_preflight_never_advances_recovery_or_clears_prior_taint(kind, failed, already_tainted):
    message = request(kind)
    runtime = SimpleNamespace(revision=9, tainted=already_tainted, reason='existing reason')
    engine = SimpleNamespace(_project_recovery_runtime=runtime, EDIT_CMDS={'batch', 'preset'})
    boundary = {'message': message, 'started': True, 'returned': not failed, 'failed': failed}
    assert head_preflight_read_only(message)
    RECOVERY.finish(engine, boundary, 'synthetic read failure' if failed else None)
    assert runtime.revision == 9 and runtime.tainted is already_tainted
    assert runtime.reason == 'existing reason'


@pytest.mark.parametrize('kind', ['batch', 'preset'])
@pytest.mark.parametrize('fault', ['action', 'mixed', 'other-family', 'token', 'ack', 'unknown', 'request-id'])
def test_read_only_exemption_cannot_be_widened_to_mutations_or_foreign_scopes(kind, fault):
    message = request(kind)
    if fault == 'action': message['action'] = 'commit' if kind == 'batch' else 'apply'
    elif fault == 'mixed': message['module_scope'].append('lnx.exposure.v1')
    elif fault == 'other-family': message['module_scope'] = ['lnx.waist_length.v1']
    elif fault == 'token': message['preflight_token'] = 'a' * 32
    elif fault == 'ack': message['head_review_ack'] = []
    elif fault == 'unknown': message['replace_support'] = True
    else: message['request_id'] = ''
    assert not head_preflight_read_only(message)
    runtime = SimpleNamespace(revision=9, tainted=False, reason=None)
    engine = SimpleNamespace(_project_recovery_runtime=runtime, EDIT_CMDS={'batch', 'preset'})
    RECOVERY.finish(engine, {'message': message, 'started': True, 'returned': True, 'failed': True})
    assert runtime.tainted and runtime.revision == 9


@pytest.mark.parametrize('docs', [[], [True], [-1], [2**53], ['bad\nselector'], ['same', 'same'], ['x']*9, [{}], 'one'])
def test_read_only_batch_requires_bounded_explicit_document_selectors(docs):
    message = request('batch'); message['docs'] = docs
    assert not head_preflight_read_only(message)


def test_derived_head_commit_routes_exact_ack_to_actual_frozen_controller():
    message = {'cmd': 'batch', 'action': 'commit', 'request_id': 'head-commit',
               'preflight_token': 'a'*32, 'head_review_ack': []}
    engine = SimpleNamespace(_creative_base={'synthetic': True}, _docs=[])
    frozen = deepcopy(message)
    require_route('batch', message)
    guard_command(engine, 'batch', message)
    assert message == frozen and not head_preflight_read_only(message)
    # Transport admission is not approval: frozen controller owns exact images,
    # family, target rows and parameters; it rejects missing/foreign/bad acks.
    for extra in ({'module_scope': [HEAD]}, {'docs': ['new-target']}, {'amount': .5},
                  {'torso_review_ack': []}, {'people_transfer': {}}):
        with pytest.raises(ValueError): require_route('batch', {**message, **extra})


def test_successful_head_mutation_still_advances_recovery_and_failed_mutation_taints():
    message = {'cmd': 'batch', 'action': 'commit', 'request_id': 'head-commit',
               'preflight_token': 'a'*32, 'head_review_ack': []}
    runtime = SimpleNamespace(revision=9, tainted=False, reason=None)
    engine = SimpleNamespace(_project_recovery_runtime=runtime, EDIT_CMDS={'batch', 'preset'})
    RECOVERY.finish(engine, {'message': message, 'started': True, 'returned': True, 'failed': False})
    assert runtime.revision == 10 and not runtime.tainted
    RECOVERY.finish(engine, {'message': message, 'started': True, 'returned': True, 'failed': True})
    assert runtime.revision == 10 and runtime.tainted
