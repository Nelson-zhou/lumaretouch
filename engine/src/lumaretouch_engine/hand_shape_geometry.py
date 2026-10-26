# SPDX-License-Identifier: GPL-3.0-or-later
"""Join standalone hand fields before the ONE established source sampler."""
from dataclasses import replace
from . import hand_shape_state as S
from .hand_shape_field import prepare


def attach(prepared,recipe,source,people_state,*,byte_budget):
    recipe=S.check(recipe)
    if not S.active(recipe):return prepared
    fields=prepare(recipe,source,tuple(prepared.geometry.delta.shape[1:3]),people_state=people_state,byte_budget=byte_budget)
    from .shoulder_shape_runtime import compose
    from .body_pose_geometry import DEFAULT_BODY_ORDER,FrozenBodyOrder
    order=DEFAULT_BODY_ORDER if prepared.body_operation_order is None else FrozenBodyOrder(prepared.body_operation_order['version'],tuple(prepared.body_operation_order['operation_ids']))
    old=prepared.geometry.delta.nbytes+prepared.geometry.owner.nbytes
    geometry=compose(prepared.face_fields,prepared.body_fields,tuple(prepared.geometry.delta.shape[1:3]),byte_budget=byte_budget-old,body_operation_order=order,document_fields=fields)
    # This replaces a map only. No image, mask, recovery layer or pixels are sampled here.
    return replace(prepared,geometry=geometry,document_fields=fields)
