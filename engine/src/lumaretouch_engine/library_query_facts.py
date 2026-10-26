"""Read-only facts from retained rows/recipes, never from thumbnail appearance."""
from datetime import datetime, timezone
import hashlib
import json
import os
import re
from .library_query_schema import canonical_format


def source_id(row):
    runtime = row.get('_lrt_runtime_version') or {}
    identity = {'path': row['path'], 'document_id': runtime.get('id'),
                'source_stamp': row.get('_local_source_stamp') or row.get('_library_source_stamp')}
    # A later save discovers a full fingerprint; discovery is not replacement.
    # Expose that stronger evidence separately instead of changing selection IDs.
    return hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False).encode('utf-8')).hexdigest()


def rating_of(row):
    reserved = [tag for tag in (row.get('tags') or []) if isinstance(tag, str)
                and tag.startswith('rating:')]
    if not reserved:
        return 0
    if any(not re.fullmatch(r'rating:[0-5]', tag) for tag in reserved):
        return None
    ratings = {int(tag[-1]) for tag in reserved}
    return next(iter(ratings)) if len(ratings) == 1 else None


def flag_of(row):
    flags = {tag for tag in (row.get('tags') or []) if isinstance(tag, str)
             and tag.startswith('flag:')}
    if not flags:
        return 'unflagged'
    if flags == {'flag:accepted'}:
        return 'accepted'
    if flags == {'flag:rejected'}:
        return 'rejected'
    return None  # Malformed or conflicting intent is not an unflagged photo.


def _nonzero(values):
    return any(float(value) != 0 for value in values)


def edited_of(state, edits):
    """Use the host's active-module inventory, plus missing recipe-only axes.

    Analysis presence, opened state, history length, labels, and version fences
    are deliberately NOT edit evidence. A no-op/undo-to-neutral stays unedited.
    """
    if not isinstance(state, dict) or not isinstance(edits, dict):
        return None
    if any(bool(value) for key, value in edits.items() if key not in ('channel', 'lut_preset')):
        return True
    try:
        from .final_canvas_flip_state import active, from_state
        if active(from_state(state)):
            return True
        if (tuple(state.get('_crop_rect', (0, 0, 1, 1))) != (0, 0, 1, 1)
                or float(state.get('_crop_rotation', 0)) != 0
                or _nonzero(state.get('_exposure', ()))
                or tuple((state.get('_wb_options') or {}).get('picked_gains', (1, 1, 1))) != (1, 1, 1)
                or bool((state.get('_bg') or {}).get('active'))):
            return True
        # Neutral strength is zero in Engine; explicit unmasked smoothing is
        # also an edit. A selected channel alone is not.
        if float(state.get('_strength', 0)) != 0:
            return True
        from . import reference_color_state, semantic_colour_state, body_pose_operations
        if (reference_color_state.active(state.get('_reference_color'))
                or semantic_colour_state.active(state.get('_semantic_colour'))):
            return True
        bank = state.get('_body_pose_bank') or {}
        for body in bank.get('bodies', {}).values():
            if body_pose_operations.active_operations(body):
                return True
        # Legacy per-face parked banks may differ from the selected live face.
        for key in ('_deform_default',):
            values = state.get(key)
            if isinstance(values, dict):
                for value in values.values():
                    if isinstance(value, dict) and _nonzero(value.values()):
                        return True
                    if type(value) in (int, float) and value != 0:
                        return True
        if any(_nonzero((value.get('amounts') or {}).values())
               for value in (state.get('_deform_overrides') or [])):
            return True
        return False
    except (ValueError, TypeError, KeyError, OverflowError):
        # Unrecognized retained intent cannot honestly become “unedited”.
        return None


def _iso_ns(value):
    if type(value) is not int or value <= 0:
        return None
    try:
        return datetime.fromtimestamp(value / 1_000_000_000, timezone.utc).isoformat()
    except (ValueError, OverflowError, OSError):
        return None


