# Neck fine-line ownership and current-stage adapters

Status: AUTHORED / UNRUN. This slice does not establish runtime, numerical,
representative-photo, performance or vendor-parity acceptance. Requirement is
exactly `control:PC-32464:19`. Existing facial wrinkle, under-eye, collarbone and
neck-shape numerical implementations are not modified by these files.

## Portable intent and nonportable ownership

`neck_wrinkle_state` owns `lnx.neck_wrinkle.v1` with exact recipe
`{version: 1, amount: 0..1}`. Unknown fields, booleans, nonfinite values and
out-of-range amounts refuse. Default zero returns before support/source/native
resolution and before effect allocation. `portable` strips nothing silently: it
accepts only the exact amount recipe. It is not cross-image authorization.

Support uses the EXISTING `people_support_assets` bank and existing face-local
pointer `{owner: FaceRef, content_sha256, kind: 'neck_wrinkle_visibility'}`.
The descriptor remains immutable and operation-specific. No new support, undo,
project, body-pose-operation or association owner is created. The shared owner
must explicitly register family `neck_wrinkle`; accepting arbitrary family names
or aliasing collarbone/neck-shape/face-wrinkle review is forbidden.

Exact review schema:

```json
{
  "body_ref": "existing exact BodyRef object, not a string",
  "points_sha256": "current measured pose digest",
  "recipe": "existing source-normalized manual add/subtract brush stack",
  "visible": true,
  "unoccluded": true,
  "ownership_confirmed": true,
  "neck": {
    "version": 1,
    "domain": "source-normalized",
    "line_half_width": "positive number: observed half-width / canonical short side",
    "protect_recipe": "independent source-normalized protection brush stack",
    "protections_reviewed": true,
    "visible_neck_skin_reviewed": true
  }
}
```

The explanatory strings above describe existing object shapes, not accepted
runtime strings. Main paint must contain an enabled positive add brush and may
use add/subtract brushes. It describes actual visible neck skin AND admissible
nearby sampling context. `neck_wrinkle_support.check_review` validates the whole
review; `check_neck_review` validates only the `neck` extension.

Protection paint is strictly enabled, opaque, unfeathered ADD brushes. Delete a
stroke to revise it; subtract, opacity decrease, feather and disabled protection
strokes are not accepted. Empty protection requires explicit reviewed-none
acknowledgment, not an inferred absence of occluders. Independently protect
jewelry, collars/clothes, hair/beard, tattoos/marks, hands, other people, Adam's
apple/tendon edges and structural jaw/collarbone shadows or unwanted lines.
A positive neck/context stroke cannot undo this separate hard veto.

Observed line half-width is 1.4..12 ACTUAL canonical pixels. This local policy is
unvalidated engineering, not a vendor slider scale. It is never derived from eye,
face, chin, shoulder or pose dimensions and is never clamped to fit a proxy.
No age/gender restriction is inferred or copied from collarbone.

The canonical owner validates actual FaceRef evidence, BodyRef/pose record,
exact explicitly confirmed same-person links, both association revisions,
source dimensions, and the measured `body_skin` observation. Face boxes only
veto pixels. All other retained owners, even disabled ones, reserve their
reviewed body regions; positive overlap refuses instead of using sorted-owner
priority. Neither face/pose boxes nor nearest-chin assignment creates support.

## Masks, sampling and diagnostics

`raster_plan` checks canonical extent, whole competing-review work and memory
BEFORE raster allocation. `raster` delegates to the existing body support owner
and Rust manual rasterizer, then applies independent protection and any nonzero
known-occluder weight as hard vetoes. `body_skin` is mandatory, not merged `skin`.
Missing known-occluder data refuses. The result is:

- `admitted_weight`: readonly full-source float32 HW skin/context permission.
- `hard_protect`: readonly full-source bool HW manual/known-occluder veto.
- JSON-safe ownership, source, semantic-observation and actual-plane hash facts.

Zero admission alone already prohibits sampling. Unpainted/background areas
are not mislabeled as manually protected merely because they have zero weight.
Every retained face is conservatively excluded by the canonical owner.

Positive paint is NOT the final numerical support. The numerical core independently
requires the complete composed dependency footprint to be inside positive owned
skin, outside all protections and inside the source. Its readonly `eligible_mask`
is separate from line detection and changed proposals. `prepare_review` returns
`(effects, NeckReviewEvidence)` containing full-grid admitted/hard planes and the
exact ROI eligibility/window. This disposable evidence is never persisted in a
support asset or recipe. Review uses cyan for numerical eligibility, magenta for
hard protection, and orange for positive support rejected by context.

