# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN. Exact mixed alias wire, paging and render ownership.

These fixtures do not establish numerical, photographic or integration quality.
No imports, collection, execution, product rendering or inference was run.
"""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import pytest

from lumaretouch_engine import eye_bag_preset_review as R
from lumaretouch_engine import eye_bag_preset_alias_review as A
from lumaretouch_engine import eye_bag_preset_store as STORE
from test_eye_bag_preset_protocol_unrun import wrapper as single


def wrapper():
    value = single(); value['version'] = 2
    sibling = deepcopy(value['visual']); sibling['document_id'] = 'sibling'; sibling['revision'] = '11'
    sibling['before_output_size'] = sibling['after_output_size'] = [40, 60]
    sibling['before']['width'] = sibling['after']['width'] = 40
    value['members'] = [{'path': 'same.png', 'role': 'active', 'visual': deepcopy(value['visual'])},
                        {'path': 'same.png', 'role': 'sibling', 'visual': sibling}]
    value['review_sha256'] = R.digest(value)
    return value


def resign(value):
    value['review_sha256'] = R.digest({key: item for key, item in value.items() if key != 'review_sha256'})
    return value


def ack(value):
    return {**{key: value[key] for key in ('review_sha256', 'preset_sha256', 'applies_sha256', 'replace_legacy')},
        'members': [{'document_id': v['document_id'], 'revision': v['revision'],
                     'before_sha256': v['before']['sha256'], 'after_sha256': v['after']['sha256'],
                     'coverage_sha256': v['coverage_sha256']} for v in (m['visual'] for m in value['members'])]}


def test_exact_shared_wire_accepts_distinct_own_crop_and_same_path():
    value = wrapper()
    assert R.checked(value) == value
    assert R.acknowledgment(ack(value), value) == ack(value)
    assert value['members'][0]['path'] == value['members'][1]['path']
    assert value['members'][0]['visual']['after_output_size'] != value['members'][1]['visual']['after_output_size']


@pytest.mark.parametrize('mutation', ['missing', 'duplicate', 'role', 'graph', 'source', 'coverage',
                                    'sibling-recipe', 'sibling-crop', 'active-pair', 'revision', 'unknown'])
def test_rehashed_wrapper_cannot_bless_incomplete_or_foreign_member(mutation):
    value = wrapper(); sibling = value['members'][1]; visual = sibling['visual']
    if mutation == 'missing': value['members'].pop()
    if mutation == 'duplicate': visual['document_id'] = 'doc'
    if mutation == 'role': sibling['role'] = 'active'
    if mutation == 'graph': visual['candidate_people_sha256'] = 'f'*64
    if mutation == 'source': visual['source_proof']['asset_sha256'] = 'f'*64
    if mutation == 'coverage': visual['coverage_sha256'] = 'f'*64
    if mutation == 'sibling-recipe': visual['candidate_state_sha256'] = 'f'*64
    if mutation == 'sibling-crop':
        visual['after_output_size'] = [50, 60]; visual['after']['width'] = 50
    if mutation == 'active-pair': value['members'][0]['visual']['after']['sha256'] = 'f'*64
    if mutation == 'revision': visual['revision'] = '9007199254740991'
    if mutation == 'unknown': sibling['mask'] = {'donor': True}
    with pytest.raises(ValueError): R.checked(resign(value))


@pytest.mark.parametrize('mutation', ['omitted', 'reorder', 'revision', 'image', 'coverage', 'legacy', 'preset', 'cross-family'])
def test_ack_requires_exact_ordered_pairs_and_full_preset_identity(mutation):
    value = wrapper(); response = ack(value)
    if mutation == 'omitted': response['members'].pop()
    if mutation == 'reorder': response['members'].reverse()
    if mutation == 'revision': response['members'][1]['revision'] = '12'
    if mutation == 'image': response['members'][1]['after_sha256'] = 'f'*64
    if mutation == 'coverage': response['members'][1]['coverage_sha256'] = 'f'*64
    if mutation == 'legacy': response['replace_legacy'] = True
    if mutation == 'preset': response['preset_sha256'] = 'f'*64
    if mutation == 'cross-family': response['support_overlay_sha256'] = 'f'*64
    with pytest.raises(ValueError): R.acknowledgment(response, value)


def test_paged_request_requires_both_member_fields_and_no_support_payload():
    value = {'cmd': 'preset', 'action': 'eye_bag_visual', 'request_id': 'request', 'id': 'preset',
             'document_id': 'load', 'revision': '2', 'side': 'before', 'sha256': '1'*64,
             'preflight_token': 'token', 'member_document_id': 'sibling', 'member_revision': '11'}
    assert STORE.image_read_only(value)
    assert not STORE.image_read_only({k: v for k, v in value.items() if k != 'member_revision'})
    assert not STORE.image_read_only({**value, 'side': 'support'})
    assert not STORE.image_read_only({**value, 'donor_mask': {}})


def test_all_actual_served_sides_required_even_with_exact_ack(monkeypatch):
    value = wrapper(); entry = {'served': set()}
    monkeypatch.setattr(R, '_entry', lambda *a, **k: entry)
    R.acknowledgment(ack(value), value)
    with pytest.raises(ValueError, match='Load every'): A.verify_served(value)
    for member in value['members']:
        A.served(value, member['visual']['document_id'], 'before')
        with pytest.raises(ValueError): A.verify_served(value)
        A.served(value, member['visual']['document_id'], 'after')
    A.verify_served(value)
    with pytest.raises(ValueError): A.served(value, 'unreviewed', 'before')


def test_v2_cannot_enter_single_document_replay_or_rollback():
    for rollback in (False, True):
        with pytest.raises(ValueError, match='composite batch ledger'):
            R.replay(None, None, None, 'load', '2', wrapper(), rollback=rollback)
    with pytest.raises(ValueError, match='composite batch ledger'):
        R.verify_applied(None, None, None, 'load', '2', wrapper())


def test_graph_noop_targets_still_include_every_alias(monkeypatch):
    value = wrapper(); rows = [{'path': m['path'], 'document_id': m['visual']['document_id'],
        'state': {'own': index}} for index, m in enumerate(value['members'])]
    versions = SimpleNamespace(check_advance=lambda row: SimpleNamespace(document_id=row['document_id'], revision=2))
    entry = {'row': rows[0], 'plan': SimpleNamespace(target_ref=value['face_ref']),
             'batch': SimpleNamespace(documents=SimpleNamespace(rows=lambda: rows), versions=versions)}
    monkeypatch.setattr(A.V, 'scope', lambda row: 'project')
    monkeypatch.setattr(A.SOURCE, 'row_proof', lambda row: value['visual']['source_proof'])
    result = A._targets(None, entry, {'current': 'not-parked'})
    assert {target['document_id'] for target in result.values()} == {'doc', 'sibling'}
    assert all(target['reviewed_face_refs'] == [value['face_ref']] for target in result.values())


def test_static_publication_and_image_ownership_are_distinct_from_graph_only_alias():
    root = Path(__file__).parents[1]/'src'/'lumaretouch_engine'
    review = (root/'eye_bag_preset_alias_review.py').read_text()
    controller = (root/'preset_controller.py').read_text()
    store = (root/'eye_bag_preset_store.py').read_text()
    planner = (root/'people_scope.py').read_text()
    assert 'after = plan.state if other is row else state' in review
    assert 'from .eye_bag_preset_alias_transaction import commit' in review
    assert 'verify_images()' in review and 'current_after=entry[\'plan\'].state' in review
    assert 'affected_assets(plan.before, plan.candidate) - {plan.target_ref[\'asset_sha256\']}' in review
    publication=(root/'preset_alias_publication.py').read_text()
    assert controller.index("return publish(self,p,portrait") < controller.index("self.ports.advance()")
    assert 'portrait.store.verify_claimed(controller.reviews' in publication and 'release_claimed(self.reviews' in controller
    assert "if name=='face_decoration':options['ack']" in publication
    assert 'cache.prune(set(reviews.pending) | set(claimed))' in store
    assert 'reviewed_eye_bag_aliases=False' in planner


def test_claimed_images_keep_same_immutable_cache_until_release(monkeypatch):
    value = wrapper(); token = 'frozen'; calls = []
    record = {'eye_bag': value, 'expires': 99999999999}
    reviews = SimpleNamespace(pending={token: record}, targets={}, _eye_bag_images=SimpleNamespace(
        prune=lambda keys: calls.append(set(keys)), read=lambda *a: {'verified': True}))
    monkeypatch.setattr(A, 'verify_served', lambda value: None)
    STORE.retain_claimed(reviews, token, record)
    reviews.pending.clear(); STORE.prune(reviews)
    assert calls[-1] == {token}
    STORE.verify_claimed(reviews, token, value)
    with pytest.raises(ValueError): STORE.retain_claimed(reviews, token, record)
    STORE.release_claimed(reviews, token)
    assert calls[-1] == set()
    with pytest.raises(ValueError): STORE.verify_claimed(reviews, token, value)


def test_prepare_renders_current_planned_recipe_and_each_siblings_own_state(monkeypatch):
    from collections import OrderedDict
    from lumaretouch_engine import people_scope, people_transfer_inventory, people_graph_owner
    value = wrapper(); source = value['visual']['source_proof']; face = value['face_ref']
    before = {'crop': 'active-before', 'repairs': ['current-repair']}
    candidate = {R.SCOPE.TARGET: face, R.SCOPE.FIELD: {'version': 2, 'amount': 1., 'preserve': 1.}}
    after = {'crop': 'active-after', 'repairs': ['current-repair'], 'exposure': .3}
    sibling = {'crop': 'sibling-crop', 'repairs': ['different-repair'], 'exposure': -.2}
    graph_a = {'phase': 'before'}; graph_b = {'phase': 'after'}
    owner = SimpleNamespace(fence=7, snapshot=lambda: deepcopy(graph_a))
    plan = SimpleNamespace(managed=True, owner=owner, owner_fence=7, before=graph_a,
                           candidate=graph_b, state=after, target_ref=face)
    rows = [{'path': 'active.png', 'document_id': 'doc'}, {'path': 'sibling.png', 'document_id': 'sibling'}]
    members = [(rows[0], before, source, SimpleNamespace(document_id='doc', revision=2)),
               (rows[1], sibling, source, SimpleNamespace(document_id='sibling', revision=11))]
    batch = object(); engine = SimpleNamespace(_batch_controller=lambda: batch,
        _document_versions=lambda: SimpleNamespace(workspace='workspace'))
    monkeypatch.setattr(R, '_target', lambda *a, **k: (owner, 'doc'))
    monkeypatch.setattr(people_scope, 'plan_preset', lambda *a, **k: plan)
    monkeypatch.setattr(people_graph_owner, 'affected_assets', lambda *a: {face['asset_sha256']})
    monkeypatch.setattr(A.PLAN, 'admit', lambda *a, **k: rows[0])
    monkeypatch.setattr(A.PLAN, 'coverage', lambda *a: value['coverage'])
    monkeypatch.setattr(A.CLOSURE, '_eligible', lambda *a: members)
    monkeypatch.setattr(A, '_dormant_key', lambda *a: 'frozen-closure')
    monkeypatch.setattr(A, '_targets', lambda *a: {'0': {'document_id': 'doc'}, '1': {'document_id': 'sibling'}})
    monkeypatch.setattr(A, '_verify', lambda *a: None)
    monkeypatch.setattr(people_transfer_inventory, 'proof', lambda *a, **k: value['owner'])
    monkeypatch.setattr(R, '_snapshot_key', lambda engine, row, state, graph: R.digest([state, graph]))
    monkeypatch.setattr(R, '_ENTRIES', OrderedDict())
    rendered = []
    def render(engine, row, state, graph, document, revision):
        rendered.append((row, deepcopy(state), deepcopy(graph)))
        size = [80, 60] if row is rows[0] else [40, 60]
        image = {'mime': 'image/png', 'width': size[0], 'height': size[1], 'sha256': str(len(rendered))*64}
        return image, {**image, 'base64': 'authored-stub'}, {'source_proof': source, 'source_size': [80, 60],
            'output_size': size, 'candidate_sha256': R.digest(state), 'people_sha256': R.digest(graph)}
    monkeypatch.setattr(R, '_image', render)
    result, duplicate = A.prepare(engine, rows[0], before, candidate, 'load', '2',
        {'id': 'mixed'}, {R.SCOPE.OP: {'recipe': candidate[R.SCOPE.FIELD]}}, False)
    assert rendered == [(rows[0], before, graph_a), (rows[0], after, graph_b),
                        (rows[1], sibling, graph_a), (rows[1], sibling, graph_b)]
    assert result == duplicate and result['members'][1]['role'] == 'sibling'
    entry = R._ENTRIES[R.digest(result)]
    assert set(entry['images']) == {'doc', 'sibling'}
    assert entry['plan'] is plan and entry['claimed'] is False
