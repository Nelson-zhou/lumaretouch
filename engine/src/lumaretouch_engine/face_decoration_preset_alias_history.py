# SPDX-License-Identifier: GPL-3.0-or-later
"""Composite mixed-preset history in the sole protected people ledger. UNRUN.

The shared graph owns portrait scalars. Only the originally selected document
owns the nonportrait recipe delta. Runtime caches and rendered pixel snapshots
are never saved here; real recipe assets use the existing project codec.
"""
from copy import deepcopy
from . import people_state as P, creative_derived_source as SOURCE, virtual_copy_people as V
from . import people_support_assets as BANK
from .collarbone_transfer_review import coverage_digest
from .eye_bag_alias_history import graph_digest, MAX_MEMBERS

KEY = 'face_decoration_preset_alias_review'
# These are editing views of the canonical graph, selection cursors or runtime
# caches, not a second portrait recipe. _proxy remains a repair-coordinate fence.
LIVE_FIELDS = frozenset(('_precompute', '_precompute_backend', '_face_index', '_face_explicit',
    '_face_box', '_deform', '_deform_defer',
    '_enhance', '_enhance_defer', '_lip_makeup', '_brow_shape', '_brow_shape_owner',
    '_nose_shape', '_nose_shape_owner', '_eye_shape', '_eye_shape_owner', '_mouth_shape',
    '_mouth_shape_owner', '_op_seq'))
OTHER_MARKERS = ('face_style_alias_review', 'eye_bag_batch_review', 'eye_bag_cohort_review', 'eye_bag_alias_review',
    'eye_bag_preset_alias_review', 'eye_bag_recovery_alias_review', 'face_decoration_batch_review',
    'face_decoration_alias_review', 'face_decoration_cohort_review', 'face_decoration_support_alias_review')


def state_fields(engine):
    return sorted((set(engine.DOC_FIELDS) | {'_proxy'}) - set(engine.HISTORY_SKIP) - LIVE_FIELDS)


def project_state(value, fields):
    from .people_preset_plan import clone_state
    if type(value) is not dict or not set(fields) <= set(value):
        raise ValueError('Mixed decoration preset history lacks complete durable document fields')
    return {key: clone_state(value[key]) for key in fields}


def stable(value):
    from .project import encode
    assets = {}; dropped = []
    encoded = encode(value, assets, dropped, 'face_decoration_preset_alias')
    if dropped: raise ValueError('Mixed decoration preset history cannot omit unsavable recipe or context data')
    # Portable packages relocate this one validated external-asset locator.
    # Content, decoded extent, bit depth, ICC and every other recipe field stay
    # exact. Never normalize arbitrary paths or recompute frozen state hashes.
    def content_identity(item):
        if type(item) is dict:
            out = {key: content_identity(child) for key, child in item.items()}
            if '_sky_replacement' in item:
                from .sky_replacement_state import check_saved_record, asset
                sky = item['_sky_replacement']; check_saved_record(sky)
                binding = asset(sky.get('asset'))
                if binding is not None: out['_sky_replacement']['asset'].pop('path')
            return out
        if type(item) is list: return [content_identity(child) for child in item]
        return item
    return coverage_digest({'value': content_identity(encoded), 'assets': {key: {name: item[name]
        for name in ('kind', 'shape', 'dtype', 'bytes')} for key, item in assets.items()}})


