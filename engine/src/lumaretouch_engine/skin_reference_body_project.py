# SPDX-License-Identifier: GPL-3.0-or-later
"""Strict graph/history admission for selected same-photo body matching. UNRUN.

No new graph, support bank, history owner, migration or portable reference. The
canonical people owner remains the sole publisher. A temporary exact admission
is usable only by the dedicated complete-image transaction.
"""
from contextlib import contextmanager
from copy import deepcopy

from . import people_state as P, people_resolver as R
from . import skin_reference_body_state as S, skin_reference_body_support as SUPPORT
from .people_support_assets import content_digest

BANK = 'people_support_assets'
_ADMISSION = '_skin_reference_body_admission'


def recipe(state, face_id):
    resolved = R.resolve(state, face_id, {S.OP: {'/amount': 0.0}})
    return R.materialize(resolved, S.OP, S.neutral(), S.check)


def active_refs(state, asset):
    P.digest(asset)
    return [P.face_ref(face) for key, face in sorted(state['faces'].items())
            if face['asset_sha256'] == asset and face['enabled'] and S.active(recipe(state, key))]


def validate_leaf(path, value):
    if path != '/amount':
        raise ValueError('Body-reference recipes store only amount, never a reference, fit or support')
    S.check({'version': 1, 'amount': value})


def validate_graph(state):
    out = P.check(state)
    for row in out['overrides']:
        if row['operation_id'] == S.OP:
            validate_leaf(row['parameter_path'], row['value'])
            if row['scope'] != 'face':
                raise ValueError('Body-reference matching requires explicit reviewed owner faces, not person/group/all-people inheritance')
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
                raise ValueError('Body-reference historical support content changed')
    return bank


def _pointer(face, bank):
    descriptor = face['local_assets'].get(SUPPORT.KIND)
    if descriptor is None:
        return
    ref = P.face_ref(face); key = descriptor['content_sha256']
    record = SUPPORT.check_record(bank.get(key))
    if (content_digest(record) != key or record['face_ref'] != ref
            or record['row']['face_evidence'] != face['evidence']
            or descriptor != {'owner': ref, 'content_sha256': key, 'kind': SUPPORT.KIND}):
        raise ValueError('Body-reference history pointer is missing, changed or owned by another face')
    # A dormant historical relation may name a former reference analysis. Its
    # metadata is still checked, but it is not current permission to render.


def common_reference(state, bank, asset, body_bank=None, analyses=None):
    """One selected donor across independently reviewed face and body lanes.

    Metadata-only use validates historical closure, never grants raster/render
    permission. Live callers supply the target document's body and analysis bank.
    The donor may own a body target but must remain outside face target support.
    """
    from . import skin_reference_match_project as FACE_PROJECT
    from . import skin_reference_match_support as FACE_SUPPORT
    face_refs = FACE_PROJECT.active_refs(state, asset)
    reference = FACE_SUPPORT.validate_active(state, bank, face_refs, analyses)
    refs = active_refs(state, asset)
    if body_bank is not None:
        selected = SUPPORT.validate_active(state, bank, refs, body_bank, analyses)
        if reference is not None and selected is not None and reference != selected:
            raise ValueError('Active face and body targets must use one explicitly selected same-photo reference')
        return deepcopy(reference if reference is not None else selected)
    for ref in refs:
        attached = SUPPORT._attached(state, bank, ref)
        if attached is None:
            raise ValueError('Every active body-reference target needs its own reviewed support')
        record, _ = attached; row = record['row']
        selected = row['reference_face_ref']
        _, target_face = FACE_SUPPORT._face(state, ref)
        _, reference_face = FACE_SUPPORT._face(state, selected)
        if (target_face['evidence'] != row['face_evidence']
                or reference_face['evidence'] != row['reference_evidence']):
            raise ValueError('Body-reference target or reference evidence differs from the retained graph')
        if reference is not None and reference != selected:
            raise ValueError('Active face and body targets must use one explicitly selected same-photo reference')
        reference = selected
    return deepcopy(reference)


def validate_owned_graph(state, bank, body_bank=None, analyses=None, *, asset=None):
    state = validate_graph(state)
    for face in state['faces'].values():
        _pointer(face, bank)
    for source in {face['asset_sha256'] for face in state['faces'].values()}:
        # A document body bank cannot authorize other photos in a shared graph.
        live = body_bank is not None and source == asset
        common_reference(state, bank, source, body_bank if live else None,
                         analyses if live else None)
    return state


def _history_body_closure(state, bank, body_bank, association_revision):
    """Authenticate historical storage, not current permission to render.

    Body disable/reanalysis/reassociation may retain nonzero unapplied intent.
    Its old immutable BodyRef/points/review must survive save/reopen unchanged.
    Return stale owner refs as a transient classification; never rebind a record
    or treat a historical match as replacement for live runtime resolution.
    """
    from . import body_pose_state as B, body_pose_evidence as E
    refs = [P.face_ref(face) for key, face in sorted(state['faces'].items())
            if face['enabled'] and S.active(recipe(state, key))]
    if not refs:
        return []
    if body_bank is None:
        raise ValueError('Active body-reference history needs its own retained body snapshot')
    body_bank = B.check(body_bank); stale = []
    for ref in refs:
        attached = SUPPORT._attached(state, bank, ref)
        if attached is None:
            raise ValueError('Active body-reference history has no owned support')
        record, _ = attached; row = record['row']; review = row['review']
        body = body_bank['bodies'].get(review['body_ref']['body_instance_id'])
        if (body is None or body['record']['body_ref'] != review['body_ref'] or not body['enabled']
                or E.content_digest(body['record']) != row['body_record_sha256']
                or body['record']['points_sha256'] != review['points_sha256']
                or body_bank['association_revision'] != row['body_association_revision']
                or body['association'] != row['body_link']
                or association_revision != row['people_association_revision']):
            stale.append(deepcopy(ref))
    return stale


