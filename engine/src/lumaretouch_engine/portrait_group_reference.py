# SPDX-License-Identifier: GPL-3.0-or-later
"""Reference-only group adapter; existing fit/render/history own all algorithms.

No skin analysis prerequisite. No fitting after the first read-only preparation.
Runtime, quality, performance and authored fixtures are UNRUN.
"""
from copy import deepcopy
from . import reference_color_scope as RC, reference_color_engine as RE
from . import workflow_preset_review as review, creative_derived_source as SOURCE
from . import full_candidate_render as full
from .optics_candidate_identity import fingerprint

MODE = 'reference_color'


def selected(preset):
    return RC.OP in preset['modules']


def support(preset):
    try:
        if set(preset['modules']) != {RC.OP} or 'xmp_import' in preset:
            raise ValueError('reference_group_requires_reference_only_intent')
        params = RC.check_params(preset['modules'][RC.OP])
        if not params['strength']:
            raise ValueError('reference_group_requires_nonzero_reference_intent')
    except (ValueError, TypeError, KeyError) as error:
        return {'supported': False, 'reason': str(error), 'mode': MODE}
    return {'supported': True, 'reason': None, 'mode': MODE}


def inputs(group, document, preset, frozen_fit=None):
    index, row = group._row(document)
    state = row['state']
    if row.get('copy_number', 0) != 0 or SOURCE.record(state) is not None:
        raise ValueError('Reference group requires original photographs, not virtual/derived copies')
    recovery = group.engine.__dict__.get('_project_recovery_runtime')
    if recovery is not None and recovery.tainted:
        raise ValueError('Resolve uncertain project recovery before reference review')
    context = full.people_context(group.engine, row)
    version = group.batch.versions.version(row)
    target = {'document_id': document, 'revision': str(version.revision)}
    params = preset['modules'][RC.OP]
    candidate = dict(state)
    record = (RE.prepare_target(group.engine, row, candidate, document, target['revision'], params)
              if frozen_fit is None else deepcopy(frozen_fit))
    # Saved reference assets are immutable; never allow the reference document
    # itself or another document with the same physical source to become a target.
    source = SOURCE.row_proof(row)
    if (record['reference']['document_id'] == document
            or record['reference']['source']['sha256'] == source['asset_sha256']):
        raise ValueError('Reference photograph and its physical source remain unchanged')
    recipe = RC.verify_target(record, state, candidate, row, document, version.revision, params)
    RC.apply_verified(candidate, recipe)
    from .white_balance_recipe import prepare_state
    prepare_state(candidate)
    left, graph = review._proof(group.engine, row, state, target)
    right, after_graph = review._proof(group.engine, row, candidate, target)
    if (graph != after_graph or left['render']['source_proof'] != right['render']['source_proof']
            or left['repair_sha256'] != right['repair_sha256']):
        raise ValueError('Reference candidate changed source, repairs or portrait ownership')
    owned = {'index': index, 'row': row, 'target': target, 'before': left, 'after': right,
        'context': fingerprint(context), 'history': fingerprint((row['undo'], row['redo'])),
        'reference_fit': deepcopy(record)}
    return owned, state, candidate, graph
