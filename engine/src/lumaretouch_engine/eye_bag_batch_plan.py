# SPDX-License-Identifier: GPL-3.0-or-later
"""Target-owned eye-bag scalar staging under the existing frozen batch. UNRUN.

ADMISSION is process-local planner authority, never a serializable review flag.
Only the ordinary explicit batch flow obtains it; image metadata is not authority.
"""
from copy import deepcopy
from dataclasses import replace
import json
from . import people_state as S, people_algorithms as A, virtual_copy_people as V
from . import eye_bag_preserve_state as EYE, eye_bag_batch_review as REVIEW
from . import creative_derived_source as SOURCE
from .people_resolver import resolve
from .portrait_review_render import snapshot_key
from .batch_preflight import canonical

ADMISSION = object()


def _set(graph, face, operation, path, value):
    # Preserve ordering and revision for an exact existing replacement. A no-op
    # must not become an affected alias merely because an override was appended.
    for item in graph['overrides']:
        if (item['scope'], item['target_id'], item['operation_id'], item['parameter_path']) == ('face', face, operation, path):
            same_domain = (type(item['value']) is type(value)
                           or type(item['value']) in (int, float) and type(value) in (int, float))
            if same_domain and item['value'] == value: return graph
    return S.set_override(graph, 'face', face, operation, path, value)


def stage(payload, graph, admission):
    if admission is not ADMISSION:
        raise ValueError('Eye-bag scalar transfer requires the dedicated full-target batch planner')
    choice = REVIEW.choice(payload.get('eye_bag'))
    if (payload.get('target_policy') != 'explicit_face_map' or not payload.get('source_owner')
            or not payload.get('target_owner') or not any(leaf['operation_id'] == EYE.OP for leaf in payload['parameters'])):
        raise ValueError('Eye-bag review requires exact owner-qualified target face maps')
    out = S.check(graph)
    for ref in payload['target_refs']:
        for leaf in payload['parameters']:
            out = _set(out, ref['face_instance_id'], leaf['operation_id'], leaf['parameter_path'], leaf['value'])
    selected_legacy = [leaf for leaf in payload['parameters']
        if leaf['operation_id'] == A.ENHANCE and leaf['parameter_path'] == '/eye_bags']
    for ref in payload['target_refs']:
        values = A.recipes(resolve(out, ref['face_instance_id'], A.defaults()))
        recipe = EYE.check(values[EYE.OP])
        if EYE.active(recipe):
            if selected_legacy and selected_legacy[0]['value'] > 0:
                raise ValueError('Selected nonzero legacy eye-bag intent conflicts with active v2; choose one, no selected leaf was dropped')
            if choice['replace_legacy'] and values[A.ENHANCE]['eye_bags'] > 0:
                out = _set(out, ref['face_instance_id'], A.ENHANCE, '/eye_bags', 0.0)
                values = A.recipes(resolve(out, ref['face_instance_id'], A.defaults()))
        EYE.check_coexistence(recipe, values[A.ENHANCE]['eye_bags'])
        A.validate_compatibility(values)
    return out


def coverage(engine, row, candidate, payload):
    from .full_candidate_render import people_context
    from . import eye_bag_preserve_support as SUPPORT
    context = people_context(engine, row)
    proof = SOURCE.row_proof(row)
    items = []
    for ref in payload['target_refs']:
        ref = S.check_ref(ref); face = candidate['faces'].get(ref['face_instance_id'])
        if (face is None or S.face_ref(face) != ref or not face['enabled']
                or face['evidence']['status'] != 'verified' or ref['asset_sha256'] != proof['asset_sha256']):
            raise ValueError('Eye-bag target requires its existing exact enabled source-owned face')
        values = A.recipes(resolve(candidate, ref['face_instance_id'], A.defaults()))
        A.validate_compatibility(values)
        item = {'face_ref': deepcopy(ref), 'scope': 'neutral-no-effect', 'ridge_sha256': None, 'sides': []}
        if EYE.active(values[EYE.OP]):
            record, key = SUPPORT.resolve(candidate, context['people_support_assets'], ref)
            item.update(scope='target-reviewed-ridge', ridge_sha256=key, sides=sorted(record['row']['eyes']))
        items.append(item)
    return REVIEW.coverage_checked({'version': 1, 'support_transfer': 'none', 'targets': items}, payload['target_refs'])


