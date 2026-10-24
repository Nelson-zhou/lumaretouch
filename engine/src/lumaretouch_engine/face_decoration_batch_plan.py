# SPDX-License-Identifier: GPL-3.0-or-later
"""Complete ordinary portrait-only target review; no second transaction owner."""
from copy import deepcopy
from dataclasses import replace
import json
from . import people_state as S
from . import face_decoration_state as D, face_decoration_batch_review as REVIEW
from . import virtual_copy_people as V, creative_derived_source as SOURCE
from . import collarbone_transfer_review as VISUAL
from .batch_preflight import canonical
from .portrait_review_render import snapshot_key


def recipe(graph, face):
    from .face_decoration_scope import resolved_recipe
    return resolved_recipe(graph,face)


def active(graph, asset):
    return any(face['enabled'] and face['asset_sha256']==asset and D.active(recipe(graph,key))
               for key,face in graph['faces'].items())


def needed(before, candidate, payload):
    asset=payload['target_owner']['source_proof']['asset_sha256']
    return (any(leaf['operation_id']==D.OP for leaf in payload['parameters'])
            or active(before,asset) or active(candidate,asset))


def coverage(engine,row,before,candidate,payload):
    from .full_candidate_render import people_context
    from .face_decoration_support import resolve
    asset=SOURCE.row_proof(row)['asset_sha256']; ids={ref['face_instance_id'] for ref in payload['target_refs']}
    for graph in (before,candidate):
        ids.update(key for key,face in graph['faces'].items() if face['enabled'] and face['asset_sha256']==asset and D.active(recipe(graph,key)))
    context=people_context(engine,row); rows=[]
    for key in sorted(ids):
        face=candidate['faces'].get(key); old=before['faces'].get(key)
        if (face is None or old is None or S.face_ref(face)!=S.face_ref(old)
                or not face['enabled'] or not old['enabled'] or face['asset_sha256']!=asset):
            raise ValueError('Decoration target face ownership changed')
        ref=S.face_ref(face); values=D.check(recipe(candidate,key)); support=None
        needs=D.active(values) or D.active(recipe(before,key))
        if needs:
            _,support=resolve(candidate,context['people_support_assets'],ref)
            _,old_support=resolve(before,context['people_support_assets'],ref)
            if support!=old_support: raise ValueError('Scalar transfer cannot modify decoration visibility')
        rows.append({'face_ref':ref,'scope':'target-reviewed-visible-skin' if needs else 'neutral-no-effect',
                     'visibility_sha256':support,'recipe_sha256':VISUAL.coverage_digest(values)})
    return REVIEW.coverage_checked({'version':1,'support_transfer':'none','targets':rows})


def snapshots(engine,row,before,candidate):
    return {'before':snapshot_key(engine,row,row['state'],before),'after':snapshot_key(engine,row,row['state'],candidate)}


def closure(engine,rows,plans):
    from .face_decoration_project import require_unaliased
    from .face_style_alias_review import verify_dormant
    from .people_graph_owner import affected_assets
    for item in plans.values():
        assets=affected_assets(item['before'],item['candidate'])
        verify_dormant(engine,item['row'],assets)
        require_unaliased(engine,item['row'],assets)


def visuals(engine,rows,targets,public,selected,rejected):
    from .people_transfer_adapter import stage
    from .eye_bag_batch_plan import ADMISSION
    if (selected['target_policy']!='explicit_face_map' or 'face_style' in selected or rejected
            or any(t.blocked for t in targets) or not 1<=len(targets)<=REVIEW.MAX_TARGETS):
        raise ValueError('Decoration requires the complete ordinary explicit target set; no target omitted')
    plans={}
    for target in targets:
        row=rows[target.index]; graph=V.row_snapshot(engine,row); payload=json.loads(target.people_json); key=V.scope(row)
        prior=plans.get(key)
        if prior and prior['before']!=graph: raise ValueError('Decoration owner changed during aggregation')
        candidate=stage(payload,graph if prior is None else prior['candidate'],eye_bag_review=ADMISSION if 'eye_bag' in payload else None)
        plans[key]={'row':row,'before':graph,'candidate':candidate}
    closure(engine,rows,plans); frozen=[]; displays={}; total=0
    for target,visible in zip(targets,public):
        row=rows[target.index]; plan=plans[V.scope(row)]; payload=json.loads(target.people_json)
        own=coverage(engine,row,plan['before'],plan['candidate'],payload)
        keys=snapshots(engine,row,plan['before'],plan['candidate'])
        visual,display=VISUAL.prepare(engine,row,plan['before'],plan['candidate'],target.document_id,str(target.revision),own)
        total+=len(display['before']['base64'])+len(display['after']['base64'])
        if total>VISUAL.MAX_TOTAL_BASE64: raise ValueError('Decoration images exceed bounded preparation budget; no downsampling substitute')
        payload.update(face_decoration_coverage=own,face_decoration_visual=visual)
        before=json.loads(target.before_json); before['face_decoration_snapshots']=keys
        frozen.append(replace(target,people_json=canonical(payload),before_json=canonical(before)))
        visible['people_transfer']=deepcopy(payload)
        displays[target.document_id]={'revision':str(target.revision),'before':display['before'],'after':display['after']}
    for target in frozen:
        row=rows[target.index]; plan=plans[V.scope(row)]
        if V.row_snapshot(engine,row)!=plan['before']: raise ValueError('Decoration owner changed during review')
        verify(engine,row,plan,target,json.loads(target.people_json))
    closure(engine,rows,plans)
    return frozen,displays


def verify(engine,row,plan,target,payload):
    own=coverage(engine,row,plan['before'],plan['candidate'],payload)
    if (own!=payload.get('face_decoration_coverage') or snapshots(engine,row,plan['before'],plan['candidate'])
            !=json.loads(target.before_json).get('face_decoration_snapshots')):
        raise ValueError('Decoration source, repair, support or full recipe changed; review again')
    VISUAL.verify(engine,row,plan['before'],plan['candidate'],target.document_id,str(target.revision),own,payload['face_decoration_visual'])


def require_generic_safe(engine,row):
    graph=V.peek_graph(engine,row)
    if graph is not None and active(graph,SOURCE.row_proof(row)['asset_sha256']):
        raise ValueError('Retained decorations require explicit portrait target mapping and complete image review; generic whole-state batch remains unavailable')
