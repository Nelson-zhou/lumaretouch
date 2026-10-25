# SPDX-License-Identifier: GPL-3.0-or-later
"""Hair-volume admission on the canonical graph/support bank. AUTHORED / UNRUN.

No parallel graph, asset store, undo stack, semantic inference or source identity.
Current-photo face intent only; shared/cohort/alias activation remains refused.
"""
from contextlib import contextmanager
from copy import deepcopy
from . import people_state as P, people_resolver as R
from . import hair_volume_state as S, hair_volume_support as A
from . import hair_colour_evidence as EVIDENCE, hair_colour_analysis as ANALYSIS

KEY = 'people_support_assets'
LEAVES = {'/crown/amount': 0., '/sides/linked': True, '/sides/left': 0., '/sides/right': 0.}


def store(engine):
    return engine.__dict__.setdefault('_people_support', {})


def _bank(value):
    from .people_support_assets import check_store
    return A.check_store(check_store(value))


def recipe(state, face_id):
    return R.materialize(R.resolve(state, face_id, {S.OPERATION_ID: LEAVES}),
                         S.OPERATION_ID, S.neutral(), S.check)


def recipes(state, asset):
    return {key: recipe(state, key) for key, face in state['faces'].items() if face['asset_sha256'] == asset}


def needed(state, asset):
    return any(state['faces'][key]['enabled'] and S.active(value) for key, value in recipes(state, asset).items())


def validate_leaf(path, value):
    if path not in LEAVES:
        raise ValueError('Hair volume accepts only independent crown/side scalar leaves, never geometry or consent')
    trial = S.neutral()
    if path == '/sides/linked':
        trial['sides']['linked'] = value
    else:
        group, name = path[1:].split('/')
        trial['sides']['linked'] = False
        trial[group][name] = value
    S.check(trial)


def validate_graph(state):
    state = P.check(state)
    for row in state['overrides']:
        if row['operation_id'] != S.OPERATION_ID:
            continue
        validate_leaf(row['parameter_path'], row['value'])
        if row['scope'] != 'face':
            raise ValueError('Hair volume has no group, linked-person, all-people or batch inheritance admission')
    for key in state['faces']:
        recipe(state, key)
    return state


def set_recipe(state, face_id, value):
    """Write the entire validated independent family, never materialize half a lock."""
    value = S.check(value)
    if recipe(state, face_id) == value:
        return validate_graph(state)  # Preserve sparse recipes and exact no-op revision.
    out = state
    for path in LEAVES:
        group, name = path[1:].split('/')
        out = P.set_override(out, 'face', face_id, S.OPERATION_ID, path, value[group][name])
    return validate_graph(out)


def _pointer(face, bank):
    """History face fragments lack a complete census; validate ownership, not a new census."""
    descriptor = face.get('local_assets', {}).get(S.SUPPORT_KIND)
    if descriptor is None:
        return
    ref = P.check_ref(P.face_ref(face)); key = descriptor.get('content_sha256')
    record = bank.get(key)
    if (record is None or A.digest(record) != key or record['face_ref'] != ref
            or descriptor != {'owner': ref, 'kind': S.SUPPORT_KIND, 'content_sha256': key}):
        raise ValueError('Saved hair-volume history lost its immutable exact-owner support')
    A.check_record(record)


def validate_owned_graph(state, bank, evidence=None):
    state = validate_graph(state)
    A.validate_project(state, bank, evidence)
    for key, face in state['faces'].items():
        value = recipe(state, key)
        if face['enabled'] and S.active(value):
            support = A.resolve(state, bank, P.face_ref(face))
            if support is None:
                raise ValueError('Active hair-volume intent lost its reviewed per-region source support')
            A.support_vector(support, value)
    return state


