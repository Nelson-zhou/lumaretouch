"""People payload adapter for existing frozen batch preflight, not a batch engine.

No mutation/commit/undo implementation here. FrozenBatchController must freeze this
payload and document fences, recheck them, then use existing atomic receipts and
protected batch undo. people_batch_transfer wires this payload into that same controller.
"""
from copy import deepcopy
from . import people_state as S
from .people_resolver import resolve


def prepare(source_state, target_state, source_ref, target_refs, selection, defaults,
            *, source_document, target_document, source_owner=None, target_owner=None):
    """selection maps operation IDs to explicit parameter pointers, never assets."""
    source = S.check(source_state); target = S.check(target_state)
    source_ref = S.check_ref(source_ref)
    face = source['faces'].get(source_ref['face_instance_id'])
    if face is None or S.face_ref(face) != source_ref: raise ValueError('Source face has changed')
    if type(selection) is not dict or not selection: raise ValueError('Select modules and parameter leaves')
    for operation, paths in selection.items():
        S.token(operation)
        if type(paths) is not list or not paths or len(set(paths)) != len(paths): raise ValueError('Select unique parameter leaves')
        for path in paths: S.parameter_path(path)
    # DocumentVersions supplies these identities/revisions; no path-as-ID inference.
    for document in (source_document, target_document):
        if type(document) is not dict or set(document) != {'document_id', 'epoch', 'revision'}: raise ValueError('Document mutation fence required')
        S.token(document['document_id']); S.token(document['epoch']); S.revision(document['revision'])
    resolved = resolve(source, source_ref['face_instance_id'], defaults)
    parameters = []
    for operation, paths in sorted(selection.items()):
        for path in sorted(paths):
            if any(x['operation_id'] == operation and x['parameter_path'] == path for x in resolved['conflicts']):
                raise ValueError('Source has ambiguous group precedence')
            record = resolved['operations'].get(operation, {}).get(path)
            if record is None: raise ValueError('Selected parameter is not available on source')
            parameters.append({'operation_id': operation, 'parameter_path': path, 'value': deepcopy(record['value'])})
    if type(target_refs) is not list or not target_refs: raise ValueError('An explicit target face map is required')
    exact = []; seen = set()
    for ref in target_refs:
        ref = S.check_ref(ref); face = target['faces'].get(ref['face_instance_id'])
        if face is None or S.face_ref(face) != ref or not face['enabled']: raise ValueError('Target face is missing, disabled or changed')
        if ref['face_instance_id'] in seen: raise ValueError('Duplicate target face would repeat strength')
        seen.add(ref['face_instance_id']); exact.append(ref)
    payload = {'version': 1, 'source_document': deepcopy(source_document), 'target_document': deepcopy(target_document),
            'source_ref': source_ref, 'target_refs': exact, 'parameters': parameters,
            'source_state_revision': source['revision'], 'target_state_revision': target['revision'],
            'source_association_revision': source['association_revision'],
            'target_association_revision': target['association_revision'],
            'transfer_policy': 'selected_parameter_keys_replace', 'excluded': ['local_assets', 'landmarks', 'masks', 'identity_links']}
    if source_owner is not None or target_owner is not None:
        from .people_transfer_inventory import check_proof
        payload['source_owner'] = check_proof(source_owner)
        payload['target_owner'] = check_proof(target_owner)
        verify(payload, source, target, source_document=source_document, target_document=target_document,
               source_owner=source_owner, target_owner=target_owner)
    return payload


def verify(payload, source_state, target_state, *, source_document, target_document,
           source_owner=None, target_owner=None):
    """Call immediately before existing batch commit, not only when previewing."""
    source = S.check(source_state); target = S.check(target_state)
    if payload['source_document'] != source_document or payload['target_document'] != target_document:
        raise ValueError('Document changed after people preflight')
    for label, state in (('source', source), ('target', target)):
        if payload[label + '_state_revision'] != state['revision'] or payload[label + '_association_revision'] != state['association_revision']:
            raise ValueError('People state or association changed after preflight')
    if 'source_owner' in payload or 'target_owner' in payload:
        from .people_transfer_inventory import check_proof, graph_digest
        for label, state, document, current in (
                ('source', source, source_document, source_owner),
                ('target', target, target_document, target_owner)):
            expected = check_proof(payload.get(label + '_owner')); current = check_proof(current)
            if (expected != current or current['document'] != document
                    or current['state_revision'] != state['revision']
                    or current['association_revision'] != state['association_revision']
                    or current['graph_sha256'] != graph_digest(state)):
                raise ValueError('Reviewed portrait owner, source or graph changed')
            refs = [payload['source_ref']] if label == 'source' else payload['target_refs']
            if any(ref['asset_sha256'] != current['source_proof']['asset_sha256'] for ref in refs):
                raise ValueError('Reviewed face belongs to another effective source')
        if (source_document['epoch'] != target_document['epoch']
                or source_document['document_id'] == target_document['document_id']):
            raise ValueError('Transfer requires distinct documents in the same workspace')
    elif payload.get('target_policy') == 'explicit_face_map':
        raise ValueError('Explicit face transfer is missing owner-qualified review proof')
    refs = [(source, payload['source_ref'])] + [(target, x) for x in payload['target_refs']]
    for state, ref in refs:
        face = state['faces'].get(ref['face_instance_id'])
        if face is None or S.face_ref(face) != ref or not face['enabled']: raise ValueError('Reviewed face is no longer available')
        if payload.get('target_policy') == 'explicit_face_map' and face['evidence']['status'] != 'verified':
            raise ValueError('Explicit transfer requires each selected face to have verified source-owned analysis')


def candidate(payload, source_state, target_state, *, source_document, target_document,
              source_owner=None, target_owner=None):
    """Return staged data only; existing atomic transaction owns publication."""
    verify(payload, source_state, target_state, source_document=source_document, target_document=target_document,
           source_owner=source_owner, target_owner=target_owner)
    out = S.check(target_state)
    for ref in payload['target_refs']:
        for parameter in payload['parameters']:
            out = S.set_override(out, 'face', ref['face_instance_id'], parameter['operation_id'], parameter['parameter_path'], parameter['value'])
    return out
