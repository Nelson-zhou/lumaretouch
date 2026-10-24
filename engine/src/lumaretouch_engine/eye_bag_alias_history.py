# SPDX-License-Identifier: GPL-3.0-or-later
"""Narrow direct ridge-edit protection in the existing shared graph ledger.

This is not the scalar-transfer marker: only the selected face's ridge pointer
may change, with its two eye scalars and explicitly approved legacy zero. Both
support contexts and every complete member input survive save/reopen. UNRUN.
"""
from copy import deepcopy
from . import people_state as P, eye_bag_preserve_state as S, people_algorithms as A
from . import creative_derived_source as SOURCE
from .collarbone_transfer_review import coverage_digest

KEY = 'eye_bag_alias_review'
MAX_MEMBERS = 16


def graph_digest(graph):
    value = P.check(graph)
    value['revision'] = 0; value['association_revision'] = 0
    from .people_graph_patch import LIST_KEYS
    for collection, keys in LIST_KEYS.items():
        value[collection] = sorted(value[collection], key=lambda row: tuple(row[key] for key in keys))
    return coverage_digest(value)


def _dependencies(engine, row, graph):
    from .full_candidate_render import people_context
    from .people_retained_analysis import key as analysis_key
    from .eye_bag_batch_history import _dependencies as input_dependencies
    from .project import encode
    context = people_context(engine, row); asset = SOURCE.row_proof(row)['asset_sha256']
    faces = {key: face for key, face in graph['faces'].items() if face['asset_sha256'] == asset}
    keys = {descriptor['content_sha256'] for face in faces.values() for descriptor in face['local_assets'].values()}
    own = {'faces': faces,
        'people_landmarks': {analysis_key(P.face_ref(face)): context['people_landmarks'].get(analysis_key(P.face_ref(face))) for face in faces.values()},
        'support_assets': {key: context['people_support_assets'].get(key) for key in sorted(keys)}}
    assets = {}; dropped = []
    encoded = encode(own, assets, dropped, 'eye_bag_alias_history')
    if dropped: raise ValueError('Eye-bag alias history cannot omit unsavable source-owned dependencies')
    context_sha256 = coverage_digest({'value': encoded, 'assets': {
        key: {name: item[name] for name in ('kind', 'shape', 'dtype', 'bytes')} for key, item in assets.items()}})
    # Canonical project codec, not runtime object identity or serialization.
    # The old and new graph select DIFFERENT immutable ridge references; never
    # use a live-old-graph context digest to authorize an after-state restore.
    return {'context_sha256': context_sha256, 'state_sha256': input_dependencies(engine, row)['state_sha256']}


def _targets(targets, marker):
    if type(targets) is not dict or len(targets) != len(marker['document_ids']):
        raise ValueError('Eye-bag alias history requires every exact reviewed document')
    seen = set()
    for target in targets.values():
        if type(target) is not dict: raise ValueError('Invalid eye-bag alias history target')
        identity = P.token(target.get('document_id'))
        if identity in seen: raise ValueError('Eye-bag alias history repeats a document')
        seen.add(identity)
        proof = SOURCE.check_row_proof(target.get('source_proof'))
        if (target.get('people_scope') != marker['people_scope']
                or target.get('asset_sha256') != marker['asset_sha256']
                or proof['asset_sha256'] != marker['asset_sha256']
                or target.get('reviewed_face_refs') != [marker['face_ref']]):
            raise ValueError('Eye-bag alias history changed its shared owner, source or selected face')
    if seen != set(marker['document_ids']):
        raise ValueError('Eye-bag alias history cannot add or omit affected documents')


