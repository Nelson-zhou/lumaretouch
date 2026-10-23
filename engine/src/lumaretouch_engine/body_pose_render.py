"""Body joins the actual common portrait map, before face inverse evaluation."""
from copy import deepcopy
from . import body_pose_evidence as E,body_pose_operations as O,body_pose_project as D
from . import shoulder_shape_project as P,shoulder_shape_adapter as A
from .body_pose_geometry import DEFAULT_BODY_ORDER


def source(value):
    return E.source({key:value[key] for key in ('sha256','width','height')}|{'orientation':E.ORIENTATION})


def retained(bank):return bool(bank['bodies'])


def check_source(bank,frame):
    frame=E.source(frame)
    if any(row['record']['source']!=frame for row in bank['bodies'].values()):raise ValueError('Retained body observations belong to another original source/orientation/dimensions')
    return frame


def prepare(prepared,bank,people,frame,*,byte_budget):
    from .people_geometry_identity import digest
    frame=check_source(bank,source(frame))
    wrapper=A.prepare_common(prepared,prepared.face_fields,bank,people,frame,people_geometry_identity=digest({'state':people,'asset_sha256':frame['sha256']}),byte_budget=byte_budget)
    return wrapper.people


def capture(engine,snap,state,path,people_graph=None):
    bank=D.bank(state)
    snap['body_pose']=None
    if not retained(bank):return snap
    from .local_mask_state import source_digest
    if not path:raise ValueError('Body export needs its exact target source path')
    records=list(bank['bodies'].values());frame=records[0]['record']['source']
    if source_digest(path)!=frame['sha256']:raise ValueError('Body export source bytes changed')
    check_source(bank,frame);snap['body_pose']=P.snapshot(bank,frame)
    if snap.get('people') is None:
        from .people_snapshot import capture as capture_people
        snap['people']=capture_people(engine._people_owner().snapshot() if people_graph is None else people_graph,frame['sha256'],{})
        snap['people']['support_assets']=deepcopy(engine._people_support)
    return snap


def check_export_decode(snap,path,before,shape):
    frozen=snap.get('body_pose')
    if frozen is None:return
    from .local_mask_state import file_stamp,source_digest
    if before is None or file_stamp(path)!=before:raise ValueError('Body source changed during original-resolution decode')
    frame=frozen['source'];P.check_snapshot(frozen,frame)
    if (frame['height'],frame['width'])!=tuple(shape) or source_digest(path)!=frame['sha256']:raise ValueError('Decoded body source identity or dimensions differ from retained observations')
    if file_stamp(path)!=before:raise ValueError('Body source changed during decoded-source verification')
    snap['body_pose_source_path']=path;snap['body_pose_source_stamp']=list(before)


def verify_render_source(spec):
    if getattr(spec,'body_pose',None) is None:return
    from .local_mask_state import file_stamp
    if not spec.body_pose_source_path or list(file_stamp(spec.body_pose_source_path))!=spec.body_pose_source_stamp:raise ValueError('Body source changed after verified full-resolution decode')


def configure_export(spec,snap,shape,*,for_document):
    frozen=snap.get('body_pose');spec.body_pose=frozen
    if frozen is None:return
    if not for_document:raise ValueError('Body reviews/pose cannot be copied to another image; explicitly transfer values and prepare that target')
    frame=frozen['source'];P.check_snapshot(frozen,frame)
    if (frame['height'],frame['width'])!=tuple(shape):raise ValueError('Body export must solve original source dimensions, never enlarge a proxy field')
    if spec.people is None:raise ValueError('Body export lacks the frozen common portrait owner')
    spec.body_pose_source_path=snap.get('body_pose_source_path');spec.body_pose_source_stamp=deepcopy(snap.get('body_pose_source_stamp'))
    verify_render_source(spec)


def geometry_record(state):
    """Rendered-canvas support identity excludes neutral review/cursor changes."""
    bank=D.bank(state);rows=[]
    for key,row in sorted(bank['bodies'].items()):
        if not row['enabled']:continue
        operations={}
        for operation_id,item in row['operations'].items():
            if not item['enabled']:continue
            policy=O.policies().get(operation_id)
            if policy is None or policy.is_active(item['recipe']):
                recipe=deepcopy(item['recipe'])
                if operation_id==O.SHOULDER_OPERATION:
                    for pair in ('square','width'):recipe[pair].pop('linked',None)
                operations[operation_id]={'recipe':recipe,'support_sha256':item['support_sha256']}
        if operations:rows.append({'record':row['record'],'operations':operations})
    return {'version':1,'body_order':DEFAULT_BODY_ORDER.record(),'body_then_face':'body-then-face-inverse-v1','bodies':rows} if rows else None


def fastpath_blocker(value):
    # Unknown enabled intent is a blocker too; never use neutral copy-through.
    if value is None:return False
    bank=P.unpack(value)
    for row in bank['bodies'].values():
        try:
            if O.active_operations(row):return True
        except ValueError:return True
    return False


def export_outcome(prepared,pixels,source_dimensions):
    """Actual final render buffer, not an encoded-file/save-success receipt.

    Later profile/container/watermark/layout publication remains the existing
    export owner's responsibility. Crop/optics/upscale may change output size.
    """
    if prepared is None or prepared.body_operation_order is None:return None
    import numpy as np
    from hashlib import sha256
    value=np.asarray(pixels)
    if value.ndim!=3 or value.shape[2]!=3 or value.dtype not in (np.uint8,np.uint16,np.float32,np.float64):raise ValueError('Body export outcome lacks an actual RGB render buffer')
    h,w=prepared.geometry.delta.shape[1:3]
    if (w,h)!=tuple(source_dimensions):raise ValueError('Body export field was not recomputed at original dimensions')
    digest=sha256()
    for row in value:
        if not np.isfinite(row).all():raise ValueError('Nonfinite body export output')
        digest.update(memoryview(np.ascontiguousarray(row)))
    return {'version':1,'stage':'export-render-buffer-before-container-publication','encoded_file_published':False,
            'render_buffer_sha256':digest.hexdigest(),'render_dtype':str(value.dtype),'render_dimensions':[value.shape[1],value.shape[0]],
            'original_dimensions':[w,h],'geometry_original_resolution':True,'body_operation_order':deepcopy(prepared.body_operation_order),
            'composition_order':'body-then-face-inverse-v1','common_portrait_sampling_stages':1,
            'geometry_delta_sha256':sha256(memoryview(prepared.geometry.delta)).hexdigest(),
            'fields':[dict(field.facts,status='rendered',applied=True) for field in prepared.body_fields],
            'runtime_quality_accepted':False}
