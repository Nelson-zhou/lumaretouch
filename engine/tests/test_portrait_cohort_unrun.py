# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: named persistent intent and whole-cohort review contracts.

Graph/recipe functions are production code in these future tests. Endpoint I/O,
render identities, complete snapshot capture and rendered pixels are explicitly
mocked where stated. Cache bytes below are synthetic NON-PNG payloads: they test
byte identity/accounting only, never PNG decoding or photographic quality.
No product imports, collection, tests, inference, builds or typechecks were run
while authoring. Static syntax inspection is not runtime acceptance.
"""
from base64 import b64encode
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
import ast
import json

import pytest
from lumaretouch_engine import people_cross_owner_workflow as W
from lumaretouch_engine import people_state as S
from lumaretouch_engine import face_style_batch_review as NAMED
from lumaretouch_engine import portrait_cohort_review as R
from lumaretouch_engine import portrait_cohort_store as STORE
from lumaretouch_engine import collarbone_visual_store as CLAVICLE
from lumaretouch_engine import cohort_image_cache as CACHE
from lumaretouch_engine import batch_preflight as PREFLIGHT

RECIPE = {'version': 1, 'style': 'classic', 'amount': .5}
ASSOCIATION = 'reviewed-portrait-cohort'


def source(asset):
    return {'original_sha256': asset, 'asset_sha256': asset, 'creative_source': None}


def intent(recipe=RECIPE):
    return [{'op': leaf['operation_id'], 'path': leaf['parameter_path'], 'value': leaf['value']}
            for leaf in NAMED.parameters(recipe)]


def request(rows, *, operation='create', recipe=RECIPE):
    return {'target_policy': 'persistent_association', 'operation': operation,
            'association_id': ASSOCIATION, 'source_ref': deepcopy(rows[0]['ref']),
            'source': deepcopy(rows[0]['proof']),
            'targets': [{'target': deepcopy(item['proof']), 'target_refs': [deepcopy(item['ref'])]}
                        for item in rows[1:]],
            'selection': NAMED.selection(recipe) if recipe is not None else {},
            **({'face_style': deepcopy(recipe)} if recipe is not None else {})}


def endpoints():
    rows = []
    for index, letter in enumerate(('a', 'b', 'c')):
        document = str(index + 1) * 32
        graph = S.empty()
        face = S.new_face(letter * 64, [.1, .1, .8, .9], {
            'backend': 'authored-fixture-only', 'detector_model_sha256': 'd' * 64,
            'semantic_model_sha256': None, 'landmark_digest': 'e' * 64,
            'status': 'verified', 'source_width': 128, 'source_height': 160,
            'orientation': 'exif_normalized_once'})
        graph['faces'][face['face_instance_id']] = face
        ref = S.face_ref(face)
        # Deliberately not the named recipe's shared value. Explicit face
        # precedence must survive, rather than becoming a donor coefficient.
        graph = S.set_override(graph, 'face', ref['face_instance_id'],
                               'lnx.face_size.v1', '/amount', .91 - index * .1)
        graph = S.set_override(graph, 'face', ref['face_instance_id'],
                               'lnx.nose_shape.v1', '/wing', -.12)
        proof = {'document': {'document_id': document, 'epoch': 'fixture-workspace', 'revision': 4},
                 'people_scope': document, 'state_revision': graph['revision'],
                 'association_revision': graph['association_revision'],
                 'graph_sha256': W.I.graph_digest(graph), 'source_proof': source(letter * 64)}
        rows.append({'index': index, 'row': {'path': letter + '.png', 'document_id': document,
                                           'state': {}, 'src_w': 128, 'src_h': 160},
                     'before': graph, 'proof': proof, 'ref': ref,
                     'member': {'document_id': document, 'scope_id': document,
                                'original_sha256': letter * 64, 'ref': deepcopy(ref)}})
    return rows


def prepare_fixture(monkeypatch, rows, selected):
    """Mock only endpoint/source I/O; retain real intent composition and graphs."""
    documents = [item['row'] for item in rows]
    by_id = {item['row']['document_id']: item for item in rows}
    engine = SimpleNamespace(
        _batch_controller=lambda: SimpleNamespace(documents=SimpleNamespace(rows=lambda: documents)),
        _document_versions=lambda: SimpleNamespace(
            version=lambda row: SimpleNamespace(document_id=row['document_id'])))

    def endpoint(_engine, actual_rows, proof, ref, *, reviewed_only=False):
        assert actual_rows is documents
        assert reviewed_only is ('face_style' in selected)
        item = deepcopy(by_id[proof['document']['document_id']])
        if item['proof'] != proof or item['ref'] != ref:
            raise ValueError('stale explicit fixture endpoint')
        return item

    with monkeypatch.context() as patch:
        patch.setattr(W, '_endpoint', endpoint)
        patch.setattr(W.I, 'verify', lambda *args, **kwargs: None)
        patch.setattr(W.SOURCE, 'verify_row', lambda *args, **kwargs: None)
        patch.setattr(W.V, 'row_snapshot', lambda _engine, row: by_id[row['document_id']]['before'])
        return W.prepare(engine, selected, validate=False)


def accept_candidates(rows, staged):
    for item, candidate in zip(rows, staged):
        item['before'] = deepcopy(candidate['candidate'])
        item['proof'].update(state_revision=item['before']['revision'],
                             association_revision=item['before']['association_revision'],
                             graph_sha256=W.I.graph_digest(item['before']))


def test_named_create_uses_local_recipe_not_selected_source_values(monkeypatch):
    rows = endpoints(); selected = request(rows); originals = deepcopy(rows)

    def forbidden(*args, **kwargs):
        raise AssertionError('Named cohort cannot read donor-selected scalar leaves')

    monkeypatch.setattr(W, '_selected', forbidden)
    staged, review = prepare_fixture(monkeypatch, rows, selected)
    assert rows == originals and review['intent'] == intent()
    assert len(review['intent']) == 30
    for item in staged:
        capsule = item['candidate']['persons'][ASSOCIATION]['cross_owner']
        assert capsule['version'] == 1 and capsule['intent'] == review['intent']
        assert 'face_style' not in capsule
        assert capsule['generation'] == review['generation']
        assert item['candidate']['faces'] == item['before']['faces']
        assert [v for v in item['candidate']['overrides'] if v['scope'] == 'face'] == item['before']['overrides']
        resolved = W.resolve(item['candidate'], item['ref']['face_instance_id'], W.A.defaults())
        assert resolved['operations']['lnx.face_size.v1']['/amount']['value'] == .91 - item['index'] * .1
        assert resolved['operations']['lnx.nose_shape.v1']['/wing']['value'] == -.12


def test_named_options_reject_unlink_partial_scope_and_mixed_leaves():
    rows = endpoints(); selected = request(rows); modules = list(selected['selection'])
    assert W.options(selected, modules) == selected
    bad = deepcopy(selected); bad['operation'] = 'unlink'
    with pytest.raises(ValueError): W.options(bad, modules)
    with pytest.raises(ValueError): W.options(selected, modules[:-1])
    with pytest.raises(ValueError): W.options(selected, modules[::-1])
    bad = deepcopy(selected); bad['selection']['lnx.collarbone.v1'] = ['/amount']
    with pytest.raises(ValueError): W.options(bad, list(bad['selection']))


@pytest.mark.parametrize('next_style', ['classic', 'square'])
def test_zero_named_patch_keeps_existing_canonical_noop_refusal(monkeypatch, next_style):
    rows = endpoints(); zero = {**RECIPE, 'amount': 0}
    created, _ = prepare_fixture(monkeypatch, rows, request(rows, recipe=zero))
    accept_candidates(rows, created); before = deepcopy(rows)
    selected = request(rows, operation='patch', recipe={**zero, 'style': next_style})
    with pytest.raises(ValueError, match='does not change shared person intent'):
        prepare_fixture(monkeypatch, rows, selected)
    assert rows == before


def test_generic_patch_and_unlink_keep_fullkey_lifecycle_gate(monkeypatch):
    rows = endpoints(); created, _ = prepare_fixture(monkeypatch, rows, request(rows))
    accept_candidates(rows, created)
    selected = request(rows, operation='patch', recipe=None)
    selected['selection'] = {'lnx.face_size.v1': ['/amount']}
    patched, review = prepare_fixture(monkeypatch, rows, selected)
    assert len(review['intent']) == 30 and R.required(patched, selected, review)
    assert next(v['value'] for v in review['intent']
                if (v['op'], v['path']) == ('lnx.face_size.v1', '/amount')) == .91
    accept_candidates(rows, patched)
    selected = request(rows, operation='unlink', recipe=None)
    removed, review = prepare_fixture(monkeypatch, rows, selected)
    assert selected['selection'] == {} and R.required(removed, selected, review)
    assert all(not item['candidate']['persons'] for item in removed)
    assert all([v for v in item['candidate']['overrides'] if v['scope'] == 'face'] ==
               [v for v in item['before']['overrides'] if v['scope'] == 'face'] for item in removed)


def test_gate_uses_complete_keys_not_values_style_label_or_one_geometry_leaf():
    full = intent({**RECIPE, 'amount': 0})
    assert R.content_required(full)
    mutated = deepcopy(full); mutated[-1]['value'] = .123
    assert R.content_required(mutated)
    assert not R.content_required(full[:-1])
    assert not R.content_required([{'op': 'lnx.face_size.v1', 'path': '/amount', 'value': .5}])
    assert not R.content_required(None)
    for stage in ('before', 'candidate'):
        rows = [{'before': {'persons': {}}, 'candidate': {'persons': {}}}]
        rows[0][stage]['persons'][ASSOCIATION] = {'cross_owner': {'association_id': ASSOCIATION, 'intent': full}}
        assert R.required(rows, {'association_id': ASSOCIATION}, {'intent': []})
        assert not R.required(rows, {'association_id': 'another'}, {'intent': []})


def pixels(label):
    raw = ('authored-non-png-' + label).encode()
    compact = {'mime': 'image/png', 'width': 1, 'height': 1, 'sha256': sha256(raw).hexdigest()}
    return compact, {**compact, 'base64': b64encode(raw).decode()}


def visual(document, *, cohort='f' * 64):
    left, _ = pixels(document + '-before'); right, _ = pixels(document + '-after')
    return {'version': 1, 'document_id': document, 'revision': '4', 'source_proof': source('a' * 64),
            'before_state_sha256': 'b' * 64, 'candidate_state_sha256': 'b' * 64,
            'before_people_sha256': 'c' * 64, 'candidate_people_sha256': 'd' * 64,
            'source_size': [1, 1], 'before_output_size': [1, 1], 'after_output_size': [1, 1],
            'before': left, 'after': right, 'cohort_sha256': cohort}


def ack(record):
    return {'document_id': record['document_id'], 'revision': record['revision'],
            'before_sha256': record['before']['sha256'], 'after_sha256': record['after']['sha256'],
            'cohort_sha256': record['cohort_sha256']}


def test_ack_requires_source_first_every_member_and_same_cohort_identity():
    records = [visual('source'), visual('target-a'), visual('target-b')]
    values = [ack(record) for record in records]
    assert R.acknowledgments(values, records) == values
    for bad in (None, [], values[1:], values[::-1], values + [values[0]]):
        with pytest.raises(ValueError): R.acknowledgments(bad, records)
    for field in values[0]:
        bad = deepcopy(values); bad[0][field] = 'changed'
        with pytest.raises(ValueError): R.acknowledgments(bad, records)
    with pytest.raises(ValueError): R.acknowledgments(values[:1], records[:1])
    changed = deepcopy(records); changed[-1]['cohort_sha256'] = 'e' * 64
    with pytest.raises(ValueError): R.acknowledgments([ack(v) for v in changed], changed)


def render_fixture(monkeypatch):
    rows = [{'row': {'state': {'owner': name}}, 'before': {'side': 'before'}, 'candidate': {'side': 'after'},
             'proof': {'document': {'document_id': name, 'revision': 4}}}
            for name in ('source', 'target-a', 'target-b')]
    records = {item['proof']['document']['document_id']: visual(item['proof']['document']['document_id']) for item in rows}
    calls = []; snapshots = {'revision': 1}
    monkeypatch.setattr(R, 'digest', lambda selected, review: 'f' * 64)
    monkeypatch.setattr(R, 'snapshots', lambda engine, item: {'before': snapshots['revision'], 'after': snapshots['revision']})
    monkeypatch.setattr(R, '_identities', lambda engine, item, digest: {
        k: deepcopy(v) for k, v in records[item['proof']['document']['document_id']].items() if k not in ('before', 'after')})

    def image(engine, row, state, graph, document, revision):
        calls.append((document, graph['side'], row, graph))
        record = records[document]; side = graph['side']
        compact, display = pixels(document + '-' + side)
        return compact, display, {'source_proof': record['source_proof'], 'source_size': [1, 1], 'output_size': [1, 1],
                                  'candidate_sha256': record['before_state_sha256'],
                                  'people_sha256': record['before_people_sha256' if side == 'before' else 'candidate_people_sha256']}

    monkeypatch.setattr(R, 'image', image)
    return rows, records, calls, snapshots


def test_preparation_renders_actual_source_and_all_members_then_fences_snapshots(monkeypatch):
    rows, _, calls, snapshots = render_fixture(monkeypatch)
    displays = R.prepare(object(), rows, {}, {})
    assert list(displays) == ['source', 'target-a', 'target-b']
    assert [(doc, side) for doc, side, _, _ in calls] == [
        (name, side) for name in displays for side in ('before', 'after')]
    assert all('portrait_snapshots' not in R.evidence(item) for item in rows)
    assert all('portrait_snapshots' in R.evidence(item, private=True) for item in rows)
    snapshots['revision'] += 1
    with pytest.raises(ValueError, match='snapshot|Complete cohort'):
        R.verify(object(), rows[0], rows[0], 'f' * 64)


def test_dual_review_reuses_identical_pixels_without_second_render(monkeypatch):
    rows, records, calls, _ = render_fixture(monkeypatch); displays = {}
    for item in rows:
        doc = item['proof']['document']['document_id']; record = records[doc]
        item['collarbone_visual'] = {k: deepcopy(v) for k, v in record.items() if k != 'cohort_sha256'}
        item['collarbone_visual']['coverage_sha256'] = 'e' * 64
        displays[doc] = {'revision': '4', 'before': pixels(doc + '-before')[1], 'after': pixels(doc + '-after')[1]}
    assert R.prepare(object(), rows, {}, {}, existing_displays=displays) == displays
    assert calls == []
    rows[0]['collarbone_visual']['candidate_people_sha256'] = '1' * 64
    with pytest.raises(ValueError, match='identical'):
        R.prepare(object(), rows, {}, {}, existing_displays=displays)
    assert calls == []


def cache_fixture(monkeypatch, *, portrait=True, collarbone=True):
    """Mock frozen-plan admission; use real proof-family/cache/byte checks."""
    records = [visual('source'), visual('target')]; displays = {}; targets = []
    params = {'_people_transfer': {'mode': 'persistent_association', 'collarbone_visual_required': collarbone}}
    for record in records:
        doc = record['document_id']
        clavicle = {k: deepcopy(v) for k, v in record.items() if k != 'cohort_sha256'}
        clavicle['coverage_sha256'] = 'e' * 64
        targets.append(SimpleNamespace(document_id=doc, revision=4, blocked=None,
                                       people_json=json.dumps({'collarbone_visual': clavicle})))
        displays[doc] = {'revision': '4', 'before': pixels(doc + '-before')[1], 'after': pixels(doc + '-after')[1]}
    plan = SimpleNamespace(token='a' * 32, source_id='source', modules=[], targets=targets, params=lambda: params)
    store = SimpleNamespace(pending={plan.token: plan}, clock=lambda: 0, _prune=lambda now: None)

    def get(token, workspace):
        if workspace != 'fixture-workspace' or token not in store.pending: raise ValueError('missing plan')
        return store.pending[token]

    store.get = get
    owner = SimpleNamespace(store=store, versions=SimpleNamespace(workspace='fixture-workspace'))
    monkeypatch.setattr(PREFLIGHT, 'portrait_cohort_records', lambda value: deepcopy(records) if portrait else None)
    read = {'cmd': 'batch', 'action': 'portrait_cohort_visual', 'request_id': 'read-source',
            'preflight_token': plan.token, 'document_id': 'source', 'revision': '4',
            'side': 'before', 'sha256': records[0]['before']['sha256']}
    return owner, plan, records, displays, read


def test_dual_families_share_one_cache_and_exact_member_pairs(monkeypatch):
    owner, plan, records, displays, read = cache_fixture(monkeypatch)
    CLAVICLE.attach(owner.store, plan, displays)
    cache = owner.store._collarbone_visual_images; size = cache.bytes
    STORE.attach(owner.store, plan, displays)
    assert cache is owner.store._portrait_cohort_images is owner.store._cohort_review_images
    assert cache.count == 4 and cache.bytes == size
    assert STORE.retrieve(owner, read)['image'] == CLAVICLE.retrieve(owner, {**read, 'action': 'collarbone_visual'})['image']
    STORE.verify_available(owner.store, plan); CLAVICLE.verify_available(owner.store, plan)
    altered = json.loads(plan.targets[0].people_json)
    altered['collarbone_visual']['candidate_people_sha256'] = '1' * 64
    plan.targets[0].people_json = json.dumps(altered)
    with pytest.raises(ValueError, match='same source and image pair'): CACHE.records(plan)
    with pytest.raises(ValueError): STORE.retrieve(owner, read)


@pytest.mark.parametrize('portrait,collarbone', [(True, False), (False, True)])
def test_shared_cache_cannot_lend_authority_to_another_family(monkeypatch, portrait, collarbone):
    owner, plan, _, displays, read = cache_fixture(monkeypatch, portrait=portrait, collarbone=collarbone)
    if portrait:
        STORE.attach(owner.store, plan, displays)
        assert STORE.retrieve(owner, read)['success'] is True
        with pytest.raises(ValueError): CLAVICLE.retrieve(owner, {**read, 'action': 'collarbone_visual'})
    else:
        CLAVICLE.attach(owner.store, plan, displays)
        assert CLAVICLE.retrieve(owner, {**read, 'action': 'collarbone_visual'})['success'] is True
        with pytest.raises(ValueError): STORE.retrieve(owner, read)


def test_shared_attach_refuses_replaced_pixels_and_prunes_all_aliases(monkeypatch):
    owner, plan, _, displays, read = cache_fixture(monkeypatch)
    CLAVICLE.attach(owner.store, plan, displays)
    changed = deepcopy(displays); changed['source']['after']['base64'] = b64encode(b'other').decode()
    with pytest.raises(ValueError, match='pixels differ'): STORE.attach(owner.store, plan, changed)
    assert STORE.retrieve(owner, read)['image'] == displays['source']['before']
    owner.store.pending.clear(); STORE.prune(owner.store)
    assert owner.store._cohort_review_images.count == 0 and owner.store._cohort_review_images.bytes == 0


def test_named_transfer_family_does_not_claim_persistent_named_requests():
    value = {'options': {'target_policy': 'persistent_association', 'face_style': RECIPE},
             'mode': 'persistent_association'}
    plan = SimpleNamespace(params=lambda: {'_people_transfer': value})
    assert not NAMED.required(plan)
    value['options']['target_policy'] = 'explicit_face_map'
    assert not NAMED.required(plan)
    value.pop('mode')
    assert NAMED.required(plan)


def test_static_commit_order_keeps_every_review_before_claim_and_ledger_publish():
    path = Path(__file__).parents[1] / 'src/lumaretouch_engine/people_cross_owner_workflow.py'
    tree = ast.parse(path.read_text())
    commit = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'commit')
    calls = [(ast.unparse(node.func), node.lineno) for node in ast.walk(commit) if isinstance(node, ast.Call)]
    line = lambda name: [number for function, number in calls if function == name]
    assert max(line('PORTRAIT.acknowledgments')) < min(line('prepare'))
    assert max(line('PORTRAIT.verify')) < min(line('controller.store.claim'))
    assert max(line('verify_available')) < min(line('controller.store.claim'))
    assert max(line('controller.store.claim')) < min(line('commit_scoped'))
