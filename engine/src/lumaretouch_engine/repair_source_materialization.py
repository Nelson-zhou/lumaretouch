# SPDX-License-Identifier: GPL-3.0-or-later
"""Existing repair-vector materialization shared with full-source measurements.

No new mask algorithm, source owner, replay order or numerical policy. Runtime
and parity acceptance for this extraction are UNRUN.
"""
from copy import deepcopy


def materialize(operations, shape):
    from .repair_record import check_repair_params, validate_repair_ops
    from .export import resample_field
    from .vram import RepairOp
    validate_repair_ops(operations)
    h, w = shape
    if type(h) is not int or type(w) is not int or min(h, w) < 1:
        raise ValueError('Repair materialization requires exact canonical dimensions')
    return [RepairOp(op_id=op.op_id,
                     weight=resample_field(op.weight, (h, w), uint8=True),
                     kind=op.kind, params=check_repair_params(op.kind, op.params),
                     source_binding=deepcopy(op.source_binding)) for op in operations]
