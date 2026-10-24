"""Private full-render body-skin review, committed by the existing people owner.

No preview swaps the live source, graph, support bank or history. Only explicit
confirmation attaches the already rendered source-owned support descriptor.
"""
from copy import deepcopy
import base64
import io
import uuid
from . import people_state as P
from . import skin_colour_body_support as SUPPORT
from .skin_colour_body_actions import check_action, action_name


def _family(family,operation_id):
    kind,operation=SUPPORT.family_spec(family,operation_id)
    # Preserve old colour call signatures/private state for existing callers.
    # Every added family has its own source reference and pending comparison;
    # none borrows another family's review, receipt or support descriptor.
    options={} if family=='skin_colour' else {'family':family,'operation_id':operation}
    prefix={'skin_colour':'_skin_body','skin_finish':'_skin_finish_body',
            'body_skin_evenness':'_body_skin_evenness'}[family]
    return kind,operation,options,prefix+'_reference',prefix+'_preview'


def _tags(family,operation):
    return {} if family=='skin_colour' else {'family':family,'operation_id':operation}


def _matches_family(value,family,operation):
    # Old colour-only private records had no tags. Explicit non-colour tags are
    # mandatory and cannot authorize another family even if copied by a bug.
    defaults={'family':family,'operation_id':operation} if family=='skin_colour' else {}
    return all(value.get(key,defaults.get(key))==expected
               for key,expected in (('family',family),('operation_id',operation)))


def selected(engine,state,target):
    source=engine._people_source()
    if target['scope']!='face' or target!=engine._people_targets.get(source['sha256']):
        raise ValueError('Body skin review requires the explicitly selected face')
    ref=P.check_ref(target['face_ref']);face=state['faces'].get(ref['face_instance_id'])
    if face is None or P.face_ref(face)!=ref or ref['asset_sha256']!=source['sha256']:
        raise ValueError('Body skin review belongs to another face/source')
    return source,ref


def _capture(engine,state,target,*,family='skin_colour',operation_id=None):
    from .optics_candidate_identity import fingerprint
    from .virtual_copy_people import current_row
    from .full_candidate_render import identity
    _,operation=SUPPORT.family_spec(family,operation_id)
    source,ref=selected(engine,state,target);row=current_row(engine)
    if row is None:raise ValueError('Body skin review has no current document')
    analysis=engine._people_analyses.get(source['sha256'],{}).get(ref['face_instance_id'])
    if analysis is None or analysis['face_ref']!=ref:raise ValueError('Body skin review needs actual current-face analysis')
    snapshot=engine._capture_state();version=engine._document_versions().version(row)
    proof,graph,context=identity(engine,row,snapshot,version.document_id,str(version.revision))
    if graph!=state:raise ValueError('Body skin owner changed during capture')
    bank=engine._body_bank()
    fence=fingerprint({'family':family,'operation_id':operation,
                       'proof':proof,'target':target,'binding':engine._people_binding(),
                       'body':bank,'analysis':analysis,'graph':state})
    return fence,source,ref,row,snapshot,context,bank,analysis,version


def _png(rgb,*,source=None):
    import numpy as np
    from PIL import Image
    value=np.asarray(rgb)
    if value.ndim!=3 or value.shape[2]!=3 or not np.isfinite(value).all():
        raise ValueError('Body skin candidate lacks actual finite RGB pixels')
    if value.dtype!=np.uint8:
        if not np.issubdtype(value.dtype,np.floating) or np.any(value<0) or np.any(value>1):
            raise ValueError('Body skin review cannot clip HDR or invalid rendered pixels')
        value=np.rint(value*255).astype(np.uint8)
    image=Image.fromarray(value,'RGB');image.thumbnail((1280,1280) if source is not None else (960,960));buffer=io.BytesIO();image.save(buffer,format='PNG')
    raw=buffer.getvalue()
    if len(raw)>1536*1024:raise ValueError('Body skin comparison exceeds its image budget')
    result={'mime':'image/png','base64':base64.b64encode(raw).decode('ascii'),'width':image.width,'height':image.height}
    if source is None:result['mapping']='rendered_result'
    else:result.update(mapping='normalized_full_frame',source_sha256=source['sha256'],source_width=source['width'],
                       source_height=source['height'],decoded_width=value.shape[1],decoded_height=value.shape[0],orientation='exif_normalized_once')
    image.close();return result


