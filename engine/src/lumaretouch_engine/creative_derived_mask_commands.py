"""Exact local-mask admission on the immutable effective source.

Native capture, preview, mutation and history owners remain authoritative. This
module cannot redeem a repair capture or invent semantic/prompted evidence.
"""
import hashlib
import json
import re
from .source_patch_controller import PROOF_KEYS

COMMANDS=frozenset(('source_patch_capture','local_masks','prompted_masks','local_grade_live','grade'))


def require_pixels(engine):
    import numpy as np
    from .creative_derived_source import analysis_rgb
    rgb=analysis_rgb(engine);source=getattr(getattr(engine,'_vram',None),'src_f32',None)
    if source is None or tuple(source.shape)!=(1,3,*rgb.shape[:2]):
        raise ValueError('Local-mask capture has another effective source extent')
    actual=source[0].permute(1,2,0).detach().cpu().numpy()
    if actual.dtype!=np.float32 or not np.allclose(actual,rgb.astype(np.float32)/255.,rtol=0,atol=np.finfo(np.float32).eps):
        raise ValueError('Local-mask pixels differ from the immutable derived source')


def validate_state(engine):
    from .creative_derived_source import binding
    from .creative_derived_masks import validate
    from .local_grade_layers import check
    source=binding(engine)
    validate(getattr(engine,'_local_masks',None),source)
    for layer in check(getattr(engine,'_local_grade_layers',None))['layers']:
        validate(layer['mask'],source)


def capture_binding(engine,capture):
    from .creative_derived_source import binding
    source=binding(engine)
    if capture.get('effective_source')!=source:
        raise ValueError('Mask capture belongs to another effective source')
    descriptor=capture['descriptor']
    if descriptor['domain']!='source-input' or descriptor['full_source']!=[source['width'],source['height']]:
        raise ValueError('Derived masks require full-source input capture, never repair input')
    return source


def _matching(engine,request,*,recipe=True,presented=True):
    capture=engine._source_patch_controller().capture._matching(request,recipe=recipe)
    capture_binding(engine,capture)
    if presented and not capture['eligible']:raise ValueError('Present the current source capture before editing masks')
    return capture


def _identity(value):
    if type(value) is not str or not 1<=len(value)<=128:raise ValueError('Invalid local-mask request identity')


def _receipt(engine,attribute,field,request):
    owner=engine.__dict__.get(attribute)
    row=getattr(owner,field,{}).get(request['request_id'])
    if row is None:return False
    digest=hashlib.sha256(json.dumps(request,sort_keys=True,allow_nan=False).encode()).hexdigest()
    if row[0]!=digest:raise ValueError('Local request identity reused with different content')
    return True


def _mutation(value,*,inner=False):
    if type(value) is not dict:raise ValueError('Mask mutation must be explicit')
    fields={'upsert':{'action','object','coordinate_space'},'delete':{'action','id'},
        'move':{'action','id','index'},'bind':{'action','enabled'},'clear':{'action'},
        'accept_prompted':{'action','preview_id','candidate','id','name','operation','opacity','feather'},
        'layer_update':{'action','id','name','enabled','grade'},'layer_delete':{'action','id'},
        'layer_move':{'action','id','index'},'layer_mask':{'action','id','mutation'}}
    action=value.get('action')
    if action not in fields or set(value)!=fields[action] or (inner and action not in ('upsert','delete','move')):
        raise ValueError('Unadapted local-mask mutation')
    if action=='layer_mask':_mutation(value['mutation'],inner=True)
    if action=='upsert':
        from .local_mask_recipe import check_stack
        check_stack({'version':1,'domain':'source-normalized','objects':[value['object']]})
        if value['coordinate_space'] not in ('capture','source'):raise ValueError('Unknown mask coordinate domain')


