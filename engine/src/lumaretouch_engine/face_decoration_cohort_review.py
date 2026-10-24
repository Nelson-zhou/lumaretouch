# SPDX-License-Identifier: GPL-3.0-or-later
"""Complete source-first association images with target-owned decoration support. UNRUN."""
from copy import deepcopy
import json
from . import face_decoration_state as D, people_state as S, people_algorithms as A
from .people_resolver import resolve
from . import collarbone_transfer_review as VISUAL
from .face_decoration_batch_plan import coverage as target_coverage
from .face_decoration_batch_review import coverage_checked
from .portrait_review_render import snapshot_key

MAX_MEMBERS=16
ACK='face_decoration_cohort_ack'
UNSUPPORTED={'lnx.torso_length.v1','lnx.waist_length.v1','lnx.head_size.v1','lnx.spill_removal.v1','lnx.original_shadow.v1','lnx.id_background.v1'}


def state(item):
    asset=item['proof']['source_proof']['asset_sha256']
    return {side:[{'face_ref':S.face_ref(face),'recipe':D.check(A.recipes(resolve(item[key],name,A.defaults()))[D.OP])}
        for name,face in sorted(item[key]['faces'].items()) if face['enabled'] and face['asset_sha256']==asset]
        for side,key in (('before','before'),('after','candidate'))}


def checked_state(value,asset):
    if type(value) is not dict or set(value)!={'before','after'}:raise ValueError('Missing actual decoration member scalar state')
    for rows in value.values():
        if type(rows) is not list or not 1<=len(rows)<=64:raise ValueError('Decoration member needs actual enabled source faces')
        ids=[]
        for row in rows:
            if type(row) is not dict or set(row)!={'face_ref','recipe'}:raise ValueError('Invalid decoration member state')
            ref=S.check_ref(row['face_ref']);D.check(row['recipe']);ids.append(ref['face_instance_id'])
            if ref['asset_sha256']!=asset:raise ValueError('Decoration member state borrowed another source')
        if ids!=sorted(set(ids)):raise ValueError('Decoration member faces must be unique and ordered')
    return deepcopy(value)


def content_required(selected,review,states):
    return D.OP in selected['selection'] or any(leaf['op']==D.OP for leaf in review['intent']) or any(
        D.active(row['recipe']) for item in states for rows in item.values() for row in rows)


def required(endpoints,selected,review):
    needed=content_required(selected,review,[state(item) for item in endpoints])
    if needed and (set(selected['selection'])|{leaf['op'] for leaf in review['intent']})&UNSUPPORTED:
        raise ValueError('Decoration cohort cannot bypass another unsupported dedicated review family')
    return needed


def coverage(engine,item):
    payload={'target_refs':[item['ref']]}
    return target_coverage(engine,item['row'],item['before'],item['candidate'],payload)


def snapshots(engine,item):
    return {side:snapshot_key(engine,item['row'],item['row']['state'],item[key]) for side,key in (('before','before'),('after','candidate'))}


def prepare(engine,endpoints,selected,*,existing_displays=None):
    if not 2<=len(endpoints)<=MAX_MEMBERS:raise ValueError('Review source and every decoration association member')
    displays={};total=0
    for item in endpoints:
        doc=item['proof']['document']['document_id'];revision=str(item['proof']['document']['revision'])
        own=coverage(engine,item)
        if existing_displays is None:
            record,display=VISUAL.prepare(engine,item['row'],item['before'],item['candidate'],doc,revision,own)
            display={'revision':revision,'before':display['before'],'after':display['after']}
        else:
            display=existing_displays[doc]
            prior=item.get('eye_bag_cohort_visual') or item.get('portrait_visual') or item.get('collarbone_visual')
            if prior is None:raise ValueError('Shared decoration pixels lack complete graph evidence')
            record={key:deepcopy(prior[key]) for key in VISUAL.FIELDS-{'coverage_sha256'}};record['coverage_sha256']=VISUAL.coverage_digest(own)
            VISUAL.verify(engine,item['row'],item['before'],item['candidate'],doc,revision,own,record)
        total+=len(display['before']['base64'])+len(display['after']['base64'])
        if total>VISUAL.MAX_TOTAL_BASE64:raise ValueError('Complete decoration cohort exceeds display budget; no member or detail omitted')
        item.update(face_decoration_cohort=own,face_decoration_cohort_visual=VISUAL.checked(record),face_decoration_cohort_snapshots=snapshots(engine,item))
        displays[doc]=display
    for item in endpoints:verify(engine,item,item)
    return displays


