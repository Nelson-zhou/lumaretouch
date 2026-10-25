"""Engine lifecycle port for the all-face bank. Shared host wiring is separate.

The host owns state/history/receipts. This adapter owns derived preview resources,
not association persistence. A failed requested graph cannot fall back to a stale
single-selected-face image and claim it rendered the people bank.
"""
import numpy as np
from .people_render_runtime import prepare, retained_bytes
from . import people_pipeline as PIPE


def prepare_preview(pipe,state,asset_sha256,analyses,*,byte_budget,document_id=None,recovery_assets=None,body_bank=None,body_source=None,body_source_path=None,body_source_pixels=None,creative_source=None,creative_proxy=None,
                    skin_reference_match_assets=None,skin_reference_match_source=None,hair_assets=None,hair_unification_assets=None,hair_unification_source=None,hair_evidence=None,hair_source_path=None,eye_light_assets=None,blush_makeup_assets=None,face_decoration_assets=None,facial_sculpt_assets=None,eye_makeup_enhance_assets=None,lipstick_assets=None,eyeliner_assets=None,eyelash_assets=None,brow_makeup_assets=None,iris_makeup_assets=None,skin_colour_body_assets=None,skin_finish_body_assets=None,body_skin_evenness_assets=None,body_face_match_assets=None,collarbone_assets=None,eye_bag_preserve_assets=None):
    import torch
    if body_bank is None and getattr(getattr(pipe,'people_prepared',None),'body_fields',()):
        raise ValueError('Preview omitted independently retained body inputs')
    source=pipe.src_f32
    if source is None:raise ValueError('All-face rendering needs the current immutable source')
    rgb=np.array(source[0].permute(1,2,0).to('cpu',torch.float32).numpy(),dtype=np.float32,copy=True)
    rgb.setflags(write=False)
    replay_evidence=None
    if creative_source is not None:
        from .creative_derived_effects import require_graph
        require_graph(state,creative_source,document_id=document_id)
        if (asset_sha256 != creative_source['sha256'] or type(creative_proxy) is not np.ndarray
                or creative_proxy.dtype != np.uint8 or creative_proxy.shape != rgb.shape
                or not np.allclose(rgb,creative_proxy.astype(np.float32)/255.,rtol=0,atol=np.finfo(np.float32).eps)):
            raise ValueError('Portrait preview pixels differ from the owned composite analysis proxy')
        if body_source_path is not None or hair_source_path is not None:
            raise ValueError('Derived portrait preview cannot acquire original-file support inputs')
        from .creative_derived_body import validate as validate_body
        if body_bank is not None:validate_body(body_bank,creative_source)
        if body_source is not None and body_source != creative_source:
            raise ValueError('Derived body preview source differs from immutable portrait owner')
        from .creative_derived_recovery import validate_fields
        validate_fields(state,creative_source,recovery_assets or {},rgb.shape[:2])
        from .creative_derived_repair_runtime import verify_pipeline
        replay_evidence=verify_pipeline(pipe,creative_source)
    elif creative_proxy is not None:
        raise ValueError('Derived preview proxy is missing its source binding')
    repaired=None
    if pipe.repair_base is not None:
        repaired=np.array(pipe.repair_base[0].permute(1,2,0).to('cpu',torch.float32).numpy(),dtype=np.float32,copy=True)
        repaired.setflags(write=False)
    prepared=prepare(state,asset_sha256,rgb,analyses,byte_budget=byte_budget,document_id=document_id,recovery_assets=recovery_assets,repaired=repaired,
        creative_source=creative_source,creative_repair_evidence=replay_evidence,skin_reference_match_assets=skin_reference_match_assets,skin_reference_match_source=skin_reference_match_source,hair_assets=hair_assets,hair_unification_assets=hair_unification_assets,hair_unification_source=hair_unification_source,hair_evidence=hair_evidence,hair_source_path=hair_source_path,eye_light_assets=eye_light_assets,blush_makeup_assets=blush_makeup_assets,face_decoration_assets=face_decoration_assets,facial_sculpt_assets=facial_sculpt_assets,eye_makeup_enhance_assets=eye_makeup_enhance_assets,lipstick_assets=lipstick_assets,eyeliner_assets=eyeliner_assets,eyelash_assets=eyelash_assets,brow_makeup_assets=brow_makeup_assets,iris_makeup_assets=iris_makeup_assets,
        skin_colour_body_assets=skin_colour_body_assets,skin_finish_body_assets=skin_finish_body_assets,body_skin_evenness_assets=body_skin_evenness_assets,body_face_match_assets=body_face_match_assets,collarbone_assets=collarbone_assets,eye_bag_preserve_assets=eye_bag_preserve_assets,body_bank=body_bank)
    if body_bank is not None:
        from .body_pose_render import prepare as prepare_body
        prepared=prepare_body(prepared,body_bank,state,body_source,byte_budget=body_budget(prepared,byte_budget),source_path=body_source_path,source_pixels=body_source_pixels)
    return prepared


