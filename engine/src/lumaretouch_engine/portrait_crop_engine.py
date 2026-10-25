# SPDX-License-Identifier: GPL-3.0-or-later
"""Canonical crop publication port, not another renderer or undo owner.

AUTHORED / UNRUN. Only the reviewed rectangle changes. Compact terminal receipts
are session-owned recovery evidence, never persisted UI approval or a substitute
for the existing project/history representation.
"""
from copy import deepcopy
from .optics_candidate_identity import fingerprint

MAX_COMMITS = 128
MAX_RECEIPT_BYTES = 16 * 1024 * 1024


def _receipts(engine):
    return engine.__dict__.setdefault('_portrait_crop_commit_receipts', {})


def candidate_status(engine, request_id):
    from .portrait_crop_controller import valid_id
    if not valid_id(request_id):
        raise ValueError('Invalid original portrait crop request identity')
    row = _receipts(engine).get(request_id)
    if row is None or row['workspace'] != engine._document_versions().workspace:
        return None
    return deepcopy(row['result'])


def commit_candidate(engine, *, before_state, candidate_state, proof, request_id):
    from .portrait_crop_controller import valid_id, canonical
    from .portrait_crop_project import verify_commit, non_crop_hash
    from .scope import OP_CROP, check_params
    if not valid_id(request_id):
        raise ValueError('Invalid original portrait crop request identity')
    identity = fingerprint({'before': before_state, 'candidate': candidate_state, 'proof': proof})
    receipts = _receipts(engine)
    old = receipts.get(request_id)
    if old is not None:
        if old['identity'] != identity or old['workspace'] != engine._document_versions().workspace:
            raise ValueError('Portrait crop request cannot be reused for another source or candidate')
        return deepcopy(old['result'])
    proof = verify_commit(engine, before_state, candidate_state, proof)
    if len(receipts) >= MAX_COMMITS:
        raise ValueError('Portrait crop terminal receipt capacity reached; no new write admitted')
    guard = engine._history_guard('portrait_crop')
    if guard is not None:
        raise ValueError(guard)
    row = engine._docs[engine._doc_index]
    versions = engine._document_versions()
    before_version = versions.version(row)
    if (before_version.document_id != proof['binding']['document_id']
            or str(before_version.revision) != proof['binding']['revision']):
        raise ValueError('Portrait crop document revision changed before canonical publication')
    compact = {'identity': identity, 'workspace': versions.workspace, 'proof': proof,
               'result': {'status': 'applied', 'document_id': before_version.document_id,
                          'revision': str(before_version.revision + 1)}}
    reserve = len(canonical(compact))
    if reserve + sum(len(canonical(value)) for value in receipts.values()) > MAX_RECEIPT_BYTES:
        raise ValueError('Portrait crop compact receipt byte capacity reached before publication')
    if fingerprint(before_state) == fingerprint(candidate_state):
        compact['result'].update(status='no_change', revision=str(before_version.revision))
        receipts[request_id] = compact
        return deepcopy(compact['result'])
    params = check_params(OP_CROP, {'rect_normalized': list(candidate_state['_crop_rect']),
                                  'rotation_degrees': candidate_state['_crop_rotation']})
    history_before = engine._history_capture()
    previous = tuple(engine._crop_rect), float(engine._crop_rotation)
    # Exactly one mutation fence; this operation is not also in EDIT_CMDS.
    versions.check_advance(row)
    versions.advance(row)
    frame = None
    try:
        geometry = engine._vram.set_geometry(params['rect_normalized'], params['rotation_degrees'])
        engine._crop_rect = tuple(geometry['crop_rect'])
        engine._crop_rotation = float(geometry['crop_rotation'])
        frame = engine._write_current_frame('portrait_crop')
        after = engine._capture_state()
        if fingerprint(after) != fingerprint(candidate_state) or non_crop_hash(after) != non_crop_hash(before_state):
            raise RuntimeError('Canonical portrait crop publication changed an unrelated recipe')
    except Exception:
        # No history insertion has started. Restore only geometry, never replace
        # another family's graph/support or re-enter the mutation on query.
        engine._crop_rect, engine._crop_rotation = previous
        try:
            engine._vram.set_geometry(*previous)
            engine._write_current_frame('portrait_crop_rollback')
        except Exception:
            engine._vram = None
        raise
    # Any exception from here may follow an actual history write. Keep the host
    # unknown fence rather than blindly removing history or resending the crop.
    engine._history_record('portrait_crop:' + request_id, history_before, coalesce=False)
    engine._remember_current()
    version = versions.version(row)
    if (version.document_id != before_version.document_id or version.revision != before_version.revision + 1
            or fingerprint(engine._capture_state()) != fingerprint(candidate_state)):
        raise RuntimeError('Portrait crop canonical outcome could not be verified')
    # Terminal proof is captured before frame/event delivery, so a transport
    # failure can query this exact outcome without executing commit again.
    receipts[request_id] = compact
    from .server import emit
    frame['doc_state'] = engine.doc_state()
    frame.setdefault('crop', {}).update(engine._vram.geometry_state())
    frame['crop']['out_full'] = list(proof['plan']['output_size'])
    emit(frame)
    return deepcopy(compact['result'])


class PortraitCropEngineMixin:
    def _portrait_crop_capability(self):
        from .portrait_crop_host import capability
        return capability(self)

    def cmd_portrait_crop(self, request):
        from .portrait_crop_host import service
        from .server import emit
        return service(self, emit).handle(request)

    def _commit_portrait_crop_candidate(self, **kwargs):
        return commit_candidate(self, **kwargs)

    def _portrait_crop_candidate_status(self, request_id):
        return candidate_status(self, request_id)