def verify(engine,item,frozen):
    own=coverage(engine,item)
    if (own!=frozen.get('face_decoration_cohort') or snapshots(engine,item)!=frozen.get('face_decoration_cohort_snapshots')
            or state(item)!=frozen.get('face_decoration_cohort_state')):
        raise ValueError('Decoration cohort source, repair, support, recovery or complete graph changed')
    doc=item['proof']['document']
    return VISUAL.verify(engine,item['row'],item['before'],item['candidate'],doc['document_id'],str(doc['revision']),own,frozen.get('face_decoration_cohort_visual'))


def evidence(item,*,private=False):
    keys=('face_decoration_cohort','face_decoration_cohort_visual')
    if private:keys+=('face_decoration_cohort_snapshots','face_decoration_cohort_state')
    return {key:deepcopy(item[key]) for key in keys if key in item}


def records(plan):
    from .people_cross_owner_workflow import options
    from .people_cross_owner import check_descriptor
    from .people_transfer_inventory import check_proof
    params=plan.params().get('_people_transfer')
    if type(params) is not dict or params.get('mode')!='persistent_association':return None
    selected=options(params.get('options'),list(plan.modules));review=params.get('review')
    if type(review) is not dict or set(review)!={'version','operation','association_id','generation','members','intent'} or review['operation']!=selected['operation'] or review['association_id']!=selected['association_id']:
        raise ValueError('Decoration cohort needs immutable exact association intent')
    capsule=check_descriptor({k:v for k,v in review.items() if k!='operation'}|{'local_document_id':plan.source_id})
    proofs=[selected['source']]+[item['target'] for item in selected['targets']]
    refs=[selected['source_ref']]+[item['target_refs'][0] for item in selected['targets']]
    if (plan.policy!='recheck' or plan.rejected() or not 2<=len(plan.targets)<=MAX_MEMBERS or len(plan.targets)!=len(proofs)
            or plan.targets[0].document_id!=plan.source_id or plan.targets[0].revision!=plan.source_revision
            or plan.targets[0].path!=plan.source_path or any(t.blocked is not None for t in plan.targets)):
        raise ValueError('Decoration cohort requires source first and every exact independent member')
    payloads=[json.loads(t.people_json) for t in plan.targets]
    states=[checked_state(p.get('face_decoration_cohort_state'),proof['source_proof']['asset_sha256']) for p,proof in zip(payloads,proofs)]
    needed=content_required(selected,review,states)
    if type(params.get('face_decoration_cohort_required')) is not bool or params['face_decoration_cohort_required'] is not needed:
        raise ValueError('Decoration cohort flag cannot replace actual retained content')
    if not needed:
        if any(any(k in p for k in ('face_decoration_cohort','face_decoration_cohort_visual','face_decoration_cohort_snapshots')) for p in payloads):raise ValueError('Unrelated cohort cannot carry decoration authority')
        return None
    if (set(selected['selection'])|{leaf['op'] for leaf in review['intent']})&UNSUPPORTED:raise ValueError('Unsupported mixed decoration cohort family')
    members={m['document_id']:m for m in capsule['members']};seen=set();out=[]
    for target,expected,ref,payload,scalar in zip(plan.targets,proofs,refs,payloads,states):
        proof=check_proof(json.loads(target.before_json));asset=proof['source_proof']['asset_sha256']
        if (proof!=expected or proof['document']['document_id']!=target.document_id or proof['document']['revision']!=target.revision
                or proof['document']['epoch']!=plan.workspace or target.document_id in seen or payload.get('ref')!=ref
                or members.get(target.document_id)!={'document_id':target.document_id,'scope_id':proof['people_scope'],'original_sha256':proof['source_proof']['original_sha256'],'ref':ref}):
            raise ValueError('Decoration cohort changed member source, owner, face or ordering')
        S.token(payload.get('person_id'));S.digest(payload.get('candidate_sha256'))
        if target.source_proof_json is not None and json.loads(target.source_proof_json)!=proof['source_proof']:raise ValueError('Decoration cohort frozen source proofs disagree')
        own=coverage_checked(payload.get('face_decoration_cohort'))
        required_ids={ref['face_instance_id']}|{r['face_ref']['face_instance_id'] for rows in scalar.values() for r in rows if D.active(r['recipe'])}
        if {r['face_ref']['face_instance_id'] for r in own['targets']}!=required_ids or any(r['face_ref']['asset_sha256']!=asset for r in own['targets']):raise ValueError('Decoration coverage omitted an active retained member face')
        after={r['face_ref']['face_instance_id']:r for r in scalar['after']}
        for row in own['targets']:
            key=row['face_ref']['face_instance_id'];entry=after.get(key)
            active=any(r['face_ref']==row['face_ref'] and D.active(r['recipe']) for rows in scalar.values() for r in rows)
            if entry is None or entry['face_ref']!=row['face_ref'] or row['recipe_sha256']!=VISUAL.coverage_digest(entry['recipe']) or (row['scope']=='target-reviewed-visible-skin')!=active:raise ValueError('Decoration coverage differs from actual resolved member recipe')
        keys=payload.get('face_decoration_cohort_snapshots')
        if type(keys) is not dict or set(keys)!={'before','after'}:raise ValueError('Both complete render snapshots required')
        for key in keys.values():
            if type(key) is not dict or set(key)!={'render_sha256','context_sha256','graph_sha256'}:raise ValueError('Incomplete decoration render proof')
            for value in key.values():S.digest(value)
        visual=VISUAL.checked(payload.get('face_decoration_cohort_visual'))
        if visual['document_id']!=target.document_id or visual['revision']!=str(target.revision) or visual['source_proof']!=proof['source_proof'] or visual['coverage_sha256']!=VISUAL.coverage_digest(own):raise ValueError('Decoration images differ from member identity')
        for other in ('collarbone_visual','portrait_visual','eye_bag_cohort_visual'):
            if other in payload and any(visual[k]!=payload[other].get(k) for k in VISUAL.FIELDS-{'coverage_sha256'}):raise ValueError('Mixed cohort families must show identical complete images')
        seen.add(target.document_id);out.append(visual)
    if seen!=set(members):raise ValueError('Decoration cohort omitted persistent membership')
    return out


def acknowledgments(raw,rows):
    if not 2<=len(rows)<=MAX_MEMBERS:raise ValueError('Decoration acknowledgment must include source and every member')
    return VISUAL.acknowledgments(raw,rows)


def closure(engine,endpoints):
    from .eye_bag_cohort_review import closure as common
    common(engine,endpoints)


def reconcile(plan,result,retained):
    rows=records(plan)
    if rows is None:
        if ACK in result or 'face_decoration_cohort' in result:raise ValueError('Decoration cohort receipt cannot authorize another plan')
        return None
    ack=acknowledgments(result.get(ACK,retained.get(ACK)),rows)
    if ACK in retained and retained[ACK]!=ack:raise ValueError('Decoration cohort receipt changed claimed image identities')
    if ('module_scope' in result and result['module_scope']!=list(plan.modules)
            or 'face_decoration_cohort' in result and result['face_decoration_cohort'] is not True):raise ValueError('Decoration cohort receipt changed frozen scope')
    result.update(face_decoration_cohort=True,face_decoration_cohort_ack=ack,module_scope=list(plan.modules))
    return ack