def synchronize(pipe,state,asset_sha256,analyses,*,byte_budget,document_id=None,recovery_assets=None,body_bank=None,body_source=None,body_source_path=None,body_source_pixels=None,creative_source=None,creative_proxy=None,
                    skin_reference_match_assets=None,skin_reference_match_source=None,hair_assets=None,hair_unification_assets=None,hair_unification_source=None,hair_evidence=None,hair_source_path=None,eye_light_assets=None,blush_makeup_assets=None,face_decoration_assets=None,facial_sculpt_assets=None,eye_makeup_enhance_assets=None,lipstick_assets=None,eyeliner_assets=None,eyelash_assets=None,brow_makeup_assets=None,iris_makeup_assets=None,skin_colour_body_assets=None,skin_finish_body_assets=None,body_skin_evenness_assets=None,body_face_match_assets=None,collarbone_assets=None,eye_bag_preserve_assets=None):
    prepared=prepare_preview(pipe,state,asset_sha256,analyses,byte_budget=byte_budget,document_id=document_id,recovery_assets=recovery_assets,body_bank=body_bank,body_source=body_source,body_source_path=body_source_path,body_source_pixels=body_source_pixels,creative_source=creative_source,creative_proxy=creative_proxy,
        skin_reference_match_assets=skin_reference_match_assets,skin_reference_match_source=skin_reference_match_source,hair_assets=hair_assets,hair_unification_assets=hair_unification_assets,hair_unification_source=hair_unification_source,hair_evidence=hair_evidence,hair_source_path=hair_source_path,eye_light_assets=eye_light_assets,blush_makeup_assets=blush_makeup_assets,face_decoration_assets=face_decoration_assets,facial_sculpt_assets=facial_sculpt_assets,eye_makeup_enhance_assets=eye_makeup_enhance_assets,lipstick_assets=lipstick_assets,eyeliner_assets=eyeliner_assets,eyelash_assets=eyelash_assets,brow_makeup_assets=brow_makeup_assets,iris_makeup_assets=iris_makeup_assets,skin_colour_body_assets=skin_colour_body_assets,skin_finish_body_assets=skin_finish_body_assets,body_skin_evenness_assets=body_skin_evenness_assets,body_face_match_assets=body_face_match_assets,collarbone_assets=collarbone_assets,eye_bag_preserve_assets=eye_bag_preserve_assets)
    PIPE.install(pipe,prepared);pipe.people_suspended=None
    return prepared


def suspend(pipe,reason):
    if type(reason) is not str or not reason:raise ValueError('People suspension needs a visible reason')
    PIPE.clear(pipe);pipe.people_key=None;pipe.people_suspended=reason


def require_ready(pipe):
    reason=getattr(pipe,'people_suspended',None)
    if reason:raise ValueError('Retained people edits are unresolved: '+reason)


