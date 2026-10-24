# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: waist scalar preset routing, ownership and write fences.

No product imports, collection, execution, builds, typechecks, inference or
native calls ran during authoring. The shared controller harness uses synthetic
manual-marker records and deliberately NON-PNG display bytes. It proves no
photographic, anatomical, decoder or rendering quality; real full-render and
transport/decode fixtures remain separate acceptance gates.
"""
from copy import deepcopy
from dataclasses import replace

import pytest

from test_torso_length_preset_review_unrun import fixture as scalar_fixture
from test_waist_length_support_unrun import synthetic_record
from lumaretouch_engine import body_pose_project as BODY, body_pose_state as B
from lumaretouch_engine import preset_controller as PC, scope as SC
from lumaretouch_engine import waist_length_scope as WAIST
from lumaretouch_engine import waist_length_state as S, waist_length_project as PROJECT
from lumaretouch_engine import waist_length_transfer_review as REVIEW
from lumaretouch_engine import creative_derived_source as SOURCE


def fixture(tmp_path, **options):
    return scalar_fixture(tmp_path, family='waist', **options)


def prepare(context, **ports):
    return context.reviews.prepare(context.preset, context.row['state'], context.row,
        context.document, context.revision, None,
        **{'prepare_waist': context.prepare, 'verify_waist': context.verify, **ports})


def ack(plan):
    review = plan['waist_transfer']
    return [{'document_id': review['document_id'], 'revision': review['revision'],
             'before_sha256': review['before']['sha256'], 'after_sha256': review['after']['sha256']}]


def claim(context, plan, **options):
    return context.reviews.claim(plan['preflight_token'], 'waist', context.row['state'],
        context.row, context.document, context.revision,
        **{'verify_waist': context.verify, 'waist_review_ack': ack(plan), **options})


def command(context, action, request, **values):
    message = {'cmd': 'preset', 'action': action, 'id': 'waist',
        'document_id': context.document, 'request_id': request, **values}
    context.owner.handle_command(message); context.owner.finish(message)
    return context.events[-1]


@pytest.mark.parametrize('derived', [False, True])
@pytest.mark.parametrize('size', [(768, 768), (1024, 768), (768, 1024)])
def test_only_scalar_crosses_into_target_owned_manual_markers(tmp_path, derived, size):
    context = fixture(tmp_path, derived=derived, size=size); before = deepcopy(context.row)
    plan = prepare(context); record = context.reviews.pending[plan['preflight_token']]
    assert plan['applies'] == {WAIST.OP: {'version': 1, 'amount': .75}}
    assert plan['module_scope'] == [WAIST.OP] and 'torso_transfer' not in plan
    assert record['source_proof'] == SOURCE.row_proof(context.row)
    assert set(record['waist_review']) == REVIEW.FIELDS and record['torso'] is None
    assert record['waist_review']['source_size'] == list(size)
    assert all('base64' not in record['waist_review'][side] for side in ('before', 'after'))
    assert all('base64' in plan['waist_transfer'][side] for side in ('before', 'after'))
    candidate = context.calls[0][2]
    old_bank = BODY.bank(before['state']); new_bank = BODY.bank(candidate)
    old = old_bank['bodies'][context.ref['body_instance_id']]
    new = new_bank['bodies'][context.ref['body_instance_id']]
    assert old_bank['support_assets'] == new_bank['support_assets']
    assert old_bank['analysis_runs'] == new_bank['analysis_runs']
    assert old['record'] == new['record'] and old['association'] == new['association']
    assert old['operations'][WAIST.OP]['review'] == new['operations'][WAIST.OP]['review']
    support = B.support(new_bank, context.ref, WAIST.OP)['data']
    assert all(marker in support for marker in S.WAIST_MARKERS)
    assert support['confirmations']['waist_endpoints_manually_marked'] is True
    assert {k: v for k, v in candidate.items() if k != BODY.KEY} == {
        k: v for k, v in before['state'].items() if k != BODY.KEY}
    assert context.row == before and not context.replays and context.revision == '7'


@pytest.mark.parametrize('missing', ['both', 'prepare', 'verify'])
def test_both_full_target_review_ports_are_required(tmp_path, missing):
    context = fixture(tmp_path); before = deepcopy(context.row)
    ports = {key: None for key in ('prepare_waist', 'verify_waist')
             if missing == 'both' or key.startswith(missing)}
    with pytest.raises(ValueError): prepare(context, **ports)
    assert context.row == before and not context.reviews.pending and not context.replays


@pytest.mark.parametrize('defect', ['unreviewed', 'operation-disabled', 'body-disabled',
    'unassociated', 'two-enabled-bodies', 'missing-own-face', 'stale-face'])
def test_unreviewed_or_ambiguous_targets_are_not_promoted(tmp_path, defect):
    context = fixture(tmp_path, reviewed=defect != 'unreviewed')
    bank = BODY.bank(context.row['state']); body = B.target(bank, context.ref)
    if defect == 'operation-disabled': body['operations'][WAIST.OP]['enabled'] = False
    elif defect == 'body-disabled': body['enabled'] = False
    elif defect == 'unassociated': body['association'] = None
    elif defect == 'two-enabled-bodies':
        record = synthetic_record(source=body['record']['source'])
        bank = B.add_run(bank, {'source': record['source'], 'records': [record],
            'detector_limit': 4, 'limit_reached': False, 'census_complete': False},
            initial_operations=(WAIST.OP,), operation_policies=S.policies())
    elif defect == 'missing-own-face': context.row['people']['links'] = []
    elif defect == 'stale-face':
        next(iter(context.row['people']['faces'].values()))['box'][0] += .001
    context.row['state'][BODY.KEY] = PROJECT.pack(bank)
    context.preset['modules'][WAIST.OP]['amount'] = 0.
    before = deepcopy(context.row)
    with pytest.raises(ValueError): prepare(context)
    assert context.row == before and not context.reviews.pending and not context.replays


@pytest.mark.parametrize('invalid', ['missing', 'empty', 'object', 'duplicate', 'wrong-target',
    'wrong-revision', 'recipe-hashes', 'swapped-images', 'extra-field'])
def test_exact_single_target_image_ack_and_correctable_rejection(tmp_path, invalid):
    context = fixture(tmp_path); plan = prepare(context); value = ack(plan)
    if invalid == 'missing': value = None
    elif invalid == 'empty': value = []
    elif invalid == 'object': value = value[0]
    elif invalid == 'duplicate': value *= 2
    elif invalid == 'wrong-target': value[0]['document_id'] = 'someone-else'
    elif invalid == 'wrong-revision': value[0]['revision'] = '8'
    elif invalid == 'recipe-hashes':
        value[0]['before_sha256'] = plan['waist_transfer']['before_sha256']
        value[0]['after_sha256'] = plan['waist_transfer']['candidate_sha256']
    elif invalid == 'swapped-images':
        value[0]['before_sha256'], value[0]['after_sha256'] = value[0]['after_sha256'], value[0]['before_sha256']
    else: value[0]['accepted'] = True
    before = deepcopy(context.row)
    result = command(context, 'apply', 'bad-ack', preflight_token=plan['preflight_token'], waist_review_ack=value)
    assert not result['success'] and not result['outcome_unknown']
    assert 'waist_review_ack' not in result and 'module_scope' not in result
    assert plan['preflight_token'] in context.reviews.pending
    assert context.row == before and not context.replays and context.revision == '7'


@pytest.mark.parametrize('changed', ['state', 'people', 'source', 'revision', 'row-identity',
    'same-identity-row', 'private-pixels', 'missing-verifier'])
def test_frozen_claim_refuses_current_context_drift(tmp_path, changed):
    context = fixture(tmp_path); plan = prepare(context); ports = {}
    if changed == 'state': context.row['state']['_unselected'] = 'later edit'
    elif changed == 'people': context.row['people']['revision'] += 1
    elif changed == 'source': (tmp_path / 'synthetic-waist-original.bin').write_bytes(b'changed-source')
    elif changed == 'revision': context.revision = '8'
    elif changed == 'row-identity': context.row['document_id'] = 'other-document'
    elif changed == 'same-identity-row': context.row = deepcopy(context.row)
    elif changed == 'private-pixels': context.reviews.pending[plan['preflight_token']]['waist_review']['after']['base64'] = 'forbidden'
    else: ports['verify_waist'] = None
    with pytest.raises(ValueError): claim(context, plan, **ports)
    assert plan['preflight_token'] in context.reviews.pending and not context.replays


def test_controller_uses_existing_ledger_and_replays_exact_receipt_only(tmp_path, monkeypatch):
    context = fixture(tmp_path); monkeypatch.setattr(PC.PS, 'find', lambda _: context.preset)
    plan = command(context, 'preflight', 'preflight'); assert plan['success'], plan
    arguments = {'preflight_token': plan['preflight_token'], 'waist_review_ack': ack(plan)}
    result = command(context, 'apply', 'apply', **arguments)
    assert result['success'] and not result['outcome_unknown'] and context.revision == '8'
    assert result['module_scope'] == [WAIST.OP] and result['preflight_token'] == plan['preflight_token']
    assert result['waist_review_ack'] == ack(plan) and 'torso_review_ack' not in result
    assert len(context.replays) == 1 and context.replays[0][1]['strict_local'] is True
    assert context.identity_calls and WAIST.params_of(context.row['state'])['amount'] == .75
    repeated = command(context, 'apply', 'apply', **arguments)
    assert repeated['replayed'] and repeated['waist_review_ack'] == result['waist_review_ack']
    changed = deepcopy(arguments); changed['waist_review_ack'][0]['after_sha256'] = 'f' * 64
    assert not command(context, 'apply', 'apply', **changed)['success']
    assert not command(context, 'apply', 'new-request', **arguments)['success']
    assert len(context.replays) == 1 and context.revision == '8'


@pytest.mark.parametrize('changed', ['row', 'document', 'revision', 'source', 'people', 'state'])
def test_before_forward_drift_never_triggers_a_snapshot_rollback(tmp_path, changed):
    context = fixture(tmp_path); plan = prepare(context)
    advance = context.owner.ports.advance; changed_rows = []
    def drifting_advance():
        advance()
        if changed == 'row': context.row = deepcopy(context.row)
        elif changed == 'document': context.row['document_id'] = 'switched'
        elif changed == 'revision': context.revision = 'invalid-revision'
        elif changed == 'source': (tmp_path / 'synthetic-waist-original.bin').write_bytes(b'replaced')
        elif changed == 'people': context.row['people']['revision'] += 1
        else: context.row['state']['_unselected'] = 'new-edit-before-any-write'
        changed_rows.append(deepcopy(context.row))
    context.owner.ports = replace(context.owner.ports, advance=drifting_advance,
        target_row=lambda: context.row, capture=lambda: deepcopy(context.row['state']))
    result = command(context, 'apply', 'before-write-drift',
        preflight_token=plan['preflight_token'], waist_review_ack=ack(plan))
    assert not result['success'] and result['outcome_unknown'] and result['requires_reload']
    assert not result['rolled_back'] and context.invalid and not context.replays
    assert context.row == changed_rows[0] and result['waist_review_ack'] == ack(plan)


@pytest.mark.parametrize('changed', ['state', 'people', 'row', 'revision', 'source'])
def test_rollback_prewrite_fence_preserves_changed_target_or_people(tmp_path, changed):
    context = fixture(tmp_path); plan = prepare(context); before = deepcopy(context.row['state'])
    replay = context.owner.ports.replay; changed_rows = []
    def drifting_replay(value, **kwargs):
        result = replay(value, **kwargs)
        if kwargs['mode'] == 'preset':
            if changed == 'state': context.row['state']['_unselected'] = 'failed-render-side-effect'
            elif changed == 'people': context.row['people']['revision'] += 1
            elif changed == 'row': context.row = deepcopy(context.row)
            elif changed == 'revision': context.revision = '9'
            else: (tmp_path / 'synthetic-waist-original.bin').write_bytes(b'replaced')
            changed_rows.append(deepcopy(context.row))
        return result
    context.owner.ports = replace(context.owner.ports, replay=drifting_replay,
        target_row=lambda: context.row, capture=lambda: deepcopy(context.row['state']))
    result = command(context, 'apply', 'rollback-fence',
        preflight_token=plan['preflight_token'], waist_review_ack=ack(plan))
    assert not result['success'] and result['rolled_back'] is (changed == 'state')
    assert result['outcome_unknown'] is (changed != 'state')
    if changed == 'state':
        assert context.row['state'] == before and len(context.replays) == 2
    else:
        assert context.row == changed_rows[0] and len(context.replays) == 1 and context.invalid
    assert result['waist_review_ack'] == ack(plan) and result['module_scope'] == [WAIST.OP]
    assert not context.row['undo'] and not context.row['redo']
    assert all(item[1]['strict_local'] is True for item in context.replays)


def test_identity_callback_cannot_switch_row_before_the_actual_write(tmp_path):
    context = fixture(tmp_path); plan = prepare(context); identity = context.history_identity
    replacement = []
    def switching_identity(*args):
        value = identity(*args)
        context.row = deepcopy(context.row); replacement.append(deepcopy(context.row))
        return value
    context.owner.ports = replace(context.owner.ports, waist_history_identity=switching_identity,
        target_row=lambda: context.row, capture=lambda: deepcopy(context.row['state']))
    result = command(context, 'apply', 'callback-switch',
        preflight_token=plan['preflight_token'], waist_review_ack=ack(plan))
    assert not result['success'] and result['outcome_unknown'] and not result['rolled_back']
    assert context.row == replacement[0] and len(replacement) == 1 and not context.replays


def test_changed_manual_support_cannot_be_overwritten_by_rollback(tmp_path):
    context = fixture(tmp_path); plan = prepare(context); replay = context.owner.ports.replay
    changed_rows = []
    def changing_support(value, **kwargs):
        result = replay(value, **kwargs)
        if kwargs['mode'] == 'preset':
            bank = BODY.bank(context.row['state']); body = B.target(bank, context.ref)
            support = B.support(bank, context.ref, WAIST.OP)['data']
            support['waist_upper_left'][1] += .005
            bank = B.set_support(bank, context.ref, WAIST.OP, S.SUPPORT_KIND,
                                 support, operation_policies=S.policies())
            bank = B.review(bank, context.ref, operation_id=WAIST.OP,
                points_sha256=body['record']['points_sha256'], visible_anchors=list(S.REQUIRED_ANCHORS),
                ownership_confirmed=True, support_sha256=B.operation(bank, context.ref, WAIST.OP)['support_sha256'],
                operation_policies=S.policies())
            context.row['state'][BODY.KEY] = PROJECT.pack(bank)
            changed_rows.append(deepcopy(context.row))
        return result
    context.owner.ports = replace(context.owner.ports, replay=changing_support)
    result = command(context, 'apply', 'changed-manual-support',
        preflight_token=plan['preflight_token'], waist_review_ack=ack(plan))
    assert not result['success'] and result['outcome_unknown'] and not result['rolled_back']
    assert context.row == changed_rows[0] and len(context.replays) == 1 and context.invalid
    assert result['waist_review_ack'] == ack(plan)


def test_identity_callback_people_drift_refuses_both_forward_and_rollback(tmp_path):
    context = fixture(tmp_path); plan = prepare(context); identity = context.history_identity
    before = deepcopy(context.row['state']); calls = []
    def people_drift_identity(*args):
        value = identity(*args)
        calls.append(value)
        if len(calls) == 1: context.row['people']['revision'] += 1
        return value
    context.owner.ports = replace(context.owner.ports, waist_history_identity=people_drift_identity)
    result = command(context, 'apply', 'people-callback-drift',
        preflight_token=plan['preflight_token'], waist_review_ack=ack(plan))
    assert not result['success'] and result['outcome_unknown'] and not result['rolled_back']
    assert len(calls) == 2 and not context.replays and context.row['state'] == before
    assert context.row['people']['revision'] == 2 and context.invalid


@pytest.mark.parametrize('other', ['xmp_review_ack', 'spill_review_ack', 'shadow_review_ack', 'torso_review_ack'])
def test_other_ack_even_null_cannot_consume_waist_token(tmp_path, other):
    context = fixture(tmp_path); plan = prepare(context)
    result = command(context, 'apply', 'mixed-ack', preflight_token=plan['preflight_token'],
        waist_review_ack=ack(plan), **{other: None})
    assert not result['success'] and not result['outcome_unknown']
    assert plan['preflight_token'] in context.reviews.pending and not context.replays


@pytest.mark.parametrize('mixed', ['torso', 'crop', 'xmp'])
def test_no_combined_or_xmp_review_bypass(tmp_path, mixed):
    context = fixture(tmp_path)
    if mixed == 'torso': context.preset['modules'][SC.TORSO_LENGTH.OP] = {'version': 1, 'amount': .2}
    elif mixed == 'crop': context.preset['modules'][SC.OP_CROP] = {'rect_normalized': [0., 0., 1., 1.], 'rotation_degrees': 0.}
    else: context.preset['xmp_import'] = {'source_sha256': 'e' * 64}
    with pytest.raises(ValueError): prepare(context)
    assert not context.replays and not context.reviews.pending


def test_missing_history_port_direct_apply_and_expired_review_refuse(tmp_path, monkeypatch):
    context = fixture(tmp_path); monkeypatch.setattr(PC.PS, 'find', lambda _: context.preset)
    assert not command(context, 'apply', 'direct')['success']
    context.owner.ports = replace(context.owner.ports, waist_history_identity=None)
    assert not command(context, 'preflight', 'no-current-identity')['success']
    plan = prepare(context)
    assert not command(context, 'apply', 'lost-current-identity',
        preflight_token=plan['preflight_token'], waist_review_ack=ack(plan))['success']
    assert plan['preflight_token'] in context.reviews.pending
    context.reviews.pending[plan['preflight_token']]['expires'] = 0
    with pytest.raises(ValueError): claim(context, plan)
    assert not context.replays and context.revision == '7'


def test_scalar_save_and_old_implicit_save_do_not_leak_or_add_waist(tmp_path, monkeypatch):
    context = fixture(tmp_path); captured = []
    monkeypatch.setattr(PC.PS, 'save', lambda value, **kw: captured.append(deepcopy(value)) or 'fixture-only')
    context.owner.save({'id': 'saved-waist', 'name': 'Saved waist', 'module_scope': [WAIST.OP]})
    assert captured[0]['modules'] == {WAIST.OP: {'version': 1, 'amount': -.25}}
    monkeypatch.setattr(SC, 'transferable_ops', lambda: [SC.OP_EXPOSURE, SC.TORSO_LENGTH.OP, WAIST.OP])
    implicit = context.owner.save({'id': 'legacy', 'name': 'Legacy implicit'})
    assert implicit['module_scope'] == [SC.OP_EXPOSURE]
    assert WAIST.OP not in captured[1]['modules'] and SC.TORSO_LENGTH.OP not in captured[1]['modules']


def test_unknown_bounded_receipt_retains_ack_and_never_reapplies(tmp_path, monkeypatch):
    context = fixture(tmp_path); plan = prepare(context)
    monkeypatch.setattr(PC, 'MAX_RESULT_BYTES', 1)
    arguments = {'preflight_token': plan['preflight_token'], 'waist_review_ack': ack(plan)}
    result = command(context, 'apply', 'bounded', **arguments)
    assert not result['success'] and result['outcome_unknown'] and result['error_code'] == 'receipt_too_large'
    assert result['module_scope'] == [WAIST.OP] and result['preflight_token'] == plan['preflight_token']
    assert result['waist_review_ack'] == ack(plan) and 'waist_transfer' not in result
    command(context, 'apply', 'bounded', **arguments)
    assert len(context.replays) == 1 and context.revision == '8'
