# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit group-only save staging over the existing project codec/CAS owner.

Caller owns the serialized mutation gate, successful batch receipt and exact
post-apply version/source/history checks. No analysis, activation, export or
whole-project save happens here. Runtime/durability acceptance remains UNRUN.
"""
from copy import deepcopy
import json
import os
from types import SimpleNamespace

from . import project as PJ, creative_document_storage as CS
from . import people_state as S, virtual_copy_people as V
from . import creative_derived_source as SOURCE
from .workflow_preset_handoff import _scoped_project
from .workflow_preset_people_save import (
    _detached_host, _context_delta, _graph_delta, _map_delta, IMMUTABLE_BANKS, PEOPLE_PROJECT_FIELDS,
)
from .workflow_preset_save import persist
from .source_relocation_transaction import read_project


def _outside(graph, assets):
    value = S.check(graph)
    faces = {key for key, face in value['faces'].items()
             if face['asset_sha256'] in assets}
    value['faces'] = {key: face for key, face in value['faces'].items() if key not in faces}
    value['overrides'] = [item for item in value['overrides'] if not (
        item['scope'] == 'face' and item['target_id'] in faces or
        item['scope'] == 'all_people' and item['target_id'] in assets)]
    value['unresolved_legacy'] = [item for item in value['unresolved_legacy']
                                  if item['asset_sha256'] not in assets]
    value['analysis_runs'] = {key: item for key, item in value['analysis_runs'].items()
                              if key not in assets}
    value.pop('revision')
    return value  # association_revision deliberately remains exact.


def _bank_delta(before, after, assets, *, landmarks=False):
    if type(before) is not dict or type(after) is not dict:
        raise ValueError('Group portrait bank must be a mapping')
    for key, value in before.items():
        if landmarks or key not in assets:
            if key not in after or after[key] != value:
                raise ValueError('Group save replaced unrelated or immutable portrait evidence')
    for key, value in after.items():
        if key in before:
            continue
        asset = (value.get('face_ref') or {}).get('asset_sha256') if landmarks and type(value) is dict else key
        if asset not in assets:
            raise ValueError('Group save added unrelated portrait evidence')


def _retained_context_delta(before, after, asset):
    """Only this photograph's graph may change; no cross-photo association."""
    before, after = V.check(before), V.check(after)
    _graph_delta(before['people_graph'], after['people_graph'], asset)
    _map_delta(before['people_landmarks'], after['people_landmarks'], asset, landmarks=True)
    for key in ('people_cursors', 'people_targets'):
        _map_delta(before[key], after[key], asset)
    if any(before[key] != after[key] for key in IMMUTABLE_BANKS):
        raise ValueError('Retained group save cannot replace authored support banks')


def _save_history(engine, saved, result, rows, batch_id):
    """Use the existing history codec on only the accepted batch and documents."""
    from .people_history_persistence import save as encode_history
    batch = engine.__dict__.get('_batch_sync')
    entry = None if batch is None else batch.ledger.get(batch_id)
    docs = {row['document_id'] for row in rows}
    if (entry is None or entry.get('undone') or entry.get('ops') != ['lnx.people_graph.v1']
            or entry.get('people_changes') != [] or not entry.get('people_scoped_changes')
            or len(entry.get('targets', {})) != len(docs)
            or {target['document_id'] for target in entry['targets'].values()} != docs):
        raise ValueError('Group save must retain exactly its canonical applied people batch')
    from .people_batch_ledger import verify_reviewed_refs, reviewed_refs
    for target in entry['targets'].values():
        row = next(row for row in rows if row['document_id'] == target['document_id'])
        if not reviewed_refs(target):
            raise ValueError('Group history cannot omit reviewed face references')
        SOURCE.verify_row_target(row, target)
        verify_reviewed_refs(engine, row, target)
    # No activation, history clearing or live owner writes. Existing unrelated
    # encoded histories are retained by the canonical document serializer.
    host = SimpleNamespace(_docs=[dict(row) for row in rows], _project=deepcopy(saved),
                           _batch_sync=SimpleNamespace(ledger={batch_id: deepcopy(entry)}))
    encode_history(host, result)
    encoded = result['people_batch_history']
    prior = deepcopy(saved.get('people_batch_history', {}))
    if batch_id in prior and prior[batch_id] != encoded[batch_id]:
        raise ValueError('Saved group batch identity already names different history')
    prior[batch_id] = encoded[batch_id]
    result['people_batch_history'] = prior


