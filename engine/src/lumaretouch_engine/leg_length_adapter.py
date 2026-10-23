# SPDX-License-Identifier: GPL-3.0-or-later
"""Length consumer port. Host supplies ALL other body fields, sampled only once."""
import numpy as np
from . import leg_length_state as S,leg_length_project as P,leg_length_runtime as R
from . import body_pose_evidence as E,shoulder_shape_adapter as Common

def prepare_common(prepared_people,face_fields,bank,people_state,source,*,people_geometry_identity,byte_budget,band_pixels=65536,extra_body_fields=()):
    source=E.source(source);bank=P.check(bank)
    shape=tuple(prepared_people.geometry.delta.shape[1:3])
    fields=R.prepare_fields(bank,source['sha256'],shape,people_state=people_state,byte_budget=byte_budget)
    # Common.require_prepared refuses omitted active arm/waist/width fields.
    return Common.prepare_common(prepared_people,face_fields,bank,people_state,source,people_geometry_identity=people_geometry_identity,
        byte_budget=byte_budget,band_pixels=band_pixels,extra_body_fields=tuple(extra_body_fields)+fields,
        operation_policies=S.policies(),body_operation_order=P.effective_order(bank))

def prepare_export(prepared_people,face_fields,snapshot,people_state,source_frame,original_pixels,*,people_geometry_identity,byte_budget,extra_body_fields=()):
    source=E.source(source_frame);pixels=np.asarray(original_pixels)
    if pixels.dtype not in (np.uint8,np.uint16,np.float32) or pixels.shape!=(source['height'],source['width'],3) or not np.isfinite(pixels).all():raise ValueError('Length export requires finite original-resolution RGB8/RGB16/HDR, not an enlarged proxy')
    if tuple(prepared_people.geometry.delta.shape[1:3])!=pixels.shape[:2]:raise ValueError('Rebuild every face/body field at original source resolution')
    bank=P.check_snapshot(snapshot,source)
    return prepare_common(prepared_people,face_fields,bank,people_state,source,people_geometry_identity=people_geometry_identity,byte_budget=byte_budget,extra_body_fields=extra_body_fields)

def validate_project_records(value):
    if isinstance(value,dict):
        if '_body_pose_bank' in value:P.unpack(value['_body_pose_bank'])
        for child in value.values():validate_project_records(child)
    elif isinstance(value,(list,tuple)):
        for child in value:validate_project_records(child)