def dependencies(engine, row, state, graph, fields, assets=None):
    from .full_candidate_render import people_context
    from .people_retained_analysis import key as analysis_key
    context = people_context(engine, row); asset = SOURCE.row_proof({**row, 'state': state})['asset_sha256']
    assets = context['people_support_assets'] if assets is None else assets
    if '_sky_replacement' in state:
        from .sky_replacement_state import check_saved_record
        sky = check_saved_record(state['_sky_replacement'])
        if sky['enabled']:
            from .sky_replacement_assets import verify
            verify(sky['asset'])  # Relocatable locator never grants different bytes.
    faces = {key: face for key, face in graph['faces'].items() if face['asset_sha256'] == asset}
    keys = {item['content_sha256'] for face in faces.values() for item in face['local_assets'].values()}
    if not keys <= set(assets): raise ValueError('Mixed decoration history lost source-owned immutable support')
    own = {'faces': faces,
        'people_landmarks': {analysis_key(P.face_ref(face)): context['people_landmarks'].get(analysis_key(P.face_ref(face))) for face in faces.values()},
        'support_assets': {key: assets[key] for key in sorted(keys)},
        # Other retained source-owned support is also a fence, never copied into
        # a recipient. Refuse rather than ignore a changed hair/evidence bank.
        **{key: value for key, value in context.items() if key not in (
            'version', 'people_graph', 'people_landmarks', 'people_support_assets', 'people_cursors', 'people_targets')}}
    return {'context_sha256': stable(own), 'state_sha256': stable(project_state(state, fields))}


def _targets(targets, marker):
    if type(targets) is not dict or len(targets) != len(marker['document_ids']):
        raise ValueError('Mixed decoration preset history requires every exact alias target')
    seen = set()
    for item in targets.values():
        if type(item) is not dict: raise ValueError('Malformed mixed preset history target')
        doc = P.token(item.get('document_id')); proof = SOURCE.check_row_proof(item.get('source_proof'))
        if (doc in seen or item.get('people_scope') != 'project' or proof['asset_sha256'] != marker['asset_sha256']
                or item.get('asset_sha256') != marker['asset_sha256'] or item.get('reviewed_face_refs') != marker['reviewed_face_refs']):
            raise ValueError('Mixed decoration preset history changed target source, face or shared owner')
        seen.add(doc)
    if seen != set(marker['document_ids']): raise ValueError('Mixed decoration preset history omitted or added an alias')


def _changes(entry, marker):
    from . import people_algorithms as A
    scopes = entry.get('people_scoped_changes')
    if (type(scopes) is not list or len(scopes) != 1 or type(scopes[0]) is not dict
            or set(scopes[0]) != {'scope', 'document_id', 'changes'} or scopes[0]['scope'] != 'project'
            or scopes[0]['document_id'] != marker['current_document_id'] or type(scopes[0]['changes']) is not list
            or len(scopes[0]['changes']) > 4096):
        raise ValueError('Mixed decoration preset history requires its one original shared owner')
    seen = set()
    for change in scopes[0]['changes']:
        if (type(change) is not dict or set(change) != {'collection', 'key', 'before', 'after'}
                or change['collection'] != 'overrides' or type(change['key']) is not list or len(change['key']) != 4
                or change['key'][:2] != ['face', marker['face_ref']['face_instance_id']]
                or change['after'] is None or change['before'] == change['after']):
            raise ValueError('Mixed decoration presets may change selected face scalars only, never observations or support')
        key = tuple(change['key']); operation, path = key[2:]
        if key in seen: raise ValueError('Mixed decoration preset history repeats a graph leaf')
        seen.add(key); P.token(operation); P.parameter_path(path)
        if operation not in marker['selected_modules']:
            raise ValueError('Mixed decoration preset history changed an unselected portrait operation')
        if path not in A.defaults().get(operation, {}): raise ValueError('Unknown mixed preset portrait leaf')
        for record in (change['before'], change['after']):
            if record is None: continue
            if (type(record) is not dict or set(record) != {'scope', 'target_id', 'operation_id', 'parameter_path', 'value'}
                    or tuple(record[name] for name in ('scope', 'target_id', 'operation_id', 'parameter_path')) != key):
                raise ValueError('Mixed decoration preset graph leaf identity changed')
            P.scalar(record['value'])
    graph_changed = marker['before_graph_sha256'] != marker['after_graph_sha256']
    if bool(scopes[0]['changes']) != graph_changed:
        raise ValueError('Mixed decoration preset history omitted or manufactured a graph change')


