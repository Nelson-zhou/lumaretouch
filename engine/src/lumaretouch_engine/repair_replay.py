"""One ordered repair replay for proxy previews and full-resolution exports."""
import numpy as np

from .optional_dependencies import optional_module
from .repair_record import DEFAULT_REPAIR, validate_repair_ops
from .ops.inpaint import crop_apply_t, hole_extent, inpaint_t, levels_for, mask_bbox

torch = optional_module("torch")


def replay_repair_t(cur, ops):
    """Read each operation's source from the preceding float32 BCHW result.

    Never write into the caller's input, including when a later operation fails.
    The caller owns the atomic state/cache commit after this function succeeds.
    """
    validate_repair_ops(ops, shape=tuple(cur.shape[-2:]))
    boxes = []
    painted = 0
    for op in ops:
        painted += op.area_px
        if op.kind == "heal_vector":
            from .ops.heal_vector import apply_t
            cur, box = apply_t(cur, op.params)
            if box is not None:
                boxes.append([int(v) for v in box])
            continue
        if op.kind == "clone_stamp":
            from .ops.clone_stamp import apply_t
            cur, box = apply_t(cur, op.params)
            if box is not None:
                boxes.append([int(v) for v in box])
            continue
        if op.kind == "source_patch":
            from .ops.source_patch import apply_t
            cur, box = apply_t(cur, op.params)
            if box is not None:
                boxes.append([int(v) for v in box])
            continue
        # Validation above permits exactly the declared heal/source-patch/clone/vector families. Keep the original
        # heal arithmetic and defaults, including its float32 coverage division.
        if op.kind != "heal":
            raise ValueError(f"Unknown repair kind: {op.kind!r}")
        p = op.params
        wsub_np = op.weight.astype(np.float32) / 255.0
        box = mask_bbox(wsub_np, pad=int(p.get("pad", DEFAULT_REPAIR["pad"])),
                        grow=float(p.get("grow", DEFAULT_REPAIR["grow"])))
        if box is None:
            continue
        y0, y1, x0, x1 = box
        lv = levels_for(hole_extent(wsub_np), y1 - y0, x1 - x0)
        sub = cur[..., y0:y1, x0:x1]
        wsub = torch.from_numpy(np.ascontiguousarray(wsub_np[None, None, y0:y1, x0:x1])).to(cur.device)
        fill = inpaint_t(sub, wsub, levels=lv,
                         smooth_iters=int(p.get("smooth_iters", DEFAULT_REPAIR["smooth_iters"])),
                         refine_iters=int(p.get("refine_iters", DEFAULT_REPAIR["refine_iters"])),
                         kappa=float(p.get("kappa", DEFAULT_REPAIR["kappa"])))
        cur = crop_apply_t(cur, box, fill)
        boxes.append([int(v) for v in box])
    return cur, boxes, painted
