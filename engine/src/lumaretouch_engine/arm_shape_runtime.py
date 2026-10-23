# SPDX-License-Identifier: GPL-3.0-or-later
"""Arm subfields with all-or-nothing ownership and common-map safety fences."""
import numpy as np
from . import arm_shape_state as S, body_pose_state as B, body_pose_evidence as E
from .arm_shape_field import ArmField


class ArmRefused(ValueError):
    def __init__(self,refusals):
        self.refusals=refusals
        super().__init__('Arm request refused: '+'; '.join(x['reason'] for x in refusals))


def _observed(p):
    return p['visibility']>=.8 and p['presence']>=.8 and 0<p['x']<1 and 0<p['y']<1


def _box(record,shape):
    h,w=shape;points=np.array([[p['x']*(w-1),p['y']*(h-1)] for p in record['points'] if _observed(p)],np.float64)
    return None if len(points)<2 else (points.min(axis=0),points.max(axis=0))


def _disk_meets(center,radius,box):
    lo,hi=box
    return np.linalg.norm(center-np.maximum(lo,np.minimum(hi,center)))<radius


def _distance(a,b,c,d):
    def cross(x,y):return x[0]*y[1]-x[1]*y[0]
    v=b-a;w=d-c;den=cross(v,w)
    if abs(den)>1e-9:
        t=cross(c-a,w)/den;s=cross(c-a,v)/den
        if 0<=t<=1 and 0<=s<=1:return 0.
    def point(p,x,y):
        v=y-x;dd=v@v
        return float(np.linalg.norm(p-(x+np.clip((p-x)@v/dd,0,1)*v))) if dd>1e-12 else float(np.linalg.norm(p-x))
    return min(point(a,c,d),point(b,c,d),point(c,a,b),point(d,a,b))


def _same_person_guards(field,row,support):
    h,w=field.shape;s=field.state;a=s[:2];u=s[2:4];b=a+u*s[4];r=max(s[7:])*s[6]
    # Opposite measured axes never supply widths, but can refute ownership.
    side=field.segment.split('_')[0];other='right' if side=='left' else 'left'
    for segment in (other+'_upper',other+'_forearm'):
        p,q=(row['record']['points'][i] for i in S.JOINTS[segment])
        if _observed(p) and _observed(q):
            c=np.array([p['x']*(w-1),p['y']*(h-1)]);d=np.array([q['x']*(w-1),q['y']*(h-1)])
            if _distance(a,b,c,d)<r: raise ValueError('Arm support reaches the opposite observed arm or a crossing')
    # Reject sharply folded own-arm geometry when the neighbouring segment is
    # actually observed. Missing adjacent joints do not invalidate partial mode.
    indices=(11,13,15) if side=='left' else (12,14,16)
    points=[row['record']['points'][i] for i in indices]
    if all(_observed(p) for p in points):
        xy=[np.array([p['x']*(w-1),p['y']*(h-1)]) for p in points]
        first=xy[1]-xy[0];second=xy[2]-xy[1];den=np.linalg.norm(first)*np.linalg.norm(second)
        if den<1 or first@second/den<.1: raise ValueError('Strongly folded/self-overlapping arm needs a different, explicitly supported policy')
    # Rectangles are explicit source-pixel keep-out regions, not model labels.
    # Conservative bounding-disk refusal may reject safe cases; it never crops
    # an AI mask to hide contamination or silently shrinks the requested field.
    for box in support['region']['exclusions']:
        lo=np.array([box[0]*(w-1),box[1]*(h-1)]);hi=np.array([box[2]*(w-1),box[3]*(h-1)])
        if any(_disk_meets(c,radius,(lo,hi)) for c,radius in field.supports):
            raise ValueError('Arm transition could reach a reviewed torso/contact/other-person exclusion')


def prepare_fields(state,asset_sha256,shape,*,people_state=None,byte_budget,operation_policies=None,source_pixels=None,source_frame=None):
    policies={**(operation_policies or {}),**S.policies()};state=B.check(state,operation_policies=policies);E.digest(asset_sha256)
    if type(byte_budget) is not int or byte_budget<1024*1024: raise ValueError('Arm field memory budget is missing')
    rows=[r for r in state['bodies'].values() if r['record']['source']['sha256']==asset_sha256]
    if source_frame is None:raise ValueError('Arm preparation requires the current exact canonical source frame')
    source_frame=E.source(source_frame)
    if source_frame['sha256']!=asset_sha256 or any(r['record']['source']!=source_frame for r in rows):
        raise ValueError('Arm records do not match the current source dimensions/orientation/digest')
    people=None
    if people_state is not None:
        from .people_state import check
        people=check(people_state)
    fields=[];failures=[]
    for row in rows:
        if not row['enabled']:continue
        for operation_id in S.OPERATION_IDS.values():
            item=row['operations'].get(operation_id)
            if item is None or not item['enabled'] or not S.active(item['recipe']):continue
            ref=row['record']['body_ref']
            try:
                if len(fields)>=32:raise ValueError('Arm active field budget exceeded; no truncation')
                face_id=None
                if people is not None and any(f['asset_sha256']==asset_sha256 for f in people['faces'].values()):
                    link=row['association']
                    if link is None or link['person_id'] not in people['persons'] or link['people_association_revision']!=people['association_revision']:
                        raise ValueError('Arm edits need current explicit anonymous body/person ownership, not nearest face')
                    faces=[x['face_instance_id'] for x in people['links'] if x['state']=='confirmed' and x['person_id']==link['person_id'] and people['faces'][x['face_instance_id']]['asset_sha256']==asset_sha256]
                    if len(faces)!=1:raise ValueError('Exactly one confirmed source face is needed for this body person')
                    face_id=faces[0]
                asset=B.support(state,ref,operation_id)
                field=ArmField(row,asset,shape,operation_id,source_pixels=source_pixels);field.associated_face_id=face_id
                if asset['data']['selection'] is not None:
                    from .arm_shape_selection import ownership_evidence
                    if asset['data']['selection']['ownership']!=ownership_evidence(row['record'],[r['record'] for r in rows],people):
                        raise ValueError('Observed body/face ownership changed since the SAM selection; re-propose and review')
                _same_person_guards(field,row,asset['data'])
                for other in rows:
                    if other['record']['body_ref']==ref:continue
                    box=_box(other['record'],shape)
                    if box is not None and any(_disk_meets(c,r,box) for c,r in field.supports):
                        raise ValueError('Arm support may affect another observed person; ownership is ambiguous')
                if people is not None:
                    h,w=shape
                    for face in people['faces'].values():
                        if face['asset_sha256']!=asset_sha256:continue
                        x0,y0,x1,y1=face['box'];box=(np.array([x0*(w-1),y0*(h-1)]),np.array([x1*(w-1),y1*(h-1)]))
                        if any(_disk_meets(c,r,box) for c,r in field.supports):raise ValueError('Arm support intersects a retained face')
                fields.append(field)
            except (ValueError,RuntimeError,OSError) as error:
                failures.append({'body_ref':ref,'operation_id':operation_id,'reason':str(error),'requested_recipe':item['recipe'],'applied':False})
    # Any requested side/segment refusal aborts the whole candidate. Linked edits
    # must never leave one side applied while presenting bilateral success.
    if failures:raise ArmRefused(failures)
    if sum(f.resident_bytes() for f in fields)>byte_budget:raise ValueError('Arm field retention exceeds budget')
    return tuple(fields)