def reference(engine,state,target,payload,*,family='skin_colour',operation_id=None):
    kind,operation,options,reference_key,preview_key=_family(family,operation_id)
    check_action(action_name('reference',family=family),payload,target,**options)
    capture=_capture(engine,state,target,**options);fence,source,ref,_,_,_,bank,analysis,_=capture
    choices=SUPPORT.choices(state,bank,ref,analysis,**options)
    from .body_pose_commands import source_preview
    preview=source_preview(engine)
    if len(preview['base64'])>2*1024*1024:raise ValueError('Body skin source reference exceeds its budget')
    if _capture(engine,state,target,**options)[0]!=fence:raise ValueError('Body skin reference changed while preparing')
    tags=_tags(family,operation)
    setattr(engine,preview_key,None)
    setattr(engine,reference_key,{'fence':fence,'source':deepcopy(source),'face_ref':ref,**tags})
    return {'kind':'reference','source':source,'face_ref':ref,'source_preview':preview,
            'bodies':choices,'attached':kind in state['faces'][ref['face_instance_id']]['local_assets'],**tags}


def preview(engine,state,target,payload,*,family='skin_colour',operation_id=None):
    _,operation,options,reference_key,preview_key=_family(family,operation_id)
    check_action(action_name('preview',family=family),payload,target,**options)
    capture=_capture(engine,state,target,**options);fence,source,ref,row,snapshot,context,bank,analysis,version=capture
    tags=_tags(family,operation);shown=engine.__dict__.get(reference_key)
    if not shown or shown['fence']!=fence or not _matches_family(shown,family,operation):
        raise ValueError('Read the current body skin source reference again')
    setattr(engine,preview_key,None)
    candidate,assets=SUPPORT.retain(state,engine._people_support,ref,bank,analysis,payload['review'],**options)
    if family=='body_skin_evenness':
        # First use must not persist an unsupported active body-only amount.
        # The explicit local amount and support are one private comparison;
        # confirmation publishes their exact face-scoped candidate together.
        candidate=P.set_override(candidate,'face',ref['face_instance_id'],operation,'/amount',payload['amount'])
    from .people_support_assets import check_store
    check_store(assets)
    if family=='skin_colour':
        from .skin_colour_state import OP, active
    elif family=='skin_finish':
        from .skin_finish_state import OP, active
    else:
        from .body_skin_evenness_state import OP, active
    from .people_resolver import resolve
    from .people_algorithms import defaults,recipes
    if not active(recipes(resolve(candidate,ref['face_instance_id'],defaults()))[OP]):
        label={'skin_colour':'skin-colour','skin_finish':'skin-finish',
               'body_skin_evenness':'body-skin-evenness'}[family]
        suffix=' region' if family=='body_skin_evenness' else ' extension'
        raise ValueError('Set a nonzero '+label+' amount before reviewing its visible body'+suffix)
    staged=deepcopy(context);staged['people_graph']=candidate;staged['people_support_assets']=assets
    from .full_candidate_render import render
    rgb,before_proof=render(engine,row,snapshot,version.document_id,str(version.revision),people_graph=state)
    before=_png(rgb);del rgb
    rgb,after_proof=render(engine,row,snapshot,version.document_id,str(version.revision),people_graph=candidate,staged_people_context=staged)
    after=_png(rgb);del rgb
    if (before['width'],before['height'])!=(after['width'],after['height']):raise ValueError('Body skin comparison geometry changed')
    from .creative_derived_source import analysis_rgb
    from .cpu_memory_budget import available_estimate
    import numpy as np
    source_rgb=analysis_rgb(engine)
    coverage,facts=SUPPORT.raster(candidate,assets,ref,bank,analysis,tuple(source_rgb.shape[:2]),byte_budget=available_estimate(),**options)
    if coverage is None:raise ValueError('Body skin candidate omitted its actual measured coverage')
    # Cyan tint displays the real semantic/vector intersection, not an invented
    # skin area. This is explicitly a source-space overlay, not rendered crop.
    tint=np.array([0.,1.,1.],np.float32);alpha=np.asarray(coverage,np.float32)[...,None]*.55
    overlay=_png(source_rgb.astype(np.float32)/255.*(1-alpha)+tint*alpha,source=source)
    if _capture(engine,state,target,**options)[0]!=fence:raise ValueError('Body skin review changed during full rendering')
    preview_id=uuid.uuid4().hex
    from .optics_candidate_identity import fingerprint
    candidate_amount={'amount':float(payload['amount'])} if family=='body_skin_evenness' else {}
    result={'kind':'preview','preview_id':preview_id,'source':source,'face_ref':ref,'before':before,'after':after,
            'overlay':overlay,'review':deepcopy(payload['review']),'runtime_quality_accepted':False,**tags,**candidate_amount}
    setattr(engine,preview_key,{'id':preview_id,'fence':fence,'candidate':candidate,'assets':assets,
        'review':deepcopy(payload['review']),'candidate_sha256':fingerprint({'state':candidate,'assets':assets}),
        'before_proof':before_proof,'after_proof':after_proof,**tags,**candidate_amount})
    return result


