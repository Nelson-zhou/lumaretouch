# SPDX-License-Identifier: GPL-3.0-or-later
"""Strict graph/history admission for selected same-photo face matching. UNRUN.

No new graph, support bank, history owner, migration or portable reference. The
canonical people owner remains the sole publisher. A temporary exact admission
is usable only by the dedicated complete-image transaction.
"""
from contextlib import contextmanager
from copy import deepcopy

from . import people_state as P, people_resolver as R
from . import skin_reference_match_state as S, skin_reference_match_support as SUPPORT
from .people_support_assets import content_digest

BANK = 'people_support_assets'
_ADMISSION = '_skin_reference_match_admission'


def recipe(state, face_id):
    resolved = R.resolve(state, face_id, {S.OP: {'/amount': 0.0}})
    return R.materialize(resolved, S.OP, S.neutral(), S.check)


def active_refs(state, asset):
    P.digest(asset)
    return [P.face_ref(face) for key, face in sorted(state['faces'].items())
            if face['asset_sha256'] == asset and face['enabled'] and S.active(recipe(state, key))]


def validate_leaf(path, value):
    if path != '/amount':
        raise ValueError('Skin-reference recipes store only amount, never a reference, fit or support')
    S.check({'version': 1, 'amount': value})


def validate_graph(state):
    out = P.check(state)
    for row in out['overrides']:
        if row['operation_id'] == S.OP:
            validate_leaf(row['parameter_path'], row['value'])
            if row['scope'] != 'face':
                raise ValueError('Skin-reference matching requires explicit reviewed faces, not person/group/all-people inheritance')
    for key in out['faces']:
        recipe(out, key)
    return out


def _bank(value):
    # The shared registry validates every other family; this module owns only
    # its relation schema. Do not invent a parallel asset bank or rewrite it.
    from .people_support_assets import check_store
    bank = check_store(value)
    for key, record in bank.items():
        if record['row'].get('target') == SUPPORT.KIND:
            SUPPORT.check_record(record)
            if content_digest(record) != key:
                raise ValueError('Skin-reference historical support content changed')
    return bank


def _pointer(face, bank):
    descriptor = face['local_assets'].get(SUPPORT.KIND)
    if descriptor is None:
        return
    ref = P.face_ref(face); key = descriptor['content_sha256']
    record = SUPPORT.check_record(bank.get(key))
    if (content_digest(record) != key or record['face_ref'] != ref
            or descriptor != {'owner': ref, 'content_sha256': key, 'kind': SUPPORT.KIND}):
        raise ValueError('Skin-reference history pointer is missing, changed or owned by another face')
    # A dormant historical relation may name a former reference analysis. Its
    # metadata is still checked, but it is not current permission to render.


def validate_owned_graph(state, bank):
    state = validate_graph(state)
    for face in state['faces'].values():
        _pointer(face, bank)
    for asset in {face['asset_sha256'] for face in state['faces'].values()}:
        SUPPORT.validate_active(state, bank, active_refs(state, asset))
    return state


def validate(project, *, allowed=True):
    """Check active/undo/redo/patch pointers under their nearest canonical bank.

    Absence is neutral. Do not insert fields into old v1 documents or change
    their digest just because this operator was registered.
    """
    if type(project) is not dict:
        raise ValueError('Skin-reference project/context must be a dictionary')
    root = _bank(project.get(BANK, {}))
    def visit(value, bank):
        if type(value) is dict:
            if BANK in value:
                bank = _bank(value[BANK])
                if not allowed and any(record['row'].get('target') == SUPPORT.KIND for record in bank.values()):
                    raise ValueError('This project version cannot silently discard skin-reference support')
            if not allowed and (value.get('operation_id') == S.OP
                    or SUPPORT.KIND in value.get('local_assets', {})
                    or value.get('target') == SUPPORT.KIND):
                raise ValueError('This project version cannot silently discard skin-reference matching')
            for name in ('people_graph', '_people_state'):
                if name in value:
                    if value[name] is None:
                        raise ValueError('Saved skin-reference people graph cannot be null')
                    validate_owned_graph(value[name], bank)
            if value.get('_people_history') is not None:
                from .people_document_history import scoped_state
                validate_owned_graph(scoped_state(value['_people_history']), bank)
            # Protected history patches carry full scalar before/after rows,
            # not always a complete graph. Validate those leaves too; a face
            # pointer elsewhere in the patch still goes through _pointer.
            if value.get('operation_id') == S.OP and 'parameter_path' in value:
                validate_leaf(value['parameter_path'], value.get('value'))
                if value.get('scope') != 'face':
                    raise ValueError('Historical skin-reference intent cannot become a shared inherited reference')
            if 'face_instance_id' in value and 'local_assets' in value:
                _pointer(value, bank)
            for key, child in value.items():
                if key != BANK:
                    visit(child, bank)
        elif type(value) in (list, tuple):
            for child in value:
                visit(child, bank)
    visit(project, root)
    return root


