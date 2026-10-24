# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN. Synthetic ownership/wire fixtures, not photographic QA."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
import json

import pytest

from lumaretouch_engine import eye_bag_recovery_alias_review as R
from lumaretouch_engine import eye_bag_recovery_alias_controller as C
from lumaretouch_engine import people_state as P, people_support_assets as BANK


def vector_fixture():
    graph = P.empty(); source = {'sha256': 'a' * 64, 'width': 100, 'height': 120}
    evidence = {'backend': 'mediapipe', 'detector_model_sha256': 'c' * 64,
        'semantic_model_sha256': 'd' * 64, 'landmark_digest': 'e' * 64, 'status': 'verified',
        'source_width': 100, 'source_height': 120, 'orientation': 'exif_normalized_once'}
    face = P.new_face(source['sha256'], [.1, .1, .9, .9], evidence)
    graph['faces'][face['face_instance_id']] = face; ref = P.face_ref(face)
    row = {'target': R.TARGET, 'enabled': True, 'owner': {'version': 1,
        'source_sha256': source['sha256'], 'landmarks_sha256': evidence['landmark_digest'], 'backend': 'mediapipe'},
        'recipe': {'version': 1, 'domain': 'source-normalized', 'objects': [{
            'id': 'recover-one', 'name': 'Recovery', 'kind': 'brush', 'enabled': True,
            'operation': 'add', 'opacity': 1., 'feather': 0., 'points': [[.3, .4], [.4, .4]],
            'axes': [[.01, 0], [0, .01]]}]}}
    candidate, assets = BANK.retain(graph, {}, ref, source, row)
    return {'context': {'face_ref': ref, 'source': source}, 'before': graph,
        'candidate': candidate, 'assets': assets, 'target': R.TARGET, 'no_change': False}


def test_recovery_candidate_changes_only_its_source_owned_pointer():
    transaction = vector_fixture(); R._narrow(transaction, {})
    ref = transaction['context']['face_ref']
    assert BANK.resolve(transaction['candidate'], transaction['assets'], ref, R.TARGET) is not None
    changed = deepcopy(transaction)
    changed['candidate']['faces'][ref['face_instance_id']]['enabled'] = False
    with pytest.raises(ValueError): R._narrow(changed, {})
    changed = deepcopy(transaction); changed['target'] = 'eye_detail'
    with pytest.raises(ValueError, match='another effect'): R._narrow(changed, {})
    changed = deepcopy(transaction); changed['candidate']['association_revision'] += 1
    with pytest.raises(ValueError, match='only this face'): R._narrow(changed, {})


def test_clear_detaches_only_pointer_and_keeps_undo_bytes():
    created = vector_fixture(); before = created['candidate']; bank = created['assets']; ref = created['context']['face_ref']
    cleared = {**created, 'before': before, 'candidate': BANK.detach(before, ref, R.TARGET)}
    R._narrow(cleared, bank)
    assert cleared['assets'] == bank
    assert BANK.resolve(before, bank, ref, R.TARGET) is not None
    assert BANK.resolve(cleared['candidate'], bank, ref, R.TARGET) is None


def test_generic_boolean_or_foreign_private_admission_is_refused():
    for value in (True, {'strict': False}, object()):
        with pytest.raises(ValueError, match='private exact-source'):
            R.validate_admission(object(), value, {}, {})


def test_singleton_stays_strict_and_only_private_alias_permit_relaxes_it(monkeypatch):
    from lumaretouch_engine import people_recovery as PEOPLE, eye_bag_effect_recovery as EYE
    from lumaretouch_engine import eye_bag_preserve_host as HOST
    transaction = vector_fixture(); ref = transaction['context']['face_ref']; source = transaction['context']['source']
    monkeypatch.setattr(PEOPLE, 'selection', lambda *args, **kwargs: (source, transaction['before'], None, ref))
    seen = []; permits = []
    def live(engine, graph, target, *, strict=True):
        seen.append(strict)
        return None, {'path': 'own'}, {}, {'asset_sha256': source['sha256']}, SimpleNamespace(revision=1)
    monkeypatch.setattr(HOST, '_live', live)
    monkeypatch.setattr(R, 'validate_admission', lambda engine, permit, graph, target: permits.append(permit))
    permit = object(); EYE.live(object()); EYE.live(object(), _alias_admission=permit)
    assert seen == [True, False] and permits == [permit]


