# SPDX-License-Identifier: GPL-3.0-or-later
"""Prepare real leg length fields, not images or a competing body bank/render path."""
import numpy as np
from . import body_pose_state as B, body_pose_evidence as E, leg_length_state as S
from .leg_length_field import LegLengthField


class LegLengthRefused(ValueError):
    def __init__(self, refusals):
        self.refusals = refusals
        super().__init__('Leg length request refused: '+'; '.join(x['reason'] for x in refusals))


def _box(record,shape):
    h,w = shape
    p = np.array([[x['x']*(w-1),x['y']*(h-1)] for x in record['points']
                  if x['visibility']>=.8 and x['presence']>=.8 and 0<=x['x']<=1 and 0<=x['y']<=1],np.float64)
    return None if len(p)<2 else (p.min(axis=0),p.max(axis=0))


def _meets_disk(center,radius,box):
    lo,hi = box
    return np.linalg.norm(center-np.maximum(lo,np.minimum(hi,center))) < radius


def prepare_fields(state,asset_sha256,shape,*,people_state=None,byte_budget,operation_policies=None):
    policies = {**(operation_policies or {}),**S.policies()}
    state = B.check(state,operation_policies=policies); E.digest(asset_sha256)
    if type(byte_budget) is not int or byte_budget < 1024*1024:
        raise ValueError('Leg length field budget is missing')
    people = None
    if people_state is not None:
        from .people_state import check
        people = check(people_state)
    rows = [r for r in state['bodies'].values() if r['record']['source']['sha256']==asset_sha256]
    active = [r for r in rows if r['enabled'] and S.OPERATION_ID in r['operations']
              and r['operations'][S.OPERATION_ID]['enabled'] and S.active(r['operations'][S.OPERATION_ID]['recipe'])]
    if len(active)>8: raise ValueError('Leg length body budget exceeded; no silent truncation')
    fields=[]; failures=[]
    for row in active:
        ref = row['record']['body_ref']
        try:
            faces=[]; link=row['association']
            if people is not None and any(f['asset_sha256']==asset_sha256 for f in people['faces'].values()):
                if link is None or link['person_id'] not in people['persons'] or link['people_association_revision']!=people['association_revision']:
                    raise ValueError('Explicitly confirm the current anonymous body/person association; never use nearest face')
                faces=[f for f in people['links'] if f['person_id']==link['person_id'] and f['state']=='confirmed' and people['faces'][f['face_instance_id']]['asset_sha256']==asset_sha256]
                if len(faces)!=1: raise ValueError('Combined face/body geometry needs one explicitly confirmed face for this body person in the source')
            field=LegLengthField(row,B.support(state,ref,S.OPERATION_ID),shape)
            field.associated_face_id=faces[0]['face_instance_id'] if faces else None
            # Bounding disks deliberately overestimate visible rectangular supports.
            # Conservative refusal is preferable to bending another person's pixels.
            for other in rows:
                if other['record']['body_ref']==ref: continue
                box=_box(other['record'],shape)
                if box is not None and any(_meets_disk(c,r,box) for c,r in field.supports):
                    raise ValueError('Leg length falloff may meet another observed body; ownership is ambiguous')
            if people is not None:
                h,w=shape
                for face in people['faces'].values():
                    if face['asset_sha256']!=asset_sha256:continue
                    x0,y0,x1,y1=face['box'];box=(np.array([x0*(w-1),y0*(h-1)]),np.array([x1*(w-1),y1*(h-1)]))
                    if any(_meets_disk(c,r,box) for c,r in field.supports):
                        raise ValueError('Leg length falloff intersects a retained face; visible ownership is unsafe')
            fields.append(field)
        except (ValueError,RuntimeError,OSError) as error:
            failures.append({'body_ref':ref,'operation_id':S.OPERATION_ID,'reason':str(error),
                             'requested_recipe':row['operations'][S.OPERATION_ID]['recipe'],'applied':False})
    if failures: raise LegLengthRefused(failures)
    if sum(f.resident_bytes() for f in fields)>byte_budget:
        raise ValueError('Retained leg length fields exceed the admitted budget')
    return tuple(fields)
