"""Real preview/export integration with preserved off-grid face evaluators.

Replace the existing prepared people's geometry, do not warp an already rendered
image. FaceGeometry evaluators must be retained by the host's face preparation;
passing only an old sampled delta would lose exact off-grid composition.
"""
from copy import deepcopy
from dataclasses import dataclass,replace
import numpy as np
from . import body_pose_evidence as E,body_pose_state as B
from . import shoulder_shape_runtime as R,shoulder_shape_project as P
from .body_pose_geometry import DEFAULT_BODY_ORDER,require_prepared


@dataclass(frozen=True)
class PreparedShoulders:
    people:object
    body_fields:tuple
    source:dict
    identity_sha256:str
    facts:tuple

    @property
    def geometry(self):return self.people.geometry


def identity(bank,source,people_geometry_identity):
    state=B.check(bank);source=E.source(source);E.digest(people_geometry_identity)
    records=[{'record':row['record'],'operations':row['operations'],'association':row['association'],'enabled':row['enabled']} for key,row in sorted(state['bodies'].items()) if row['record']['source']['sha256']==source['sha256']]
    return E.content_digest({'version':1,'source':source,'bodies':records,'people_geometry_sha256':people_geometry_identity,'order':R.ORDER})


def prepare_common(prepared_people,face_fields,bank,people_state,source,*,people_geometry_identity,byte_budget,band_pixels=65536,extra_body_fields=(),operation_policies=None,body_operation_order=DEFAULT_BODY_ORDER):
    """Actual host preparation, neutral bodies reuse the already prepared map."""
    face_fields=tuple(face_fields)
    source=E.source(source);shape=tuple(prepared_people.geometry.delta.shape[1:3]);h,w=shape
    E.whole_source_shape(source,(h,w))
    bank=B.check(bank,operation_policies=operation_policies)
    fields=R.prepare_fields(bank,source['sha256'],shape,people_state=people_state,byte_budget=byte_budget,operation_policies=operation_policies)+tuple(extra_body_fields)
    require_prepared(bank,source['sha256'],fields,operation_policies=operation_policies,people_state=people_state)
    if fields:
        if tuple(sorted(f.face_instance_id for f in face_fields))!=tuple(prepared_people.geometry.face_ids):raise ValueError('Common preparation lacks exact original face evaluators')
        # Release/replacement of the prior map is the host's responsibility. Admit
        # both maps here because the previous prepared publication may remain live.
        old_bytes=prepared_people.geometry.delta.nbytes+prepared_people.geometry.owner.nbytes
        geometry=R.compose(face_fields,fields,shape,byte_budget=byte_budget-old_bytes,band_pixels=band_pixels,body_operation_order=body_operation_order)
        prepared_people=replace(prepared_people,geometry=geometry)
    else:
        old=prepared_people.geometry
        prepared_people=replace(prepared_people,geometry=R.ShoulderGeometry(old.delta,old.owner,old.peak,old.overlap_pixels,old.face_ids,(),body_operation_order.record()))
    prepared_people=replace(prepared_people,body_fields=fields,body_operation_order=body_operation_order.record())
    return PreparedShoulders(prepared_people,fields,source,E.content_digest({'bank_identity':identity(bank,source,people_geometry_identity),'body_order':body_operation_order.record()}),tuple(deepcopy(f.facts) for f in fields))


def prepare_export(prepared_people,face_fields,snapshot,people_state,source_frame,original_pixels,*,people_geometry_identity,byte_budget,extra_body_fields=(),operation_policies=None,body_operation_order=DEFAULT_BODY_ORDER):
    """Original RGB8/16, never enlarge a proxy correction or reuse proxy geometry."""
    source=E.source(source_frame);pixels=np.asarray(original_pixels)
    if pixels.dtype not in (np.uint8,np.uint16) or pixels.shape!=(source['height'],source['width'],3):raise ValueError('Shoulder final export requires original-resolution RGB8/16')
    if tuple(prepared_people.geometry.delta.shape[1:3])!=pixels.shape[:2]:raise ValueError('Face map must also be recomputed at original export resolution')
    bank=P.check_snapshot(snapshot,source,operation_policies=operation_policies,body_operation_order=body_operation_order)
    return prepare_common(prepared_people,face_fields,bank,people_state,source,people_geometry_identity=people_geometry_identity,byte_budget=byte_budget,extra_body_fields=extra_body_fields,operation_policies=operation_policies,body_operation_order=body_operation_order)


def validate_project_records(value):
    """Apply to active/undo/redo project trees before any live mutation."""
    if isinstance(value,dict):
        if '_body_pose_bank' in value:P.unpack(value['_body_pose_bank'])
        for child in value.values():validate_project_records(child)
    elif isinstance(value,(list,tuple)):
        for child in value:validate_project_records(child)
