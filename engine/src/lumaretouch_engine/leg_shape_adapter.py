# SPDX-License-Identifier: GPL-3.0-or-later
"""Installed actual shoulder+leg consumer: one BodyRef chain, one image sample.

No alternate body bank, sampled displacement addition or module-local RGB warp.
The canonical body render owner calls this adapter without changing the existing
face/effect/recovery inputs. Neutral legs preserve the original shoulder-only order.
"""
import numpy as np
from . import body_pose_evidence as E, leg_shape_state as S
from . import leg_shape_runtime as R, leg_shape_project as P
from . import shoulder_shape_adapter as Common


def prepare_common(prepared_people,face_fields,bank,people_state,source,*,people_geometry_identity,byte_budget,band_pixels=65536):
    source=E.source(source);bank=P.check(bank)
    shape=tuple(prepared_people.geometry.delta.shape[1:3])
    legs=R.prepare_fields(bank,source['sha256'],shape,people_state=people_state,
                          byte_budget=byte_budget,operation_policies=S.policies())
    # Common verifies each actual field's exact recipe/review/source binding,
    # groups same-BodyRef operations, checks ownership/budgets/Jacobians, then
    # replaces prepared_people.geometry. It does not resample RGB at this step.
    return Common.prepare_common(prepared_people,face_fields,bank,people_state,source,
                                 people_geometry_identity=people_geometry_identity,
                                 byte_budget=byte_budget,band_pixels=band_pixels,
                                 extra_body_fields=legs,operation_policies=S.policies(),
                                 body_operation_order=P.effective_order(bank))


def prepare_export(prepared_people,face_fields,snapshot,people_state,source_frame,original_pixels,*,people_geometry_identity,byte_budget):
    source=E.source(source_frame);pixels=np.asarray(original_pixels)
    if pixels.dtype not in (np.uint8,np.uint16) or pixels.shape!=(source['height'],source['width'],3):
        raise ValueError('Leg export needs original-resolution RGB8/16, not an enlarged proxy')
    bank=P.check_snapshot(snapshot,source)
    if tuple(prepared_people.geometry.delta.shape[1:3])!=pixels.shape[:2]:
        raise ValueError('Face and body evaluators must both be rebuilt at original export resolution')
    return prepare_common(prepared_people,face_fields,bank,people_state,source,
                          people_geometry_identity=people_geometry_identity,byte_budget=byte_budget)


def validate_project_records(value):
    """Validate active and every undo/redo/export tree before any live mutation."""
    if isinstance(value,dict):
        if '_body_pose_bank' in value:P.unpack(value['_body_pose_bank'])
        for child in value.values():validate_project_records(child)
    elif isinstance(value,(list,tuple)):
        for child in value:validate_project_records(child)
