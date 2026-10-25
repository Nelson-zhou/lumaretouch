# SPDX-License-Identifier: GPL-3.0-or-later
"""Canonical graph/history/project hooks; no copied graph or semantic producer."""
from copy import deepcopy
from . import hair_unification_state as S, hair_unification_assets as A
from . import hair_colour_assets as HAIR, hair_colour_analysis as ANALYSIS, hair_colour_evidence as EVIDENCE
from . import people_state as P, people_resolver as R

KEY = 'hair_unification_assets'


def store(engine):
    return engine.__dict__.setdefault('_hair_unification_assets', {})


def recipe(state, face_id):
    resolved = R.resolve(state, face_id, {S.OP: {'/amount': 0.0}})
    return R.materialize(resolved, S.OP, S.neutral(), S.check)


def needed(state, asset):
    return any(face['asset_sha256'] == asset and face['enabled'] and S.active(recipe(state, key))
               for key, face in state['faces'].items())


def validate_leaf(path, value):
    if path != '/amount': raise ValueError('Unknown hair-unification scalar; samples cannot enter recipe leaves')
    S.check({'version': 1, 'amount': value})


def validate_graph(state):
    state = P.check(state)
    for row in state['overrides']:
        if row['operation_id'] != S.OP: continue
        validate_leaf(row['parameter_path'], row['value'])
        if row['scope'] != 'face':
            raise ValueError('Hair unification currently requires an individually reviewed current-photo face; cohort/batch inheritance is unsupported')
    for key in state['faces']: recipe(state, key)
    return state


def validate(project, *, allowed=True):
    """Validate all graph/history pointers using the nearest canonical owned bank."""
    if type(project) is not dict: raise ValueError('Invalid hair-unification project/context')
    def visit(value, bank, hair, evidence):
        if type(value) is dict:
            if not allowed and (KEY in value or value.get('operation_id') == S.OP
                                or S.KIND in value.get('local_assets', {})):
                raise ValueError('This project version cannot silently ignore hair-unification ownership')
            bank = value.get(KEY, bank); hair = value.get('hair_colour_assets', hair)
            evidence = value.get(EVIDENCE.KEY, evidence)
            if KEY in value:
                bank = A.check_store(bank)
                for record in bank.values(): A.verify_record(record, hair, evidence)
            graph = value.get('people_graph')
            if graph is not None:
                validate_graph(graph); A.verify_graph(graph, bank, hair, evidence)
            if 'face_instance_id' in value and 'local_assets' in value and S.KIND in value['local_assets']:
                graph = P.empty(); graph['faces'][value['face_instance_id']] = value
                A.resolve(P.check(graph), bank, P.face_ref(value), hair)
            for key, child in value.items():
                if key not in (KEY, 'hair_colour_assets', EVIDENCE.KEY): visit(child, bank, hair, evidence)
        elif type(value) in (list, tuple):
            for child in value: visit(child, bank, hair, evidence)
    root = A.check_store(project.get(KEY, {}))
    visit(project, root, project.get('hair_colour_assets', {}), project.get(EVIDENCE.KEY, {}))
    return root


def save(engine, project):
    project[KEY] = A.verify_graph(engine._people_owner().snapshot(), store(engine),
        engine.__dict__.get('_hair_colour_assets', {}), engine.__dict__.get('_hair_colour_evidence', {}))


def load(engine, project):
    engine._hair_unification_assets = validate(project)
    for key in ('_hair_unification_reviews', '_hair_unification_reference', '_hair_unification_receipts', '_hair_unification_uncertain'):
        engine.__dict__.pop(key, None)


def preview_kwargs(engine, state=None):
    state = engine._people_owner().snapshot() if state is None else state
    binding = engine._people_source()
    # Own kwargs never overwrite canonical shared hair_evidence/source_path.
    # Shared forwarding calls shared_preview when this operator is active.
    if needed(state, binding['sha256']):
        EVIDENCE.current(engine, binding)
    return {'hair_unification_assets': A.check_store(store(engine))}


def shared_preview(engine, state=None):
    state = engine._people_owner().snapshot() if state is None else state
    if not needed(state, engine._people_source()['sha256']): return {}
    from .creative_derived_source import record, verify
    binding = engine._people_source(); derived = record(engine) is not None
    if derived: verify(binding, engine)
    return {'hair_evidence': EVIDENCE.current(engine, binding),
            'hair_source_path': None if derived else engine._doc_path}


def capture(engine, snapshot, precompute, binding, *, source_path):
    snapshot[KEY] = A.check_store(store(engine))
    if not needed(snapshot['state'], snapshot['asset_sha256']): return snapshot
    evidence = EVIDENCE.current(engine, binding, precompute)
    snapshot['hair_colour_evidence'] = ANALYSIS.freeze(evidence)
    snapshot['hair_colour_source_path'] = source_path
    from .local_mask_state import file_stamp, source_digest
    if not source_path: raise ValueError('Original hair-unification export needs the exact source path')
    stamp = file_stamp(source_path)
    if source_digest(source_path) != binding['sha256'] or file_stamp(source_path) != stamp:
        raise ValueError('Hair-unification source changed during export capture')
    snapshot['hair_colour_source_stamp'] = list(stamp)
    return snapshot


def capture_derived(engine, state, snapshot, precompute, source):
    from .creative_derived_source import verify, verify_precompute
    verify(source, state); verify_precompute(state, precompute)
    snapshot[KEY] = A.check_store(store(engine))
    if needed(snapshot['state'], source['sha256']):
        evidence = EVIDENCE.for_source(engine.__dict__.get('_hair_colour_evidence', {}), source)
        if evidence is None:
            evidence = ANALYSIS.capture(precompute, source)
        snapshot['hair_colour_evidence'] = ANALYSIS.freeze(evidence)
    snapshot['hair_colour_source_path'] = None; snapshot['hair_colour_source_stamp'] = None
    validate_derived(snapshot['state'], snapshot[KEY], snapshot.get('hair_colour_assets', {}),
                     snapshot.get('hair_colour_evidence'), source)
    return snapshot