def image_metadata(label):
    raw = label.encode()
    return {'mime': 'image/png', 'width': 20, 'height': 10, 'sha256': sha256(raw).hexdigest()}


def review_entry():
    members = []
    for index in range(2):
        visual = {'document_id': str(index + 1) * 32, 'revision': str(index + 3),
            'before': image_metadata('before' + str(index)), 'after': image_metadata('after' + str(index))}
        members.append({'visual': visual})
    return {'members': members, 'review': {'token': 'f' * 32, 'review_sha256': 'a' * 64, 'members': members}, 'served': set()}


def test_exact_order_and_every_immutable_page_required_for_ack(monkeypatch):
    entry = review_entry(); ack = R.acknowledgment(entry)
    monkeypatch.setattr(R, 'verify', lambda *args: None)
    monkeypatch.setattr(R, '_cache', lambda engine: SimpleNamespace(read=lambda *args: None))
    with pytest.raises(ValueError, match='Load every'): R.confirm(object(), entry, ack)
    entry['served'] = {(member['visual']['document_id'], side) for member in entry['members'] for side in ('before', 'after')}
    R.confirm(object(), entry, ack)
    altered = deepcopy(ack); altered['members'].reverse()
    with pytest.raises(ValueError, match='frozen order'): R.confirm(object(), entry, altered)
    def corrupt(*args): raise ValueError('immutable image changed')
    monkeypatch.setattr(R, '_cache', lambda engine: SimpleNamespace(read=corrupt))
    with pytest.raises(ValueError, match='immutable image'): R.confirm(object(), entry, ack)


def test_image_page_cannot_substitute_revision_or_member(monkeypatch):
    entry = review_entry(); visual = entry['members'][0]['visual']
    monkeypatch.setattr(R, 'verify', lambda *args: None)
    monkeypatch.setattr(R, '_cache', lambda engine: SimpleNamespace(read=lambda *args: {'base64': 'actual'}))
    request = {'member_document_id': visual['document_id'], 'member_revision': visual['revision'],
        'side': 'before', 'sha256': visual['before']['sha256'], 'review_sha256': entry['review']['review_sha256']}
    assert R.image(object(), entry, request) == {'base64': 'actual'}
    assert entry['served'] == {(visual['document_id'], 'before')}
    with pytest.raises(ValueError, match='exact member'):
        R.image(object(), entry, {**request, 'member_revision': '99'})
    with pytest.raises(ValueError, match='another complete review'):
        R.image(object(), entry, {**request, 'review_sha256': 'b' * 64})