def _evidence(entry, marker):
    from .face_decoration_preset_alias_review import check_ack
    from .face_decoration_preset_coverage import checked
    from .face_decoration_state import OP
    from .face_decoration_support import KIND
    P.digest(marker['ack_sha256']); P.digest(marker['before_bank_sha256'])
    ack = check_ack(marker['ack'])
    if (coverage_digest(ack) != marker['ack_sha256']
            or any(ack[key] != marker[key] for key in ('review_sha256', 'preset_sha256', 'applies_sha256'))
            or [item['document_id'] for item in ack['members']][0] != marker['current_document_id']
            or sorted(item['document_id'] for item in ack['members']) != marker['document_ids']):
        raise ValueError('Mixed decoration history lacks the exact all-member image acknowledgment')
    coverage = checked(marker['coverage'], marker['asset_sha256'])
    refs = [item['face_ref'] for item in coverage['targets']]
    if marker['reviewed_face_refs'] != refs or marker['face_ref'] not in refs:
        raise ValueError('Mixed decoration history omitted selected or active face coverage')
    if OP not in marker['selected_modules'] and not any(item['scope'] == 'target-reviewed-visible-skin' for item in coverage['targets']):
        raise ValueError('Mixed decoration history has no selected or retained decoration review purpose')
    for item in ack['members']:
        target = next(value for value in entry['targets'].values() if value['document_id'] == item['document_id'])
        if str(target['revision']) != item['revision'] or item['coverage_sha256'] != coverage_digest(coverage):
            raise ValueError('Mixed decoration acknowledgment changed a reviewed revision or complete coverage')
    BANK.check_store(marker['support_assets'])
    if any(record['face_ref']['asset_sha256'] != marker['asset_sha256'] for record in marker['support_assets'].values()):
        raise ValueError('Mixed decoration history cannot retain a donor source support asset')
    for item in coverage['targets']:
        if item['scope'] != 'target-reviewed-visible-skin': continue
        record = marker['support_assets'].get(item['visibility_sha256'])
        if record is None or record['face_ref'] != item['face_ref'] or record['row']['target'] != KIND:
            raise ValueError('Mixed decoration history visibility proof is not its exact target-owned retained record')


def require_assets(marker, assets, graph=None):
    """History admits append-only bank growth, never deletion or rebinding."""
    BANK.check_store(assets)
    if any(assets.get(key) != record for key, record in marker['support_assets'].items()):
        raise ValueError('Mixed decoration history immutable target-owned support is missing or changed')
    if graph is not None:
        required = {descriptor['content_sha256'] for face in graph['faces'].values()
                    if face['asset_sha256'] == marker['asset_sha256'] for descriptor in face['local_assets'].values()}
        if required != set(marker['support_assets']):
            raise ValueError('Mixed decoration history changed its exact source-owned support references')