def _capture_command(engine,p):
    from .source_patch_capture import _hex,_uint
    action=p.get('action');fields={'cmd','action','capture_id','ticket','document_id'}
    fields|={'epoch','purpose'} if action=='arm' else ({'generation'} if action!='cancel' or 'generation' in p else set())
    if action=='arm' and 'group_id' in p:fields.add('group_id')
    if action not in ('arm','presented','cancel') or set(p)!=fields:
        raise ValueError('Derived mask capture requires its exact source-input envelope')
    if not _hex(p['capture_id']) or not _uint(p['ticket']) or not _uint(p['document_id']):
        raise ValueError('Invalid mask capture identity')
    if action=='arm':
        if p['purpose']!='local-masks' or not _hex(p['epoch']):raise ValueError('Derived local masks cannot capture repair input')
        group=p.get('group_id')
        if group is not None:
            from .local_grade_layers import check
            if type(group) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',group):raise ValueError('Invalid capture group')
            if not any(layer['id']==group for layer in check(engine._local_grade_layers)['layers']):raise ValueError('Capture group no longer exists')
    elif action=='cancel':
        # Native owner only invalidates this exact identity, never a newer one.
        if 'generation' in p and not _uint(p['generation']):raise ValueError('Invalid capture generation')
        return
    else:
        if not _uint(p['generation']):raise ValueError('Invalid capture generation')
        _matching(engine,p,recipe=False,presented=False)
    validate_state(engine);require_pixels(engine)


def require_command(engine,name,p):
    if name not in COMMANDS or type(p) is not dict or p.get('cmd')!=name:raise ValueError('Unknown derived mask command')
    if name=='source_patch_capture':return _capture_command(engine,p)
    if name=='grade':
        if set(p)!={'cmd','action','scope'} or p['action']!='scope' or p['scope']!='objects':
            raise ValueError('Only exact composed-object grade scope is adapted')
        validate_state(engine);require_pixels(engine)
        return
    action=p.get('action')
    if name=='local_masks':
        if set(p)!={'cmd','action','request_id','mutation',*PROOF_KEYS} or action!='apply':raise ValueError('Invalid derived mask edit envelope')
        for key in ('request_id',*PROOF_KEYS):_identity(p[key])
        if _receipt(engine,'_local_mask_owner','cache',p):return
        _mutation(p['mutation']);capture=_matching(engine,p)
        group=p['mutation'].get('id') if p['mutation']['action'].startswith('layer_') else None
        if capture['descriptor'].get('mask_group_id')!=group:raise ValueError('Mask edit names another captured group')
    elif name=='prompted_masks':
        extras={'open':set(),'predict':{'prompts','device'},'poll':set(),'presented':{'candidate'},'cancel':set()}
        if action not in extras or set(p)!={'cmd','action','preview_id',*PROOF_KEYS}|extras[action]:raise ValueError('Invalid derived prompted-mask envelope')
        if type(p['preview_id']) is not str or not re.fullmatch('[0-9a-f]{32}',p['preview_id']):raise ValueError('Invalid prompted preview identity')
        for key in PROOF_KEYS:_identity(p[key])
        if action=='cancel':return
        _matching(engine,p)
        if action=='predict':
            from .prompted_mask_source import check_prompts
            check_prompts(p['prompts'])
            if p['device'] not in ('cpu','cuda'):raise ValueError('Choose actual prompted device')
        if action in ('poll','presented'):
            owner=engine.__dict__.get('_prompted_mask_owner')
            if owner is None or owner.preview_id!=p['preview_id'] or owner.proof!={key:p[key] for key in PROOF_KEYS}:raise ValueError('Prompted preview source capture changed')
        if action=='presented' and (type(p['candidate']) is not int or not 0<=p['candidate']<3):raise ValueError('Invalid prompted candidate')
    else:
        from .local_grade_live import BASE_KEYS,IDENTITY,identifier
        from .local_grade_layers import check,grade
        if action not in ('begin','preview','commit','cancel') or set(p)!=BASE_KEYS|({'grade'} if action in ('begin','preview') else set()):raise ValueError('Invalid derived live grade envelope')
        for key in ('request_id',*IDENTITY):identifier(p[key],64 if key=='group_id' else 128)
        if _receipt(engine,'_local_grade_live_owner','receipts',p):return
        if action=='cancel':return
        if action in ('begin','preview'):grade(p['grade'])
        if str(engine._load_id)!=p['document_id']:raise ValueError('Live grade document changed')
        if not any(row['id']==p['group_id'] for row in check(engine._local_grade_layers)['layers']):raise ValueError('Live grade group no longer exists')
        if action!='begin':
            owner=engine.__dict__.get('_local_grade_live_owner')
            if owner is None:raise ValueError('Live grade session expired')
            owner.matching(p)
    validate_state(engine);require_pixels(engine)
