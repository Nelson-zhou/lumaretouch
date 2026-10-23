"""Authored source-contract regressions only. UNRUN; no model/quality acceptance.

The fixed detector and image digests below are synthetic schema fixtures, not
claims that real inference, native rendering or photo review has occurred.
"""
from copy import deepcopy
from types import SimpleNamespace
import pytest

from lumaretouch_engine import people_state as S
from lumaretouch_engine import people_transfer_adapter as T
from lumaretouch_engine import people_transfer_inventory as I
from lumaretouch_engine import people_batch_transfer as B
from lumaretouch_engine.people_confirmed_transfer import prepare_confirmed

OP = 'test.portrait'
ASSET = 'a' * 64
FACE = 'same-face-id-in-independent-owners'


def graph(asset=ASSET, revision=0):
    value = S.empty()
    evidence = {'backend': 'authored_fixture', 'detector_model_sha256': 'b' * 64,
        'semantic_model_sha256': None, 'landmark_digest': 'c' * 64, 'status': 'verified',
        'source_width': 640, 'source_height': 480, 'orientation': 'exif_normalized_once'}
    face = S.new_face(asset, [.1, .2, .6, .8], evidence)
    face['face_instance_id'] = FACE; value['faces'][FACE] = face
    value['persons']['identical-local-person'] = {'anonymous': True}
    value['links'] = [{'face_instance_id': FACE, 'person_id': 'identical-local-person',
                      'state': 'confirmed', 'confirmation_revision': 0}]
    value['revision'] = revision
    return S.check(value)


def endpoint(state, identity, *, scope=None, derived=False):
    asset = state['faces'][FACE]['asset_sha256']
    return I.check_proof({'document': {'document_id': identity, 'epoch': 'workspace', 'revision': 2},
        'people_scope': identity if scope is None else scope,
        'state_revision': state['revision'], 'association_revision': state['association_revision'],
        'graph_sha256': I.graph_digest(state), 'source_proof': {'asset_sha256': asset,
            'creative_source': {'sha256': asset, 'width': 640, 'height': 480} if derived else None,
            'original_sha256': 'd' * 64 if derived else asset}})


def prepared(*, same_source=True):
    source = S.set_override(graph(revision=5), 'face', FACE, OP, '/strength', .65)
    target = S.set_override(graph(ASSET if same_source else 'e' * 64, 13), 'face', FACE, OP, '/other', .3)
    if not same_source:
        target['persons'] = {}; target['links'] = []
    source_owner = endpoint(source, 'source-owner')
    target_owner = endpoint(target, 'target-owner', derived=not same_source)
    kwargs = {'source_document': source_owner['document'], 'target_document': target_owner['document'],
              'source_owner': source_owner, 'target_owner': target_owner}
    payload = T.prepare(source, target, S.face_ref(source['faces'][FACE]),
        [S.face_ref(target['faces'][FACE])], {OP: ['/strength']},
        {OP: {'/strength': 0., '/other': 0.}}, **kwargs)
    payload['target_policy'] = 'explicit_face_map'
    return source, target, payload, kwargs


@pytest.mark.parametrize('same_source', [True, False])
def test_explicit_owner_map_copies_only_selected_leaves(same_source):
    source, target, payload, kwargs = prepared(same_source=same_source)
    original_source = deepcopy(source); original_target = deepcopy(target)
    candidate = T.candidate(payload, source, target, **kwargs)
    assert source == original_source and target == original_target
    for name in ('faces', 'persons', 'groups', 'links', 'analysis_runs', 'unresolved_legacy'):
        assert candidate[name] == target[name]
    assert next(row['value'] for row in candidate['overrides'] if row['parameter_path'] == '/strength') == .65
    assert next(row['value'] for row in candidate['overrides'] if row['parameter_path'] == '/other') == .3
    assert payload['excluded'] == ['local_assets', 'landmarks', 'masks', 'identity_links']
    assert payload['source_owner']['people_scope'] != payload['target_owner']['people_scope']


