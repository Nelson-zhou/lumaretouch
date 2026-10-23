# SPDX-License-Identifier: GPL-3.0-or-later
"""Registered common-map arm consumer; never a second image warp.

Shared integration supplies other active family policies/fields and a unified
frozen order. No inactive leg/hair semantic module is imported here.
"""
import numpy as np
from . import arm_shape_state as S, arm_shape_runtime as R, arm_shape_project as P
from . import shoulder_shape_adapter as Common, body_pose_evidence as E


def prepare_common(prepared_people,face_fields,bank,people_state,source,*,people_geometry_identity,
                   byte_budget,source_pixels=None,band_pixels=65536,extra_body_fields=(),
                   operation_policies=None,body_operation_order=None):
    policies={**(operation_policies or {}),**S.policies()};source=E.source(source)
    bank=P.check(bank,operation_policies=policies)
    body_operation_order=P.effective_order(bank) if body_operation_order is None else body_operation_order
    shape=tuple(prepared_people.geometry.delta.shape[1:3])
    fields=R.prepare_fields(bank,source['sha256'],shape,people_state=people_state,byte_budget=byte_budget,
                            operation_policies=policies,source_pixels=source_pixels,source_frame=source)
    return Common.prepare_common(prepared_people,face_fields,bank,people_state,source,
        people_geometry_identity=people_geometry_identity,byte_budget=byte_budget,band_pixels=band_pixels,
        extra_body_fields=tuple(extra_body_fields)+fields,operation_policies=policies,body_operation_order=body_operation_order)


def prepare_export(prepared_people,face_fields,snapshot,people_state,source_frame,original_pixels,*,
                   people_geometry_identity,byte_budget,extra_body_fields=(),operation_policies=None,
                   body_operation_order=None):
    source=E.source(source_frame);pixels=np.asarray(original_pixels)
    if pixels.dtype not in (np.uint8,np.uint16) or pixels.shape!=(source['height'],source['width'],3):raise ValueError('Arm export requires original-resolution RGB8/16')
    if tuple(prepared_people.geometry.delta.shape[1:3])!=pixels.shape[:2]:raise ValueError('Rebuild all actual face/body fields at final source resolution')
    bank=P.check_snapshot(snapshot,source,body_operation_order=body_operation_order)
    return prepare_common(prepared_people,face_fields,bank,people_state,source,
        people_geometry_identity=people_geometry_identity,byte_budget=byte_budget,source_pixels=pixels,
        extra_body_fields=extra_body_fields,operation_policies=operation_policies,body_operation_order=body_operation_order)


def validate_project_records(value):
    if isinstance(value,dict):
        if '_body_pose_bank' in value:P.unpack(value['_body_pose_bank'])
        for child in value.values():validate_project_records(child)
    elif isinstance(value,(list,tuple)):
        for child in value:validate_project_records(child)


def publication_receipt(prepared,rendered_pixels,*,request_id,published_frame_id,render_revision,sampling_passes):
    from hashlib import sha256
    E.token(request_id);E.token(published_frame_id);E.revision(render_revision)
    if not isinstance(prepared,Common.PreparedShoulders):raise ValueError('Actual prepared common-map consumer required')
    pixels=np.asarray(rendered_pixels);geometry=prepared.geometry
    if pixels.ndim!=3 or pixels.shape[2]!=3 or pixels.shape[:2]!=geometry.delta.shape[1:3] or pixels.dtype not in (np.uint8,np.uint16,np.float32) or not np.isfinite(pixels).all():raise ValueError('Receipt needs the actually published RGB bytes')
    if type(sampling_passes) is not int or sampling_passes!=1:raise ValueError('Exactly one shared source RGB sampling pass is required')
    return {'version':1,'request_id':request_id,'published_frame_id':published_frame_id,'render_revision':render_revision,
            'source_sha256':prepared.source['sha256'],'prepared_identity_sha256':prepared.identity_sha256,
            'output_pixel_sha256':sha256(memoryview(np.ascontiguousarray(pixels))).hexdigest(),
            'geometry_delta_sha256':sha256(memoryview(np.ascontiguousarray(geometry.delta))).hexdigest(),
            'output_dtype':str(pixels.dtype),'render_dimensions':[pixels.shape[1],pixels.shape[0]],
            'source_dimensions':[prepared.source['width'],prepared.source['height']],
            'body_operation_order':geometry.body_operation_order,'single_source_sample':True,'runtime_quality_accepted':False}
