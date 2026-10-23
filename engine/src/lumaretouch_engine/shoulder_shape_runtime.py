"""One versioned inverse chain for bodies and faces, one final source sample.

BODY_THEN_FACE means inverse B(x) followed by the existing face inverse at B(x).
It is NOT addition of independent face/body displacements and NOT a second image
warp. Reuses CombinedGeometry's RGB8/16 + float mask/recovery sampling contract.
"""
from dataclasses import dataclass
from copy import deepcopy
import numpy as np
from . import body_pose_state as B, body_pose_evidence as E, shoulder_shape_state as S
from .shoulder_shape_field import ShoulderField
from .people_geometry import CombinedGeometry
from .body_pose_geometry import DEFAULT_BODY_ORDER,group_subfields

ORDER='body-then-face-inverse-v1'


class ShoulderRefused(ValueError):
    def __init__(self,refusals):
        self.refusals=refusals
        super().__init__('Shoulder request refused: '+'; '.join(x['reason'] for x in refusals))


@dataclass(frozen=True)
class ShoulderGeometry:
    delta:object
    owner:object
    peak:float
    overlap_pixels:int
    face_ids:tuple
    body_refs:tuple
    body_operation_order:dict
    composition_order:str=ORDER
    warp=CombinedGeometry.warp
    warp_original=CombinedGeometry.warp_original


def _visible_box(record,shape):
    h,w=shape
    p=np.array([[x['x']*(w-1),x['y']*(h-1)] for x in record['points'] if x['visibility']>=.8 and x['presence']>=.8 and 0<=x['x']<=1 and 0<=x['y']<=1],np.float64)
    return None if len(p)<2 else (p.min(axis=0),p.max(axis=0))


def _intersects_box(center,radius,box):
    lo,hi=box;nearest=np.maximum(lo,np.minimum(hi,center))
    return np.linalg.norm(center-nearest)<radius


def prepare_fields(state,asset_sha256,shape,*,people_state=None,byte_budget,operation_policies=None):
    state=B.check(state,operation_policies=operation_policies);E.digest(asset_sha256)
    if type(byte_budget) is not int or byte_budget<1024*1024:raise ValueError('Shoulder field budget is missing')
    people=None
    if people_state is not None:
        from .people_state import check
        people=check(people_state)
    rows=[row for row in state['bodies'].values() if row['record']['source']['sha256']==asset_sha256]
    active=[row for row in rows if row['enabled'] and S.OPERATION_ID in row['operations'] and row['operations'][S.OPERATION_ID]['enabled'] and S.active(row['operations'][S.OPERATION_ID]['recipe'])]
    if len(active)>8:raise ValueError('Shoulder body budget exceeded; no silent truncation')
    fields=[];failures=[]
    for row in active:
        ref=row['record']['body_ref']
        try:
            link=row['association']
            if people is not None and any(f['asset_sha256']==asset_sha256 for f in people['faces'].values()):
                if link is None or link['person_id'] not in people['persons'] or link['people_association_revision']!=people['association_revision']:raise ValueError('Confirm current body-to-anonymous-person association explicitly; never choose nearest face')
                faces=[x for x in people['links'] if x['person_id']==link['person_id'] and x['state']=='confirmed' and people['faces'][x['face_instance_id']]['asset_sha256']==asset_sha256]
                if len(faces)!=1:raise ValueError('Body person must have one explicitly confirmed face in this source before combined face/body shaping')
            field=ShoulderField(row,shape)
            field.associated_face_id=faces[0]['face_instance_id'] if people is not None and any(f['asset_sha256']==asset_sha256 for f in people['faces'].values()) else None
            if people is not None:
                h,w=shape
                for face in people['faces'].values():
                    if face['asset_sha256']!=asset_sha256:continue
                    x0,y0,x1,y1=face['box'];box=(np.array([x0*(w-1),y0*(h-1)]),np.array([x1*(w-1),y1*(h-1)]))
                    if any(_intersects_box(c,r,box) for c,r in field.supports):raise ValueError('Shoulder support intersects a retained face; fixed head support cannot be verified')
            # Even an unedited other body can own pixels near this support.
            # Boxes are conservative visible bounds, never an inferred body mesh.
            for other in rows:
                if other['record']['body_ref']==ref:continue
                box=_visible_box(other['record'],shape)
                if box is not None and any(_intersects_box(c,r,box) for c,r in field.supports):raise ValueError('Visible shoulder support overlaps another detected body; ownership is ambiguous')
            fields.append(field)
        except (ValueError,RuntimeError,OSError) as error:
            failures.append({'body_ref':ref,'reason':str(error),'operation_id':S.OPERATION_ID,'requested_recipe':row['operations'][S.OPERATION_ID]['recipe'],'applied':False})
    if failures:raise ShoulderRefused(failures)
    if sum(f.resident_bytes() for f in fields)>byte_budget:raise ValueError('Retained shoulder fields exceed admitted budget')
    return tuple(fields)


def _face_stage(faces,points):
    delta=np.zeros_like(points);owner=np.full(len(points),-1,np.int32);overlap=np.zeros(len(points),bool)
    for i,face in enumerate(faces):
        values=face.evaluate(points)
        if values.shape!=points.shape or not np.isfinite(values).all():raise ValueError('Invalid existing face evaluator')
        active=np.any(values!=0,axis=1);overlap|=active&(owner>=0)
        take=active&(owner<0);delta[take]=values[take];owner[take]=i
    return delta,owner,overlap


