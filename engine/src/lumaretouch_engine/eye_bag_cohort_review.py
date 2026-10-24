# SPDX-License-Identifier: GPL-3.0-or-later
"""Complete source-first eye-bag v2 association review. AUTHORED / UNRUN.

The capsule remains v1 scalar intent. These session-only proofs neither carry
support assets nor grant a generic graph publisher permission to skip review.
"""
from copy import deepcopy
import json
from . import people_state as S, people_algorithms as A, eye_bag_preserve_state as EYE
from . import collarbone_transfer_review as VISUAL
from .people_resolver import resolve
from .portrait_review_render import snapshot_key

MAX_MEMBERS = 16
UNSUPPORTED = {'lnx.torso_length.v1', 'lnx.waist_length.v1', 'lnx.head_size.v1', 'lnx.spill_removal.v1', 'lnx.original_shadow.v1', 'lnx.id_background.v1'}


def options(value, selected):
    if (type(value) is not dict or set(value) != {'version', 'members'}
            or type(value['version']) is not int or value['version'] != 1
            or type(value['members']) is not list or not 2 <= len(value['members']) <= MAX_MEMBERS
            or selected.get('target_policy') != 'persistent_association'):
        raise ValueError('Eye-bag cohort requires explicit source-first member replacement choices')
    expected = [selected['source']['document']['document_id']] + [item['target']['document']['document_id'] for item in selected['targets']]
    actual = []
    for item in value['members']:
        if (type(item) is not dict or set(item) != {'document_id', 'replace_legacy'}
                or type(item['replace_legacy']) is not bool):
            raise ValueError('Each eye-bag cohort member needs its own explicit legacy replacement choice')
        actual.append(S.token(item['document_id']))
    if actual != expected or len(set(actual)) != len(actual):
        raise ValueError('Eye-bag choices must cover source first and every exact association member in review order')
    return deepcopy(value)


def policy(selected, document):
    return next(item['replace_legacy'] for item in options(selected['eye_bag_cohort'], selected)['members'] if item['document_id'] == document)


def state(item):
    return {side: EYE.check(A.recipes(resolve(item[graph], item['ref']['face_instance_id'], A.defaults()))[EYE.OP])
            for side, graph in (('before', 'before'), ('after', 'candidate'))}


def content_required(selected, review, states):
    return (EYE.OP in selected['selection'] or any(leaf['op'] == EYE.OP for leaf in review['intent'])
            or any(EYE.active(EYE.check(recipe)) for item in states for recipe in item.values()))


def required(endpoints, selected, review):
    needed = 'eye_bag_cohort' in selected or content_required(selected, review, [state(item) for item in endpoints])
    if needed and (set(selected['selection']) | {leaf['op'] for leaf in review['intent']}) & UNSUPPORTED:
        raise ValueError('This eye-bag cohort contains a dedicated review family without a supported complete cohort proof')
    return needed


def stage(candidate, item, selected, intent):
    """Only replace this member's legacy scalar, never its local assets/analysis."""
    from .eye_bag_batch_plan import _set
    out = S.check(candidate)
    values = A.recipes(resolve(out, item['ref']['face_instance_id'], A.defaults()))
    if EYE.active(values[EYE.OP]):
        if any(leaf['op'] == A.ENHANCE and leaf['path'] == '/eye_bags' and leaf['value'] > 0 and leaf['path'] in selected['selection'].get(A.ENHANCE, []) for leaf in intent):
            raise ValueError('Active cohort v2 cannot discard selected nonzero legacy eye-bag intent')
        if policy(selected, item['member']['document_id']) and values[A.ENHANCE]['eye_bags'] > 0:
            out = _set(out, item['ref']['face_instance_id'], A.ENHANCE, '/eye_bags', 0.0)
            values = A.recipes(resolve(out, item['ref']['face_instance_id'], A.defaults()))
    EYE.check_coexistence(values[EYE.OP], values[A.ENHANCE]['eye_bags'])
    A.validate_compatibility(values)
    return out