def check(entry):
    if KEY not in entry: return None
    marker = entry[KEY]
    fields = {'version', 'review_sha256', 'preset_sha256', 'applies_sha256', 'selected_modules',
        'current_document_id', 'document_ids', 'asset_sha256', 'face_ref', 'reviewed_face_refs',
        'ack_sha256', 'ack', 'before_bank_sha256', 'support_assets', 'coverage',
        'before_graph_sha256', 'after_graph_sha256', 'state_fields', 'current_states', 'dependencies'}
    if (type(marker) is not dict or set(marker) != fields or type(marker['version']) is not int or marker['version'] != 1
            or any(key in entry for key in OTHER_MARKERS) or entry.get('ops') != ['lnx.people_graph.v1']
            or entry.get('people_changes') != [] or entry.get('policy') != 'protected_scoped_graph'):
        raise ValueError('Malformed mixed decoration preset alias history marker')
    for key in ('review_sha256', 'preset_sha256', 'applies_sha256', 'asset_sha256', 'before_graph_sha256', 'after_graph_sha256'):
        P.digest(marker[key])
    modules = marker['selected_modules']; ids = marker['document_ids']; saved_fields = marker['state_fields']
    if (type(modules) is not list or not 1 <= len(modules) <= 256 or any(type(op) is not str for op in modules)
            or len(set(modules)) != len(modules) or 'lnx.people_graph.v1' in modules):
        raise ValueError('Mixed decoration preset history lost its exact selected modules')
    from . import scope as SC
    if len(modules) > SC.PRESET_MAX_MODULES or SC.check_scope(modules) != modules:
        raise ValueError('Mixed decoration preset history exceeds the existing selected-module contract')
    for op in modules: P.token(op)
    if type(ids) is not list or not 2 <= len(ids) <= MAX_MEMBERS: raise ValueError('Mixed decoration preset history needs two to sixteen aliases')
    for doc in ids: P.token(doc)
    if ids != sorted(set(ids)) or P.token(marker['current_document_id']) not in ids:
        raise ValueError('Mixed decoration preset history changed its original current document')
    if P.check_ref(marker['face_ref'])['asset_sha256'] != marker['asset_sha256']:
        raise ValueError('Mixed decoration preset history changed its source or selected face')
    if (type(saved_fields) is not list or not 1 <= len(saved_fields) <= 256
            or any(type(key) is not str or not key.startswith('_') for key in saved_fields)
            or saved_fields != sorted(set(saved_fields)) or set(saved_fields) & LIVE_FIELDS
            or any(key.startswith('_people_') or key.endswith(('_preset_target', '_preset_owner', '_preset_requested')) for key in saved_fields)):
        raise ValueError('Mixed decoration preset history contains runtime or parallel portrait state')
    states = marker['current_states']
    if (type(states) is not dict or set(states) != {'before', 'after'}
            or any(type(state) is not dict or set(state) != set(saved_fields) for state in states.values())):
        raise ValueError('Mixed decoration preset history lacks complete durable current states')
    digests = {side: stable(state) for side, state in states.items()}
    if marker['before_graph_sha256'] == marker['after_graph_sha256'] and digests['before'] == digests['after']:
        raise ValueError('Mixed decoration preset history cannot manufacture a complete no-op')
    _changes(entry, marker); _targets(entry.get('targets'), marker)
    _evidence(entry, marker)
    dependencies_ = marker['dependencies']
    if type(dependencies_) is not list or len(dependencies_) != len(ids): raise ValueError('Mixed decoration preset history lacks every member input fence')
    seen = set()
    for item in dependencies_:
        if type(item) is not dict or set(item) != {'document_id', 'source_proof', 'before', 'after'}:
            raise ValueError('Malformed mixed preset member dependency')
        doc = P.token(item['document_id']); proof = SOURCE.check_row_proof(item['source_proof'])
        if doc not in ids or doc in seen: raise ValueError('Mixed decoration preset dependencies changed membership')
        seen.add(doc)
        matches = [target for target in entry['targets'].values() if target['document_id'] == doc]
        if len(matches) != 1 or matches[0]['source_proof'] != proof: raise ValueError('Mixed decoration preset member source changed')
        for side in ('before', 'after'):
            value = item[side]
            if type(value) is not dict or set(value) != {'context_sha256', 'state_sha256'}: raise ValueError('Missing mixed preset dependency fence')
            for digest in value.values(): P.digest(digest)
            if doc == marker['current_document_id'] and value['state_sha256'] != digests[side]:
                raise ValueError('Mixed decoration preset current history differs from its actual durable recipe')
        if doc != marker['current_document_id'] and item['before']['state_sha256'] != item['after']['state_sha256']:
            raise ValueError('Mixed decoration preset history cannot replace a sibling recipe, crop or repair')
    return marker


