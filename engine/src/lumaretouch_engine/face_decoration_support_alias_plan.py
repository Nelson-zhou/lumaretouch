# SPDX-License-Identifier: GPL-3.0-or-later
"""Detached visibility-only alias candidate and complete-face coverage. UNRUN.

No scalar recipe, recovery vector, analysis or numerical support is invented.
Absent initial visibility is admissible only for a genuinely neutral before.
"""
from copy import deepcopy
from . import people_state as S, people_support_assets as BANK
from . import face_decoration_state as D, face_decoration_support as SUPPORT
from .face_decoration_batch_plan import recipe
from .collarbone_transfer_review import coverage_digest


def visibility(graph, bank, ref):
    face=graph['faces'][ref['face_instance_id']]
    descriptor=face['local_assets'].get(SUPPORT.KIND)
    if descriptor is None:
        if D.active(recipe(graph,ref['face_instance_id'])):
            raise ValueError('Active decoration has no valid before visibility; support cannot fabricate its before image')
        return None
    _,key=SUPPORT.resolve(graph,bank,ref)
    return key


def narrow(before,candidate,before_assets,assets,ref):
    from .people_graph_patch import between
    from .people_graph_owner import affected_assets
    from .face_style_alias_review import MAX_REVISION
    S.check(before);S.check(candidate);ref=S.check_ref(ref)
    BANK.check_store(before_assets);BANK.check_store(assets)
    face=ref['face_instance_id']
    if (face not in before['faces'] or face not in candidate['faces']
            or S.face_ref(before['faces'][face])!=ref or S.face_ref(candidate['faces'][face])!=ref):
        raise ValueError('Support aliases require the unchanged selected retained face')
    old_key=visibility(before,before_assets,ref)
    _,key=SUPPORT.resolve(candidate,assets,ref)
    if old_key is not None and before_assets[old_key]['row']['region']==assets[key]['row']['region']:
        raise ValueError('Identical painted visibility is not a support alias transaction')
    expected=deepcopy(before);expected['revision']=candidate['revision']
    expected['faces'][face]['local_assets'][SUPPORT.KIND]=deepcopy(candidate['faces'][face]['local_assets'][SUPPORT.KIND])
    if (candidate!=expected or candidate['revision']!=before['revision']+1 or candidate['revision']>MAX_REVISION
            or not between(before,candidate) or affected_assets(before,candidate)!={ref['asset_sha256']}):
        raise ValueError('Support aliases may change only one nonempty selected visibility pointer')
    if any(assets.get(k)!=value for k,value in before_assets.items()):
        raise ValueError('Support aliases cannot overwrite or remove immutable assets')
    if set(assets)-set(before_assets)!={key}-set(before_assets):
        raise ValueError('Support candidate contains unrelated or unreviewed assets')


def coverage(before,candidate,before_assets,assets,ref):
    ref=S.check_ref(ref);asset=ref['asset_sha256'];ids={ref['face_instance_id']}
    for graph in (before,candidate):
        ids.update(key for key,face in graph['faces'].items()
            if face['enabled'] and face['asset_sha256']==asset and D.active(recipe(graph,key)))
    if len(ids)>64:raise ValueError('Support alias complete-face coverage exceeds its bounded review; no face was omitted')
    rows=[]
    for key in sorted(ids):
        left=before['faces'].get(key);right=candidate['faces'].get(key)
        if (left is None or right is None or not left['enabled'] or not right['enabled']
                or S.face_ref(left)!=S.face_ref(right) or left['asset_sha256']!=asset):
            raise ValueError('Support alias complete-face coverage changed ownership')
        own=S.face_ref(left);a=visibility(before,before_assets,own);b=visibility(candidate,assets,own)
        if key!=ref['face_instance_id'] and a!=b:
            raise ValueError('Support aliases cannot replace another face visibility')
        left_recipe=D.check(recipe(before,key));right_recipe=D.check(recipe(candidate,key))
        if left_recipe!=right_recipe:raise ValueError('Support aliases cannot alter decoration recipes')
        rows.append({'face_ref':own,'before_visibility_sha256':a,'visibility_sha256':b,
            'before_recipe_sha256':coverage_digest(left_recipe),'recipe_sha256':coverage_digest(right_recipe)})
    return {'version':1,'support_change':'selected-face-only','targets':rows}


def staged_context(engine,row,candidate,before_assets,assets):
    from .full_candidate_render import people_context
    context=people_context(engine,row)
    if context['people_support_assets']!=before_assets:
        raise ValueError('Support alias member belongs to a different immutable support bank')
    context['people_graph']=deepcopy(candidate);context['people_support_assets']=deepcopy(assets)
    return context
