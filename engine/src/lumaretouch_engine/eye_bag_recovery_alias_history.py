# SPDX-License-Identifier: GPL-3.0-or-later
"""Exact shared-source effect-recovery history in the existing ledger. UNRUN.

Only the selected face's eye_bag_preserve immutable vector pointer may change.
This is neither ridge editing nor mixed preset/document-state history. Both
vector records and every member's own source/repair/input dependencies survive
save/reopen; no donor vector, scalar or association mutation is authorized.
"""
from copy import deepcopy
from . import people_state as P, people_support_assets as BANK
from . import creative_derived_source as SOURCE, virtual_copy_people as V
from .eye_bag_alias_history import graph_digest, MAX_MEMBERS
from .eye_bag_preset_alias_history import stable, state_fields, project_state, LIVE_FIELDS

KEY = 'eye_bag_recovery_alias_review'
TARGET = 'eye_bag_preserve'
OTHER_MARKERS = ('face_style_alias_review', 'eye_bag_batch_review', 'eye_bag_cohort_review',
                 'eye_bag_alias_review', 'eye_bag_preset_alias_review')


def current_state(engine, row):
    return engine._people_preset_capture() if row is V.current_row(engine) else row['state']


def dependencies(engine, row, graph, assets, fields):
    from .full_candidate_render import people_context
    from .people_retained_analysis import key as analysis_key
    state = current_state(engine, row); context = people_context(engine, row)
    asset = SOURCE.row_proof({**row, 'state': state})['asset_sha256']
    if '_sky_replacement' in state:
        from .sky_replacement_state import check_saved_record
        sky = check_saved_record(state['_sky_replacement'])
        if sky['enabled']:
            from .sky_replacement_assets import verify
            verify(sky['asset'])
    faces = {key: face for key, face in graph['faces'].items() if face['asset_sha256'] == asset}
    keys = {item['content_sha256'] for face in faces.values() for item in face['local_assets'].values()}
    if not keys <= set(assets): raise ValueError('Recovery history is missing referenced immutable support')
    own = {'faces': faces,
        'people_landmarks': {analysis_key(P.face_ref(face)): context['people_landmarks'].get(analysis_key(P.face_ref(face))) for face in faces.values()},
        'support_assets': {key: assets[key] for key in sorted(keys)},
        **{key: value for key, value in context.items() if key not in (
            'version', 'people_graph', 'people_landmarks', 'people_support_assets', 'people_cursors', 'people_targets')}}
    return {'context_sha256': stable(own), 'state_sha256': stable(project_state(state, fields))}


def _targets(targets, marker):
    if type(targets) is not dict or len(targets) != len(marker['document_ids']):
        raise ValueError('Recovery alias history requires every exact affected member')
    seen = set()
    for item in targets.values():
        if type(item) is not dict: raise ValueError('Invalid recovery alias target')
        doc = P.token(item.get('document_id')); proof = SOURCE.check_row_proof(item.get('source_proof'))
        if (doc in seen or item.get('people_scope') != 'project' or item.get('asset_sha256') != marker['asset_sha256']
                or proof['asset_sha256'] != marker['asset_sha256'] or item.get('reviewed_face_refs') != [marker['face_ref']]):
            raise ValueError('Recovery alias history changed source, face or shared owner')
        seen.add(doc)
    if seen != set(marker['document_ids']): raise ValueError('Recovery alias history added or omitted a member')


def _asset(face, ref, record):
    descriptor = face['local_assets'].get(TARGET)
    if descriptor is None:
        if record is not None: raise ValueError('Detached recovery pointer cannot name a vector')
        return None
    if type(record) is not dict or type(record.get('version')) is not int:
        raise ValueError('Recovery history needs its exact immutable vector record')
    digest = BANK.content_digest(record)
    if descriptor != {'owner': ref, 'content_sha256': digest, 'kind': TARGET}:
        raise ValueError('Recovery history vector and selected face pointer disagree')
    graph = P.empty(); graph['faces'][ref['face_instance_id']] = deepcopy(face)
    BANK.check_store({digest: record}); BANK.resolve(graph, {digest: record}, ref, TARGET)
    return digest