def compose(faces,bodies,shape,*,byte_budget,band_pixels=65536,body_operation_order=DEFAULT_BODY_ORDER):
    """Host must pass FaceGeometry evaluators, not a pre-sampled/warped image.

    Body ownership is separate metadata. Body IDs never enter face_instance_id.
    The final combined map is consumed once by existing image/support consumers.
    """
    h,w=shape
    if type(h) is not int or type(w) is not int or min(h,w)<2:raise ValueError('Invalid common geometry dimensions')
    if type(band_pixels) is not int or not w<=band_pixels<=1048576:raise ValueError('Common geometry needs a bounded complete-row band')
    faces=tuple(sorted(faces,key=lambda f:f.face_instance_id));bodies=group_subfields(bodies,body_operation_order)
    if len({f.face_instance_id for f in faces})!=len(faces):raise ValueError('Duplicate face target would apply strength twice')
    if any(f.shape!=tuple(shape) for f in (*faces,*bodies)):raise ValueError('Every field must share canonical source coordinates')
    resident=sum(f.resident_bytes() for f in (*faces,*bodies))
    # Includes delta/owner plus bounded float64 point, displacement and Jacobian bands.
    if type(byte_budget) is not int or resident+h*w*24+band_pixels*160>byte_budget:raise ValueError('Common body/face geometry exceeds admitted memory budget')
    for i,a in enumerate(bodies):
        for b in bodies[i+1:]:
            if any(np.linalg.norm(c-d)<r+s for c,r in a.supports for d,s in b.supports):raise ValueError('Two active body supports overlap; no silent priority over people')
    delta=np.zeros((1,h,w,2),np.float32);owner=np.full((h,w),-1,np.int32);overlap=0;peak=0.
    rows=max(1,band_pixels//w)
    for y in range(0,h,rows):
        end=min(h,y+rows);yy,xx=np.mgrid[y:end,:w];points=np.stack((xx.ravel(),yy.ravel()),axis=1).astype(np.float64)
        body_delta=np.zeros_like(points);body_owner=np.full(len(points),-1,np.int32)
        for i,field in enumerate(bodies):
            value=field.evaluate(points);active=np.any(value!=0,axis=1)
            if np.any(active&(body_owner>=0)):raise ValueError('Ambiguous body support at evaluated coordinates')
            body_delta[active]=value[active];body_owner[active]=i
        # Exact off-grid inverse composition: x -> B(x) -> Face(B(x)).
        face_delta,face_owner,face_overlap=_face_stage(faces,points-body_delta)
        for i,field in enumerate(bodies):
            affected=(body_owner==i)&(face_owner>=0)
            if np.any(affected):
                expected=getattr(field,'associated_face_id',None)
                if expected is None or any(faces[index].face_instance_id!=expected for index in np.unique(face_owner[affected])):raise ValueError('A shoulder map meets another face owner; explicit ownership correction required')
        total=body_delta+face_delta
        if not np.isfinite(total).all():raise ValueError('Nonfinite final body/face field')
        block=total.reshape(end-y,w,2).astype(np.float32)
        delta[0,y:end]=block;peak=max(peak,float(np.max(np.abs(block))))
        # Negative body-owner namespace is distinct from nonnegative face indices.
        owners=np.where(body_owner>=0,-2-body_owner,face_owner)
        owner[y:end]=owners.reshape(end-y,w);overlap+=int(np.count_nonzero(face_overlap))
    # Final map, not just each native lobe, is admitted. The checks include band seams.
    for y in range(0,h-1,rows):
        end=min(h-1,y+rows);base=delta[0,y:end,:-1]
        dx=delta[0,y:end,1:]-base;dy=delta[0,y+1:end+1,:-1]-base
        det=(1-dx[...,0])*(1-dy[...,1])-dy[...,0]*dx[...,1]
        if not np.isfinite(det).all() or np.any(det<.15) or np.any(det>6):raise ValueError('Final composed body/face Jacobian refused; reduce or correct the actual request')
    delta.setflags(write=False);owner.setflags(write=False)
    return ShoulderGeometry(delta,owner,peak,overlap,tuple(f.face_instance_id for f in faces),tuple(deepcopy(f.body_ref) for f in bodies),body_operation_order.record())


def outcome(fields,geometry,*,request_id,render_revision,original_dimensions,rendered_pixels,published_frame_id,sampling_passes):
    """Call only after the host actually renders and publishes this exact map."""
    from hashlib import sha256
    E.token(request_id);E.token(published_frame_id);E.revision(render_revision)
    pixels=np.asarray(rendered_pixels)
    if pixels.ndim!=3 or pixels.shape[2]!=3 or pixels.dtype not in (np.uint8,np.uint16,np.float32) or not np.isfinite(pixels).all() or pixels.shape[:2]!=geometry.delta.shape[1:3]:raise ValueError('Outcome needs actual rendered RGB pixels matching the composed field')
    if type(sampling_passes) is not int or sampling_passes!=1:raise ValueError('Actual geometry sampling count was not one')
    render_dimensions=(pixels.shape[1],pixels.shape[0])
    return {'version':1,'request_id':request_id,'published_frame_id':published_frame_id,'output_pixel_sha256':sha256(memoryview(np.ascontiguousarray(pixels))).hexdigest(),'output_dtype':str(pixels.dtype),'geometry_delta_sha256':sha256(memoryview(geometry.delta)).hexdigest(),'render_revision':render_revision,'composition_order':ORDER,'body_operation_order':deepcopy(geometry.body_operation_order),'original_dimensions':list(original_dimensions),'render_dimensions':list(render_dimensions),'original_resolution':tuple(original_dimensions)==tuple(render_dimensions),'single_source_sample':True,'fields':[dict(f.facts,status='rendered',applied=True) for f in fields],'max_displacement_component':geometry.peak,'face_overlap_pixels':geometry.overlap_pixels,'runtime_quality_accepted':False}