def row_facts(row, event, state):
    metadata = dict((row.get('thumb') or {}).get('library_metadata') or {})
    metadata.update(row.get('_library_metadata') or {})
    fmt = canonical_format(metadata.get('format'))
    fmt_source = metadata.get('format_source') if fmt else None
    if fmt is None:
        fmt = canonical_format((row.get('thumb') or {}).get('format'))
        fmt_source = 'decoder' if fmt else None
    if fmt is None:
        fmt = canonical_format(os.path.splitext(row['path'])[1])
        fmt_source = 'filename_extension' if fmt else 'unknown'
    width = row.get('src_w') or metadata.get('src_w') or (row.get('thumb') or {}).get('src_w')
    height = row.get('src_h') or metadata.get('src_h') or (row.get('thumb') or {}).get('src_h')
    orientation = 'unknown'
    if type(width) is int and type(height) is int and width > 0 and height > 0:
        orientation = 'landscape' if width > height else 'portrait' if width < height else 'square'
    size = row.get('bytes_on_disk')
    size = size if type(size) is int and size >= 0 else None
    fp = row.get('fingerprint') or {}
    return {'source_id': source_id(row),
            'source_fingerprint': {key: fp.get(key) for key in ('sha256', 'head_sha256', 'bytes', 'mtime_ns')},
            'rating': rating_of(row), 'flag': flag_of(row),
            'label': row.get('label') or '', 'edited': edited_of(state, event.get('edits')),
            'exported': False, 'export_scope': 'successful_receipt_in_project_ledger',
            'format': fmt, 'format_source': fmt_source, 'orientation': orientation,
            'size': size, 'capture_time': metadata.get('capture_time'),
            'capture_time_source': metadata.get('capture_time_source', 'unavailable'),
            'capture_time_zone': metadata.get('capture_time_zone', 'unknown'),
            'edit_time': _iso_ns(row.get('_library_edit_time_ns')),
            'edit_time_source': 'confirmed_session_edit' if row.get('_library_edit_time_ns') else 'unavailable'}


def successful_exports(tasks):
    """Failed, queued, cancelled, and conflict-skipped items are never success."""
    return {item.get('document_id') or item['path'] for task in tuple(tasks.values()) if task.get('kind') == 'export'
            for item in tuple(task.get('items') or [])
            if item.get('state') == 'succeeded' and type(item.get('out')) is str
            and item['out'] and type(item.get('path')) is str}


def people_edits(engine, row, state):
    """Resolve retained per-person recipes without hashing/loading a source.

    A graph may have edits for an unsaved source whose digest is not exposed on
    its row. Report unknown for that ambiguity instead of borrowing another face.
    """
    from .virtual_copy_people import peek_graph
    graph = peek_graph(engine,row)
    if graph is None: return None
    if not isinstance(graph, dict) or not graph.get('overrides'):
        return False
    asset = (row.get('fingerprint') or {}).get('sha256')
    if not asset and 0 <= engine._doc_index < len(engine._docs) and row is engine._docs[engine._doc_index]:
        prepared = getattr(getattr(engine, '_vram', None), 'people_prepared', None)
        plan = getattr(prepared, 'plan', {})
        asset = plan.get('asset_sha256') if isinstance(plan, dict) else None
    if not asset:
        hints = [(state.get(key) or {}).get('source') for key in
                 ('_local_masks', '_reference_color', '_semantic_colour')]
        hints += [(snap.get('_people_history') or {}) for snap in (row.get('undo') or [])]
        asset = next((hint.get('sha256') or hint.get('asset_sha256')
                      for hint in hints if isinstance(hint, dict)
                      and (hint.get('sha256') or hint.get('asset_sha256'))), None)
    if not asset:
        return None
    try:
        from . import people_algorithms as algorithms
        from .people_resolver import resolve
        defaults = algorithms.defaults()
        for key, face in graph['faces'].items():
            if face['asset_sha256'] != asset or not face['enabled']:
                continue
            resolved = resolve(graph, key, defaults)
            if resolved['conflicts']:
                return None
            for operation, leaves in resolved['operations'].items():
                baseline = defaults.get(operation)
                if baseline is None:
                    return None
                if any(record['value'] != baseline.get(path) for path, record in leaves.items()):
                    return True
        return False
    except (ValueError, TypeError, KeyError):
        return None
