# SPDX-License-Identifier: GPL-3.0-or-later
"""Target-local multi-face preparation for retained-operation group presets.

No identity recognition, cross-photo matching, mask transfer or scalar-skin
reinterpretation. Every FaceRef comes from this original's own canonical binder.
Source integration only: inference, build, quality and performance remain UNRUN.
"""
from . import creative_derived_source as SOURCE, virtual_copy_people as V, people_state as S
from . import full_candidate_render as full
from .optics_candidate_identity import fingerprint
from .workflow_preset_preparation import SkinPreparation, DERIVED_FIELDS

MAX_FACES = 8


def _analysis(pc, channel):
    if (pc is None or getattr(pc, 'backend', None) != 'mediapipe'
            or type(getattr(pc, 'num_faces', None)) is not int
            or not 1 <= pc.num_faces <= MAX_FACES
            or getattr(pc, 'detection_limit_reached', True) is not False
            or channel != 'skin'
            or any((getattr(pc, 'masks', None) or {}).get(key) is None
                   for key in ('skin', 'face_skin'))):
        raise ValueError('Retained group needs one to eight real target-owned MediaPipe faces, non-limit-hit detection and face-skin support')
    pool = getattr(pc, 'all_landmarks', None) or [pc.landmarks]
    if len(pool) != pc.num_faces or getattr(pc, 'manual', ()):
        raise ValueError('Manual or inconsistent face detections cannot enter automatic group preparation')
    return pool


def admit(engine, row, state):
    """Read-only parked/live admission; return canonical context and own FaceRefs.

    A multi-face group explicitly selects all verified instances in each target;
    it neither borrows the editor cursor nor infers correspondences between photos.
    Non-limit-hit detection is not proof that every person in the scene was found.
    Semantic weights are photo-owned class observations, not person ID masks.
    Existing per-face operators intersect them with each exact retained geometry.
    """
    if (row.get('trashed') or row.get('copy_number', 0) != 0
            or SOURCE.record(state) is not None or row.get('_people_new_import')
            or row.get('undo') != [] or row.get('redo') != []):
        raise ValueError('Retained group requires prepared unedited originals without history')
    recovery = engine.__dict__.get('_project_recovery_runtime')
    if recovery is not None and recovery.tainted:
        raise ValueError('Uncertain project recovery must be resolved before retained group review')
    fresh = engine._fresh_doc_state()
    omitted = DERIVED_FIELDS | {'_proxy'}
    if (fingerprint({k: v for k, v in state.items() if k not in omitted}) !=
            fingerprint({k: v for k, v in fresh.items() if k not in omitted})
            or state.get('_strength') != 0.0
            or state.get('_deform', {}).get('amounts') != fresh.get('_deform', {}).get('amounts')
            or state.get('_enhance', {}).get('amounts') != fresh.get('_enhance', {}).get('amounts')):
        raise ValueError('Retained group cannot replace an edited target or change legacy scalar skin semantics')
    pc = state.get('_precompute')
    pool = _analysis(pc, state.get('_channel'))
    SOURCE.verify_precompute(state, pc)
    source = SOURCE.row_proof({**row, 'state': state})
    asset = source['asset_sha256']
    context = full.people_context(engine, row)
    graph = context['people_graph']
    faces = sorted((face for face in graph['faces'].values() if face['asset_sha256'] == asset),
                   key=lambda face: face['face_instance_id'])
    run = graph['analysis_runs'].get(asset)
    if (len(faces) != len(pool) or run is None or run['limit_reached']
            or any(face['manual'] or not face['enabled'] for face in faces)):
        raise ValueError('Target detection is limit-hit, manual, disabled or differs from its retained graph')
    ids = {face['face_instance_id'] for face in faces}
    if (any(link['face_instance_id'] in ids for link in graph['links'])
            or any(ids.intersection(group['face_ids']) for group in graph['groups'].values())
            or any(item['scope'] == 'face' and item['target_id'] in ids
                   or item['scope'] == 'all_people' and item['target_id'] == asset
                   for item in graph['overrides'])
            or any(item['asset_sha256'] == asset and item['status'] == 'unresolved'
                   for item in graph['unresolved_legacy'])):
        raise ValueError('Retained group cannot replace existing per-face edits, associations or unresolved intent')
    from .people_binding import evidence
    from .people_render_runtime import verify_analysis
    from .skin_colour_support import check_analysis_fields
    measured = [evidence(pc, points, (row['src_w'], row['src_h'])) for points in pool]
    if any(item['status'] != 'verified' for item in measured) or len({item['landmark_digest'] for item in measured}) != len(measured):
        raise ValueError('Unverified or indistinguishable target face detections require individual review')
    runtime = row.get(V.RUNTIME) if V.is_private(row) else engine.__dict__.get('_people_project_context')
    analyses = (engine.__dict__.get('_people_analyses', {})
                if runtime is not None and runtime is engine.__dict__.get('_people_active_context')
                else (runtime or {}).get('analyses', {})).get(asset, {})
    if set(analyses) != ids:
        raise ValueError('Every retained target face needs its own exact analysis; no silent omission')
    refs = []
    for face in faces:
        if measured.count(face['evidence']) != 1:
            raise ValueError('Retained face does not match exactly one target-owned detection')
        analysis = analyses[face['face_instance_id']]
        if any(analysis.get(key) is None for key in ('skin', 'face_skin', 'excluded')):
            raise ValueError('A target face lacks its own measured skin, face-skin or exclusion support')
        shape = analysis['face_skin'].shape
        verify_analysis(face, analysis, shape)
        if check_analysis_fields(analysis, shape) is None:
            raise ValueError('Target face-skin support lacks genuine source/model observation')
        refs.append(S.face_ref(face))
    return context, refs


class PeoplePreparation(SkinPreparation):
    """Same retained analysis/rollback owner, distinct non-scalar admission."""
    def _require_analysis(self):
        _analysis(self.engine._precompute, self.engine._channel)

    def _require_retained_target(self):
        admit(self.engine, self.row, self.engine._capture_state())
