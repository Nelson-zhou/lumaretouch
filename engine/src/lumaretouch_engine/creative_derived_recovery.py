"""Reviewed face, fabric, smoothing, common key and dedicated ID recovery.

Face ownership stays separate from the reviewed global consumers. No other global
operator or second history owner is admitted; recovery attenuates one delta.
"""
import hashlib
import json
from .facial_wrinkle_recovery import FACE_TARGETS as TARGETS

GLOBAL_TARGETS = frozenset(('fabric_fine', 'skin_smoothing', 'background_replace', 'id_background'))

COMMANDS = frozenset(('source_patch_capture','effect_recovery_preview','effect_recovery'))


def source_binding(engine):
    from .creative_derived_source import record,binding,verify_precompute
    if record(engine) is None:
        from .local_mask_state import bind_source
        return bind_source(engine)
    pc=getattr(engine,'_precompute',None)
    if pc is None or getattr(pc,'backend',None)!='mediapipe':
        raise ValueError('Derived face recovery requires actual current portrait analysis')
    verify_precompute(engine,pc)
    return binding(engine)


def _context(engine):
    from . import people_recovery as P
    source=source_binding(engine)
    if not P.managed(engine):raise ValueError('Derived recovery requires the canonical people owner')
    context=P.context(engine)
    if context['source']!=source:raise ValueError('Recovery source differs from immutable composite')
    _global_value(engine)
    return context


def _global_value(engine):
    from .creative_derived_source import binding
    from .creative_derived_global_recovery import validate
    return validate(getattr(engine,'_effect_recovery',None),binding(engine))


def global_context(engine,target):
    """Read-only producer evidence, never a face cursor used as global identity."""
    from .creative_derived_source import record
    if target == 'id_background':
        from .id_background_recovery import context
        from .effect_recovery_state import check
        return {'target':target,'consumer':context(engine),'recovery':check(getattr(engine,'_effect_recovery',None))}
    if target == 'background_replace':
        from .common_background_recovery import context
        from .effect_recovery_state import check
        return {'target':target,'consumer':context(engine),'recovery':check(getattr(engine,'_effect_recovery',None))}
    if record(engine) is None:return None
    if target not in GLOBAL_TARGETS:
        raise ValueError('This global recovery consumer is not derived-source adapted')
    if target == 'skin_smoothing':
        from .creative_derived_smoothing import recovery_context
    else:
        from .creative_derived_fabric import recovery_context
    return {'target':target,'consumer':recovery_context(engine),'recovery':_global_value(engine)}


def assert_review(engine,record):
    """Revalidate even when a caller reaches the review owner without dispatch."""
    from .creative_derived_source import record as source_record
    if record['target'] == 'id_background':
        if record.get('people_context') is not None or record.get('global_context') != global_context(engine,'id_background'):
            raise ValueError('ID recovery compositor source, recipe, asset or fields changed')
        return
    if record['target'] == 'background_replace':
        if record.get('people_context') is not None or record.get('global_context') != global_context(engine,'background_replace'):
            raise ValueError('Common recovery source, key, color, matte, geometry or activation changed')
        return
    if source_record(engine) is None:
        if record.get('global_context') is not None:
            raise ValueError('Derived recovery review cannot become an original-file edit')
        return
    target=record['target']
    if target in GLOBAL_TARGETS:
        if record.get('people_context') is not None or record.get('global_context')!=global_context(engine,target):
            raise ValueError('Derived global recovery source, recipe or measured evidence changed')
    elif target in TARGETS:
        if record.get('global_context') is not None or record.get('people_context')!=_context(engine):
            raise ValueError('Derived recovery review source, face or graph changed')
    else:
        raise ValueError('This recovery consumer is not derived-source adapted')


def _capture(engine,request):
    owner=engine._source_patch_controller().capture
    capture=owner._matching(request,recipe=request['cmd']!='source_patch_capture')
    descriptor=capture['descriptor']
    if descriptor['domain']!='source-input' or descriptor.get('mask_group_id') is not None:
        raise ValueError('Derived face recovery requires ungrouped source-input capture')
    return capture


def _pixels(engine):
    """Do not label an old pipeline buffer with the new source's identity."""
    import numpy as np
    from .creative_derived_source import analysis_rgb
    rgb=analysis_rgb(engine);pipe=getattr(engine,'_vram',None)
    source=getattr(pipe,'src_f32',None)
    if source is None or tuple(source.shape)!=(1,3,*rgb.shape[:2]):
        raise ValueError('Recovery capture has another source extent')
    actual=source[0].permute(1,2,0).detach().cpu().numpy()
    if actual.dtype!=np.float32 or not np.allclose(actual,rgb.astype(np.float32)/255.,rtol=0,atol=np.finfo(np.float32).eps):
        raise ValueError('Recovery capture pixels differ from the actual derived source')


