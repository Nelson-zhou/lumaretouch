# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN current-photo BODY source/full-image review contracts.

Real scalar/relation/graph validators, synthetic retained source evidence and
mocked authenticated decode/full-render/publication boundaries. No test was
collected/executed; no product import, native inference, build or photographic
acceptance ran while authoring. Fake display bytes are explicitly not real PNG.
"""
from base64 import b64encode
from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace

import numpy as np
import pytest

from lumaretouch_engine import skin_reference_body_host as H
from lumaretouch_engine import skin_reference_body_project as PROJECT
from lumaretouch_engine import skin_reference_body_state as S
from lumaretouch_engine import skin_reference_body_support as SUPPORT
from lumaretouch_engine import people_state as P, virtual_copy_people as V
from lumaretouch_engine import face_style_alias_review as ALIASES
from lumaretouch_engine import full_candidate_render as FULL
from lumaretouch_engine import people_transfer_inventory as INVENTORY
from lumaretouch_engine import people_host_commands as COMMANDS
from lumaretouch_engine import skin_colour_support as SEM
from lumaretouch_engine import body_skin_semantics as BODY_SEM
from lumaretouch_engine import body_pose_state as B, body_pose_evidence as E
from lumaretouch_engine import body_pose_project as BODY_PROJECT
from lumaretouch_engine import shoulder_shape_project as BODY_STORE
from lumaretouch_engine import people_associations as ASSOCIATIONS
from lumaretouch_engine import people_graph_owner as GRAPH
from lumaretouch_engine import skin_reference_match_project as FACE_PROJECT
from lumaretouch_engine import skin_reference_match_support as FACE_SUPPORT
from lumaretouch_engine import skin_reference_match_state as FACE_STATE

ASSET = 'a' * 64


class Owner:
    def __init__(self, state):
        self.state = deepcopy(state); self.fence = 7
    def snapshot(self):
        return deepcopy(self.state)


def face(state, key, x):
    points = np.full((478, 3), [x, .5, 0.], dtype='<f4')
    evidence = {'backend': 'mediapipe', 'detector_model_sha256': 'b'*64,
        'semantic_model_sha256': 'c'*64, 'landmark_digest': sha256(points.tobytes()).hexdigest(),
        'status': 'verified', 'source_width': 256, 'source_height': 128,
        'orientation': 'exif_normalized_once'}
    value = P.new_face(ASSET, [x-.06, .2, x+.06, .8], evidence)
    value['face_instance_id'] = key; state['faces'][key] = value
    ref = P.face_ref(value)
    return ref, {'face_ref': ref, 'evidence': deepcopy(evidence), 'landmarks': points,
        'body_skin': np.full((64, 128), .8, np.float32),
        'body_skin_observation': {'contract': BODY_SEM.CONTRACT, 'source_sha256': ASSET,
            'semantic_model_sha256': 'c'*64, 'detector_model_sha256': 'b'*64,
            'producer_width': 128, 'producer_height': 64},
        'face_skin': np.full((64, 128), .7, np.float32), 'excluded': np.zeros((64, 128), np.float32),
        'face_skin_observation': {'contract': SEM.CONTRACT, 'source_sha256': ASSET,
            'semantic_model_sha256': 'c'*64, 'producer_width': 128, 'producer_height': 64}}


def display(raw):
    return {'mime': 'image/png', 'width': 256, 'height': 128, 'sha256': sha256(raw).hexdigest(),
            'base64': b64encode(raw).decode('ascii')}


@pytest.fixture
def host(monkeypatch):
    state = P.empty(); refs = {}; analyses = {}
    for key, x in (('first', .15), ('second', .38), ('reference', .62), ('other-reference', .85)):
        refs[key], analyses[key] = face(state, key, x)
    state = P.set_override(state, 'face', 'first', 'lnx.nose_shape.v1', '/wing', -.12)
    people = {}
    for key in ('first', 'second', 'reference'):
        state, people[key] = ASSOCIATIONS.create_person(state)
        state = ASSOCIATIONS.set_link(state, key, people[key], 'confirmed', user_confirmed=True)
    source_frame = {'sha256': ASSET, 'width': 256, 'height': 128, 'orientation': E.ORIENTATION}
    points = [{'index': index, 'x': .5, 'y': .5, 'z': 0., 'visibility': 0., 'presence': 0.}
              for index in range(33)]
    body_records = {key: E.create(source_frame=source_frame, values=points,
        backend_version='synthetic-fixture', backend_code_sha256='d'*64, model_id='synthetic-fixture',
        model_sha256='e'*64, input_rgb_sha256='f'*64, input_dimensions=(128, 64)) for key in people}
    bodies = B.add_run(B.empty(), {'source': source_frame, 'records': list(body_records.values()),
        'detector_limit': 4, 'limit_reached': False, 'census_complete': False})
    for key, measured in body_records.items():
        bodies = B.associate(bodies, measured['body_ref'], people[key], state, user_confirmed=True)
    owner = Owner(state)
    row = {'path': '/synthetic/source.png', 'src_w': 256, 'src_h': 128, 'document_id': 'document-one'}
    version = SimpleNamespace(document_id='document-one', revision=5)
    source = {'sha256': ASSET, 'width': 256, 'height': 128}
    source_proof = {'asset_sha256': ASSET, 'original_sha256': ASSET, 'creative_source': None}
    target = {'scope': 'all_people', 'target_id': ASSET, 'face_ref': None}
    engine = SimpleNamespace(_people_graph_owner=owner, _people_active_context={'owner': owner}, _people_scope_row=row,
        _load_id='load-one', _people_support={}, _people_analyses={ASSET: analyses}, _docs=[row],
        _people_cursors={ASSET: 'other-reference'}, _people_targets={ASSET: {'scope': 'person', 'target_id': 'unrelated'}},
        current={'source': ASSET, 'repair': 'repair-0'}, row=row, version=version, context='context-0',
        renders=[], writes=[], _people_staged=None, body_bank=bodies)
    engine._body_bank = lambda: deepcopy(engine.body_bank)
    engine._people_source = lambda: deepcopy(source)
    engine._people_preset_capture = lambda: deepcopy(engine.current)
    engine._document_versions = lambda: SimpleNamespace(version=lambda r: version)
    monkeypatch.setattr(V, 'current_row', lambda e: e.row)
    monkeypatch.setattr(V, 'scope_rows', lambda e, row=None: e._docs)
    monkeypatch.setattr(ALIASES, 'verify_dormant', lambda *args: None)
    monkeypatch.setattr(H.SOURCE, 'binding', lambda *args: deepcopy(source))
    monkeypatch.setattr(H.SOURCE, 'row_asset', lambda r: r.get('state', engine.current)['source'])
    monkeypatch.setattr(H.SOURCE, 'row_proof', lambda r: {**source_proof, 'asset_sha256': r.get('state', engine.current)['source']})
    def verify(r, proof):
        if H.SOURCE.row_proof(r) != proof:
            raise ValueError('Synthetic source changed')
    monkeypatch.setattr(H.SOURCE, 'verify_row', verify)
    monkeypatch.setattr(S, 'capability', lambda: {'skin_reference_body_available': True, 'skin_reference_body_reason': None})
    monkeypatch.setattr(H, '_source_display', lambda e, s: (display(b'FAKE SOURCE DISPLAY'), 'd'*64))
    monkeypatch.setattr(INVENTORY, 'proof', lambda e, r, s, source_row: {
        'document_id': version.document_id, 'revision': str(version.revision), 'people_scope': 'project',
        'state_revision': s['revision'], 'association_revision': s['association_revision'], 'source_proof': source_proof})
    monkeypatch.setattr(FULL, 'people_context', lambda e, r: {
        'people_graph': owner.snapshot(), 'people_support_assets': deepcopy(e._people_support), 'other': e.context})
    def key(e, r, current, graph, *, staged_people_context=None):
        context = FULL.people_context(e, r) if staged_people_context is None else staged_people_context
        normalized = deepcopy(graph); normalized['revision'] = 0
        return {'render_sha256': H.digest(current), 'graph_sha256': H.digest(normalized),
                'context_sha256': H.digest({k: v for k, v in context.items() if k != 'people_graph'})}
    monkeypatch.setattr(H, 'snapshot_key', key)
    def render(e, r, current, graph, document, revision, *, staged_people_context=None):
        e.renders.append({'graph': deepcopy(graph), 'live_bank': deepcopy(e._people_support),
                          'context': deepcopy(staged_people_context)})
        pixels = display(('FAKE MIXED DISPLAY ' + H.digest(key(e, r, current, graph,
            staged_people_context=staged_people_context))).encode())
        compact = {k: v for k, v in pixels.items() if k != 'base64'}
        proof = {'source_proof': source_proof, 'source_size': [256, 128], 'output_size': [256, 128],
                 'candidate_sha256': H.digest(current), 'people_sha256': H.digest(graph)}
        return compact, pixels, proof
    monkeypatch.setattr(H, 'render_image', render)
    def publish(e, before, candidate, request, *, shared=False, before_publish=None):
        assert shared is False
        PROJECT.require_transition(e, before, candidate)
        if before_publish:
            before_publish()
        e.writes.append(request); owner.state = deepcopy(candidate); owner.fence += 1; version.revision += 1
        return None, {'event': 'frame'}
    monkeypatch.setattr(COMMANDS, 'publish', publish)
    yield SimpleNamespace(engine=engine, owner=owner, refs=refs, target=target, source=source,
                          version=version, bodies=body_records, source_proof=source_proof)
    if '_skin_reference_body_reviews' in engine.__dict__:
        engine._skin_reference_body_reviews['images'].directory.cleanup()



def catalog(h):
    return H.catalogue(h.engine, h.owner.snapshot(), h.target, {})


def body_review(h, target='first'):
    record = h.bodies[target]
    return {'operation_id': S.OP, 'body_ref': deepcopy(record['body_ref']),
        'points_sha256': record['points_sha256'], 'visible': True, 'unoccluded': True,
        'ownership_confirmed': True, 'reference_unchanged': True,
        'recipe': {'version': 1, 'domain': 'source-normalized', 'objects': [{
            'id': 'body-selection', 'name': 'Synthetic manually reviewed body skin', 'kind': 'brush',
            'enabled': True, 'operation': 'add', 'opacity': 1., 'feather': 0.,
            'points': [[.25, .85], [.25, .92]], 'axes': [[.08, 0.], [0., .05]]}]}}


def payload(h, *, reference='reference', target='first', amount=.5):
    source = catalog(h)
    return {'version': 1, 'reference_face_ref': deepcopy(h.refs[reference]),
        'target_face_ref': deepcopy(h.refs[target]), 'review': body_review(h, target), 'amount': amount,
        'source_review_sha256': source['source_review_sha256'], 'ownership_confirmed': True}


def preview(h, **kwargs):
    return H.preview(h.engine, h.owner.snapshot(), h.target, payload(h, **kwargs))['review']


def loaded(h, review):
    for side in ('before', 'after'):
        result = H.image(h.engine, h.owner.snapshot(), h.target, {'token': review['token'], 'side': side,
            'sha256': review['visual'][side]['sha256'], 'review_sha256': review['review_sha256']})
        assert result['image']['sha256'] == review['visual'][side]['sha256']
    return {'token': review['token'], 'ack': H._ack(review)}


def commit(h, review):
    action = loaded(h, review); before = h.owner.snapshot()
    candidate, proof = H.confirm(h.engine, before, h.target, action)
    started = []
    result = H.publish(h.engine, before, h.target, action, candidate, proof,
                       'request-' + review['token'], lambda: started.append(True))
    assert result[0] is None and started == [True]
    return candidate, proof


def attach_face(h, *, target='second', reference='reference', amount=.3):
    before = h.owner.snapshot(); analyses = h.engine._people_analyses[ASSET]
    state, assets = FACE_SUPPORT.retain(before, h.engine._people_support,
        h.refs[target], h.refs[reference], analyses[target], analyses[reference], confirmed=True)
    state = P.set_override(state, 'face', target, FACE_STATE.OP, '/amount', amount)
    h.owner.state = state; h.engine._people_support = assets
    return state


def test_catalog_is_explicit_current_source_and_lists_genuine_owned_body_choices(host):
    h = host; before = h.owner.snapshot(); result = catalog(h)
    assert result['operation_id'] == S.OP and result['scope'] == 'current-photo-body-only'
    assert result['source_image']['base64'] == b64encode(b'FAKE SOURCE DISPLAY').decode()
    assert result['source'] == h.source and result['source_proof'] == h.source_proof
    assert result['body_matching'] is True and result['automatic_reference'] is False
    assert len(result['faces']) == 4 and len(result['targets']) == 3
    assert {row['face_ref']['face_instance_id'] for row in result['targets']} == {'first', 'second', 'reference'}
    assert h.owner.snapshot() == before and h.engine._people_support == {} and h.engine.writes == []
    assert h.engine._people_cursors[ASSET] == 'other-reference'


def test_body_only_preview_keeps_all_face_recipes_and_uses_separate_support(host):
    h = host; before = h.owner.snapshot(); review = preview(h)
    assert len(h.engine.renders) == 2 and h.engine.renders[0]['graph'] == before
    candidate = h.engine.renders[1]['graph']; assets = h.engine.renders[1]['context']['people_support_assets']
    assert h.owner.snapshot() == before and h.engine._people_support == {} and h.engine.writes == []
    assert PROJECT.active_refs(candidate, ASSET) == [h.refs['first']]
    assert FACE_PROJECT.active_refs(candidate, ASSET) == []
    assert FACE_SUPPORT.KIND not in candidate['faces']['first']['local_assets']
    assert candidate['faces']['reference'] == before['faces']['reference']
    assert [row for row in candidate['overrides'] if row['operation_id'] != S.OP] == before['overrides']
    assert len(assets) == 1 and review['body_review'] == body_review(h)
    assert review['body_ref'] == h.bodies['first']['body_ref']
    assert review['body_bank_sha256'] == H.digest(h.engine.body_bank)
    assert review['before_current']['target_face_refs'] == []
    assert review['candidate_current']['target_face_refs'] == [h.refs['first']]


def test_reference_can_be_body_owners_own_face_without_face_correction(host):
    h = host; review = preview(h, target='reference')
    candidate, _ = commit(h, review)
    assert review['reference_face_ref'] == review['target_face_ref'] == h.refs['reference']
    assert FACE_PROJECT.active_refs(candidate, ASSET) == []
    assert PROJECT.common_reference(candidate, h.engine._people_support, ASSET, h.engine.body_bank) == h.refs['reference']


def test_body_owner_does_not_need_face_skin_when_another_face_is_reference(host):
    h = host; row = h.engine._people_analyses[ASSET]['first']
    row.pop('face_skin'); row.pop('face_skin_observation')
    result = catalog(h)
    assert next(item for item in result['faces'] if item['face_ref'] == h.refs['first'])['available'] is False
    assert any(item['face_ref'] == h.refs['first'] for item in result['targets'])
    review = preview(h); assert review['target_face_ref'] == h.refs['first']


def test_one_body_review_retains_prior_targets_and_amounts(host):
    h = host; first, _ = commit(h, preview(h, amount=.25))
    old_pointer = deepcopy(first['faces']['first']['local_assets'][SUPPORT.KIND])
    review = preview(h, target='second', amount=.7)
    candidate, _ = commit(h, review)
    assert PROJECT.active_refs(candidate, ASSET) == [h.refs['first'], h.refs['second']]
    assert PROJECT.recipe(candidate, 'first')['amount'] == .25
    assert candidate['faces']['first']['local_assets'][SUPPORT.KIND] == old_pointer
    assert review['before_current']['amounts'][0] == review['candidate_current']['amounts'][0]
    assert review['candidate_current']['amounts'][1]['amount'] == .7
    assert len(h.engine.writes) == 2 and len(h.engine._people_support) == 2


def test_mixed_face_body_uses_common_reference_without_touching_face_support(host):
    h = host; before = attach_face(h)
    review = preview(h); candidate, _ = commit(h, review)
    assert candidate['faces']['second']['local_assets'] == before['faces']['second']['local_assets']
    assert FACE_PROJECT.recipe(candidate, 'second') == FACE_PROJECT.recipe(before, 'second')
    assert FACE_PROJECT.active_refs(candidate, ASSET) == [h.refs['second']]
    assert PROJECT.common_reference(candidate, h.engine._people_support, ASSET, h.engine.body_bank) == h.refs['reference']


@pytest.mark.parametrize('existing', ['face', 'body'])
def test_changing_reference_cannot_silently_replace_other_active_targets(host, existing):
    h = host
    if existing == 'face': attach_face(h)
    else: commit(h, preview(h))
    before = h.owner.snapshot(); before_assets = deepcopy(h.engine._people_support)
    count = len(h.engine.renders)
    with pytest.raises(ValueError, match='reference'):
        preview(h, target='second', reference='other-reference')
    assert h.owner.snapshot() == before and h.engine._people_support == before_assets
    assert len(h.engine.renders) == count


@pytest.mark.parametrize('fault', ['ownership', 'wrong-op', 'old-consent', 'missing-proof', 'foreign',
    'foreign-body', 'stale-points', 'zero', 'extra-target', 'false-visible', 'false-reference', 'body-as-owner'])
def test_preview_refuses_borrowed_or_ambiguous_consent(host, fault):
    h = host; action = payload(h)
    if fault == 'ownership': action['ownership_confirmed'] = False
    elif fault == 'wrong-op': action['review']['operation_id'] = 'lnx.body_face_match.v1'
    elif fault == 'old-consent': del action['review']['operation_id']; del action['review']['reference_unchanged']
    elif fault == 'missing-proof': del action['source_review_sha256']
    elif fault == 'foreign': action['reference_face_ref']['asset_sha256'] = '9'*64
    elif fault == 'foreign-body': action['review']['body_ref']['asset_sha256'] = '9'*64
    elif fault == 'stale-points': action['review']['points_sha256'] = '9'*64
    elif fault == 'zero': action['amount'] = 0
    elif fault == 'extra-target': action['target_face_refs'] = [h.refs['second']]
    elif fault == 'false-visible': action['review']['visible'] = False
    elif fault == 'false-reference': action['review']['reference_unchanged'] = False
    else: action['target_face_ref'] = action['review']['body_ref']
    with pytest.raises(ValueError): H.preview(h.engine, h.owner.snapshot(), h.target, action)
    assert h.engine.writes == [] and h.engine._people_support == {}


def test_metadata_ack_without_both_actual_image_reads_cannot_confirm(host):
    h = host; review = preview(h); action = {'token': review['token'], 'ack': H._ack(review)}
    with pytest.raises(ValueError, match='Load both'): H.confirm(h.engine, h.owner.snapshot(), h.target, action)
    H.image(h.engine, h.owner.snapshot(), h.target, {'token': review['token'], 'side': 'before',
        'sha256': review['visual']['before']['sha256'], 'review_sha256': review['review_sha256']})
    with pytest.raises(ValueError, match='Load both'): H.confirm(h.engine, h.owner.snapshot(), h.target, action)
    action = loaded(h, review); wrong = deepcopy(action); wrong['ack']['after_sha256'] = '9'*64
    with pytest.raises(ValueError): H.confirm(h.engine, h.owner.snapshot(), h.target, wrong)
    candidate, proof = H.confirm(h.engine, h.owner.snapshot(), h.target, action)
    assert proof['body_ref'] == review['body_ref'] and candidate['revision'] == review['candidate_state_revision']
    assert h.engine.writes == []


@pytest.mark.parametrize('fault', ['repair', 'source', 'revision', 'fence', 'load', 'path', 'context',
    'body-link', 'body-record', 'body-revision', 'body-disabled', 'analysis', 'reference-analysis',
    'support', 'alias', 'reference-disabled', 'review-mutation'])
def test_exact_review_rejects_source_ownership_body_support_or_analysis_changes(host, fault):
    h = host; review = preview(h); action = loaded(h, review)
    if fault == 'repair': h.engine.current['repair'] = 'repair-1'
    elif fault == 'source': h.engine.current['source'] = '9'*64
    elif fault == 'revision': h.version.revision += 1
    elif fault == 'fence': h.owner.fence += 1
    elif fault == 'load': h.engine._load_id = 'load-two'
    elif fault == 'path': h.engine.row['path'] = '/synthetic/replaced.png'
    elif fault == 'context': h.engine.context = 'context-1'
    elif fault == 'body-link': B.target(h.engine.body_bank, review['body_ref'])['association'] = None
    elif fault == 'body-record': B.target(h.engine.body_bank, review['body_ref'])['record']['model_sha256'] = '9'*64
    elif fault == 'body-revision': h.engine.body_bank['revision'] += 1
    elif fault == 'body-disabled': B.target(h.engine.body_bank, review['body_ref'])['enabled'] = False
    elif fault == 'analysis': h.engine._people_analyses[ASSET]['first']['body_skin'][0, 0] = .2
    elif fault == 'reference-analysis': h.engine._people_analyses[ASSET]['reference']['face_skin'][0, 0] = .2
    elif fault == 'support': h.engine._people_support['9'*64] = {}
    elif fault == 'alias': h.engine._docs.append({**h.engine.row, 'document_id': 'alias-document'})
    elif fault == 'reference-disabled': h.owner.state['faces']['reference']['enabled'] = False
    else: h.engine._skin_reference_body_reviews['pending'][review['token']]['review']['body_review']['visible'] = False
    with pytest.raises(ValueError): H.confirm(h.engine, h.owner.snapshot(), h.target, action)
    assert h.engine.writes == []


def test_face_review_token_cannot_authorize_body_image_or_confirmation(host):
    h = host; review = preview(h); action = loaded(h, review)
    entry = h.engine._skin_reference_body_reviews['pending'].pop(review['token'])
    h.engine._skin_reference_match_reviews = {'pending': {review['token']: entry}}
    with pytest.raises(ValueError, match='expired'): H.confirm(h.engine, h.owner.snapshot(), h.target, action)
    assert h.engine.writes == []


def test_clear_removes_only_body_lane_even_when_live_body_evidence_is_stale(host):
    h = host; attach_face(h); commit(h, preview(h))
    before = h.owner.snapshot(); assets = deepcopy(h.engine._people_support)
    B.target(h.engine.body_bank, h.bodies['first']['body_ref'])['association'] = None
    candidate, proof = H.clear(h.engine, before, h.target, {})
    assert PROJECT.active_refs(candidate, ASSET) == []
    assert FACE_PROJECT.active_refs(candidate, ASSET) == [h.refs['second']]
    assert FACE_PROJECT.recipe(candidate, 'second') == FACE_PROJECT.recipe(before, 'second')
    assert candidate['faces']['second']['local_assets'] == before['faces']['second']['local_assets']
    assert proof['cleared_face_refs'] == [h.refs['first']]
    assert h.engine._people_support == assets
    H.publish(h.engine, before, h.target, {}, candidate, proof, 'clear-request')
    assert h.owner.snapshot() == candidate and h.engine._people_support == assets


def test_generic_activation_amount_and_association_change_need_body_review(host):
    h = host; commit(h, preview(h)); before = h.owner.snapshot()
    changed = P.set_override(before, 'face', 'first', S.OP, '/amount', .9)
    with pytest.raises(ValueError, match='review'): PROJECT.require_unreviewed_transition(before, changed)
    with pytest.raises(ValueError): PROJECT.require_transition(h.engine, before, changed)
    changed = deepcopy(before); changed['association_revision'] += 1
    with pytest.raises(ValueError, match='review'): PROJECT.require_unreviewed_transition(before, changed)
    neutral = P.set_override(before, 'face', 'first', S.OP, '/amount', 0.)
    assert PROJECT.require_unreviewed_transition(before, neutral) == neutral


def test_common_reference_guard_also_rejects_face_lane_donor_replacement(host):
    h = host; commit(h, preview(h)); before = h.owner.snapshot()
    analyses = h.engine._people_analyses[ASSET]
    candidate, assets = FACE_SUPPORT.retain(before, h.engine._people_support,
        h.refs['second'], h.refs['other-reference'], analyses['second'], analyses['other-reference'], confirmed=True)
    candidate = P.set_override(candidate, 'face', 'second', FACE_STATE.OP, '/amount', .5)
    with pytest.raises(ValueError, match='one explicitly selected'):
        PROJECT.common_reference(candidate, assets, ASSET, h.engine.body_bank)


def test_history_keeps_nearest_support_and_exact_historical_body_bank(host):
    h = host; candidate, _ = commit(h, preview(h)); assets = deepcopy(h.engine._people_support)
    history = GRAPH.document_slice(candidate, ASSET)
    historical = {'people_support_assets': assets, 'people_graph': candidate,
        'document_history': {'undo': [{'_people_history': history, BODY_PROJECT.KEY: BODY_STORE.pack(h.engine.body_bank)}]}}
    assert PROJECT.validate(historical) == assets
    old = deepcopy(historical)
    for key in ('undo',):
        record = old['document_history'][key][0]
        packed = record[BODY_PROJECT.KEY]
        packed['state']['association_revision'] += 1
        packed['content_sha256'] = E.content_digest(packed['state'])
    assert PROJECT.validate(old) == assets
    assert PROJECT._history_body_closure(candidate, assets, packed['state'],
        history['association_revision']) == [h.refs['first']]
    missing = deepcopy(historical); missing['document_history']['undo'][0].pop(BODY_PROJECT.KEY)
    with pytest.raises(ValueError, match='snapshot'): PROJECT.validate(missing)
    shadowed = {'people_support_assets': assets, 'docs': [{'people_context': {'people_support_assets': {}},
                'state': {'_people_history': history, BODY_PROJECT.KEY: BODY_STORE.pack(h.engine.body_bank)}}]}
    with pytest.raises(ValueError): PROJECT.validate(shadowed)
    with pytest.raises(ValueError): PROJECT.validate(historical, allowed=False)


def test_history_dormant_pointer_does_not_grant_current_reference_permission(host):
    h = host; candidate, _ = commit(h, preview(h)); assets = deepcopy(h.engine._people_support)
    candidate = P.set_override(candidate, 'face', 'first', S.OP, '/amount', 0.)
    candidate['faces']['reference']['enabled'] = False
    assert PROJECT.validate({'people_graph': candidate, 'people_support_assets': assets}) == assets


def test_scalar_history_rejects_shared_scope_reference_fields_and_unknown_amounts(host):
    h = host; state = h.owner.snapshot()
    for path, value in (('/reference_face_ref', h.refs['reference']), ('/amount', True), ('/amount', float('nan'))):
        with pytest.raises(ValueError): PROJECT.validate_leaf(path, value)
    candidate = P.set_override(state, 'all_people', ASSET, S.OP, '/amount', .5)
    with pytest.raises(ValueError, match='owner faces'): PROJECT.validate_graph(candidate)
    assert PROJECT.validate({'people_graph': state}) == {}


def test_preview_publication_is_single_claim_and_still_uses_canonical_owner(host):
    h = host; review = preview(h); candidate, proof = commit(h, review)
    assert h.owner.snapshot() == candidate and h.owner.fence == 8 and h.version.revision == 6
    assert PROJECT._ADMISSION not in h.engine.__dict__
    with pytest.raises(ValueError): H.confirm(h.engine, candidate, h.target, {'token': review['token'], 'ack': H._ack(review)})
    assert len(h.engine.writes) == 1 and proof['kind'] == 'skin_reference_body_confirm'
    assert proof['review'] == review


@pytest.mark.parametrize('fault', ['disabled', 'stale-pose', 'unlinked', 'unavailable'])
def test_stale_body_intent_report_and_neutral_clear_remain_reachable(host, fault):
    h = host; commit(h, preview(h)); before = h.owner.snapshot()
    if fault == 'disabled': B.target(h.engine.body_bank, h.bodies['first']['body_ref'])['enabled'] = False
    elif fault == 'stale-pose': B.target(h.engine.body_bank, h.bodies['first']['body_ref'])['record']['model_sha256'] = '9'*64
    elif fault == 'unlinked': B.target(h.engine.body_bank, h.bodies['first']['body_ref'])['association'] = None
    else:
        def unavailable():
            raise ValueError('Synthetic unavailable body evidence')
        h.engine._body_bank = unavailable
    retained = H.report(h.engine, before)
    assert retained['target_face_refs'] == [h.refs['first']]
    candidate, proof = H.clear(h.engine, before, h.target, {})
    assert PROJECT.active_refs(candidate, ASSET) == []
    assert proof['cleared_face_refs'] == [h.refs['first']]


def test_neutral_clear_publication_does_not_load_unavailable_body_evidence(host):
    h = host; commit(h, preview(h)); before = h.owner.snapshot()
    def unavailable():
        raise ValueError('Synthetic unavailable body evidence')
    h.engine._body_bank = unavailable
    candidate, proof = H.clear(h.engine, before, h.target, {})
    H.publish(h.engine, before, h.target, {}, candidate, proof, 'unavailable-clear')
    assert h.owner.snapshot() == candidate


@pytest.mark.parametrize('fault', ['disabled', 'reanalysed', 'unlinked', 'removed'])
def test_stale_body_snapshot_saves_as_unapplied_intent_without_rebinding(host, fault):
    h = host; candidate, _ = commit(h, preview(h)); assets = deepcopy(h.engine._people_support)
    body_ref = h.bodies['first']['body_ref']; body_bank = deepcopy(h.engine.body_bank)
    if fault == 'disabled': B.target(body_bank, body_ref)['enabled'] = False
    elif fault == 'reanalysed':
        B.target(body_bank, body_ref)['record']['body_ref']['analysis_revision'] += 1
        body_bank['bodies'][body_ref['body_instance_id']]['association'] = None
    elif fault == 'unlinked': B.target(body_bank, body_ref)['association'] = None
    else: del body_bank['bodies'][body_ref['body_instance_id']]
    history = GRAPH.document_slice(candidate, ASSET)
    saved = {'people_support_assets': assets, 'people_graph': candidate,
        'document_history': {'undo': [{'_people_history': history,
            BODY_PROJECT.KEY: BODY_STORE.pack(body_bank)}]}}
    before = deepcopy(saved)
    assert PROJECT.validate(saved) == assets and saved == before
    assert PROJECT._history_body_closure(candidate, assets, body_bank,
        history['association_revision']) == [h.refs['first']]
    with pytest.raises(ValueError):
        PROJECT.common_reference(candidate, assets, ASSET, body_bank)
    stored = next(record for record in assets.values() if record['row']['target'] == SUPPORT.KIND)
    assert stored['row']['review']['body_ref'] == body_ref


def test_disabling_an_unrelated_face_does_not_erase_its_protection_or_require_body_reconsent(host):
    h = host; commit(h, preview(h)); before = h.owner.snapshot()
    candidate = deepcopy(before); candidate['faces']['other-reference']['enabled'] = False
    assert candidate['faces']['other-reference']['box'] == before['faces']['other-reference']['box']
    assert PROJECT.require_unreviewed_transition(before, candidate) == candidate
    assert PROJECT.require_transition(h.engine, before, candidate) == candidate