def prepare_export(snapshot,source,repaired,*,byte_budget,document_id=None,recovery_assets=None,body_pose=None,body_source_path=None,creative_repair_evidence=None,source_materialization_version=0):
    """Original RGB8/16 enters once; all face solvers run before tile slicing."""
    if type(source_materialization_version) is not int or source_materialization_version not in (0,1):
        raise ValueError('Unsupported portrait source materialization strategy')
    if type(source) is not np.ndarray or source.ndim != 3 or source.shape[2] != 3 or min(source.shape[:2]) < 1:
        raise ValueError('People export requires actual RGB source pixels; alpha is unsupported')
    from .people_snapshot import at_dimensions
    from .people_cross_owner import validate_owner
    if snapshot.get('document_id') != document_id:
        raise ValueError('Frozen portrait document differs from the export owner')
    validate_owner(snapshot['state'],snapshot['asset_sha256'],document_id)
    creative=snapshot.get('creative_source')
    if creative is not None:
        from .creative_derived_effects import require_graph
        require_graph(snapshot['state'],creative,document_id=document_id)
        if body_source_path is not None:
            raise ValueError('Derived portrait export cannot replay original-path body inputs')
        if repaired is not None:
            from .creative_derived_repair_runtime import verify_evidence
            verify_evidence(creative_repair_evidence,creative,source,repaired)
        if (source.dtype!=np.float32 or source.ndim!=3 or source.shape[2]!=3
                or (creative['height'],creative['width'])!=source.shape[:2]
                or creative['sha256']!=snapshot['asset_sha256']
                or not np.isfinite(source).all() or np.any(source<0) or np.any(source>1)):
            raise ValueError('People export requires the verified creative float32 working source')
        from .creative_derived_recovery import validate_fields
        validate_fields(snapshot['state'],creative,recovery_assets or {},source.shape[:2])
        divisor=1
    else:
        if source.dtype not in (np.uint8,np.uint16):raise ValueError('People export needs original RGB8/16')
        divisor=255 if source.dtype==np.uint8 else 65535
    # Admit all target-grid semantic copies before at_dimensions allocates them.
    # Reserve source/repair storage plus the existing RGB conversion/copy peak;
    # no proxy effect or RGB is substituted when the supplied budget is short.
    if type(byte_budget) is not int or byte_budget < 0:
        raise ValueError('People export needs an explicit nonnegative byte budget')
    pixels=int(source.shape[0])*int(source.shape[1])
    reserved=source.nbytes+(0 if repaired is None else repaired.nbytes)+pixels*36
    materialization=None
    if source_materialization_version == 1:
        from .people_source_materialization import can_materialize_export_source, inspect_export_source
        if can_materialize_export_source(source,divisor):
            materialization=inspect_export_source(source,divisor)
            # Retain the historical semantic-resampling allowance. A small view
            # may own a larger backing allocation, never charge only its nbytes.
            reserved=max(source.nbytes+pixels*36,materialization.peak_bytes)+(0 if repaired is None else repaired.nbytes)
    state,asset,analyses=at_dimensions(snapshot,tuple(source.shape[:2]),byte_budget=byte_budget-reserved)
    if materialization is None:
        rgb=np.array(source.astype(np.float32)/divisor,dtype=np.float32,copy=True)
        rgb.setflags(write=False)
    else:
        from .people_source_materialization import materialize_export_source
        rgb=materialize_export_source(source,divisor,max_bytes=materialization.peak_bytes)
    if creative is None:
        from .hair_colour_project import kwargs as hair_inputs
        source_inputs=hair_inputs(snapshot)
    else:
        from .creative_derived_hair import export_inputs
        source_inputs={'creative_source':creative,'creative_repair_evidence':creative_repair_evidence,**export_inputs(snapshot)}
    from .hair_unification_project import kwargs as unification_inputs
    source_inputs.update(unification_inputs(snapshot))
    from .skin_reference_match_inputs import export_kwargs as reference_inputs
    source_inputs.update(reference_inputs(snapshot,source))
    # Independent reviewed skin families consume the target's retained BodyRef
    # before composing once. Body geometry joins the single common map below.
    bank=frame=None
    if body_pose is not None:
        from .arm_shape_project import check_snapshot
        frame=body_pose['source'];bank=check_snapshot(body_pose,frame)
        if creative is not None:
            from .creative_derived_body import validate as validate_body
            validate_body(bank,creative)
        if (frame['height'],frame['width'])!=source.shape[:2]:raise ValueError('Body final preparation requires exact original dimensions')
        if frame['sha256']!=asset:raise ValueError('Body colour support belongs to another portrait source')
    prepared=prepare(state,asset,rgb,analyses,byte_budget=byte_budget,document_id=document_id,recovery_assets=recovery_assets,repaired=repaired,
        **source_inputs,full_source_verified=creative is not None,force_hair_prompted=True,eye_light_assets=snapshot.get('support_assets',{}),blush_makeup_assets=snapshot.get('support_assets',{}),face_decoration_assets=snapshot.get('support_assets',{}),facial_sculpt_assets=snapshot.get('support_assets',{}),eye_makeup_enhance_assets=snapshot.get('support_assets',{}),lipstick_assets=snapshot.get('support_assets',{}),eyeliner_assets=snapshot.get('support_assets',{}),eyelash_assets=snapshot.get('support_assets',{}),brow_makeup_assets=snapshot.get('support_assets',{}),iris_makeup_assets=snapshot.get('support_assets',{}),
        skin_colour_body_assets=snapshot.get('support_assets',{}),skin_finish_body_assets=snapshot.get('support_assets',{}),body_skin_evenness_assets=snapshot.get('support_assets',{}),body_face_match_assets=snapshot.get('support_assets',{}),collarbone_assets=snapshot.get('support_assets',{}),eye_bag_preserve_assets=snapshot.get('support_assets',{}),body_bank=bank)
    if bank is not None:
        from .body_pose_render import prepare as prepare_body
        # Selection replay must use its canonical true-bit-depth decoder, even
        # when the requested output is RGB8 from RAW/high-bit-depth TIFF.
        # Output pixels retain their independent existing export decode path.
        prepared=prepare_body(prepared,bank,state,frame,byte_budget=body_budget(prepared,byte_budget),source_path=body_source_path,source_pixels=source if creative is not None else None)
    return prepared


def body_budget(prepared,budget):
    # Body composition already counts retained face evaluators and both maps.
    # Reserve independent colour/recovery arrays and source buffers as well.
    colour=sum(array.nbytes for record in prepared.effects for array in (record.delta,record.weights,record.chroma_shift,record.log_gain) if array is not None)
    colour+=sum(record.amounts.resident_bytes() for record in prepared.effects if record.stage=='skin_reference_match')
    recovery=sum(record['weight'].nbytes for record in prepared.recovery.values())
    h,w=prepared.geometry.delta.shape[1:3]
    return budget-colour-recovery-h*w*24