def snapshots(engine, row, before, candidate):
    return {'before': snapshot_key(engine, row, row['state'], before),
            'after': snapshot_key(engine, row, row['state'], candidate)}


def closure(engine, rows, plans, reviewed):
    from .people_graph_owner import affected_assets
    from .face_style_alias_review import verify_dormant
    for identity, plan in plans.items():
        assets = affected_assets(plan['before'], plan['candidate'])
        verify_dormant(engine, plan['row'], assets)
        for row in rows:
            if V.scope(row) == identity and SOURCE.row_proof(row)['asset_sha256'] in assets:
                if engine._document_versions().version(row).document_id not in reviewed:
                    raise ValueError('Eye-bag batch affects an unreviewed shared-source document; review every alias or use independent copies')


def visuals(engine, rows, targets, public):
    from . import collarbone_transfer_review as VISUAL
    if len(targets) > REVIEW.MAX_TARGETS: raise ValueError('Eye-bag batch supports at most sixteen exact target documents')
    plans = {}; policies = {}
    for target in targets:
        if target.blocked: continue
        row = rows[target.index]; before = V.row_snapshot(engine, row); identity = V.scope(row)
        payload = json.loads(target.people_json)
        alias = (identity, payload['target_owner']['source_proof']['asset_sha256'])
        policy = REVIEW.choice(payload['eye_bag'])
        if alias in policies and policies[alias] != policy:
            raise ValueError('Shared-source aliases require the same explicit legacy replacement choice')
        policies[alias] = policy
        previous = plans.get(identity)
        if previous is not None and previous['before'] != before: raise ValueError('Eye-bag target owner changed during aggregation')
        candidate = stage(json.loads(target.people_json), before if previous is None else previous['candidate'], ADMISSION)
        plans[identity] = {'row': row, 'before': before, 'candidate': candidate}
    closure(engine, rows, plans, {target.document_id for target in targets if not target.blocked})
    frozen = []; displays = {}; total = 0
    for target, visible in zip(targets, public):
        if target.blocked: frozen.append(target); continue
        row = rows[target.index]; payload = json.loads(target.people_json); plan = plans[V.scope(row)]
        own_coverage = coverage(engine, row, plan['candidate'], payload)
        if own_coverage != payload.get('eye_bag_coverage'): raise ValueError('Eye-bag target support changed during aggregate rendering')
        keys = snapshots(engine, row, plan['before'], plan['candidate'])
        record, display = VISUAL.prepare(engine, row, plan['before'], plan['candidate'], target.document_id, str(target.revision), own_coverage)
        total += len(display['before']['base64']) + len(display['after']['base64'])
        if total > VISUAL.MAX_TOTAL_BASE64: raise ValueError('Eye-bag display budget exceeded; no target was omitted or detail reduced')
        payload['eye_bag_visual'] = record
        before = json.loads(target.before_json); before['eye_bag_snapshots'] = keys
        frozen.append(replace(target, people_json=canonical(payload), before_json=canonical(before)))
        visible['people_transfer'] = deepcopy(payload)
        displays[target.document_id] = {'revision': str(target.revision), 'before': display['before'], 'after': display['after']}
    for target in frozen:
        if target.blocked: continue
        row = rows[target.index]; plan = plans[V.scope(row)]
        if V.row_snapshot(engine, row) != plan['before']: raise ValueError('Eye-bag owner changed while other targets rendered')
        verify(engine, row, plan, target, json.loads(target.people_json))
    closure(engine, rows, plans, {target.document_id for target in targets if not target.blocked})
    return frozen, displays


def verify(engine, row, scoped, target, payload):
    from . import collarbone_transfer_review as VISUAL
    own_coverage = coverage(engine, row, scoped['candidate'], payload)
    if (own_coverage != payload.get('eye_bag_coverage')
            or snapshots(engine, row, scoped['before'], scoped['candidate']) != json.loads(target.before_json).get('eye_bag_snapshots')):
        raise ValueError('Eye-bag target complete source, repair, support or mixed graph changed; review again')
    VISUAL.verify(engine, row, scoped['before'], scoped['candidate'], target.document_id, str(target.revision), own_coverage, payload['eye_bag_visual'])
