# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only admission of one genuinely prepared target's canonical people owner.

Legacy skin strength is not reinterpreted as a new retained-person operation.
The normal people preset planner must prove an unchanged graph for that scalar.
"""
from . import creative_derived_source as SOURCE, people_state as S
from .people_preset_plan import require_active_owner
from .optics_candidate_identity import fingerprint


def require_target(engine, row, state):
    if SOURCE.record(state) is not None or row.get('copy_number', 0) != 0:
        raise ValueError('Workflow skin preparation requires its original-source target')
    owner = require_active_owner(engine)
    graph = owner.snapshot()
    source = SOURCE.row_proof({**row, 'state': state})
    asset = source['asset_sha256']
    pc = state.get('_precompute')
    if (pc is None or type(getattr(pc, 'num_faces', None)) is not int or pc.num_faces != 1
            or getattr(pc, 'backend', None) != 'mediapipe'
            or state.get('_channel') != 'skin'
            or getattr(pc, 'masks', {}).get('skin') is None):
        raise ValueError('Workflow skin needs exactly one real analysed face and selected target skin mask')
    SOURCE.verify_precompute(state, pc)
    faces = [face for face in graph['faces'].values() if face['asset_sha256'] == asset]
    run = graph['analysis_runs'].get(asset)
    if (len(faces) != 1 or not faces[0]['enabled'] or faces[0]['manual']
            or run is None or run['limit_reached']):
        raise ValueError('Target retained analysis is missing, ambiguous, manual or detection-limited')
    face = faces[0]
    ref = S.face_ref(face)
    from .people_binding import evidence, landmark_digest
    measured = evidence(pc, pc.landmarks, (row['src_w'], row['src_h']))
    analysis = engine.__dict__.get('_people_analyses', {}).get(asset, {}).get(ref['face_instance_id'])
    target = engine.__dict__.get('_people_targets', {}).get(asset)
    if (measured['status'] != 'verified' or face['evidence'] != measured
            or analysis is None or analysis['face_ref'] != ref or analysis['evidence'] != measured
            or landmark_digest(analysis['landmarks']) != measured['landmark_digest']
            or analysis.get('skin') is None
            or engine.__dict__.get('_people_cursors', {}).get(asset) != ref['face_instance_id']
            or target != {'scope': 'face', 'target_id': ref['face_instance_id'], 'face_ref': ref}):
        raise ValueError('Prepared skin mask, measured landmarks and explicit retained target differ')
    if (any(link['face_instance_id'] == ref['face_instance_id'] for link in graph['links'])
            or any(ref['face_instance_id'] in group['face_ids'] for group in graph['groups'].values())
            or any(item['scope'] == 'face' and item['target_id'] == ref['face_instance_id']
                   or item['scope'] == 'all_people' and item['target_id'] == asset
                   for item in graph['overrides'])
            or any(item['asset_sha256'] == asset and item['status'] == 'unresolved'
                   for item in graph['unresolved_legacy'])):
        raise ValueError('Workflow scalar skin cannot replace retained edits or shared person associations')
    return owner, graph, ref


def require_candidate(engine, row, before, after):
    """Use the same planner as normal preset replay, without publishing a graph."""
    owner, graph, ref = require_target(engine, row, before)
    fence = owner.fence
    from .people_scope import plan_preset
    plan = plan_preset(engine, after)
    if (not plan.managed or plan.owner is not owner or plan.owner_fence != fence
            or plan.before != graph or plan.candidate != graph or plan.patches
            or plan.target_ref != ref or fingerprint(plan.state) != fingerprint(after)
            or require_active_owner(engine) is not owner or owner.fence != fence
            or owner.snapshot() != graph
            or fingerprint(engine._people_preset_capture()) != fingerprint(before)):
        raise ValueError('Canonical people preset plan differs from the reviewed target scalar candidate')
    return plan
