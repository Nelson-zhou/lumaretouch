# SPDX-License-Identifier: GPL-3.0-or-later
"""Exact eye-bag review closure in the existing protected graph ledger. UNRUN.

Scalar transfer never copies local assets. This marker refuses replay against
new aliases, changed target observations/support/recovery or repair inputs.
Legacy entries retain their existing behavior. No second history owner exists.
"""
from copy import deepcopy
from . import people_state as S, virtual_copy_people as V, creative_derived_source as SOURCE
from .collarbone_transfer_review import coverage_digest

KEY = 'eye_bag_batch_review'


def _dependencies(engine, row):
    from .full_candidate_render import people_context
    from .people_retained_analysis import key as analysis_key
    from .project import encode
    context = people_context(engine, row)
    asset = SOURCE.row_proof(row)['asset_sha256']
    faces = {key: face for key, face in context['people_graph']['faces'].items() if face['asset_sha256'] == asset}
    keys = {descriptor['content_sha256'] for face in faces.values() for descriptor in face['local_assets'].values()}
    # Only the target's retained observations and referenced immutable records
    # matter. Cursor movement and unrelated append-only/project-union records
    # are not edits and must not break protected history after save/reopen.
    own = {'faces': faces,
        'people_landmarks': {analysis_key(S.face_ref(face)): context['people_landmarks'].get(analysis_key(S.face_ref(face))) for face in faces.values()},
        'support_assets': {key: context['people_support_assets'].get(key) for key in sorted(keys)}}
    def stable(value):
        assets = {}; dropped = []
        encoded = encode(value, assets, dropped, 'eye_bag_history')
        if dropped: raise ValueError('Eye-bag protected history cannot omit unsavable target dependencies')
        # The canonical project codec normalizes list/tuple representation and
        # pins arrays/blobs by digest. It is the same contract used on reopen.
        return coverage_digest({'value': encoded, 'assets': {key: {name: item[name] for name in ('kind', 'shape', 'dtype', 'bytes')}
            for key, item in assets.items()}})
    # These are runtime caches, UI cursors, or legacy portrait editing mirrors.
    # people_export.isolated_snapshot suppresses those mirrors in the real
    # renderer; the retained source-owned graph above is their sole authority.
    ignored = {'_precompute', '_proxy', '_face_index', '_face_explicit', '_face_box', '_face_manual',
        '_deform', '_deform_defer', '_deform_default', '_deform_overrides', '_enhance', '_enhance_defer',
        '_lip_makeup', '_brow_shape', '_brow_shape_owner', '_nose_shape', '_nose_shape_owner',
        '_eye_shape', '_eye_shape_owner', '_mouth_shape', '_mouth_shape_owner', '_op_seq'}
    return {'context_sha256': stable(own),
            'state_sha256': stable({key: value for key, value in row['state'].items() if key not in ignored})}


