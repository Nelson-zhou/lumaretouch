# SPDX-License-Identifier: GPL-3.0-or-later
"""Transient hair smoothing source ports and frozen metadata, never pixels in history."""
from copy import deepcopy

KEY = 'hair_smoothing_source_info'


def needed(state, asset):
    from . import people_algorithms as A, people_resolver as R
    from .hair_smoothing_state import OP, active
    return any(face['asset_sha256'] == asset and face['enabled']
        and active(A.recipes(R.resolve(state, key, A.defaults()))[OP])
        for key, face in state['faces'].items())


def preview(engine, state, assets):
    source = engine._people_source()
    result = {'hair_smoothing_assets': assets}
    if needed(state, source['sha256']):
        from .hair_smoothing_source import from_engine
        result['hair_smoothing_source'] = from_engine(engine, state=state, source=source)
    return result


def freeze(snapshot, source, *, document_state, source_path):
    """Capture metadata from the same document snapshot that owns repair replay."""
    if not needed(snapshot['state'], snapshot['asset_sha256']):
        return snapshot
    from . import creative_derived_source as D, creative_derived_repairs as R
    from .local_mask_state import file_stamp
    from .portrait_fit_source import _binding
    source = _binding(source)
    proof = D.row_proof({'path': source_path, 'state': document_state})
    if proof['asset_sha256'] != source['sha256'] or proof['creative_source'] is not None or proof['original_sha256'] != source['sha256']:
        raise ValueError('Hair smoothing export source does not match its owned document')
    active, redo = R._stacks(document_state)
    bound = R.validate_stacks(document_state)
    snapshot[KEY] = {'version': 1, 'source': deepcopy(source), 'source_proof': proof,
        'path': source_path, 'stamp': list(file_stamp(source_path)),
        'repair_sha256': R.digest_ops(active, redo, bound),
        'active_sha256': R.digest_ops(active, [], bound)}
    return snapshot
