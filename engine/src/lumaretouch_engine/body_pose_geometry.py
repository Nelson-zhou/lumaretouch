"""One off-grid inverse chain per stable BodyRef, not one body row per effect."""
from dataclasses import dataclass
import math
import numpy as np
from . import body_pose_evidence as E,body_pose_operations as O


@dataclass(frozen=True)
class FrozenBodyOrder:
    version:int
    operation_ids:tuple

    def record(self):
        if type(self.version) is not int or self.version<1 or type(self.operation_ids) is not tuple or len(self.operation_ids)>O.MAX_OPERATIONS or len(set(self.operation_ids))!=len(self.operation_ids):raise ValueError('Invalid frozen body operation order')
        for operation_id in self.operation_ids:E.token(operation_id)
        return {'version':self.version,'operation_ids':list(self.operation_ids)}


DEFAULT_BODY_ORDER=FrozenBodyOrder(1,(O.SHOULDER_OPERATION,))
LEG_BODY_ORDER=FrozenBodyOrder(2,(O.SHOULDER_OPERATION,'lnx.leg_shape.v1'))
ARM_OPERATION_IDS=tuple('lnx.arm_shape.'+segment+'.v1' for segment in ('left_upper','left_forearm','right_upper','right_forearm'))
PORTRAIT_BODY_ORDER=FrozenBodyOrder(3,(*LEG_BODY_ORDER.operation_ids,*ARM_OPERATION_IDS))

WAIST_BODY_ORDER=FrozenBodyOrder(4,(*PORTRAIT_BODY_ORDER.operation_ids,'lnx.waist_shape.v1'))

LEG_LENGTH_BODY_ORDER=FrozenBodyOrder(5,(*WAIST_BODY_ORDER.operation_ids,'lnx.leg_length.v1'))

NECK_BODY_ORDER=FrozenBodyOrder(6,(*LEG_LENGTH_BODY_ORDER.operation_ids,'lnx.neck_shape.v1'))

TORSO_LENGTH_BODY_ORDER=FrozenBodyOrder(7,(*NECK_BODY_ORDER.operation_ids,'lnx.torso_length.v1'))

WAIST_LENGTH_BODY_ORDER=FrozenBodyOrder(8,(*TORSO_LENGTH_BODY_ORDER.operation_ids,'lnx.waist_length.v1'))

HEAD_SIZE_BODY_ORDER=FrozenBodyOrder(9,(*WAIST_LENGTH_BODY_ORDER.operation_ids,'lnx.head_size.v1'))

def effective_order(state):
    """One authoritative chain. Neutral new families preserve older map identity."""
    active={op for row in state['bodies'].values() for op in O.active_operations(row)}
    if 'lnx.head_size.v1' in active:return HEAD_SIZE_BODY_ORDER
    if 'lnx.waist_length.v1' in active:return WAIST_LENGTH_BODY_ORDER
    if 'lnx.torso_length.v1' in active:return TORSO_LENGTH_BODY_ORDER
    if 'lnx.neck_shape.v1' in active:return NECK_BODY_ORDER
    if 'lnx.leg_length.v1' in active:return LEG_LENGTH_BODY_ORDER
    if 'lnx.waist_shape.v1' in active:return WAIST_BODY_ORDER
    if active.intersection(ARM_OPERATION_IDS):return PORTRAIT_BODY_ORDER
    if 'lnx.leg_shape.v1' in active:return LEG_BODY_ORDER
    return DEFAULT_BODY_ORDER



