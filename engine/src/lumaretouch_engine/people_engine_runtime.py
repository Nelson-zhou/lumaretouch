"""Engine lifecycle port for the all-face bank. Shared host wiring is separate.

The host owns state/history/receipts. This adapter owns derived preview resources,
not association persistence. A failed requested graph cannot fall back to a stale
single-selected-face image and claim it rendered the people bank.
"""
import numpy as np
from .people_render_runtime import prepare, retained_bytes
from . import people_pipeline as PIPE


def prepare_preview(pipe,state,asset_sha256,analyses,*,byte_budget,recovery_assets=None,body_bank=None,body_source=None,body_source_path=None,
                    hair_assets=None,hair_evidence=None,hair_source_path=None,eye_light_assets=None,blush_makeup_assets=None,lipstick_assets=None,eyeliner_assets=None,eyelash_assets=None,brow_makeup_assets=None,iris_makeup_assets=None):
    import torch
    if body_bank is None and getattr(getattr(pipe,'people_prepared',None),'body_fields',()):
        raise ValueError('Preview omitted independently retained body inputs')
    source=pipe.src_f32
    if source is None:raise ValueError('All-face rendering needs the current immutable source')
    rgb=np.array(source[0].permute(1,2,0).to('cpu',torch.float32).numpy(),dtype=np.float32,copy=True)
    rgb.setflags(write=False)
    repaired=None
    if pipe.repair_base is not None:
        repaired=np.array(pipe.repair_base[0].permute(1,2,0).to('cpu',torch.float32).numpy(),dtype=np.float32,copy=True)
        repaired.setflags(write=False)
    prepared=prepare(state,asset_sha256,rgb,analyses,byte_budget=byte_budget,recovery_assets=recovery_assets,repaired=repaired,
        hair_assets=hair_assets,hair_evidence=hair_evidence,hair_source_path=hair_source_path,eye_light_assets=eye_light_assets,blush_makeup_assets=blush_makeup_assets,lipstick_assets=lipstick_assets,eyeliner_assets=eyeliner_assets,eyelash_assets=eyelash_assets,brow_makeup_assets=brow_makeup_assets,iris_makeup_assets=iris_makeup_assets)
    if body_bank is not None:
        from .body_pose_render import prepare as prepare_body
        prepared=prepare_body(prepared,body_bank,state,body_source,byte_budget=body_budget(prepared,byte_budget),source_path=body_source_path)
    return prepared


def synchronize(pipe,state,asset_sha256,analyses,*,byte_budget,recovery_assets=None,body_bank=None,body_source=None,body_source_path=None,
                    hair_assets=None,hair_evidence=None,hair_source_path=None,eye_light_assets=None,blush_makeup_assets=None,lipstick_assets=None,eyeliner_assets=None,eyelash_assets=None,brow_makeup_assets=None,iris_makeup_assets=None):
    prepared=prepare_preview(pipe,state,asset_sha256,analyses,byte_budget=byte_budget,recovery_assets=recovery_assets,body_bank=body_bank,body_source=body_source,body_source_path=body_source_path,
        hair_assets=hair_assets,hair_evidence=hair_evidence,hair_source_path=hair_source_path,eye_light_assets=eye_light_assets,blush_makeup_assets=blush_makeup_assets,lipstick_assets=lipstick_assets,eyeliner_assets=eyeliner_assets,eyelash_assets=eyelash_assets,brow_makeup_assets=brow_makeup_assets,iris_makeup_assets=iris_makeup_assets)
    PIPE.install(pipe,prepared);pipe.people_suspended=None
    return prepared


def suspend(pipe,reason):
    if type(reason) is not str or not reason:raise ValueError('People suspension needs a visible reason')
    PIPE.clear(pipe);pipe.people_key=None;pipe.people_suspended=reason


def require_ready(pipe):
    reason=getattr(pipe,'people_suspended',None)
    if reason:raise ValueError('Retained people edits are unresolved: '+reason)


def prepare_export(snapshot,source,repaired,*,byte_budget,recovery_assets=None,body_pose=None,body_source_path=None):
    """Original RGB8/16 enters once; all face solvers run before tile slicing."""
    from .people_snapshot import at_dimensions
    creative=snapshot.get('creative_source')
    if creative is not None:
        if (source.dtype!=np.float32 or source.ndim!=3 or source.shape[2]!=3
                or (creative['height'],creative['width'])!=source.shape[:2]
                or creative['sha256']!=snapshot['asset_sha256']
                or not np.isfinite(source).all() or np.any(source<0) or np.any(source>1)):
            raise ValueError('People export requires the verified creative float32 working source')
        divisor=1
    else:
        if source.dtype not in (np.uint8,np.uint16):raise ValueError('People export needs original RGB8/16')
        divisor=255 if source.dtype==np.uint8 else 65535
    state,asset,analyses=at_dimensions(snapshot,tuple(source.shape[:2]))
    rgb=np.array(source.astype(np.float32)/divisor,dtype=np.float32,copy=True)
    rgb.setflags(write=False)
    from .hair_colour_project import kwargs as hair_inputs
    prepared=prepare(state,asset,rgb,analyses,byte_budget=byte_budget,recovery_assets=recovery_assets,repaired=repaired,
        **hair_inputs(snapshot),force_hair_prompted=True,eye_light_assets=snapshot.get('support_assets',{}),blush_makeup_assets=snapshot.get('support_assets',{}),lipstick_assets=snapshot.get('support_assets',{}),eyeliner_assets=snapshot.get('support_assets',{}),eyelash_assets=snapshot.get('support_assets',{}),brow_makeup_assets=snapshot.get('support_assets',{}),iris_makeup_assets=snapshot.get('support_assets',{}))
    if body_pose is not None:
        from .arm_shape_project import check_snapshot
        from .body_pose_render import prepare as prepare_body
        frame=body_pose['source'];bank=check_snapshot(body_pose,frame)
        if (frame['height'],frame['width'])!=source.shape[:2]:raise ValueError('Body final preparation requires exact original dimensions')
        # Selection replay must use its canonical true-bit-depth decoder, even
        # when the requested output is RGB8 from RAW/high-bit-depth TIFF.
        # Output pixels retain their independent existing export decode path.
        prepared=prepare_body(prepared,bank,state,frame,byte_budget=body_budget(prepared,byte_budget),source_path=body_source_path)
    return prepared


def body_budget(prepared,budget):
    # Body composition already counts retained face evaluators and both maps.
    # Reserve independent colour/recovery arrays and source buffers as well.
    colour=sum(array.nbytes for record in prepared.effects for array in (record.delta,record.weights) if array is not None)
    recovery=sum(record['weight'].nbytes for record in prepared.recovery.values())
    h,w=prepared.geometry.delta.shape[1:3]
    return budget-colour-recovery-h*w*24
