"""Atomic cohort validation at the existing graph publication boundary.

This is not another registry or undo owner. Person capsules travel in ordinary
protected graph patches; both forward publication and history replay must carry
every participant when their common accepted content changes.
"""
from . import people_state as S


def _capsules(graph):
    from .people_cross_owner import check_descriptor
    result = {}
    for person in S.check(graph)['persons'].values():
        if 'cross_owner' not in person:
            continue
        capsule = check_descriptor(person['cross_owner'])
        identity = capsule['association_id']
        if identity in result:
            raise ValueError('Duplicate persistent person association in one owner')
        result[identity] = capsule
    return result


def validate_plans(plans, targets):
    """Reject incomplete cohorts before any graph or document fence advances."""
    owners = {}
    touched = set()
    for scope, plan in plans.items():
        identity = plan['row']['document_id']
        if identity in owners:
            raise ValueError('Persistent association repeats a document owner')
        before, after = _capsules(plan['before']), _capsules(plan['candidate'])
        owners[identity] = (scope, plan, before, after)
        touched.update(key for key in set(before) | set(after)
                       if before.get(key) != after.get(key))
    for association in touched:
        relevant = [entry for entry in owners.values()
                    if association in entry[2] or association in entry[3]]
        for offset in (2, 3):
            capsules = [entry[offset][association] for entry in relevant
                        if association in entry[offset]]
            if not capsules:
                continue  # Explicit creation or unlink of the entire cohort.
            common = capsules[0]
            members = common['members']
            if len(capsules) != len(members):
                raise ValueError('Persistent association history requires every owner atomically')
            expected_ids = {member['document_id'] for member in members}
            if {capsule['local_document_id'] for capsule in capsules} != expected_ids:
                raise ValueError('Persistent association history changed its owner membership')
            if any(capsule['members'] != members or capsule['intent'] != common['intent']
                   or capsule['generation'] != common['generation'] for capsule in capsules):
                raise ValueError('Persistent association projections disagree')
            for member in members:
                identity = member['document_id']
                scope, plan, before, after = owners[identity]
                capsule = (before if offset == 2 else after).get(association)
                if scope != member['scope_id'] or capsule is None or capsule['local_document_id'] != identity:
                    raise ValueError('Persistent association capsule belongs to another owner')
                matches = [target for target in targets.values()
                           if target['document_id'] == identity and target['people_scope'] == scope]
                if len(matches) != 1:
                    raise ValueError('Persistent association participant is missing or dormant')
                target = matches[0]
                proof = target.get('source_proof') or {}
                if (proof.get('asset_sha256') != member['ref']['asset_sha256']
                        or proof.get('original_sha256') != member['original_sha256']
                        or member['ref'] not in target.get('reviewed_face_refs', [])):
                    raise ValueError('Persistent association participant source or analysis changed')
                graph = plan['before'] if offset == 2 else plan['candidate']
                face = graph['faces'].get(member['ref']['face_instance_id'])
                if (face is None or S.face_ref(face) != member['ref'] or not face['enabled']
                        or face['evidence']['status'] != 'verified'):
                    raise ValueError('Persistent association needs its exact independently analysed face')
        before_capsules = [entry[2][association] for entry in relevant if association in entry[2]]
        after_capsules = [entry[3][association] for entry in relevant if association in entry[3]]
        if before_capsules and after_capsules and before_capsules[0]['members'] != after_capsules[0]['members']:
            raise ValueError('Persistent association membership expansion requires a separate reviewed operation')