def test_each_full_render_uses_own_recipe_and_staged_candidate_bank(monkeypatch):
    from lumaretouch_engine import full_candidate_render as FULL
    transaction = vector_fixture(); engine = SimpleNamespace(_people_support={'old': 'retained'})
    rows = [{'path': 'one', 'document_id': '1' * 32}, {'path': 'two', 'document_id': '2' * 32}]
    recipes = [{'crop': 'left', 'repair': 'own-one'}, {'crop': 'right', 'repair': 'own-two'}]
    source = {'asset_sha256': 'a' * 64}; members = [(row, recipe, source,
        SimpleNamespace(document_id=row['document_id'], revision=index + 1)) for index, (row, recipe) in enumerate(zip(rows, recipes))]
    permit = SimpleNamespace(row=rows[0]); live = (None, rows[0], recipes[0], source, members[0][3])
    monkeypatch.setattr(R, '_narrow', lambda *args: None)
    monkeypatch.setattr(R, 'validate_admission', lambda *args: live)
    monkeypatch.setattr(R.CLOSURE, '_eligible', lambda *args: members)
    monkeypatch.setattr(R, '_dormant_key', lambda *args: 'closure')
    monkeypatch.setattr(R, 'verify', lambda *args: None)
    engine._batch_controller = lambda: object()
    monkeypatch.setattr(R, '_targets', lambda *args: {str(i): {'document_id': row['document_id']} for i, row in enumerate(rows)})
    def proof(row, recipe, side):
        return {'document_id': row['document_id'], 'candidate_sha256': R.digest(recipe),
            'people_sha256': side, 'source_proof': source}
    def identity(engine, row, recipe, version, candidate):
        return {'before': proof(row, recipe, 'before'), 'after': proof(row, recipe, 'after'), 'path_stamp': [1, 2]}, {
            'people_graph': candidate['candidate'], 'people_support_assets': candidate['assets']}
    monkeypatch.setattr(R, '_identity', identity); calls = []
    def render(engine, row, recipe, document, revision, **kwargs):
        calls.append((row, deepcopy(recipe), deepcopy(kwargs)))
        side = 'after' if 'staged_people_context' in kwargs else 'before'
        return side, {**proof(row, recipe, side), 'source_size': [100, 120], 'output_size': [20, 10]}
    monkeypatch.setattr(FULL, 'render', render)
    monkeypatch.setattr(R, '_display', lambda rgb, proof: (image_metadata(rgb), {**image_metadata(rgb), 'base64': rgb}))
    saved = {}
    cache = SimpleNamespace(prune=lambda pending: None, attach=lambda plan, displays: saved.update(displays))
    monkeypatch.setattr(R, '_cache', lambda engine: cache)
    result, entry = R.preview(engine, transaction, permit)
    assert [call[1] for call in calls] == [recipes[0], recipes[0], recipes[1], recipes[1]]
    assert all('staged_people_context' not in calls[index][2] for index in (0, 2))
    assert all(calls[index][2]['staged_people_context']['people_support_assets'] == transaction['assets'] for index in (1, 3))
    assert engine._people_support == {'old': 'retained'}
    assert set(saved) == {row['document_id'] for row in rows}
    assert result['review']['visual'] == result['review']['members'][0]['visual']
    assert 'prepared' not in entry['transaction']


def request():
    ack = R.acknowledgment(review_entry())
    return {'cmd': 'effect_recovery', 'action': 'apply', 'protocol': 2, 'request_id': 'request-one',
        'preview_id': 'a' * 32, 'document_id': '7', 'capture_id': 'b' * 32, 'ticket': '9',
        'generation': '11', 'recipe_document_id': '1' * 32, 'recipe_revision': '3', 'ack': ack}


def test_protocol_two_does_not_authorize_generic_or_partial_requests():
    p = request(); assert C.check_apply_request(p) is True
    for altered in ({**p, 'target': 'eye_detail'}, {**p, 'protocol': True}, {**p, 'ack': {'review_sha256': 'a' * 64, 'members': []}}):
        with pytest.raises(ValueError): C.check_apply_request(altered)
    assert C.prepared(object(), {'result': {'protocol': 2}}) is False


def test_noop_tuple_never_claims_or_enters_ordinary_rollback(monkeypatch):
    from lumaretouch_engine import eye_bag_recovery_alias_transaction as T
    p = request(); entry = {'review': {}, 'targets': {}, 'before_assets': {}, 'claimed': False}
    pending = {'result': {'request_id': p['request_id']}, 'request': p, 'recovery_alias': entry,
        'stage': SimpleNamespace(people_recovery={'assets': {}}), 'started': False}
    monkeypatch.setattr(C, 'prepared', lambda *args: True)
    monkeypatch.setattr(R, '_plans', lambda entry: {})
    monkeypatch.setattr(T, 'commit', lambda *args, **kwargs: (None, None))
    C.apply(object(), pending)
    assert pending['started'] is False and entry['claimed'] is False
    assert pending['result']['success'] is False and pending['result']['outcome_unknown'] is False
    assert 'batch_id' not in pending['result']