def check(entry):
    if KEY not in entry: return None
    marker = entry[KEY]
    fields = {'version', 'review_sha256', 'people_scope', 'document_ids', 'asset_sha256', 'face_ref', 'target',
        'before_face', 'after_face', 'before_graph_sha256', 'after_graph_sha256', 'recovery_assets', 'state_fields', 'dependencies'}
    if (type(marker) is not dict or set(marker) != fields or type(marker['version']) is not int or marker['version'] != 1
            or any(key in entry for key in OTHER_MARKERS) or entry.get('ops') != ['lnx.people_graph.v1']
            or entry.get('people_changes') != [] or entry.get('policy') != 'protected_scoped_graph'):
        raise ValueError('Malformed eye-bag recovery alias history marker')
    for key in ('review_sha256', 'asset_sha256', 'before_graph_sha256', 'after_graph_sha256'): P.digest(marker[key])
    ref = P.check_ref(marker['face_ref']); ids = marker['document_ids']; saved_fields = marker['state_fields']
    if (marker['people_scope'] != 'project' or marker['target'] != TARGET or ref['asset_sha256'] != marker['asset_sha256']
            or marker['before_graph_sha256'] == marker['after_graph_sha256']):
        raise ValueError('Recovery history requires a real change on its exact shared source')
    if type(ids) is not list or not 2 <= len(ids) <= MAX_MEMBERS: raise ValueError('Recovery history needs two to sixteen exact members')
    for doc in ids: P.token(doc)
    if ids != sorted(set(ids)): raise ValueError('Recovery history member list is not canonical')
    if (type(saved_fields) is not list or not saved_fields or len(saved_fields) > 512
            or any(type(field) is not str or not field for field in saved_fields)
            or saved_fields != sorted(set(saved_fields)) or set(saved_fields) & LIVE_FIELDS):
        raise ValueError('Recovery history lacks complete durable member input fields')
    assets = marker['recovery_assets']
    if type(assets) is not dict or set(assets) != {'before', 'after'}: raise ValueError('Recovery history needs both vector sides')
    pointers = []
    for side in ('before', 'after'):
        face = marker[side + '_face']; graph = P.empty()
        if type(face) is not dict or P.face_ref(face) != ref: raise ValueError('Recovery history changed selected face identity')
        graph['faces'][ref['face_instance_id']] = face; P.check(graph)
        if not face['enabled'] or face['evidence']['status'] != 'verified':
            raise ValueError('Recovery history requires the original enabled verified face')
        pointers.append(_asset(face, ref, assets[side]))
    before = deepcopy(marker['before_face']); after = deepcopy(marker['after_face'])
    before['local_assets'].pop(TARGET, None); after['local_assets'].pop(TARGET, None)
    if before != after or pointers[0] == pointers[1]:
        raise ValueError('Recovery history may change only its exact effect vector reference')
    scopes = entry.get('people_scoped_changes')
    if (type(scopes) is not list or len(scopes) != 1 or type(scopes[0]) is not dict
            or set(scopes[0]) != {'scope', 'document_id', 'changes'} or scopes[0]['scope'] != 'project'
            or scopes[0]['document_id'] not in ids or type(scopes[0]['changes']) is not list or len(scopes[0]['changes']) != 1):
        raise ValueError('Recovery history requires one shared owner and one exact face patch')
    expected = {'collection': 'faces', 'key': ref['face_instance_id'], 'before': marker['before_face'], 'after': marker['after_face']}
    if scopes[0]['changes'][0] != expected:
        raise ValueError('Recovery history cannot change scalars, ridge support, associations or another face')
    _targets(entry.get('targets'), marker)
    records = marker['dependencies']
    if type(records) is not list or len(records) != len(ids): raise ValueError('Recovery history omitted complete member dependencies')
    seen = set()
    for record in records:
        if type(record) is not dict or set(record) != {'document_id', 'source_proof', 'before', 'after'}:
            raise ValueError('Malformed recovery history dependency')
        doc = P.token(record['document_id']); proof = SOURCE.check_row_proof(record['source_proof'])
        if doc in seen or doc not in ids: raise ValueError('Recovery history dependency membership changed')
        seen.add(doc)
        target = next(item for item in entry['targets'].values() if item['document_id'] == doc)
        if target['source_proof'] != proof: raise ValueError('Recovery history member source provenance changed')
        for side in ('before', 'after'):
            value = record[side]
            if type(value) is not dict or set(value) != {'context_sha256', 'state_sha256'}:
                raise ValueError('Recovery history lacks a complete input/support context')
            for digest in value.values(): P.digest(digest)
        if record['before']['state_sha256'] != record['after']['state_sha256']:
            raise ValueError('Recovery alias history cannot change any member document recipe')
    return deepcopy(marker)


