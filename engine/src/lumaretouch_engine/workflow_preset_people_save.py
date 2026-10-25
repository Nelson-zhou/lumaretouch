# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure, target-scoped staging through the existing portrait project serializer.

This is not a graph, transaction, history or file owner. The caller retains its
lease/source CAS, original imported row, frozen review and explicit save action.
The retained handoff supplies its explicit preparation/cancellation ownership.
"""
from copy import deepcopy
from dataclasses import dataclass
from types import SimpleNamespace

from . import people_state as S, virtual_copy_people as V
from .workflow_owner_protocol import digest


PEOPLE_PROJECT_FIELDS = frozenset(('people_graph', 'people_support_assets',
    'people_landmarks', 'people_cursors', 'hair_colour_assets',
    'hair_unification_assets', 'hair_colour_evidence'))
IMMUTABLE_BANKS = ('people_support_assets', 'hair_colour_assets',
                   'hair_unification_assets', 'hair_colour_evidence')


def _source(row):
    fp = row.get('fingerprint') or {}
    managed = row.get('managed_import') or {}
    asset = S.digest(fp.get('sha256'))
    if (fp.get('hash_level') != 'full' or managed.get('mode') != 'copy'
            or managed.get('content_sha256') != asset or row.get('copy_number', 0) != 0):
        raise ValueError('Portrait workflow save requires the original complete managed source')
    return asset, deepcopy({key: row.get(key) for key in ('document_id', 'path',
        'source_asset_id', 'root_document_id', 'copy_number', 'fingerprint',
        'managed_import', 'import_origin')})


def _context_snapshot(engine, context):
    if type(context) is not dict or 'owner' not in context:
        raise ValueError('Portrait save requires an already established canonical context')
    active = context is engine.__dict__.get('_people_active_context')
    owner = engine.__dict__.get('_people_graph_owner') if active else context['owner']
    if owner is not context['owner']:
        raise ValueError('Active portrait owner differs from its established context')
    values = {key: engine.__dict__.get(field, {}) if active else context.get(key, {})
              for key, field in V.FIELDS.items()}
    return V.check({'version': 1, 'people_graph': owner.snapshot(), **values})


def context(engine, row):
    """Read the exact active target context without activate/remember/migration."""
    if (engine.__dict__.get('_people_scope_row') is not row
            or engine.__dict__.get('_doc_index', -1) < 0
            or engine._docs[engine._doc_index] is not row):
        raise ValueError('Portrait save target must be the already active document')
    return _context_snapshot(engine, engine.__dict__.get('_people_active_context'))


@dataclass(frozen=True)
class Baseline:
    row: object
    owner: object
    context_owner: object
    source: dict
    asset: str
    saved_sha256: str
    before: dict
    private: bool


def capture(engine, row, saved):
    """Capture before explicit target preparation; no source bytes are read here."""
    if engine.__dict__.get('_creative_base') is not None:
        raise ValueError('Portrait workflow save cannot prepare a derived source')
    asset, source = _source(row)
    before = context(engine, row)
    graph = before['people_graph']
    if (any(face['asset_sha256'] == asset for face in graph['faces'].values())
            or asset in graph['analysis_runs']
            or any(item['scope'] == 'all_people' and item['target_id'] == asset
                   for item in graph['overrides'])):
        raise ValueError('Portrait save preparation is bounded to a fresh unanalyzed target')
    selected = [doc for doc in saved['docs'] if doc.get('document_id') == row['document_id']]
    if len(selected) != 1 or selected[0].get('source_asset_id') != row['source_asset_id']:
        raise ValueError('Saved portrait target/source is unavailable or ambiguous')
    return Baseline(row, engine._people_graph_owner, engine._people_active_context,
                    source, asset, digest(saved), before, V.is_private(row))


def _outside(graph, asset):
    """Remove only the one source's local slice, preserving all associations."""
    value = S.check(graph)
    faces = {key for key, face in value['faces'].items() if face['asset_sha256'] == asset}
    value['faces'] = {key: face for key, face in value['faces'].items() if key not in faces}
    value['overrides'] = [item for item in value['overrides'] if not (
        item['scope'] == 'face' and item['target_id'] in faces or
        item['scope'] == 'all_people' and item['target_id'] == asset)]
    value['unresolved_legacy'] = [item for item in value['unresolved_legacy']
                                  if item['asset_sha256'] != asset]
    value['analysis_runs'].pop(asset, None)
    value.pop('revision'); value.pop('association_revision')
    return value


def _graph_delta(before, after, asset):
    before, after = S.check(before), S.check(after)
    if (_outside(before, asset) != _outside(after, asset)
            or before['association_revision'] != after['association_revision']):
        raise ValueError('Portrait save changed another source or shared association')
    if after['revision'] < before['revision']:
        raise ValueError('Portrait save cannot rewind its canonical graph revision')


def _map_delta(before, after, asset, *, landmarks=False):
    if type(before) is not dict or type(after) is not dict:
        raise ValueError('Portrait save bank must be an exact mapping')
    for key, value in before.items():
        if landmarks or key != asset:
            if key not in after or after[key] != value:
                raise ValueError('Portrait save replaced immutable or unrelated target evidence')
    for key, value in after.items():
        if key in before: continue
        if landmarks:
            if (type(value) is not dict or
                    (value.get('face_ref') or {}).get('asset_sha256') != asset):
                raise ValueError('New landmark evidence belongs to another source')
        elif key != asset:
            raise ValueError('Portrait save added another source cursor/target')


