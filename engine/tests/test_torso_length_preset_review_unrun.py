"""AUTHORED / UNRUN: torso-only preset freeze, acknowledgments and rollback.

No product imports, collection, execution, builds, inference or native calls ran
during authoring. Body/face records are synthetic schema fixtures, not observed
anatomy. Visual ports below intentionally return non-PNG fixture bytes: these
contracts exercise routing only, not real rendering or photographic acceptance.
"""
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import base64
import struct
from types import SimpleNamespace

import pytest

from test_torso_length_support_unrun import fixture as body_fixture
from lumaretouch_engine import body_pose_evidence as E, body_pose_project as BODY
from lumaretouch_engine import creative_derived_source as SOURCE
from lumaretouch_engine import preset_controller as PC, scope as SC
from lumaretouch_engine import torso_length_project as PROJECT
from lumaretouch_engine import torso_length_scope as TORSO
from lumaretouch_engine import torso_length_transfer_review as REVIEW
from lumaretouch_engine.creative_document_assets import make_asset
from lumaretouch_engine.optics_candidate_identity import fingerprint


def stored():
    return {'schema': SC.PRESET_SCHEMA, 'id': 'torso', 'name': 'Torso scalar review',
            'kind': 'custom', 'note': '', 'modules': {TORSO.OP: {'version': 1, 'amount': .75}}}


