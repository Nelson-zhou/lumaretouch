# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN protocol, ownership and publication fixtures.

Synthetic graph evidence and fake display bytes deliberately mock the full
renderer, source decoder and manual-support admission. These fixtures do not
establish native correctness, actual photo quality or runtime acceptance.
No collection, imports, tests, inference, builds or downloads ran in authoring.
"""
from base64 import b64encode
from collections import OrderedDict
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from lumaretouch_engine import people_state as P, people_algorithms as A
from lumaretouch_engine import people_host_commands as H, people_edit as EDIT
from lumaretouch_engine import eye_bag_preserve_host as R, eye_bag_preserve_state as S
from lumaretouch_engine import eye_bag_preserve_support as SUPPORT
from lumaretouch_engine.eye_bag_preserve_project import require_unreviewed_transition

ASSET = 'a' * 64


def graph():
    state = P.empty()
    evidence = {'backend': 'mediapipe', 'detector_model_sha256': 'd' * 64,
        'semantic_model_sha256': 'e' * 64, 'landmark_digest': 'f' * 64,
        'status': 'verified', 'source_width': 128, 'source_height': 192,
        'orientation': 'exif_normalized_once'}
    face = P.new_face(ASSET, [.1, .1, .9, .9], evidence)
    state['faces'][face['face_instance_id']] = face
    target = {'scope': 'face', 'target_id': face['face_instance_id'], 'face_ref': P.face_ref(face)}
    return state, target


def eye():
    # Structural vectors only. The genuine raster/admission is mocked below.
    return {'recipe': {'version': 1, 'domain': 'source-normalized', 'objects': [{'id': 'paint-one', 'name': 'manual lower lid', 'enabled': True,
        'kind': 'brush', 'operation': 'add', 'opacity': 1., 'feather': 0.,
        'points': [[.3, .4], [.4, .4]], 'axes': [[.01, 0], [0, .01]]}]},
        'visible': True, 'unoccluded': True, 'ownership_confirmed': True}


def display(tag):
    raw = ('MOCK DISPLAY, NOT A PNG: ' + tag).encode()
    compact = {'mime': 'image/png', 'width': 64, 'height': 96, 'sha256': sha256(raw).hexdigest()}
    return compact, {**compact, 'base64': b64encode(raw).decode()}


@pytest.fixture
def host(monkeypatch):
    from lumaretouch_engine import face_style_alias_review as ALIASES
    from lumaretouch_engine import people_support_assets as BANK, body_pose_commands as BODY
    state, target = graph()
    row = {'document_id': 'doc-eye', 'document_revision': 4, 'path': '/fixture/photo.png',
        'state': {'source': ASSET, 'repair': 'saved-old'}, 'src_w': 128, 'src_h': 192}
    owner = SimpleNamespace(state=deepcopy(state), fence=7)
    owner.snapshot = lambda: deepcopy(owner.state)
    versions = SimpleNamespace(workspace='epoch-eye', version=lambda item: SimpleNamespace(
        document_id=item['document_id'], revision=item['document_revision']))
    engine = SimpleNamespace(_docs=[row], _doc_index=0, _load_id='load-eye',
        _people_scope_row=row, _people_graph_owner=owner, _people_active_context={'owner': owner},
        _people_targets={ASSET: deepcopy(target)}, _people_cursors={ASSET: target['target_id']},
        _people_support={}, _people_analyses={ASSET: {target['target_id']: {'analysis': 'real-boundary-mocked'}}},
        current={'source': ASSET, 'repair': 'committed-current', 'crop': [64, 96]},
        _vram=object(), _project=None, _people_receipts=OrderedDict(),
        _people_bind=Mock(side_effect=AssertionError('A read may not bind/migrate')), doc_state=Mock(return_value={}),
        _guard_editable=lambda _: None, render_calls=[])
    engine._people_owner = lambda: owner
    engine._people_preset_capture = lambda: deepcopy(engine.current)
    engine._document_versions = lambda: versions
    engine._people_source = lambda: {'sha256': engine.current['source'], 'width': 128, 'height': 192}
    engine._people_binding = lambda: {'document_id': row['document_id'], 'document_epoch': versions.workspace,
        'document_revision': row['document_revision'], 'asset_sha256': engine.current['source']}
    def source_proof(item):
        asset = item.get('state', {}).get('source', ASSET)
        return {'asset_sha256': asset, 'original_sha256': asset, 'creative_source': None}
    monkeypatch.setattr(R.SOURCE, 'row_proof', source_proof)
    monkeypatch.setattr(R.SOURCE, 'row_asset', lambda item: source_proof(item)['asset_sha256'])
    monkeypatch.setattr(R.SOURCE, 'record', lambda _: None)
    def verify_source(item, proof):
        if source_proof(item) != proof: raise ValueError('Changed effective source')
    monkeypatch.setattr(R.SOURCE, 'verify_row', verify_source)
    monkeypatch.setattr(ALIASES, 'verify_dormant', Mock())
    def key(actual, item, current, candidate):
        candidate = deepcopy(candidate); candidate['revision'] = 0
        return {'render_sha256': R.digest(current), 'graph_sha256': R.digest(candidate),
            'context_sha256': R.digest({'bank': actual._people_support, 'analysis': actual._people_analyses})}
    monkeypatch.setattr(R, 'snapshot_key', key)
    monkeypatch.setattr(BODY, 'source_preview', lambda _: {'mime': 'image/png', 'base64': 'MOCK',
        'width': 64, 'height': 96, 'source_sha256': ASSET, 'source_width': 128, 'source_height': 192,
        'decoded_width': 64, 'decoded_height': 96, 'mapping': 'normalized_full_frame',
        'orientation': 'exif_normalized_once'})
    from lumaretouch_engine import eye_bag_preserve_crop as CROP
    def crops(actual, graph, selected, current, source, snapshot_sha256, **kwargs):
        return {'version': 1, 'mapping': 'source_pixel_edges', 'orientation': 'exif_normalized_once',
            'display_encoding': 'srgb_rgb8', 'sampling': 'one_source_pixel_per_image_pixel',
            'source_sha256': source['sha256'], 'source_width': 128, 'source_height': 192,
            'snapshot_sha256': snapshot_sha256, 'input_stage': 'committed_repair',
            'eyes': {side: {'rect': [0, 0, 64, 96], 'image': display(side)[1]} for side in ('left', 'right')}}
    monkeypatch.setattr(CROP, 'prepare', crops)
    monkeypatch.setattr(BANK, 'check_store', lambda bank: deepcopy(bank))
    def retain(before, bank, ref, eyes, **kwargs):
        candidate = P.check(before); bank = deepcopy(bank)
        record = {'face_ref': ref, 'row': {'eyes': deepcopy(eyes)}}; support = R.digest(record)
        bank[support] = record
        candidate['faces'][ref['face_instance_id']]['local_assets'][S.KIND] = {
            'owner': ref, 'content_sha256': support, 'kind': S.KIND}
        candidate['revision'] += 1
        return candidate, bank
    monkeypatch.setattr(SUPPORT, 'retain', retain)
    def resolve_support(candidate, bank, ref):
        support = candidate['faces'][ref['face_instance_id']]['local_assets'][S.KIND]['content_sha256']
        return deepcopy(bank[support]), support
    monkeypatch.setattr(SUPPORT, 'resolve', resolve_support)
    def render(actual, item, current, candidate, document, revision, **kwargs):
        actual.render_calls.append((deepcopy(current), deepcopy(candidate)))
        compact, pixels = display(R.digest(candidate) + R.digest(current))
        return compact, pixels, {'source_proof': source_proof({**item, 'state': current}),
            'candidate_sha256': R.digest(current), 'people_sha256': R.digest(candidate),
            'source_size': [128, 192], 'output_size': [64, 96]}
    monkeypatch.setattr(R, 'render_image', render)
    monkeypatch.setattr(R, '_overlay', lambda *args: (*display('support'), {
        'source_width': 128, 'source_height': 192, 'decoded_width': 64, 'decoded_height': 96}))
    return engine, owner, row, state, target


def payload(amount=.4, *, replace=False, eyes=None):
    return {'recipe': {'version': 2, 'amount': amount, 'preserve': 1.},
        'eyes': {'left': eye()} if eyes is None else eyes, 'replace_legacy': replace}


def served_reference(engine, state, target):
    reference = R.reference(engine, state, target, {})
    crops = reference['source_crops']
    for side in ('left', 'right'):
        R.source_image(engine, state, target, {'token': crops['token'], 'side': side,
            'sha256': crops['eyes'][side]['image']['sha256']})
    return reference


def reviewed(host):
    engine, _, _, state, target = host
    served_reference(engine, state, target)
    return R.preview(engine, state, target, payload())['review']


def raw(engine, state, target, action, value, request='request-eye'):
    return {'cmd': 'people', 'action': action, 'payload': value, 'request_id': request,
        **{key: value for key, value in engine._people_binding().items() if key != 'asset_sha256'},
        'state_revision': state['revision'], 'association_revision': state['association_revision'], 'target': target}


def test_reference_and_preview_keep_existing_owner_graph_and_current_repair(host):
    engine, owner, _, state, target = host
    review = reviewed(host)
    assert review['version'] == 1 and 'members' not in review
    assert owner.snapshot() == state and owner.fence == 7 and engine._people_support
    assert len(engine.render_calls) == 2
    assert all(current['repair'] == 'committed-current' for current, _ in engine.render_calls)
    assert review['support_sha256'] in engine._people_support and review['face_ref'] == target['face_ref']
    assert 'base64' not in review['visual']['before'] and 'base64' not in review['support_overlay']
    engine._people_bind.assert_not_called()


def test_repeat_preview_accepts_only_its_own_append_only_bank_refresh(host):
    engine, _, _, state, target = host
    first = reviewed(host)
    second = R.preview(engine, state, target, payload(.6, eyes={'right': eye()}))['review']
    assert first['token'] != second['token'] and len(engine._people_support) == 2
    candidate, _ = R.confirm(engine, state, target, {'token': second['token'], 'ack': R._ack(second)})
    record, _ = SUPPORT.resolve(candidate, engine._people_support, target['face_ref'])
    assert set(record['row']['eyes']) == {'right'}
    with pytest.raises(ValueError): R.image(engine, state, target, {
        'token': first['token'], 'side': 'before', 'sha256': first['visual']['before']['sha256']})
    engine._people_support['c' * 64] = {'unexpected': 'append'}
    with pytest.raises(ValueError): R.preview(engine, state, target, payload(.7))


@pytest.mark.parametrize('change', ['repair', 'source', 'analysis', 'bank', 'graph', 'epoch', 'revision'])
def test_complete_snapshot_and_owner_fences_reject_stale_preview(host, change):
    engine, owner, row, state, target = host; review = reviewed(host)
    if change in ('repair', 'source'): engine.current[change] = 'changed' if change == 'repair' else 'b' * 64
    elif change == 'analysis': engine._people_analyses[ASSET][target['target_id']]['analysis'] = 'changed'
    elif change == 'bank': engine._people_support['b' * 64] = {'changed': True}
    elif change == 'graph': owner.state['revision'] += 1
    elif change == 'epoch': engine._document_versions().workspace = 'different-epoch'
    else: row['document_revision'] += 1
    with pytest.raises(ValueError): R.confirm(engine, state, target, {'token': review['token'], 'ack': R._ack(review)})
    assert not R.claimed(engine, review['token'])


def test_wrong_hash_ack_missing_image_and_single_use_claim(host):
    engine, owner, _, state, target = host; review = reviewed(host); token = review['token']
    with pytest.raises(ValueError): R.image(engine, state, target, {'token': token, 'side': 'support', 'sha256': '0' * 64})
    bad_ack = {**R._ack(review), 'support_overlay_sha256': '0' * 64}
    with pytest.raises(ValueError): R.confirm(engine, state, target, {'token': token, 'ack': bad_ack})
    store, entry = R._entry(engine, token)
    after = store['images'].plans[token][review['visual']['document_id']]['after']
    original_path = after['path']; after['path'] = original_path.with_name('missing.png')
    with pytest.raises(ValueError): R.confirm(engine, state, target, {'token': token, 'ack': R._ack(review)})
    assert not entry['claimed']; after['path'] = original_path
    command = {'token': token, 'ack': R._ack(review)}
    candidate, proof = R.confirm(engine, state, target, command)
    R.verify_before_publish(engine, state, target, command, candidate, proof)
    assert entry['claimed'] and owner.snapshot() == state
    with pytest.raises(ValueError): R.confirm(engine, state, target, command)


def test_legacy_replacement_is_explicit_atomic_and_preserves_old_graph(host):
    engine, owner, _, _, target = host
    owner.state = P.set_override(owner.state, 'face', target['target_id'], A.ENHANCE, '/eye_bags', .5)
    state = owner.snapshot(); served_reference(engine, state, target)
    with pytest.raises(ValueError): R.preview(engine, state, target, payload())
    review = R.preview(engine, state, target, payload(replace=True))['review']
    candidate, proof = R.confirm(engine, state, target, {'token': review['token'], 'ack': R._ack(review)})
    assert R._values(state, target)[1] == .5 and R._values(candidate, target)[1] == 0
    assert R._values(candidate, target)[0]['amount'] == .4 and proof['replace_legacy'] is True
    assert owner.snapshot() == state


def test_unestablished_shared_owner_and_unavailable_dormant_aliases_refuse(host, monkeypatch):
    from lumaretouch_engine import face_style_alias_review as ALIASES
    engine, _, row, state, target = host
    engine._docs.append({**deepcopy(row), 'document_id': 'alias'})
    with pytest.raises(ValueError): R.reference(engine, state, target, {})
    engine._docs.pop()
    monkeypatch.setattr(ALIASES, 'verify_dormant', Mock(side_effect=ValueError('unavailable retained source')))
    with pytest.raises(ValueError): R.reference(engine, state, target, {})


def test_read_receipt_echo_is_idempotent_and_never_emits_doc_state(host):
    engine, _, _, state, target = host
    command = raw(engine, state, target, 'eye_bag_reference', {}); events = []
    H.apply(engine, command, events.append); H.finish(engine, command, None, events.append)
    H.apply(engine, command, events.append); H.finish(engine, command, None, events.append)
    assert len(events) == 2 and events[0] == events[1] and events[0]['success']
    assert 'doc_state' not in events[0] and events[0]['eye_bag_request']['payload'] == {}
    engine._people_bind.assert_not_called(); engine.doc_state.assert_not_called()


@pytest.mark.parametrize('claimed', [False, True])
def test_preparation_refusal_vs_claimed_unknown_and_no_blind_retry(host, monkeypatch, claimed):
    engine, _, _, state, target = host; review = reviewed(host)
    command = raw(engine, state, target, 'eye_bag_confirm', {'token': review['token'], 'ack': R._ack(review)})
    def publication(*args, **kwargs):
        if claimed: kwargs['before_publish']()
        raise ValueError('mock publication boundary failure')
    publish = Mock(side_effect=publication); monkeypatch.setattr(H, 'publish', publish)
    events = []
    with pytest.raises(ValueError): H.apply(engine, command, events.append)
    H.finish(engine, command, 'mock publication boundary failure', events.append)
    H.apply(engine, command, events.append); H.finish(engine, command, None, events.append)
    assert publish.call_count == 1 and events[0] == events[1]
    assert events[0]['outcome_unknown'] is claimed and not events[0]['success']


def test_generic_patch_requires_review_but_reset_needs_neither_support_nor_native(host, monkeypatch):
    engine, owner, _, state, target = host
    def stage(before, patches):
        command = raw(engine, before, target, 'patch', {'patches': patches})
        return EDIT.stage({key: value for key, value in command.items() if key != 'cmd'}, before,
            document_id='doc-eye', document_epoch='epoch-eye', document_revision=4,
            asset_sha256=ASSET, source_dimensions=(128, 192))['state']
    patch = lambda path, value: {'operation_id': S.OP, 'parameter_path': path, 'value': value, 'unset': False}
    with pytest.raises(ValueError): stage(state, [patch('/amount', .5)])
    dormant = stage(state, [patch('/preserve', .25)])
    assert R._values(dormant, target)[0] == {'version': 2, 'amount': 0., 'preserve': .25}
    active = P.set_override(state, 'face', target['target_id'], S.OP, '/amount', .5)
    from lumaretouch_engine import eye_bag_preserve_native as NATIVE
    monkeypatch.setattr(SUPPORT, 'resolve', Mock(side_effect=AssertionError('Reset may not require support')))
    monkeypatch.setattr(NATIVE, 'native', Mock(side_effect=AssertionError('Reset may not load native')))
    reset = stage(active, [patch('/amount', 0.)])
    assert R._values(reset, target)[0]['amount'] == 0
    with pytest.raises(ValueError): stage(active, [patch('/preserve', .2)])


def test_shared_transition_guard_covers_enable_source_and_support_changes():
    state, target = graph(); key = target['target_id']
    active = P.set_override(state, 'face', key, S.OP, '/amount', .5)
    disabled = deepcopy(active); disabled['faces'][key]['enabled'] = False
    assert require_unreviewed_transition(state, disabled) == disabled
    with pytest.raises(ValueError): require_unreviewed_transition(disabled, active)
    for change in ('support', 'evidence', 'box'):
        candidate = deepcopy(active)
        if change == 'support': candidate['faces'][key]['local_assets'][S.KIND] = {
            'kind': S.KIND, 'owner': target['face_ref'], 'content_sha256': 'b' * 64}
        elif change == 'evidence': candidate['faces'][key]['evidence']['landmark_digest'] = 'c' * 64
        else: candidate['faces'][key]['box'] = [.2, .2, .8, .8]
        with pytest.raises(ValueError): require_unreviewed_transition(active, candidate)
    assert require_unreviewed_transition(active, active) == active


def test_missing_dormant_support_keeps_diagnostics_but_not_a_false_integrity_proof(host, monkeypatch):
    engine, owner, _, state, target = host
    owner.state['faces'][target['target_id']]['local_assets'][S.KIND] = {
        'owner': target['face_ref'], 'kind': S.KIND, 'content_sha256': 'b' * 64}
    state = owner.snapshot()
    monkeypatch.setattr(SUPPORT, 'resolve', Mock(side_effect=ValueError('missing immutable support')))
    view = R.report(engine, state, engine._people_source(), target['target_id'])
    assert view['recipe']['amount'] == 0 and view['support_error'] and not view['reviewed']
    monkeypatch.setattr(R, 'snapshot_key', Mock(side_effect=ValueError('persisted asset integrity requires recovery')))
    with pytest.raises(ValueError, match='integrity'): R.reference(engine, state, target, {})


def test_candidate_counter_is_exact_and_refuses_unsafe_document_increment(host):
    engine, _, row, state, target = host
    review = reviewed(host)
    candidate, proof = R.confirm(engine, state, target, {'token': review['token'], 'ack': R._ack(review)})
    assert review['candidate_state_revision'] == proof['candidate_state_revision'] == candidate['revision']
    row['document_revision'] = R.MAX_SAFE_REVISION
    R.reference(engine, state, target, {})
    with pytest.raises(ValueError): R.preview(engine, state, target, payload())


def test_postpublish_requires_exact_candidate_and_existing_owner_fence(host):
    engine, owner, row, state, target = host; review = reviewed(host)
    command = {'token': review['token'], 'ack': R._ack(review)}
    candidate, proof = R.confirm(engine, state, target, command)
    R.verify_before_publish(engine, state, target, command, candidate, proof)
    owner.state = deepcopy(candidate); owner.fence += 1; row['document_revision'] += 1
    R.verify_after_publish(engine, candidate, proof)
    owner.state['revision'] += 1
    with pytest.raises(ValueError): R.verify_after_publish(engine, candidate, proof)


def test_returned_source_reference_never_labels_original_path_pixels_as_current(host, monkeypatch):
    engine, _, _, state, target = host
    derived_proof = {'asset_sha256': ASSET, 'original_sha256': 'b' * 64,
        'creative_source': {'sha256': ASSET, 'width': 128, 'height': 192}}
    monkeypatch.setattr(R.SOURCE, 'row_proof', lambda _: deepcopy(derived_proof))
    monkeypatch.setattr(R.SOURCE, 'row_asset', lambda _: ASSET)
    reference = R.reference(engine, state, target, {})
    assert reference['source']['sha256'] == reference['source_preview']['source_sha256'] == ASSET
    assert engine._eye_bag_reference['source'] == derived_proof


def test_exact_read_classifier_excludes_confirm_malformed_masks_and_extra_fields(host):
    engine, _, _, state, target = host
    for action, value in [('eye_bag_reference', {}), ('eye_bag_preview', payload()),
            ('eye_bag_image', {'token': 'a' * 32, 'side': 'support', 'sha256': 'b' * 64})]:
        command = raw(engine, state, target, action, value)
        assert H.eye_bag_read_only(command) and not H.face_style_read_only(command)
        assert not H.eye_bag_read_only({**command, 'extra': True})
    assert not H.eye_bag_read_only(raw(engine, state, target, 'eye_bag_confirm', {}))
    bad = payload(); bad['eyes']['left']['recipe']['objects'][0]['operation'] = 'intersect'
    assert not H.eye_bag_read_only(raw(engine, state, target, 'eye_bag_preview', bad))


def test_read_failure_preserves_existing_recovery_state_and_confirm_does_not_coalesce(host):
    from lumaretouch_engine import project_recovery_runtime as RECOVERY, history_policy as HISTORY
    engine, _, _, state, target = host
    engine._project_recovery_runtime = SimpleNamespace(tainted=True, reason='existing', revision=8)
    command = raw(engine, state, target, 'eye_bag_reference', {})
    RECOVERY.finish(engine, {'message': command, 'started': True, 'returned': False, 'failed': True}, 'read refused')
    assert vars(engine._project_recovery_runtime) == {'tainted': True, 'reason': 'existing', 'revision': 8}
    command['action'] = 'eye_bag_confirm'
    assert HISTORY.command_group('people', command) != HISTORY.command_group('people', {
        **command, 'request_id': 'another-reviewed-confirmation'})


def test_cross_owner_create_update_unlink_cannot_introduce_active_unreviewed_output():
    from lumaretouch_engine import people_cross_owner as CROSS
    state, target = graph(); _, remote_target = graph()
    members = [{'document_id': 'doc-local', 'scope_id': 'project', 'original_sha256': ASSET,
        'ref': target['face_ref']}, {'document_id': 'doc-remote', 'scope_id': 'doc-remote',
        'original_sha256': ASSET, 'ref': remote_target['face_ref']}]
    def capsule(amount):
        return CROSS.descriptor('association-eye', 'doc-local', members,
            [{'op': S.OP, 'path': '/amount', 'value': amount}])
    created = CROSS.create(state, 'person-eye', capsule(.5))
    with pytest.raises(ValueError): require_unreviewed_transition(state, created)
    updated = CROSS.update(created, 'person-eye', capsule(.6))
    with pytest.raises(ValueError): require_unreviewed_transition(created, updated)
    # Unlink may expose a previously shadowed photograph-wide active amount.
    inherited = P.set_override(state, 'all_people', ASSET, S.OP, '/amount', .7)
    suppressed = CROSS.create(inherited, 'person-eye', capsule(0.))
    revealed = CROSS.unlink(suppressed, 'person-eye')
    with pytest.raises(ValueError): require_unreviewed_transition(suppressed, revealed)
    # Removing active intent to genuine zero remains an ordinary safe reset.
    reset = CROSS.unlink(created, 'person-eye')
    assert require_unreviewed_transition(created, reset) == reset
    swapped = deepcopy(created)
    swapped['faces'][target['target_id']]['local_assets'][S.KIND] = {
        'owner': target['face_ref'], 'kind': S.KIND, 'content_sha256': 'c' * 64}
    with pytest.raises(ValueError): require_unreviewed_transition(created, swapped)


def test_cross_owner_source_guard_is_after_every_candidate_and_before_render():
    """Source-only wiring assertion, not execution of a real association."""
    source = (Path(__file__).parents[1] / 'src/lumaretouch_engine/people_cross_owner_workflow.py').read_text()
    prepare = source[source.index('def prepare('):source.index('\ndef _public(')]
    guard = prepare.index("require_unreviewed_transition(item['before'], candidate)")
    for operation in ('C.create(', 'C.update(', 'C.unlink('):
        assert prepare.index(operation) < guard
    assert guard < prepare.index("render(engine, item['row'], candidate)")


def test_native_crop_pages_are_hash_bound_and_required_before_painted_review(host):
    engine, _, _, state, target = host
    reference = R.reference(engine, state, target, {})
    crops = reference['source_crops']
    assert all('base64' not in record['image'] for record in crops['eyes'].values())
    assert all(type(raw) is bytes for raw in engine._eye_bag_reference['crop_images'].values())
    with pytest.raises(ValueError, match='Load each painted eye'):
        R.preview(engine, state, target, payload())
    request = {'token': crops['token'], 'side': 'left', 'sha256': crops['eyes']['left']['image']['sha256']}
    with pytest.raises(ValueError):
        R.source_image(engine, state, target, {**request, 'sha256': '0' * 64})
    page = R.source_image(engine, state, target, request)
    assert page['snapshot_sha256'] == crops['snapshot_sha256']
    assert R.preview(engine, state, target, payload())['review']
    with pytest.raises(ValueError, match='Load each painted eye'):
        R.preview(engine, state, target, payload(eyes={'right': eye()}))


def test_native_crop_expiry_and_repair_change_release_cached_bytes(host, monkeypatch):
    engine, _, _, state, target = host
    reference = served_reference(engine, state, target)
    crops = reference['source_crops']
    request = {'token': crops['token'], 'side': 'left', 'sha256': crops['eyes']['left']['image']['sha256']}
    engine.current['repair'] = 'different'
    with pytest.raises(ValueError): R.source_image(engine, state, target, request)
    assert engine._eye_bag_reference is None
    reference = served_reference(engine, state, target)
    engine._eye_bag_reference['expires'] = 0
    with pytest.raises(ValueError): R.source_image(engine, state, target, request)
    assert engine._eye_bag_reference is None


@pytest.mark.parametrize('pipeline_present', [True, False])
def test_actual_finish_cancelled_read_has_native_terminal_shape(host, pipeline_present):
    engine, owner, _, state, target = host
    request = {'cmd': 'people', 'action': 'eye_bag_preview', 'request_id': 'read-cancelled',
        'document_id': 'doc-eye', 'document_epoch': 'epoch-eye', 'document_revision': 4,
        'state_revision': state['revision'], 'association_revision': state['association_revision'],
        'target': target, 'payload': payload()}
    engine._vram = object() if pipeline_present else None
    engine._people_receipts[request['request_id']] = {'success': False,
        'before_fence': owner.fence, 'eye_bag_cancelled': True,
        'payload': {'review': 'late-result-must-not-escape'}}
    output = []
    H.finish(engine, request, 'Eye-bag read stopped after cancellation', output.append)
    result = output[-1]
    assert result['eye_bag_cancelled'] is True
    assert result['success'] is False and result['outcome_unknown'] is False
    assert isinstance(result['error'], str) and result['frame_emitted'] is False
    assert not {'payload', 'doc_state', 'batch_id', 'created_id'} & result.keys()
    assert result['eye_bag_request'] == {key: request[key] for key in (
        'action','document_id','document_epoch','document_revision','state_revision',
        'association_revision','target','payload')}
    assert engine._people_receipts[request['request_id']]['result'] == result


def test_actual_finish_changed_fence_cannot_claim_cancelled_success(host):
    engine, owner, _, state, target = host
    request = {'cmd': 'people', 'action': 'eye_bag_preview', 'request_id': 'read-fence-changed',
        'document_id': 'doc-eye', 'document_epoch': 'epoch-eye', 'document_revision': 4,
        'state_revision': state['revision'], 'association_revision': state['association_revision'],
        'target': target, 'payload': payload()}
    engine._people_receipts[request['request_id']] = {'success': False,
        'before_fence': owner.fence - 1, 'eye_bag_cancelled': True}
    engine._vram = None
    output = []; H.finish(engine, request, 'Unexpected fence change', output.append)
    assert output[-1]['outcome_unknown'] is True
    assert 'eye_bag_cancelled' not in output[-1]
