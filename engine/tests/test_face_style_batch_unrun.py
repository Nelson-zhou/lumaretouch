# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN named-style batch contracts, not photo acceptance.

Recipes, graph data, endpoint validation and frozen metadata are production
code. Face evidence/digests are synthetic fixtures. Aggregate tests explicitly
mock source access, snapshot capture and image rendering; fake display bytes
are not PNGs. Nothing in this file proves native execution, model availability,
photographic output, rollback or export equivalence. No product import, test
collection, execution, build or typecheck was performed while authoring.
"""
from base64 import b64encode
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
from types import SimpleNamespace
import json
import struct

import pytest
from lumaretouch_engine import face_style_batch_review as R
from lumaretouch_engine import face_style_batch_plan as PLAN
from lumaretouch_engine import face_style_batch_store as STORE
from lumaretouch_engine import face_style_recipes as RECIPES
from lumaretouch_engine import people_batch_transfer as BATCH
from lumaretouch_engine import people_transfer_adapter as TRANSFER
from lumaretouch_engine import people_transfer_inventory as INVENTORY
from lumaretouch_engine import people_state as S, people_algorithms as A
from lumaretouch_engine.batch_preflight import FrozenTarget, canonical

RECIPE = {'version': 1, 'style': 'classic', 'amount': .5}
STYLES = ('classic', 'youthful', 'bold', 'youth', 'round', 'long', 'square')


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def source(asset):
    return {'asset_sha256': asset, 'original_sha256': asset, 'creative_source': None}


def graph(*assets):
    result = S.empty(); refs = []
    for asset in assets:
        face = S.new_face(asset, [.2, .1, .8, .9], {
            'backend': 'fixture_only', 'detector_model_sha256': 'd' * 64,
            'semantic_model_sha256': None, 'landmark_digest': 'e' * 64,
            'status': 'verified', 'source_width': 128, 'source_height': 160,
            'orientation': 'exif_normalized_once'})
        result['faces'][face['face_instance_id']] = face
        refs.append(S.face_ref(face))
    return result, refs


def endpoint(state, asset, document, *, scope=None):
    return {'document': {'document_id': document, 'epoch': 'fixture-workspace', 'revision': 4},
            'people_scope': document if scope is None else scope,
            'state_revision': state['revision'], 'association_revision': state['association_revision'],
            'graph_sha256': INVENTORY.graph_digest(state), 'source_proof': source(asset)}


@pytest.fixture
def endpoints():
    left, a = graph('a' * 64); right, b = graph('b' * 64)
    left = S.set_override(left, 'face', a[0]['face_instance_id'], 'lnx.face_size.v1', '/amount', .91)
    right = S.set_override(right, 'face', b[0]['face_instance_id'], 'lnx.nose_shape.v1', '/wing', -.12)
    x = endpoint(left, a[0]['asset_sha256'], '1' * 32)
    y = endpoint(right, b[0]['asset_sha256'], '2' * 32)
    return SimpleNamespace(left=left, right=right, a=a[0], b=b[0], x=x, y=y)


def prepared(h, recipe=RECIPE):
    return TRANSFER.prepare(h.left, h.right, h.a, [h.b], R.selection(recipe), A.defaults(),
        source_document=h.x['document'], target_document=h.y['document'],
        source_owner=h.x, target_owner=h.y, face_style=recipe)


def verify(h, payload):
    return TRANSFER.verify(payload, h.left, h.right,
        source_document=h.x['document'], target_document=h.y['document'],
        source_owner=h.x, target_owner=h.y)


def request(h, recipe=RECIPE):
    return {'source_ref': deepcopy(h.a), 'target_policy': 'explicit_face_map',
            'source': deepcopy(h.x), 'selection': R.selection(recipe), 'face_style': deepcopy(recipe),
            'targets': [{'target': deepcopy(h.y), 'target_refs': [deepcopy(h.b)]}]}


def visual(document='2' * 32, recipe=RECIPE):
    return {'version': 1, 'document_id': document, 'revision': '4', 'source_proof': source('b' * 64),
            'before_state_sha256': '1' * 64, 'candidate_state_sha256': '1' * 64,
            'before_people_sha256': '2' * 64, 'candidate_people_sha256': '3' * 64,
            'source_size': [128, 160], 'before_output_size': [128, 160], 'after_output_size': [128, 160],
            'before': {'mime': 'image/png', 'width': 128, 'height': 160, 'sha256': '4' * 64},
            'after': {'mime': 'image/png', 'width': 128, 'height': 160, 'sha256': '5' * 64},
            'recipe_sha256': R.recipe_digest(recipe)}


def ack(record):
    return {key: record[key] for key in ('document_id', 'revision', 'recipe_sha256')} | {
        'before_sha256': record['before']['sha256'], 'after_sha256': record['after']['sha256']}


def test_catalogue_has_exact_seven_names_and_thirty_complete_owned_leaves():
    catalogue = RECIPES.catalogue()
    assert tuple(item['id'] for item in catalogue['styles']) == STYLES
    for style in STYLES:
        value = {**RECIPE, 'style': style}
        parameters = R.parameters(value)
        assert len(parameters) == 30 and len(R.selection(value)) == 10
        assert {op: sorted(paths) for op, paths in catalogue['owned_parameters'].items()} == R.selection(value)
        assert parameters == sorted(({k: patch[k] for k in ('operation_id', 'parameter_path', 'value')}
            for patch in RECIPES.patches(style, .5)), key=lambda p: (p['operation_id'], p['parameter_path']))
        assert all(set(item) == {'operation_id', 'parameter_path', 'value'} for item in parameters)


@pytest.mark.parametrize('change', ({'version': True}, {'version': 2}, {'style': 'legacy_classic'},
    {'style': '经典'}, {'amount': True}, {'amount': -.01}, {'amount': 1.01},
    {'amount': float('nan')}, {'amount': float('inf')}, {'amount': '0.5'}, {'extra': 1}))
def test_recipe_rejects_nonexact_version_style_amount_and_fields(change):
    with pytest.raises(ValueError): R.recipe({**RECIPE, **change})


def test_digest_has_explicit_domain_style_separator_and_big_endian_f64():
    expected = sha256(b'lumaretouch.face-style.v1\0classic\0' + struct.pack('>d', .5)).hexdigest()
    assert R.recipe_digest(RECIPE) == expected
    assert R.recipe_digest({**RECIPE, 'amount': 0}) == R.recipe_digest({**RECIPE, 'amount': -0.0})
    assert R.recipe_digest({**RECIPE, 'amount': 1}) == R.recipe_digest({**RECIPE, 'amount': 1.0})
    assert len({R.recipe_digest({**RECIPE, 'style': style}) for style in STYLES}) == 7
    assert R.recipe_digest(RECIPE) != R.recipe_digest({**RECIPE, 'amount': .5000000000000001})


def test_selection_accepts_order_only_and_rejects_partial_mixed_or_duplicate_leaves():
    selected = R.selection(RECIPE)
    assert R.check_selection(RECIPE, {op: list(reversed(paths)) for op, paths in reversed(list(selected.items()))}) is None
    first = next(iter(selected))
    variants = [None, {}, {k: v for k, v in selected.items() if k != first},
                {**selected, 'lnx.collarbone.v1': ['/amount']}]
    duplicate = deepcopy(selected); duplicate[first].append(duplicate[first][0]); variants.append(duplicate)
    missing = deepcopy(selected); missing[first].pop(); variants.append(missing)
    for value in variants:
        with pytest.raises(ValueError): R.check_selection(RECIPE, value)


def test_preparation_does_not_read_donor_values_and_keeps_target_identity(endpoints, monkeypatch):
    h = endpoints; left = deepcopy(h.left); right = deepcopy(h.right)
    def forbidden(*args, **kwargs):
        raise AssertionError('Named recipe must not resolve donor scalar values')
    monkeypatch.setattr(TRANSFER, 'resolve', forbidden)
    payload = prepared(h)
    assert payload['target_policy'] == 'explicit_face_map'
    assert payload['parameters'] == R.parameters(RECIPE)
    result = TRANSFER.candidate(payload, h.left, h.right,
        source_document=h.x['document'], target_document=h.y['document'], source_owner=h.x, target_owner=h.y)
    assert result['faces'] == right['faces'] and result['persons'] == right['persons']
    assert result['links'] == right['links'] and result['groups'] == right['groups']
    assert h.left == left and h.right == right
    actual = {(item['operation_id'], item['parameter_path']): item['value'] for item in result['overrides']}
    assert actual[('lnx.nose_shape.v1', '/wing')] == -.12
    for leaf in payload['parameters']:
        assert actual[(leaf['operation_id'], leaf['parameter_path'])] == leaf['value']


@pytest.mark.parametrize('mutation', ('parameter', 'bool_as_int', 'zero_as_bool', 'policy', 'missing_policy', 'missing_owner', 'recipe'))
def test_frozen_recipe_requires_exact_typed_parameters_and_explicit_owner_proofs(endpoints, mutation):
    h = endpoints; value = prepared(h)
    if mutation == 'parameter': value['parameters'][0]['extra'] = 'not-owned'
    elif mutation == 'bool_as_int': next(p for p in value['parameters'] if type(p['value']) is bool)['value'] = 1
    elif mutation == 'zero_as_bool': next(p for p in value['parameters'] if type(p['value']) is float and p['value'] == 0)['value'] = False
    elif mutation == 'policy': value['target_policy'] = 'confirmed_person_only'
    elif mutation == 'missing_policy': value.pop('target_policy')
    elif mutation == 'missing_owner': value.pop('target_owner')
    elif mutation == 'recipe': value['face_style']['amount'] = .7
    with pytest.raises(ValueError): verify(h, value)


def test_named_recipe_prepare_requires_both_owner_proofs(endpoints):
    h = endpoints
    with pytest.raises(ValueError):
        TRANSFER.prepare(h.left, h.right, h.a, [h.b], R.selection(RECIPE), A.defaults(),
            source_document=h.x['document'], target_document=h.y['document'], face_style=RECIPE)


def test_target_face_analysis_change_is_not_authorized_by_same_recipe(endpoints):
    h = endpoints; value = prepared(h)
    changed = deepcopy(h.right); changed['faces'][h.b['face_instance_id']]['analysis_revision'] += 1
    with pytest.raises(ValueError):
        TRANSFER.verify(value, h.left, changed, source_document=h.x['document'], target_document=h.y['document'],
            source_owner=h.x, target_owner=h.y)


def test_named_style_options_require_exact_map_modules_and_no_mixed_selection(endpoints):
    h = endpoints; value = request(h); modules = list(value['selection'])
    assert BATCH.options(value, modules, h.a['asset_sha256']) == value
    variants = []
    for policy in ('confirmed_person_only', 'persistent_association'):
        variants.append(({**value, 'target_policy': policy}, modules))
    variants.extend([(value, modules[:-1]), (value, modules + [modules[0]])])
    bad = deepcopy(value); bad['selection']['lnx.collarbone.v1'] = ['/amount']
    variants.append((bad, list(bad['selection'])))
    bad = deepcopy(value); bad['targets'].append(deepcopy(bad['targets'][0])); variants.append((bad, modules))
    bad = deepcopy(value); bad['targets'][0]['target_refs'] *= 2; variants.append((bad, modules))
    bad = deepcopy(value); bad['targets'][0]['target']['document']['epoch'] = 'other'; variants.append((bad, modules))
    for item, scope in variants:
        with pytest.raises(ValueError): BATCH.options(item, scope, h.a['asset_sha256'])


@pytest.mark.parametrize('field', ('document_id', 'revision', 'before_sha256', 'after_sha256', 'recipe_sha256'))
def test_ack_binds_every_target_coordinate_image_and_recipe(field):
    record = visual(); correct = ack(record)
    assert R.acknowledgments([correct], [record]) == [correct]
    bad = {**correct, field: 'different'}
    with pytest.raises(ValueError): R.acknowledgments([bad], [record])


def test_ack_requires_exact_order_complete_count_and_distinct_documents():
    records = [visual('2' * 32), visual('3' * 32)]
    values = [ack(record) for record in records]
    for bad in (None, [], values[:1], values[::-1], values + [values[0]]):
        with pytest.raises(ValueError): R.acknowledgments(bad, records)
    with pytest.raises(ValueError): R.acknowledgments([values[0], values[0]], [records[0], records[0]])


def test_visual_rejects_inline_pixels_wrong_size_hash_and_derived_canvas():
    record = visual(); assert R.checked(record) == record
    changes = []
    bad = deepcopy(record); bad['before']['base64'] = 'AA=='; changes.append(bad)
    bad = deepcopy(record); bad['before']['width'] = 64; changes.append(bad)
    bad = deepcopy(record); bad['recipe_sha256'] = 'not-a-hash'; changes.append(bad)
    bad = deepcopy(record); bad['revision'] = str(2**64); changes.append(bad)
    bad = deepcopy(record); bad['source_proof']['creative_source'] = {'sha256': 'b' * 64, 'width': 1, 'height': 1}; changes.append(bad)
    for value in changes:
        with pytest.raises(ValueError): R.checked(value)


@pytest.fixture
def aggregate(monkeypatch):
    """Real aggregation/recipe validation, mocked source/snapshot/render boundary."""
    state, refs = graph('a' * 64, 'b' * 64)
    rows = [{'document_id': str(i + 1) * 32, 'path': f'/fixture/{i}.png', 'asset': ref['asset_sha256'],
             'scope': 'project', 'state': {'fixture_repair': 'old'}, 'src_w': 128, 'src_h': 160}
            for i, ref in enumerate(refs)]
    engine = SimpleNamespace(graphs={'project': state}, context='original', calls=[])
    engine._document_versions = lambda: SimpleNamespace(version=lambda row: SimpleNamespace(document_id=row['document_id'], revision=4))
    monkeypatch.setattr(PLAN.V, 'scope', lambda row: row['scope'])
    monkeypatch.setattr(PLAN.V, 'row_snapshot', lambda e, row: deepcopy(e.graphs[row['scope']]))
    monkeypatch.setattr(PLAN.SOURCE, 'row_proof', lambda row: source(row['asset']))
    def snapshot(e, row, current, candidate):
        normalized = deepcopy(candidate); normalized['revision'] = 0
        return {'render_sha256': digest(current), 'context_sha256': digest(e.context), 'graph_sha256': digest(normalized)}
    monkeypatch.setattr(PLAN, 'snapshot_key', snapshot)
    def identity(e, row, before, candidate, document, revision, recipe):
        result = visual(document, recipe)
        result.update(revision=str(revision), source_proof=source(row['asset']),
            before_state_sha256=digest(row['state']), candidate_state_sha256=digest(row['state']),
            before_people_sha256=digest(before), candidate_people_sha256=digest(candidate))
        return {key: value for key, value in result.items() if key not in ('before', 'after')}
    monkeypatch.setattr(R, '_identity', identity)
    def image(e, row, current, candidate, document, revision):
        e.calls.append((document, deepcopy(candidate)))
        raw = ('FAKE DISPLAY ONLY ' + document + digest(candidate) + digest(current)).encode()
        compact = {'mime': 'image/png', 'width': 128, 'height': 160, 'sha256': sha256(raw).hexdigest()}
        proof = {'source_proof': source(row['asset']), 'source_size': [128, 160], 'output_size': [128, 160],
                 'candidate_sha256': digest(current), 'people_sha256': digest(candidate)}
        return compact, {**compact, 'base64': b64encode(raw).decode()}, proof
    monkeypatch.setattr(R, 'image', image)
    targets = []
    for i, row in enumerate(rows):
        payload = {'target_refs': [refs[i]], 'parameters': R.parameters(RECIPE), 'face_style': deepcopy(RECIPE)}
        targets.append(FrozenTarget(row['document_id'], 4, i, row['path'], None,
            canonical({'source_proof': source(row['asset'])}), people_json=canonical(payload)))
    return SimpleNamespace(engine=engine, rows=rows, state=state, refs=refs, targets=targets,
                           public=[{}, {}], image=image)


def test_aggregate_reviews_final_shared_graph_for_every_document_without_mutating_owner(aggregate):
    h = aggregate; before = deepcopy(h.state)
    frozen, displays = PLAN.visuals(h.engine, h.rows, h.targets, h.public)
    assert h.engine.graphs['project'] == before
    assert set(displays) == {row['document_id'] for row in h.rows}
    assert len(h.engine.calls) == 4
    for _, candidate in h.engine.calls[1::2]:
        for ref in h.refs:
            leaves = [item for item in candidate['overrides'] if item['target_id'] == ref['face_instance_id']]
            assert len(leaves) == 30
    assert h.engine.calls[1][1] == h.engine.calls[3][1]
    assert all('face_style_snapshots' in json.loads(target.before_json) for target in frozen)
    assert all('base64' not in canonical(json.loads(target.people_json)) for target in frozen)


def test_unreviewed_shared_source_alias_refuses_before_any_render(aggregate):
    h = aggregate
    h.rows.append({**h.rows[0], 'document_id': '9' * 32, 'path': '/fixture/unseen.png'})
    with pytest.raises(ValueError, match='unreviewed shared-source'):
        PLAN.visuals(h.engine, h.rows, h.targets, h.public)
    assert h.engine.calls == [] and h.engine.graphs['project'] == h.state


def test_byte_identical_independent_owner_is_not_silently_merged_or_changed(aggregate):
    h = aggregate; private = deepcopy(h.state)
    h.engine.graphs['9' * 32] = private
    h.rows.append({**h.rows[0], 'document_id': '9' * 32, 'scope': '9' * 32})
    PLAN.visuals(h.engine, h.rows, h.targets, h.public)
    assert h.engine.graphs['9' * 32] == private
    assert all(document != '9' * 32 for document, _ in h.engine.calls)


@pytest.mark.parametrize('change', ('context', 'repair', 'owner'))
def test_change_during_later_target_render_invalidates_entire_visual_set(aggregate, monkeypatch, change):
    h = aggregate
    def image(*args):
        result = h.image(*args)
        if len(h.engine.calls) == 4:
            if change == 'context': h.engine.context = 'changed'
            elif change == 'repair': h.rows[0]['state']['fixture_repair'] = 'changed'
            else: h.engine.graphs['project']['revision'] += 1
        return result
    monkeypatch.setattr(R, 'image', image)
    with pytest.raises(ValueError): PLAN.visuals(h.engine, h.rows, h.targets, h.public)


def test_snapshot_check_refuses_commit_candidate_missing_other_selected_face(aggregate):
    h = aggregate; frozen, _ = PLAN.visuals(h.engine, h.rows, h.targets, h.public)
    candidate = deepcopy(h.state)
    for leaf in R.parameters(RECIPE):
        candidate = S.set_override(candidate, 'face', h.refs[0]['face_instance_id'],
                                   leaf['operation_id'], leaf['parameter_path'], leaf['value'])
    scoped = {'before': h.state, 'candidate': candidate}
    with pytest.raises(ValueError, match='snapshot'):
        PLAN.verify(h.engine, h.rows[0], scoped, frozen[0], json.loads(frozen[0].people_json))


def test_store_records_bind_token_family_target_document_and_revision():
    record = visual()
    target = FrozenTarget(record['document_id'], 4, 0, '/fixture/target.png', None, '{}',
                          people_json=canonical({'face_style_visual': record}))
    options = {'_people_transfer': {'options': {'face_style': deepcopy(RECIPE)}}}
    plan = SimpleNamespace(targets=(target,), params=lambda: deepcopy(options))
    assert STORE._records(plan) == {record['document_id']: record}
    for changed in (replace(target, document_id='9' * 32), replace(target, revision=5)):
        plan.targets = (changed,)
        with pytest.raises(ValueError): STORE._records(plan)
    plan.targets = (target, target)
    with pytest.raises(ValueError): STORE._records(plan)
    plan.targets = (target,); options['_people_transfer']['options'].pop('face_style')
    with pytest.raises(ValueError): STORE._records(plan)


def test_plan_target_limit_refuses_instead_of_truncating(aggregate):
    h = aggregate
    with pytest.raises(ValueError, match='sixteen'):
        PLAN.visuals(h.engine, h.rows, h.targets * 9, h.public * 9)
    assert h.engine.calls == []
