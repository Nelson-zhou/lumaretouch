# SPDX-License-Identifier: GPL-3.0-or-later
"""Waist-length consumer of the sole body chain, sampler and export snapshot.

Derived sizes are produced downstream from the same full-source preparation;
there is no waist-only image resize/warp or reuse of a preview field at export.
"""
import numpy as np
from . import waist_length_state as S, waist_length_project as P, waist_length_runtime as R
from . import body_pose_evidence as E, shoulder_shape_adapter as Common


def prepare_common(prepared_people, face_fields, bank, people_state, source, *,
                   people_geometry_identity, byte_budget, band_pixels=65536, extra_body_fields=()):
    source = E.source(source)
    bank = P.check(bank)
    shape = tuple(prepared_people.geometry.delta.shape[1:3])
    fields = R.prepare_fields(bank, source['sha256'], shape, people_state=people_state,
                              byte_budget=byte_budget, source_frame=source)
    # Common.require_prepared refuses missing OR stale active family fields;
    # this module cannot publish a partial shoulder/neck/leg/arm/torso/waist chain.
    return Common.prepare_common(
        prepared_people, face_fields, bank, people_state, source,
        people_geometry_identity=people_geometry_identity, byte_budget=byte_budget,
        band_pixels=band_pixels, extra_body_fields=tuple(extra_body_fields)+fields,
        operation_policies=S.policies(), body_operation_order=P.effective_order(bank))


def prepare_export(prepared_people, face_fields, snapshot, people_state, source_frame,
                   original_pixels, *, people_geometry_identity, byte_budget, extra_body_fields=()):
    source = E.source(source_frame)
    pixels = np.asarray(original_pixels)
    if (pixels.dtype not in (np.uint8, np.uint16, np.float32)
            or pixels.shape != (source['height'], source['width'], 3)
            or not np.isfinite(pixels).all()):
        raise ValueError('Waist length export needs finite original-resolution RGB8/RGB16/float32 RGB, never an enlarged proxy')
    if tuple(prepared_people.geometry.delta.shape[1:3]) != pixels.shape[:2]:
        raise ValueError('Rebuild every face/body field at original source resolution for waist export')
    bank = P.check_snapshot(snapshot, source)
    return prepare_common(prepared_people, face_fields, bank, people_state, source,
        people_geometry_identity=people_geometry_identity, byte_budget=byte_budget,
        extra_body_fields=extra_body_fields)


def validate_project_records(value):
    if isinstance(value, dict):
        if '_body_pose_bank' in value:
            P.unpack(value['_body_pose_bank'])
        for child in value.values():
            validate_project_records(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            validate_project_records(child)
