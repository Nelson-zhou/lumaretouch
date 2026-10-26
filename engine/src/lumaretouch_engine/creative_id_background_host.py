"""Exact native ID transactions and picker admission, not a background exemption."""
from hashlib import sha256
import json

ACTIONS=frozenset(('id_state','id_initialize_foreground','id_sample','id_clear','id_import','id_import_material','id_set','id_review','id_spill_preview','id_spill_apply','id_spill_paint_source','id_original_shadow_paint_source','id_original_shadow_preview','id_original_shadow_apply'))
MODES=frozenset(('id_background','id_background_subject','id_background_reference'))


def is_command(engine,name,request):
    if name=='background':return request.get('action') in ACTIONS
    if name!='color_picker_capture':return False
    if request.get('picker_action') in MODES:return True
    owner=engine.__dict__.get('_id_background_capture_owner')
    capture=getattr(owner,'capture',None)
    return capture is not None and capture['descriptor']['capture_id']==request.get('capture_id')


def require_command(engine,name,request):
    from . import creative_derived_id_background as C,id_background_state as S
    if type(request) is not dict or request.get('cmd')!=name or not is_command(engine,name,request):
        raise ValueError('Unknown derived ID background command')
    action=request.get('action')
    if action=='id_initialize_foreground':
        raise ValueError('自动前景初始化暂不支持创意回流源图；不会回退到原照片推理')
    if name=='background':
        rid=request.get('request_id')
        if type(rid) is not str or not 1<=len(rid)<=128:raise ValueError('Invalid ID request identity')
        owner_key=('_original_shadow_owner' if action in ('id_original_shadow_paint_source','id_original_shadow_preview','id_original_shadow_apply') else
                   '_spill_removal_owner' if action in ('id_spill_preview','id_spill_apply','id_spill_paint_source') else '_id_background_owner')
        owner=engine.__dict__.get(owner_key)
        cached=getattr(owner,'cache',{}).get(rid)
        if cached is not None:
            digest=sha256(json.dumps(request,sort_keys=True,allow_nan=False).encode()).hexdigest()
            if digest!=cached[0]:raise ValueError('ID request identity reused with different content')
            return  # Native terminal receipt remains authoritative after switching.
        if action=='id_state':
            if set(request)!={'cmd','action','request_id','document_id'}:raise ValueError('Invalid ID state request')
            return  # Status must remain readable when an effect cannot render.
        if action=='id_sample':
            picker=engine.__dict__.get('_id_background_capture_owner')
            if picker is None:raise ValueError('ID sample requires its presented source capture')
            picker.matching(request)
            return  # Native sample validates the exact envelope and eligibility.
        from .spill_removal_controller import EXTRA, ACTIONS as SPILL_ACTIONS, envelope
        if action in SPILL_ACTIONS:
            envelope(request)
        from .original_shadow_controller import ACTIONS as SHADOW_ACTIONS, envelope as shadow_envelope
        if action in SHADOW_ACTIONS:
            shadow_envelope(request)
        extra={'id_clear':set(),'id_import':{'path'},'id_import_material':{'selection'},'id_set':{'recipe'},'id_review':{'category','object_ids','reviewed'},**EXTRA}
        if action not in SPILL_ACTIONS|SHADOW_ACTIONS and set(request)!={'cmd','action','request_id','document_id','recipe_document_id','recipe_revision'}|extra[action]:
            raise ValueError('Invalid ID mutation envelope')
    else:
        allowed={'cmd','action','capture_id','ticket','document_id'}
        allowed|={'epoch','picker_action','picker_channel','reference'} if action=='arm' else {'generation'}
        if action not in ('arm','presented','cancel') or set(request)-allowed:
            raise ValueError('Invalid ID capture envelope')
        if action=='cancel':return  # Native owner checks identity and releases stale lease.
        if action=='presented':
            picker=engine.__dict__.get('_id_background_capture_owner')
            if picker is None or picker.capture is None:raise ValueError('ID source capture expired')
            from .id_background_picker import PROOF_KEYS
            picker.matching({**request,**{k:picker.capture['descriptor'][k] for k in PROOF_KEYS}})
            return
    # Independent source proof allows disabling a broken active proposal without
    # running its model or reusing the physical original as an input.
    C.validate_state(engine)
    C.preview(engine,S.empty())
