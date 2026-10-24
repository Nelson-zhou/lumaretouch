# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN face-style review/staging/publication contracts.

Real people stage/resolver/recipe validation; synthetic retained face evidence,
mocked immutable source and full-render boundaries. No model/native/photo quality
claim. No product imports, collection, execution, builds or typechecks occurred
while authoring. Blob fixtures are explicitly fake display bytes, not real PNGs.
"""
from base64 import b64encode
from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace
import pytest
from lumaretouch_engine import face_style_review as R, face_style_recipes as REC
from lumaretouch_engine import people_state as S, people_algorithms as A
from lumaretouch_engine import people_preset_plan as PLAN, virtual_copy_people as V
from lumaretouch_engine import people_transfer_inventory as INVENTORY
from lumaretouch_engine.people_resolver import resolve
from lumaretouch_engine import portrait_review_render as DISPLAY

ASSET = 'a' * 64
PAYLOAD = {'version': 1, 'style': 'classic', 'amount': .5}


class Owner:
    def __init__(self, state):
        self.state = deepcopy(state)
        self.fence = 9
    def snapshot(self):
        return deepcopy(self.state)


@pytest.fixture
def host(monkeypatch):
    state = S.empty()
    face = S.new_face(ASSET, [.2, .1, .8, .9], {
        'backend': 'synthetic', 'detector_model_sha256': None,
        'semantic_model_sha256': None, 'landmark_digest': None,
        'status': 'synthetic', 'source_width': 128, 'source_height': 160,
        'orientation': 'exif_normalized_once'})
    face_id = face['face_instance_id']; state['faces'][face_id] = face
    # A known unrelated manual leaf must survive the actual production stage.
    state = S.set_override(state, 'face', face_id, 'lnx.nose_shape.v1', '/wing', -.12)
    owner = Owner(state)
    target = {'scope': 'face', 'target_id': face_id, 'face_ref': S.face_ref(face)}
    row = {'path': '/fixture/source.png', 'src_w': 128, 'src_h': 160, 'asset': ASSET}
    version = SimpleNamespace(document_id='document-one', revision=4)
    current = {'repair': 'repair-0', 'source': ASSET}
    engine = SimpleNamespace(_load_id='load-one', _people_cursors={ASSET: face_id},
        _people_targets={ASSET: deepcopy(target)}, _people_graph_owner=owner,
        _people_scope_row=row, _people_active_context={'owner': owner},
        context='context-0', current=current, row=row, aliases=[row], version=version,
        render_calls=[], history=[], verified=[])
    engine._people_preset_capture = lambda: deepcopy(engine.current)
    engine._docs = engine.aliases
    engine._document_versions = lambda: SimpleNamespace(version=lambda r: engine.version)
    engine._people_binding = lambda: {'document_id': version.document_id,
        'document_epoch': 'epoch-one', 'document_revision': version.revision}
    monkeypatch.setattr(V, 'current_row', lambda e: e.row)
    monkeypatch.setattr(V, 'scope_rows', lambda e, row=None: e.aliases)
    # Retain actual require_active_owner; it must not manufacture/activate owner.
    def source_proof(r):
        asset = r.get('state', current)['source']
        return {'asset_sha256': asset, 'original_sha256': asset, 'creative_source': None}
    monkeypatch.setattr(R.SOURCE, 'row_proof', source_proof)
    monkeypatch.setattr(R.SOURCE, 'row_asset', lambda r: r.get('asset', ASSET))
    monkeypatch.setattr(R.SOURCE, 'binding', lambda state, *args: {
        'sha256': state['source'], 'width': 128, 'height': 160})
    monkeypatch.setattr(R.SOURCE, 'record', lambda state: None)
    def verify(r, proof):
        if source_proof(r) != proof: raise ValueError('Fixture source changed')
        engine.verified.append(deepcopy(proof))
    monkeypatch.setattr(R.SOURCE, 'verify_row', verify)
    monkeypatch.setattr(INVENTORY, 'proof', lambda e, r, s, source_row: {
        'source_proof': source_proof(source_row)})
    def key(e, r, captured, graph):
        normalized = deepcopy(graph); normalized['revision'] = 0
        return {'render_sha256': R.digest(captured), 'context_sha256': R.digest(e.context),
                'graph_sha256': R.digest(normalized)}
    monkeypatch.setattr(R, 'snapshot_key', key)
    def render(e, r, captured, graph, document, revision):
        e.render_calls.append(deepcopy(graph))
        raw = ('FAKE DISPLAY ' + R.digest(graph)).encode()
        compact = {'mime': 'image/png', 'width': 128, 'height': 160,
                   'sha256': sha256(raw).hexdigest()}
        proof = {'source_proof': source_proof({**r, 'state': captured}),
            'source_size': [128, 160], 'output_size': [128, 160],
            'candidate_sha256': R.digest(captured), 'people_sha256': R.digest(graph)}
        return compact, {**compact, 'base64': b64encode(raw).decode()}, proof
    monkeypatch.setattr(R, 'render_image', render)
    yield SimpleNamespace(engine=engine, owner=owner, state=state, target=target, face_id=face_id)
    if '_face_style_reviews' in engine.__dict__:
        engine._face_style_reviews['images'].directory.cleanup()


def preview(h, payload=None):
    return R.preview(h.engine, h.owner.snapshot(), h.target, PAYLOAD if payload is None else payload)['review']


def confirmation(review):
    return {'token': review['token'], 'ack': R._ack(review)}


def test_preview_actual_stage_has_exact_owned_leaves_before_full_render_and_no_mutation(host):
    h = host; before = h.owner.snapshot(); saved = deepcopy(h.engine.current)
    review = preview(h)
    assert h.owner.snapshot() == before and h.owner.fence == 9
    assert h.engine.current == saved and h.engine.history == []
    assert len(h.engine.render_calls) == 2 and h.engine.render_calls[0] == before
    candidate = h.engine.render_calls[1]
    values = A.recipes(resolve(candidate, h.face_id, A.defaults()))
    for patch in REC.patches('classic', .5):
        assert A.leaves(values[patch['operation_id']])[patch['parameter_path']] == patch['value']
    assert values['lnx.nose_shape.v1']['wing'] == -.12
    expected = {(p['operation_id'], p['parameter_path']) for p in REC.patches('classic', .5)}
    actual = {(p['operation_id'], p['parameter_path']) for p in candidate['overrides']}
    assert actual == expected | {('lnx.nose_shape.v1', '/wing')}
    assert review['patches_sha256'] == R.digest(REC.patches('classic', .5))
    assert review['face_ref'] == h.target['face_ref']


@pytest.mark.parametrize('mode', ('person', 'group', 'all_people', 'disabled', 'cursor', 'target', 'source', 'owner'))
def test_live_requires_explicit_current_face_and_source(host, mode):
    h = host; target = deepcopy(h.target)
    if mode in ('person', 'group', 'all_people'): target['scope'] = mode
    elif mode == 'disabled': h.owner.state['faces'][h.face_id]['enabled'] = False
    elif mode == 'cursor': h.engine._people_cursors[ASSET] = 'another-face'
    elif mode == 'target': h.engine._people_targets[ASSET] = {'scope': 'all_people'}
    elif mode == 'source': h.engine.current['source'] = 'b' * 64
    elif mode == 'owner': h.engine._people_active_context = None
    with pytest.raises(ValueError): R.catalogue(h.engine, h.owner.snapshot(), target, {})
    assert not h.engine.render_calls and not h.engine.history


def test_catalogue_allows_alias_discovery_without_render_or_mutation(host):
    h = host; before = h.owner.snapshot()
    h.engine.aliases.append({**h.engine.row, 'path': '/fixture/alias.png'})
    result = R.catalogue(h.engine, h.owner.snapshot(), h.target, {})
    assert result['kind'] == 'face_style_catalog'
    assert h.owner.snapshot() == before and h.owner.fence == 9
    assert not h.engine.render_calls and not h.engine.history


def test_preexisting_v1_review_cannot_authorize_a_new_unseen_alias(host):
    h = host; review = preview(h)
    assert review['version'] == 1
    h.engine.aliases.append({**h.engine.row, 'path': '/fixture/alias.png'})
    with pytest.raises(ValueError):
        R.confirm(h.engine, h.owner.snapshot(), h.target, confirmation(review))
    assert h.owner.snapshot() == h.state and h.owner.fence == 9
    assert h.engine.history == []


@pytest.mark.parametrize('mode', ('source', 'repair', 'context', 'load', 'revision', 'fence', 'cursor', 'analysis', 'path'))
def test_pending_review_refuses_stale_fences_and_snapshots(host, mode):
    h = host; review = preview(h)
    if mode == 'source': h.engine.current['source'] = 'b' * 64
    elif mode == 'repair': h.engine.current['repair'] = 'repair-1'
    elif mode == 'context': h.engine.context = 'context-1'
    elif mode == 'load': h.engine._load_id = 'load-two'
    elif mode == 'revision': h.engine.version.revision += 1
    elif mode == 'fence': h.owner.fence += 1
    elif mode == 'cursor': h.engine._people_cursors[ASSET] = 'another-face'
    elif mode == 'analysis': h.owner.state['faces'][h.face_id]['analysis_revision'] += 1
    elif mode == 'path': h.engine.row['path'] = '/fixture/replaced.png'
    with pytest.raises(ValueError): R.confirm(h.engine, h.owner.snapshot(), h.target, confirmation(review))
    assert h.engine.history == []


def test_images_exact_hash_ack_and_cache_availability(host):
    h = host; review = preview(h)
    for side in ('before', 'after'):
        result = R.image(h.engine, h.owner.snapshot(), h.target,
            {'token': review['token'], 'side': side, 'sha256': review['visual'][side]['sha256']})
        assert result['image']['sha256'] == review['visual'][side]['sha256']
        assert result['review_sha256'] == review['review_sha256']
    with pytest.raises(ValueError):
        R.image(h.engine, h.owner.snapshot(), h.target, {'token': review['token'], 'side': 'after', 'sha256': '0' * 64})
    wrong = confirmation(review); wrong['ack']['review_sha256'] = '0' * 64
    with pytest.raises(ValueError): R.confirm(h.engine, h.owner.snapshot(), h.target, wrong)
    h.engine._face_style_reviews['images'].discard(review['token'])
    with pytest.raises(ValueError): R.confirm(h.engine, h.owner.snapshot(), h.target, confirmation(review))


def test_confirm_detached_candidate_and_successful_own_publish_plus_one(host):
    h = host; review = preview(h); payload = confirmation(review)
    candidate, proof = R.confirm(h.engine, h.owner.snapshot(), h.target, payload)
    assert h.owner.state == h.state and h.owner.fence == 9 and h.engine.version.revision == 4
    R.verify_before_publish(h.engine, h.owner.snapshot(), h.target, payload, candidate, proof)
    # Simulate only the existing owner publication boundary, not a second owner.
    h.owner.state = deepcopy(candidate); h.owner.state['revision'] = h.state['revision'] + 1
    h.owner.fence += 1; h.engine.version.revision += 1
    R.verify_after_publish(h.engine, candidate, proof)
    with pytest.raises(ValueError): R.confirm(h.engine, h.owner.snapshot(), h.target, payload)


@pytest.mark.parametrize('mode', ('candidate', 'proof', 'foreign-owner', 'foreign-row', 'failed', 'double-fence', 'double-revision'))
def test_failed_or_foreign_publication_is_never_accepted(host, mode):
    h = host; review = preview(h); payload = confirmation(review)
    candidate, proof = R.confirm(h.engine, h.owner.snapshot(), h.target, payload)
    if mode in ('candidate', 'proof'):
        if mode == 'candidate': candidate['faces'][h.face_id]['labels']['changed'] = True
        else: proof['review_sha256'] = '0' * 64
        with pytest.raises(ValueError):
            R.verify_before_publish(h.engine, h.owner.snapshot(), h.target, payload, candidate, proof)
        assert not h.engine._face_style_reviews['pending'][review['token']]['claimed']
        return
    R.verify_before_publish(h.engine, h.owner.snapshot(), h.target, payload, candidate, proof)
    if mode != 'failed':
        h.owner.state = deepcopy(candidate); h.owner.fence += 1; h.engine.version.revision += 1
    if mode == 'foreign-owner':
        replacement = Owner(candidate); replacement.fence = h.owner.fence
        h.engine._people_graph_owner = replacement; h.engine._people_active_context = {'owner': replacement}
    elif mode == 'foreign-row':
        h.engine.row = deepcopy(h.engine.row); h.engine._people_scope_row = h.engine.row
    elif mode == 'double-fence': h.owner.fence += 1
    elif mode == 'double-revision': h.engine.version.revision += 1
    with pytest.raises(ValueError): R.verify_after_publish(h.engine, candidate, proof)


@pytest.mark.parametrize('amount', (True, False, None, '0.5', {}, [], -.01, 1.01, float('nan'), float('inf'), 10**1000))
def test_invalid_preview_scalar_refuses_before_render(host, amount):
    h = host
    with pytest.raises(ValueError): preview(h, {**PAYLOAD, 'amount': amount})
    assert not h.engine.render_calls and h.owner.state == h.state


@pytest.mark.parametrize('payload', ({}, {'version': True, 'style': 'classic', 'amount': .5},
    {'version': 2, 'style': 'classic', 'amount': .5}, {**PAYLOAD, 'extra': 1},
    {**PAYLOAD, 'style': 'unknown'}, {**PAYLOAD, 'style': []}))
def test_invalid_preview_schema_refuses_before_render(host, payload):
    with pytest.raises(ValueError): preview(host, payload)
    assert not host.engine.render_calls


def test_conflicting_legacy_intent_refused_before_render(host):
    h = host
    h.owner.state = S.set_override(h.owner.state, 'face', h.face_id, A.DEFORM, '/big_eye', .2)
    before = h.owner.snapshot()
    with pytest.raises(ValueError): preview(h)
    assert not h.engine.render_calls and h.owner.snapshot() == before


def test_render_failure_or_mid_pair_change_never_publishes(host, monkeypatch):
    h = host; original = R.render_image; calls = []
    def changed(*args):
        value = original(*args); calls.append(True)
        if len(calls) == 2: h.engine.current['repair'] = 'changed-during-render'
        return value
    monkeypatch.setattr(R, 'render_image', changed)
    with pytest.raises(ValueError): preview(h)
    assert h.owner.state == h.state and h.owner.fence == 9
    assert '_face_style_reviews' not in h.engine.__dict__


@pytest.mark.parametrize('output,expected', (([128, 160], (128, 160)), ([2048, 4096], (512, 1024)), ([1, 100000], (1, 1024))))
def test_review_display_extent_only(output, expected):
    assert DISPLAY.preview_size(output) == expected


@pytest.mark.parametrize('output', (None, [0, 100], [True, 100], [1., 100], [1, 2, 3], [1, 2**32]))
def test_invalid_full_output_dimensions_refuse(output):
    with pytest.raises(ValueError): DISPLAY.preview_size(output)


def test_shared_snapshot_normalizes_only_graph_commit_counter(host, monkeypatch):
    from lumaretouch_engine import full_candidate_render as FULL
    from lumaretouch_engine import people_export as EXPORT, optics_candidate_identity as IDENTITY
    h = host; e = h.engine
    monkeypatch.setattr(FULL, 'people_context', lambda engine, row: {
        'people_graph': engine._people_graph_owner.snapshot(), 'support': engine.context})
    monkeypatch.setattr(EXPORT, 'isolated_snapshot', lambda snap, **kw: deepcopy(snap))
    monkeypatch.setattr(IDENTITY, 'fingerprint', R.digest)
    def snap(state, **kw):
        return {'repair': state['repair'], 'source': state['source'],
                'people': {'state': deepcopy(kw['people_graph'])}}
    e._state_to_export_snap = snap
    graph = h.owner.snapshot()
    before = DISPLAY.snapshot_key(e, e.row, e.current, graph)
    graph['revision'] += 1
    assert DISPLAY.snapshot_key(e, e.row, e.current, graph) == before
    graph['association_revision'] += 1
    assert DISPLAY.snapshot_key(e, e.row, e.current, graph) != before
    graph = h.owner.snapshot(); graph['overrides'][0]['value'] = -.11
    assert DISPLAY.snapshot_key(e, e.row, e.current, graph) != before
    e.context = 'support-replaced'
    assert DISPLAY.snapshot_key(e, e.row, e.current, h.owner.snapshot()) != before


def test_renderer_exception_has_no_publication_or_pending_review(host, monkeypatch):
    def refuse(*args): raise ValueError('Fixture full render refused evidence')
    monkeypatch.setattr(R, 'render_image', refuse)
    with pytest.raises(ValueError): preview(host)
    assert host.owner.state == host.state and host.owner.fence == 9
    assert '_face_style_reviews' not in host.engine.__dict__


def test_expired_review_cannot_confirm(host):
    review = preview(host)
    host.engine._face_style_reviews['pending'][review['token']]['expires'] = 0
    with pytest.raises(ValueError):
        R.confirm(host.engine, host.owner.snapshot(), host.target, confirmation(review))
    assert host.owner.state == host.state


@pytest.mark.parametrize('target', (None, [], {}, {'scope': 'face'},
    {'scope': 'face', 'target_id': 'different', 'face_ref': {
        'asset_sha256': ASSET, 'face_instance_id': 'face-one', 'analysis_revision': 0}}))
def test_malformed_target_refuses_cleanly(target):
    with pytest.raises(ValueError): R.check_action('face_style_catalog', {}, target)