def check(entry):
    if KEY not in entry: return None
    marker = entry[KEY]
    fields = {'version', 'review_sha256', 'people_scope', 'document_ids', 'asset_sha256', 'face_ref',
              'recipe', 'replace_legacy', 'support_sha256', 'before_face', 'after_face',
              'before_graph_sha256', 'after_graph_sha256', 'dependencies'}
    if (type(marker) is not dict or set(marker) != fields or type(marker['version']) is not int or marker['version'] != 1
            or any(key in entry for key in ('face_style_alias_review', 'eye_bag_batch_review', 'eye_bag_cohort_review'))
            or entry.get('ops') != ['lnx.people_graph.v1'] or entry.get('people_changes') != []
            or entry.get('policy') != 'protected_scoped_graph'):
        raise ValueError('Malformed direct eye-bag alias history marker')
    for key in ('review_sha256', 'asset_sha256', 'support_sha256', 'before_graph_sha256', 'after_graph_sha256'):
        P.digest(marker[key])
    if marker['before_graph_sha256'] == marker['after_graph_sha256']:
        raise ValueError('Eye-bag alias history cannot manufacture a graph no-op')
    ref = P.check_ref(marker['face_ref']); recipe = S.check(marker['recipe'])
    if (marker['people_scope'] != 'project' or ref['asset_sha256'] != marker['asset_sha256']
            or type(marker['replace_legacy']) is not bool or not S.active(recipe)):
        raise ValueError('Direct eye-bag aliases require an active reviewed recipe on their original shared owner')
    ids = marker['document_ids']
    if type(ids) is not list or not 2 <= len(ids) <= MAX_MEMBERS:
        raise ValueError('Eye-bag alias history needs two to sixteen exact members')
    for identity in ids: P.token(identity)
    if ids != sorted(set(ids)): raise ValueError('Eye-bag alias member identities are not canonical')
    for side in ('before', 'after'):
        face = marker[side + '_face']; graph = P.empty()
        if type(face) is not dict or P.face_ref(face) != ref:
            raise ValueError('Eye-bag alias history changed the selected observation identity')
        graph['faces'][ref['face_instance_id']] = face; P.check(graph)
        if not face['enabled'] or face['evidence']['status'] != 'verified':
            raise ValueError('Eye-bag aliases cannot restore an unreviewed or disabled face')
    before = deepcopy(marker['before_face']); after = deepcopy(marker['after_face'])
    expected_support = {'owner': ref, 'content_sha256': marker['support_sha256'], 'kind': S.KIND}
    if after['local_assets'].get(S.KIND) != expected_support:
        raise ValueError('Eye-bag alias history changed its exact reviewed ridge asset')
    before['local_assets'].pop(S.KIND, None); after['local_assets'].pop(S.KIND, None)
    if before != after:
        raise ValueError('Direct eye-bag history cannot change observations, other support or face ownership')
    scopes = entry.get('people_scoped_changes')
    if (type(scopes) is not list or len(scopes) != 1 or type(scopes[0]) is not dict
            or set(scopes[0]) != {'scope', 'document_id', 'changes'}
            or scopes[0]['scope'] != marker['people_scope'] or scopes[0]['document_id'] not in ids
            or type(scopes[0]['changes']) is not list or not 1 <= len(scopes[0]['changes']) <= 4):
        raise ValueError('Eye-bag aliases require one exact shared graph scope and narrow patch')
    seen = set(); changed_face = False
    for change in scopes[0]['changes']:
        if (type(change) is not dict or set(change) != {'collection', 'key', 'before', 'after'}
                or change['before'] == change['after']):
            raise ValueError('Invalid or no-op eye-bag alias patch')
        collection = change['collection']; key = change['key']
        if collection == 'faces':
            if (changed_face or key != ref['face_instance_id']
                    or change['before'] != marker['before_face'] or change['after'] != marker['after_face']):
                raise ValueError('Eye-bag history may change only the exact selected face ridge descriptor')
            changed_face = True
        elif collection == 'overrides':
            if type(key) is not list or len(key) != 4 or key[:2] != ['face', ref['face_instance_id']]:
                raise ValueError('Eye-bag alias history cannot change another editing scope')
            operation, path = key[2:]
            if operation == S.OP and path in ('/amount', '/preserve'):
                value = recipe[path[1:]]
            elif operation == A.ENHANCE and path == '/eye_bags' and marker['replace_legacy']:
                value = 0.0
            else: raise ValueError('Eye-bag alias history contains an unapproved parameter')
            identity = (operation, path)
            if identity in seen: raise ValueError('Eye-bag alias history repeats a scalar patch')
            seen.add(identity)
            for record in (change['before'], change['after']):
                if record is None: continue
                if (type(record) is not dict or set(record) != {'scope', 'target_id', 'operation_id', 'parameter_path', 'value'}
                        or [record[name] for name in ('scope', 'target_id', 'operation_id', 'parameter_path')] != key):
                    raise ValueError('Eye-bag alias scalar identity changed')
                P.scalar(record['value'])
            after_value = (change['after'] or {}).get('value')
            if type(after_value) not in (int, float) or after_value != value:
                raise ValueError('Eye-bag alias scalar differs from reviewed intent or explicit legacy zero')
        else: raise ValueError('Eye-bag alias history cannot change associations or other observations')
    if changed_face != (marker['before_face'] != marker['after_face']):
        raise ValueError('Eye-bag history omitted or invented its source-owned ridge change')
    _targets(entry.get('targets'), marker)
    dependencies = marker['dependencies']
    if type(dependencies) is not list or len(dependencies) != len(ids):
        raise ValueError('Eye-bag alias history needs every member complete input dependency')
    seen = set()
    for item in dependencies:
        if type(item) is not dict or set(item) != {'document_id', 'source_proof', 'before', 'after'}:
            raise ValueError('Incomplete eye-bag alias dependency record')
        doc = P.token(item['document_id'])
        if doc not in ids or doc in seen: raise ValueError('Eye-bag alias dependency membership changed')
        seen.add(doc); proof = SOURCE.check_row_proof(item['source_proof'])
        matches = [target for target in entry['targets'].values() if target['document_id'] == doc]
        if len(matches) != 1 or matches[0]['source_proof'] != proof:
            raise ValueError('Eye-bag alias dependency source changed')
        for side in ('before', 'after'):
            value = item[side]
            if type(value) is not dict or set(value) != {'context_sha256', 'state_sha256'}:
                raise ValueError('Eye-bag history lacks its before/after support context')
            for digest in value.values(): P.digest(digest)
        if item['before']['state_sha256'] != item['after']['state_sha256']:
            raise ValueError('Direct eye-bag editing cannot replace a member repair/crop input')
    return deepcopy(marker)