def require_command(engine,name,request):
    from .source_patch_controller import PROOF_KEYS
    from .source_patch_capture import _hex,_uint
    from .effect_recovery_preview import preview_id
    if name not in COMMANDS or type(request) is not dict or request.get('cmd')!=name:
        raise ValueError('Unknown derived recovery command')
    action=request.get('action')
    from .eye_bag_recovery_alias_derived import check_request, require_record
    alias_envelope=check_request(name,request)
    if name=='effect_recovery':
        if not alias_envelope and (set(request)!={'cmd','action','request_id','preview_id',*PROOF_KEYS} or action!='apply'):
            raise ValueError('Derived recovery apply requires its exact review receipt')
        if type(request['request_id']) is not str or not 1<=len(request['request_id'])<=128:
            raise ValueError('Invalid recovery request identity')
        # Exact terminal receipt replay has no mutation and must survive capture
        # invalidation after the original apply. Different content never reuses it.
        owner=engine.__dict__.get('_effect_recovery_owner')
        cached=getattr(owner,'cache',{}).get(request['request_id'])
        if cached is not None:
            digest=hashlib.sha256(json.dumps(request,sort_keys=True,allow_nan=False).encode()).hexdigest()
            if cached[0]!=digest:raise ValueError('Recovery request identity reused with different content')
            return
    _global_value(engine)
    if name=='source_patch_capture':
        fields={'cmd','action','capture_id','ticket','document_id'}
        fields |= {'epoch','purpose'} if action=='arm' else ({'generation'} if action!='cancel' or 'generation' in request else set())
        if action=='arm' and 'group_id' in request:fields.add('group_id')
        if action not in ('arm','presented','cancel') or set(request)!=fields:
            raise ValueError('Derived recovery capture accepts only its exact source-input envelope')
        if not _hex(request['capture_id']) or not _uint(request['ticket']) or not _uint(request['document_id']):
            raise ValueError('Invalid recovery capture identity')
        if action=='arm':
            if request['purpose']!='local-masks' or request.get('group_id') is not None or not _hex(request['epoch']):
                raise ValueError('Derived recovery cannot capture repair or grouped mask inputs')
        else:
            matching=request
            if action=='cancel' and 'generation' not in request:
                retained=engine._source_patch_controller().capture.capture
                if retained is None:raise ValueError('Recovery capture no longer exists')
                matching={**request,'generation':retained['descriptor']['generation']}
            if not _uint(matching['generation']):raise ValueError('Invalid recovery capture generation')
            _capture(engine,matching)
        # Source-input coordinates do not require a detected face. Face
        # mutation previews still validate their exact analysis in _context.
        from .creative_derived_source import binding
        from .creative_derived_repair_runtime import verify_pipeline
        verify_pipeline(engine._vram,binding(engine))
        _pixels(engine)
        return
    fields={'cmd','action','preview_id',*PROOF_KEYS}
    if name=='effect_recovery_preview' and not alias_envelope:
        if action=='preview':fields.add('mutation')
        if action not in ('preview','presented','cancel') or set(request)!=fields:
            raise ValueError('Invalid derived recovery preview envelope')
    preview_id(request['preview_id'])
    capture=_capture(engine,request)
    if not capture['eligible']:raise ValueError('Recovery source capture has not been presented')
    _pixels(engine)
    if name=='effect_recovery_preview' and action=='preview':
        mutation=request['mutation']
        if type(mutation) is not dict or mutation.get('target') not in TARGETS | GLOBAL_TARGETS:
            raise ValueError('Only reviewed face, fabric, smoothing, common key and dedicated ID operators support derived recovery')
        allowed={'view':{'action','target'},'stroke':{'action','target','stroke'},
                 'clear':{'action','target'},'enable':{'action','target','enabled'},
                 'delete':{'action','target','id'}}
        if mutation.get('action') not in allowed or set(mutation)!=allowed[mutation['action']]:
            raise ValueError('Invalid recovery mutation')
        if mutation['target'] in GLOBAL_TARGETS:global_context(engine,mutation['target'])
        else:_context(engine)
        return # Canonical mutation owner validates vectors and operator readiness.
    owner=engine.__dict__.get('_effect_recovery_preview_owner')
    record=getattr(owner,'record',None)
    if (record is None or record['id']!=request['preview_id'] or record['target'] not in TARGETS | GLOBAL_TARGETS
            or record['proof']!={key:request[key] for key in PROOF_KEYS}):
        raise ValueError('Derived recovery review source, face or graph changed')
    assert_review(engine,record)
    require_record(engine,record,request)
    if name=='effect_recovery' and (not record['presented'] or not record['committable']):
        raise ValueError('Derived recovery requires a presented committable review')


def validate_supports(state,assets,source):
    from . import people_state as S,people_support_assets as A
    for face in state['faces'].values():
        if face['asset_sha256']!=source['sha256']:continue
        for kind in face['local_assets']:
            if kind not in TARGETS:continue
            value=A.resolve(state,assets,S.face_ref(face),kind)
            if value is None or value['source']!=source:
                raise ValueError('Recovery vectors belong to another effective source')


def validate_fields(state,source,fields,shape):
    from . import people_state as S,people_effects as E
    fields={} if fields is None else fields
    if type(fields) is not dict:raise ValueError('Invalid derived recovery field bank')
    expected={}
    for key,face in state['faces'].items():
        if face['asset_sha256']!=source['sha256'] or not face['enabled']:continue
        for kind,descriptor in face['local_assets'].items():
            if kind in TARGETS:
                ref=S.face_ref(face)
                if descriptor.get('owner')!=ref or descriptor.get('kind')!=kind:
                    raise ValueError('Derived recovery descriptor belongs to another face or operator')
                expected[(key,kind)]=(ref,descriptor)
    if set(fields)!=set(expected):raise ValueError('Derived recovery fields do not exactly cover owned face descriptors')
    for key,(ref,descriptor) in expected.items():
        value=fields[key]
        if type(value) is not dict or value.get('recipe_sha256')!=descriptor['content_sha256']:
            raise ValueError('Derived recovery raster does not match its retained vectors')
        E.verify_recovery(ref,key[1],value,tuple(shape))