The review host may release these diagnostics before mixed full rendering and
repeat deterministic measurement, but must compare source/repair/support identities
AND actual rendered `{face_ref, measurement_key}`. A brush image, an eligibility
checkbox or a source pathname is not an exact presented comparison receipt.

## Canonical source and admission interface

`neck_wrinkle_layer.prepare(ref, analysis, recipe, *, people_state, body_assets,
body_bank, full_source, byte_budget, cancelled=None)` accepts only the parent-owned
`neck_wrinkle_source.resolve` route. That resolver validates its exact internal
class and supplies:

- readonly canonical/repaired encoded-working-sRGB float32 HWC `rgb`;
- exact canonical-grid `analysis` with original measured-observation provenance;
- JSON-safe `proof` binding actual source pixels, extent, orientation, format,
  pixel digest and repair identity;
- `resident_bytes` including source/repair/analysis allocations.

No plain array plus hash, arbitrary callback, UI verification boolean, original
path relabeled as a creative asset or ordinary inference/display proxy is source
authority. Original and returned creative sources stay distinct. Semantic
resampling is not claimed as new full-resolution inference.

`layer.plan` is allocation-free aggregate admission. It conservatively plans
native full-source measurement rather than a face crop, adds raster scratch,
and exposes native retained bytes. Native `required_work_bytes` is a TOTAL that
already counts its RGB/weight/protect inputs (17 bytes/source pixel); the layer
subtracts that overlap before adding the resolver's residents and raster budget.
Parent additionally reserves every concurrent neck, other operator and current
render buffer before resolving/allocating. Native measurement receives its exact
bounded plan allowance, never an arbitrary remainder above its 4 GiB limit.
Budget refusal does not rescale, truncate people, alter line width or reuse stale
results. Cancellation is checked between stages; no partial field is published.

`measurement_key` excludes amount but includes the entire immutable support
record, exact actual body-skin/occluder/admitted/hard-plane digests, source/repair
proof and algorithm version. The support record already binds source dimensions,
FaceRef/evidence, BodyRef/record/pose digest, both association revisions, measured
semantic observation, region/protection vectors and observed scale. Amount-only
changes may reuse the field; any of these identities changing cannot.

## Current-stage composition and output tiles

`LocalEffect(stage='neck_wrinkle')` owns a readonly scalar positive `log_gain`
ROI, its integer source `(y,x,h,w)` and independently checked amount. There is no
RGB source delta, chroma replacement or geometry map. Valid no-line measurement
publishes honest zero field facts; inadequate context refuses separately.
`no_detected_wrinkle_lines` means no line evidence; `no_positive_wrinkle_lift`
means line-like evidence survived but conservative lift gates produced zero.
Supported, detected-line, positive-source-proposal and actual-rendered-change
counts are not interchangeable. Zero changed pixels never claim visible repair.

`apply_np/apply_t` consume CURRENT LINEAR RGB records. Existing people-pipeline
`apply_records_np/apply_records_t` consume CURRENT encoded-working-sRGB and use
the existing attributed transfer helpers around the same native linear apply.
Only positive-field current pixels with actual headroom and nonzero light are
gathered, in bounded strips. Only native-changed pixels are written back. Zero
field, zero amount, black, zero current headroom, outside-owner pixels and signed
zeros remain exact input bytes. Native common gain, not independent channel
clipping, chooses the output. No Python detector or gain fallback exists.

Every full-source record is validated and all owner overlaps are preflighted
BEFORE application, even outside the requested output tile. Each owned neck is
composed once. Source/repair identities cannot mix. Export crops exactly the
already solved field using the true expanded-tile origin, with no resizing,
per-tile solve or RGB8 intermediate. Current scalar gain preserves linear channel
ratios under that gain, not perceptual hue or pore-amplitude invariance across all
ordered edits. Composition remains before common geometry.

## History and integration fences

`neck_wrinkle_project` validates the exact amount leaf and only face-scoped
intent. It resolves historical support structurally through the existing owner,
not today's body association. Detach retains immutable historical bytes and is
reachable with stale evidence. Generic face recovery, shared cohorts, batch and
cross-image transfers are explicitly fenced in this first slice. Parent owns
shared registries, actual source decoder/repair replay, ordered rendering,
canonical receipt/history publication and native/UI transport.

The isolated fixtures `engine/tests/test_neck_wrinkle_support_unrun.py` cover
schema, independent consent, source scale, hard veto, canonical ownership, stale
evidence, proxy/budget refusal, neutral/no-signal behavior, immutable fields,
current-stage transport, exact tile origins, overlap and history fences. They
include deliberate synthetic and mocked boundaries and remain UNRUN. Static
source/AST inspection cannot replace decoder, native, visual, round-trip,
cancellation, aggregate-memory, RGB16 or real 100% portrait/export acceptance.