def fixture(tmp_path, *, derived=False, reviewed=True, family='torso', size=None):
    # Fixed synthetic families share only the controller-port harness. These
    # non-PNG proofs are not substitutes for the separate complete-render tests.
    if family == 'torso':
        scope, project, review_api, make_body = TORSO, PROJECT, REVIEW, body_fixture
    elif family == 'waist':
        from test_waist_length_support_unrun import fixture as make_body
        from lumaretouch_engine import waist_length_scope as scope
        from lumaretouch_engine import waist_length_project as project
        from lumaretouch_engine import waist_length_transfer_review as review_api
    elif family == 'head':
        from test_head_size_support_unrun import fixture as make_body
        from lumaretouch_engine import head_size_scope as scope
        from lumaretouch_engine import head_size_project as project
        from lumaretouch_engine import head_size_transfer_review as review_api
    else:
        raise ValueError('Synthetic preset fixture needs a fixed torso/waist/head family')
    if size is None: size = (512, 512) if family == 'torso' else (1024, 1024)
    width, height = size
    path = tmp_path / f'synthetic-{family}-original.bin'
    path.write_bytes(b'not-a-decoded-photo-or-observed-body')
    state = {'_crop_rect': (0., 0., 1., 1.), '_crop_rotation': 0.,
             '_exposure': (0.,) * 7, '_unselected': 'target-owned'}
    if derived:
        state['_creative_base'] = make_asset('rgba', width, height,
            struct.pack('<4f', .2, .3, .4, 1.) * (width * height))
    source = E.source({**SOURCE.binding(state, str(path), size), 'orientation': E.ORIENTATION})
    bank, people, ref, _, _ = make_body(amount=.25 if family == 'head' else -.25, review=reviewed, source=source)
    state[BODY.KEY] = project.pack(bank)
    row = {'document_id': 'row-target', 'path': str(path), 'src_w': width, 'src_h': height,
           'state': state, 'people': people, 'undo': [], 'redo': []}
    context = SimpleNamespace(row=row, revision='7', document='loaded', events=[],
        calls=[], identity_calls=[], replays=[], invalid=[], preset=stored(), ref=ref)
    if family in ('waist', 'head'):
        context.preset.update(id=family, name=family.capitalize()+' scalar review',
            modules={scope.OP: {'version': 1, 'amount': .75}})

    def proof(current, before, candidate, document_id, revision):
        source_proof = SOURCE.row_proof({**current, 'state': before})
        size = [current['src_w'], current['src_h']]
        left = review_api._target_identity(before, current['people'], source_proof, size)
        right = review_api._target_identity(candidate, current['people'], source_proof, size)
        if any(left[key] != right[key] for key in left if key != 'bank_sha256'):
            raise ValueError('Synthetic transfer attempted to replace owned body support')
        binding = {key: value for key, value in right.items() if key != 'bank_sha256'}
        private = {'version': 1, 'document_id': document_id, 'revision': revision,
            'source_proof': source_proof, 'before_sha256': fingerprint(before),
            'candidate_sha256': fingerprint(candidate),
            'before_people_sha256': fingerprint(current['people']),
            'candidate_people_sha256': fingerprint(current['people']),
            'source_size': size, 'before_output_size': size, 'after_output_size': size,
            'parameters': scope.params_of(candidate), **binding,
            'before_bank_sha256': left['bank_sha256'], 'candidate_bank_sha256': right['bank_sha256']}
        public_images = {}
        for side, value in (('before', before), ('after', candidate)):
            raw = ('SYNTHETIC NON-PNG PORT: ' + document_id + ':' + fingerprint(value)).encode()
            scale = min(1., 256 / max(size))
            private[side] = {'mime': 'image/png', 'width': max(1, round(size[0] * scale)),
                             'height': max(1, round(size[1] * scale)),
                             'sha256': sha256(raw).hexdigest()}
            public_images[side] = {**private[side], 'base64': base64.b64encode(raw).decode('ascii')}
        private = review_api.checked(private)
        return private, {**deepcopy(private), **public_images}

    def prepare(current, before, candidate, document_id, revision):
        context.calls.append(('prepare', deepcopy(before), deepcopy(candidate), document_id, revision))
        return proof(current, before, candidate, document_id, revision)

    def verify(current, before, candidate, document_id, revision, record):
        context.calls.append(('verify', deepcopy(before), deepcopy(candidate), document_id, revision))
        if context.document != document_id or context.revision != revision:
            raise ValueError('Synthetic target document or revision changed')
        expected, _ = proof(current, before, candidate, document_id, revision)
        if review_api.checked(record) != expected:
            raise ValueError('Synthetic complete target, body, face or source changed')
        return expected

    def history_identity(current, actual, document_id, revision):
        """Synthetic current-state/people fence, never a render or real image."""
        review_api._context(document_id, revision)
        context.identity_calls.append((document_id, revision, fingerprint(actual)))
        if context.document != document_id or context.revision != revision:
            raise ValueError('Synthetic current-state identity changed')
        source_proof = SOURCE.row_proof({**current, 'state': actual})
        review_api._target_identity(actual, current['people'], source_proof,
                                   [current['src_w'], current['src_h']])
        return {'document_id': document_id, 'revision': revision,
                'source_proof': source_proof, 'candidate_sha256': fingerprint(actual),
                'people_sha256': fingerprint(current['people'])}

    def replay(value, **kwargs):
        context.replays.append((deepcopy(value), kwargs))
        row['state'] = deepcopy(value)
        return {'event': 'frame', 'render_ms': 1}

    def advance():
        context.revision = str(int(context.revision) + 1)

    context.prepare = prepare; context.verify = verify; context.history_identity = history_identity
    context.owner = PC.PresetController(PC.PresetPorts(lambda _: None,
        lambda: context.document, lambda: deepcopy(row['state']), replay,
        lambda: ('ok', ''), lambda: {'document_id': context.document},
        lambda: context.invalid.append(True), target_row=lambda: row,
        revision=lambda: context.revision, advance=advance,
        **{f'prepare_{family}': prepare, f'verify_{family}': verify,
           f'{family}_history_identity': history_identity}), context.events.append)
    context.reviews = context.owner.reviews
    return context


def prepare(context, **ports):
    return context.reviews.prepare(context.preset, context.row['state'], context.row,
        context.document, context.revision, None,
        **{'prepare_torso': context.prepare, 'verify_torso': context.verify, **ports})


def ack(plan):
    review = plan['torso_transfer']
    return [{'document_id': review['document_id'], 'revision': review['revision'],
             'before_sha256': review['before']['sha256'], 'after_sha256': review['after']['sha256']}]