def _context_delta(before, after, asset):
    before, after = V.check(before), V.check(after)
    _graph_delta(before['people_graph'], after['people_graph'], asset)
    faces = [face for face in after['people_graph']['faces'].values()
             if face['asset_sha256'] == asset]
    if (len(faces) != 1 or not faces[0]['enabled'] or faces[0]['manual']
            or faces[0]['evidence']['status'] != 'verified'
            or faces[0]['evidence']['backend'] != 'mediapipe'
            or any(item['scope'] == 'all_people' and item['target_id'] == asset
                   or item['scope'] == 'face' and item['target_id'] == faces[0]['face_instance_id']
                   for item in after['people_graph']['overrides'])):
        raise ValueError('Fresh skin save requires one verified neutral target-owned face')
    _map_delta(before['people_landmarks'], after['people_landmarks'], asset, landmarks=True)
    for key in ('people_cursors', 'people_targets'):
        _map_delta(before[key], after[key], asset)
    # Fresh skin analysis creates measured landmarks, not authored support/hair.
    if any(before[key] != after[key] for key in IMMUTABLE_BANKS):
        raise ValueError('Fresh portrait preparation cannot create or replace authored support')


class _FrozenGraphView:
    """Serializer-only snapshot adapter; deliberately has no commit method."""
    def __init__(self, graph): self._graph = S.check(graph)
    def snapshot(self): return deepcopy(self._graph)


def _frozen_context(snapshot):
    value = V.check(snapshot)
    return {'owner': _FrozenGraphView(value['people_graph']), 'analyses': {},
            **{key: value[key] for key in V.FIELDS}}


def _detached_host(engine):
    contexts = {}
    def detached(value):
        if id(value) not in contexts:
            contexts[id(value)] = _frozen_context(_context_snapshot(engine, value))
        return contexts[id(value)]
    root = engine.__dict__.get('_people_project_context')
    active = engine.__dict__.get('_people_active_context')
    host = SimpleNamespace(_docs=[], _people_project_context=detached(root),
                           _people_active_context=detached(active))
    for original in engine._docs:
        if original.get('_people_new_import'):
            raise ValueError('Scoped portrait save cannot classify another unprepared import')
        row = dict(original)  # No recipe/model-array copy; serializer never reads them.
        if V.RUNTIME in row: row[V.RUNTIME] = detached(row[V.RUNTIME])
        if V.KEY in row: row[V.KEY] = deepcopy(row[V.KEY])
        if V.is_private(row) and V.RUNTIME not in row:
            row[V.RUNTIME] = _frozen_context(row.get(V.KEY))
        host._docs.append(row)
        if original is engine._people_scope_row: host._people_scope_row = row
    host._people_graph_owner = host._people_active_context['owner']
    host._people_analyses = {}
    for key, field in V.FIELDS.items(): setattr(host, field, host._people_active_context[key])
    return host


def stage(engine, saved, recipe_project, row, baseline, expected_context):
    """Return a detached project; caller still checks codec/CAS and writes it.

    `expected_context` is frozen by the handoff after preparation and rechecked
    against the reviewed/applied candidate, not read afresh as save authority.
    """
    if (type(baseline) is not Baseline or baseline.row is not row
            or baseline.owner is not engine.__dict__.get('_people_graph_owner')
            or baseline.context_owner is not engine.__dict__.get('_people_active_context')
            or baseline.private != V.is_private(row) or baseline.saved_sha256 != digest(saved)
            or _source(row) != (baseline.asset, baseline.source)
            or engine.__dict__.get('_creative_base') is not None):
        raise ValueError('Portrait save lost its original preparation/source/project owner')
    current = context(engine, row)
    expected = V.check(expected_context)
    if current != expected:
        raise ValueError('Portrait save context differs from the frozen reviewed result')
    _context_delta(baseline.before, current, baseline.asset)
    result = deepcopy(recipe_project)
    V.save_project(_detached_host(engine), result)
    target = row['document_id']
    selected = [doc for doc in result['docs'] if doc.get('document_id') == target]
    prior = [doc for doc in recipe_project['docs'] if doc.get('document_id') == target]
    if len(selected) != 1 or len(prior) != 1:
        raise ValueError('Scoped portrait serializer lost its exact target')
    expected_doc = deepcopy(prior[0])
    if baseline.private: expected_doc[V.KEY] = expected
    if selected[0] != expected_doc:
        raise ValueError('Portrait serializer changed target fields outside its context')
    old_others = [doc for doc in saved['docs'] if doc.get('document_id') != target]
    new_others = [doc for doc in result['docs'] if doc.get('document_id') != target]
    if old_others != new_others or saved.get('source_assets') != result.get('source_assets'):
        raise ValueError('Portrait save changed another document or source registration')
    if {key: value for key, value in recipe_project.items() if key not in PEOPLE_PROJECT_FIELDS | {'docs'}} != {
            key: value for key, value in result.items() if key not in PEOPLE_PROJECT_FIELDS | {'docs'}}:
        raise ValueError('Portrait serializer changed unrelated project data')
    for key in IMMUTABLE_BANKS:
        if saved.get(key, {}) != result.get(key, {}):
            raise ValueError('Scoped portrait save changed global immutable support banks')
    if baseline.private:
        for key in PEOPLE_PROJECT_FIELDS:
            if saved.get(key) != result.get(key):
                raise ValueError('Private target save changed shared portrait state')
    else:
        _graph_delta(saved.get('people_graph', S.empty()), result['people_graph'], baseline.asset)
        _map_delta(saved.get('people_landmarks', {}), result['people_landmarks'], baseline.asset, landmarks=True)
        _map_delta(saved.get('people_cursors', {}), result['people_cursors'], baseline.asset)
    if context(engine, row) != expected:
        raise ValueError('Portrait target changed during pure save staging')
    return result