def require_assets(marker, assets):
    BANK.check_store(assets)
    for side, record in marker['recovery_assets'].items():
        key = _asset(marker[side + '_face'], marker['face_ref'], record)
        if key is not None and assets.get(key) != record:
            raise ValueError('Recovery alias history immutable vector is missing or changed')


def prepare(engine, review, plans, targets, *, before_assets, after_assets):
    from .people_graph_patch import between
    if set(plans) != {'project'}: raise ValueError('Recovery aliases require their original shared owner')
    BANK.check_store(before_assets); BANK.check_store(after_assets)
    if any(after_assets.get(key) != value for key, value in before_assets.items()):
        raise ValueError('Recovery publication cannot replace or remove immutable retained assets')
    plan = plans['project']; ref = P.check_ref(review['face_ref']); members = review.get('members')
    if type(members) is not list or not 2 <= len(members) <= MAX_MEMBERS:
        raise ValueError('Recovery history requires every full-render reviewed member')
    marker = {'version': 1, 'review_sha256': review['review_sha256'], 'people_scope': 'project', 'target': TARGET,
        'document_ids': sorted(member['visual']['document_id'] for member in members), 'asset_sha256': ref['asset_sha256'],
        'face_ref': deepcopy(ref), 'before_face': deepcopy(plan['before']['faces'][ref['face_instance_id']]),
        'after_face': deepcopy(plan['candidate']['faces'][ref['face_instance_id']]),
        'before_graph_sha256': graph_digest(plan['before']), 'after_graph_sha256': graph_digest(plan['candidate']),
        'state_fields': state_fields(engine), 'recovery_assets': {}, 'dependencies': []}
    for side, bank in (('before', before_assets), ('after', after_assets)):
        pointer = marker[side + '_face']['local_assets'].get(TARGET)
        marker['recovery_assets'][side] = None if pointer is None else deepcopy(bank.get(pointer['content_sha256']))
    after_pointer = marker['after_face']['local_assets'].get(TARGET)
    allowed = set() if after_pointer is None else {after_pointer['content_sha256']}
    if set(after_assets) - set(before_assets) - allowed:
        raise ValueError('Recovery publication cannot append unrelated or donor support assets')
    for member in members:
        visual = member['visual']; doc = visual['document_id']
        matches = [target for target in targets.values() if target.get('document_id') == doc]
        if (len(matches) != 1 or matches[0]['path'] != member['path'] or str(matches[0]['revision']) != visual['revision']
                or matches[0]['source_proof'] != visual['source_proof']):
            raise ValueError('Recovery ledger target differs from its actual reviewed source/revision')
        found = engine._document_versions().find(engine._docs, doc)
        if found is None: raise ValueError('Recovery history member disappeared')
        marker['dependencies'].append({'document_id': doc, 'source_proof': deepcopy(visual['source_proof']),
            'before': dependencies(engine, found[1], plan['before'], before_assets, marker['state_fields']),
            'after': dependencies(engine, found[1], plan['candidate'], after_assets, marker['state_fields'])})
    entry = {'ops': ['lnx.people_graph.v1'], 'people_changes': [], 'policy': 'protected_scoped_graph', 'targets': targets,
        'people_scoped_changes': [{'scope': 'project', 'document_id': plan['row']['document_id'],
                                  'changes': between(plan['before'], plan['candidate'])}], KEY: marker}
    checked = check(entry); require_assets(checked, after_assets)
    before_pointer = marker['before_face']['local_assets'].get(TARGET); after_pointer = marker['after_face']['local_assets'].get(TARGET)
    if (review.get('target') != TARGET or review.get('before_recovery_sha256') != (before_pointer or {}).get('content_sha256')
            or review.get('recovery_sha256') != (after_pointer or {}).get('content_sha256')):
        raise ValueError('Recovery history pointers differ from the actual full-render review')
    return checked