def claim(context, plan, **kwargs):
    return context.reviews.claim(plan['preflight_token'], 'torso', context.row['state'],
        context.row, context.document, context.revision,
        **{'verify_torso': context.verify, 'torso_review_ack': ack(plan), **kwargs})


def command(context, action, request, **values):
    message = {'cmd': 'preset', 'action': action, 'id': 'torso',
        'document_id': context.document, 'request_id': request, **values}
    context.owner.handle_command(message); context.owner.finish(message)
    return context.events[-1]


@pytest.mark.parametrize('missing', ['both', 'prepare', 'verify'])
def test_torso_review_requires_both_full_target_ports_without_writes(tmp_path, missing):
    context = fixture(tmp_path); before = deepcopy(context.row)
    ports = {key: None for key in ('prepare_torso', 'verify_torso')
             if missing == 'both' or key.startswith(missing)}
    with pytest.raises(ValueError):prepare(context, **ports)
    assert context.row == before and not context.reviews.pending and not context.replays


@pytest.mark.parametrize('derived', [False, True])
def test_scalar_preflight_keeps_target_body_face_review_and_source_owned(tmp_path, derived):
    context = fixture(tmp_path, derived=derived); before = deepcopy(context.row)
    plan = prepare(context); record = context.reviews.pending[plan['preflight_token']]
    assert plan['applies'] == stored()['modules'] and plan['module_scope'] == [TORSO.OP]
    assert context.row == before and context.revision == '7' and not context.replays
    assert record['source_proof'] == SOURCE.row_proof(context.row)
    assert set(record['torso']) == REVIEW.FIELDS
    assert all('base64' not in record['torso'][side] for side in ('before', 'after'))
    assert all('base64' in plan['torso_transfer'][side] for side in ('before', 'after'))
    old_bank = BODY.bank(before['state']); new_bank = BODY.bank(context.calls[0][2])
    assert old_bank['support_assets'] == new_bank['support_assets']
    old = old_bank['bodies'][context.ref['body_instance_id']]
    new = new_bank['bodies'][context.ref['body_instance_id']]
    assert old['record'] == new['record'] and old['association'] == new['association']
    assert old['operations'][TORSO.OP]['review'] == new['operations'][TORSO.OP]['review']
    assert TORSO.params_of(context.calls[0][2]) == {'version': 1, 'amount': .75}


@pytest.mark.parametrize('invalid', ['missing', 'empty', 'object', 'duplicate', 'other-target',
    'wrong-revision', 'recipe-hashes', 'swapped-images', 'extra-field'])
def test_ack_is_exactly_one_frozen_target_image_pair_and_bad_ack_keeps_token(tmp_path, invalid):
    context = fixture(tmp_path); plan = prepare(context); value = ack(plan)
    if invalid == 'missing': value = None
    elif invalid == 'empty': value = []
    elif invalid == 'object': value = value[0]
    elif invalid == 'duplicate': value *= 2
    elif invalid == 'other-target': value[0]['document_id'] = 'other'
    elif invalid == 'wrong-revision': value[0]['revision'] = '8'
    elif invalid == 'recipe-hashes':
        value[0]['before_sha256'] = plan['torso_transfer']['before_sha256']
        value[0]['after_sha256'] = plan['torso_transfer']['candidate_sha256']
    elif invalid == 'swapped-images':
        value[0]['before_sha256'], value[0]['after_sha256'] = value[0]['after_sha256'], value[0]['before_sha256']
    else:value[0]['accepted'] = True
    before = deepcopy(context.row)
    result = command(context, 'apply', 'bad-ack', preflight_token=plan['preflight_token'], torso_review_ack=value)
    assert not result['success'] and not result['outcome_unknown']
    assert 'torso_review_ack' not in result and 'module_scope' not in result
    assert plan['preflight_token'] in context.reviews.pending
    assert context.row == before and context.revision == '7' and not context.replays