def coverage_checked(value, ref):
    if (type(value) is not dict or set(value) != {'version', 'support_transfer', 'replace_legacy', 'face_ref', 'before', 'after'}
            or type(value['version']) is not int or value['version'] != 1 or value['support_transfer'] != 'none'
            or type(value['replace_legacy']) is not bool or value['face_ref'] != S.check_ref(ref)):
        raise ValueError('Eye-bag cohort requires exact member-owned before and after coverage')
    for side in ('before', 'after'):
        item = value[side]
        if (type(item) is not dict or set(item) != {'scope', 'ridge_sha256', 'sides'}
                or type(item['sides']) is not list or any(type(k) is not str or k not in ('left', 'right') for k in item['sides'])
                or item['sides'] != sorted(set(item['sides']))):
            raise ValueError('Eye-bag cohort side coverage is not exact')
        if item['scope'] == 'neutral-no-effect':
            if item['ridge_sha256'] is not None or item['sides']: raise ValueError('Neutral cohort member cannot claim ridge support')
        elif item['scope'] == 'target-reviewed-ridge':
            S.digest(item['ridge_sha256'])
            if not item['sides']: raise ValueError('Active cohort member requires at least one independently reviewed ridge side')
        else: raise ValueError('Unknown eye-bag cohort support scope')
    return deepcopy(value)


def coverage(engine, item, selected):
    from .full_candidate_render import people_context
    from . import eye_bag_preserve_support as SUPPORT
    context = people_context(engine, item['row']); ref = item['ref']
    value = {'version': 1, 'support_transfer': 'none', 'replace_legacy': policy(selected, item['member']['document_id']), 'face_ref': ref}
    for side, graph in (('before', item['before']), ('after', item['candidate'])):
        face = graph['faces'].get(ref['face_instance_id'])
        if (face is None or S.face_ref(face) != ref or not face['enabled'] or face['evidence']['status'] != 'verified'
                or ref['asset_sha256'] != item['proof']['source_proof']['asset_sha256']):
            raise ValueError('Eye-bag cohort cannot borrow or revive another member source/analysis')
        recipe = EYE.check(A.recipes(resolve(graph, ref['face_instance_id'], A.defaults()))[EYE.OP])
        value[side] = {'scope': 'neutral-no-effect', 'ridge_sha256': None, 'sides': []}
        if EYE.active(recipe):
            support, key = SUPPORT.resolve(graph, context['people_support_assets'], ref)
            value[side] = {'scope': 'target-reviewed-ridge', 'ridge_sha256': key, 'sides': sorted(support['row']['eyes'])}
    return coverage_checked(value, ref)


def snapshots(engine, item):
    return {side: snapshot_key(engine, item['row'], item['row']['state'], item[graph])
            for side, graph in (('before', 'before'), ('after', 'candidate'))}


def prepare(engine, endpoints, selected, *, existing_displays=None):
    if not 2 <= len(endpoints) <= MAX_MEMBERS: raise ValueError('Review source and every eye-bag cohort member')
    displays = {}; total = 0
    for item in endpoints:
        document = item['proof']['document']; doc = document['document_id']; revision = str(document['revision'])
        own = coverage(engine, item, selected); keys = snapshots(engine, item)
        if existing_displays is None:
            record, display = VISUAL.prepare(engine, item['row'], item['before'], item['candidate'], doc, revision, own)
            display = {'revision': revision, 'before': display['before'], 'after': display['after']}
        else:
            display = existing_displays[doc]
            prior = item.get('collarbone_visual') or item.get('portrait_visual')
            if prior is None: raise ValueError('Shared eye-bag cohort images lack independently verified complete-render evidence')
            record = {key: deepcopy(value) for key, value in prior.items() if key in VISUAL.FIELDS}
            record['coverage_sha256'] = VISUAL.coverage_digest(own)
            VISUAL.verify(engine, item['row'], item['before'], item['candidate'], doc, revision, own, record)
        total += len(display['before']['base64']) + len(display['after']['base64'])
        if total > VISUAL.MAX_TOTAL_BASE64: raise ValueError('Complete eye-bag cohort display budget exceeded; no member or detail was omitted')
        item['eye_bag_cohort'] = own; item['eye_bag_cohort_visual'] = VISUAL.checked(record)
        item['eye_bag_cohort_snapshots'] = keys; displays[doc] = display
    for item in endpoints: verify(engine, item, item, selected)
    return displays