def test_identical_person_and_face_ids_never_authorize_cross_owner_confirmed_transfer():
    source, target, payload, kwargs = prepared()
    with pytest.raises(ValueError, match='Independent portrait owners'):
        prepare_confirmed(source, target, payload['source_ref'], ASSET, {OP: ['/strength']},
                          {OP: {'/strength': 0.}}, **kwargs)


def test_confirmed_transfer_keeps_explicit_same_owner_contract():
    source, _, _, _ = prepared(); target = deepcopy(source)
    source_owner = endpoint(source, 'source-document', scope='project')
    target_owner = endpoint(target, 'target-document', scope='project')
    payload = prepare_confirmed(source, target, S.face_ref(source['faces'][FACE]), ASSET,
        {OP: ['/strength']}, {OP: {'/strength': 0.}}, source_document=source_owner['document'],
        target_document=target_owner['document'], source_owner=source_owner, target_owner=target_owner)
    assert payload['confirmed_person_id'] == 'identical-local-person'
    assert payload['target_policy'] == 'confirmed_person_only'


def test_graph_content_change_is_rejected_even_with_unchanged_counters():
    source, target, payload, kwargs = prepared()
    target['faces'][FACE]['box'] = [.2, .2, .7, .8]
    with pytest.raises(ValueError, match='owner, source or graph changed'):
        T.verify(payload, source, target, **kwargs)


@pytest.mark.parametrize('side', ['source_owner', 'target_owner'])
def test_owner_or_source_substitution_is_rejected(side):
    source, target, payload, kwargs = prepared()
    changed = deepcopy(kwargs); changed[side]['source_proof']['original_sha256'] = 'f' * 64
    changed[side]['source_proof']['creative_source'] = {
        'sha256': ASSET, 'width': 640, 'height': 480}
    with pytest.raises(ValueError, match='owner, source or graph changed'):
        T.verify(payload, source, target, **changed)


def test_explicit_map_cannot_fall_back_to_counter_only_proof():
    source, target, payload, kwargs = prepared()
    payload.pop('source_owner'); payload.pop('target_owner')
    with pytest.raises(ValueError, match='missing owner-qualified'):
        T.verify(payload, source, target, **kwargs)


def test_disabled_or_unverified_target_cannot_enter_explicit_map():
    source, target, payload, kwargs = prepared()
    target['faces'][FACE]['evidence']['status'] = 'unresolved'
    proof = endpoint(target, 'target-owner')
    payload['target_owner'] = proof; kwargs['target_owner'] = proof
    with pytest.raises(ValueError, match='verified source-owned analysis'):
        T.verify(payload, source, target, **kwargs)


def test_explicit_options_require_exact_map_and_reject_cross_source_face(monkeypatch):
    source, target, payload, kwargs = prepared()
    monkeypatch.setattr(B.A, 'defaults', lambda: {OP: {'/strength': 0.}})
    request = {'source_ref': payload['source_ref'], 'selection': {OP: ['/strength']},
        'target_policy': 'explicit_face_map', 'source': kwargs['source_owner'],
        'targets': [{'target': kwargs['target_owner'], 'target_refs': payload['target_refs']}]}
    assert B.options(request, [OP], ASSET) == request
    malformed = deepcopy(request); malformed['targets'][0]['target_refs'][0]['asset_sha256'] = 'f' * 64
    with pytest.raises(ValueError, match='another effective source'):
        B.options(malformed, [OP], ASSET)
    malformed = deepcopy(request); malformed['targets'].append(deepcopy(malformed['targets'][0]))
    with pytest.raises(ValueError, match='duplicated'):
        B.options(malformed, [OP], ASSET)