@pytest.mark.parametrize('changed', ['state', 'people', 'source', 'row-identity', 'revision', 'proof', 'verifier'])
def test_claim_cannot_follow_target_edits_identity_people_or_source_changes(tmp_path, changed):
    context = fixture(tmp_path); plan = prepare(context); ports = {}
    if changed == 'state':context.row['state']['_unselected'] = 'later edit'
    elif changed == 'people':context.row['people']['revision'] += 1
    elif changed == 'source':(tmp_path / 'synthetic-torso-original.bin').write_bytes(b'replaced')
    elif changed == 'row-identity':context.row['document_id'] = 'new-row'
    elif changed == 'revision':context.revision = '8'
    elif changed == 'proof':context.reviews.pending[plan['preflight_token']]['torso']['after']['base64'] = 'forbidden'
    else:ports['verify_torso'] = None
    with pytest.raises(ValueError):claim(context, plan, **ports)
    assert plan['preflight_token'] in context.reviews.pending and not context.replays


@pytest.mark.parametrize('amount', [0., .75])
def test_unreviewed_target_is_not_promoted_even_for_neutral_amount(tmp_path, amount):
    context = fixture(tmp_path, reviewed=False)
    context.preset['modules'][TORSO.OP]['amount'] = amount
    before = deepcopy(context.row)
    with pytest.raises(ValueError):prepare(context)
    assert context.row == before and not context.replays and not context.reviews.pending


def test_controller_strict_apply_receipt_and_identical_request_replay(tmp_path, monkeypatch):
    context = fixture(tmp_path); monkeypatch.setattr(PC.PS, 'find', lambda _: context.preset)
    before = deepcopy(context.row['state'])
    plan = command(context, 'preflight', 'preflight'); assert plan['success'], plan
    arguments = {'preflight_token': plan['preflight_token'], 'torso_review_ack': ack(plan)}
    result = command(context, 'apply', 'apply', **arguments)
    assert result['success'] and not result['outcome_unknown'] and context.revision == '8'
    assert result['module_scope'] == [TORSO.OP] and result['preflight_token'] == plan['preflight_token']
    assert result['torso_review_ack'] == ack(plan) and result['torso_review_ack'][0]['revision'] == '7'
    assert len(context.replays) == 1 and context.replays[0][1]['strict_local'] is True
    assert [entry[4] for entry in context.calls if entry[0] == 'verify'] == ['7', '7', '7', '8']
    assert context.calls[-1][1] == before and context.calls[-1][2] == context.row['state']
    repeated = command(context, 'apply', 'apply', **arguments)
    assert repeated['replayed'] and repeated['torso_review_ack'] == result['torso_review_ack']
    assert len(context.replays) == 1 and context.revision == '8'
    changed = deepcopy(arguments); changed['torso_review_ack'][0]['after_sha256'] = 'f' * 64
    rejected = command(context, 'apply', 'apply', **changed)
    assert not rejected['success'] and len(context.replays) == 1
    assert not command(context, 'apply', 'new-request', **arguments)['success']


@pytest.mark.parametrize('changed', ['state', 'people'])
def test_replay_drift_requires_strict_verified_rollback_and_preserves_ack_receipt(tmp_path, changed):
    context = fixture(tmp_path); plan = prepare(context); before = deepcopy(context.row['state'])
    native = context.owner.ports.replay
    def drifting_replay(value, **kwargs):
        result = native(value, **kwargs)
        if kwargs['mode'] == 'preset':
            if changed == 'state':context.row['state']['_unselected'] = 'unexpected replay edit'
            else:context.row['people']['revision'] += 1
        return result
    context.owner.ports = replace(context.owner.ports, replay=drifting_replay)
    result = command(context, 'apply', 'drift', preflight_token=plan['preflight_token'], torso_review_ack=ack(plan))
    assert not result['success'] and result['rolled_back'] is (changed == 'state')
    assert result['outcome_unknown'] is (changed == 'people')
    assert result['requires_reload'] is (changed == 'people') and bool(context.invalid) is (changed == 'people')
    assert result['torso_review_ack'] == ack(plan) and result['preflight_token'] == plan['preflight_token']
    assert result['module_scope'] == [TORSO.OP] and 'torso_transfer' not in result
    assert (context.row['state'] == before) is (changed == 'state')
    assert not context.row['undo'] and not context.row['redo']
    assert [entry[1]['mode'] for entry in context.replays] == (['preset', 'preset_rollback'] if changed == 'state' else ['preset'])
    assert all(entry[1]['strict_local'] is True for entry in context.replays)
    assert not any(event.get('event') == 'preset_applied' for event in context.events)


