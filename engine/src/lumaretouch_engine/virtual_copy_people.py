"""Document-scoped portrait ownership without changing physical source evidence.

Established original documents retain their shared graph and confirmed links.
A virtual copy owns a deep-frozen graph and retained stores. Newly imported
byte-identical independent roots start with a private empty portrait recipe. Face
references and SHA-256 values still identify the original measured source; the
logical document context, not a fabricated digest, provides edit isolation.
"""
from copy import deepcopy
from . import people_state as S
from .people_graph_owner import PeopleGraphOwner

KEY = 'people_context'
RUNTIME = '_virtual_people_context'
PROJECT = 'project'
FIELDS = {
    'people_support_assets': '_people_support',
    'people_landmarks': '_people_landmarks',
    'people_cursors': '_people_cursors',
    'people_targets': '_people_targets',
    'hair_colour_assets': '_hair_colour_assets',
    'hair_colour_evidence': '_hair_colour_evidence',
}


def is_copy(row):
    return row is not None and row.get('copy_number', 0) > 0


def is_private(row):
    return row is not None and (is_copy(row) or KEY in row or RUNTIME in row)


def scope(row):
    # A fresh unclassified import has no right to inherit an older shared graph
    # merely because its uninspected source might contain the same bytes.
    return row['document_id'] if is_private(row) or (row is not None and row.get('_people_new_import')) else PROJECT


def current_row(engine):
    index = getattr(engine, '_doc_index', -1)
    rows = getattr(engine, '_docs', [])
    return rows[index] if 0 <= index < len(rows) else None


def check(value):
    required = {'version', 'people_graph', *FIELDS}
    if type(value) is not dict or set(value) != required or type(value['version']) is not int or value['version'] != 1:
        raise ValueError('Invalid virtual-copy portrait context')
    from .people_project import validate_records
    from .hair_colour_project import validate
    validate_records(value)
    validate(value)
    graph = S.check(value['people_graph'])
    for key in ('people_cursors', 'people_targets'):
        if type(value[key]) is not dict or len(value[key]) > 8192:
            raise ValueError('Invalid virtual-copy portrait cursors')
        for asset in value[key]: S.digest(asset)
    for asset, face_id in value['people_cursors'].items():
        if face_id is not None:
            S.token(face_id)
            face = graph['faces'].get(face_id)
            if face is not None and face['asset_sha256'] != asset:
                raise ValueError('Portrait cursor belongs to another source')
    for target in value['people_targets'].values():
        if type(target) is not dict or target.get('scope') not in S.SCOPES:
            raise ValueError('Invalid portrait editing target')
        S.token(target.get('target_id'))
        if target['scope'] == 'face': S.check_ref(target.get('face_ref'))
    return deepcopy(value)


def _runtime(value):
    checked = check(value)
    return {'owner': PeopleGraphOwner(checked['people_graph']),
            'analyses': {}, **{key: checked[key] for key in FIELDS}}


def _snapshot(context):
    return {'version': 1, 'people_graph': context['owner'].snapshot(),
            **{key: deepcopy(context[key]) for key in FIELDS}}


def _project(engine):
    context = engine.__dict__.get('_people_project_context')
    if context is None:
        context = {'owner': engine.__dict__.get('_people_graph_owner') or PeopleGraphOwner(),
                   'analyses': engine.__dict__.get('_people_analyses', {}),
                   **{key: engine.__dict__.get(field, {}) for key, field in FIELDS.items()}}
        engine._people_project_context = context
    return context


def _remember_active(engine):
    context = engine.__dict__.get('_people_active_context')
    if context is None: return
    context['owner'] = engine._people_graph_owner
    context['analyses'] = engine.__dict__.get('_people_analyses', {})
    for key, field in FIELDS.items(): context[key] = engine.__dict__.get(field, {})


