"""Selection-independent, revision-pinned plan for existing portrait consumers.

No geometry is executed here. Adapters must compose per-face fields from the same
frozen source, then sample original RGB8/16 exactly once with the combined field.
A plan is NOT evidence that those adapters have been integrated or validated.
"""
from . import people_state as S
from .people_resolver import resolve

FIELD_ORDER = ('deform', 'brow_shape', 'nose_shape', 'eye_shape', 'mouth_shape')
OVERLAP_POLICY = 'stable_instance_priority_partition'


def build(state, asset_sha256, defaults, *, max_faces, per_face_cost, total_budget,
          available_evidence, operation_check):
    """operation_check(face, resolved) returns explicit consumer refusal strings.

    available_evidence maps stable face IDs to exact FaceRef and actual evidence.
    The editing cursor is intentionally not an argument. Every enabled face gets
    either a render entry or an explicit refusal, never an omitted implicit face.
    """
    state = S.check(state); S.digest(asset_sha256)
    for n in (max_faces, per_face_cost, total_budget):
        if type(n) is not int or n < 0: raise ValueError('Render budgets must be explicit')
    entries = []; used = 0; admitted = 0
    for key, face in sorted(state['faces'].items()):
        if face['asset_sha256'] != asset_sha256 or not face['enabled']: continue
        resolved = resolve(state, key, defaults); reasons = []
        required = bool(face['local_assets']) or any(
            operation not in defaults or path not in defaults[operation] or record['value'] != defaults[operation][path]
            for operation,leaves in resolved['operations'].items() for path,record in leaves.items()
            # New v2 link state is interaction intent, not a rendered effect.
            # Ignore only this exact valid boolean leaf; nonzero side amounts,
            # unknown/malformed leaves, other operations and owned assets keep
            # their existing evidence requirements. Canonical recipe validation
            # still runs even for an otherwise neutral render entry.
            if not (operation == 'lnx.slim_face.v2' and path == '/linked'
                    and type(record['value']) is bool))
        actual = available_evidence.get(key)
        if required and face['evidence']['status'] != 'verified': reasons.append('face_analysis_unresolved_or_synthetic')
        if required and (actual is None or actual.get('face_ref') != S.face_ref(face) or actual.get('evidence') != face['evidence']):
            reasons.append('frozen_source_analysis_missing_or_stale')
        if resolved['conflicts']: reasons.append('ambiguous_parameter_inheritance')
        if not reasons:
            consumer_reasons = operation_check(face, resolved)
            if type(consumer_reasons) is not list or any(type(x) is not str for x in consumer_reasons):
                raise ValueError('Consumer readiness must report a list of refusal reasons')
            reasons.extend(consumer_reasons)
        if required and (admitted >= max_faces or used + per_face_cost > total_budget): reasons.append('portrait_render_budget_exceeded')
        if not reasons and required: used += per_face_cost; admitted += 1
        entries.append({'face_ref': S.face_ref(face), 'resolved': resolved,
                        'status': 'refused' if reasons else 'ready', 'reasons': reasons, 'requires_analysis': required,
                        'local_assets': face['local_assets'], 'overlap_rank': len(entries)})
    return {'version': 1, 'asset_sha256': asset_sha256, 'state_revision': state['revision'],
            'association_revision': state['association_revision'], 'entries': entries,
            'field_order': list(FIELD_ORDER), 'overlap_policy': OVERLAP_POLICY,
            'sample_policy': 'one_original_source_sample_after_composed_field',
            'mask_policy': 'same_composed_field_for_source_masks_and_deltas',
            'budget_used': used, 'refused_count': sum(x['status'] == 'refused' for x in entries),
            'requires_explicit_partial_acceptance': any(x['status'] == 'refused' for x in entries)}


def assert_current(plan, state):
    state = S.check(state)
    if (plan['state_revision'], plan['association_revision']) != (state['revision'], state['association_revision']):
        raise ValueError('People render plan is stale')
    expected = {k for k, f in state['faces'].items() if f['asset_sha256'] == plan['asset_sha256'] and f['enabled']}
    if {x['face_ref']['face_instance_id'] for x in plan['entries']} != expected:
        raise ValueError('Render plan does not cover all enabled source faces')
    for entry in plan['entries']:
        face = state['faces'][entry['face_ref']['face_instance_id']]
        if entry['face_ref'] != S.face_ref(face): raise ValueError('Face analysis changed after freeze')