def test_no_token_apply_and_unrelated_ack_do_not_mutate(tmp_path, monkeypatch):
    context = fixture(tmp_path); monkeypatch.setattr(PC.PS, 'find', lambda _: context.preset)
    before = deepcopy(context.row)
    assert not command(context, 'apply', 'direct')['success']
    assert not command(context, 'preflight', 'stray-ack', torso_review_ack=[])['success']
    assert context.row == before and not context.replays and context.revision == '7'


@pytest.mark.parametrize('changed', ['row', 'revision', 'source'])
def test_rollback_never_replays_old_state_across_a_changed_target_fence(tmp_path, changed):
    context = fixture(tmp_path); plan = prepare(context)
    native = context.owner.ports.replay
    def drifting_replay(value, **kwargs):
        result = native(value, **kwargs)
        if changed == 'row':context.row['document_id'] = 'replaced-row'
        elif changed == 'revision':context.revision = '9'
        else:(tmp_path / 'synthetic-torso-original.bin').write_bytes(b'replaced-source')
        return result
    context.owner.ports = replace(context.owner.ports, replay=drifting_replay)
    result = command(context, 'apply', 'changed-target', preflight_token=plan['preflight_token'], torso_review_ack=ack(plan))
    assert not result['success'] and result['outcome_unknown'] and result['requires_reload']
    assert not result['rolled_back'] and context.invalid
    assert len(context.replays) == 1 and context.replays[0][1]['mode'] == 'preset'
    assert result['torso_review_ack'] == ack(plan)


def test_same_identity_replacement_row_never_receives_a_rollback_snapshot(tmp_path):
    context = fixture(tmp_path); plan = prepare(context)
    reviewed_row = context.row; native = context.owner.ports.replay; replacements = []
    def replacing_replay(value, **kwargs):
        result = native(value, **kwargs)
        context.row = deepcopy(context.row)
        replacements.append(deepcopy(context.row))
        return result
    context.owner.ports = replace(context.owner.ports, replay=replacing_replay,
        target_row=lambda: context.row, capture=lambda: deepcopy(context.row['state']))
    result = command(context, 'apply', 'same-identity-replacement',
        preflight_token=plan['preflight_token'], torso_review_ack=ack(plan))
    assert context.row is not reviewed_row and context.row == replacements[0]
    assert context.row['document_id'] == reviewed_row['document_id']
    assert context.row['path'] == reviewed_row['path'] and context.revision == '8'
    assert not result['success'] and result['outcome_unknown'] and result['requires_reload']
    assert not result['rolled_back'] and context.invalid
    assert len(context.replays) == 1 and len(replacements) == 1
    assert not any(event.get('event') == 'preset_applied' for event in context.events)


def test_same_identity_replacement_before_publish_never_receives_forward_snapshot(tmp_path):
    context = fixture(tmp_path); plan = prepare(context)
    reviewed_row = context.row; advance = context.owner.ports.advance; replacements = []
    def replacing_advance():
        advance()
        context.row = deepcopy(context.row)
        replacements.append(deepcopy(context.row))
    context.owner.ports = replace(context.owner.ports, advance=replacing_advance,
        target_row=lambda: context.row, capture=lambda: deepcopy(context.row['state']))
    result = command(context, 'apply', 'replacement-before-publish',
        preflight_token=plan['preflight_token'], torso_review_ack=ack(plan))
    assert context.row is not reviewed_row and context.row == replacements[0]
    assert context.row == reviewed_row and context.revision == '8'
    assert not result['success'] and result['outcome_unknown'] and result['requires_reload']
    assert not result['rolled_back'] and context.invalid and not context.replays