def prepare(engine, review, plans, targets, *, current_before, current_after, modules, ack):
    from .people_graph_patch import between
    if set(plans) != {'project'}: raise ValueError('Mixed decoration preset history requires its original project owner')
    from .face_decoration_preset_alias_review import checked, acknowledgment
    from .face_decoration_preset_alias_transaction import bank
    review = checked(review); ack = acknowledgment(ack, review)
    plan = plans['project']; current = P.token(review['visual']['document_id']); fields = state_fields(engine)
    if coverage_digest(modules) != review['applies_sha256']:
        raise ValueError('Mixed decoration preset selected modules changed after review')
    assets = bank(engine); BANK.check_store(assets)
    if review['before_bank_sha256'] != coverage_digest(assets):
        raise ValueError('Mixed decoration preset immutable bank changed since complete image review')
    from .face_decoration_preset_alias_authority import mixed_changes
    refs = deepcopy(plan['reviewed_face_refs'])
    mixed_changes(plan['before'], plan['candidate'], refs, selected_ref=review['face_ref'], modules=modules, assets=assets)
    keys = {descriptor['content_sha256'] for face in plan['before']['faces'].values()
            if face['asset_sha256'] == review['face_ref']['asset_sha256'] for descriptor in face['local_assets'].values()}
    if not keys <= set(assets): raise ValueError('Mixed decoration history lost referenced immutable support')
    marker = {'version': 1, **{key: review[key] for key in ('review_sha256', 'preset_sha256', 'applies_sha256', 'face_ref')},
        'selected_modules': list(modules), 'current_document_id': current,
        'reviewed_face_refs': refs, 'ack': deepcopy(ack), 'ack_sha256': coverage_digest(ack),
        'before_bank_sha256': review['before_bank_sha256'], 'coverage': deepcopy(review['coverage']),
        'support_assets': {key: deepcopy(assets[key]) for key in sorted(keys)},
        'document_ids': sorted(member['visual']['document_id'] for member in review['members']),
        'asset_sha256': review['face_ref']['asset_sha256'], 'before_graph_sha256': graph_digest(plan['before']),
        'after_graph_sha256': graph_digest(plan['candidate']), 'state_fields': fields,
        'current_states': {'before': project_state(current_before, fields), 'after': project_state(current_after, fields)}, 'dependencies': []}
    for member in review['members']:
        visual = member['visual']; doc = visual['document_id']
        matches = [target for target in targets.values() if target.get('document_id') == doc]
        found = engine._document_versions().find(engine._docs, doc)
        if (found is None or len(matches) != 1 or matches[0]['path'] != member['path']
                or str(matches[0]['revision']) != visual['revision'] or matches[0]['source_proof'] != visual['source_proof']):
            raise ValueError('Mixed decoration preset history differs from its exact reviewed inputs')
        row = found[1]; before = current_before if doc == current else row['state']; after = current_after if doc == current else before
        for state in (before, after): SOURCE.verify_row({**row, 'state': state}, visual['source_proof'])
        marker['dependencies'].append({'document_id': doc, 'source_proof': deepcopy(visual['source_proof']),
            'before': dependencies(engine, row, before, plan['before'], fields),
            'after': dependencies(engine, row, after, plan['candidate'], fields)})
    entry = {'ops': ['lnx.people_graph.v1'], 'people_changes': [], 'policy': 'protected_scoped_graph', 'targets': targets,
        'people_scoped_changes': [{'scope': 'project', 'document_id': plan['row']['document_id'],
            'changes': between(plan['before'], plan['candidate'])}], KEY: marker}
    check(entry); require_assets(marker, assets, plan['before'])
    return marker


def targets(engine, marker, graph, *, advance=True):
    """Exact closure also when only the current document recipe changes."""
    from .face_decoration_support_alias_history import _members
    members = _members(engine, marker, graph, advance=advance); result = {}
    for row, state, proof, version in members:
        index = next(index for index, item in enumerate(engine._docs) if item is row)
        result[str(index)] = {'path': row['path'], 'document_id': version.document_id, 'revision': version.revision,
            'asset_sha256': proof['asset_sha256'], 'people_scope': 'project', 'source_proof': proof,
            'reviewed_face_refs': deepcopy(marker['reviewed_face_refs'])}
    _targets(result, marker)
    return result


