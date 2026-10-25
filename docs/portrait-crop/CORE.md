# Portrait crop scalar planner, ABI 1

Status: **AUTHORED / UNRUN**. This is original GPL-3.0-or-later source, not copied
upstream implementation. No native build/load, product import, test, inference,
image rendering, photographic acceptance or runtime timing was performed while
authoring this slice. AST parsing and source/hash inspection are not execution
acceptance. The existing crop sampler is unchanged.

## Module ownership

- `core/portrait_crop/`: dependency-free Rust geometry, C ABI and UNRUN fixtures.
- `portrait_crop_state.py`: strict copied scalar records and local convention.
- `portrait_crop_native.py`: explicit version/capability admission and FFI.
- `portrait_crop_planner.py`: production native planning and separate Python
  reference oracle; no automatic fallback.
- Host capture/review/project/controller modules own pixels, selected face,
  source/edit/repair/geometry identity, genuine user review, cancellation,
  transaction/history, persistence and export. These are not inferred from a
  caller's scalar dictionaries, hashes or boolean flags by this planner.

No new sampling, crop operation identifier, landmark model, crown estimator,
rule preset, image generator, resizer, filler or padding operator is introduced.
The existing operation remains `lnx.crop.v1`, rotation zero. Any nonzero existing
rotation requires an explicit host refusal, not silently resetting that edit.

## Coordinates and constraints

Convention identifier: `lrt.portrait-crop.source-edge-pixels.v1`.

Inputs address the **uncropped current edited full source grid**. X increases
rightward and Y downward. Extent is `[0,width] × [0,height]`; integer coordinates
are pixel-cell edges. The outer extent is a geometric boundary, not a claim that
a sampled pixel centre exists at `width` or `height`. Host display mappings must
preserve this convention. Original proxy points cannot be reused after warps
without a verified mapping or fresh analysis of the current composite.

The host supplies genuinely reviewed crown, chin and face-center observations.
There is no landmark-10, bounding-box or forehead extrapolation. Chin must be
strictly below crown; face-center Y lies between them. Every anchor must lie in
the source and in both the ideal and rounded crop. This does not prove that the
entire hair outline, ears or shoulders fit; photographic review remains needed.

All three anchors are required. No arbitrary Euclidean head length, eye line,
skull estimate or inferred face-center definition replaces the reviewed values.
The height is specifically vertical crown-to-chin separation, not length along
a tilted head axis. This convention is local, not an undisclosed vendor claim.

## Public Python contract

`portrait_crop_planner.plan(width, height, anchors, rules)` returns a fresh
JSON-serializable plan or raises. Dimensions are exact Python integers in
`1..2**31-1`, excluding booleans; this scalar bound is not a memory admission.
Host image-memory limits remain independently authoritative.

Anchors have exactly these keys:

```json
{"version": 1, "crown": [500, 100], "chin": [500, 700], "face_center": [500, 400]}
```

Rules have exactly these keys:

```json
{"version": 1, "aspect_ratio": 1.0, "headroom_fraction": 0.1,
 "head_fraction": 0.6, "horizontal_position": 0.5}
```

These values are an illustrative full-frame numerical fixture for a 1000×1000
source, **not defaults**. Fractions are not percentages. Aspect is positive
finite width/height; head fraction is `(0,1]`; headroom and horizontal position
are `[0,1]`. Headroom plus head fraction must not exceed one. Unknown fields,
nonfinite values, booleans, strings and wrong versions are refused.

For crown Y `cy`, chin Y `jy`, face center `fx,fy`, head fraction `f`, headroom
`m`, horizontal position `p` and aspect `a`, the independent authored equations
are:

```text
head_height = jy - cy
H = head_height / f
W = a * H
top = cy - m * H
left = fx - p * W
right = left + W
bottom = top + H
implied_vertical_position = (fy - top) / H
```

There is no separately adjustable vertical-position target: headroom and head
fraction already determine top and height. The source itself is not moved or
resized to satisfy the requested frame. Out-of-image or nonfinite intermediate
geometry is rejected without epsilon clamping, subject movement or invented
pixels. Rounding can also make a request infeasible, including a fractional
crown with zero headroom that would be trimmed by a rounded top edge.

### Returned plan

The exact top-level keys are:

```text
version: 1
convention: lrt.portrait-crop.source-edge-pixels.v1
operation_id: lnx.crop.v1
rotation_degrees: 0.0
source_size: [width, height]
anchors: validated copied input
rules: validated copied input
continuous_rect_pixels: [left, top, right, bottom], ideal requested bounds
rect_normalized: [left/Wsource, top/Hsource, right/Wsource, bottom/Hsource],
                 calculated from ACTUAL INTEGER edges
pixel_bounds: [left, top, right, bottom], actual integers
output_size: [right-left, bottom-top], actual integers
requested: aspect_ratio, headroom_fraction, head_fraction,
           horizontal_position, vertical_position
achieved: the same five metrics, plus head_height_pixels
is_full_frame: actual pixel_bounds equal the complete source extent
backend: rust-portrait-crop-v1
```