def validate_derived(state, assets, hair_assets, evidence, source):
    source = A.source(source)
    if needed(state, source['sha256']):
        ANALYSIS.check(evidence, source)
    for face in state['faces'].values():
        if face['asset_sha256'] != source['sha256'] or S.KIND not in face['local_assets']: continue
        record = A.resolve(state, assets, P.face_ref(face), hair_assets)
        support = A.verify_record(record, hair_assets)
        if record['source'] != source:
            raise ValueError('Derived hair-unification samples belong to another effective source')
        if any(obj['kind'] == 'prompted' for obj in support['support']['objects']):
            raise ValueError('Derived hair-unification cannot acquire original-file prompted selection')
        if S.active(recipe(state, face['face_instance_id'])) and EVIDENCE.identity(evidence) != record['semantic_evidence_sha256']:
            raise ValueError('Derived hair-unification evidence differs from sample review')


def kwargs(snapshot):
    from .hair_colour_project import verify_snapshot
    if snapshot.get('creative_source') is not None:
        validate_derived(snapshot['state'], snapshot.get(KEY, {}), snapshot.get('hair_colour_assets', {}),
                         snapshot.get('hair_colour_evidence'), snapshot['creative_source'])
        if snapshot.get('hair_colour_source_path') is not None:
            raise ValueError('Derived hair-unification cannot use an original file path')
    else:
        verify_snapshot(snapshot)
    return {'hair_unification_assets': A.check_store(snapshot.get(KEY, {}))}


def changed_assets(before, candidate):
    def signature(state, key):
        face = state['faces'].get(key)
        if face is None: return None
        rows = [row for row in state['overrides'] if row['operation_id'] == S.OP and row['scope'] == 'face' and row['target_id'] == key]
        asset = face['local_assets'].get(S.KIND)
        if not rows and asset is None: return None
        return sorted(rows, key=lambda row: row['parameter_path']), asset, P.face_ref(face), face['enabled']
    changed = set()
    for key in set(before['faces']) | set(candidate['faces']):
        if signature(before, key) != signature(candidate, key):
            changed.update(graph['faces'][key]['asset_sha256'] for graph in (before, candidate) if key in graph['faces'])
    return changed


def require_unreviewed_transition(before, candidate):
    """Hook generic scalar patch/preset paths; clear remains native-independent."""
    for key, face in candidate['faces'].items():
        new = recipe(candidate, key)
        old = recipe(before, key) if key in before['faces'] else S.neutral()
        if S.active(new) and (new != old or (key in before['faces'] and
                face['local_assets'].get(S.KIND) != before['faces'][key]['local_assets'].get(S.KIND))):
            raise ValueError('Hair-unification activation/amount changes require the exact complete image review, not a generic patch')


def require_scope(engine, before, candidate, *, row=None):
    validate_graph(candidate)
    changed = changed_assets(before, candidate)
    if not changed: return
    from . import virtual_copy_people as V, creative_derived_source as SOURCE
    actual = V.current_row(engine) if row is None else row
    if actual is not V.current_row(engine):
        raise ValueError('Hair unification currently supports only the current photograph, not batch/cohort targets')
    source_row = {**actual, 'state': engine._people_preset_capture()}
    source = SOURCE.row_asset(source_row)
    if changed - {source}:
        raise ValueError('Hair-unification samples are never copied across photographs or linked people')
    aliases = [other for other in V.scope_rows(engine, actual)
               if SOURCE.row_asset(source_row if other is actual else other) == source]
    if len(aliases) != 1 or aliases[0] is not actual:
        raise ValueError('Hair unification requires complete per-document alias review, which this current-photo slice does not yet support')
    from .face_style_alias_review import verify_dormant
    verify_dormant(engine, actual, changed)


# Scope and exact publication authority remain operation-local. A generic patch
# cannot manufacture this admission merely by targeting the current photograph.
def _active_changes(before, candidate):
    changes = []
    for key, face in candidate['faces'].items():
        new = recipe(candidate, key)
        if not face['enabled'] or not S.active(new): continue
        old_face = before['faces'].get(key)
        old = recipe(before, key) if old_face is not None else S.neutral()
        if (old_face is None or not old_face['enabled'] or old != new
                or P.face_ref(old_face) != P.face_ref(face)
                or old_face['local_assets'].get(S.KIND) != face['local_assets'].get(S.KIND)):
            changes.append(key)
    return changes


def require_transition(engine, before, candidate, *, row=None):
    require_scope(engine, before, candidate, row=row)
    if not _active_changes(before, candidate): return
    authority = engine.__dict__.get('_hair_unification_admission')
    if (not authority or authority['before'] != before or authority['candidate'] != candidate
            or authority['bank_sha256'] != A.digest(store(engine)) or authority['review_token'] is None):
        raise ValueError('Active hair-unification changes require the exact presented complete image review')


from contextlib import contextmanager


@contextmanager
def reviewed_transition(engine, before, candidate, bank, review_token):
    if '_hair_unification_admission' in engine.__dict__:
        raise ValueError('Hair-unification publication cannot nest another admission')
    if review_token is not None: P.digest(review_token)
    engine._hair_unification_admission = {'before': deepcopy(before), 'candidate': deepcopy(candidate),
        'bank_sha256': A.digest(bank), 'review_token': review_token}
    try:
        yield
    finally:
        engine.__dict__.pop('_hair_unification_admission', None)
