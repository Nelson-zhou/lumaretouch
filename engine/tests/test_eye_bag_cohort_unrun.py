# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: persistent eye-bag cohort staging/review/store/history.

Graph functions are production functions in these future fixtures. Endpoint I/O,
renderer dependencies and image production are explicitly mocked. Synthetic
NON-PNG bytes test transport identity only, never photographic or native quality.
No imports, test collection, execution, inference, build or typecheck were run.
"""
from base64 import b64encode
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
from types import SimpleNamespace
import json
import pytest
from lumaretouch_engine import people_state as S, people_algorithms as A
from lumaretouch_engine import people_cross_owner_workflow as W, people_cross_owner as C
from lumaretouch_engine import eye_bag_preserve_state as EYE
from lumaretouch_engine import eye_bag_cohort_review as R, eye_bag_cohort_store as STORE
from lumaretouch_engine import eye_bag_cohort_history as HISTORY, batch_preflight as B
from lumaretouch_engine import collarbone_transfer_review as VISUAL
from lumaretouch_engine.people_graph_patch import between, apply
from lumaretouch_engine.people_resolver import resolve
from lumaretouch_engine.batch_preflight_controller import FrozenBatchController


def rows():
    out = []
    for index, letter in enumerate(('a', 'b', 'c')):
        doc = 'member-' + letter; graph = S.empty()
        face = S.new_face(letter * 64, [.1, .1, .8, .9], {'backend': 'authored-fixture',
            'detector_model_sha256': 'd' * 64, 'semantic_model_sha256': None, 'landmark_digest': 'e' * 64,
            'status': 'verified', 'source_width': 128, 'source_height': 160, 'orientation': 'exif_normalized_once'})
        graph['faces'][face['face_instance_id']] = face; ref = S.face_ref(face)
        if index == 0:
            for path, value in (('/amount', .6), ('/preserve', .8)):
                graph = S.set_override(graph, 'face', ref['face_instance_id'], EYE.OP, path, value)
            graph = S.set_override(graph, 'face', ref['face_instance_id'], 'lnx.deform.v1', '/slim_face', .2)
        else:
            graph = S.set_override(graph, 'face', ref['face_instance_id'], A.ENHANCE, '/eye_bags', .3)
        proof = {'document': {'document_id': doc, 'epoch': 'workspace', 'revision': 3}, 'people_scope': doc,
            'state_revision': graph['revision'], 'association_revision': graph['association_revision'],
            'graph_sha256': W.I.graph_digest(graph),
            'source_proof': {'original_sha256': letter * 64, 'asset_sha256': letter * 64, 'creative_source': None}}
        out.append({'index': index, 'row': {'path': '/' + doc, 'document_id': doc, 'state': {}, 'src_w': 128, 'src_h': 160},
            'before': graph, 'proof': proof, 'ref': ref,
            'member': {'document_id': doc, 'scope_id': doc, 'original_sha256': letter * 64, 'ref': ref}})
    return out


def request(items, operation='create', *, eye=True):
    return {'target_policy': 'persistent_association', 'operation': operation, 'association_id': 'cohort',
        'source_ref': deepcopy(items[0]['ref']), 'source': deepcopy(items[0]['proof']),
        'targets': [{'target': deepcopy(item['proof']), 'target_refs': [deepcopy(item['ref'])]} for item in items[1:]],
        'selection': {} if operation == 'unlink' else {EYE.OP: ['/amount', '/preserve']},
        **({'eye_bag_cohort': {'version': 1, 'members': [{'document_id': item['member']['document_id'],
            'replace_legacy': index != 0} for index, item in enumerate(items)]}} if eye else {})}


def stage(monkeypatch, items, selected):
    documents = [item['row'] for item in items]; by_id = {item['member']['document_id']: item for item in items}
    engine = SimpleNamespace(_docs=documents, _batch_controller=lambda: SimpleNamespace(documents=SimpleNamespace(rows=lambda: documents)),
        _document_versions=lambda: SimpleNamespace(version=lambda row: SimpleNamespace(document_id=row['document_id'])))
    with monkeypatch.context() as patch:
        patch.setattr(W, '_endpoint', lambda engine, actual, proof, ref, **kw: deepcopy(by_id[proof['document']['document_id']]))
        patch.setattr(W.I, 'verify', lambda *a, **k: None)
        patch.setattr(W.SOURCE, 'verify_row', lambda *a, **k: None)
        patch.setattr(W.V, 'row_snapshot', lambda engine, row: by_id[row['document_id']]['before'])
        patch.setattr(R, 'closure', lambda *a: None)  # I/O/dormant closure tested separately.
        return W.prepare(engine, selected, validate=False)


def accept(items, candidates):
    for item, prepared in zip(items, candidates):
        item['before'] = deepcopy(prepared['candidate'])
        item['proof'].update(state_revision=item['before']['revision'], association_revision=item['before']['association_revision'],
            graph_sha256=W.I.graph_digest(item['before']))


def test_create_preserves_v1_capsule_and_all_selected_mixed_intent(monkeypatch):
    items = rows(); selected = request(items); selected['selection']['lnx.deform.v1'] = ['/slim_face']
    original = deepcopy(items); staged, review = stage(monkeypatch, items, selected)
    assert items == original and len(review['intent']) == 3
    for item in staged:
        capsule = item['candidate']['persons']['cohort']['cross_owner']
        assert capsule['version'] == 1 and capsule['intent'] == review['intent']
        assert set(capsule) == {'version', 'association_id', 'generation', 'local_document_id', 'members', 'intent'}
        assert item['candidate']['faces'] == item['before']['faces']
        values = A.recipes(resolve(item['candidate'], item['ref']['face_instance_id'], A.defaults()))
        assert values[EYE.OP]['amount'] == .6 and values[A.ENHANCE]['eye_bags'] == 0
        assert item['eye_bag_cohort_state']['after']['amount'] == .6
    assert staged[0]['eye_bag_cohort_state']['before'] == staged[0]['eye_bag_cohort_state']['after']
    assert between(staged[0]['before'], staged[0]['candidate'])  # Membership change is not a visual no-op.


def test_generic_retained_patch_and_unlink_cannot_bypass_full_review(monkeypatch):
    items = rows(); created, _ = stage(monkeypatch, items, request(items)); accept(items, created)
    generic = request(items, 'patch', eye=False); generic['selection'] = {'lnx.deform.v1': ['/slim_face']}
    with pytest.raises(ValueError, match='complete before/after review'): stage(monkeypatch, items, generic)
    with pytest.raises(ValueError, match='complete before/after review'): stage(monkeypatch, items, request(items, 'unlink', eye=False))
    reviewed = request(items, 'unlink'); unlinked, review = stage(monkeypatch, items, reviewed)
    assert R.required(unlinked, reviewed, review) and reviewed['selection'] == {}
    assert all(not item['candidate']['persons'] for item in unlinked)
    assert unlinked[0]['eye_bag_cohort_state']['after']['amount'] == .6  # Explicit source face value still wins.
    assert all(item['eye_bag_cohort_state']['after']['amount'] == 0 for item in unlinked[1:])
    assert all(item['eye_bag_cohort_state']['before']['amount'] == .6 for item in unlinked)


def test_actual_retained_active_without_eye_capsule_or_selection_requires_review():
    item = rows()[0]; item['candidate'] = deepcopy(item['before'])
    selected = {'selection': {'lnx.deform.v1': ['/slim_face']}}
    assert R.required([item], selected, {'intent': [{'op': 'lnx.deform.v1', 'path': '/slim_face', 'value': .2}]})
    item['before'] = S.set_override(item['before'], 'face', item['ref']['face_instance_id'], EYE.OP, '/amount', 0)
    item['candidate'] = deepcopy(item['before'])
    assert not R.required([item], selected, {'intent': [{'op': 'lnx.deform.v1', 'path': '/slim_face', 'value': .2}]})
    assert R.required([item], {**selected, 'eye_bag_cohort': {}}, {'intent': []})  # Explicit neutral review is reachable.


def test_legacy_choices_are_member_local_and_never_drop_newly_selected_nonzero_leaf(monkeypatch):
    items = rows(); selected = request(items); selected['eye_bag_cohort']['members'][1]['replace_legacy'] = False
    with pytest.raises(ValueError): stage(monkeypatch, items, selected)
    selected = request(items)
    item = items[0]
    item['before'] = S.set_override(item['before'], 'face', item['ref']['face_instance_id'], A.ENHANCE, '/eye_bags', .2)
    selected['selection'][A.ENHANCE] = ['/eye_bags']
    with pytest.raises(ValueError, match='selected nonzero legacy'): stage(monkeypatch, items, selected)


def test_exact_noop_patch_is_refused_without_creating_review(monkeypatch):
    items = rows(); created, _ = stage(monkeypatch, items, request(items)); accept(items, created)
    with pytest.raises(ValueError, match='do not change shared person intent'): stage(monkeypatch, items, request(items, 'patch'))


@pytest.mark.parametrize('fault', ['omit-source', 'omit-target', 'reorder', 'duplicate', 'numeric-choice', 'bool-version', 'support'])
def test_policy_schema_is_exact_source_first(fault):
    selected = request(rows()); value = selected['eye_bag_cohort']
    if fault == 'omit-source': value['members'] = value['members'][1:]
    elif fault == 'omit-target': value['members'].pop()
    elif fault == 'reorder': value['members'].reverse()
    elif fault == 'duplicate': value['members'][-1] = value['members'][0]
    elif fault == 'numeric-choice': value['members'][0]['replace_legacy'] = 1
    elif fault == 'bool-version': value['version'] = True
    else: value['support'] = 'donor'
    with pytest.raises(ValueError): W.options(selected, list(selected['selection']))


def test_removed_active_effect_requires_own_before_support(monkeypatch):
    items = rows(); created, _ = stage(monkeypatch, items, request(items)); accept(items, created)
    selected = request(items, 'unlink'); candidates, _ = stage(monkeypatch, items, selected); target = candidates[1]
    from lumaretouch_engine import full_candidate_render, eye_bag_preserve_support
    bank = {'target-only': True}; calls = []
    monkeypatch.setattr(full_candidate_render, 'people_context', lambda engine, row: {'people_support_assets': bank})
    def support(graph, actual_bank, ref):
        assert graph == target['before'] and actual_bank is bank and ref == target['ref']
        calls.append(ref); return {'row': {'eyes': {'right': {}}}}, '7' * 64
    monkeypatch.setattr(eye_bag_preserve_support, 'resolve', support)
    coverage = R.coverage(None, target, selected)
    assert len(calls) == 1 and coverage['before']['sides'] == ['right']
    assert coverage['before']['scope'] == 'target-reviewed-ridge' and coverage['after']['scope'] == 'neutral-no-effect'
    monkeypatch.setattr(eye_bag_preserve_support, 'resolve', lambda *a: (_ for _ in ()).throw(ValueError('broken before support')))
    with pytest.raises(ValueError, match='broken before support'): R.coverage(None, target, selected)


def frozen(monkeypatch):
    items = rows(); selected = request(items); candidates, review = stage(monkeypatch, items, selected)
    targets = []; displays = {}; ack = []
    for item in candidates:
        doc = item['member']['document_id']; pair = {}
        own = {'version': 1, 'support_transfer': 'none', 'replace_legacy': R.policy(selected, doc), 'face_ref': item['ref']}
        for side, recipe in item['eye_bag_cohort_state'].items():
            own[side] = {'scope': 'target-reviewed-ridge' if EYE.active(recipe) else 'neutral-no-effect',
                'ridge_sha256': '7' * 64 if EYE.active(recipe) else None, 'sides': ['right'] if EYE.active(recipe) else []}
            raw = (doc + side + '-SYNTHETIC-NON-PNG').encode()
            pair[side] = {'mime': 'image/png', 'width': 128, 'height': 160, 'sha256': sha256(raw).hexdigest(), 'base64': b64encode(raw).decode()}
        visual = {'version': 1, 'document_id': doc, 'revision': '3', 'source_proof': item['proof']['source_proof'],
            'before_state_sha256': '1' * 64, 'candidate_state_sha256': '1' * 64,
            'before_people_sha256': '2' * 64, 'candidate_people_sha256': '3' * 64,
            'source_size': [128, 160], 'before_output_size': [128, 160], 'after_output_size': [128, 160],
            'coverage_sha256': VISUAL.coverage_digest(own),
            **{side: {key: value for key, value in pixels.items() if key != 'base64'} for side, pixels in pair.items()}}
        snapshot = {'render_sha256': '4' * 64, 'context_sha256': '5' * 64, 'graph_sha256': '6' * 64}
        payload = {'ref': item['ref'], 'person_id': 'cohort', 'candidate_sha256': item['candidate_sha256'],
            'eye_bag_cohort_state': item['eye_bag_cohort_state'], 'eye_bag_cohort': own,
            'eye_bag_cohort_visual': visual, 'eye_bag_cohort_snapshots': {'before': snapshot, 'after': snapshot}}
        targets.append(B.FrozenTarget(doc, 3, item['index'], item['row']['path'], None, B.canonical(item['proof']), people_json=B.canonical(payload)))
        displays[doc] = {'revision': '3', **pair}
        ack.append({'document_id': doc, 'revision': '3', 'before_sha256': visual['before']['sha256'],
            'after_sha256': visual['after']['sha256'], 'coverage_sha256': visual['coverage_sha256'], 'replace_legacy': own['replace_legacy']})
    params = {'_people_transfer': {'mode': 'persistent_association', 'options': selected, 'review': review,
        'portrait_cohort_required': False, 'collarbone_visual_required': False, 'eye_bag_cohort_required': True}}
    store = B.PreflightStore(lambda: 1)
    plan = store.create('workspace', targets[0].document_id, 3, targets[0].path, [EYE.OP], params, 'recheck', targets, [])
    return store, plan, ack, displays, candidates, review


def test_freeze_requires_concrete_eye_content_even_when_flag_is_forged(monkeypatch):
    _, plan, _, _, _, _ = frozen(monkeypatch)
    params = plan.params(); params['_people_transfer']['eye_bag_cohort_required'] = False
    with pytest.raises(ValueError, match='actual retained scalar content'): R.records(replace(plan, params_json=B.canonical(params)))
    params = plan.params(); del params['_people_transfer']['options']['eye_bag_cohort']
    with pytest.raises(ValueError, match='explicit per-member'): R.records(replace(plan, params_json=B.canonical(params)))


def test_all_source_first_acks_required_before_claim_and_exact_replay(monkeypatch):
    store, plan, ack, _, _, _ = frozen(monkeypatch)
    for bad in (None, [], ack[1:], ack[::-1]):
        with pytest.raises(ValueError): store.claim(plan, eye_bag_cohort_ack=bad)
        assert plan.token in store.pending and not store.terminal
    store.claim(plan, eye_bag_cohort_ack=ack, request_id='first')
    assert plan.token not in store.pending and store.completed(plan.token, 'workspace')['outcome_unknown'] is True
    result = store.finish(plan, {'success': False, 'outcome_unknown': True, 'error': 'synthetic failure after claim'})
    assert result['eye_bag_cohort_ack'] == ack and result['module_scope'] == [EYE.OP] and result['eye_bag_cohort'] is True
    emitted = []; controller = FrozenBatchController(None, SimpleNamespace(workspace='workspace'), emitted.append, lambda: 1)
    controller.store = store
    request = {'cmd': 'batch', 'action': 'commit', 'request_id': 'retry', 'preflight_token': plan.token, 'module_scope': [EYE.OP], 'eye_bag_cohort_ack': ack}
    assert controller.replay_completed(request)
    assert emitted[-1]['outcome_unknown'] is True and emitted[-1]['replayed'] is True
    request['eye_bag_cohort_ack'] = ack[::-1]
    with pytest.raises(ValueError): controller.replay_completed(request)


def test_source_first_cache_retrieval_is_family_and_coordinate_qualified(monkeypatch):
    store, plan, ack, displays, _, _ = frozen(monkeypatch); STORE.attach(store, plan, displays)
    controller = SimpleNamespace(store=store, versions=SimpleNamespace(workspace='workspace'))
    for item in ack:
        for side in ('before', 'after'):
            request = {'cmd': 'batch', 'action': 'eye_bag_cohort_visual', 'request_id': 'pixels', 'preflight_token': plan.token,
                'document_id': item['document_id'], 'revision': item['revision'], 'side': side, 'sha256': item[side + '_sha256']}
            result = STORE.retrieve(controller, request)
            assert result['image'] == displays[item['document_id']][side] and result['outcome_unknown'] is False
            with pytest.raises(ValueError): STORE.retrieve(controller, {**request, 'sha256': 'f' * 64})
    store.claim(plan, eye_bag_cohort_ack=ack)
    with pytest.raises(ValueError): STORE.retrieve(controller, request)


def history(monkeypatch):
    _, _, ack, _, candidates, review = frozen(monkeypatch)
    documents = [item['row'] for item in candidates]; plans = {}; targets = {}
    for item in candidates:
        doc = item['member']['document_id']; plans[doc] = {'row': item['row'], 'before': item['before'], 'candidate': item['candidate'], 'reviewed_face_refs': [item['ref']]}
        targets[str(item['index'])] = {'path': item['row']['path'], 'document_id': doc, 'revision': 3,
            'people_scope': doc, 'source_proof': item['proof']['source_proof'], 'asset_sha256': item['ref']['asset_sha256'], 'reviewed_face_refs': [item['ref']]}
    engine = SimpleNamespace(_docs=documents, _document_versions=lambda: SimpleNamespace(find=lambda docs, doc: next(((i, row) for i, row in enumerate(docs) if row['document_id'] == doc), None)))
    monkeypatch.setattr(HISTORY, '_dependencies', lambda *a: {'context_sha256': '8' * 64, 'state_sha256': '9' * 64})
    marker = HISTORY.prepare(engine, plans, targets, review, ack)
    entry = {'ops': ['lnx.people_graph.v1'], 'people_changes': [], 'policy': 'protected_scoped_graph', 'targets': targets,
        'people_scoped_changes': [{'scope': scope, 'document_id': plan['row']['document_id'], 'changes': between(plan['before'], plan['candidate'])} for scope, plan in plans.items()], HISTORY.KEY: marker}
    return engine, plans, targets, entry


def test_history_json_roundtrip_and_monotonic_fences_remain_usable(monkeypatch):
    engine, plans, targets, entry = history(monkeypatch)
    restored = json.loads(json.dumps(entry)); assert HISTORY.check(restored) == entry[HISTORY.KEY]
    undo = {}
    for scope, plan in plans.items():
        before = deepcopy(plan['candidate']); before['revision'] += 99; before['association_revision'] += 99
        undo[scope] = {'row': plan['row'], 'before': before, 'candidate': apply(before, between(plan['before'], plan['candidate']), redo=False)}
    from lumaretouch_engine import eye_bag_batch_plan
    calls = []; monkeypatch.setattr(eye_bag_batch_plan, 'closure', lambda *args: calls.append(args))
    HISTORY.verify_restore(engine, restored, undo, targets, redo=False)
    assert len(calls) == 1 and HISTORY.status_summary(restored)['member_count'] == 3
    undo[next(iter(undo))]['before'] = S.set_override(undo[next(iter(undo))]['before'], 'face', next(iter(undo[next(iter(undo))]['before']['faces'])), 'lnx.deform.v1', '/slim_face', .4)
    with pytest.raises(ValueError, match='full mixed graph'): HISTORY.verify_restore(engine, restored, undo, targets, redo=False)


@pytest.mark.parametrize('fault', ['missing-member', 'extra-member', 'borrowed-source', 'support-edit', 'ordinary-marker', 'nonzero-legacy', 'split-capsule'])
def test_history_refuses_partial_foreign_or_unreviewed_changes(monkeypatch, fault):
    _, _, _, original = history(monkeypatch); entry = deepcopy(original)
    if fault == 'missing-member': entry['targets'].pop(next(iter(entry['targets'])))
    elif fault == 'extra-member': entry['targets']['extra'] = deepcopy(next(iter(entry['targets'].values())))
    elif fault == 'borrowed-source': entry[HISTORY.KEY]['targets'][0]['source_proof']['asset_sha256'] = 'f' * 64
    elif fault == 'support-edit': entry['people_scoped_changes'][0]['changes'].append({'collection': 'faces', 'key': 'foreign', 'before': None, 'after': {}})
    elif fault == 'ordinary-marker': entry['eye_bag_batch_review'] = {}
    elif fault == 'nonzero-legacy':
        for change in entry['people_scoped_changes'][1]['changes']:
            if change['collection'] == 'overrides' and change['key'][0] == 'face': change['after']['value'] = .2
    else: entry[HISTORY.KEY]['targets'][0]['after_capsule']['generation'] = 'f' * 64
    with pytest.raises(ValueError): HISTORY.check(entry)


def test_unmarked_legacy_history_is_not_migrated_or_rejected():
    assert HISTORY.check({'legacy': True}) is None
    assert HISTORY.status_summary({'legacy': True}) is None


@pytest.mark.parametrize('terminal', ['claimed', 'finished', 'consumed-without-terminal'])
def test_delegated_throw_after_claim_never_becomes_false_no_write(monkeypatch, terminal):
    store, plan, ack, _, _, _ = frozen(monkeypatch); events = []
    def delegated(controller, request, reviewed):
        assert reviewed is plan
        controller.store.claim(plan, eye_bag_cohort_ack=ack, request_id=request['request_id'])
        if terminal == 'finished':
            controller.store.finish(plan, {'success': True, 'outcome_unknown': False, 'batch_id': 'synthetic-applied'})
        elif terminal == 'consumed-without-terminal':
            controller.store.terminal.pop(plan.token)
        raise RuntimeError('synthetic adapter receipt failure after claim')
    controller = FrozenBatchController(SimpleNamespace(people_transfer=delegated), SimpleNamespace(workspace='workspace'), events.append, lambda: 1)
    controller.store = store
    request = {'cmd': 'batch', 'action': 'commit', 'request_id': 'commit', 'preflight_token': plan.token,
               'module_scope': [EYE.OP], 'eye_bag_cohort_ack': ack}
    controller.handle(request)
    result = next(event for event in reversed(events) if event.get('event') == 'batch_result')
    assert result['eye_bag_cohort_ack'] == ack and result['module_scope'] == [EYE.OP] and result['eye_bag_cohort'] is True
    assert result['outcome_unknown'] is (terminal != 'finished')
    assert result['success'] is (terminal == 'finished')
    if terminal == 'finished': assert result['batch_id'] == 'synthetic-applied'
    assert plan.token not in store.pending


def test_real_batch_image_dispatch_precedes_mutation_guard(monkeypatch):
    from lumaretouch_engine.batch_sync import BatchSyncController
    store, plan, ack, displays, _, _ = frozen(monkeypatch); STORE.attach(store, plan, displays)
    events = []; preflight = FrozenBatchController(None, SimpleNamespace(workspace='workspace'), events.append, lambda: 1); preflight.store = store
    def forbidden(*args): raise AssertionError('Read-only cohort images cannot enter the editor mutation guard')
    owner = SimpleNamespace(preflight=preflight, emit=events.append, editor=SimpleNamespace(guard=forbidden))
    owner._reject = lambda *a, **k: forbidden()
    request = {'cmd': 'batch', 'action': 'eye_bag_cohort_visual', 'request_id': 'read', 'preflight_token': plan.token,
        'document_id': ack[0]['document_id'], 'revision': '3', 'side': 'before', 'sha256': ack[0]['before_sha256']}
    BatchSyncController.handle_command(owner, request)
    assert events[-1]['success'] is True and events[-1]['image'] == displays[ack[0]['document_id']]['before']


def test_dormant_closure_is_not_bypassed_by_complete_live_member_list(monkeypatch):
    items = rows(); selected = request(items); candidates, _ = stage(monkeypatch, items, selected)
    from lumaretouch_engine import face_style_alias_review
    def blocked(*args): raise ValueError('unreviewed dormant saved owner')
    monkeypatch.setattr(face_style_alias_review, 'verify_dormant', blocked)
    with pytest.raises(ValueError, match='dormant saved owner'):
        R.closure(SimpleNamespace(_docs=[item['row'] for item in candidates]), candidates)


def test_static_history_and_review_order_integrate_existing_owners():
    import ast
    from pathlib import Path
    root = Path(__file__).parents[1] / 'src/lumaretouch_engine'
    tree = ast.parse((root / 'people_cross_owner_workflow.py').read_text())
    commit = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'commit')
    calls = [(ast.unparse(node.func), node.lineno) for node in ast.walk(commit) if isinstance(node, ast.Call)]
    line = lambda name: [number for function, number in calls if function == name]
    assert max(line('EYE.acknowledgments')) < min(line('prepare'))
    assert max(line('EYE.verify')) < min(line('controller.store.claim'))
    assert max(line('prepare_eye_history')) < min(line('controller.store.claim')) < min(line('commit_scoped'))
    persistence = ast.parse((root / 'people_history_persistence.py').read_text())
    for name in ('save', 'prepare'):
        function = next(node for node in persistence.body if isinstance(node, ast.FunctionDef) and node.name == name)
        assert any(isinstance(node, ast.Call) and ast.unparse(node.func) == 'check_cohort_history' for node in ast.walk(function))
    ledger = ast.parse((root / 'people_batch_ledger.py').read_text())
    restore = next(node for node in ledger.body if isinstance(node, ast.FunctionDef) and node.name == 'restore_scoped')
    checks = [node.lineno for node in ast.walk(restore) if isinstance(node, ast.Call) and ast.unparse(node.func) == 'verify_cohort_restore']
    preparation = next(node.lineno for node in ast.walk(restore) if isinstance(node, ast.Call) and ast.unparse(node.func) == 'prepare_scoped')
    assert len(checks) == 2 and min(checks) < preparation < max(checks)
