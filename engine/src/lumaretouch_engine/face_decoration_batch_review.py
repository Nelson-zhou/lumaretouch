# SPDX-License-Identifier: GPL-3.0-or-later
"""Exact ordinary target-owned decoration review. Source only / UNRUN."""
from copy import deepcopy
import json
from . import people_state as S, collarbone_transfer_review as VISUAL
from .face_decoration_state import OP

MAX_TARGETS = 16
ACK = 'face_decoration_review_ack'
checked = VISUAL.checked
acknowledgments = VISUAL.acknowledgments


def coverage_checked(value):
    if (type(value) is not dict or set(value) != {'version','support_transfer','targets'}
            or type(value['version']) is not int or value['version'] != 1
            or value['support_transfer'] != 'none' or type(value['targets']) is not list
            or not 1 <= len(value['targets']) <= 64):
        raise ValueError('Decoration review needs exact target-local visible-skin coverage')
    ids=[]
    for item in value['targets']:
        if type(item) is not dict or set(item) != {'face_ref','scope','visibility_sha256','recipe_sha256'}:
            raise ValueError('Invalid decoration coverage row')
        ref=S.check_ref(item['face_ref']); ids.append(ref['face_instance_id']); S.digest(item['recipe_sha256'])
        if item['scope']=='target-reviewed-visible-skin': S.digest(item['visibility_sha256'])
        elif item['scope']=='neutral-no-effect':
            if item['visibility_sha256'] is not None: raise ValueError('Neutral coverage cannot invent visibility')
        else: raise ValueError('Unknown decoration coverage scope')
    if ids!=sorted(set(ids)): raise ValueError('Decoration faces must be unique and canonically ordered')
    return deepcopy(value)


def required(plan):
    p=plan.params().get('_people_transfer')
    return type(p) is dict and p.get('face_decoration_visual_required') is True


def records(plan):
    params=plan.params().get('_people_transfer')
    if type(params) is dict and params.get('mode')=='persistent_association':
        if params.get('face_decoration_visual_required') is True:raise ValueError('Ordinary decoration proof cannot authorize a cohort')
        return None
    if not required(plan):
        if OP in plan.modules: raise ValueError('Decoration batch requires actual image review')
        return None
    p=plan.params()['_people_transfer']; selected=p.get('options',{})
    if (p.get('mode')=='persistent_association' or selected.get('target_policy')!='explicit_face_map'
            or 'face_style' in selected or not 1<=len(plan.targets)<=MAX_TARGETS
            or plan.rejected() or any(t.blocked for t in plan.targets)):
        raise ValueError('Decoration review requires every ordinary explicit target, no aliases or cohorts')
    expected={x['target']['document']['document_id']:x for x in selected['targets']}
    if set(expected)!={t.document_id for t in plan.targets} or len(expected)!=len(plan.targets):
        raise ValueError('Decoration image set must exactly cover the selected documents')
    out=[]
    for target in plan.targets:
        payload=json.loads(target.people_json); mapping=expected[target.document_id]
        coverage=coverage_checked(payload.get('face_decoration_coverage'))
        record=checked(payload.get('face_decoration_visual'))
        refs={item['face_ref']['face_instance_id']:item['face_ref'] for item in coverage['targets']}
        if any(refs.get(ref['face_instance_id'])!=ref for ref in mapping['target_refs']):
            raise ValueError('Decoration coverage omitted a mapped target face')
        before=json.loads(target.before_json); snapshots=before.get('face_decoration_snapshots')
        if type(snapshots) is not dict or set(snapshots)!={'before','after'}:
            raise ValueError('Decoration review needs complete before/after snapshot proofs')
        for snap in snapshots.values():
            if type(snap) is not dict or set(snap)!={'render_sha256','context_sha256','graph_sha256'}:
                raise ValueError('Decoration snapshot must retain full source, repair and graph')
            for key in snap.values(): S.digest(key)
        if (payload.get('target_policy')!='explicit_face_map' or payload.get('target_refs')!=mapping['target_refs']
                or payload.get('target_owner')!=mapping['target'] or payload.get('source_owner')!=selected['source']
                or record['document_id']!=target.document_id or record['revision']!=str(target.revision)
                or record['source_proof']!=before.get('source_proof')
                or record['source_proof']!=mapping['target']['source_proof']
                or record['coverage_sha256']!=VISUAL.coverage_digest(coverage)
                or any(item['face_ref']['asset_sha256']!=record['source_proof']['asset_sha256'] for item in coverage['targets'])):
            raise ValueError('Decoration images, source and coverage have different owners')
        for field in ('collarbone_visual','eye_bag_visual'):
            if field in payload:
                other=checked(payload[field])
                if any(record[k]!=other[k] for k in VISUAL.FIELDS-{'coverage_sha256'}):
                    raise ValueError('Mixed families must review the same complete target images')
        out.append(record)
    return out


def reconcile(plan, result, retained):
    values=records(plan)
    if values is None:
        if ACK in result: raise ValueError('Decoration ACK cannot authorize another frozen plan')
        return None
    ack=acknowledgments(result.get(ACK,retained.get(ACK)),values)
    if ACK in retained and retained[ACK]!=ack: raise ValueError('Decoration receipt changed its claimed acknowledgment')
    result.update({ACK:ack,'module_scope':list(plan.modules),'face_decoration_visual_required':True})
    return ack