def _members(engine, marker, graph, *, advance):
    from . import face_style_alias_review as CLOSURE
    project = engine.__dict__.get('_people_project_context')
    if type(project) is not dict or project.get('owner') is None or project['owner'].snapshot() != graph:
        raise ValueError('Recovery history needs its exact retained shared owner')
    anchor = next((row for row in engine._docs if row.get('document_id') in marker['document_ids']), None)
    if anchor is None or V.scope(anchor) != 'project': raise ValueError('Recovery history original owner disappeared')
    CLOSURE._pending(engine, anchor)
    result = []; seen = set()
    for row in CLOSURE._scope_rows(engine, anchor):
        state = current_state(engine, row); proof = SOURCE.row_proof({**row, 'state': state})
        if proof['asset_sha256'] != marker['asset_sha256']: continue
        path = row.get('path')
        if (row.get('trashed') or row.get('_people_new_import') or type(state) is not dict or type(path) is not str
                or not 1 <= len(path.encode('utf-8')) <= 4096 or '\0' in path):
            raise ValueError('Every recovery alias must retain its available complete document input')
        versions = engine._document_versions()
        version = versions.check_advance(row) if advance else versions.version(row)
        if (version.document_id in seen or version.document_id != row.get('document_id')
                or version.revision > CLOSURE.MAX_REVISION or (advance and version.revision == CLOSURE.MAX_REVISION)):
            raise ValueError('Recovery history member identity or bounded revision is invalid')
        P.token(version.document_id); seen.add(version.document_id)
        SOURCE.verify_row({**row, 'state': state}, proof)
        result.append((row, state, proof, version))
    if not 2 <= len(result) <= MAX_MEMBERS or seen != set(marker['document_ids']):
        raise ValueError('Recovery history exact affected member closure changed')
    return result


def targets(engine, marker, graph, *, advance=True):
    members = _members(engine, marker, graph, advance=advance)
    result = {}
    for row, state, proof, version in members:
        index = next(index for index, candidate in enumerate(engine._docs) if candidate is row)
        result[str(index)] = {'path': row['path'], 'document_id': version.document_id, 'revision': version.revision,
            'asset_sha256': marker['asset_sha256'], 'people_scope': 'project', 'source_proof': proof,
            'reviewed_face_refs': [deepcopy(marker['face_ref'])]}
    _targets(result, marker)
    return result


def verify_restore(engine, entry, plans, actual_targets, *, redo, assets, advance=True):
    marker = check(entry)
    if marker is None: return
    from .people_graph_owner import affected_assets
    from .face_style_alias_review import verify_dormant
    if set(plans) != {'project'} or state_fields(engine) != marker['state_fields']:
        raise ValueError('Recovery history shared owner or durable field schema changed')
    _targets(actual_targets, marker); require_assets(marker, assets)
    plan = plans['project']; expected = 'before' if redo else 'after'; result = 'after' if redo else 'before'
    if (plan['before']['association_revision'] != plan['candidate']['association_revision']
            or affected_assets(plan['before'], plan['candidate']) != {marker['asset_sha256']}
            or graph_digest(plan['before']) != marker[expected + '_graph_sha256']
            or graph_digest(plan['candidate']) != marker[result + '_graph_sha256']):
        raise ValueError('Recovery history complete graph changed; protected replay refused')
    verify_dormant(engine, plan['row'], {marker['asset_sha256']})
    closure = targets(engine, marker, plan['before'], advance=advance)
    if {item['document_id']: item for item in closure.values()} != {item['document_id']: item for item in actual_targets.values()}:
        raise ValueError('Recovery alias member availability, source, path or revision changed')
    for item in marker['dependencies']:
        row = engine._document_versions().find(engine._docs, item['document_id'])[1]
        proof = SOURCE.row_proof({**row, 'state': current_state(engine, row)})
        if (proof != item['source_proof'] or dependencies(engine, row, plan['before'], assets, marker['state_fields']) != item[expected]
                or dependencies(engine, row, plan['candidate'], assets, marker['state_fields']) != item[result]):
            raise ValueError('Recovery history source, repair, own recipe, analysis or support changed; protected replay refused')


def validate_project_assets(entry, project):
    marker = check(entry)
    if marker is not None: require_assets(marker, project.get('people_support_assets'))


def status_summary(entry):
    marker = check(entry)
    return None if marker is None else {'version': 1, 'review_sha256': marker['review_sha256'], 'member_count': len(marker['document_ids'])}