def validate(project, *, allowed=True):
    """Close active/undo/redo/patch metadata under its nearest canonical owners.

    No source pixels, current analyses or inference are needed during project
    I/O. Full graph contexts validate selected-reference consistency; scoped
    history authenticates its own retained pose snapshot; stale body relations
    remain durable nonrenderable intent without rebinding to new evidence.
    Dormant relations remain structurally authenticated, not live permission.
    Absence stays neutral without migration or changing old recipe digests.
    """
    if type(project) is not dict:
        raise ValueError('Body-reference project/context must be a dictionary')
    from . import body_pose_project as BODY_PROJECT
    root = _bank(project.get(BANK, {}))
    def visit(value, bank, body_bank=None):
        if type(value) is dict:
            # A private virtual-copy context owns both graph and support for its
            # sibling document state/history. Never borrow the shared root bank.
            private = value.get('people_context')
            if type(private) is dict and BANK in private:
                bank = _bank(private[BANK])
            if BANK in value:
                bank = _bank(value[BANK])
            if not allowed and any(record['row'].get('target') == SUPPORT.KIND for record in bank.values()):
                raise ValueError('This project version cannot silently discard body-reference support')
            if BODY_PROJECT.KEY in value:
                body_bank = BODY_PROJECT.bank(value)
            if not allowed and (value.get('operation_id') == S.OP
                    or SUPPORT.KIND in value.get('local_assets', {})
                    or value.get('target') == SUPPORT.KIND):
                raise ValueError('This project version cannot silently discard body-reference matching')
            for name in ('people_graph', '_people_state'):
                if name in value:
                    if value[name] is None:
                        raise ValueError('Saved body-reference people graph cannot be null')
                    state = validate_owned_graph(value[name], bank)
            history = value.get('_people_history')
            if history is not None:
                from .people_document_history import scoped_state
                state = validate_owned_graph(scoped_state(history), bank)
                _history_body_closure(state, bank, body_bank, history['association_revision'])
            # Protected sparse patches still carry full scalar before/after rows
            # and face pointers. Their original immutable records must survive.
            if value.get('operation_id') == S.OP and 'parameter_path' in value:
                validate_leaf(value['parameter_path'], value.get('value'))
                if value.get('scope') != 'face':
                    raise ValueError('Historical body-reference intent cannot become shared inherited permission')
            if 'face_instance_id' in value and 'local_assets' in value:
                _pointer(value, bank)
            for key, child in value.items():
                if key not in (BANK, BODY_PROJECT.KEY):
                    visit(child, bank, body_bank)
        elif type(value) in (list, tuple):
            for child in value:
                visit(child, bank, body_bank)
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
        return ([(key, P.face_ref(face), face['evidence'], face['box'])
                 for key, face in sorted(state['faces'].items()) if face['asset_sha256'] == asset],
                state['association_revision'], state['links'], state['persons'])
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
        raise ValueError('Active body-reference changes require their own complete current-photo image review')
    return candidate


def require_scope(engine, before, candidate, *, row=None):
    changed = changed_assets(before, candidate)
    if not changed:
        return
    from . import virtual_copy_people as V, creative_derived_source as SOURCE
    current = V.current_row(engine); actual = current if row is None else row
    if actual is not current or current is None:
        raise ValueError('Body-reference matching is current-photo only, not batch/cohort transfer')
    source_row = {**current, 'state': engine._people_preset_capture()}
    asset = SOURCE.row_asset(source_row)
    if changed - {asset}:
        raise ValueError('Body-reference matching cannot change another photograph')
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
    source = engine._people_source()['sha256']
    # Clearing the last body target must not resolve stale/unavailable body
    # evidence or load the native extension. Other active targets still resolve.
    body_bank = engine._body_bank() if active_refs(candidate, source) else None
    validate_owned_graph(candidate, bank, body_bank, asset=source)
    if not _active_changes(before, candidate):
        return candidate
    authority = engine.__dict__.get(_ADMISSION)
    from .people_preset_plan import require_active_owner
    owner = require_active_owner(engine)
    if (not authority or authority['owner'] is not owner or owner.fence != authority['fence']
            or authority['before'] != before or authority['candidate'] != candidate
            or authority['bank_sha256'] != content_digest(bank)
            or authority['body_bank_sha256'] != content_digest(engine._body_bank())
            or authority['review_sha256'] is None):
        raise ValueError('Body-reference publication is not the exact reviewed graph, support bank and owner')
    return candidate


@contextmanager
def reviewed_transition(engine, before, candidate, bank, review_sha256):
    """Operation-local, exact candidate/context admission; never a global bypass."""
    if _ADMISSION in engine.__dict__:
        raise ValueError('Body-reference publication cannot nest another review admission')
    P.digest(review_sha256)
    from .people_preset_plan import require_active_owner
    owner = require_active_owner(engine)
    if owner.snapshot() != before:
        raise ValueError('Body-reference owner changed before publication')
    validate_owned_graph(candidate, _bank(bank), engine._body_bank(),
                         asset=engine._people_source()['sha256'])
    engine.__dict__[_ADMISSION] = {'owner': owner, 'fence': owner.fence,
        'before': deepcopy(before), 'candidate': deepcopy(candidate),
        'bank_sha256': content_digest(bank), 'body_bank_sha256': content_digest(engine._body_bank()),
        'review_sha256': review_sha256}
    try:
        yield
    finally:
        engine.__dict__.pop(_ADMISSION, None)
