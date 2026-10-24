# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: ordinary eye-bag batch scalar/evidence/history contracts.

Synthetic face/source/digest fixtures and explicitly mocked image production.
No test collection, imports, execution, builds, inference or photographic/native
acceptance ran while authoring. Fake display bytes are not an image-quality test.
"""
from base64 import b64encode
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from lumaretouch_engine import people_state as S, people_algorithms as A
from lumaretouch_engine import people_transfer_adapter as T, people_transfer_inventory as I
from lumaretouch_engine import people_batch_transfer as BATCH, people_batch_ledger as LEDGER
from lumaretouch_engine import eye_bag_preserve_state as EYE
from lumaretouch_engine import eye_bag_batch_plan as PLAN, eye_bag_batch_review as R
from lumaretouch_engine import eye_bag_batch_store as STORE, eye_bag_batch_history as HISTORY
from lumaretouch_engine import batch_preflight as B
from lumaretouch_engine import collarbone_transfer_review as VISUAL
from lumaretouch_engine.batch_preflight_controller import FrozenBatchController
from lumaretouch_engine.people_resolver import resolve
from lumaretouch_engine.people_graph_patch import between


def graph(asset):
    state = S.empty()
    face = S.new_face(asset, [.2, .1, .8, .9], {'backend': 'fixture_only',
        'detector_model_sha256': 'd'*64, 'semantic_model_sha256': None, 'landmark_digest': 'e'*64,
        'status': 'verified', 'source_width': 128, 'source_height': 160, 'orientation': 'exif_normalized_once'})
    state['faces'][face['face_instance_id']] = face
    return state, S.face_ref(face)


def proof(state, ref, document, scope=None):
    return {'document': {'document_id': document, 'epoch': 'workspace', 'revision': 3},
        'people_scope': scope or document, 'state_revision': state['revision'],
        'association_revision': state['association_revision'], 'graph_sha256': I.graph_digest(state),
        'source_proof': {'original_sha256': ref['asset_sha256'], 'asset_sha256': ref['asset_sha256'], 'creative_source': None}}


def endpoints(amount=.6, target_amount=0, legacy=0):
    source, ref = graph('a'*64); target, other = graph('b'*64)
    source = S.set_override(source, 'face', ref['face_instance_id'], EYE.OP, '/amount', amount)
    source = S.set_override(source, 'face', ref['face_instance_id'], EYE.OP, '/preserve', .8)
    target = S.set_override(target, 'face', other['face_instance_id'], EYE.OP, '/amount', target_amount)
    target = S.set_override(target, 'face', other['face_instance_id'], A.ENHANCE, '/eye_bags', legacy)
    return SimpleNamespace(source=source, target=target, ref=ref, other=other,
        a=proof(source, ref, 'source'), b=proof(target, other, 'target'))


def prepared(h, replace_legacy=False, paths=None, extra=None, admission=PLAN.ADMISSION):
    selected = {EYE.OP: paths or ['/amount', '/preserve'], **(extra or {})}
    return T.prepare(h.source, h.target, h.ref, [h.other], selected, A.defaults(),
        source_document=h.a['document'], target_document=h.b['document'], source_owner=h.a, target_owner=h.b,
        eye_bag={'version': 1, 'replace_legacy': replace_legacy}, eye_bag_review=admission)


def values(graph, ref): return A.recipes(resolve(graph, ref['face_instance_id'], A.defaults()))


def request(h):
    selected = {'source_ref': h.ref, 'source': h.a, 'target_policy': 'explicit_face_map',
        'selection': {EYE.OP: ['/amount', '/preserve']}, 'targets': [{'target': h.b, 'target_refs': [h.other]}],
        'eye_bag': {'version': 1, 'targets': [{'document_id': 'target', 'replace_legacy': False}]}}
    return {'cmd': 'batch', 'action': 'preflight', 'request_id': 'review', 'docs': ['target'],
        'module_scope': [EYE.OP], 'people_transfer': selected}


def test_explicit_scalar_stage_never_copies_source_faces_support_or_associations():
    h = endpoints(); payload = prepared(h); before = deepcopy(h.target)
    out = PLAN.stage(payload, h.target, PLAN.ADMISSION)
    for key in ('faces', 'persons', 'links', 'groups', 'analysis_runs', 'unresolved_legacy'):
        assert out[key] == before[key]
    assert h.target == before and values(out, h.other)[EYE.OP] == {'version': 2, 'amount': .6, 'preserve': .8}
    assert payload['excluded'] == ['local_assets', 'landmarks', 'masks', 'identity_links']


def test_metadata_alone_cannot_lift_generic_active_adapter_fence():
    h = endpoints()
    for admission in (None, True, {}, {'reviewed': True}):
        with pytest.raises(ValueError): prepared(h, admission=admission)
    payload = prepared(h)
    with pytest.raises(ValueError): T.stage(payload, h.target)
    with pytest.raises(ValueError): T.verify(payload, h.source, h.target,
        source_document=h.a['document'], target_document=h.b['document'], source_owner=h.a, target_owner=h.b)


def test_preserve_only_resolves_target_amount_instead_of_donor_amount():
    h = endpoints(amount=0, target_amount=.4)
    payload = prepared(h, paths=['/preserve'])
    assert values(PLAN.stage(payload, h.target, PLAN.ADMISSION), h.other)[EYE.OP]['amount'] == .4
    with pytest.raises(ValueError):
        T.prepare(h.source, h.target, h.ref, [h.other], {EYE.OP: ['/preserve']}, A.defaults(),
            source_document=h.a['document'], target_document=h.b['document'], source_owner=h.a, target_owner=h.b)


@pytest.mark.parametrize('paths', [['/amount'], ['/preserve']])
def test_generic_neutral_and_dormant_transfer_remain_compatible(paths):
    h = endpoints(amount=0, target_amount=0)
    payload = T.prepare(h.source, h.target, h.ref, [h.other], {EYE.OP: paths}, A.defaults(),
        source_document=h.a['document'], target_document=h.b['document'], source_owner=h.a, target_owner=h.b)
    assert not any(key.startswith('eye_bag') for key in payload)


def test_active_legacy_requires_explicit_target_choice_and_only_selected_face_is_cleared():
    h = endpoints(legacy=.5)
    with pytest.raises(ValueError): prepared(h)
    payload = prepared(h, replace_legacy=True)
    candidate = PLAN.stage(payload, h.target, PLAN.ADMISSION)
    assert values(candidate, h.other)[A.ENHANCE]['eye_bags'] == 0
    assert values(h.target, h.other)[A.ENHANCE]['eye_bags'] == .5
    assert candidate['faces'] == h.target['faces']


def test_selected_nonzero_legacy_is_refused_not_silently_dropped():
    h = endpoints()
    h.source = S.set_override(h.source, 'face', h.ref['face_instance_id'], A.ENHANCE, '/eye_bags', .2)
    h.a = proof(h.source, h.ref, 'source')
    with pytest.raises(ValueError, match='Selected nonzero'):
        prepared(h, replace_legacy=True, extra={A.ENHANCE: ['/eye_bags']})


def test_neutral_recipe_does_not_clear_existing_legacy_even_if_choice_true():
    h = endpoints(amount=0, legacy=.5)
    candidate = PLAN.stage(prepared(h, replace_legacy=True), h.target, PLAN.ADMISSION)
    assert values(candidate, h.other)[A.ENHANCE]['eye_bags'] == .5


@pytest.mark.parametrize('old,new', [(0, 0.), (1, 1.), (.5, .5)])
def test_numeric_noop_does_not_reorder_or_advance_graph(old, new):
    h = endpoints()
    target = S.set_override(h.target, 'face', h.other['face_instance_id'], EYE.OP, '/amount', old)
    target = S.set_override(target, 'face', h.other['face_instance_id'], EYE.OP, '/preserve', .9)
    result = PLAN._set(target, h.other['face_instance_id'], EYE.OP, '/amount', new)
    assert result == target and result['revision'] == target['revision'] and not between(target, result)
    assert PLAN._set(target, h.other['face_instance_id'], EYE.OP, '/amount', True) != target


@pytest.mark.parametrize('fault', ['bool-version', 'numeric-policy', 'missing-target', 'foreign-target', 'duplicate', 'cohort', 'no-eye', 'extra'])
def test_options_and_read_only_refuse_ambiguous_or_foreign_policy(fault):
    h = endpoints(); p = request(h); selected = p['people_transfer']
    if fault == 'bool-version': selected['eye_bag']['version'] = True
    elif fault == 'numeric-policy': selected['eye_bag']['targets'][0]['replace_legacy'] = 1
    elif fault == 'missing-target': selected['eye_bag']['targets'] = []
    elif fault == 'foreign-target': selected['eye_bag']['targets'][0]['document_id'] = 'other'
    elif fault == 'duplicate': selected['eye_bag']['targets'] *= 2
    elif fault == 'cohort': selected['target_policy'] = 'persistent_association'
    elif fault == 'no-eye': selected['selection'] = {A.ENHANCE: ['/eye_bags']}
    else: selected['eye_bag']['support'] = 'donor'
    with pytest.raises((ValueError, KeyError)): BATCH.options(selected, p['module_scope'], h.ref['asset_sha256'])
    assert not STORE.read_only(p)


def test_coverage_reads_parked_target_bank_and_preserves_explicit_side_subset(monkeypatch):
    h = endpoints(); payload = prepared(h); candidate = PLAN.stage(payload, h.target, PLAN.ADMISSION)
    from lumaretouch_engine import full_candidate_render, eye_bag_preserve_support
    bank = {'target-only': 'fixture'}; engine = SimpleNamespace(_people_support={'donor': 'wrong'})
    row = {'state': {}, 'proof': h.b['source_proof']}
    monkeypatch.setattr(full_candidate_render, 'people_context', lambda engine, row: {'people_support_assets': bank})
    monkeypatch.setattr(PLAN.SOURCE, 'row_proof', lambda row: row['proof'])
    def support(state, actual, ref):
        assert actual is bank and ref == h.other and state == candidate
        return {'row': {'eyes': {'right': {}}}}, 'c'*64
    monkeypatch.setattr(eye_bag_preserve_support, 'resolve', support)
    coverage = PLAN.coverage(engine, row, candidate, payload)
    assert coverage['targets'] == [{'face_ref': h.other, 'scope': 'target-reviewed-ridge', 'ridge_sha256': 'c'*64, 'sides': ['right']}]


def test_neutral_coverage_never_requests_support(monkeypatch):
    h = endpoints(amount=0); payload = prepared(h); candidate = PLAN.stage(payload, h.target, PLAN.ADMISSION)
    from lumaretouch_engine import full_candidate_render, eye_bag_preserve_support
    monkeypatch.setattr(full_candidate_render, 'people_context', lambda *a: {'people_support_assets': {}})
    monkeypatch.setattr(PLAN.SOURCE, 'row_proof', lambda row: h.b['source_proof'])
    monkeypatch.setattr(eye_bag_preserve_support, 'resolve', Mock(side_effect=AssertionError('No neutral support')))
    assert PLAN.coverage(None, {}, candidate, payload)['targets'][0]['scope'] == 'neutral-no-effect'


def frozen_fixture(count=1):
    h = endpoints(); selected = request(h)['people_transfer']; targets = []; displays = {}; acks = []
    selected['targets'] = []; selected['eye_bag']['targets'] = []
    for n in range(count):
        document = 'target-' + str(n); endpoint = proof(h.target, h.other, document)
        selected['targets'].append({'target': endpoint, 'target_refs': [h.other]})
        selected['eye_bag']['targets'].append({'document_id': document, 'replace_legacy': False})
        payload = prepared(h); payload['target_owner'] = endpoint; payload['target_document'] = endpoint['document']
        coverage = {'version': 1, 'support_transfer': 'none', 'targets': [
            {'face_ref': h.other, 'scope': 'target-reviewed-ridge', 'ridge_sha256': 'a'*64, 'sides': ['left']}]}
        pair = {}
        for side in ('before', 'after'):
            raw = (document + side).encode(); pair[side] = {'mime': 'image/png', 'width': 128, 'height': 160,
                'sha256': sha256(raw).hexdigest(), 'base64': b64encode(raw).decode()}
        record = {'version': 1, 'document_id': document, 'revision': '3', 'source_proof': endpoint['source_proof'],
            'before_state_sha256': '1'*64, 'candidate_state_sha256': '1'*64,
            'before_people_sha256': '2'*64, 'candidate_people_sha256': '3'*64,
            'source_size': [128,160], 'before_output_size': [128,160], 'after_output_size': [128,160],
            'coverage_sha256': VISUAL.coverage_digest(coverage),
            **{side: {key: value for key,value in pair[side].items() if key != 'base64'} for side in pair}}
        payload.update(eye_bag_coverage=coverage, eye_bag_visual=record)
        snapshot = {'render_sha256': '4'*64, 'context_sha256': '5'*64, 'graph_sha256': '6'*64}
        targets.append(B.FrozenTarget(document, 3, n, '/'+document, None,
            B.canonical({'source_proof': endpoint['source_proof'], 'eye_bag_snapshots': {'before': snapshot, 'after': snapshot}}),
            people_json=B.canonical(payload)))
        displays[document] = {'revision': '3', **pair}
        acks.append({'document_id': document, 'revision': '3', 'before_sha256': record['before']['sha256'],
            'after_sha256': record['after']['sha256'], 'coverage_sha256': record['coverage_sha256'], 'replace_legacy': False})
    store = B.PreflightStore(lambda: 1)
    plan = store.create('workspace', 'source', 3, '/source', [EYE.OP],
        {'_people_transfer': {'options': selected}}, 'skip_and_report', targets, [])
    return store, plan, acks, displays


def test_claim_missing_ack_keeps_plan_live_exact_claim_is_consumed_unknown_then_known():
    store, plan, ack, _ = frozen_fixture()
    with pytest.raises(ValueError): store.claim(plan, request_id='commit')
    assert store.pending[plan.token] is plan and not store.terminal
    store.claim(plan, eye_bag_review_ack=ack, request_id='commit')
    assert plan.token not in store.pending and store.completed(plan.token, 'workspace')['outcome_unknown']
    result = store.finish(plan, {'success': True, 'outcome_unknown': False, 'batch_id': None})
    assert result['eye_bag_review_ack'] == ack and result['request_id'] == 'commit'
    assert result['module_scope'] == [EYE.OP]


@pytest.mark.parametrize('field', ['document_id','revision','before_sha256','after_sha256','coverage_sha256','replace_legacy'])
def test_ack_coordinates_and_typed_choice_are_exact(field):
    store, plan, ack, _ = frozen_fixture(); bad = deepcopy(ack)
    bad[0][field] = 0 if field == 'replace_legacy' else 'wrong'
    with pytest.raises(ValueError): store.claim(plan, eye_bag_review_ack=bad)
    assert plan.token in store.pending and not store.terminal


def test_ack_order_count_and_foreign_families_cannot_consume_plan():
    store, plan, ack, _ = frozen_fixture(2)
    for raw in ([], ack[:1], ack[::-1], ack+[ack[0]], tuple(ack)):
        with pytest.raises(ValueError): store.claim(plan, eye_bag_review_ack=raw)
    for key in ('portrait_cohort_ack', 'face_style_review_ack', 'spill_review_ack', 'shadow_review_ack', 'head_review_ack'):
        with pytest.raises(ValueError): store.claim(plan, eye_bag_review_ack=ack, **{key: []})
    assert plan.token in store.pending


def test_terminal_overflow_and_replay_preserve_exact_claim_and_never_rewrite(monkeypatch):
    store, plan, ack, _ = frozen_fixture(); store.claim(plan, eye_bag_review_ack=ack, request_id='original')
    monkeypatch.setattr(B, 'MAX_RESULT_BYTES', 1)
    receipt = store.finish(plan, {'success': True, 'huge': object()})
    assert receipt['outcome_unknown'] and receipt['eye_bag_review_ack'] == ack and receipt['request_id'] == 'original'
    events = []; ports = SimpleNamespace(people_transfer=Mock())
    controller = FrozenBatchController(ports, SimpleNamespace(workspace='workspace'), events.append, lambda: 1)
    controller.store = store
    assert controller.replay_completed({'cmd':'batch','action':'commit','request_id':'retry',
        'preflight_token':plan.token,'eye_bag_review_ack':ack})
    ports.people_transfer.assert_not_called()
    assert events[-1]['replayed'] and events[-1]['request_id'] == 'retry'
    with pytest.raises(ValueError): controller.replay_completed({'cmd':'batch','action':'commit',
        'preflight_token':plan.token,'eye_bag_review_ack':[]})


def test_cached_image_is_exact_paged_compact_and_unavailable_after_claim():
    store, plan, ack, displays = frozen_fixture(); STORE.attach(store, plan, displays)
    controller = SimpleNamespace(store=store, versions=SimpleNamespace(workspace='workspace'))
    record = R.records(plan)[0]['visual']
    p = {'cmd':'batch','action':'eye_bag_visual','request_id':'image','preflight_token':plan.token,
        'document_id':record['document_id'],'revision':'3','side':'after','sha256':record['after']['sha256']}
    assert STORE.read_only(p) and STORE.image_read_only(p)
    result = STORE.retrieve(controller, p)
    assert result['compact'] == record['after'] and result['image'] == displays[record['document_id']]['after']
    for bad in ({**p,'document_id':'other'}, {**p,'revision':'4'}, {**p,'sha256':'0'*64}, {**p,'side':'support'}):
        with pytest.raises(ValueError): STORE.retrieve(controller, bad)
    store.claim(plan, eye_bag_review_ack=ack)
    with pytest.raises(ValueError): STORE.retrieve(controller, p)


def test_failure_echoes_bounded_request_context_without_authorizing_it():
    h = endpoints(); p = request(h)
    assert STORE.failure_context(p) == {'module_scope':[EYE.OP], 'policy':'skip_and_report', 'applies':p['people_transfer']}
    assert STORE.failure_context({'action':'commit','preflight_token':'x','eye_bag_review_ack':[]}) == {
        'preflight_token':'x','eye_bag_review_ack':[]}


def test_final_full_snapshot_change_refuses_even_when_coverage_is_same(monkeypatch):
    store, plan, _, _ = frozen_fixture(); target = plan.targets[0]; payload = json.loads(target.people_json)
    monkeypatch.setattr(PLAN, 'coverage', lambda *a: payload['eye_bag_coverage'])
    monkeypatch.setattr(PLAN, 'snapshots', lambda *a: {'before': {}, 'after': {}})
    verify = Mock(); monkeypatch.setattr(VISUAL, 'verify', verify)
    with pytest.raises(ValueError): PLAN.verify(None, {}, {'before':{},'candidate':{}}, target, payload)
    verify.assert_not_called()


def test_alias_closure_refuses_hidden_active_and_dormant_documents(monkeypatch):
    from lumaretouch_engine import face_style_alias_review
    h = endpoints(); payload = prepared(h); candidate = PLAN.stage(payload, h.target, PLAN.ADMISSION)
    row = {'document_id':'target','state':{},'proof':h.b['source_proof']}
    hidden = {**row,'document_id':'hidden'}
    engine = SimpleNamespace(_document_versions=lambda:SimpleNamespace(version=lambda row:SimpleNamespace(document_id=row['document_id'])))
    monkeypatch.setattr(PLAN.SOURCE, 'row_proof', lambda row: row['proof'])
    dormant = Mock(); monkeypatch.setattr(face_style_alias_review, 'verify_dormant', dormant)
    plans = {'project':{'row':row,'before':h.target,'candidate':candidate}}
    with pytest.raises(ValueError, match='unreviewed'): PLAN.closure(engine, [row,hidden], plans, {'target'})
    dormant.side_effect = ValueError('dormant history')
    with pytest.raises(ValueError, match='dormant'): PLAN.closure(engine, [row], plans, {'target'})


def test_history_dependency_encoding_is_save_reopen_stable_and_ignores_unrelated_bank(monkeypatch):
    from lumaretouch_engine import full_candidate_render
    h = endpoints(); own = {'people_graph':h.target,'people_landmarks':{},'people_support_assets':{},
        'people_cursors':{},'people_targets':{}}
    row = {'state':{'_crop_rect':(0.,0.,1.,1.),'_precompute':object(),'_proxy':(100,200)}, 'proof':h.b['source_proof']}
    monkeypatch.setattr(full_candidate_render, 'people_context', lambda *a:own)
    monkeypatch.setattr(HISTORY.SOURCE, 'row_proof', lambda row:row['proof'])
    before = HISTORY._dependencies(None,row)
    row['state']['_crop_rect'] = [0.,0.,1.,1.]; row['state']['_precompute'] = None; row['state']['_proxy'] = [50,100]
    row['state']['_enhance'] = {'amounts':{'eye_bags':.8}}
    own['people_support_assets']['unrelated'] = {'anything':'append-only'}
    own['people_cursors'] = {'different':'selection'}
    assert HISTORY._dependencies(None,row) == before
    row['state']['_crop_rect'][0] = .1
    assert HISTORY._dependencies(None,row) != before


def test_history_marker_rejects_foreign_face_or_added_alias_and_legacy_is_unchanged():
    assert HISTORY.check({}) is None
    h = endpoints(); candidate = PLAN.stage(prepared(h),h.target,PLAN.ADMISSION)
    ref = h.other
    target = {'document_id':'target','people_scope':'target','asset_sha256':ref['asset_sha256'],
        'source_proof':h.b['source_proof'],'reviewed_face_refs':[ref]}
    marker = {'version':1,'review_sha256':'a'*64,'targets':[{'document_id':'target','people_scope':'target',
        'source_proof':h.b['source_proof'],'faces':[h.target['faces'][ref['face_instance_id']]],
        'context_sha256':'b'*64,'state_sha256':'c'*64}]}
    entry = {'ops':['lnx.people_graph.v1'],'people_changes':[],'policy':'protected_scoped_graph',
        'targets':{'0':target},'people_scoped_changes':[{'scope':'target','document_id':'target',
        'changes':between(h.target,candidate)}],HISTORY.KEY:marker}
    assert HISTORY.check(entry) == marker
    bad = deepcopy(entry); bad['targets']['1'] = {**target,'document_id':'hidden'}
    with pytest.raises(ValueError): HISTORY.check(bad)
    bad = deepcopy(entry); bad[HISTORY.KEY]['targets'][0]['faces'][0]['asset_sha256'] = 'f'*64
    with pytest.raises(ValueError): HISTORY.check(bad)


@pytest.fixture
def aggregate(monkeypatch):
    from lumaretouch_engine import face_style_alias_review
    h = endpoints(); other_graph, second = graph('c'*64)
    h.target['faces'].update(other_graph['faces']); h.b = proof(h.target,h.other,'target-0',scope='project')
    payload = prepared(h)
    refs = [h.other, second]; rows = []; targets = []; calls = []
    owner_graph = deepcopy(h.target)
    for index, ref in enumerate(refs):
        document = 'target-' + str(index)
        endpoint = proof(owner_graph,ref,document,scope='project')
        row = {'document_id':document,'path':'/'+document,'state':{'fixture_repair':'initial'},
            'proof':endpoint['source_proof']}
        rows.append(row)
        item = {**deepcopy(payload),'target_refs':[ref],'target_owner':endpoint,'target_document':endpoint['document']}
        own = {'version':1,'support_transfer':'none','targets':[{'face_ref':ref,
            'scope':'target-reviewed-ridge','ridge_sha256':'f'*64,'sides':['left']}]}
        item['eye_bag_coverage'] = own
        targets.append(B.FrozenTarget(document,3,index,row['path'],None,
            B.canonical({'source_proof':row['proof']}),people_json=B.canonical(item)))
    engine = SimpleNamespace(_docs=rows,_document_versions=lambda:SimpleNamespace(
        version=lambda row:SimpleNamespace(document_id=row['document_id'])))
    monkeypatch.setattr(PLAN.V,'row_snapshot',lambda engine,row:deepcopy(owner_graph))
    monkeypatch.setattr(PLAN.SOURCE,'row_proof',lambda row:row['proof'])
    monkeypatch.setattr(face_style_alias_review,'verify_dormant',lambda *a:None)
    monkeypatch.setattr(PLAN,'coverage',lambda engine,row,candidate,payload:deepcopy(payload['eye_bag_coverage']))
    def snap(engine,row,state,candidate):
        cleaned=deepcopy(candidate);cleaned['revision']=0
        return {'render_sha256':VISUAL.coverage_digest(state),'context_sha256':'a'*64,
                'graph_sha256':VISUAL.coverage_digest(cleaned)}
    monkeypatch.setattr(PLAN,'snapshot_key',snap)
    def render(engine,row,before,candidate,document,revision,coverage):
        calls.append((document,deepcopy(candidate)))
        compact={'mime':'image/png','width':128,'height':160,'sha256':'a'*64}
        record={'version':1,'document_id':document,'revision':revision,'source_proof':row['proof'],
            'before_state_sha256':VISUAL.coverage_digest(row['state']),'candidate_state_sha256':VISUAL.coverage_digest(row['state']),
            'before_people_sha256':VISUAL.coverage_digest(before),'candidate_people_sha256':VISUAL.coverage_digest(candidate),
            'source_size':[128,160],'before_output_size':[128,160],'after_output_size':[128,160],
            'coverage_sha256':VISUAL.coverage_digest(coverage),'before':compact,'after':compact}
        pixels={**compact,'base64':b64encode(b'FAKE DISPLAY').decode()}
        return record,{'before':pixels,'after':pixels}
    monkeypatch.setattr(VISUAL,'prepare',render)
    monkeypatch.setattr(VISUAL,'verify',lambda *a:None)
    return SimpleNamespace(engine=engine,rows=rows,targets=targets,public=[{},{}],
        refs=refs,graph=owner_graph,calls=calls,render=render)


def test_each_target_image_contains_complete_aggregate_owner_not_isolated_face(aggregate):
    h=aggregate;before=deepcopy(h.graph)
    frozen,displays=PLAN.visuals(h.engine,h.rows,h.targets,h.public)
    assert set(displays)=={'target-0','target-1'} and len(h.calls)==2
    assert h.calls[0][1]==h.calls[1][1] and h.graph==before
    for _,candidate in h.calls:
        assert all(values(candidate,ref)[EYE.OP]['amount']==.6 for ref in h.refs)
    assert all('eye_bag_snapshots' in json.loads(target.before_json) for target in frozen)
    assert all('base64' not in target.people_json for target in frozen)


def test_different_alias_replacement_choices_refuse_before_any_image(aggregate):
    h=aggregate
    h.rows[1]['proof']=h.rows[0]['proof']
    payload=json.loads(h.targets[1].people_json)
    payload['target_owner']['source_proof']=h.rows[0]['proof']
    payload['eye_bag']['replace_legacy']=True
    h.targets[1]=replace(h.targets[1],people_json=B.canonical(payload))
    with pytest.raises(ValueError,match='same explicit'):PLAN.visuals(h.engine,h.rows,h.targets,h.public)
    assert h.calls==[]


def test_later_render_repair_change_invalidates_all_prepared_images(aggregate,monkeypatch):
    h=aggregate
    def render(*args):
        result=h.render(*args)
        if len(h.calls)==2:h.rows[0]['state']['fixture_repair']='changed'
        return result
    monkeypatch.setattr(VISUAL,'prepare',render)
    with pytest.raises(ValueError,match='repair'):PLAN.visuals(h.engine,h.rows,h.targets,h.public)
    assert len(h.calls)==2


def test_commit_cannot_use_preflight_image_of_different_aggregate(aggregate):
    h=aggregate;frozen,_=PLAN.visuals(h.engine,h.rows,h.targets,h.public)
    payload=json.loads(frozen[0].people_json)
    isolated=PLAN.stage(payload,h.graph,PLAN.ADMISSION)
    with pytest.raises(ValueError,match='mixed graph'):
        PLAN.verify(h.engine,h.rows[0],{'before':h.graph,'candidate':isolated},frozen[0],payload)


def history_fixture():
    h=endpoints();candidate=PLAN.stage(prepared(h),h.target,PLAN.ADMISSION);ref=h.other
    row={'document_id':'target','copy_number':1,'path':'/target','state':{}}
    target={'path':'/target','document_id':'target','revision':3,'people_scope':'target','asset_sha256':ref['asset_sha256'],
        'source_proof':h.b['source_proof'],'reviewed_face_refs':[ref]}
    marker={'version':1,'review_sha256':'a'*64,'targets':[{'document_id':'target','people_scope':'target',
        'source_proof':h.b['source_proof'],'faces':[h.target['faces'][ref['face_instance_id']]],
        'context_sha256':'b'*64,'state_sha256':'c'*64}]}
    entry={'ops':['lnx.people_graph.v1'],'people_changes':[],'policy':'protected_scoped_graph',
        'at_ns':1,'undone':False,'targets':{'0':target},'people_scoped_changes':[{'scope':'target','document_id':'target',
        'changes':between(h.target,candidate)}],HISTORY.KEY:marker}
    return SimpleNamespace(h=h,row=row,candidate=candidate,entry=entry,marker=marker,
        plans={'target':{'row':row,'before':h.target,'candidate':candidate,'reviewed_face_refs':[ref]}})


def test_protected_history_save_load_retains_marker_and_rejects_malformed_scope():
    from lumaretouch_engine import people_history_persistence
    h=history_fixture();project={'people_batch_history':{'batch-one':h.entry},'assets':{}}
    _,entries=people_history_persistence.prepare(project,[],64)
    assert entries['batch-one'][HISTORY.KEY]==h.marker
    project['people_batch_history']['batch-one'][HISTORY.KEY]['targets'][0]['people_scope']='foreign'
    with pytest.raises(ValueError):people_history_persistence.prepare(project,[],64)


def test_history_marker_checked_before_publication_and_rollbacks_leave_no_entry(monkeypatch):
    h=history_fixture();owner=SimpleNamespace(ledger={},sequence=0,clock=lambda:1.,monotonic=lambda:1,
        documents=SimpleNamespace(remember_current=lambda:None),editor=SimpleNamespace(mark_dirty=lambda:None))
    monkeypatch.setattr(LEDGER,'_verify',lambda *a:None)
    publish=Mock(side_effect=ValueError('Existing all-owner publication rolled back'))
    monkeypatch.setattr(LEDGER,'_publish',publish)
    bad=deepcopy(h.marker);bad['targets']=[]
    with pytest.raises(ValueError):LEDGER.commit_scoped(owner,SimpleNamespace(),h.plans,request_id='bad',
        prepare=False,prepared_targets=h.entry['targets'],eye_bag_history=bad)
    publish.assert_not_called()
    with pytest.raises(ValueError,match='rolled back'):LEDGER.commit_scoped(owner,SimpleNamespace(),h.plans,request_id='commit',
        prepare=False,prepared_targets=h.entry['targets'],eye_bag_history=h.marker)
    assert not owner.ledger and publish.call_count==1


def test_history_checks_new_alias_and_support_dependencies_again_after_prepare(monkeypatch):
    h=history_fixture();calls=[];engine=SimpleNamespace(_docs=[h.row],
        _document_versions=lambda:SimpleNamespace(find=lambda rows,doc:(0,h.row)))
    monkeypatch.setattr(HISTORY,'_dependencies',lambda *a:{'context_sha256':'b'*64,'state_sha256':'c'*64})
    monkeypatch.setattr(PLAN,'closure',lambda *a:calls.append('closure'))
    HISTORY.verify_restore(engine,h.entry,h.plans,h.entry['targets'])
    assert calls==['closure']
    added={**h.entry['targets'],'1':{**h.entry['targets']['0'],'document_id':'new-alias'}}
    with pytest.raises(ValueError,match='aliases'):HISTORY.verify_restore(engine,h.entry,h.plans,added)
    monkeypatch.setattr(HISTORY,'_dependencies',lambda *a:{'context_sha256':'changed','state_sha256':'c'*64})
    with pytest.raises(ValueError,match='support'):HISTORY.verify_restore(engine,h.entry,h.plans,h.entry['targets'])


def test_history_summary_is_bounded_and_does_not_expose_support_or_faces():
    h=history_fixture()
    assert HISTORY.status_summary(h.entry)=={'version':1,'review_sha256':'a'*64,'member_count':1}
    assert HISTORY.status_summary({}) is None


def test_source_contract_representative_and_history_validation_precede_claim():
    """Source-order contract, not an execution assertion about transaction code."""
    from pathlib import Path
    source=(Path(__file__).parents[1]/'src/lumaretouch_engine/people_batch_transfer.py').read_text()
    assert source.index("scoped['row']=found[1]") < source.index('eye_history=prepare_history') < source.index('controller.store.claim')
    ledger=(Path(__file__).parents[1]/'src/lumaretouch_engine/people_batch_ledger.py').read_text()
    restore=ledger[ledger.index('def restore_scoped'):]
    assert restore.index('owner.documents.remember_current()') < restore.index('SOURCE.verify_row_target')
    assert restore.count('verify_eye_restore(engine,batch,plans,')==2


@pytest.fixture
def commit_host(monkeypatch):
    """Real scalar/ledger orchestration; source IO and rendering are explicit mocks."""
    from lumaretouch_engine.people_graph_owner import PeopleGraphOwner
    from lumaretouch_engine import face_style_alias_review
    h=endpoints();second_graph,second=graph('c'*64)
    target=deepcopy(h.target);target['faces'].update(second_graph['faces'])
    target=S.set_override(target,'face',h.other['face_instance_id'],EYE.OP,'/amount',.6)
    target=S.set_override(target,'face',h.other['face_instance_id'],EYE.OP,'/preserve',.8)
    refs=[h.other,second]
    rows=[{'document_id':'source','path':'/source','copy_number':1,'state':{},'_rev':3,'proof':h.a['source_proof']}]
    rows += [{'document_id':'target-'+str(i),'path':'/target-'+str(i),'state':{},'_rev':3,
        'proof':{'asset_sha256':ref['asset_sha256'],'original_sha256':ref['asset_sha256'],'creative_source':None}}
        for i,ref in enumerate(refs)]
    owners={'source':PeopleGraphOwner(h.source),'project':PeopleGraphOwner(target)}
    def version(row):return SimpleNamespace(document_id=row['document_id'],revision=row['_rev'])
    versions=SimpleNamespace(workspace='workspace',version=version,check_advance=version,
        find=lambda docs,identity:next(((i,row) for i,row in enumerate(docs) if row['document_id']==identity),None),
        advance=lambda row:row.update(_rev=row['_rev']+1))
    documents=SimpleNamespace(rows=lambda:rows,remember_current=Mock(),current_index=lambda:0)
    batch=SimpleNamespace(documents=documents,versions=versions,ledger={},sequence=0,clock=lambda:1.,monotonic=lambda:1,
        editor=SimpleNamespace(mark_dirty=Mock()))
    engine=SimpleNamespace(_docs=rows,_doc_index=0,_batch_controller=lambda:batch,_document_versions=lambda:versions)
    monkeypatch.setattr(PLAN.V,'row_owner',lambda engine,row:owners[PLAN.V.scope(row)])
    monkeypatch.setattr(PLAN.V,'row_snapshot',lambda engine,row:owners[PLAN.V.scope(row)].snapshot())
    monkeypatch.setattr(PLAN.V,'remember',lambda engine:None)
    monkeypatch.setattr(PLAN.SOURCE,'row_proof',lambda row:deepcopy(row['proof']))
    monkeypatch.setattr(PLAN.SOURCE,'verify_row',lambda row,expected:deepcopy(row['proof']) if row['proof']==expected else (_ for _ in ()).throw(ValueError('source changed')))
    monkeypatch.setattr(PLAN.SOURCE,'verify_row_target',lambda *a:None)
    monkeypatch.setattr(face_style_alias_review,'verify_dormant',lambda *a:None)
    monkeypatch.setattr(LEDGER,'prepare_scoped',lambda *a:None)
    monkeypatch.setattr(STORE,'verify_available',lambda *a:None)
    monkeypatch.setattr(HISTORY,'_dependencies',lambda *a:{'context_sha256':'b'*64,'state_sha256':'c'*64})
    def owner_proof(engine,row,current,**kwargs):
        ref=next(S.face_ref(face) for face in current['faces'].values() if face['asset_sha256']==row['proof']['asset_sha256'])
        value=proof(current,ref,row['document_id'],scope=PLAN.V.scope(row));value['document']['revision']=row['_rev'];return value
    monkeypatch.setattr(I,'proof',owner_proof)
    source_owner=owner_proof(engine,rows[0],h.source)
    selected={'source_ref':h.ref,'source':source_owner,'target_policy':'explicit_face_map','selection':{EYE.OP:['/amount','/preserve']},
        'targets':[],'eye_bag':{'version':1,'targets':[]}}
    targets=[];reviews=[];acks=[];expected=deepcopy(target)
    for i,ref in enumerate(refs):
        row=rows[i+1];endpoint=owner_proof(engine,row,target)
        payload=T.prepare(h.source,target,h.ref,[ref],selected['selection'],A.defaults(),
            source_document=source_owner['document'],target_document=endpoint['document'],source_owner=source_owner,target_owner=endpoint,
            eye_bag={'version':1,'replace_legacy':False},eye_bag_review=PLAN.ADMISSION)
        selected['targets'].append({'target':endpoint,'target_refs':[ref]})
        selected['eye_bag']['targets'].append({'document_id':row['document_id'],'replace_legacy':False})
        expected=PLAN.stage(payload,expected,PLAN.ADMISSION)
        own={'version':1,'support_transfer':'none','targets':[{'face_ref':ref,'scope':'target-reviewed-ridge','ridge_sha256':'a'*64,'sides':['left']}]}
        compact={'mime':'image/png','width':128,'height':160,'sha256':'e'*64}
        visual={'version':1,'document_id':row['document_id'],'revision':'3','source_proof':row['proof'],
            'before_state_sha256':'1'*64,'candidate_state_sha256':'1'*64,'before_people_sha256':'2'*64,'candidate_people_sha256':'3'*64,
            'source_size':[128,160],'before_output_size':[128,160],'after_output_size':[128,160],
            'coverage_sha256':VISUAL.coverage_digest(own),'before':compact,'after':compact}
        payload.update(eye_bag_coverage=own,eye_bag_visual=visual)
        snap={'render_sha256':'4'*64,'context_sha256':'5'*64,'graph_sha256':'6'*64}
        targets.append(B.FrozenTarget(row['document_id'],3,i+1,row['path'],None,
            B.canonical({'source_proof':row['proof'],'eye_bag_snapshots':{'before':snap,'after':snap}}),people_json=B.canonical(payload)))
        reviews.append({'visual':visual,'replace_legacy':False})
        acks.append({'document_id':row['document_id'],'revision':'3','before_sha256':'e'*64,'after_sha256':'e'*64,
            'coverage_sha256':visual['coverage_sha256'],'replace_legacy':False})
    monkeypatch.setattr(PLAN,'coverage',lambda engine,row,candidate,payload:deepcopy(payload['eye_bag_coverage']))
    def verify(engine,row,scoped,frozen,payload):
        if scoped['candidate']!=expected:raise ValueError('Frozen complete aggregate changed')
    monkeypatch.setattr(PLAN,'verify',verify)
    store=B.PreflightStore(lambda:1)
    plan=store.create('workspace','source',3,'/source',[EYE.OP],{'_people_transfer':{
        'options':selected,'source_asset':h.ref['asset_sha256'],'source_proof':h.a['source_proof'],
        'state_revision':h.source['revision'],'association_revision':h.source['association_revision'],'source_owner':source_owner}},
        'skip_and_report',targets,[])
    events=[]
    controller=FrozenBatchController(SimpleNamespace(),versions,events.append,lambda:1);controller.store=store
    return SimpleNamespace(engine=engine,batch=batch,rows=rows,owners=owners,plan=plan,controller=controller,
        request={'cmd':'batch','action':'commit','request_id':'commit','preflight_token':plan.token,'eye_bag_review_ack':acks},
        events=events,target=target,expected=expected,refs=refs)


def test_real_commit_first_shared_target_noop_later_target_changed_has_correct_representative(commit_host):
    h=commit_host;BATCH.commit(h.engine,h.controller,h.request,h.plan)
    result=h.events[-1]
    assert result['success'] and result['outcome_unknown'] is False
    assert result['applied']==[2] and result['batch_id'] is not None
    assert [item['outcome'] for item in result['target_outcomes']]==['noop','applied']
    assert h.rows[1]['_rev']==3 and h.rows[2]['_rev']==4
    entry=h.batch.ledger[result['batch_id']]
    assert entry['people_scoped_changes'][0]['document_id']=='target-1'
    assert HISTORY.status_summary(entry)['member_count']==1
    assert h.owners['project'].snapshot()['overrides']==h.expected['overrides']


def test_skip_and_report_cannot_weaken_frozen_aggregate_after_one_target_changes(commit_host):
    h=commit_host;h.rows[2]['_rev']+=1
    with pytest.raises(ValueError,match='aggregate'):BATCH.commit(h.engine,h.controller,h.request,h.plan)
    assert h.plan.token in h.controller.store.pending and not h.controller.store.terminal and not h.batch.ledger
    assert h.owners['project'].snapshot()==h.target


def test_publication_rollback_keeps_consumed_unknown_receipt_and_no_history_entry(commit_host,monkeypatch):
    h=commit_host;owner=h.owners['project'];original=owner.commit
    def fail_after_graph(*args,**kwargs):
        if owner.fence==0:
            original(*args,**kwargs)
            raise ValueError('Injected unknown publication after graph write')
        return original(*args,**kwargs)
    monkeypatch.setattr(owner,'commit',fail_after_graph)
    BATCH.commit(h.engine,h.controller,h.request,h.plan)
    result=h.events[-1]
    assert result['success'] is False and result['outcome_unknown'] is True
    assert result['eye_bag_review_ack']==h.request['eye_bag_review_ack']
    assert h.plan.token not in h.controller.store.pending and not h.batch.ledger
    # Unknown is intentional: a throwing owner may have written before returning.
    assert owner.fence>0


def test_scoped_restore_remembers_active_row_before_dependency_check(commit_host,monkeypatch):
    h=commit_host;BATCH.commit(h.engine,h.controller,h.request,h.plan)
    entry=next(iter(h.batch.ledger.values()));h.engine._doc_index=2
    order=[]
    h.batch.documents.remember_current=lambda:order.append('capture-live')
    def changed(*args):
        order.append('check-repair');raise ValueError('live repair changed')
    monkeypatch.setattr(HISTORY,'verify_restore',changed)
    before=h.owners['project'].snapshot()
    with pytest.raises(ValueError,match='live repair'):LEDGER.restore_scoped(h.engine,entry,False)
    assert order[:2]==['capture-live','check-repair'] and h.owners['project'].snapshot()==before


@pytest.mark.parametrize('value',[True,0,-.1,1.1,'0.6'])
def test_frozen_eye_leaf_domain_and_explicit_activity_match_target_coverage(value):
    store,plan,_,_=frozen_fixture();target=plan.targets[0];payload=json.loads(target.people_json)
    next(leaf for leaf in payload['parameters'] if leaf['parameter_path']=='/amount')['value']=value
    changed=replace(plan,targets=(replace(target,people_json=B.canonical(payload)),))
    with pytest.raises(ValueError):R.records(changed)