@pytest.mark.parametrize('started,rolled_back,late', [(False, False, False), (True, True, False),
    (True, False, False), (True, False, True)])
def test_failure_receipt_distinguishes_no_write_compensation_and_unknown(monkeypatch, started, rolled_back, late):
    from lumaretouch_engine import eye_bag_recovery_alias_transaction as T
    entry = review_entry(); entry.update(targets={}, before_assets={}, claimed=False)
    p = request(); pending = {'result': {'request_id': p['request_id']}, 'request': p, 'recovery_alias': entry,
        'stage': SimpleNamespace(people_recovery={'assets': {}}), 'started': False}
    error = ValueError('publication interrupted'); error.side_effects_started = started
    error.rolled_back = rolled_back; error.requires_reload = started and not rolled_back
    if late:
        error.batch_id = 'saved-ledger'
        error.eye_bag_recovery_alias_review = {'version': 1, 'review_sha256': entry['review']['review_sha256'], 'member_count': 2}
        error.alias_members = [{'document_id': member['visual']['document_id'],
            'expected_revision': member['visual']['revision'],
            'result_revision': str(int(member['visual']['revision']) + 1)} for member in entry['members']]
    def fail(*args, **kwargs): raise error
    monkeypatch.setattr(C, 'prepared', lambda *args: True)
    monkeypatch.setattr(R, '_plans', lambda entry: {})
    monkeypatch.setattr(T, 'commit', fail)
    C.apply(object(), pending)
    result = pending['result']
    assert result['success'] is False and result['no_write'] is (not started)
    assert result['outcome_unknown'] is (started and not rolled_back)
    assert pending['started'] is started and entry['claimed'] is started
    if late:
        assert result['batch_id'] == 'saved-ledger'
        assert result['eye_bag_recovery_alias_review'] == error.eye_bag_recovery_alias_review
        assert result['alias_members'] == error.alias_members
    else:
        assert not {'batch_id', 'alias_members', 'eye_bag_recovery_alias_review'} & result.keys()


def test_cleanup_failure_preserves_original_terminal_receipt(monkeypatch):
    from lumaretouch_engine.effect_recovery_controller import RecoveryController
    state = {'document_id': '7', 'history': {'undo_steps': 0, 'redo_steps': 0}}
    owner = RecoveryController(SimpleNamespace(doc_state=lambda: state), lambda event: emitted.append(deepcopy(event)))
    emitted = []; p = request(); result = {'event': 'effect_recovery_result', 'protocol': 2,
        'action': 'apply', 'request_id': p['request_id'], 'document_id': '7', 'success': True,
        'outcome_unknown': False, 'requires_reload': False, 'batch_id': 'actual-batch'}
    owner.pending = {'result': result, 'digest': 'digest', 'started': True, 'recovery_alias': {}}
    def failed_cleanup(*args): raise OSError('temporary cache unavailable')
    monkeypatch.setattr(C, 'finish', failed_cleanup)
    owner.finish(p)
    assert emitted[-1]['success'] is True and emitted[-1]['batch_id'] == 'actual-batch'
    assert owner.cache[p['request_id']][1] == emitted[-1]


def test_source_wiring_keeps_singleton_and_alias_history_separate():
    root = Path(__file__).parents[1] / 'src' / 'lumaretouch_engine'
    single = (root / 'eye_bag_effect_recovery.py').read_text()
    shared = (root / 'eye_bag_recovery_alias_review.py').read_text()
    controller = (root / 'effect_recovery_controller.py').read_text()
    assert 'strict=_alias_admission is None' in single
    assert "preview_size(proof['output_size'])" in shared
    assert "staged_people_context=staged" in shared
    assert controller.index("if 'recovery_alias' in pending:") < controller.index("previous = S.check")
    assert 'effect_recovery_rollback' not in (root / 'eye_bag_recovery_alias_controller.py').read_text()