def test_claim_is_single_use_and_mixed_scope_is_rejected(tmp_path):
    context = fixture(tmp_path); plan = prepare(context); record = claim(context, plan)
    assert record['torso']['parameters'] == {'version': 1, 'amount': .75}
    with pytest.raises(ValueError):claim(context, plan)
    context.preset['modules'][SC.OP_CROP] = {'rect_normalized': [0., 0., 1., 1.], 'rotation_degrees': 0.}
    with pytest.raises(ValueError):prepare(context)
    assert not context.reviews.pending and not context.replays


@pytest.mark.parametrize('field', ['xmp_review_ack', 'spill_review_ack', 'shadow_review_ack'])
def test_torso_ack_cannot_carry_another_review_even_null(tmp_path, field):
    context = fixture(tmp_path); plan = prepare(context)
    result = command(context, 'apply', 'mixed-ack', preflight_token=plan['preflight_token'],
        torso_review_ack=ack(plan), **{field: None})
    assert not result['success'] and not result['outcome_unknown']
    assert plan['preflight_token'] in context.reviews.pending and not context.replays


def test_expired_token_and_xmp_torso_combination_refuse_before_writes(tmp_path):
    context = fixture(tmp_path); plan = prepare(context)
    context.reviews.pending[plan['preflight_token']]['expires'] = 0
    with pytest.raises(ValueError):claim(context, plan)
    assert not context.replays
    context.preset['xmp_import'] = {'source_sha256': 'e' * 64}
    with pytest.raises(ValueError):prepare(context)


@pytest.mark.parametrize('value', [None, []])
def test_unselected_torso_ack_does_not_consume_another_review_token(tmp_path, value):
    context = fixture(tmp_path)
    context.preset['modules'] = {SC.OP_CROP: {'rect_normalized': [0., 0., 1., 1.], 'rotation_degrees': 0.}}
    def prepare_crop(row, candidate, document_id, revision):
        return {'candidate_sha256': fingerprint(candidate), 'revision': revision}, {'fixture_only': True}
    def verify_crop(row, candidate, document_id, revision, record):
        if record != {'candidate_sha256': fingerprint(candidate), 'revision': revision}:
            raise ValueError('Synthetic crop candidate changed')
    context.owner.ports = replace(context.owner.ports, prepare_crop=prepare_crop, verify_crop=verify_crop)
    plan = prepare(context, prepare_crop=prepare_crop, verify_crop=verify_crop)
    result = command(context, 'apply', 'unselected-ack', preflight_token=plan['preflight_token'], torso_review_ack=value)
    assert not result['success'] and not result['outcome_unknown']
    assert plan['preflight_token'] in context.reviews.pending and not context.replays


def test_scalar_save_never_contains_body_face_or_support_data(tmp_path, monkeypatch):
    context = fixture(tmp_path); captured = []
    monkeypatch.setattr(PC.PS, 'save', lambda value, **kwargs: captured.append(deepcopy(value)) or 'fixture-only')
    result = context.owner.save({'id': 'saved-torso', 'name': 'Saved torso', 'module_scope': [TORSO.OP]})
    assert result['module_scope'] == [TORSO.OP]
    assert captured[0]['modules'] == {TORSO.OP: {'version': 1, 'amount': -.25}}


def test_receipt_size_fallback_retains_exact_review_binding(tmp_path, monkeypatch):
    context = fixture(tmp_path); plan = prepare(context)
    monkeypatch.setattr(PC, 'MAX_RESULT_BYTES', 1)
    result = command(context, 'apply', 'bounded', preflight_token=plan['preflight_token'], torso_review_ack=ack(plan))
    assert not result['success'] and result['outcome_unknown'] and result['error_code'] == 'receipt_too_large'
    assert result['module_scope'] == [TORSO.OP] and result['preflight_token'] == plan['preflight_token']
    assert result['torso_review_ack'] == ack(plan) and 'torso_transfer' not in result
    assert len(context.replays) == 1