def verify(engine, item, frozen, selected):
    own = coverage(engine, item, selected)
    if (own != frozen.get('eye_bag_cohort') or snapshots(engine, item) != frozen.get('eye_bag_cohort_snapshots')
            or state(item) != frozen.get('eye_bag_cohort_state')):
        raise ValueError('Eye-bag cohort source, repair, local support, recovery or full mixed graph changed')
    document = item['proof']['document']
    return VISUAL.verify(engine, item['row'], item['before'], item['candidate'], document['document_id'],
                         str(document['revision']), own, frozen.get('eye_bag_cohort_visual'))


def evidence(item, *, private=False):
    keys = ('eye_bag_cohort', 'eye_bag_cohort_visual')
    if private: keys += ('eye_bag_cohort_snapshots', 'eye_bag_cohort_state')
    return {key: deepcopy(item[key]) for key in keys if key in item}


def records(plan):
    """Derive mandatory review from frozen typed resolved states and scalar intent."""
    from .people_cross_owner_workflow import options as checked_options
    from .people_cross_owner import check_descriptor
    from .people_transfer_inventory import check_proof
    value = plan.params().get('_people_transfer')
    if type(value) is not dict or value.get('mode') != 'persistent_association': return None
    selected = checked_options(value.get('options'), list(plan.modules)); review = value.get('review')
    if (type(review) is not dict or set(review) != {'version', 'operation', 'association_id', 'generation', 'members', 'intent'}
            or review['operation'] != selected['operation'] or review['association_id'] != selected['association_id']):
        raise ValueError('Eye-bag cohort requires the actual immutable association intent')
    capsule = check_descriptor({key: entry for key, entry in review.items() if key != 'operation'} | {'local_document_id': plan.source_id})
    proofs = [selected['source']] + [item['target'] for item in selected['targets']]
    refs = [selected['source_ref']] + [item['target_refs'][0] for item in selected['targets']]
    if (plan.policy != 'recheck' or plan.rejected() or not 2 <= len(plan.targets) <= MAX_MEMBERS or len(plan.targets) != len(proofs)
            or plan.targets[0].document_id != plan.source_id or plan.targets[0].revision != plan.source_revision
            or plan.targets[0].path != plan.source_path or any(target.blocked is not None for target in plan.targets)):
        raise ValueError('Eye-bag association requires source first and every exact atomic member')
    payloads = [json.loads(target.people_json) for target in plan.targets]; states = []
    for payload in payloads:
        raw = payload.get('eye_bag_cohort_state')
        if type(raw) is not dict or set(raw) != {'before', 'after'}: raise ValueError('Missing actual frozen before/after eye-bag scalar recipes')
        states.append({side: EYE.check(recipe) for side, recipe in raw.items()})
    needed = 'eye_bag_cohort' in selected or content_required(selected, review, states)
    if type(value.get('eye_bag_cohort_required')) is not bool or value['eye_bag_cohort_required'] is not needed:
        raise ValueError('Eye-bag cohort flag cannot override actual retained scalar content')
    if not needed:
        if any(any(key in payload for key in ('eye_bag_cohort', 'eye_bag_cohort_visual', 'eye_bag_cohort_snapshots')) for payload in payloads):
            raise ValueError('Generic cohort cannot smuggle eye-bag image authority')
        return None
    if 'eye_bag_cohort' not in selected: raise ValueError('Actual eye-bag cohort requires explicit per-member replacement choices')
    if (set(selected['selection']) | {leaf['op'] for leaf in review['intent']}) & UNSUPPORTED:
        raise ValueError('Eye-bag cohort cannot bypass another dedicated review family')
    members = {item['document_id']: item for item in capsule['members']}; seen = set(); out = []
    for target, expected, ref, payload, scalar in zip(plan.targets, proofs, refs, payloads, states):
        proof = check_proof(json.loads(target.before_json))
        if (type(target.revision) is not int or proof != expected or proof['document']['document_id'] != target.document_id or proof['document']['revision'] != target.revision
                or proof['document']['epoch'] != plan.workspace or target.document_id in seen or payload.get('ref') != ref
                or members.get(target.document_id) != {'document_id': target.document_id, 'scope_id': proof['people_scope'],
                    'original_sha256': proof['source_proof']['original_sha256'], 'ref': ref}
                or ref['asset_sha256'] != proof['source_proof']['asset_sha256']):
            raise ValueError('Eye-bag cohort member changed source, owner, FaceRef or order')
        S.token(payload.get('person_id')); S.digest(payload.get('candidate_sha256'))
        if target.source_proof_json is not None and json.loads(target.source_proof_json) != proof['source_proof']:
            raise ValueError('Eye-bag cohort frozen source proofs disagree')
        own = coverage_checked(payload.get('eye_bag_cohort'), ref)
        if own['replace_legacy'] != policy(selected, target.document_id): raise ValueError('Eye-bag cohort member replacement choice changed')
        for side in ('before', 'after'):
            if (own[side]['scope'] == 'target-reviewed-ridge') != EYE.active(scalar[side]):
                raise ValueError('Eye-bag coverage contradicts actual resolved before/after recipe')
        keys = payload.get('eye_bag_cohort_snapshots')
        if type(keys) is not dict or set(keys) != {'before', 'after'}: raise ValueError('Both full mixed eye-bag render snapshots are mandatory')
        for snapshot in keys.values():
            if type(snapshot) is not dict or set(snapshot) != {'render_sha256', 'context_sha256', 'graph_sha256'}: raise ValueError('Incomplete eye-bag snapshot identity')
            for digest in snapshot.values(): S.digest(digest)
        record = VISUAL.checked(payload.get('eye_bag_cohort_visual'))
        if (record['document_id'] != target.document_id or record['revision'] != str(target.revision)
                or record['source_proof'] != proof['source_proof'] or record['coverage_sha256'] != VISUAL.coverage_digest(own)):
            raise ValueError('Eye-bag cohort image differs from exact reviewed source and local support')
        for other in ('collarbone_visual', 'portrait_visual'):
            if other in payload and any(record[key] != payload[other].get(key) for key in VISUAL.FIELDS - {'coverage_sha256'}):
                raise ValueError('Mixed cohort families must describe the identical complete member image pair')
        seen.add(target.document_id); out.append({'visual': record, 'replace_legacy': own['replace_legacy']})
    if seen != set(members): raise ValueError('Eye-bag cohort cannot omit or invent a persistent member')
    return out


def acknowledgments(raw, rows):
    from .eye_bag_batch_review import acknowledgments as checked_ack
    if not 2 <= len(rows) <= MAX_MEMBERS: raise ValueError('Eye-bag cohort acknowledgment requires every source and target member')
    return checked_ack(raw, rows)


def closure(engine, endpoints):
    from .eye_bag_batch_plan import closure as exact_closure
    plans = {item['member']['scope_id']: {'row': item['row'], 'before': item['before'], 'candidate': item['candidate']} for item in endpoints}
    exact_closure(engine, engine._docs, plans, {item['member']['document_id'] for item in endpoints})