def validate(project, *, allowed=True):
    """Validate active/private/history references with their nearest owned bank."""
    if type(project) is not dict:
        raise ValueError('Invalid hair-volume project/context')
    def visit(value, bank, evidence):
        if type(value) is dict:
            if not allowed and (value.get('operation_id') == S.OPERATION_ID
                    or value.get('target') == S.SUPPORT_KIND
                    or S.SUPPORT_KIND in value.get('local_assets', {})):
                raise ValueError('This project version cannot silently discard hair-volume intent or support')
            bank = value.get(KEY, bank); evidence = value.get(EVIDENCE.KEY, evidence)
            if KEY in value:
                bank = _bank(bank); A.validate_project(P.empty(), bank, evidence)
                if not allowed and any(record['row'].get('target') == S.SUPPORT_KIND for record in bank.values()):
                    raise ValueError('This project version cannot silently discard retained hair-volume support')
            for name in ('people_graph', '_people_state'):
                if name in value:
                    validate_owned_graph(value[name], bank, evidence)
            if value.get('_people_history') is not None:
                from .people_document_history import scoped_state
                validate_owned_graph(scoped_state(value['_people_history']), bank, evidence)
            if 'face_instance_id' in value and 'local_assets' in value:
                _pointer(value, bank)
            if value.get('operation_id') == S.OPERATION_ID and 'parameter_path' in value:
                validate_leaf(value['parameter_path'], value['value'])
                if value.get('scope') != 'face':
                    raise ValueError('Saved hair-volume intent cannot acquire cohort or alias scope')
            for name, child in value.items():
                if name not in (KEY, EVIDENCE.KEY):
                    visit(child, bank, evidence)
        elif type(value) in (list, tuple):
            for child in value:
                visit(child, bank, evidence)
    root = _bank(project.get(KEY, {}))
    A.validate_project(P.empty(), root, project.get(EVIDENCE.KEY, {}))
    visit(project, root, project.get(EVIDENCE.KEY, {}))
    return root


def save(engine, project):
    bank = _bank(store(engine))
    validate_owned_graph(engine._people_owner().snapshot(), bank, engine.__dict__.get('_hair_colour_evidence', {}))
    project[KEY] = bank


def load(engine, project):
    # The canonical people loader owns assignment of the shared support bank.
    validate(project)
    for name in ('reviews', 'reference', 'receipts', 'uncertain'):
        engine.__dict__.pop('_hair_volume_' + name, None)


def preview_kwargs(engine, state=None):
    return {'hair_volume_assets': _bank(store(engine))}


def shared_preview(engine, state=None):
    state = engine._people_owner().snapshot() if state is None else state
    binding = engine._people_source()
    if not needed(state, binding['sha256']):
        return {}
    from .creative_derived_source import record, verify
    derived = record(engine) is not None
    verify(binding, engine)
    return {'hair_evidence': EVIDENCE.current(engine, binding),
            'hair_source_path': None if derived else engine._doc_path}


def capture(engine, snapshot, precompute, binding, *, source_path):
    snapshot['support_assets'] = _bank(store(engine))
    if not needed(snapshot['state'], binding['sha256']):
        return snapshot
    from .local_mask_state import file_stamp, source_digest
    if not source_path:
        raise ValueError('Original hair-volume export needs its exact original source path')
    stamp = file_stamp(source_path)
    if source_digest(source_path) != binding['sha256'] or file_stamp(source_path) != stamp:
        raise ValueError('Original hair-volume source changed during immutable capture')
    evidence = EVIDENCE.current(engine, binding, precompute)
    snapshot.update(hair_colour_evidence=ANALYSIS.freeze(evidence),
                    hair_colour_source_path=source_path, hair_colour_source_stamp=list(stamp))
    return snapshot


def validate_derived(state, assets, evidence, source):
    source = A.source(source)
    if needed(state, source['sha256']):
        ANALYSIS.check(evidence, source)
    for key, face in state['faces'].items():
        if face['asset_sha256'] != source['sha256'] or S.SUPPORT_KIND not in face['local_assets']:
            continue
        record = A.resolve(state, assets, P.face_ref(face))
        if record['source'] != source:
            raise ValueError('Hair-volume support belongs to a different effective source')
        if face['enabled'] and S.active(recipe(state, key)):
            A.verify_evidence(record, evidence)
            A.support_vector(record, recipe(state, key))


def capture_derived(engine, state, snapshot, precompute, source):
    from .creative_derived_source import verify, verify_precompute
    verify(source, state); verify_precompute(state, precompute)
    snapshot['support_assets'] = _bank(store(engine))
    if needed(snapshot['state'], source['sha256']):
        evidence = EVIDENCE.for_source(engine.__dict__.get('_hair_colour_evidence', {}), source)
        if evidence is None:
            evidence = ANALYSIS.capture(precompute, source)
        snapshot['hair_colour_evidence'] = ANALYSIS.freeze(evidence)
    snapshot['hair_colour_source_path'] = None; snapshot['hair_colour_source_stamp'] = None
    validate_derived(snapshot['state'], snapshot['support_assets'], snapshot.get('hair_colour_evidence'), source)
    return snapshot