def check(entry):
    if KEY not in entry: return None
    marker = entry[KEY]
    if (type(marker) is not dict or set(marker) != {'version', 'review_sha256', 'targets'}
            or type(marker['version']) is not int or marker['version'] != 1
            or type(marker['targets']) is not list or not 1 <= len(marker['targets']) <= 16
            or entry.get('ops') != ['lnx.people_graph.v1'] or entry.get('people_changes') != []
            or entry.get('policy') != 'protected_scoped_graph'):
        raise ValueError('Malformed eye-bag protected batch history marker')
    S.digest(marker['review_sha256'])
    targets = entry.get('targets'); scopes = entry.get('people_scoped_changes')
    if type(targets) is not dict or len(targets) != len(marker['targets']) or type(scopes) is not list or not scopes:
        raise ValueError('Eye-bag history requires every exact affected target and graph owner')
    by_document = {}; faces_by_scope = {}
    for item in marker['targets']:
        if (type(item) is not dict or set(item) != {'document_id', 'people_scope', 'source_proof', 'faces', 'context_sha256', 'state_sha256'}
                or type(item['faces']) is not list or not 1 <= len(item['faces']) <= 128):
            raise ValueError('Eye-bag history requires exact target dependencies')
        document = S.token(item['document_id']); scope = S.token(item['people_scope'])
        if document in by_document or scope not in ('project', document): raise ValueError('Eye-bag history repeats or changes its owner')
        proof = SOURCE.check_row_proof(item['source_proof'])
        S.digest(item['context_sha256']); S.digest(item['state_sha256'])
        refs = []; graph = S.empty()
        for face in item['faces']:
            if type(face) is not dict: raise ValueError('Invalid frozen eye-bag face')
            ref = S.check_ref(S.face_ref(face))
            if ref['asset_sha256'] != proof['asset_sha256'] or ref['face_instance_id'] in graph['faces']:
                raise ValueError('Eye-bag history repeats or borrows a target face')
            graph['faces'][ref['face_instance_id']] = face; refs.append(ref)
        S.check(graph)
        matches = [target for target in targets.values() if target.get('document_id') == document]
        if (len(matches) != 1 or matches[0].get('people_scope') != scope or matches[0].get('source_proof') != proof
                or matches[0].get('asset_sha256') != proof['asset_sha256'] or matches[0].get('reviewed_face_refs') != refs):
            raise ValueError('Eye-bag history changed exact target source, faces or membership')
        by_document[document] = item
        known = faces_by_scope.setdefault(scope, {})
        for face in item['faces']:
            key = face['face_instance_id']
            if key in known and known[key] != face: raise ValueError('Shared eye-bag aliases disagree on frozen target support')
            known[key] = face
    seen = set()
    for scoped in scopes:
        if (type(scoped) is not dict or set(scoped) != {'scope', 'document_id', 'changes'}
                or scoped['scope'] in seen or scoped['scope'] not in faces_by_scope
                or scoped['document_id'] not in by_document or by_document[scoped['document_id']]['people_scope'] != scoped['scope']
                or type(scoped['changes']) is not list or not scoped['changes']):
            raise ValueError('Eye-bag history changed its exact graph scopes')
        seen.add(scoped['scope']); changes = set()
        for change in scoped['changes']:
            if (type(change) is not dict or set(change) != {'collection', 'key', 'before', 'after'}
                    or change['collection'] != 'overrides' or type(change['key']) is not list or len(change['key']) != 4
                    or change['key'][0] != 'face' or change['key'][1] not in faces_by_scope[scoped['scope']]):
                raise ValueError('Eye-bag scalar history cannot change observations, assets or associations')
            key = tuple(change['key'])
            if key in changes: raise ValueError('Eye-bag history repeats a scalar patch')
            changes.add(key); S.token(key[2]); S.parameter_path(key[3])
            if change['after'] is None: raise ValueError('Eye-bag batch requires reviewed scalar replacement leaves')
            for record in (change['before'], change['after']):
                if record is None: continue
                if (type(record) is not dict or set(record) != {'scope', 'target_id', 'operation_id', 'parameter_path', 'value'}
                        or tuple(record[name] for name in ('scope', 'target_id', 'operation_id', 'parameter_path')) != key):
                    raise ValueError('Eye-bag history scalar identity changed')
                S.scalar(record['value'])
    if seen != set(faces_by_scope): raise ValueError('Eye-bag history omitted an owner')
    return deepcopy(marker)


def prepare(engine, plans, targets, ack):
    from .people_graph_patch import between
    marker = {'version': 1, 'review_sha256': coverage_digest(ack), 'targets': []}
    for target in targets.values():
        found = engine._document_versions().find(engine._docs, target['document_id'])
        if found is None: raise ValueError('Eye-bag history target disappeared')
        row = found[1]; plan = plans[target['people_scope']]
        faces = [deepcopy(plan['before']['faces'][ref['face_instance_id']]) for ref in target['reviewed_face_refs']]
        if any(plan['candidate']['faces'].get(face['face_instance_id']) != face for face in faces):
            raise ValueError('Eye-bag scalar transfer cannot change target support or observations')
        marker['targets'].append({'document_id': target['document_id'], 'people_scope': target['people_scope'],
            'source_proof': deepcopy(target['source_proof']), 'faces': faces, **_dependencies(engine, row)})
    entry = {'ops': ['lnx.people_graph.v1'], 'people_changes': [], 'policy': 'protected_scoped_graph',
             'targets': targets, 'people_scoped_changes': [
                 {'scope': identity, 'document_id': plan['row']['document_id'], 'changes': changes}
                 for identity, plan in plans.items() if (changes := between(plan['before'], plan['candidate']))], KEY: marker}
    return check(entry)


def verify_restore(engine, entry, plans, targets):
    marker = check(entry)
    if marker is None: return
    expected = {item['document_id']: item for item in marker['targets']}
    if {target['document_id'] for target in targets.values()} != set(expected):
        raise ValueError('Eye-bag history cannot add or omit shared-source aliases')
    for target in targets.values():
        item = expected[target['document_id']]
        if (target['people_scope'] != item['people_scope'] or target['source_proof'] != item['source_proof']
                or target.get('reviewed_face_refs') != [S.face_ref(face) for face in item['faces']]):
            raise ValueError('Eye-bag history changed target source, owner or reviewed faces')
        found = engine._document_versions().find(engine._docs, target['document_id'])
        if found is None: raise ValueError('Eye-bag history target disappeared')
        graph = plans[item['people_scope']]['before']
        if (any(graph['faces'].get(face['face_instance_id']) != face for face in item['faces'])
                or _dependencies(engine, found[1]) != {key: item[key] for key in ('context_sha256', 'state_sha256')}):
            raise ValueError('Eye-bag history target observations, support, recovery or repair inputs changed; protected replay refused')
    from .eye_bag_batch_plan import closure
    closure(engine, engine._docs, plans, set(expected))


def status_summary(entry):
    """Bounded history classification, never support data or write authority."""
    marker = check(entry)
    return None if marker is None else {'version': 1, 'review_sha256': marker['review_sha256'],
                                        'member_count': len(marker['targets'])}