class BodyGeometry:
    def __init__(self,fields,order=DEFAULT_BODY_ORDER):
        self.order=order;order.record();fields=tuple(fields)
        if not fields:raise ValueError('Body geometry requires actual prepared subfields')
        first=fields[0];self.body_ref=E.ref(first.body_ref);self.shape=tuple(first.shape)
        first_record=E.check(first.record);self.record=first_record
        if first_record['body_ref']!=self.body_ref:raise ValueError('Body subfield observation differs from its declared target')
        self.associated_face_id=getattr(first,'associated_face_id',None)
        by_operation={}
        for field in fields:
            operation_id=E.token(field.operation_id)
            if operation_id in by_operation:raise ValueError('Duplicate operation would repeat one body’s strength')
            if operation_id not in order.operation_ids:raise ValueError('Actual body operation is absent from the explicit frozen order')
            if E.ref(field.body_ref)!=self.body_ref or tuple(field.shape)!=self.shape or E.check(field.record)!=first_record:raise ValueError('Body subfields do not share exact source/observation/analysis ownership')
            if getattr(field,'associated_face_id',None)!=self.associated_face_id:raise ValueError('Body operation association ownership differs')
            bound=getattr(field,'max_displacement',None)
            if type(bound) not in (int,float) or not math.isfinite(bound) or bound<0:raise ValueError('Body subfield lacks a finite conservative displacement bound')
            by_operation[operation_id]=field
        self.fields=tuple(by_operation[key] for key in order.operation_ids if key in by_operation)
        # Later subfield input may already have moved. These conservative support
        # envelopes include its inverse preimage under preceding body subfields.
        supports=[];prefix=0.
        for field in self.fields:
            for center,radius in field.supports:
                center=np.array(center,dtype=np.float64,copy=True)
                if center.shape!=(2,) or not np.isfinite(center).all() or not math.isfinite(radius) or radius<=0:raise ValueError('Invalid source-owned body support envelope')
                center.setflags(write=False);supports.append((center,float(radius)+prefix))
            prefix+=float(field.max_displacement)
        self.supports=tuple(supports);self.max_displacement=prefix

    def evaluate(self,points):
        points=np.asarray(points,dtype=np.float64)
        if points.ndim!=2 or points.shape[1]!=2 or not np.isfinite(points).all():raise ValueError('Body chain requires actual finite off-grid points')
        total=np.zeros_like(points)
        for field in self.fields:
            value=field.evaluate(points-total)
            if value.shape!=points.shape or not np.isfinite(value).all():raise ValueError('Invalid body operation inverse output')
            total+=value
        return total

    def resident_bytes(self):
        return sum(field.resident_bytes() for field in self.fields)+sum(center.nbytes for center,_ in self.supports)


def group_subfields(fields,order=DEFAULT_BODY_ORDER):
    order.record();grouped={}
    for field in fields:
        children=field.fields if isinstance(field,BodyGeometry) else (field,)
        if isinstance(field,BodyGeometry) and field.order!=order:raise ValueError('Prepared body chain order changed')
        for child in children:
            ref=E.ref(child.body_ref);key=ref['body_instance_id'];grouped.setdefault(key,[]).append(child)
    return tuple(BodyGeometry(grouped[key],order) for key in sorted(grouped))


def require_prepared(state,asset_sha256,fields,*,operation_policies=None,people_state=None):
    """Every active operation needs a field bound to its CURRENT exact inputs."""
    expected={}
    for row in state['bodies'].values():
        if row['record']['source']['sha256']!=asset_sha256:continue
        for operation_id in O.active_operations(row,operation_policies=operation_policies):
            expected[(E.content_digest(row['record']['body_ref']),operation_id)]=row
    supplied=[]
    people=None
    if people_state is not None:
        from .people_state import check
        people=check(people_state)
    for field in fields:
        children=field.fields if isinstance(field,BodyGeometry) else (field,)
        for child in children:
            key=(E.content_digest(E.ref(child.body_ref)),E.token(child.operation_id));supplied.append(key)
            row=expected.get(key)
            if row is None or E.check(child.record)!=row['record'] or getattr(child,'input_binding_sha256',None)!=O.field_binding(row,child.operation_id):raise ValueError('Prepared body operation is stale: recipe/review/support/record/association changed')
            if row['operations'][child.operation_id]['review'] is None:raise ValueError('Prepared active body operation lacks its current operation-specific review')
            if people is not None:
                source_faces=[face for face in people['faces'].values() if face['asset_sha256']==asset_sha256]
                expected_face=None
                if source_faces:
                    link=row['association']
                    if link is None or link['person_id'] not in people['persons'] or link['people_association_revision']!=people['association_revision']:raise ValueError('Prepared body operation has stale anonymous-person ownership')
                    confirmed=[link_row['face_instance_id'] for link_row in people['links'] if link_row['person_id']==link['person_id'] and link_row['state']=='confirmed' and people['faces'][link_row['face_instance_id']]['asset_sha256']==asset_sha256]
                    if len(confirmed)!=1:raise ValueError('Body requires exactly one explicitly confirmed source face, never nearest-face identity')
                    expected_face=confirmed[0]
                if getattr(child,'associated_face_id',None)!=expected_face:raise ValueError('Prepared body field refers to an outdated face association')
    if len(set(supplied))!=len(supplied):raise ValueError('Duplicate prepared body operation')
    if set(supplied)!=set(expected):raise ValueError('Prepared body fields do not exactly cover active operation intent; no silent partial export')
