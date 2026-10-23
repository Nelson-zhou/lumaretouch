# SPDX-License-Identifier: GPL-3.0-or-later
"""Source-owned bilateral waist admission, all-or-nothing before common solve."""
import numpy as np
from . import waist_shape_state as S,body_pose_state as B,body_pose_evidence as E
from .waist_shape_field import WaistField


class WaistRefused(ValueError):
    def __init__(self,refusals):
        self.refusals=refusals
        super().__init__('Waist request refused: '+'; '.join(x['reason'] for x in refusals))


def _observed(p):return p['visibility']>=.8 and p['presence']>=.8 and 0<p['x']<1 and 0<p['y']<1


def _overlap(a,b):return bool(np.all(a[0]<b[1]) and np.all(b[0]<a[1]))


def _box(values,shape):
    h,w=shape;xy=np.array([[p['x']*(w-1),p['y']*(h-1)] for p in values if _observed(p)],np.float64)
    return None if len(xy)<2 else (xy.min(axis=0),xy.max(axis=0))


def prepare_fields(state,asset_sha256,shape,*,people_state=None,byte_budget,operation_policies=None,source_pixels=None,source_frame=None):
    policies={**(operation_policies or {}),**S.policies()};state=B.check(state,operation_policies=policies);E.digest(asset_sha256)
    if type(byte_budget) is not int or byte_budget<1024*1024:raise ValueError('Waist field memory budget is missing')
    rows=[r for r in state['bodies'].values() if r['record']['source']['sha256']==asset_sha256]
    if source_frame is None:raise ValueError('Waist preparation requires the exact canonical source frame')
    source_frame=E.source(source_frame)
    if source_frame['sha256']!=asset_sha256 or any(r['record']['source']!=source_frame for r in rows):
        raise ValueError('Waist records differ from current source dimensions, orientation or digest')
    people=None
    if people_state is not None:
        from .people_state import check
        people=check(people_state)
    fields=[];failures=[];h,w=shape
    for row in rows:
        item=row['operations'].get(S.OPERATION_ID)
        if not row['enabled'] or item is None or not item['enabled'] or not S.active(item['recipe']):continue
        ref=row['record']['body_ref']
        try:
            if len(fields)>=32:raise ValueError('Waist active field budget exceeded; no truncation')
            face_id=None
            if people is not None and any(f['asset_sha256']==asset_sha256 for f in people['faces'].values()):
                link=row['association']
                if link is None or link['person_id'] not in people['persons'] or link['people_association_revision']!=people['association_revision']:
                    raise ValueError('Waist needs current explicit anonymous body/person ownership, never nearest face')
                faces=[x['face_instance_id'] for x in people['links'] if x['state']=='confirmed' and x['person_id']==link['person_id'] and people['faces'][x['face_instance_id']]['asset_sha256']==asset_sha256]
                if len(faces)!=1:raise ValueError('Exactly one confirmed source face is needed for this body person')
                face_id=faces[0]
            asset=B.support(state,ref,S.OPERATION_ID);field=WaistField(row,asset,shape);field.associated_face_id=face_id
            envelope=field.envelope()
            for box in asset['data']['region']['exclusions']:
                rectangle=(np.array([box[0]*(w-1),box[1]*(h-1)]),np.array([box[2]*(w-1),box[3]*(h-1)]))
                if _overlap(envelope,rectangle):raise ValueError('Waist transition reaches a reviewed hand, garment/contact or other-person exclusion')
            # Actual arm observations can disprove clear waist ownership. Missing
            # joints cannot fabricate an arm: explicit no-occlusion review still required.
            for ids in ((11,13),(13,15),(12,14),(14,16)):
                points=[row['record']['points'][i] for i in ids]
                if all(_observed(p) for p in points):
                    box=_box(points,shape)
                    margin=2.*min(w,h)/min(source_frame['width'],source_frame['height'])
                    box=(box[0]-margin,box[1]+margin)
                    if _overlap(envelope,box):raise ValueError('Waist transition may reach an observed arm; clear bilateral ownership is required')
            for other in rows:
                if other['record']['body_ref']==ref:continue
                box=_box(other['record']['points'],shape)
                if box is not None and _overlap(envelope,box):raise ValueError('Waist transition may reach another observed person')
            if people is not None:
                for face in people['faces'].values():
                    if face['asset_sha256']!=asset_sha256:continue
                    x0,y0,x1,y1=face['box'];box=(np.array([x0*(w-1),y0*(h-1)]),np.array([x1*(w-1),y1*(h-1)]))
                    if _overlap(envelope,box):raise ValueError('Waist transition intersects a retained face')
            fields.append(field)
        except (ValueError,RuntimeError,OSError) as error:
            failures.append({'body_ref':ref,'operation_id':S.OPERATION_ID,'reason':str(error),'requested_recipe':item['recipe'],'applied':False})
    if failures:raise WaistRefused(failures)
    if sum(f.resident_bytes() for f in fields)>byte_budget:raise ValueError('Waist field retention exceeds memory budget')
    return tuple(fields)