def _ensure_scope(engine, row, *, hash_source=True):
    if row is None or is_copy(row) or not row.get('_people_new_import'): return
    if KEY in row:
        row['_people_new_import'] = False
        return
    asset = row.get('_people_source_sha256') or (row.get('fingerprint') or {}).get('sha256')
    if asset is None and hash_source:
        from .local_mask_state import source_digest
        asset = source_digest(row['path'])
    if asset is not None: S.digest(asset)
    source_id = row.get('source_asset_id')
    duplicate = any(other is not row and not is_copy(other)
                    and other.get('source_asset_id') != source_id
                    and (other.get('_people_source_sha256') or (other.get('fingerprint') or {}).get('sha256')) == asset
                    for other in engine._docs) if asset is not None else True
    graph = _project(engine)['owner'].snapshot()
    retained = (asset in graph['analysis_runs'] or any(face['asset_sha256'] == asset for face in graph['faces'].values())
                or any(item['scope'] == 'all_people' and item['target_id'] == asset for item in graph['overrides'])
                or any(item['asset_sha256'] == asset for item in graph['unresolved_legacy']))
    if duplicate or retained:
        # New independent imports start unedited. Copying a face/link/support
        # from a byte-identical root would invent a cross-document association.
        row[KEY] = {'version': 1, 'people_graph': S.empty(), **{key: {} for key in FIELDS}}
    if asset is not None: row['_people_source_sha256'] = asset
    row['_people_new_import'] = False


def _context(engine, row):
    _ensure_scope(engine, row)
    if not is_private(row): return _project(engine)
    context = row.get(RUNTIME)
    if context is None:
        if KEY not in row:
            raise ValueError('Virtual copy is missing its independent portrait recipe')
        context = _runtime(row[KEY])
        row[RUNTIME] = context
    return context


def remember(engine):
    """Call while remembering the active row, before changing document selection."""
    _remember_active(engine)
    row = engine.__dict__.get('_people_scope_row')
    if is_private(row): row[KEY] = _snapshot(_context(engine, row))


def activate(engine, row):
    """Install exact document ownership before open/render/history operations."""
    _remember_active(engine)
    context = _context(engine, row)
    changed = engine.__dict__.get('_people_active_context') is not context
    engine._people_active_context = context
    engine._people_scope_row = row
    engine._people_graph_owner = context['owner']
    engine._people_analyses = context['analyses']
    for key, field in FIELDS.items(): setattr(engine, field, context[key])
    if changed:
        engine._people_analysis_key = None
        engine._people_render_enabled = False
        engine._people_path = None
        engine._people_staged = None
    return context['owner']


def owner(engine):
    row = current_row(engine)
    if engine.__dict__.get('_people_active_context') is None or engine.__dict__.get('_people_scope_row') is not row:
        return activate(engine, row)
    return engine._people_graph_owner


def inherit(engine, source, target):
    """Create a copy's initial portrait recipe; never inherit undo or fences."""
    _remember_active(engine)
    value = _snapshot(_context(engine, source))
    target.pop(RUNTIME, None)
    target['_people_new_import'] = False
    target[KEY] = check(value)
    target['undo'] = []
    target['redo'] = []
    target['_history_owned'] = True
    return target


def encode(row):
    """Return JSON-safe private context, or None for shared project originals."""
    if not is_private(row): return None
    value = _snapshot(row[RUNTIME]) if RUNTIME in row else row.get(KEY)
    return check(value)


def decode(row, record):
    """Validate restored context before replacing any live engine documents."""
    row.pop(RUNTIME, None)
    if is_copy(row) or KEY in record:
        row[KEY] = check(record.get(KEY))
    row['_people_new_import'] = False
    return row


def row_context(engine, row):
    _remember_active(engine)
    return _snapshot(_context(engine, row))


