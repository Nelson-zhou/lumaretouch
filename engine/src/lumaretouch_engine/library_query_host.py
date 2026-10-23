"""Tiny Engine adapter: view preferences and a read-only query result.

Host integration owns dispatch ordering and emits its usual session_state.
Nothing here renders, alters a recipe/history stack, selects a photo, scans a
directory, or hashes a source file. A rejected query preserves the old view and
returns the attempted request ID alongside its explicit rejection.
"""
from copy import deepcopy
import time
import uuid
from .library_query_schema import QueryError, default_query, validate_query
from .library_query_engine import evaluate
from .library_query_facts import row_facts, successful_exports, people_edits


def session_id(engine):
    versions = engine.__dict__.get('_document_version_owner')
    if versions is not None:
        return str(versions.workspace)
    # Only empty/uninitialized hosts need this view-only fallback identity.
    value = engine.__dict__.get('_library_empty_session')
    if value is None:
        value = uuid.uuid4().hex
        engine._library_empty_session = value
    return value


def _owner(engine):
    identity = session_id(engine)
    owner = engine.__dict__.get('_library_query_owner')
    if owner is None or owner['session_id'] != identity:
        owner = {'session_id': identity, 'query': default_query(),
                 'request_id': None, 'error': None, 'success': True}
        engine._library_query_owner = owner
    return owner


def set_query(engine, command):
    owner = _owner(engine)
    request_id = command.get('request_id')
    # Capture a safe correlation ID even when the remaining candidate is invalid.
    owner['request_id'] = request_id if type(request_id) is str and len(request_id) <= 128 else None
    try:
        if set(command) - {'cmd', 'action', 'query', 'request_id', 'session_id'}:
            raise QueryError('Library query contains unsupported parameters')
        if type(request_id) is not str or not 1 <= len(request_id) <= 128:
            raise QueryError('Library query requires a bounded request_id')
        if command.get('session_id') != owner['session_id']:
            raise QueryError('The library session changed; refresh before querying')
        candidate = validate_query(command.get('query'))
    except (QueryError, TypeError, ValueError) as error:
        owner['success'], owner['error'] = False, str(error)
        return False
    owner.update(query=candidate, success=True, error=None)
    return True


def enrich_row(engine, index, row, event_row, state):
    result = dict(event_row)
    facts = row_facts(row, event_row, state)
    if facts['edited'] is not True:
        people = people_edits(engine, row, state)
        if people is True or (people is None and facts['edited'] is False):
            facts['edited'] = people
    result['library'] = facts
    return result


def query_state(engine, event_rows):
    owner = _owner(engine)
    exported = successful_exports(getattr(engine, '_tasks', {}))
    # These are response copies, not source rows. Keep every outgoing fact in
    # one result consistent with the same observed export-ledger snapshot.
    rows = [{**row, 'library': {**row['library'], 'exported': (row.get('document_id',row['path']) in exported or (not row.get('copy_number',0) and row['path'] in exported))}}
            for row in event_rows]
    visible = evaluate(rows, owner['query'])
    return {'version': 1, 'session_id': owner['session_id'],
            'request_id': owner['request_id'], 'success': owner['success'], 'error': owner['error'],
            'query': deepcopy(owner['query']), 'paths': [row['path'] for row in visible], 'document_ids':[row['document_id'] for row in visible],
            'indices': [row['index'] for row in visible], 'count': len(visible), 'total': len(rows),
            'source_ids': {row['document_id']: row['source_asset_id'] for row in rows},
            'facts': {row['document_id']: row['library'] for row in rows},
            'unknown': {key: sum(row['library'].get(key) is None for row in rows)
                        for key in ('rating', 'flag', 'edited', 'capture_time', 'edit_time', 'size', 'format')},
            'policies': {'combination': 'and_axes_or_choices', 'unknown_sort': 'last_in_both_directions',
                         'sort_tie': 'ascending_casefold_path_then_exact_path_then_original_index',
                         'capture_time': 'utc_when_offset_known_otherwise_camera_wall_time',
                         'exported_no': 'no_successful_receipt_in_current_or_restored_project_ledger',
                         'format_fallback': 'filename_extension_is_reported_as_unverified',
                         'edit_time': 'confirmed_changes_this_session_only;_older_unrecorded_edits_unknown'}}


def note_edit(engine, row=None):
    """Call only after a confirmed recipe change, never an attempted command.

    This metadata is outside recipe/history. Querying never calls this function.
    Undo/redo that actually change the recipe are edits; selection, save, label,
    analysis, history clearing and a rejected/no-op action are not.
    """
    if row is None:
        index = getattr(engine, '_doc_index', -1)
        rows = getattr(engine, '_docs', ())
        row = rows[index] if 0 <= index < len(rows) else None
    if row is not None:
        row['_library_edit_time_ns'] = time.time_ns()
