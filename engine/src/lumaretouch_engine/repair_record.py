"""Versioned repair inputs shared by persistence, preview and full-size replay.

Records contain coverage and a recipe, never rendered pixels. Validation is a
separate preflight so constructing/owning a snapshot cannot mutate live state.
"""
from dataclasses import dataclass, field
import math

import numpy as np


DEFAULT_REPAIR = dict(smooth_iters=1, refine_iters=6, kappa=0.06, pad=32, grow=1.5)
REPAIR_KINDS = ("heal", "source_patch", "clone_stamp")


@dataclass
class RepairOp:
    op_id: int
    weight: np.ndarray
    params: dict = field(default_factory=lambda: dict(DEFAULT_REPAIR))
    # Last field deliberately preserves legacy RepairOp(id, weight, params).
    kind: str = "heal"

    @property
    def area_px(self) -> int:
        return int((self.weight > 0).sum())

    def nbytes(self) -> int:
        return int(self.weight.nbytes)


def check_repair_params(kind, params):
    """Return independently owned canonical parameters; never coerce bad kinds."""
    if type(kind) is not str or kind not in REPAIR_KINDS:
        raise ValueError(f"Unknown repair kind: {kind!r}")
    if type(params) is not dict:
        raise ValueError("Repair params must be an object")
    if kind == "clone_stamp":
        from .ops.clone_stamp import check_recipe
        return check_recipe(params)
    if kind == "source_patch":
        from .ops.source_patch import check_recipe
        return check_recipe(params)
    if set(params) - set(DEFAULT_REPAIR):
        raise ValueError("Unsupported heal parameters")
    clean = {}
    for key, low, high, integral in (
            ("smooth_iters", 0, 4, True), ("refine_iters", 0, 32, True),
            ("kappa", 1e-3, 1.0, False), ("pad", 0, 256, True),
            ("grow", 1.0, 8.0, False)):
        if key not in params:
            continue
        value = params[key]
        if (type(value) not in (int, float) or not low <= value <= high
                or not math.isfinite(value) or (integral and int(value) != value)):
            raise ValueError(f"Invalid heal parameter {key}: {value!r}")
        clean[key] = int(value) if integral else float(value)
    return clean


def check_repair_fields(fields, *, shape=None, allow_legacy=True):
    """Validate decoded fields, allowing only the historical missing kind."""
    required = {"op_id", "weight", "params"}
    if type(fields) is not dict or set(fields) - (required | {"kind"}) or not required <= set(fields):
        raise ValueError("Invalid RepairOp fields")
    if "kind" not in fields and not allow_legacy:
        raise ValueError("RepairOp kind is required")
    op_id, weight = fields["op_id"], fields["weight"]
    if type(op_id) is not int or op_id < 0:
        raise ValueError("RepairOp op_id must be a nonnegative integer")
    if type(weight) is not np.ndarray or weight.dtype != np.uint8 or weight.ndim != 2 or min(weight.shape) < 1:
        raise ValueError("Repair coverage must be nonempty (H,W) uint8")
    if shape is not None and weight.shape != tuple(shape):
        raise ValueError(f"Repair coverage 掩膜尺寸 {weight.shape} != expected {tuple(shape)}")
    kind = fields.get("kind", "heal")
    return {"op_id": op_id, "weight": weight, "kind": kind,
            "params": check_repair_params(kind, fields["params"])}


def validate_repair_ops(ops, *, shape=None):
    """Preflight a whole active/redo stack without changing records or pixels."""
    if not isinstance(ops, (list, tuple)):
        raise ValueError("Repair operations must be a list")
    if shape is not None and (not isinstance(shape, (list, tuple)) or len(shape) != 2
            or any(type(n) is not int or n < 1 for n in shape)):
        raise ValueError("Repair dimensions must be positive (H,W) integers")
    for op in ops:
        if type(op) is not RepairOp:
            raise ValueError(f"Repair operation must be RepairOp, got {type(op).__name__}")
        check_repair_fields(vars(op), shape=shape, allow_legacy=False)
    return ops
