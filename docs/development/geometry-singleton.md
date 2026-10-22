# One-pixel crop axes under arbitrary rotation

Status: candidate, awaiting exact-commit CI. No local execution performed.

A legal normalized crop can round to one source pixel in either dimension. The
legacy four-neighbour validity test then had no valid interval (`x0 < width-1`
or its vertical equivalent), making every arbitrary-angle output pixel black.
This is a statically established validity defect, not evidence of a runtime crash.

The narrowly scoped fix treats a singleton axis as one constant pixel cell over
[-0.5,0.5], inclusive. Outside that cell remains zero fill. In these degenerate images only, both axes use the half-pixel cell footprint
with edge-clamped interpolation inside it. Double-precision inverse coordinates
keep NumPy/Torch boundary membership aligned, including60°; Torch returns the
original floating dtype. Images with both dimensions
at least2 retain exactly the previous arithmetic and boundary pixels. Quarter-turn
snapping, crop rounding, output dimensions and normal preview resizing are unchanged.

This is an explicit compatibility choice, not a claim of equivalence to general
zero-padded bilinear sampling, whose edges may fade. The pixel-cell convention is
consistent with the documented square-pixel/align_corners=False convention in
https://docs.pytorch.org/docs/2.14/generated/torch.nn.functional.interpolate.html .
No upstream implementation was copied, and the runtime remains the pinned CI
CPU Torch2.10.0 rather than the documentation site's newer version.

The candidate adds85 tests: an independent scalar rotation oracle, NumPy/Torch
comparisons, exact and just-outside half-pixel boundaries, a real uint8 one-pixel
crop, frozen normal-size legacy sampling, and source-coverage projection. CI runs
these plus the existing geometry suite with installed CPU Torch and rejects skips.
Coverage for future action pickers must use this identical geometry path rather
than guessing coverage from whether RGB happens to be black.