def prepare(engine, review, plans, targets):
    from .people_graph_patch import between
    # Check the complete visual-to-ledger target correspondence without
    # treating a ridge change as face-style scalar-only history.
    members = review.get('members')
    if type(members) is not list or not 2 <= len(members) <= MAX_MEMBERS or set(plans) != {'project'}:
        raise ValueError('Eye-bag alias history needs its complete actual shared owner review')
    plan = plans['project']; ref = P.check_ref(review['face_ref'])
    marker = {'version': 1, 'review_sha256': review['review_sha256'], 'people_scope': 'project',
        'document_ids': sorted(member['visual']['document_id'] for member in members),
        'asset_sha256': ref['asset_sha256'], 'face_ref': deepcopy(ref), 'recipe': deepcopy(review['recipe']),
        'replace_legacy': review['replace_legacy'], 'support_sha256': review['support_sha256'],
        'before_face': deepcopy(plan['before']['faces'][ref['face_instance_id']]),
        'after_face': deepcopy(plan['candidate']['faces'][ref['face_instance_id']]),
        'before_graph_sha256': graph_digest(plan['before']), 'after_graph_sha256': graph_digest(plan['candidate']),
        'dependencies': []}
    for member in members:
        visual = member['visual']; doc = visual['document_id']
        matches = [target for target in targets.values() if target.get('document_id') == doc]
        if (len(matches) != 1 or member['path'] != matches[0]['path']
                or visual['revision'] != str(matches[0]['revision']) or visual['source_proof'] != matches[0]['source_proof']):
            raise ValueError('Eye-bag history differs from its exact reviewed member input')
        found = engine._document_versions().find(engine._docs, doc)
        if found is None: raise ValueError('Eye-bag alias history document disappeared')
        row = found[1]
        marker['dependencies'].append({'document_id': doc, 'source_proof': deepcopy(visual['source_proof']),
            'before': _dependencies(engine, row, plan['before']), 'after': _dependencies(engine, row, plan['candidate'])})
    entry = {'ops': ['lnx.people_graph.v1'], 'people_changes': [], 'policy': 'protected_scoped_graph',
        'targets': targets, 'people_scoped_changes': [{'scope': 'project', 'document_id': plan['row']['document_id'],
                                                    'changes': between(plan['before'], plan['candidate'])}], KEY: marker}
    return check(entry)