def verify_restore(engine, entry, plans, actual_targets, *, redo, advance=True):
    marker = check(entry)
    if marker is None: return
    from .face_style_alias_review import verify_dormant
    from .people_graph_owner import affected_assets
    if set(plans) != {'project'} or state_fields(engine) != marker['state_fields']:
        raise ValueError('Mixed decoration preset history changed its graph owner or durable state contract')
    plan = plans['project']; expected = 'before' if redo else 'after'; result = 'after' if redo else 'before'
    from .face_decoration_preset_alias_transaction import bank
    assets = bank(engine); require_assets(marker, assets, plan['before']); require_assets(marker, assets, plan['candidate'])
    from .face_decoration_preset_alias_authority import mixed_changes
    mixed_changes(plan['before'], plan['candidate'], marker['reviewed_face_refs'],
                  selected_ref=marker['face_ref'], modules=marker['selected_modules'], assets=assets)
    face = plan['before']['faces'].get(marker['face_ref']['face_instance_id'])
    if (plan['row']['document_id'] != marker['current_document_id'] or face is None
            or P.face_ref(face) != marker['face_ref'] or not face['enabled'] or face['evidence']['status'] != 'verified'):
        raise ValueError('Mixed decoration preset history changed its reviewed source observation or original current document')
    if (graph_digest(plan['before']) != marker[expected + '_graph_sha256']
            or graph_digest(plan['candidate']) != marker[result + '_graph_sha256']
            or not affected_assets(plan['before'], plan['candidate']) <= {marker['asset_sha256']}):
        raise ValueError('Mixed decoration preset complete graph changed; protected replay refused')
    _targets(actual_targets, marker)
    closure = targets(engine, marker, plan['before'], advance=advance)
    if {item['document_id']: item for item in closure.values()} != {item['document_id']: item for item in actual_targets.values()}: raise ValueError('Mixed decoration preset exact alias closure changed during preparation')
    verify_dormant(engine, plan['row'], {marker['asset_sha256']})
    by_document = {item['document_id']: item for item in marker['dependencies']}
    for target in actual_targets.values():
        row = engine._document_versions().find(engine._docs, target['document_id'])[1]
        state = engine._people_preset_capture() if row is V.current_row(engine) else row['state']
        item = by_document[target['document_id']]
        restored = {**state, **marker['current_states'][result]} if target['document_id'] == marker['current_document_id'] else state
        if (target['source_proof'] != item['source_proof']
                or dependencies(engine, row, state, plan['before'], marker['state_fields']) != item[expected]
                or dependencies(engine, row, restored, plan['candidate'], marker['state_fields']) != item[result]):
            raise ValueError('Mixed decoration preset source, repair, crop, recipe, analysis or support changed; protected replay refused')
        SOURCE.verify_row({**row, 'state': restored}, item['source_proof'])


def encode_states(entry, assets):
    """Only this new marker gains a codec; legacy ledger formats are unchanged."""
    marker = check(entry)
    if marker is None: return entry
    from .project import encode
    out = deepcopy(entry); dropped = []
    value = encode(marker['current_states'], assets, dropped, 'face_decoration_preset_alias.current_states')
    if dropped: raise ValueError('Mixed decoration preset current history cannot be saved lossily')
    out[KEY]['current_states'] = {'codec': 'project.v1', 'value': value}
    return out


def decode_states(entry, assets):
    if KEY not in entry: return entry
    from .project import decode
    from .repair_record import RepairOp
    from .vram import LightOp
    out = deepcopy(entry); marker = out[KEY]
    value = marker.get('current_states') if type(marker) is dict else None
    if type(value) is not dict or set(value) != {'codec', 'value'} or value['codec'] != 'project.v1':
        raise ValueError('Saved mixed preset current history lacks its canonical codec')
    dropped = []; marker['current_states'] = decode(value['value'], assets, dropped,
        'face_decoration_preset_alias.current_states', dc_types={'RepairOp': RepairOp, 'LightOp': LightOp})
    if dropped: raise ValueError('Saved mixed preset current history cannot be restored lossily')
    check(out)
    return out


def status_summary(entry):
    marker = check(entry)
    return None if marker is None else {key: deepcopy(marker[key]) for key in (
        'version', 'review_sha256', 'preset_sha256', 'applies_sha256', 'current_document_id', 'selected_modules')} | {
        'member_count': len(marker['document_ids'])}


def validate_project_assets(entry, project):
    marker = check(entry)
    if marker is not None: require_assets(marker, project.get('people_support_assets'))