def test_inventory_returns_exact_owner_boxes_without_mutating_graph_or_selection(monkeypatch):
    source = graph(); target = graph('e' * 64)
    rows = [{'document_id': 'source', 'copy_number': 1, 'path': 'source.jpg', 'state': {}},
            {'document_id': 'target', 'copy_number': 1, 'path': 'target.jpg', 'state': {}}]
    states = {'source': source, 'target': target}
    versions = SimpleNamespace(workspace='workspace', version=lambda row: SimpleNamespace(document_id=row['document_id'], revision=2))
    engine = SimpleNamespace(_docs=rows, _doc_index=0, _creative_base=None, _document_versions=lambda: versions)
    monkeypatch.setattr(I.V, 'peek_graph', lambda engine, row: deepcopy(states[row['document_id']]))
    monkeypatch.setattr(I.SOURCE, 'row_proof', lambda row: endpoint(states[row['document_id']], row['document_id'])['source_proof'])
    monkeypatch.setattr(I, '_preview', lambda row, proof, faces: {'mime': 'image/png', 'base64': 'authored-fixture-only',
        'width': 320, 'height': 240, 'source_sha256': proof['source_proof']['asset_sha256']})
    before = deepcopy((rows, states)); replies = []
    controller = SimpleNamespace(emit_result=lambda request, body: replies.append(body))
    I.inventory(engine, controller, {'cmd': 'batch', 'action': 'people_targets', 'request_id': 'inventory', 'docs': ['target']})
    assert (rows, states) == before and engine._doc_index == 0
    assert replies[0]['source']['people_scope'] == 'source'
    assert replies[0]['targets'][0]['people_scope'] == 'target'
    assert replies[0]['targets'][0]['faces'][0]['box'] == target['faces'][FACE]['box']
    assert replies[0]['targets'][0]['source_preview']['source_sha256'] == 'e' * 64


def test_inventory_has_exact_read_only_schema_and_no_partial_face_census():
    with pytest.raises(ValueError, match='exact read-only'):
        I.inventory(None, None, {'cmd': 'batch', 'action': 'people_targets', 'request_id': 'query',
                                'docs': ['target'], 'people_transfer': {}})
    assert I.MAX_FACES == 128 and I.MAX_TARGETS == 16


def test_derived_inventory_preview_uses_canonical_pixels_not_original_path(monkeypatch):
    import struct
    import numpy as np
    from lumaretouch_engine import creative_document_base as BASE, decode
    from lumaretouch_engine.creative_document_assets import make_asset
    base = make_asset('rgba', 2, 1, struct.pack('<ffff', .25, .125, .0625, 1.) * 2)
    state = graph(base['id'][7:]); face = state['faces'][FACE]
    face['evidence'].update(source_width=2, source_height=1)
    expected = endpoint(state, 'derived', derived=True)
    expected['source_proof']['creative_source'].update(width=2, height=1)
    row = {'path': 'must-not-be-decoded.jpg', 'state': {'_creative_base': base}}
    calls = []
    def proxy(original, owned, **options):
        assert original is None and owned['_creative_base'] is base
        assert options['max_pixels'] == 320 * 320
        calls.append(base['id'])
        return np.zeros((1, 2, 3), dtype=np.uint8)
    monkeypatch.setattr(BASE, 'proxy_for_state', proxy)
    monkeypatch.setattr(decode, 'load_rgb', lambda *_args, **_kwargs: pytest.fail('Decoded original for derived inventory'))
    result = I._preview(row, expected, [face])
    assert calls == [base['id']]
    assert result['source_sha256'] == base['id'][7:] and (result['width'], result['height']) == (2, 1)


@pytest.mark.parametrize('rgba', [(.25, .125, .0625, .5), (1.25, .125, .0625, 1.)])
def test_inventory_refuses_alpha_or_hdr_before_display_conversion(monkeypatch, rgba):
    import struct
    from lumaretouch_engine import creative_document_base as BASE
    from lumaretouch_engine.creative_document_assets import make_asset
    base = make_asset('rgba', 1, 1, struct.pack('<ffff', *rgba))
    monkeypatch.setattr(BASE, 'proxy_for_state', lambda *_args, **_kwargs: pytest.fail('Clipped or matted before admission'))
    with pytest.raises(ValueError, match='SDR'):
        I._preview({'state': {'_creative_base': base}}, {'source_proof': {'asset_sha256': base['id'][7:]}}, [])