def _restore_members(engine, row, asset, graph):
    """Same closure/availability contract without requiring an active alias.

    Protected batch undo can be requested while another source or private copy
    is selected. It still uses the retained existing project owner, never a new
    owner or a temporary switch to an alias document.
    """
    from . import face_style_alias_review as CLOSURE, virtual_copy_people as V
    CLOSURE._pending(engine, row)
    project = engine.__dict__.get('_people_project_context')
    if (V.scope(row) != V.PROJECT or type(project) is not dict or project.get('owner') is None
            or project['owner'].snapshot() != graph):
        raise ValueError('Eye-bag alias restore requires its exact retained shared portrait owner')
    current = engine._people_preset_capture() if V.current_row(engine) is not None else None
    members = []; seen = set()
    for other in CLOSURE._scope_rows(engine, row):
        source = SOURCE.row_proof(CLOSURE._source_row(engine, other, current))
        if source['asset_sha256'] != asset: continue
        state = CLOSURE._current_state(engine, other, current); path = other.get('path')
        if (other.get('trashed') or other.get('_people_new_import') or type(state) is not dict
                or type(path) is not str or not 1 <= len(path.encode('utf-8')) <= 4096 or '\0' in path):
            raise ValueError('Every restored eye-bag alias must retain its available complete document input')
        version = engine._document_versions().check_advance(other)
        if (version.revision >= CLOSURE.MAX_REVISION or version.document_id in seen
                or version.document_id != other.get('document_id')):
            raise ValueError('Eye-bag alias restore document identity or revision is invalid')
        P.token(version.document_id); seen.add(version.document_id)
        SOURCE.verify_row({**other, 'state': state}, source)
        members.append((other, state, source, version))
    if not 2 <= len(members) <= MAX_MEMBERS or not any(member[0] is row for member in members):
        raise ValueError('Eye-bag alias restore lost its complete original shared member set')
    return members


def verify_restore(engine, entry, plans, targets, *, redo):
    marker = check(entry)
    if marker is None: return
    from .people_graph_owner import affected_assets
    from .face_style_alias_review import verify_dormant
    if set(plans) != {marker['people_scope']}:
        raise ValueError('Eye-bag alias restore changed its shared graph owner')
    _targets(targets, marker)
    plan = plans[marker['people_scope']]; expected = 'before' if redo else 'after'; result = 'after' if redo else 'before'
    if (affected_assets(plan['before'], plan['candidate']) != {marker['asset_sha256']}
            or graph_digest(plan['before']) != marker[expected + '_graph_sha256']
            or graph_digest(plan['candidate']) != marker[result + '_graph_sha256']):
        raise ValueError('Eye-bag alias complete mixed graph changed; protected replay refused')
    verify_dormant(engine, plan['row'], {marker['asset_sha256']})
    # The generic ledger is intentionally broader than direct alias authority.
    # Require the same live, non-trashed, available project rows on restore.
    members = _restore_members(engine, plan['row'], marker['asset_sha256'], plan['before'])
    if {member[3].document_id for member in members} != set(marker['document_ids']):
        raise ValueError('Eye-bag alias availability or exact membership changed')
    by_document = {item['document_id']: item for item in marker['dependencies']}
    for target in targets.values():
        item = by_document[target['document_id']]
        if target['source_proof'] != item['source_proof']:
            raise ValueError('Eye-bag alias history changed effective source provenance')
        found = engine._document_versions().find(engine._docs, target['document_id'])
        if found is None: raise ValueError('Eye-bag alias history target disappeared')
        if (_dependencies(engine, found[1], plan['before']) != item[expected]
                or _dependencies(engine, found[1], plan['candidate']) != item[result]):
            raise ValueError('Eye-bag alias repair, crop, analysis, ridge or recovery inputs changed; protected replay refused')


def status_summary(entry):
    marker = check(entry)
    return None if marker is None else {'version': 1, 'review_sha256': marker['review_sha256'],
                                        'member_count': len(marker['document_ids'])}
