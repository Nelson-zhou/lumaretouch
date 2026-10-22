"""Explicit review of ambiguous retained parameter intent, never mask rebinding."""
from . import people_algorithms as A,people_state as S


def parameters(record):
    name,value=record['legacy_key'],record['intent']
    geometry=dict(zip(('_brow_shape','_nose_shape','_eye_shape','_mouth_shape'),A.GEOMETRY))
    if name in geometry:return {geometry[name]:A.specifications()[geometry[name]][1](value)}
    if name=='_lip_makeup':return {A.LIP:A.specifications()[A.LIP][1](value)}
    if name=='_deform_default':return {A.DEFORM:A.specifications()[A.DEFORM][1](value)}
    if name=='_deform' or name.startswith('_deform_override_'):
        return {A.DEFORM:A.specifications()[A.DEFORM][1](value.get('amounts',{}))}
    if name=='_enhance':
        amounts=value.get('amounts',{})
        from . import facial_wrinkle_state as W
        return {A.WRINKLES:W.check({k:v for k,v in amounts.items() if k in W.INTENT_KEYS}),
                A.ENHANCE:A.check_enhance({k:v for k,v in amounts.items() if k not in W.INTENT_KEYS})}
    raise ValueError('This retained intent is not portable parameters; its source-owned support cannot be rebound')


def report(state,asset):
    result=[]
    for row in state['unresolved_legacy']:
        if row['asset_sha256']!=asset or row['status']!='unresolved':continue
        try:parameters(row);bindable=True
        except ValueError:bindable=False
        result.append({'id':row['id'],'legacy_key':row['legacy_key'],'intent':row['intent'],'bindable':bindable})
    return result


def resolve(state,archive_id,target,mode):
    out=S.check(state);row=next((r for r in out['unresolved_legacy'] if r['id']==archive_id),None)
    if row is None or row['status']!='unresolved':raise ValueError('Legacy review record changed')
    if target['scope'] not in ('face','all_people'):raise ValueError('Legacy review needs an explicit current face or photograph scope')
    asset=target['face_ref']['asset_sha256'] if target['scope']=='face' else target['target_id']
    if row['asset_sha256']!=asset:raise ValueError('Legacy intent belongs to another source photograph')
    if mode=='apply_parameters':
        for op,recipe in parameters(row).items():
            for path,value in A.leaves(recipe).items():out=S.set_override(out,target['scope'],target['target_id'],op,path,value)
        row=next(r for r in out['unresolved_legacy'] if r['id']==archive_id)
        row['status']='confirmed' if target['scope']=='face' else 'retained'
        row['binding']=target['face_ref'] if target['scope']=='face' else None
    elif mode=='retain_inactive':row['status']='retained'
    else:raise ValueError('Unknown legacy review decision')
    out['revision']+=1
    return S.check(out)