Requested metrics echo the rules plus the **implied** vertical position.
Achieved metrics use rounded pixel width/height and origins; they must be shown
separately because pixel rounding can alter the aspect and other proportions.
No rounding error is hidden by returning requested numbers as measured numbers.

`reference_plan(...)` has the same result schema but backend
`python-reference-unrun`. It is an explicitly selected analytical fixture oracle,
not a production fallback or evidence that the native library works. Production
`plan()` also calculates this oracle to reject native geometry disagreements;
absence, ABI failure or mismatch never publishes the reference answer instead.

### Capability and errors

`capability()` returns exactly `version`, `backend`, `available`, `abi`,
`capabilities`, `reason`. Admitted results use version/ABI 1, capabilities 15,
reason null; unavailable results use ABI null, capabilities 0 and a reason.
It loads only `bin/liblrt_portrait_crop.so` beside the engine modules, never
builds, installs or downloads. Importing the Python modules does not load it.
Available means presence plus ABI contract, not numerical/photographic approval.

`PortraitCropError(ValueError)` supplies `.code`: `invalid_geometry`,
`infeasible` or `pixel_rounding`. Native absence, ABI failure, unexpected status
or numerical disagreement raises `RuntimeError`. A caller must not catch these
and apply a different centred crop, old plan or silently clamped rectangle.

## Unchanged sampler and pixel rounding

`engine/src/lumaretouch_engine/ops/geometry.py::_cut` normalizes dimensions by
individual edges and uses Python `round`, which is ties-to-even. A raw `round`
in Rust rounds halfway away from zero, so the new core explicitly implements
ties-to-even. It uses the **same order**: divide each continuous edge by its
axis dimension, multiply by that dimension, then round. It does not use
`round(n*(right-left))`, independent width rounding, floor or JS `Math.round`.

Unlike `_cut`, the planner does not rely on boundary clamps or a forced minimum
one-pixel crop. It rejects collapsed windows and rounded-out anchors. It then
normalizes the actual integer edges. At admitted int32 dimensions the floating
round-trip error of an integer edge is far below half a pixel, so the existing
sampler recovers the same window. Host still independently checks `_cut` and
`out_size` on the final candidate and renders actual before/after imagery.

For a complete source, the emitted rectangle is exactly `[0,0,1,1]`. This keeps
the existing byte/object-identity neutral path, rather than fabricating an
image or bypassing the existing sampler.

Source-inspection hash of the unchanged sampler on 2026-10-25:
`d8926644d923b5589eb112ac1ec3bb3a96c908789c9f53968aaecb8f618b4985`.

## Native ABI

The authoritative declarations are `core/portrait_crop/portrait_crop.h`.
Exports: `lrt_portrait_crop_abi`, `lrt_portrait_crop_capabilities`,
`lrt_portrait_crop_result_len`, `lrt_portrait_crop_plan_v1`.

- ABI is 1. Capabilities are reviewed-anchor input (1), no padding (2),
  ties-even edges (4), achieved metrics (8). Reviewed-anchor input capability
  does not authenticate or auto-review the caller's observations.
- Width/height are uint32, restricted to positive int32.
- Input arrays are 6 doubles (crown x/y, chin x/y, face center x/y) and 4 doubles
  (aspect, headroom fraction, head fraction, horizontal position).
- Output is exactly 20 doubles: ideal bounds 0–3; normalized snapped bounds
  4–7; integer pixel bounds 8–11; achieved aspect/headroom/head fraction/
  horizontal/vertical 12–16; head height 17; output width/height 18–19.
- Status: 0 success, 1 ABI/span error, 2 invalid geometry, 3 infeasible,
  4 pixel rounding failure, 5 contained panic.
- Valid aligned live memory is the caller's obligation. Exact lengths and
  integer span overflow are checked. Output must not overlap input; the two
  read-only inputs may alias. Errors preserve every output byte. All values
  are staged on stack before the final copy; no image allocation exists.
- Panic containment requires unwind; compiling with `panic=abort` removes it.
  No fast-math or alternate precision contract is admitted.

`build_portrait_crop.sh` is an authored, **unexecuted** explicit offline build
and local installation entry point, consistent with the existing plugin layout.
Packaging integration is owned outside this isolated slice.

## Authored acceptance fixtures, all UNRUN

- Rust: full-frame neutral, portrait/landscape/singleton boundaries, both
  half-pixel parities, achieved-aspect divergence, no forced one-pixel crop,
  no crown trimming, NaN/Inf/range/orientation rejection, overflow/infeasibility,
  output transactionality, null/span/alias refusal and a composition grid.
- Python state: strict versions/keys, copied records, type/finite/range checks,
  anchor domains and refusal of fictitious extra vertical constraints.
- Python planner: same scalar cases, real coordinate-ramp assertions against
  existing sampler, neutral object identity, source-aware horizontal position,
  no native fallback and disagreement rejection.
- Python native: admission errors, real installed-library parity and unchanged
  output on error. Missing-library skips are explicitly not acceptance.

The remaining release gates include actual compilation, numerical fixtures,
Python/native ABI parity, native packaging, real-current-composite inference,
real before/after review, cancel/stale/undo/reopen/export verification and user
acceptance. Static source review cannot discharge any of those gates.