def validate_records(value):
    """Structural registry hook; use validate(project) for full support closure."""
    if type(value) is dict:
        for name in ('people_graph', '_people_state'):
            if name in value:
                validate_graph(value[name])
        for child in value.values():
            validate_records(child)
    elif type(value) in (list, tuple):
        for child in value:
            validate_records(child)


def _signature(state, key):
    face = state['faces'].get(key)
    if face is None:
        return None
    amount = recipe(state, key)
    pointer = face['local_assets'].get(SUPPORT.KIND)
    if not S.active(amount) and pointer is None:
        return None
    return (amount, pointer, P.face_ref(face), face['evidence'], face['box'], face['enabled'])


def changed_assets(before, candidate):
    changed = set()
    for key in set(before['faces']) | set(candidate['faces']):
        if _signature(before, key) != _signature(candidate, key):
            changed.update(graph['faces'][key]['asset_sha256'] for graph in (before, candidate)
                           if key in graph['faces'])
    return changed


def _active_changes(before, candidate):
    def anatomy(state, asset):
        # Every retained face box is a protection veto, including inactive
        # faces. Changing a donor/neighbor is not an unrelated scalar edit.
        # Disabling a neighbor does not remove its retained protection box.
        # Active target/reference enablement is checked separately by relation validation.
        return [(key, P.face_ref(face), face['evidence'], face['box'])
                for key, face in sorted(state['faces'].items()) if face['asset_sha256'] == asset]
    changes = []
    for key, face in candidate['faces'].items():
        if face['enabled'] and S.active(recipe(candidate, key)):
            if (_signature(before, key) != _signature(candidate, key)
                    or anatomy(before, face['asset_sha256']) != anatomy(candidate, face['asset_sha256'])):
                changes.append(key)
    return changes


def require_unreviewed_transition(before, candidate):
    """Generic patches, aliases, presets and transfers cannot activate/change it.

    Complete neutral reset and disabling remain reachable under the original
    people/source/analysis guards, without requiring this native extension.
    """
    before = validate_graph(before); candidate = validate_graph(candidate)
    if _active_changes(before, candidate):
        raise ValueError('Active skin-reference changes require their own complete current-photo image review')
    return candidate


def require_scope(engine, before, candidate, *, row=None):
    changed = changed_assets(before, candidate)
    if not changed:
        return
    from . import virtual_copy_people as V, creative_derived_source as SOURCE
    current = V.current_row(engine); actual = current if row is None else row
    if actual is not current or current is None:
        raise ValueError('Skin-reference matching is current-photo only, not batch/cohort transfer')
    source_row = {**current, 'state': engine._people_preset_capture()}
    asset = SOURCE.row_asset(source_row)
    if changed - {asset}:
        raise ValueError('Skin-reference matching cannot change another photograph')
    aliases = [other for other in V.scope_rows(engine, current)
               if SOURCE.row_asset(source_row if other is current else other) == asset]
    if len(aliases) != 1 or aliases[0] is not current:
        raise ValueError('Source-identical documents require separate complete alias review; this path is current-photo only')
    from .face_style_alias_review import verify_dormant
    verify_dormant(engine, current, changed)


def require_transition(engine, before, candidate, *, row=None):
    before = validate_graph(before); candidate = validate_graph(candidate)
    require_scope(engine, before, candidate, row=row)
    bank = engine.__dict__.get('_people_support', {})
    validate_owned_graph(candidate, bank)
    if not _active_changes(before, candidate):
        return candidate
    authority = engine.__dict__.get(_ADMISSION)
    from .people_preset_plan import require_active_owner
    owner = require_active_owner(engine)
    if (not authority or authority['owner'] is not owner or owner.fence != authority['fence']
            or authority['before'] != before or authority['candidate'] != candidate
            or authority['bank_sha256'] != content_digest(bank)
            or authority['review_sha256'] is None):
        raise ValueError('Skin-reference publication is not the exact reviewed graph, support bank and owner')
    return candidate


@contextmanager
def reviewed_transition(engine, before, candidate, bank, review_sha256):
    """Operation-local, exact candidate/context admission; never a global bypass."""
    if _ADMISSION in engine.__dict__:
        raise ValueError('Skin-reference publication cannot nest another review admission')
    P.digest(review_sha256)
    from .people_preset_plan import require_active_owner
    owner = require_active_owner(engine)
    if owner.snapshot() != before:
        raise ValueError('Skin-reference owner changed before publication')
    validate_owned_graph(candidate, _bank(bank))
    engine.__dict__[_ADMISSION] = {'owner': owner, 'fence': owner.fence,
        'before': deepcopy(before), 'candidate': deepcopy(candidate),
        'bank_sha256': content_digest(bank), 'review_sha256': review_sha256}
    try:
        yield
    finally:
        engine.__dict__.pop(_ADMISSION, None)