def peek_graph(engine, row):
    """Query-only graph lookup: no source hashing, classification, or new owner.

    None means a fresh independent import has not established its portrait
    scope yet. The library must not borrow another source's people facts.
    """
    if row.get('_people_new_import') and not is_private(row): return None
    _remember_active(engine)
    if is_private(row):
        if RUNTIME in row: return row[RUNTIME]['owner'].snapshot()
        value = row.get(KEY)
        return None if value is None else S.check(value['people_graph'])
    context = engine.__dict__.get('_people_project_context')
    if context is not None: return context['owner'].snapshot()
    graph_owner = engine.__dict__.get('_people_graph_owner')
    return S.empty() if graph_owner is None else graph_owner.snapshot()


def row_snapshot(engine, row):
    _remember_active(engine)
    return _context(engine, row)['owner'].snapshot()


def row_owner(engine, row):
    _remember_active(engine)
    return _context(engine, row)['owner']


def scope_rows(engine, row=None):
    row = current_row(engine) if row is None else row
    wanted = scope(row)
    return [item for item in engine._docs if scope(item) == wanted]


def export_context(engine, state, source_path, context=None):
    if context is not None: return check(context)
    # Parked preparation uses exact state-object identity, not the shared path.
    matches = [row for row in engine._docs if row.get('state') is state]
    if len(matches) == 1: return row_context(engine, matches[0])
    current = current_row(engine)
    if current is not None and current.get('path') == source_path:
        return row_context(engine, current)
    matches = [row for row in engine._docs if row.get('path') == source_path]
    if len(matches) == 1: return row_context(engine, matches[0])
    if len(matches) > 1:
        raise ValueError('Export needs an explicit virtual-copy portrait context')
    return _snapshot(_project(engine))


def view(engine, context):
    """Read-only export view with exact retained stores, not live selection changes."""
    from copy import copy
    result = copy(engine)
    result.__dict__ = dict(engine.__dict__)
    local = {'owner': PeopleGraphOwner(context['people_graph']), 'analyses': {},
             **{key: context[key] for key in FIELDS}}
    result._people_graph_owner = local['owner']
    result._people_active_context = local
    result._people_scope_row = current_row(result)
    result._people_project_context = local
    result._people_analyses = {}
    for key, field in FIELDS.items(): setattr(result, field, context[key])
    return result


def save_project(engine, project):
    """Keep legacy root graph, retaining immutable evidence for all graph scopes."""
    remember(engine)
    for row in engine._docs:
        # Project build already fingerprinted available originals. Do not read
        # more source files here; a new unavailable source is isolated safely.
        _ensure_scope(engine, row, hash_source=False)
    stored = {row.get('document_id'): row for row in project.get('docs', [])}
    for row in engine._docs:
        if is_private(row) and row.get('document_id') in stored:
            stored[row['document_id']][KEY] = encode(row)
    base = _snapshot(_project(engine))
    contexts = [base] + [row_context(engine, row) for row in engine._docs if is_private(row)]
    # Existing validators traverse the full saved project. The top-level banks
    # therefore retain the union, while active recipes remain in their owners.
    # Landmark keys include face/reanalysis revision, not document identity.
    # Their banks stay in their exact contexts rather than being unioned: two
    # independent copies may explicitly reanalyse the same retained face.
    for key in ('people_support_assets', 'hair_colour_assets', 'hair_colour_evidence'):
        merged = {}
        for context in contexts:
            for identity, value in context[key].items():
                if identity in merged and merged[identity] != value:
                    raise ValueError('Conflicting immutable portrait evidence across virtual copies')
                merged[identity] = deepcopy(value)
        base[key] = merged
    for key in ('people_graph', 'people_support_assets', 'people_landmarks', 'people_cursors',
                'hair_colour_assets', 'hair_colour_evidence'):
        project[key] = base[key]
    from .hair_colour_project import validate
    validate(project)


def loaded(engine):
    """Call after loading top-level stores, before selecting a project row."""
    for key in ('_people_project_context', '_people_active_context', '_people_scope_row'):
        engine.__dict__.pop(key, None)
    _project(engine)