def kwargs(snapshot):
    result = {'hair_volume_assets': _bank(snapshot.get('support_assets', {}))}
    if not needed(snapshot['state'], snapshot['asset_sha256']):
        return result
    evidence = snapshot.get('hair_colour_evidence')
    if snapshot.get('creative_source') is not None:
        validate_derived(snapshot['state'], result['hair_volume_assets'], evidence, snapshot['creative_source'])
        if snapshot.get('hair_colour_source_path') is not None or snapshot.get('hair_colour_source_stamp') is not None:
            raise ValueError('Derived hair volume cannot borrow original-file pixels or provenance as its source')
    else:
        from .hair_colour_project import verify_snapshot
        if evidence is None:
            raise ValueError('Hair volume lacks frozen actual source hair evidence')
        verify_snapshot(snapshot)
    result.update(hair_evidence=ANALYSIS.freeze(evidence), hair_source_path=snapshot.get('hair_colour_source_path'))
    return result


def changed_assets(before, candidate):
    def signature(state, key):
        face = state['faces'].get(key)
        if face is None:
            return None
        value = recipe(state, key)
        support = face['local_assets'].get(S.SUPPORT_KIND)
        if not S.active(value) and support is None:
            return None
        return value, support, P.face_ref(face), face['evidence'], face['box'], face['manual'], face['enabled']
    changed = set()
    for key in set(before['faces']) | set(candidate['faces']):
        if signature(before, key) != signature(candidate, key):
            changed.update(graph['faces'][key]['asset_sha256'] for graph in (before, candidate) if key in graph['faces'])
    return changed


def require_scope(engine, before, candidate, *, row=None):
    validate_graph(candidate); changed = changed_assets(before, candidate)
    if not changed:
        return
    from . import virtual_copy_people as V, creative_derived_source as SOURCE
    actual = V.current_row(engine) if row is None else row
    if actual is None or actual is not V.current_row(engine):
        raise ValueError('Hair volume currently supports only the selected current photograph')
    current = {**actual, 'state': engine._people_preset_capture()}; source = SOURCE.row_asset(current)
    if changed - {source}:
        raise ValueError('Hair-volume support and review cannot transfer to another source or linked person')
    aliases = [other for other in V.scope_rows(engine, actual)
               if SOURCE.row_asset(current if other is actual else other) == source]
    if len(aliases) != 1 or aliases[0] is not actual:
        raise ValueError('Per-document hair-volume alias review is not supported in this current-photo slice')
    from .face_style_alias_review import verify_dormant
    verify_dormant(engine, actual, changed)


def _active_changes(before, candidate):
    def anatomy(state, asset):
        return [(key, P.face_ref(face), face['evidence'], face['box'], face['manual'])
                for key, face in sorted(state['faces'].items()) if face['asset_sha256'] == asset]
    for key, face in candidate['faces'].items():
        new = recipe(candidate, key)
        if not face['enabled'] or not S.active(new):
            continue
        old = before['faces'].get(key)
        if (old is None or not old['enabled'] or recipe(before, key) != new
                or P.face_ref(old) != P.face_ref(face)
                or old['local_assets'].get(S.SUPPORT_KIND) != face['local_assets'].get(S.SUPPORT_KIND)
                or anatomy(before, face['asset_sha256']) != anatomy(candidate, face['asset_sha256'])):
            yield key


def require_unreviewed_transition(before, candidate):
    validate_graph(candidate)
    if next(_active_changes(before, candidate), None) is not None:
        raise ValueError('Active hair-volume changes require a new exact complete-image review, not generic patches or presets')


def require_transition(engine, before, candidate, *, row=None):
    require_scope(engine, before, candidate, row=row)
    validate_owned_graph(candidate, store(engine))
    if next(_active_changes(before, candidate), None) is None:
        return
    authority = engine.__dict__.get('_hair_volume_admission')
    owner = engine._people_owner()
    if (not authority or authority['owner'] is not owner or authority['fence'] != owner.fence
            or authority['before'] != before or authority['candidate'] != candidate
            or authority['bank_sha256'] != A.digest(store(engine)) or authority['review_token'] is None):
        raise ValueError('Hair volume needs the exact presented full-image candidate before publication')


@contextmanager
def reviewed_transition(engine, before, candidate, bank, review_token):
    if '_hair_volume_admission' in engine.__dict__:
        raise ValueError('Hair-volume publication cannot nest another admission')
    if review_token is not None:
        P.digest(review_token)
    owner = engine._people_owner()
    if owner.snapshot() != before:
        raise ValueError('Hair-volume graph owner changed before publication admission')
    validate_owned_graph(candidate, _bank(bank))
    engine._hair_volume_admission = {'owner': owner, 'fence': owner.fence,
        'before': deepcopy(before), 'candidate': deepcopy(candidate),
        'bank_sha256': A.digest(bank), 'review_token': review_token}
    try:
        yield
    finally:
        engine.__dict__.pop('_hair_volume_admission', None)