def confirm(engine,state,target,payload,*,mark_started=lambda:None,family='skin_colour',operation_id=None):
    _,operation,options,reference_key,preview_key=_family(family,operation_id)
    check_action(action_name('confirm',family=family),payload,target,**options)
    capture=_capture(engine,state,target,**options);fence,source,ref,_,_,_,bank,analysis,_=capture
    tags=_tags(family,operation);pending=engine.__dict__.get(preview_key)
    if (not pending or pending['id']!=payload['preview_id'] or pending['fence']!=fence
            or not _matches_family(pending,family,operation)):
        raise ValueError('Body skin candidate is missing or changed; render a new comparison')
    candidate,assets=SUPPORT.retain(state,engine._people_support,ref,bank,analysis,pending['review'],**options)
    if family=='body_skin_evenness':
        candidate=P.set_override(candidate,'face',ref['face_instance_id'],operation,'/amount',pending['amount'])
    from .people_support_assets import check_store
    check_store(assets)
    from .optics_candidate_identity import fingerprint
    if fingerprint({'state':candidate,'assets':assets})!=pending['candidate_sha256']:
        raise ValueError('Body skin candidate/support no longer matches the reviewed rendering')
    # Only this explicit confirmation may retain immutable asset bytes. The
    # caller still prepares/publishes the graph via the canonical transaction.
    mark_started()
    engine._people_support=assets;setattr(engine,preview_key,None);setattr(engine,reference_key,None)
    return candidate,{'kind':'confirmed','attached':True,**tags}


def detach(engine,state,target,payload,*,family='skin_colour',operation_id=None):
    _,operation,options,reference_key,preview_key=_family(family,operation_id)
    check_action(action_name('detach',family=family),payload,target,**options);_,ref=selected(engine,state,target)
    if family=='body_skin_evenness':
        from .body_skin_evenness_state import active
        from .people_resolver import resolve
        from .people_algorithms import defaults,recipes
        if active(recipes(resolve(state,ref['face_instance_id'],defaults()))[operation]):
            raise ValueError('Reset the body-skin-evenness amount to zero before detaching its support')
    candidate=SUPPORT.detach(state,ref,**options)
    setattr(engine,preview_key,None);setattr(engine,reference_key,None)
    return candidate,{'kind':'detached','attached':False,**_tags(family,operation)}


def report(engine,state,source,selected_id,*,family='skin_colour',operation_id=None):
    kind,operation,options,_,_=_family(family,operation_id)
    face=state['faces'].get(selected_id)
    if face is None or face['asset_sha256']!=source['sha256']:return None
    ref=P.face_ref(face);attached=kind in face['local_assets']
    result={'attached':attached,'face_ref':ref,'source':deepcopy(source),'needs_review':False,'reason':None,
            **_tags(family,operation)}
    if attached:
        try:
            analysis=engine._people_analyses.get(source['sha256'],{}).get(selected_id)
            SUPPORT.resolve(state,engine._people_support,ref,engine._body_bank(),analysis,**options)
        except (ValueError,KeyError,TypeError) as error:
            result.update(needs_review=True,reason=str(error))
    return result


def bound_receipt_payloads(records):
    """Keep at most two bounded image replies, preserving outcome identities."""
    remaining=2
    for row in reversed(records.values()):
        result=row.get('result',row);payload=result.get('payload')
        if not isinstance(payload,dict) or payload.get('kind') not in ('reference','preview'):continue
        if remaining:remaining-=1
        else:result.pop('payload',None);result['payload_released']=True
