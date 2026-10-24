# Eye symmetry: measured level and opening area over unchanged eye controls

**AUTHORED / UNRUN.** This is a source contract, not passed imports, tests,
collection, builds, typechecks, numerical experiments, photographic review,
performance measurements or product acceptance. Shared source has been read,
not executed. The new fixtures must not be interpreted as verification results.

## Scope, requirements and official semantics

The exact operation is `lnx.eye_symmetry.v1`. Its requirement identifiers are:

- Family: `LNX-REF-PC-32470-C-2745ac86f5`, 眼睛对称.
- Level: `LNX-REF-PC-32470-C-a86e5c0175`, 水平对称.
- Size: `LNX-REF-PC-32470-C-4601eb7797`, 大小对称.
- Reference: `LNX-REF-PC-32470-C-118aa67e04`, 参考眼选择.

The [official iPad guide](https://www.pixcakeai.com/guide/32513) and its
[official mirror](https://wiki.pixcakeai.com/guide/9810.html) describe separate
level and size correction, automatic use of the larger eye for size, and a
manual reference-side choice. The [official eye-retouching article](https://wiki.pixcakeai.com/portrait-retouching/15464.html)
clarifies high/low eye leveling, not changing eye spacing. These sources do
not specify an axis, size metric, midpoint versus fixed-eye leveling,
strength calibration, native gain, support envelope or proprietary algorithm.
The forehead/chin axis, midpoint targets, polygon-area size metric and every
bound below are original local policy, not a claim of proprietary equivalence.

Subject left/right use the existing factual MediaPipe topology, not screen
left/right. Each eye retains the established ordered 16-point lid ring and
5-point iris group. The reference selects a measurement, never copied pixels,
an external donor, a stored donor geometry or synthesized eye content.

This is not bilateral manual eye shape, iris size, eyelid height, spacing,
gaze, head pose or 3-D symmetry. Equal manual slider values are not measured
symmetry. No prior eye, brow, nose, mouth, face, philtrum or automatic operation
is reset, converted, replaced or implicitly switched off.

## Exact portable state and two different no-op cases

The sole state schema is

`{"version":1,"horizontal":0.0,"size":0.0,"reference":"auto"}`.

Only these exact four keys are allowed. Version is an exact Python integer 1.
Horizontal and size strengths are exact Python integers/floats, finite and in
[0,1]; booleans, NumPy scalars, subclasses, strings, extra keys and unknown
versions refuse. Reference is an exact string `auto`, `left` or `right`.
`check` returns a fresh dictionary with float strengths. `None` means the
default; `preset`, `check`, `neutral` and `active` do not load native code.

Only either nonzero numeric strength activates the operation. Zero/zero/left
and zero/zero/right remain neutral, though their size-reference intent is
preserved. They do not require new source analysis, geometry, native loading
or an appended field. The render planner exempts only this exact valid
reference enum from its analysis predicate; full state validation remains.
Reference-only changes do not move pixels. Canonical reset returns 0/0/auto.

By contrast, a **nonzero** request can validly yield a measured identity when
the selected source eyes are already exactly level and/or have equal measured
areas for the requested controls. This still requires actual retained source
evidence, both eyes, actual native availability and the normal identity/native
audits. It records requested/applied and already-symmetric facts, with no
fabricated motion. A field without a TPS state is then valid, not a missing
native result or an excuse to skip the request. Unequal measurements whose
correction disappears through rounding are not an already-symmetric result.

No landmark, area, head axis, resolved automatic reference, source identity,
FaceRef, mask, RGB, path, native result or cache belongs to portable state.
Transfers and presets must measure each target's own two eyes again.

## Independent source frame and actual measurements

The host requires the canonical retained 478x3 normalized observations, exact
retained landmark digest, verified MediaPipe analysis and a same-source known
occluder field. The canonical owner authenticates original/derived source
identity and exact enabled FaceRef. Decoded floating RGB is not asserted to
hash to an encoded-file SHA-256. Both actual eyes require source RGB evidence,
even for a manually selected size reference. Known occluders and regional
photometry can veto; they are not complete glasses, eye or visibility masks.

Durable evidence's source dimensions identify the genuine source, not necessarily
the current render grid. The existing snapshot path preserves that evidence and
normalized landmark bytes while resampling same-source semantic coverage to the
requested grid. Preview may use its admitted proxy grid; export rebuilds from
the retained normalized observations on the actual output source grid. The
current RGB and exclusion-mask shapes must match, but requiring durable evidence
width/height to equal the current RGB dimensions would incorrectly reject this
established contract. Positive valid durable dimensions, exact owner/FaceRef,
landmark digest and current-grid mask checks all remain mandatory. Source pixel
units below mean the current admitted grid's source coordinates. Geometry and
visibility are recomputed per grid; no proxy displacement, corrected preview
RGB, or invented higher-resolution semantic detail is promoted to export.

Let `up=normalize(forehead10-chin152)` and `lateral=(-up_y,up_x)`. The head
span must be at least 64 source pixels. Ordered bridge observations
168,6,197,195,5,4,1 must be consistent with this independent axis: projected
span in [0.08,0.5] head spans, alignment at least 0.90, backward step no more
than 0.005 head spans, lateral distance no more than 0.12 head spans, and
ordered endpoint positions strictly between 0.1 and 0.85 head spans.

Using the eye-to-eye or iris-to-iris vector as the correction axis would make
the measured level difference zero by definition and is forbidden here. The
old eye evidence routine may use its own axis for conservative vetoes only;
its returned axis never supplies the new measurement or correction frame.

For each side, c is the midpoint of its two observed lid corners, w their
Euclidean distance, and H the full lid ring's projected range along up. The
host requires w>=24px, H>=4px, H/w in [0.10,0.65], sufficient corner ordering,
an iris center inside the lid polygon and resolved retained iris points.
Inter-eye lateral center separation must lie strictly in (0.12,0.8) head
spans. Duplicate/degenerate/self-crossing lid rings refuse. All are local
admission policies, not clinical facial measurements.

Opening area A is the absolute shoelace area of the **actual ordered 16-point
lid polygon**, evaluated after centering the ring for translation stability.
Area must be at least 12 square source pixels. Width alone, iris radius,
bounding-box area, an ellipse template or estimated eyeball volume is not A.
The head-up level difference is `d=(c_left-c_right) dot up`, not screen-y and
not an eye-center-line-relative difference.

## Independent level target and size-only reference target

For horizontal strength h, the desired translations along up are:

- Left: `t_left=-0.5*h*d`.
- Right: `t_right=+0.5*h*d`.

In exact arithmetic, the midpoint level and lateral center coordinates stay
fixed, and the level difference becomes `(1-h)*d`. At h=1 both measured corner
centers reach their common mean head-relative level. This policy translates
all 21 points of each eye and does not alter its measured area. It is not
spacing adjustment. Reference never affects these translations.

For size strength a, automatic reference is the greater opening area; an
exact tie deterministically resolves to subject-left and yields no size
motion. Explicit left/right overrides this selection for size only. Let r
be the reference eye and o the other eye:

`s_reference=1; s_other=1+a*(sqrt(A_reference/A_other)-1)`.

The other eye's full 21-point group scales isotropically about its observed
corner center. In exact arithmetic its area becomes `A_other*s_other^2` and
at a=1 equals the reference area. Strength is linear in scale, not in area.
A manually selected smaller reference can shrink the other eye. Area equality
does not force equal width, height, shape, iris texture or anatomical identity.

Combined desired forward motion for each source point p is

`delta=(s_side-1)*(p-c_side)+t_side*up`.

Reference-eye size invariance does not imply positional invariance when level
correction is also enabled. Both level translations still apply. These targets
are source-domain contracts, not guaranteed final-image symmetry after
arbitrary earlier overlapping eye/face geometry.

## Unchanged shared Rust controls, no second implementation

`eye_symmetry_native.controls(points, frame, scale=..., shift=...)` delegates
to `eye_shape_native.controls`, which calls the unchanged ABI-1
`lrt_eye_shape_controls` in `bin/liblrt_eye_shape.so`. There is no symmetry
binary, loader cache, build step, runtime compilation, Python offset fallback,
new solver, model, inference or download.

Points must be an exact native-endian NumPy float64 ndarray [N,2], N=1..256.
The host supplies the actual 21-point group. Frame must be an exact native
float64 ndarray [10], with this unchanged order:

`[outward_x,outward_y,up_x,up_y,c_x,c_y,iris_x,iris_y,width,height]`.

Both shapes/dtypes are checked before copying. Private, contiguous, read-only
snapshots are made for points and frame. Finiteness, unchanged frame constraints
and all subsequent delegation use those same private snapshots. Strided,
read-only and overlapping caller arrays are acceptable because the delegated
inputs are independent. The caller must not mutate during copying.

The adapter does not repair or renormalize axes. It preserves the old ABI's
unit-squared-norm and orthogonality tolerance 1e-6 and width/height>=1 bounds.
Geometry construction supplies its independently normalized axes; the host's
requested-target audit, not a loose frame tolerance, controls actual accuracy.

Scale and shift are exact built-in finite numbers, not booleans or NumPy
scalars. The adapter creates the unchanged ten-slot value vector with only

`values[0]=(scale-1)/0.12; values[9]=shift/(0.08*width)`.

All other controls and both role weights are exactly zero. The old size and
position terms do not consume the role weights. The Rust core alone produces
the actual forward offsets. Computing measurement-to-control conversion or
checking requested targets is not a separate deformation implementation.

Every converted control must remain in the original strict [-1,1] interval.
No control is clipped, weakened or rewritten and no supported width is enlarged
to rescue it. A nonzero shift that converts to zero refuses. Floating endpoint
behavior is literal: a nominal scale 1.12 can convert just above 1 because of
rounding and must then refuse rather than be silently clamped.

In real arithmetic these limits imply scale in [0.88,1.12] and absolute shift
at most 0.08*w for each side. Thus horizontal correction requires
`h*abs(d) <= 0.16*min(w_left,w_right)`. At full automatic size strength the
larger-to-smaller area ratio must be no more than 1.12 squared (1.2544), apart
from the stricter literal floating conversion. These are admitted-control
limits, not an instruction to cap an otherwise excessive source request.
The original native per-point displacement limit 0.30*w also remains.

`available()` invokes the actual shared loader, ABI function and required
control symbol. A path that merely exists is not capability. `capability()`
returns `eye_symmetry_available` and `eye_symmetry_reason`, not anatomical,
photographic or final-render availability. Errors identify the shared eye-shape
core rather than pretending a separate symmetry library exists.

The original C boundary assumes live, correctly sized, nonoverlapping input
and output extents; its simple ABI does not establish allocation provenance,
contain invalid foreign pointers or prove thread safety. This adapter supplies
bounded private input arrays and the shared bridge allocates a separate output.
No claim is made that the unchanged Rust ABI has new memory-safety mechanisms.
Its statuses remain 1 invalid count/null pointer, 2 nonfinite/range, 3 frame,
4 displacement bound, 5 nonfinite output, and 0 success. It prepares output
before copying on success. No partial failed offset array is published.

The adapter checks exact output ndarray shape/dtype, finite values, original
displacement bound and exact zero for identity controls, then publishes an
owned writable contiguous float64 result. A successful all-zero result is not
automatically rejected: the host decides whether it matches actual requested
targets. Direct identity evaluation still loads native; portable neutral does
not. No source/cache availability is inferred from output nonzeroness.

## Existing inverse TPS, guards and finite admission

The host checks every native point offset against the full requested target:
relative tolerance 1e-10 for moving points and exact zero for zero targets.
A nonzero displacement that disappears when added to a source point refuses.
Moving targets, original source points and complete compact support must stay
inside the genuine image margin. Same-source foreign-face boxes, including
retained disabled faces, guard source/target coordinates and whole support
bounding rectangles, not only nominal eye points.

For each moved eye the unchanged compact window encloses both source and
target groups: flat radius is their maximum radius about the combined mean
plus 0.04*w; the feather adds 0.25*w. Existing nose, brow and outer-lip
protection polygons and zero landmark/border anchors are retained. An unmoved
reference opening is protected continuously, not just at its 21 points.
These polygons are not complete anatomical segmentation, and the compact
halo can affect nearby tissue. Moving controls conflicting with protection
anchors refuse instead of being silently averaged by deduplication.

The unchanged `EyeField` consumes controls at target coordinates
`P=source+delta`, with inverse displacement `D(P)=delta`. Its established
regularized TPS interpolates the destination-to-source pullback
`source(q)=q-D(q)`. It is not a global analytical inverse of a new forward
field, and regularization/protection need not interpolate exact real targets.
The new host audits the unmerged requested controls after all protection:
moving-point error <=1e-4 of its requested displacement and zero-pin error
<=1e-7 source pixels. Failure refuses, never attenuates or adds an alternative
solver. Very small or tightly protected corrections may therefore refuse.

The unchanged fold admission samples 33x33 finite-difference probes over each
support and refuses determinant below 0.15. The existing canonical combined
map also checks its sampled pixel-grid Jacobians. These are **sampled numerical
admission, not mathematical global injectivity or no-fold guarantees between
samples**. No photographic safety, naturalness, performance or success-rate
claim follows from those finite checks.

The new source-owned field retains immutable numeric geometry and owned facts, never
caller RGB or masks as a portable cache. Actual nonzero evaluation checks both
q and q-D(q) against source/foreign-face guards. Original field/core modules
and their cache ownership remain unchanged.

## Canonical order, identity and cache boundaries

The new operation appends after the established prefix, including optional
philtrum, preserving the original fields by identity and legacy mouth slot 3.
For symmetry displacement S and prefix displacement P, total pullback is

`T(q)=S(q)+P(q-S(q))`.

The single final RGB/mask sampler reads q-T(q). Prefix displacements are
evaluated at the actual off-grid intermediate coordinates, not added as two
independently sampled dense fields. Output q, intermediate q-S and actual
source q-T are guarded when symmetry changes the map; baseline-prefix
comparison prevents cancellation from hiding a changed footprint.

Exact neutral returns the original prefix object without new analysis or
field work. Active measured identity can retain facts with TPS state None;
it leaves the prefix map unchanged but is not portable neutral. Source-owned
analysis, exact FaceRef, current effective source, recipe, history, cancellation
and preview/export owners retain their established invalidation rules. No
new source-agnostic field cache is introduced. A source/owner/reference/strength
change must never reuse another target's measurements or resolved reference.

Source protection does not promise invariance after arbitrary prior geometry:
that prefix may have moved texture into the protected region or feather.
The implementation reports this limitation rather than changing old requests
to force final symmetry. It does not introduce a second image sampler.

## Preserved source hashes and unpassed gates

The following shared files were read and hashed, not modified by this slice:

| Shared source | SHA-256 |
| --- | --- |
| `core/eye_shape/lib.rs` | `3817392fc8f44974b1fa7215c067e3fe966e813f76a2299bbc66afe142eb0a65` |
| `engine/src/lumaretouch_engine/eye_shape_native.py` | `32f3dc6925d628203e9a7b057a02a5d75af72b3a7f60a6de82a4af25c10faf3d` |
| `engine/src/lumaretouch_engine/eye_shape_field.py` | `0dec74c9a8f91b5d0dd10c101864964ac4c1701e28d797a37e699f22697c87d7` |

New source is original GPL-3.0-or-later. Existing shared controls, TPS and
sampler are project code. The [primary scikit-image TPS example](https://scikit-image.org/docs/stable/auto_examples/transform/plot_tps_deformation.html)
is methodological context for inverse warping, not copied code or an added
dependency. Official documentation establishes feature semantics only. No
model weights, reference images, external implementation or new binary is
downloaded or bundled here; prior producer/model license gates remain.

`test_eye_symmetry_native_unrun.py` authors strict state/schema/reference-only
neutral behavior, real ABI/symbol capability, exact converted slots, native
float64 shapes/counts, private snapshot ownership, finite/frame/bound checks,
literal endpoint and underflow refusal, native failure propagation, output
postconditions and identity acceptance using fixed-output doubles. Optional
installed-core fixtures cover exact identity, signed translation, isotropic
scale, roll/mirror/uniform-scale/translation covariance and bounded point
counts. Missing native skips those fixtures, never builds or substitutes it.

All new fixtures remain **UNRUN**, including source geometry, canonical
integration, transfer, reset, history, preview and export suites. No import,
test collection, typecheck, build, inference, numerical evaluation, real-photo
review or performance run has occurred for this slice. Strict tolerance
refusal prevalence, arbitrary composition appearance and product acceptance
remain open, and this does not close the whole portrait workflow.
