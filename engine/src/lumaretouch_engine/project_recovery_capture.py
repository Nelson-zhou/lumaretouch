"""Lossless encoded capture, called only after a proven committed command.

Unlike manual _project_build this retains inactive named versions/assets and does
not erase _precompute or unknown tensors. Unsupported values stop autosave with
an actionable error rather than silently changing the reopened image.
"""
from copy import deepcopy
from . import project as PJ, tasks as T
from .project_recovery_store import RecoveryError, no_dropped
from .virtual_copy_project import save_row, save_receipts


def capture(engine, *, revision, native_receipts, transaction_open):
    if transaction_open or any(row.get('phase') not in ('committed', 'cancelled', 'rejected')
                               for row in native_receipts):
        raise RecoveryError('Unsettled command/native transaction cannot be autosaved')
    if engine._project is None:
        raise RecoveryError('Create a project before enabling recovery snapshots')
    engine._remember_current()
    project = deepcopy(engine._project)
    project.pop('_source_path', None)
    project.pop('_source_sha256', None)
    live_ids = {row['document_id'] for row in engine._docs}
    project['docs'] = [row for row in project['docs'] if row['document_id'] in live_ids]
    for row in sorted(engine._docs, key=lambda row: bool(row.get('copy_number', 0))):
        fp = row.get('fingerprint')
        if fp is None:
            raise RecoveryError('Source fingerprint has not reached a committed import boundary')
        stored = PJ.add_doc(project, row['path'], row['state'], fp=fp,
            tags=row.get('tags'), budget=row.get('budget'),
            version_id=row.get('_project_version_id', row['recipe_version_id']),
            trashed=bool(row.get('trashed')),
            **{key: row[key] for key in ('document_id', 'source_asset_id',
                'root_document_id', 'copy_number', 'recipe_version_id')})
        save_row(project, row, stored, PJ)
        # save_row strips derived precompute from history. Recovery has a stricter
        # contract: encode the entire stacks or fail, never keep a reduced graph.
        dropped = []
        stored['document_history'] = PJ.encode(
            {key: row.get(key, []) for key in ('undo', 'redo')},
            project['assets'], dropped, 'recovery.document_history.' + row['document_id'])
        if dropped:
            raise RecoveryError('Recovery history contains unsupported assets: ' + str(dropped[:3]))
        stored['label'] = row.get('label')
    order = {row['document_id']: i for i, row in enumerate(engine._docs)}
    project['docs'].sort(key=lambda row: order[row['document_id']])
    # for_json reads copies; do not mark live tasks persisted as a capture side effect.
    project['tasks'] = [T.for_json(deepcopy(task)) for task in engine._tasks.values()]
    engine._people_save(project)
    save_receipts(engine, project)
    from .managed_import_project import save_receipts as save_import_receipts
    save_import_receipts(engine, project)
    project['active_document_id'] = (engine._docs[engine._doc_index]['document_id']
        if 0 <= engine._doc_index < len(engine._docs) else None)
    no_dropped(project)
    PJ.validate(project)
    return project, {'revision': revision, 'native_receipts': deepcopy(native_receipts),
                     'transaction_open': False, 'original_path': engine._project_path}