def stage(engine, saved, rows, *, batch_id=None):
    """Pure staging; unrelated recipe/history rows remain their saved bytes."""
    if not 1 <= len(rows) <= 8 or len({row['document_id'] for row in rows}) != len(rows):
        raise ValueError('Group save needs 1–8 distinct exact documents')
    stored = {row['document_id']: row for row in saved['docs']}
    assets, shared = set(), set()
    result = deepcopy(saved)
    for row in rows:
        target = row['document_id']
        if row.get('copy_number', 0) != 0 or target not in stored or row.get('trashed'):
            raise ValueError('Group save requires already saved original targets')
        prior = stored[target]
        # Project row/source identity is not a capability to rewrite provenance.
        for key in ('path', 'document_id', 'source_asset_id', 'root_document_id',
                    'copy_number', 'fingerprint', 'managed_import', 'import_origin'):
            if prior.get(key) != row.get(key):
                raise ValueError('Group save source/provenance differs from its saved original')
        asset = SOURCE.row_proof(row)['asset_sha256']
        if asset in assets:
            raise ValueError('Group save cannot alias a source across targets')
        assets.add(asset)
        if not V.is_private(row):
            shared.add(asset)
        else:
            if V.KEY not in prior:
                raise ValueError('Group private portrait context has no saved baseline')
            (_retained_context_delta if batch_id is not None else _context_delta)(
                prior[V.KEY], V.encode(row), asset)
        result = _scoped_project(result, row)

    # Reuse the canonical serializer with detached contexts. It cannot remember
    # into the real engine or activate another photograph. Restore unrelated
    # private rows immediately: their unsaved recipes/contexts are not this save.
    recipe_rows = deepcopy(result['docs'])
    V.save_project(_detached_host(engine), result)
    selected = {row['document_id'] for row in rows}
    expected_rows = {row['document_id']: row for row in recipe_rows}
    result['docs'] = [row if row['document_id'] in selected else expected_rows[row['document_id']]
                      for row in result['docs']]
    if result['docs'] != recipe_rows:
        raise ValueError('Portrait serializer changed a staged group document')
    before_graph, after_graph = S.check(saved.get('people_graph', S.empty())), S.check(result['people_graph'])
    if (_outside(before_graph, shared) != _outside(after_graph, shared)
            or after_graph['revision'] < before_graph['revision']):
        raise ValueError('Unrelated shared portrait edits must be saved separately')
    _bank_delta(saved.get('people_landmarks', {}), result['people_landmarks'], shared, landmarks=True)
    _bank_delta(saved.get('people_cursors', {}), result['people_cursors'], shared)
    for key in IMMUTABLE_BANKS:
        if saved.get(key, {}) != result.get(key, {}):
            raise ValueError('Group save cannot publish unrelated authored support banks')
    allowed = PEOPLE_PROJECT_FIELDS | {'docs', 'assets'}
    if batch_id is not None:
        _save_history(engine, saved, result, rows, batch_id)
        allowed |= {'people_document_history', 'people_batch_history'}
    if {key: value for key, value in saved.items() if key not in allowed} != {
            key: value for key, value in result.items() if key not in allowed}:
        raise ValueError('Group save changed unrelated project data')
    PJ.validate(result)
    if PJ._migrate(result) != result:
        raise ValueError('Group save requires a canonical existing project')
    return result


def save(engine, rows, recheck, *, batch_id=None):
    """Return succeeded/unknown; a pre-replacement exception proves no write.

    The caller MUST retain an uncertain result and never automatically retry it.
    A successful scoped save intentionally does not clear the global dirty flag.
    """
    if not callable(recheck) or engine._project is None or not engine._project_path:
        raise ValueError('Group save requires its existing project and exact owner recheck')
    recheck()
    path, expected = os.path.abspath(engine._project_path), engine._project_disk_sha256
    raw, actual = read_project(path)
    if not expected or actual != expected:
        raise ValueError('Saved project changed outside this group handoff')
    saved = json.loads(raw.decode('utf-8'))
    saved = CS.hydrate(saved, CS.read_blobs(saved, path))
    PJ.validate(saved)
    if PJ._migrate(saved) != saved:
        raise ValueError('Group save cannot silently migrate the existing project')
    project = stage(engine, saved, rows, batch_id=batch_id)
    def check():
        if os.path.abspath(engine._project_path) != path or engine._project_disk_sha256 != expected:
            raise ValueError('Group save project ownership changed')
        recheck()
    outcome = persist(project, path, expected, check)
    if outcome['status'] != 'succeeded':
        return outcome
    # Replacement already happened: any publication/readback failure is Unknown,
    # never a normal exception that could invite a new save request.
    try:
        engine._project = CS.hydrate(outcome['project'], CS.read_blobs(outcome['project'], path))
        engine._project_disk_sha256 = outcome['sha256']
        engine._project_saved_ns = outcome['updated_ns']
    except Exception as error:
        return {'status': 'unknown', 'expected_sha256': outcome['sha256'],
                'requires_readback': True, 'error': str(error)}
    return outcome
